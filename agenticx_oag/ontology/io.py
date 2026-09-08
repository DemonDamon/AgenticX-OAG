"""YAML persistence for the ontology model (FR-5).

Top-level document keys mirror the model fields:
``namespace / version / object_types / link_types / action_types / metadata``.
Round-trip guarantee: ``load_ontology`` -> ``dump_ontology`` -> ``load_ontology``
yields a model whose ``model_dump()`` is equal to the original's.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from agenticx_oag.ontology.model import Ontology


class _IndentedSafeDumper(yaml.SafeDumper):
    """SafeDumper variant that indents block sequences under mapping keys."""

    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        super().increase_indent(flow, False)


def to_yaml(ontology: Ontology) -> str:
    """Serialize an ontology to a YAML document (unicode-preserving)."""
    return yaml.dump(
        ontology.model_dump(mode="json"),
        Dumper=_IndentedSafeDumper,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=120,
    )


def load_ontology(path: str | Path) -> Ontology:
    """Load an ontology from a YAML file (UTF-8)."""
    data: Any = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Ontology.model_validate(data)


def dump_ontology(ontology: Ontology, path: str | Path) -> None:
    """Write an ontology to a YAML file (UTF-8)."""
    Path(path).write_text(to_yaml(ontology), encoding="utf-8")
