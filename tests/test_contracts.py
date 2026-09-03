from typing import Any

from agenticx_oag.contracts import stores
from agenticx_oag.contracts.gen import ontology_v1_pb2

PROTOCOL_NAMES = (
    "GraphStore",
    "VectorStore",
    "EmbeddingProvider",
    "LLMProvider",
    "AuditSink",
    "EventBus",
    "IDPProvider",
    "ApprovalProvider",
    "Notifier",
)


def test_proto_roundtrip() -> None:
    ontology = ontology_v1_pb2.Ontology(
        namespace="finance.aml",
        version="1.2.0",
        metadata={"domain": "aml", "tier": "core"},
    )

    customer = ontology.object_types.add(
        api_name="Customer",
        display_name="Customer",
        description="KYC customer",
    )
    customer_id = customer.properties.add(
        api_name="customerId",
        display_name="Customer ID",
        data_type=ontology_v1_pb2.DATA_TYPE_STRING,
        required=True,
        description="Primary identifier",
    )
    customer_id.enum_values.append("C-0001")
    risk_level = customer.properties.add(
        api_name="riskLevel",
        display_name="Risk Level",
        data_type=ontology_v1_pb2.DATA_TYPE_STRING,
    )
    risk_level.enum_values.extend(["low", "high"])
    customer.primary_key.append("customerId")

    account = ontology.object_types.add(
        api_name="Account",
        display_name="Account",
        parent="BaseEntity",
    )
    account.properties.add(api_name="balance", display_name="Balance",
                           data_type=ontology_v1_pb2.DATA_TYPE_DOUBLE, required=True)
    account.properties.add(api_name="txnCount", display_name="Transaction Count",
                           data_type=ontology_v1_pb2.DATA_TYPE_INT64)
    account.properties.add(api_name="frozen", display_name="Frozen",
                           data_type=ontology_v1_pb2.DATA_TYPE_BOOL)
    account.properties.add(api_name="openedAt", display_name="Opened At",
                           data_type=ontology_v1_pb2.DATA_TYPE_TIMESTAMP)
    account.properties.add(api_name="raw", display_name="Raw",
                           data_type=ontology_v1_pb2.DATA_TYPE_JSON)

    owns = ontology.link_types.add(
        api_name="owns",
        display_name="Owns",
        source_type="Customer",
        target_type="Account",
        cardinality=ontology_v1_pb2.CARDINALITY_ONE_TO_MANY,
    )
    owns.properties.add(api_name="since", display_name="Since",
                        data_type=ontology_v1_pb2.DATA_TYPE_TIMESTAMP)

    freeze = ontology.action_types.add(
        api_name="freezeAccount",
        display_name="Freeze Account",
        target_types=["Account"],
        preconditions=["rule.balance_anomaly"],
        approval_policy="single",
        rollback_handler="rollback.freeze_account",
    )
    freeze.parameters.add(api_name="reason", display_name="Reason",
                          data_type=ontology_v1_pb2.DATA_TYPE_STRING, required=True)

    data = ontology.SerializeToString(deterministic=True)
    parsed = ontology_v1_pb2.Ontology()
    parsed.ParseFromString(data)

    assert parsed == ontology
    assert parsed.SerializeToString(deterministic=True) == data
    assert parsed.link_types[0].cardinality == ontology_v1_pb2.CARDINALITY_ONE_TO_MANY
    assert parsed.object_types[1].parent == "BaseEntity"


def test_protocols() -> None:
    for name in PROTOCOL_NAMES:
        protocol = getattr(stores, name)
        # isinstance on a non-runtime_checkable Protocol raises TypeError
        assert not isinstance(object(), protocol)

    class FakeGraphStore:
        async def upsert_objects(self, objects: list[dict[str, Any]]) -> None: ...
        async def upsert_links(self, links: list[dict[str, Any]]) -> None: ...
        async def get_objects(self, object_type: str, ids: list[str] | None = None) -> list[dict[str, Any]]: ...
        async def neighbors(self, object_id: str, link_type: str | None = None, max_hops: int = 2) -> list[dict[str, Any]]: ...
        async def query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...

    assert isinstance(FakeGraphStore(), stores.GraphStore)
