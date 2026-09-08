"""FR-4: ContextPackPipeline with a scripted mock LLM and mock retriever."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from agenticx_oag.context.pack import ClaimStatus, Evidence, ObjectRef
from agenticx_oag.context.pipeline import ContextPackPipeline
from agenticx_oag.ontology.model import ObjectType, Ontology, PropertyType
from agenticx_oag.retrieval import RetrievalResult
from agenticx_oag.retrieval.entity_link import LinkedEntity

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "schemas" / "claim-ledger.schema.json"

REWRITES = '["客户张三名下账户有哪些异常交易？", "列出客户张三的所有账户"]'
LINKED = '[{"name": "张三", "object_type": "Customer"}]'
CLAIMS = """[
  {"text": "客户张三持有账户 A 和账户 B", "evidence_ids": ["E1"], "confidence": 0.9},
  {"text": "账户 A 余额为 5000", "evidence_ids": ["E2"], "confidence": 0.4},
  {"text": "张三是高净值客户", "evidence_ids": ["E404"], "confidence": 0.8}
]"""
UNCERTAINTY = "账户历史交易数据缺失，余额信息可能滞后。"


class ScriptedLLM:
    def __init__(self, replies: list[Any]) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self, prompt: str, *, system: str | None = None, json_mode: bool = False
    ) -> str:
        self.calls.append(
            {"prompt": prompt, "system": system, "json_mode": json_mode}
        )
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return str(reply)


class FakeRetriever:
    def __init__(self, result: RetrievalResult) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    async def retrieve(
        self, question: str, linked: list[LinkedEntity], top_k: int = 8
    ) -> RetrievalResult:
        self.calls.append({"question": question, "linked": linked})
        return self.result


@pytest.fixture()
def ontology() -> Ontology:
    return Ontology(
        namespace="test.aml",
        version="0.1.0",
        object_types=[
            ObjectType(
                api_name="Customer",
                display_name="客户",
                properties=[PropertyType(api_name="name", display_name="名称", required=True)],
            ),
            ObjectType(
                api_name="Account",
                display_name="账户",
                properties=[PropertyType(api_name="balance", display_name="余额")],
            ),
        ],
    )


def _retrieval_result() -> RetrievalResult:
    return RetrievalResult(
        evidence=[
            Evidence(
                id="E1",
                object_id="cust-1",
                text="客户张三持有账户 A 和账户 B",
                score=0.8,
                provenance="https://db.example/cust-1",
            ),
            Evidence(
                id="E2",
                object_id="acct-1",
                text="账户 A 余额 5000",
                score=0.5,
                provenance="graph:cust-1",
            ),
        ],
        objects=[
            ObjectRef(id="cust-1", object_type="Customer"),
            ObjectRef(id="acct-1", object_type="Account"),
        ],
    )


def _pipeline(
    ontology: Ontology, replies: list[Any]
) -> tuple[ContextPackPipeline, FakeRetriever]:
    retriever = FakeRetriever(_retrieval_result())
    return ContextPackPipeline(ScriptedLLM(replies), ontology, retriever), retriever


@pytest.mark.asyncio
async def test_build_pack_full_flow(ontology: Ontology) -> None:
    pipeline, retriever = _pipeline(
        ontology, [REWRITES, LINKED, CLAIMS, UNCERTAINTY]
    )
    question = "张三的账户情况如何？"
    pack = await pipeline.build_pack(question)

    # 改写链：原问题为第 0 条，随后 1~2 个 LLM 改写
    assert pack.rewrites[0] == question
    assert pack.rewrites[1:] == [
        "客户张三名下账户有哪些异常交易？",
        "列出客户张三的所有账户",
    ]
    # 检索用改写后的主问题 + 实体链接结果
    assert retriever.calls[0]["question"] == pack.rewrites[1]
    assert retriever.calls[0]["linked"] == [
        LinkedEntity(name="张三", object_type="Customer")
    ]
    # 证据与对象引用透传
    assert [ev.id for ev in pack.evidence] == ["E1", "E2"]
    assert [ref.id for ref in pack.object_refs] == ["cust-1", "acct-1"]
    # 主张：引用不存在证据的第三条被丢弃；status/confidence 映射
    assert [claim.claim_id for claim in pack.claims] == ["claim:1", "claim:2"]
    assert [claim.status for claim in pack.claims] == [
        ClaimStatus.SUPPORTED,
        ClaimStatus.UNVERIFIED,
    ]
    assert [claim.confidence for claim in pack.claims] == [0.9, 0.4]
    evidence_ids = {ev.id for ev in pack.evidence}
    assert all(set(claim.evidence_ids) <= evidence_ids for claim in pack.claims)
    # claim 的 ledger 字段（schema 对齐）已填充
    assert pack.claims[0].entities == ["entity:cust-1"]
    assert pack.claims[0].evidence[0].source_id == "src:E1"
    assert pack.claims[1].entities == ["entity:acct-1"]
    # 不确定性汇总来自 LLM
    assert pack.uncertainty == UNCERTAINTY


@pytest.mark.asyncio
async def test_build_pack_output_conforms_to_ledger_schema(
    ontology: Ontology,
) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    pipeline, _ = _pipeline(ontology, [REWRITES, LINKED, CLAIMS, UNCERTAINTY])
    pack = await pipeline.build_pack("张三的账户情况如何？")
    jsonschema.validate(pack.to_ledger(), schema)


@pytest.mark.asyncio
async def test_build_pack_garbage_rewrite_falls_back_to_original(
    ontology: Ontology,
) -> None:
    pipeline, retriever = _pipeline(
        ontology, ["这不是 JSON", LINKED, CLAIMS, UNCERTAINTY]
    )
    pack = await pipeline.build_pack("原问题")
    assert pack.rewrites == ["原问题"]
    # 无改写时检索用原问题
    assert retriever.calls[0]["question"] == "原问题"


@pytest.mark.asyncio
async def test_build_pack_uncertainty_rule_fallback(ontology: Ontology) -> None:
    pipeline, _ = _pipeline(
        ontology, [REWRITES, LINKED, CLAIMS, RuntimeError("llm down")]
    )
    pack = await pipeline.build_pack("张三的账户情况如何？")
    assert "共 2 条主张" in pack.uncertainty
    assert "1" in pack.uncertainty  # 其中 1 条低置信


@pytest.mark.asyncio
async def test_build_pack_claims_empty_when_llm_garbage(ontology: Ontology) -> None:
    pipeline, _ = _pipeline(
        ontology, [REWRITES, LINKED, "无法输出 JSON", UNCERTAINTY]
    )
    pack = await pipeline.build_pack("问题")
    assert pack.claims == []
    jsonschema.validate(pack.to_ledger(), json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
