"""FR-8 tests: prototype scene JSON -> ontology YAML conversion."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from agenticx_oag.ontology import Ontology, dump_ontology, load_ontology

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENE_PATH = REPO_ROOT / "prototype" / "scenes" / "bank-aml.json"
CONVERTER_PATH = REPO_ROOT / "scripts" / "scene_to_ontology.py"

EXPECTED_OBJECT_TYPES = [
    "Customer",
    "Account",
    "Transaction",
    "SuspiciousTxn",
    "LoanApplication",
    "Collateral",
    "SanctionHit",
    "DueDiligence",
]
EXPECTED_LINK_TYPES = [
    "owns",
    "initiates",
    "flaggedAs",
    "applies",
    "securedBy",
    "hitsSanction",
    "reviewedBy",
    "risk",
]


def test_bank_aml_conversion(converter: Any) -> None:
    ontology: Ontology = converter.convert_scene(
        SCENE_PATH, namespace="finance.aml", version="0.1.0"
    )

    assert [ot.api_name for ot in ontology.object_types] == EXPECTED_OBJECT_TYPES
    assert [lt.api_name for lt in ontology.link_types] == EXPECTED_LINK_TYPES

    # load + validate must pass (FR-8 AC)
    assert ontology.validate() is None


def test_bank_aml_conversion_details(converter: Any) -> None:
    ontology: Ontology = converter.convert_scene(
        SCENE_PATH, namespace="finance.aml", version="0.1.0"
    )

    # every object type defaults its primary key to "id"
    assert all(ot.primary_key == ["id"] for ot in ontology.object_types)

    # "amount"/"status" relKeywords are attribute names, not links
    link_names = {lt.api_name for lt in ontology.link_types}
    assert "amount" not in link_names
    assert "status" not in link_names

    # link endpoints are all declared object types
    object_type_names = {ot.api_name for ot in ontology.object_types}
    for link in ontology.link_types:
        assert link.source_type in object_type_names
        assert link.target_type in object_type_names

    # data-type inference rules (FR-8)
    customer = next(ot for ot in ontology.object_types if ot.api_name == "Customer")
    risk_level = next(p for p in customer.properties if p.api_name == "riskLevel")
    est_year = next(p for p in customer.properties if p.api_name == "estYear")
    assert risk_level.data_type.value == "STRING"
    assert est_year.data_type.value == "DOUBLE"  # numeric key

    account = next(ot for ot in ontology.object_types if ot.api_name == "Account")
    open_date = next(p for p in account.properties if p.api_name == "openDate")
    assert open_date.data_type.value == "TIMESTAMP"  # key contains "date"

    suspicious = next(ot for ot in ontology.object_types if ot.api_name == "SuspiciousTxn")
    detected = next(p for p in suspicious.properties if p.api_name == "detected")
    assert detected.data_type.value == "TIMESTAMP"  # date-like string values


def test_bank_aml_yaml_roundtrip(converter: Any, tmp_path: Path) -> None:
    ontology: Ontology = converter.convert_scene(
        SCENE_PATH, namespace="finance.aml", version="0.1.0"
    )
    path = tmp_path / "ontology.yaml"
    dump_ontology(ontology, path)
    loaded = load_ontology(path)
    assert loaded.model_dump() == ontology.model_dump()
    assert loaded.validate() is None


def test_committed_template_artifact() -> None:
    """The committed template (converter output + display/description/enum tweaks) stays valid."""
    artifact = REPO_ROOT / "templates" / "finance" / "aml" / "ontology.yaml"
    ontology = load_ontology(artifact)
    assert [ot.api_name for ot in ontology.object_types] == EXPECTED_OBJECT_TYPES
    assert [lt.api_name for lt in ontology.link_types] == EXPECTED_LINK_TYPES
    assert ontology.validate() is None
    # the plan's sample: riskLevel is an enum on Customer
    customer = ontology.object_types[0]
    risk_level = next(p for p in customer.properties if p.api_name == "riskLevel")
    assert risk_level.enum_values == ["low", "medium", "high"]


def _write_scene(tmp_path: Path, scene: dict[str, Any]) -> Path:
    path = tmp_path / "scene.json"
    path.write_text(json.dumps(scene, ensure_ascii=False), encoding="utf-8")
    return path


def test_data_type_inference_rules(converter: Any, tmp_path: Path) -> None:
    scene = {
        "id": "inference",
        "types": {"Widget": {"label": "小部件"}},
        "relKeywords": {"relatesTo": ["关联"]},
        "nodes": [
            {
                "id": "W-1",
                "type": "Widget",
                "name": "w1",
                "props": {
                    "flag": True,
                    "amount": 10,
                    "updatedAt": "v1",
                    "createdAt": "2026-01-01",
                    "detected": "2026-01-02",
                    "note": "hello",
                },
            },
            {
                "id": "W-2",
                "type": "Widget",
                "name": "w2",
                "props": {
                    "flag": False,
                    "amount": 2.5,
                    "updatedAt": "v2",
                    "createdAt": "2026-01-03",
                    "detected": "2026-01-04",
                    "note": "world",
                },
            },
        ],
        "edges": [
            {"source": "W-1", "target": "W-2", "rel": "relatesTo", "label": "关联"}
        ],
    }
    ontology: Ontology = converter.convert_scene(
        _write_scene(tmp_path, scene), namespace="test.scene"
    )
    widget = ontology.object_types[0]
    data_types = {p.api_name: p.data_type.value for p in widget.properties}
    assert data_types["flag"] == "BOOL"
    assert data_types["amount"] == "DOUBLE"
    assert data_types["updatedAt"] == "TIMESTAMP"  # key contains "date"
    assert data_types["createdAt"] == "TIMESTAMP"  # date-like string values
    assert data_types["detected"] == "TIMESTAMP"  # date-like string values
    assert data_types["note"] == "STRING"
    assert widget.primary_key == ["id"]


def test_primary_key_fallback(converter: Any, tmp_path: Path) -> None:
    # No node-level "id" field -> no id property; primary_key falls back to the
    # first required property (with a WARNING in the converter log).
    scene = {
        "id": "nokeys",
        "types": {"Widget": {"label": "小部件"}},
        "relKeywords": {"risk": ["风险"]},
        "propMap": {"risk": [["score"], "风险分"]},
        "nodes": [
            {"type": "Widget", "name": "w1", "props": {"score": 5, "code": "A"}},
            {"type": "Widget", "name": "w2", "props": {"score": 3, "code": "B"}},
        ],
        "edges": [],
    }
    ontology: Ontology = converter.convert_scene(
        _write_scene(tmp_path, scene), namespace="test.scene"
    )
    widget = ontology.object_types[0]
    assert "id" not in {p.api_name for p in widget.properties}
    assert widget.primary_key == ["name"]  # first required property


def test_cli_conversion(tmp_path: Path) -> None:
    out_path = tmp_path / "templates" / "finance" / "aml" / "ontology.yaml"
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH")}
    result = subprocess.run(
        [
            sys.executable,
            str(CONVERTER_PATH),
            str(SCENE_PATH),
            "--namespace",
            "finance.aml",
            "--version",
            "0.1.0",
            "--out",
            str(out_path),
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    ontology = load_ontology(out_path)
    assert [ot.api_name for ot in ontology.object_types] == EXPECTED_OBJECT_TYPES
    assert [lt.api_name for lt in ontology.link_types] == EXPECTED_LINK_TYPES
    assert ontology.validate() is None
    assert "Approver" in result.stderr  # dropped types are reported


def test_cli_stdout(tmp_path: Path) -> None:
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH")}
    result = subprocess.run(
        [
            sys.executable,
            str(CONVERTER_PATH),
            str(SCENE_PATH),
            "--namespace",
            "finance.aml",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    document = yaml.safe_load(result.stdout)
    assert document["namespace"] == "finance.aml"
    assert len(document["object_types"]) == 8
    assert len(document["link_types"]) == 8


@pytest.mark.parametrize(
    "scene_name",
    ["power-grid", "supply-chain", "workshop"],
)
def test_other_scenes_convert(converter: Any, tmp_path: Path, scene_name: str) -> None:
    """The converter is generic: every prototype scene yields a valid ontology."""
    scene_path = REPO_ROOT / "prototype" / "scenes" / f"{scene_name}.json"
    ontology: Ontology = converter.convert_scene(
        scene_path, namespace=f"prototype.{scene_name.replace('-', '_')}"
    )
    assert ontology.validate() is None
    assert ontology.object_types
