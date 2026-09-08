"""FR-5: OAGGenerator parses [E{n}]/[C{n}] citation markers from the answer."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agenticx_oag.context.pack import (
    Claim,
    ClaimStatus,
    ContextPack,
    Evidence,
    LedgerEvidence,
)
from agenticx_oag.generation import Citation, OAGAnswer, OAGGenerator, parse_citations


class FakeLLM:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[dict[str, object]] = []

    async def complete(
        self, prompt: str, *, system: str | None = None, json_mode: bool = False
    ) -> str:
        self.calls.append({"prompt": prompt, "system": system, "json_mode": json_mode})
        return self.reply


@pytest.fixture()
def pack() -> ContextPack:
    ev1 = Evidence(id="E1", object_id="cust-1", text="客户张三持有账户 A", score=0.8)
    ev2 = Evidence(id="E2", object_id="acct-1", text="账户 A 余额 5000", score=0.5)
    return ContextPack(
        question="张三的账户情况如何？",
        evidence=[ev1, ev2],
        claims=[
            Claim(
                claim_id="claim:1",
                text="客户张三持有两个账户",
                status=ClaimStatus.SUPPORTED,
                entities=["entity:cust-1"],
                evidence=[LedgerEvidence(source_id="src:E1")],
                evidence_ids=["E1"],
                confidence=0.9,
            ),
            Claim(
                claim_id="claim:2",
                text="账户 A 余额为 5000",
                status=ClaimStatus.SUPPORTED,
                entities=["entity:acct-1"],
                evidence=[LedgerEvidence(source_id="src:E2")],
                evidence_ids=["E2"],
                confidence=0.9,
            ),
        ],
        created_at=datetime(2026, 9, 3, 12, 0, 0, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_generate_parses_citations(pack: ContextPack) -> None:
    reply = "客户张三持有两个账户[E1]，其中账户 A 余额为 5000[C1]。根据现有证据无法判断其风险等级。"
    llm = FakeLLM(reply)
    answer = await OAGGenerator(llm).generate(pack)
    assert isinstance(answer, OAGAnswer)
    assert answer.text == reply
    assert answer.citations == [
        Citation(marker="[E1]", evidence_id="E1"),
        Citation(marker="[C1]", claim_id="claim:1"),
    ]


@pytest.mark.asyncio
async def test_generate_prompt_carries_pack_and_rules(pack: ContextPack) -> None:
    llm = FakeLLM("答案[E1]。")
    await OAGGenerator(llm).generate(pack)
    call = llm.calls[0]
    prompt = str(call["prompt"])
    assert pack.pack_id in prompt  # pack JSON 注入
    assert "E1" in prompt and "claim:1" in prompt
    assert "Context Pack" in prompt
    assert call["system"] is not None and "引用标记" in str(call["system"])


def test_parse_citations_dedup_in_order() -> None:
    text = "第一句[E1]。第二句[E1][E2]。第三句[C2]。"
    citations = parse_citations(text)
    assert [(c.marker, c.evidence_id, c.claim_id) for c in citations] == [
        ("[E1]", "E1", None),
        ("[E2]", "E2", None),
        ("[C2]", None, "claim:2"),
    ]


def test_parse_citations_ignores_other_markers() -> None:
    assert parse_citations("普通句子，没有标记。") == []
    assert parse_citations("无效标记 [X1] 与 [Eabc]。") == []
    assert parse_citations("多位编号 [E12] 有效。") == [
        Citation(marker="[E12]", evidence_id="E12")
    ]
