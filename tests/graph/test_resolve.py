"""FR-4 AC: two-level entity disambiguation with alias_map."""

from __future__ import annotations

import math

import pytest
from fixtures.mock_llm import MockEmbedder

from agenticx_oag.graph.records import ObjectRecord, ProvInfo
from agenticx_oag.graph.resolve import EntityResolver


def _customer(object_id: str, name: str, **props: object) -> ObjectRecord:
    return ObjectRecord(
        object_type="Customer",
        id=object_id,
        properties={"name": name, **props},
        prov=ProvInfo(source_doc="doc.md", span=f"{name}……", confidence=0.9),
    )


@pytest.mark.asyncio
async def test_level1_same_primary_key_merges() -> None:
    first = _customer("C-001", "张三", riskLevel="high")
    second = _customer("C-001", "张三", riskLevel="high", region="SH")
    resolver = EntityResolver(embedder=None)

    resolved, alias_map = await resolver.resolve([first, second])

    assert len(resolved) == 1
    survivor = resolved[0]
    # property union, later record wins on conflicts
    assert survivor.properties == {"name": "张三", "riskLevel": "high", "region": "SH"}
    # prov 链接追加
    assert len(survivor.prov.merged_provs) == 1
    assert survivor.prov.merged_provs[0]["source_doc"] == "doc.md"
    assert alias_map == {}


@pytest.mark.asyncio
async def test_level1_keeps_different_types_and_ids() -> None:
    records = [
        _customer("C-001", "张三"),
        _customer("C-002", "李四"),
        ObjectRecord(object_type="Account", id="C-001", properties={"name": "张三"}),
    ]
    resolver = EntityResolver(embedder=None)

    resolved, alias_map = await resolver.resolve(records)

    assert [r.id for r in resolved] == ["C-001", "C-002", "C-001"]
    assert [r.object_type for r in resolved] == ["Customer", "Customer", "Account"]
    assert alias_map == {}


@pytest.mark.asyncio
async def test_level2_embedding_merge() -> None:
    # cosine(v1, v2) == 0.95 >= 0.92; v3 is orthogonal to both
    v1 = [1.0, 0.0]
    v2 = [0.95, math.sqrt(1.0 - 0.95**2)]
    v3 = [0.0, 1.0]
    records = [
        _customer("C-001", "张三", riskLevel="high"),
        _customer("C-002", "张三", riskLevel="high"),
        _customer("C-003", "王五", riskLevel="low"),
    ]
    resolver = EntityResolver(embedder=MockEmbedder([v1, v2, v3]))

    resolved, alias_map = await resolver.resolve(records)

    assert [r.id for r in resolved] == ["C-001", "C-003"]
    assert alias_map == {"C-002": "C-001"}
    survivor = resolved[0]
    assert survivor.prov.merged_via == "embedding"
    assert len(survivor.prov.merged_provs) == 1


@pytest.mark.asyncio
async def test_level2_respects_threshold() -> None:
    # cosine(v1, v2) == 0.8 < 0.92
    v1 = [1.0, 0.0]
    v2 = [0.8, math.sqrt(1.0 - 0.8**2)]
    resolver = EntityResolver(embedder=MockEmbedder([v1, v2]))

    resolved, alias_map = await resolver.resolve(
        [_customer("C-001", "张三"), _customer("C-002", "张三")]
    )

    assert len(resolved) == 2
    assert alias_map == {}
    assert all(r.prov.merged_via == "" for r in resolved)


@pytest.mark.asyncio
async def test_level2_no_cross_type_merge() -> None:
    same_vector = [1.0, 0.0]
    records = [
        _customer("C-001", "张三"),
        ObjectRecord(object_type="Account", id="A-001", properties={"name": "张三"}),
    ]
    resolver = EntityResolver(embedder=MockEmbedder([same_vector, same_vector]))

    resolved, alias_map = await resolver.resolve(records)

    assert len(resolved) == 2
    assert alias_map == {}


@pytest.mark.asyncio
async def test_level2_custom_threshold() -> None:
    v1 = [1.0, 0.0]
    v2 = [0.8, math.sqrt(1.0 - 0.8**2)]  # cosine 0.8
    resolver = EntityResolver(embedder=MockEmbedder([v1, v2]), threshold=0.75)

    resolved, alias_map = await resolver.resolve(
        [_customer("C-001", "张三"), _customer("C-002", "张三")]
    )

    assert len(resolved) == 1
    assert alias_map == {"C-002": "C-001"}
