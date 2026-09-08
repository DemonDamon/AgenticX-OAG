"""FR-6: CitationValidator (dangling refs + unsupported assertion sentences)."""

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
from agenticx_oag.generation import Citation, CitationValidator, OAGAnswer


@pytest.fixture()
def pack() -> ContextPack:
    return ContextPack(
        question="张三的账户情况如何？",
        evidence=[
            Evidence(id="E1", object_id="cust-1", text="客户张三持有两个账户", score=0.8),
            Evidence(id="E2", object_id="acct-1", text="账户 A 余额 5000", score=0.5),
        ],
        claims=[
            Claim(
                claim_id="claim:1",
                text="客户张三持有两个账户",
                status=ClaimStatus.SUPPORTED,
                entities=["entity:cust-1"],
                evidence=[LedgerEvidence(source_id="src:E1")],
                evidence_ids=["E1"],
            ),
            Claim(
                claim_id="claim:2",
                text="账户 A 余额为 5000",
                status=ClaimStatus.SUPPORTED,
                entities=["entity:acct-1"],
                evidence=[LedgerEvidence(source_id="src:E2")],
                evidence_ids=["E2"],
            ),
        ],
        created_at=datetime(2026, 9, 3, 12, 0, 0, tzinfo=UTC),
    )


def test_dangling_and_unsupported_violations(pack: ContextPack) -> None:
    answer = OAGAnswer(
        text=(
            "客户张三持有两个账户[E1]。"
            "该客户是高净值客户。"
            "根据现有证据无法判断其风险等级。"
            "他是否已婚？"
        ),
        citations=[
            Citation(marker="[E1]", evidence_id="E1"),
            Citation(marker="[E99]", evidence_id="E99"),
            Citation(marker="[C7]", claim_id="claim:7"),
        ],
    )
    violations = CitationValidator().validate(answer, pack)
    dangling = [v for v in violations if v.kind == "dangling"]
    unsupported = [v for v in violations if v.kind == "unsupported"]
    # 引用了不存在的 evidence / claim id
    assert {v.ref_id for v in dangling} == {"E99", "claim:7"}
    assert all(v.marker in {"[E99]", "[C7]"} for v in dangling)
    # 无引用标记的断言句（问句与白名单引导句豁免）
    assert [v.sentence for v in unsupported] == ["该客户是高净值客户"]


def test_clean_answer_is_valid(pack: ContextPack) -> None:
    answer = OAGAnswer(
        text=(
            "客户张三持有两个账户[E1]。"
            "其中账户 A 余额为 5000[C2]。"
            "综上，其账户结构已核对[C1]。"
        ),
        citations=[
            Citation(marker="[E1]", evidence_id="E1"),
            Citation(marker="[C2]", claim_id="claim:2"),
            Citation(marker="[C1]", claim_id="claim:1"),
        ],
    )
    validator = CitationValidator()
    assert validator.validate(answer, pack) == []
    assert validator.is_valid(answer, pack) is True


def test_lead_whitelist_and_questions_are_exempt(pack: ContextPack) -> None:
    answer = OAGAnswer(
        text=(
            "如下。"
            "综上，情况已说明。"
            "针对该问题暂无更多数据。"
            "根据现有证据无法判断婚姻状况。"
            "他名下还有哪些账户?"
        ),
        citations=[],
    )
    assert CitationValidator().is_valid(answer, pack) is True


def test_unsupported_without_final_punctuation(pack: ContextPack) -> None:
    answer = OAGAnswer(text="客户张三持有账户[E1]。末尾还有一个未引用断言", citations=[])
    violations = CitationValidator().validate(answer, pack)
    assert [v.sentence for v in violations] == ["末尾还有一个未引用断言"]


def test_newline_separated_sentences(pack: ContextPack) -> None:
    answer = OAGAnswer(
        text="客户张三持有两个账户[E1]。\n账户余额未知。\n综上，信息有限。",
        citations=[Citation(marker="[E1]", evidence_id="E1")],
    )
    violations = CitationValidator().validate(answer, pack)
    assert [v.sentence for v in violations if v.kind == "unsupported"] == ["账户余额未知"]
