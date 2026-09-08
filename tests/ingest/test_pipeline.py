"""FR-5/FR-6 AC: full mocked pipeline -> IngestReport + link redirection."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest
from fixtures.mock_llm import MockEmbedder, MockLLM

from agenticx_oag.contracts import stores
from agenticx_oag.ingest.pipeline import IngestPipeline
from agenticx_oag.ontology.io import load_ontology

REPO_ROOT = Path(__file__).resolve().parents[2]
AML_ONTOLOGY = REPO_ROOT / "templates" / "finance" / "aml" / "ontology.yaml"


class FakeGraphStore:
    """In-memory GraphStore recording upserts."""

    def __init__(self) -> None:
        self.objects: list[dict[str, Any]] = []
        self.links: list[dict[str, Any]] = []

    async def upsert_objects(self, objects: list[dict[str, Any]]) -> None:
        self.objects.extend(objects)

    async def upsert_links(self, links: list[dict[str, Any]]) -> None:
        self.links.extend(links)

    async def get_objects(
        self, object_type: str, ids: list[str] | None = None
    ) -> list[dict[str, Any]]:
        found = [o for o in self.objects if o["object_type"] == object_type]
        if ids is not None:
            found = [o for o in found if o["id"] in ids]
        return found

    async def neighbors(
        self, object_id: str, link_type: str | None = None, max_hops: int = 2
    ) -> list[dict[str, Any]]:
        return []

    async def query(
        self, cypher: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        return []


def _write_doc(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_plan_fixture_full_run(tmp_path: Path) -> None:
    docs = [
        _write_doc(tmp_path, "a.md", "客户张三……命中OFAC名单……"),
        _write_doc(tmp_path, "b.md", "客户张三再次出现……"),
    ]
    store = FakeGraphStore()
    pipeline = IngestPipeline()

    report = await pipeline.run(docs, AML_ONTOLOGY, store, MockLLM())

    assert isinstance(store, stores.GraphStore)
    assert report.docs == 2
    assert report.chunks == 2
    assert report.extracted_objects == 4  # 2 objects x 2 docs
    assert report.extracted_links == 2
    assert report.merged == 2  # C-001 x2 -> 1, S-001 x2 -> 1
    assert report.dropped == 0

    assert sorted(o["id"] for o in store.objects) == ["C-001", "S-001"]
    customer = next(o for o in store.objects if o["id"] == "C-001")
    assert customer["object_type"] == "Customer"
    assert customer["properties"] == {"name": "张三", "riskLevel": "high"}
    assert customer["prov"]["source_doc"] == "a.md"
    # prov of the level-1 merge is chained
    assert len(customer["prov"]["merged_provs"]) == 1
    assert customer["prov"]["merged_provs"][0]["source_doc"] == "b.md"

    assert len(store.links) == 2
    link = store.links[0]
    assert link["link_type"] == "hitsSanction"
    assert (link["source_id"], link["target_id"]) == ("C-001", "S-001")


@pytest.mark.asyncio
async def test_link_redirect_after_embedding_merge(tmp_path: Path) -> None:
    doc1 = _write_doc(tmp_path, "1.md", "客户张三开户……")
    doc2 = _write_doc(tmp_path, "2.md", "客户张三（另一系统登记）有风险关联……")
    response1 = json.dumps(
        {
            "objects": [
                {"type": "Customer", "id": "C-001",
                 "properties": {"name": "张三", "riskLevel": "high"},
                 "source_span": "客户张三开户", "confidence": 0.95},
            ],
            "links": [],
        },
        ensure_ascii=False,
    )
    response2 = json.dumps(
        {
            "objects": [
                {"type": "Customer", "id": "C-002",
                 "properties": {"name": "张三", "riskLevel": "high", "region": "SH"},
                 "source_span": "客户张三（另一系统登记）", "confidence": 0.9},
            ],
            "links": [
                {"type": "risk", "source_id": "C-002", "target_id": "C-001",
                 "source_span": "风险关联", "confidence": 0.8},
            ],
        },
        ensure_ascii=False,
    )
    # vectors make C-001/C-002 cosine == 0.95 >= 0.92
    v1 = [1.0, 0.0]
    v2 = [0.95, math.sqrt(1.0 - 0.95**2)]
    store = FakeGraphStore()
    pipeline = IngestPipeline()

    report = await pipeline.run(
        [doc1, doc2], AML_ONTOLOGY, store, MockLLM([response1, response2]),
        embedder=MockEmbedder([v1, v2]),
    )

    assert report.extracted_objects == 2
    assert report.merged == 1
    assert report.dropped == 0

    # FR-5: link source redirected C-002 -> C-001, no dangling reference
    assert len(store.objects) == 1
    assert store.objects[0]["id"] == "C-001"
    assert len(store.links) == 1
    assert store.links[0]["source_id"] == "C-001"
    assert store.links[0]["target_id"] == "C-001"
    known_ids = {o["id"] for o in store.objects}
    assert all(
        link["source_id"] in known_ids and link["target_id"] in known_ids
        for link in store.links
    )


@pytest.mark.asyncio
async def test_dangling_links_dropped(tmp_path: Path) -> None:
    doc = _write_doc(tmp_path, "dangling.md", "孤儿链接文档……")
    response = json.dumps(
        {
            "objects": [
                {"type": "Customer", "id": "C-001",
                 "properties": {"name": "张三"}, "source_span": "客户张三",
                 "confidence": 0.9},
            ],
            "links": [
                {"type": "owns", "source_id": "C-001", "target_id": "A-404",
                 "source_span": "持有账户", "confidence": 0.7},
            ],
        },
        ensure_ascii=False,
    )
    store = FakeGraphStore()
    pipeline = IngestPipeline()

    report = await pipeline.run([doc], AML_ONTOLOGY, store, MockLLM([response]))

    assert report.extracted_links == 1
    assert report.dropped == 1  # the dangling link
    assert store.links == []
    assert len(store.objects) == 1


@pytest.mark.asyncio
async def test_sliding_window_chunks(tmp_path: Path) -> None:
    # 2500 chars -> chunk_size 1000, overlap 100, step 900 -> 3 chunks
    content = "风险客户交易记录。" * 250  # 9 chars * 250 = 2250
    doc = _write_doc(tmp_path, "big.md", content)
    store = FakeGraphStore()
    llm = MockLLM()
    pipeline = IngestPipeline()

    report = await pipeline.run([doc], AML_ONTOLOGY, store, llm, chunk_size=1000)

    assert report.docs == 1
    assert report.chunks == 3
    assert report.extracted_objects == 6  # 2 objects per chunk
    prompts = [c["prompt"] for c in llm.calls]
    assert all(len(p) <= 1000 for p in prompts)
    # 10% overlap between consecutive chunks
    assert prompts[1][:100] == prompts[0][-100:]


@pytest.mark.asyncio
async def test_unsupported_doc_skipped(tmp_path: Path) -> None:
    doc = _write_doc(tmp_path, "img.png", "binary-ish")
    store = FakeGraphStore()
    pipeline = IngestPipeline()

    report = await pipeline.run([doc], AML_ONTOLOGY, store, MockLLM())

    assert report.docs == 0
    assert report.chunks == 0
    assert store.objects == []


def test_ontology_loadable() -> None:
    ontology = load_ontology(AML_ONTOLOGY)
    assert ontology.namespace == "finance.aml"
    assert len(ontology.object_types) == 8
    assert len(ontology.link_types) == 8
