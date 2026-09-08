"""FR-5 tests: YAML load/dump round-trip."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from agenticx_oag.ontology import Ontology, dump_ontology, load_ontology


def test_yaml_roundtrip(sample_ontology: Ontology, tmp_path: Path) -> None:
    first = tmp_path / "first.yaml"
    second = tmp_path / "second.yaml"

    dump_ontology(sample_ontology, first)
    loaded1 = load_ontology(first)

    dump_ontology(loaded1, second)
    loaded2 = load_ontology(second)

    assert loaded1.model_dump() == sample_ontology.model_dump()
    assert loaded2.model_dump() == loaded1.model_dump()
    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")


def test_yaml_top_level_keys(sample_ontology: Ontology, tmp_path: Path) -> None:
    path = tmp_path / "onto.yaml"
    dump_ontology(sample_ontology, path)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert list(document) == [
        "namespace",
        "version",
        "object_types",
        "link_types",
        "action_types",
        "metadata",
    ]
    assert document["namespace"] == "test.core"
    assert document["version"] == "1.2.3"
    assert document["metadata"] == {"source": "unit-test"}


def test_yaml_enum_literals(sample_ontology: Ontology, tmp_path: Path) -> None:
    path = tmp_path / "onto.yaml"
    dump_ontology(sample_ontology, path)
    text = path.read_text(encoding="utf-8")
    assert "data_type: TIMESTAMP" in text
    assert "data_type: DOUBLE" in text
    assert "data_type: JSON" in text
    assert "cardinality: ONE_TO_MANY" in text
    assert "enum_values:" in text
    # unicode display names survive the round-trip
    assert "客户" in text


def test_load_accepts_str_and_path(sample_ontology: Ontology, tmp_path: Path) -> None:
    path = tmp_path / "onto.yaml"
    dump_ontology(sample_ontology, path)
    assert load_ontology(str(path)).model_dump() == load_ontology(path).model_dump()


def test_load_empty_document_raises(tmp_path: Path) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_ontology(path)
