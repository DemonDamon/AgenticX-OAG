"""P06 FR-1: metric hand-computed fixtures (plan-specified)."""

from __future__ import annotations

import json

import pytest

from agenticx_oag.context.pack import Claim, LedgerEvidence
from agenticx_oag.eval.metrics import (
    aggregate,
    citation_correctness,
    faithfulness,
    hallucination_rate,
    judge_claims,
    keyword_coverage,
    recall_at_k,
    split_assertions,
    summarize,
)


def _claim(claim_id: str, text: str) -> Claim:
    return Claim(
        claim_id=claim_id,
        text=text,
        entities=["entity:test"],
        evidence=[LedgerEvidence(source_id="src:test", excerpt=text)],
    )


class FixedJudge:
    """LLMProvider fake: entitles exactly the scripted claim texts."""

    def __init__(self, entailed_texts: set[str]) -> None:
        self._entailed = entailed_texts
        self.prompts: list[str] = []

    async def complete(
        self, prompt: str, *, system: str | None = None, json_mode: bool = False
    ) -> str:
        self.prompts.append(prompt)
        claim = ""
        for line in prompt.splitlines():
            if line.startswith("陈述："):
                claim = line[len("陈述：") :].strip()
        return json.dumps(
            {"entailed": claim in self._entailed, "reason": "fixed judge"},
            ensure_ascii=False,
        )


class BrokenJudge:
    async def complete(
        self, prompt: str, *, system: str | None = None, json_mode: bool = False
    ) -> str:
        raise RuntimeError("judge down")


class GarbageJudge:
    async def complete(
        self, prompt: str, *, system: str | None = None, json_mode: bool = False
    ) -> str:
        return "not json at all"


# --- recall_at_k ------------------------------------------------------------


def test_recall_at_k_plan_fixture() -> None:
    assert recall_at_k(["A", "B", "C"], ["B", "D"], 2) == 0.5


def test_recall_at_k_edges() -> None:
    assert recall_at_k([], ["B"], 5) == 0.0
    assert recall_at_k(["A", "B", "C"], [], 2) == 0.0
    assert recall_at_k(["A", "B", "C"], ["B", "D"], 0) == 0.0
    assert recall_at_k(["B", "A", "C"], ["B", "D"], 2) == 0.5
    assert recall_at_k(["B", "D"], ["B", "D"], 5) == 1.0


# --- citation_correctness ---------------------------------------------------


def test_citation_correctness_plan_fixture() -> None:
    assert citation_correctness(["E1", "E9"], ["E1", "E2"]) == 0.5


def test_citation_correctness_edges() -> None:
    assert citation_correctness([], ["E1"]) == 0.0
    assert citation_correctness(["E1", "E1"], ["E1"]) == 1.0
    assert citation_correctness(["E1", "claim:1"], ["E1", "claim:1"]) == 1.0


# --- hallucination_rate -----------------------------------------------------


def test_hallucination_rate_plan_fixture() -> None:
    assert hallucination_rate(
        ["a[E1]。", "b。", "c[E2]。"], ["a[E1]。", "c[E2]。"]
    ) == pytest.approx(1 / 3)


def test_hallucination_rate_edges() -> None:
    assert hallucination_rate([], []) == 0.0
    assert hallucination_rate(["b。"], []) == 1.0
    assert hallucination_rate(["a[E1]。"], ["a[E1]。"]) == 0.0


# --- split_assertions (P05 rule reuse) ---------------------------------------


def test_split_assertions_reuses_p05_rules() -> None:
    text = "句子一[E1]。这是问题？根据现有证据无法判断。句子二[E2]。"
    assertions, cited = split_assertions(text)
    # 问句与白名单开头的句子豁免，不计入断言句
    assert assertions == ["句子一[E1]", "句子二[E2]"]
    assert cited == ["句子一[E1]", "句子二[E2]"]
    assert hallucination_rate(assertions, cited) == 0.0
    assert hallucination_rate(assertions, []) == 1.0


def test_split_assertions_claim_and_evidence_markers() -> None:
    text = "主张一[C1]。证据句[E2]。无引用句。"
    assertions, cited = split_assertions(text)
    assert assertions == ["主张一[C1]", "证据句[E2]", "无引用句"]
    assert cited == ["主张一[C1]", "证据句[E2]"]
    assert hallucination_rate(assertions, cited) == pytest.approx(1 / 3)


# --- faithfulness ------------------------------------------------------------


@pytest.mark.asyncio
async def test_faithfulness_two_of_three_entailed() -> None:
    claims = [_claim("claim:1", "甲"), _claim("claim:2", "乙"), _claim("claim:3", "丙")]
    judge = FixedJudge({"甲", "乙"})
    value = await faithfulness(claims, ["证据甲", "证据乙"], judge)
    assert value == pytest.approx(2 / 3, abs=1e-3)
    assert round(value, 3) == 0.667
    # judge receives one prompt per claim (逐条判定)
    assert len(judge.prompts) == 3


@pytest.mark.asyncio
async def test_faithfulness_judge_failure_counts_half() -> None:
    claims = [_claim("claim:1", "甲"), _claim("claim:2", "乙")]
    value = await faithfulness(claims, ["证据"], BrokenJudge())
    assert value == pytest.approx(0.5)  # 每条失败按 0.5 计入


@pytest.mark.asyncio
async def test_faithfulness_garbage_reply_is_judge_failure() -> None:
    claims = [_claim("claim:1", "甲")]
    result = await judge_claims(claims, ["证据"], GarbageJudge())
    assert result.value == pytest.approx(0.5)
    assert result.judge_failures == 1
    assert result.verdicts[0].entailed is None


@pytest.mark.asyncio
async def test_faithfulness_marks_failures_in_verdicts() -> None:
    claims = [_claim("claim:1", "甲"), _claim("claim:2", "乙")]
    judge = FixedJudge({"甲"})
    result = await judge_claims(claims, ["证据甲"], judge)
    assert result.judge_failures == 0
    assert [verdict.entailed for verdict in result.verdicts] == [True, False]
    assert result.value == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_faithfulness_empty_claims() -> None:
    value = await faithfulness([], ["证据"], FixedJudge(set()))
    assert value == 0.0


# --- keyword_coverage --------------------------------------------------------


def test_keyword_coverage() -> None:
    assert keyword_coverage("华鑫贸易风险等级高", ["华鑫", "高"]) == 1.0
    assert keyword_coverage("华鑫贸易", ["华鑫", "凯越"]) == 0.5
    assert keyword_coverage("任意文本", []) == 0.0
    assert keyword_coverage("文本", ["", "文本"]) == 0.5


# --- aggregate ---------------------------------------------------------------


def test_aggregate_hand_computed() -> None:
    summaries = aggregate({"x": [1.0, 0.5, 0.2, 0.0]})
    summary = summaries["x"]
    assert summary.n == 4
    assert summary.mean == pytest.approx(0.425)
    assert summary.p50 == pytest.approx(0.35)  # 0.2 与 0.5 线性插值
    assert summary.p95 == pytest.approx(0.925)  # 0.5 与 1.0 线性插值


def test_summarize_edges() -> None:
    single = summarize([0.7])
    assert (single.mean, single.p50, single.p95, single.n) == (0.7, 0.7, 0.7, 1)
    empty = summarize([])
    assert (empty.mean, empty.n) == (0.0, 0)
    assert aggregate({}) == {}
