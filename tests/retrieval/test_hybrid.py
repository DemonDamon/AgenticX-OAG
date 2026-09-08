"""FR-2 / FR-7: OntologyHybridRetriever (vector + type filter + graph expansion).

Fixture scores are hand-computed against the FR-2 formula
``score = vector_score * 0.6 + graph_bonus * 0.4`` with
``graph_bonus = 0.25`` for objects on a graph expansion path.
"""

from __future__ import annotations

from typing import Any

import pytest

from agenticx_oag.retrieval import (
    GRAPH_ADJACENCY_BONUS,
    GRAPH_WEIGHT,
    VECTOR_WEIGHT,
    LinkedEntity,
    OntologyHybridRetriever,
)


class FakeEmbedder:
    def __init__(self) -> None:
        self.texts: list[list[str]] | None = None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.texts = texts
        return [[0.1, 0.2, 0.3] for _ in texts]


class FakeVectorStore:
    def __init__(
        self, hits: list[dict[str, Any]] | None = None, error: Exception | None = None
    ) -> None:
        self.hits = hits or []
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def search(
        self,
        collection: str,
        vector: list[float],
        top_k: int,
        filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append({"collection": collection, "vector": vector, "top_k": top_k})
        if self.error is not None:
            raise self.error
        return self.hits[:top_k]


class FakeGraphStore:
    def __init__(
        self,
        neighbors: dict[str, list[dict[str, Any]]] | None = None,
        objects_by_type: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self.neighbors_map = neighbors or {}
        self.objects_by_type = objects_by_type or {}
        self.neighbor_calls: list[tuple[str, int]] = []
        self.object_calls: list[str] = []

    async def neighbors(
        self,
        object_id: str,
        link_type: str | None = None,
        max_hops: int = 2,
    ) -> list[dict[str, Any]]:
        self.neighbor_calls.append((object_id, max_hops))
        return self.neighbors_map.get(object_id, [])

    async def get_objects(
        self, object_type: str, ids: list[str] | None = None
    ) -> list[dict[str, Any]]:
        self.object_calls.append(object_type)
        return self.objects_by_type.get(object_type, [])


def vec_hit(oid: str, score: float, object_type: str, text: str = "", prov: str = "") -> dict:
    return {
        "id": oid,
        "score": score,
        "meta": {"object_type": object_type, "text": text, "prov": prov},
    }


def graph_obj(oid: str, object_type: str, text: str = "") -> dict:
    return {"id": oid, "object_type": object_type, "text": text}


CUSTOMER_HITS: list[dict[str, Any]] = [
    vec_hit("cust-1", 0.90, "Customer", "客户张三", "prov:cust-1"),
    vec_hit("cust-2", 0.80, "Customer", "客户李四", "prov:cust-2"),
    vec_hit("cust-3", 0.70, "Customer", "客户王五", "prov:cust-3"),
    vec_hit("cust-4", 0.60, "Customer", "客户赵六", "prov:cust-4"),
    vec_hit("cust-5", 0.50, "Customer", "客户钱七", "prov:cust-5"),
    vec_hit("cust-6", 0.40, "Customer", "客户孙八", "prov:cust-6"),
    vec_hit("txn-1", 0.85, "Transaction", "转账交易1", "prov:txn-1"),
    vec_hit("txn-2", 0.75, "Transaction", "转账交易2", "prov:txn-2"),
]

LINKED_CUSTOMER = [LinkedEntity(name="张三", object_type="Customer")]


@pytest.mark.asyncio
async def test_type_constraint_and_graph_expansion() -> None:
    graph = FakeGraphStore(
        neighbors={
            "cust-1": [
                graph_obj("txn-1", "Transaction", "客户张三的转账交易1"),
                graph_obj("cust-2", "Customer", "客户李四"),
            ]
        }
    )
    vectors = FakeVectorStore(hits=CUSTOMER_HITS)
    retriever = OntologyHybridRetriever(graph, vectors, FakeEmbedder())

    result = await retriever.retrieve("张三的情况", LINKED_CUSTOMER, top_k=8)

    # 向量召回宽度为 top_k x 3
    assert vectors.calls[0]["top_k"] == 24
    # 类型约束：仅 Customer 命中 + 其图邻居（txn-2 被过滤且不在邻域）
    ids = {ev.object_id for ev in result.evidence}
    assert ids == {"cust-1", "cust-2", "cust-3", "cust-4", "cust-5", "cust-6", "txn-1"}
    assert "txn-2" not in ids
    # 手算核对 FR-2 分数合成：向量分 x 0.6 + 图邻接加成(0.25) x 0.4
    scores = {ev.object_id: ev.score for ev in result.evidence}
    assert scores["cust-1"] == pytest.approx(0.90 * VECTOR_WEIGHT)  # 0.54
    assert scores["cust-2"] == pytest.approx(  # 0.58（向量命中且在扩展路径）
        0.80 * VECTOR_WEIGHT + GRAPH_ADJACENCY_BONUS * GRAPH_WEIGHT
    )
    assert scores["cust-3"] == pytest.approx(0.70 * VECTOR_WEIGHT)  # 0.42
    assert scores["txn-1"] == pytest.approx(  # 0.10（仅图扩展补全）
        GRAPH_ADJACENCY_BONUS * GRAPH_WEIGHT
    )
    # 结果按分数降序，id 顺序编号
    ordered = [ev.score for ev in result.evidence]
    assert ordered == sorted(ordered, reverse=True)
    assert [ev.id for ev in result.evidence] == [f"E{i}" for i in range(1, 8)]
    # 文本与 provenance 透传；图邻居 provenance 记录来源对象
    by_id = {ev.object_id: ev for ev in result.evidence}
    assert by_id["cust-1"].text == "客户张三"
    assert by_id["cust-1"].provenance == "prov:cust-1"
    assert by_id["txn-1"].provenance == "graph:cust-1"
    # objects 覆盖全部证据对象
    assert {ref.id for ref in result.objects} == ids
    assert all(ref.object_type for ref in result.objects)
    assert result.degraded is False
    assert result.reranked is False


@pytest.mark.asyncio
async def test_no_type_filter_when_linked_empty() -> None:
    graph = FakeGraphStore()
    retriever = OntologyHybridRetriever(graph, FakeVectorStore(hits=CUSTOMER_HITS), FakeEmbedder())
    result = await retriever.retrieve("客户和交易", [], top_k=8)
    ids = {ev.object_id for ev in result.evidence}
    assert {"cust-1", "txn-1", "txn-2"} <= ids


@pytest.mark.asyncio
async def test_top_k_limits_seed_objects() -> None:
    graph = FakeGraphStore(neighbors={"cust-1": [graph_obj("acct-1", "Account", "账户")]})
    retriever = OntologyHybridRetriever(graph, FakeVectorStore(hits=CUSTOMER_HITS), FakeEmbedder())
    result = await retriever.retrieve("q", LINKED_CUSTOMER, top_k=2)
    # top-2 Customer 种子（cust-1/cust-2）+ cust-1 的邻居
    assert {ev.object_id for ev in result.evidence} == {"cust-1", "cust-2", "acct-1"}


@pytest.mark.asyncio
async def test_max_five_neighbors_per_object() -> None:
    graph = FakeGraphStore(
        neighbors={"cust-1": [graph_obj(f"nb-{i}", "Account") for i in range(1, 8)]}
    )
    retriever = OntologyHybridRetriever(
        graph, FakeVectorStore(hits=CUSTOMER_HITS[:1]), FakeEmbedder()
    )
    result = await retriever.retrieve("q", [], top_k=1)
    neighbor_ids = [ev.object_id for ev in result.evidence if ev.object_id.startswith("nb-")]
    assert len(neighbor_ids) == 5


@pytest.mark.asyncio
async def test_evidence_capped_at_24_by_score() -> None:
    hits = [vec_hit(f"seed-{i}", 0.90 - i * 0.01, "Customer", "种子") for i in range(8)]
    neighbors = {
        f"seed-{i}": [graph_obj(f"nb-{i}-{j}", "Account") for j in range(5)]
        for i in range(8)
    }
    retriever = OntologyHybridRetriever(
        FakeGraphStore(neighbors=neighbors), FakeVectorStore(hits=hits), FakeEmbedder()
    )
    result = await retriever.retrieve("q", [], top_k=8)
    # 8 个种子 + 40 个邻居 -> 按分数截断为 24 条
    assert len(result.evidence) == 24
    seed_ids = {ev.object_id for ev in result.evidence if ev.object_id.startswith("seed-")}
    assert seed_ids == {f"seed-{i}" for i in range(8)}
    scores = [ev.score for ev in result.evidence]
    assert scores == sorted(scores, reverse=True)
    assert len({ev.id for ev in result.evidence}) == 24


@pytest.mark.asyncio
async def test_degraded_on_vector_store_error() -> None:
    graph = FakeGraphStore(
        neighbors={"cust-1": [graph_obj("txn-1", "Transaction", "客户张三的转账")]},
        objects_by_type={
            "Customer": [
                graph_obj("cust-1", "Customer", "客户张三"),
                graph_obj("cust-2", "Customer", "客户李四"),
            ]
        },
    )
    retriever = OntologyHybridRetriever(
        graph, FakeVectorStore(error=RuntimeError("vector store down")), FakeEmbedder()
    )
    result = await retriever.retrieve("q", LINKED_CUSTOMER, top_k=8)
    assert result.degraded is True
    ids = {ev.object_id for ev in result.evidence}
    assert ids == {"cust-1", "cust-2", "txn-1"}
    assert all(ev.score == pytest.approx(GRAPH_ADJACENCY_BONUS * GRAPH_WEIGHT) for ev in result.evidence)
    assert graph.object_calls == ["Customer"]


@pytest.mark.asyncio
async def test_degraded_when_vectors_not_injected() -> None:
    graph = FakeGraphStore(
        objects_by_type={"Customer": [graph_obj("cust-1", "Customer", "客户张三")]}
    )
    retriever = OntologyHybridRetriever(graph)  # vectors/embedder 未注入
    result = await retriever.retrieve("q", LINKED_CUSTOMER, top_k=8)
    assert result.degraded is True
    assert {ev.object_id for ev in result.evidence} == {"cust-1"}
    assert result.evidence[0].text == "客户张三"
