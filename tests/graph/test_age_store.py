"""FR-2 AC: AGEGraphStore against a real PG+AGE (docker compose dev).

Integration-marked; skipped unless TEST_PG_DSN is set, e.g.:
TEST_PG_DSN=postgresql://agenticx:agenticx@localhost:5433/agenticx
Each test gets a fresh namespace (fresh AGE graph) dropped on teardown.
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Any

import asyncpg
import pytest
import pytest_asyncio

from agenticx_oag.contracts import stores
from agenticx_oag.graph.age_store import AGEGraphStore
from agenticx_oag.ontology.io import load_ontology

DSN = os.environ.get("TEST_PG_DSN")
requires_dsn = pytest.mark.skipif(not DSN, reason="TEST_PG_DSN not set")
pytestmark = [pytest.mark.integration, requires_dsn]

REPO_ROOT = Path(__file__).resolve().parents[2]
AML_ONTOLOGY = REPO_ROOT / "templates" / "finance" / "aml" / "ontology.yaml"


def _object(object_type: str, object_id: str, **props: Any) -> dict[str, Any]:
    return {
        "object_type": object_type,
        "id": object_id,
        "properties": props,
        "prov": {
            "source_doc": "aml.md",
            "span": f"{object_id}……",
            "extracted_at": "2026-09-08T00:00:00+00:00",
            "confidence": 0.9,
        },
    }


def _link(link_type: str, source_id: str, target_id: str) -> dict[str, Any]:
    return {
        "link_type": link_type,
        "source_id": source_id,
        "target_id": target_id,
        "properties": {},
        "prov": {"source_doc": "aml.md", "confidence": 0.8},
    }


@pytest_asyncio.fixture
async def store() -> Any:
    namespace = f"test.p04.{uuid.uuid4().hex[:8]}"
    st = AGEGraphStore(DSN, namespace, ontology=load_ontology(AML_ONTOLOGY))
    yield st
    await st.close()
    conn = await asyncpg.connect(DSN)
    try:
        # graph_name is ^[A-Za-z0-9_]+$-validated at construction; the graph
        # is created lazily on first use, so guard-only tests never create it.
        row = await conn.fetchrow(
            "SELECT count(*) FROM ag_catalog.ag_graph WHERE name = $1", st.graph_name
        )
        if row is not None and row[0]:
            await conn.execute(f"SELECT ag_catalog.drop_graph('{st.graph_name}', true)")
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_satisfies_graphstore_protocol(store: AGEGraphStore) -> None:
    assert isinstance(store, stores.GraphStore)


@pytest.mark.asyncio
async def test_upsert_merge_semantics(store: AGEGraphStore) -> None:
    await store.upsert_objects([_object("Customer", "C-001", name="张三", riskLevel="high")])
    await store.upsert_objects(
        [_object("Customer", "C-001", name="张三", riskLevel="low", region="SH")]
    )

    objects = await store.get_objects("Customer", ["C-001"])
    assert len(objects) == 1
    customer = objects[0]
    # second upsert updates MERGE-matched node: new value + added key, old key kept
    assert customer["properties"]["riskLevel"] == "low"
    assert customer["properties"]["region"] == "SH"
    assert customer["properties"]["name"] == "张三"
    # __prov/__ns stripped and prov parsed back to a dict
    assert not any(k.startswith("__") for k in customer["properties"])
    assert customer["prov"]["source_doc"] == "aml.md"
    assert customer["prov"]["confidence"] == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_get_objects_label_filter_and_shape(store: AGEGraphStore) -> None:
    await store.upsert_objects(
        [
            _object("Customer", "C-001", name="张三"),
            _object("Customer", "C-002", name="李四"),
            _object("Account", "A-101", name="对公账户"),
        ]
    )

    all_customers = await store.get_objects("Customer")
    assert sorted(c["id"] for c in all_customers) == ["C-001", "C-002"]
    assert all(c["object_type"] == "Customer" for c in all_customers)

    selected = await store.get_objects("Customer", ["C-002"])
    assert [c["id"] for c in selected] == ["C-002"]


@pytest.mark.asyncio
async def test_neighbors_two_hops_cross_type(store: AGEGraphStore) -> None:
    await store.upsert_objects(
        [
            _object("Customer", "C-001", name="张三"),
            _object("Account", "A-101", name="基本户"),
            _object("Transaction", "T-201", name="转账"),
        ]
    )
    await store.upsert_links(
        [
            _link("owns", "C-001", "A-101"),
            _link("initiates", "A-101", "T-201"),
        ]
    )

    hops = await store.neighbors("C-001", max_hops=2)
    assert {(h["node"]["object_type"], h["node"]["id"], h["depth"]) for h in hops} == {
        ("Account", "A-101", 1),
        ("Transaction", "T-201", 2),
    }
    hop1 = next(h for h in hops if h["depth"] == 1)
    assert hop1["rel"]["link_type"] == "owns"
    assert hop1["rel"]["source_id"] == "C-001"
    assert hop1["rel"]["target_id"] == "A-101"
    assert hop1["rel"]["prov"]["confidence"] == pytest.approx(0.8)
    hop2 = next(h for h in hops if h["depth"] == 2)
    assert hop2["rel"]["link_type"] == "initiates"

    # link_type filter restricts traversal
    filtered = await store.neighbors("C-001", link_type="owns", max_hops=2)
    assert {h["node"]["id"] for h in filtered} == {"A-101"}
    assert all(h["depth"] == 1 for h in filtered)

    assert await store.neighbors("C-404") == []


@pytest.mark.asyncio
async def test_upsert_links_merge_idempotent(store: AGEGraphStore) -> None:
    await store.upsert_objects(
        [_object("Customer", "C-001", name="张三"), _object("Account", "A-101", name="户")]
    )
    await store.upsert_links([_link("owns", "C-001", "A-101")])
    await store.upsert_links([_link("owns", "C-001", "A-101")])

    counts = await store.query("MATCH ()-[r:owns]->() RETURN count(r)")
    assert counts == [1]


@pytest.mark.asyncio
async def test_query_passthrough(store: AGEGraphStore) -> None:
    await store.upsert_objects([_object("Customer", "C-001", name="张三")])

    counts = await store.query("MATCH (n:Customer) RETURN count(n)")
    assert counts == [1]
    names = await store.query(
        "MATCH (n:Customer) RETURN n.name", params=None
    )
    assert names == ["张三"]


@pytest.mark.asyncio
async def test_label_whitelist_rejects_unknown_and_unsafe(store: AGEGraphStore) -> None:
    with pytest.raises(ValueError, match="not defined in the ontology"):
        await store.upsert_objects([_object("NotInOntology", "X-1", name="x")])
    with pytest.raises(ValueError, match="must match"):
        await store.upsert_objects([_object("Bad; DROP TABLE x", "X-1", name="x")])
    with pytest.raises(ValueError, match="not defined in the ontology"):
        await store.upsert_links([_link("nope", "C-001", "C-002")])
    with pytest.raises(ValueError, match="must match"):
        await store.upsert_links([_link("owns} RETURN 1", "C-001", "C-002")])
    with pytest.raises(ValueError):
        await store.get_objects("Evil Type")
    with pytest.raises(ValueError):
        await store.neighbors("C-001", link_type="x y")
    with pytest.raises(ValueError):
        await store.neighbors("C-001", max_hops=0)


@pytest.mark.asyncio
async def test_regex_guard_without_ontology() -> None:
    bare = AGEGraphStore(DSN, "test.p04.bare")
    try:
        with pytest.raises(ValueError, match="must match"):
            await bare.upsert_objects([_object("Bad-Type", "X-1", name="x")])
        # without an ontology, any ^[A-Za-z0-9_]+$ label is allowed
        await bare.upsert_objects([_object("Anything", "X-1", name="x")])
        assert [o["id"] for o in await bare.get_objects("Anything")] == ["X-1"]
    finally:
        await bare.close()
        conn = await asyncpg.connect(DSN)
        try:
            await conn.execute(f"SELECT ag_catalog.drop_graph('{bare.graph_name}', true)")
        finally:
            await conn.close()


@pytest.mark.asyncio
async def test_nfr1_500_node_batch_under_5s(store: AGEGraphStore) -> None:
    objects = [
        _object("Account", f"A-{i:04d}", name=f"acct-{i}", balance=float(i))
        for i in range(500)
    ]
    started = time.perf_counter()
    await store.upsert_objects(objects)
    elapsed = time.perf_counter() - started
    assert elapsed < 5.0, f"500-node upsert took {elapsed:.2f}s (NFR-1: < 5s)"
    assert len(await store.get_objects("Account")) == 500
