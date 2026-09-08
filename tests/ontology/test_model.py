"""FR-1/FR-2/FR-3/FR-4 tests for the ontology Pydantic model."""

from __future__ import annotations

import subprocess
import sys

import pytest

from agenticx_oag.ontology import (
    ActionType,
    DataType,
    LinkType,
    ObjectType,
    Ontology,
    OntologyValidationError,
    PropertyType,
)


def _prop(api_name: str = "riskLevel", **overrides: object) -> PropertyType:
    kwargs: dict[str, object] = {
        "api_name": api_name,
        "display_name": "风险等级",
        "enum_values": ["low", "high"],
    }
    kwargs.update(overrides)
    return PropertyType(**kwargs)  # type: ignore[arg-type]


def _object_type(api_name: str = "Customer", **overrides: object) -> ObjectType:
    kwargs: dict[str, object] = {
        "api_name": api_name,
        "display_name": "客户",
        "properties": [_prop("id", display_name="ID", enum_values=[], required=True)],
        "primary_key": ["id"],
    }
    kwargs.update(overrides)
    return ObjectType(**kwargs)  # type: ignore[arg-type]


def _ontology(**overrides: object) -> Ontology:
    kwargs: dict[str, object] = {
        "namespace": "test.core",
        "version": "0.1.0",
        "object_types": [_object_type(), _object_type("Account")],
        "link_types": [
            LinkType(
                api_name="owns",
                display_name="持有",
                source_type="Customer",
                target_type="Account",
            )
        ],
    }
    kwargs.update(overrides)
    return Ontology(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------- FR-1 mirrors


def test_field_names_mirror_proto_contract() -> None:
    # proto message fields, verbatim.
    assert list(PropertyType.model_fields) == [
        "api_name",
        "display_name",
        "data_type",
        "required",
        "description",
        "enum_values",
    ]
    assert list(ObjectType.model_fields) == [
        "api_name",
        "display_name",
        "properties",
        "primary_key",
        "parent",
        "description",
    ]
    assert list(LinkType.model_fields) == [
        "api_name",
        "display_name",
        "source_type",
        "target_type",
        "cardinality",
        "properties",
    ]
    assert list(ActionType.model_fields) == [
        "api_name",
        "display_name",
        "target_types",
        "parameters",
        "preconditions",
        "approval_policy",
        "rollback_handler",
    ]
    assert list(Ontology.model_fields) == [
        "namespace",
        "version",
        "object_types",
        "link_types",
        "action_types",
        "metadata",
    ]


def test_defaults_and_enum_literals() -> None:
    prop = PropertyType(api_name="note", display_name="备注")
    assert prop.data_type is DataType.STRING
    assert prop.required is False
    assert prop.description == ""
    assert prop.enum_values == []
    assert LinkType.model_fields["cardinality"].default is not None
    # YAML/JSON literals mirror the proto enum value names.
    assert prop.model_dump(mode="json")["data_type"] == "STRING"
    assert [member.value for member in DataType] == [
        "STRING",
        "DOUBLE",
        "INT64",
        "BOOL",
        "TIMESTAMP",
        "JSON",
    ]


# ---------------------------------------------------------------- FR-2 naming


@pytest.mark.parametrize(
    ("model", "bad_name"),
    [
        (ObjectType, "customer"),
        (ObjectType, "Customer Type"),
        (LinkType, "Owns"),
        (ActionType, "FreezeAccount"),
    ],
)
def test_name_validation_rejects_bad_api_names(model: type, bad_name: str) -> None:
    kwargs: dict[str, object] = {"api_name": bad_name, "display_name": "x"}
    if model is LinkType:
        kwargs.update(source_type="Customer", target_type="Account")
    if model is ObjectType:
        kwargs.update(properties=[], primary_key=[])
    with pytest.raises(OntologyValidationError):
        model(**kwargs)  # type: ignore[call-arg]


def test_name_validation_accepts_valid_api_names() -> None:
    assert _prop("riskLevel").api_name == "riskLevel"
    assert _object_type("SuspiciousTxn").api_name == "SuspiciousTxn"


def test_property_type_name_validation() -> None:
    with pytest.raises(OntologyValidationError, match="camelCase"):
        _prop("RiskLevel")


# ---------------------------------------------------- FR-3 reference integrity


def test_reference_integrity_dangling_link() -> None:
    ontology = _ontology(
        link_types=[
            LinkType(
                api_name="hitsSanction",
                display_name="命中制裁",
                source_type="Customer",
                target_type="SanctionHit2",
            )
        ]
    )
    with pytest.raises(OntologyValidationError, match="SanctionHit2"):
        ontology.validate()


def test_reference_integrity_dangling_source_link() -> None:
    ontology = _ontology(
        link_types=[
            LinkType(
                api_name="owns",
                display_name="持有",
                source_type="Ghost",
                target_type="Account",
            )
        ]
    )
    with pytest.raises(OntologyValidationError, match="Ghost"):
        ontology.validate()


def test_reference_integrity_primary_key_not_required() -> None:
    ontology = _ontology(
        object_types=[
            _object_type(
                properties=[
                    _prop("id", display_name="ID", enum_values=[], required=True),
                    _prop("riskLevel"),
                ],
                primary_key=["riskLevel"],
            ),
            _object_type("Account"),
        ]
    )
    with pytest.raises(OntologyValidationError, match="must reference a required property"):
        ontology.validate()


def test_reference_integrity_primary_key_unknown_property() -> None:
    ontology = _ontology(
        object_types=[_object_type(primary_key=["nope"]), _object_type("Account")]
    )
    with pytest.raises(OntologyValidationError, match="does not reference an existing property"):
        ontology.validate()


def test_reference_integrity_parent_cycle() -> None:
    a = _object_type("Customer", parent="Account")
    b = _object_type("Account", parent="Customer")
    ontology = _ontology(object_types=[a, b])
    with pytest.raises(OntologyValidationError, match="parent cycle"):
        ontology.validate()


def test_reference_integrity_self_parent_cycle() -> None:
    ontology = _ontology(object_types=[_object_type(parent="Customer"), _object_type("Account")])
    with pytest.raises(OntologyValidationError, match="parent cycle"):
        ontology.validate()


def test_reference_integrity_unknown_parent() -> None:
    ontology = _ontology(object_types=[_object_type(parent="Ghost"), _object_type("Account")])
    with pytest.raises(OntologyValidationError, match="parent 'Ghost'"):
        ontology.validate()


def test_reference_integrity_valid_ontology(sample_ontology: Ontology) -> None:
    assert sample_ontology.validate() is None


def test_reference_integrity_problems_are_aggregated() -> None:
    # Two independent problems must surface in a single OntologyValidationError.
    ontology = _ontology(
        link_types=[
            LinkType(
                api_name="hitsSanction",
                display_name="命中制裁",
                source_type="Customer",
                target_type="SanctionHit2",
            )
        ]
    )
    ontology.object_types[0].parent = "Ghost"
    with pytest.raises(OntologyValidationError) as excinfo:
        ontology.validate()
    message = str(excinfo.value)
    assert "SanctionHit2" in message
    assert "Ghost" in message
    assert "2 problem(s)" in message


# ---------------------------------------------------- FR-4 type constraints


def test_type_constraints_enum_requires_string() -> None:
    prop = _prop("score", data_type=DataType.DOUBLE, enum_values=["1", "2"])
    ontology = _ontology(
        object_types=[_object_type(properties=[prop], primary_key=[]), _object_type("Account")]
    )
    with pytest.raises(OntologyValidationError, match="enum_values"):
        ontology.validate()


def test_type_constraints_timestamp_primary_key() -> None:
    prop = _prop("createdAt", data_type=DataType.TIMESTAMP, required=True)
    ontology = _ontology(
        object_types=[_object_type(properties=[prop], primary_key=["createdAt"]), _object_type("Account")]
    )
    with pytest.raises(OntologyValidationError, match="TIMESTAMP"):
        ontology.validate()


def test_type_constraints_json_primary_key() -> None:
    prop = _prop("extra", data_type=DataType.JSON, required=True)
    ontology = _ontology(
        object_types=[_object_type(properties=[prop], primary_key=["extra"]), _object_type("Account")]
    )
    with pytest.raises(OntologyValidationError, match="JSON"):
        ontology.validate()


def test_type_constraints_string_enum_is_valid() -> None:
    ontology = _ontology(
        object_types=[_object_type(), _object_type("Account")],
    )
    ontology.object_types[0].properties.append(_prop("riskLevel"))
    assert ontology.validate() is None


# ---------------------------------------------------- ActionType references


def test_action_type_references() -> None:
    bad_target = ActionType(api_name="freezeAccount", display_name="冻结", target_types=["Ghost"])
    with pytest.raises(OntologyValidationError, match="Ghost"):
        _ontology(action_types=[bad_target]).validate()

    bad_precondition = ActionType(
        api_name="freezeAccount", display_name="冻结", preconditions=["Bad Rule!"]
    )
    with pytest.raises(OntologyValidationError, match="precondition"):
        _ontology(action_types=[bad_precondition]).validate()

    # Forward references to P08 rule ids are allowed if well-formed.
    ok = ActionType(
        api_name="freezeAccount",
        display_name="冻结",
        target_types=["Account"],
        preconditions=["aml.rule-01", "kyc.check:strict"],
    )
    assert _ontology(action_types=[ok]).validate() is None


# ---------------------------------------------------- NFR-2: no rdflib needed


def test_core_import_does_not_require_rdflib() -> None:
    """Importing the core package must work with rdflib/pyshacl unavailable."""
    code = "\n".join(
        [
            "import sys",
            "sys.modules['rdflib'] = None",
            "sys.modules['pyshacl'] = None",
            "import agenticx_oag.ontology as o",
            "assert o.Ontology is not None",
            "try:",
            "    o.to_turtle",
            "    raise SystemExit('to_turtle should not resolve')",
            "except ImportError:",
            "    pass",
            "print('ok')",
        ]
    )
    env = {k: v for k, v in __import__('os').environ.items() if k not in ('PYTHONHOME', 'PYTHONPATH')}
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
