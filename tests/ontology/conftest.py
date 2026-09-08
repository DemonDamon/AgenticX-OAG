"""Shared fixtures for the ontology test suite (P03)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from agenticx_oag.ontology import (
    ActionType,
    Cardinality,
    DataType,
    LinkType,
    ObjectType,
    Ontology,
    PropertyType,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENE_PATH = REPO_ROOT / "prototype" / "scenes" / "bank-aml.json"
CONVERTER_PATH = REPO_ROOT / "scripts" / "scene_to_ontology.py"


def _load_converter_module() -> Any:
    spec = importlib.util.spec_from_file_location("scene_to_ontology", CONVERTER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("scene_to_ontology", module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def converter() -> Any:
    """The scripts/scene_to_ontology.py module, loaded by path."""
    return _load_converter_module()


@pytest.fixture(scope="session")
def bank_aml_ontology() -> Ontology:
    """The ontology converted from the bank-aml prototype scene."""
    module = _load_converter_module()
    return module.convert_scene(SCENE_PATH, namespace="finance.aml", version="0.1.0")


@pytest.fixture()
def sample_ontology() -> Ontology:
    """A small synthetic ontology exercising parents, enums, types and actions."""
    return Ontology(
        namespace="test.core",
        version="1.2.3",
        metadata={"source": "unit-test"},
        object_types=[
            ObjectType(
                api_name="Party",
                display_name="参与方",
                description="abstract party",
                properties=[
                    PropertyType(api_name="partyId", display_name="ID", required=True),
                    PropertyType(api_name="displayName", display_name="名称", required=True),
                ],
                primary_key=["partyId"],
            ),
            ObjectType(
                api_name="Customer",
                display_name="客户",
                parent="Party",
                properties=[
                    PropertyType(api_name="id", display_name="ID", required=True),
                    PropertyType(api_name="name", display_name="名称", required=True),
                    PropertyType(
                        api_name="riskLevel",
                        display_name="风险等级",
                        enum_values=["low", "medium", "high"],
                    ),
                    PropertyType(api_name="score", display_name="评分", data_type=DataType.DOUBLE),
                    PropertyType(
                        api_name="createdAt",
                        display_name="创建时间",
                        data_type=DataType.TIMESTAMP,
                        required=True,
                    ),
                    PropertyType(api_name="extra", display_name="扩展", data_type=DataType.JSON),
                ],
                primary_key=["id"],
            ),
            ObjectType(
                api_name="Account",
                display_name="账户",
                parent="Party",
                properties=[
                    PropertyType(api_name="id", display_name="ID", required=True),
                    PropertyType(api_name="balance", display_name="余额", data_type=DataType.DOUBLE),
                ],
                primary_key=["id"],
            ),
        ],
        link_types=[
            LinkType(
                api_name="owns",
                display_name="持有",
                source_type="Customer",
                target_type="Account",
                cardinality=Cardinality.ONE_TO_MANY,
                properties=[
                    PropertyType(api_name="since", display_name="持有起始日", required=False)
                ],
            )
        ],
        action_types=[
            ActionType(
                api_name="freezeAccount",
                display_name="冻结账户",
                target_types=["Account"],
                parameters=[
                    PropertyType(api_name="reason", display_name="原因", required=True),
                    PropertyType(api_name="days", display_name="天数", data_type=DataType.INT64),
                ],
                preconditions=["aml.rule-01", "kyc.check:strict"],
                approval_policy="two_level",
                rollback_handler="releaseFreeze",
            )
        ],
    )
