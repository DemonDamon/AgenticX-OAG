#!/usr/bin/env python3
"""Convert a prototype scene JSON into an ontology YAML document (FR-8).

Usage::

    python scripts/scene_to_ontology.py prototype/scenes/bank-aml.json \
        --namespace finance.aml --version 0.1.0 --out templates/finance/aml/ontology.yaml

Verified scene format (see ``prototype/scenes/*.json``)::

    types:       {TypeName: {"label": str, "color": str}}
    relKeywords: {concept: [str, ...]}          # NLU keyword lists
    propMap:     {concept: [[propPath, ...], label]}
    nodes:       [{"id", "type", "name", "props": {...}}]
    edges:       [{"source", "target", "rel", "label"}]

Conversion rules
---------------
LinkTypes
    Every ``relKeywords`` key that is **not** an attribute name observed in the
    instance data (keywords such as "amount"/"status" that collide with real
    property keys denote property concepts, not relations). The
    (source_type, target_type) pair is the most frequently observed edge pair
    for that relation (ties: first observed); edge-less keywords (e.g. "risk")
    are materialized as a self-relation on the object type owning their
    propMap property. Cardinality: MANY_TO_MANY when several edges converge on
    the same target node, else ONE_TO_MANY.

ObjectTypes
    Entries of ``types`` referenced by at least one derived LinkType; types
    only appearing in secondary edge pairs are dropped with a warning.
    Properties are inferred from the instances: the node-level ``id``/``name``
    fields plus every key found in ``props`` (first-seen order); a property is
    required when present on every instance of the type. Display names come
    from ``types[x].label``, propMap labels, or edge labels.

Data types (FR-8)
    all-bool values -> BOOL; key contains date/time -> TIMESTAMP; all-numeric
    values -> DOUBLE; date-like string values -> TIMESTAMP; numeric key names
    (amount/risk/score/...) -> DOUBLE; otherwise STRING.

Primary key
    "id" when the type has one; otherwise the first required property (WARNING).
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from agenticx_oag.ontology.errors import OntologyError
from agenticx_oag.ontology.io import dump_ontology, to_yaml
from agenticx_oag.ontology.model import (
    Cardinality,
    DataType,
    LinkType,
    ObjectType,
    Ontology,
    PropertyType,
)

LOGGER = logging.getLogger(__name__)

_DATE_LIKE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?$")
_NUMERIC_KEY_NAMES = frozenset(
    {"amount", "risk", "score", "balance", "value", "price", "cost", "count", "total", "rate"}
)


def _infer_data_type(prop_name: str, values: list[Any]) -> DataType:
    """Infer a DataType for a property from its key name and observed values."""
    non_null = [value for value in values if value is not None]
    if non_null and all(isinstance(value, bool) for value in non_null):
        return DataType.BOOL
    lowered = prop_name.lower()
    if "date" in lowered or "time" in lowered:
        return DataType.TIMESTAMP
    if non_null and all(
        isinstance(value, (int, float)) and not isinstance(value, bool) for value in non_null
    ):
        return DataType.DOUBLE
    if non_null and all(
        isinstance(value, str) and _DATE_LIKE_PATTERN.match(value.strip()) for value in non_null
    ):
        return DataType.TIMESTAMP
    if prop_name in _NUMERIC_KEY_NAMES:
        return DataType.DOUBLE
    return DataType.STRING


def _prop_display_labels(prop_map: dict[str, Any]) -> dict[str, str]:
    """Reverse propMap into {propPath: label}."""
    labels: dict[str, str] = {}
    for spec in prop_map.values():
        if (
            isinstance(spec, list)
            and len(spec) == 2
            and isinstance(spec[0], list)
            and isinstance(spec[1], str)
        ):
            for path in spec[0]:
                if isinstance(path, str):
                    labels.setdefault(path, spec[1])
    return labels


def _prop_map_paths(prop_map: dict[str, Any], concept: str) -> list[str]:
    spec = prop_map.get(concept)
    if isinstance(spec, list) and spec and isinstance(spec[0], list):
        return [path for path in spec[0] if isinstance(path, str)]
    return []


def _prop_map_label(prop_map: dict[str, Any], concept: str) -> str:
    spec = prop_map.get(concept)
    if isinstance(spec, list) and len(spec) == 2 and isinstance(spec[1], str):
        return spec[1]
    return ""


def convert_scene(scene_path: str | Path, namespace: str, version: str = "0.1.0") -> Ontology:
    """Convert a prototype scene JSON file into a validated Ontology."""
    scene: dict[str, Any] = json.loads(Path(scene_path).read_text(encoding="utf-8"))

    types_config: dict[str, Any] = scene.get("types") or {}
    rel_keywords: dict[str, Any] = scene.get("relKeywords") or {}
    prop_map: dict[str, Any] = scene.get("propMap") or {}
    nodes: list[dict[str, Any]] = scene.get("nodes") or []
    edges: list[dict[str, Any]] = scene.get("edges") or []

    node_type_by_id = {
        node["id"]: node.get("type") for node in nodes if node.get("id") and node.get("type")
    }

    # Observed property values per type: {type: {prop: [values...]}}.
    # The node-level id/name fields become regular properties.
    values_by_type: dict[str, dict[str, list[Any]]] = defaultdict(lambda: defaultdict(list))
    instance_counts: Counter[str] = Counter()
    for node in nodes:
        type_name = node.get("type")
        if not type_name:
            continue
        instance_counts[type_name] += 1
        values = values_by_type[type_name]
        for field in ("id", "name"):
            if field in node:
                values[field].append(node[field])
        for key, value in (node.get("props") or {}).items():
            values[key].append(value)

    observed_prop_names = {key for values in values_by_type.values() for key in values}
    prop_labels = _prop_display_labels(prop_map)

    # Edge-derived statistics per relation: type-pair counts, target-node counts, labels.
    pair_counts: dict[str, Counter[tuple[str, str]]] = defaultdict(Counter)
    target_counts: dict[str, Counter[str]] = defaultdict(Counter)
    edge_labels: dict[str, Counter[str]] = defaultdict(Counter)
    for edge in edges:
        rel = edge.get("rel")
        source_type = node_type_by_id.get(edge.get("source"))
        target_type = node_type_by_id.get(edge.get("target"))
        if not rel or not source_type or not target_type:
            continue
        if source_type in types_config and target_type in types_config:
            pair_counts[rel][(source_type, target_type)] += 1
        target_counts[rel][edge.get("target", "")] += 1
        edge_labels[rel][edge.get("label") or ""] += 1

    def _edgeless_pair(rel: str) -> tuple[str, str] | None:
        """Pair for a keyword without edges: self-relation on the propMap owner."""
        owners: list[str] = []
        for path in _prop_map_paths(prop_map, rel):
            for type_name in types_config:
                if path in values_by_type.get(type_name, {}):
                    owners.append(type_name)
            if owners:
                owner = max(owners, key=lambda name: instance_counts.get(name, 0))
                return owner, owner
        return None

    # --- LinkTypes (relKeywords order preserved) ---
    link_types: list[LinkType] = []
    for rel in rel_keywords:
        if rel in observed_prop_names:
            LOGGER.info(
                "relKeyword %r is also an attribute name in the scene data; "
                "treating it as a property concept, not a link",
                rel,
            )
            continue
        counts = pair_counts.get(rel)
        if counts:
            pair = counts.most_common(1)[0][0]
            max_in = max(target_counts[rel].values(), default=0)
            cardinality = Cardinality.MANY_TO_MANY if max_in >= 2 else Cardinality.ONE_TO_MANY
            labels = edge_labels[rel]
            display_name = labels.most_common(1)[0][0] if labels else rel
        else:
            pair = _edgeless_pair(rel)
            if pair is None:
                LOGGER.warning(
                    "relation %r has no edges and no propMap property owner; skipped", rel
                )
                continue
            LOGGER.info(
                "relation %r has no edges; emitted as a self-relation on %r "
                "(owner of its propMap property)",
                rel,
                pair[0],
            )
            cardinality = Cardinality.MANY_TO_MANY
            display_name = _prop_map_label(prop_map, rel) or rel
        link_types.append(
            LinkType(
                api_name=rel,
                display_name=display_name,
                source_type=pair[0],
                target_type=pair[1],
                cardinality=cardinality,
            )
        )

    referenced_types = {lt.source_type for lt in link_types}
    referenced_types.update(lt.target_type for lt in link_types)

    # --- ObjectTypes (types order preserved) ---
    object_types: list[ObjectType] = []
    for type_name, config in types_config.items():
        if type_name not in referenced_types:
            LOGGER.warning(
                "object type %r is not referenced by any derived LinkType; skipped", type_name
            )
            continue
        object_types.append(
            _build_object_type(type_name, config, values_by_type.get(type_name, {}),
                               instance_counts.get(type_name, 0), prop_labels)
        )

    ontology = Ontology(
        namespace=namespace,
        version=version,
        object_types=object_types,
        link_types=link_types,
        metadata={
            "source_scene": str(scene.get("id") or Path(scene_path).stem),
            "source_file": str(scene_path),
        },
    )
    ontology.validate()
    return ontology


def _build_object_type(
    type_name: str,
    config: Any,
    values: dict[str, list[Any]],
    instance_count: int,
    prop_labels: dict[str, str],
) -> ObjectType:
    """Build one ObjectType from its label config and observed property values."""
    display_name = config.get("label", type_name) if isinstance(config, dict) else type_name

    properties: list[PropertyType] = []
    for prop_name, prop_values in values.items():
        properties.append(
            PropertyType(
                api_name=prop_name,
                display_name=prop_labels.get(prop_name, prop_name),
                data_type=_infer_data_type(prop_name, prop_values),
                required=instance_count > 0 and len(prop_values) >= instance_count,
            )
        )

    prop_names = [prop.api_name for prop in properties]
    primary_key: list[str]
    if "id" in prop_names:
        primary_key = ["id"]
    else:
        required_props = [prop.api_name for prop in properties if prop.required]
        if required_props:
            primary_key = [required_props[0]]
            LOGGER.warning(
                "object type %r has no 'id' property; using first required property %r "
                "as primary_key",
                type_name,
                required_props[0],
            )
        else:
            primary_key = []
            LOGGER.warning(
                "object type %r has no 'id' and no required property; primary_key left empty",
                type_name,
            )

    return ObjectType(
        api_name=type_name,
        display_name=display_name,
        properties=properties,
        primary_key=primary_key,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert a prototype scene JSON into an ontology YAML document."
    )
    parser.add_argument("scene", help="path to the prototype scene JSON file")
    parser.add_argument("--namespace", required=True, help="ontology namespace, e.g. finance.aml")
    parser.add_argument("--version", default="0.1.0", help="semantic version (default: 0.1.0)")
    parser.add_argument("--out", default=None, help="output YAML path (default: stdout)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        ontology = convert_scene(args.scene, namespace=args.namespace, version=args.version)
    except OntologyError as error:
        LOGGER.error("conversion failed: %s", error)
        return 1

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        dump_ontology(ontology, out_path)
        print(f"wrote {out_path} ({len(ontology.object_types)} object types, "
              f"{len(ontology.link_types)} link types)")
    else:
        sys.stdout.write(to_yaml(ontology))
    return 0


if __name__ == "__main__":
    sys.exit(main())
