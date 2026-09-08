"""Evaluation metrics (P06 FR-1): pure, deterministic functions.

Sentence-level rules reuse the P05 citation-validator constants (imported,
never duplicated): ``iter_sentences`` splitting, the question terminators and
the lead-in whitelist. ``faithfulness`` is async because the injected judge is
an async :class:`~agenticx_oag.contracts.stores.LLMProvider`.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from pydantic import BaseModel

from agenticx_oag.context.pack import Claim
from agenticx_oag.contracts.stores import LLMProvider
from agenticx_oag.generation.oag import CITATION_RE
from agenticx_oag.generation.validate import (
    _QUESTION_DELIMS,
    LEAD_WHITELIST,
    iter_sentences,
)
from agenticx_oag.retrieval.entity_link import parse_json_payload

JUDGE_PROMPT_MARKER = "判断以下陈述是否能由给定证据推出"
"""Marker shared with the eval-side mock judge for prompt dispatch."""

_JUDGE_FAILURE_SCORE = 0.5  # plan FR-1: a judge failure counts as 0.5

_JUDGE_PROMPT = (
    f"{JUDGE_PROMPT_MARKER}，仅输出 JSON "
    '{{"entailed": true/false, "reason": "..."}}。\n\n'
    "陈述：{claim}\n\n"
    "证据：\n{evidence}"
)

_CITATION_MARKER_RE = re.compile(CITATION_RE)


class MetricSummary(BaseModel):
    """Aggregated view of one metric across items (mean / p50 / p95 / n)."""

    mean: float
    p50: float
    p95: float
    n: int


@dataclass
class FaithfulnessVerdict:
    """One claim's judge outcome; ``entailed=None`` marks a judge failure."""

    claim_id: str
    entailed: bool | None
    reason: str = ""


@dataclass
class FaithfulnessResult:
    """Faithfulness value plus per-claim detail (failure marking)."""

    value: float
    verdicts: list[FaithfulnessVerdict] = field(default_factory=list)
    judge_failures: int = 0


def recall_at_k(retrieved_ids: list[str], golden_ids: list[str], k: int) -> float:
    """Fraction of golden ids hit by the first ``k`` retrieved ids."""
    if not golden_ids or k <= 0:
        return 0.0
    top_k = set(retrieved_ids[:k])
    hits = len(set(golden_ids) & top_k)
    return hits / len(set(golden_ids))


def citation_correctness(
    answer_citations: list[str], pack_evidence_ids: list[str]
) -> float:
    """Legal citations (present in the pack's evidence/claim ids) / total.

    An answer with no citations scores 0.0 (vacuous correctness is not
    credited).
    """
    if not answer_citations:
        return 0.0
    legal = set(pack_evidence_ids)
    valid = sum(1 for citation in answer_citations if citation in legal)
    return valid / len(answer_citations)


def hallucination_rate(
    answer_sentences: list[str], cited_sentences: list[str]
) -> float:
    """Uncited assertion sentences / total assertion sentences."""
    if not answer_sentences:
        return 0.0
    cited = set(cited_sentences)
    uncited = sum(1 for sentence in answer_sentences if sentence not in cited)
    return uncited / len(answer_sentences)


def keyword_coverage(answer_text: str, keywords: list[str]) -> float:
    """Weak answer-coverage check: hit golden keywords / total keywords."""
    if not keywords:
        return 0.0
    hits = sum(1 for keyword in keywords if keyword and keyword in answer_text)
    return hits / len(keywords)


def split_assertions(text: str) -> tuple[list[str], list[str]]:
    """Split into ``(assertion_sentences, cited_subset)`` via the P05 rules.

    Questions (terminator ``？``/``?``) and lead-in whitelisted sentences are
    exempt and never count as assertions.
    """
    assertions: list[str] = []
    cited: list[str] = []
    for fragment, terminator in iter_sentences(text):
        if terminator in _QUESTION_DELIMS:
            continue  # questions are exempt
        sentence = fragment.strip()
        if not sentence or sentence.startswith(LEAD_WHITELIST):
            continue  # lead-in / disclaimer sentences are exempt
        assertions.append(sentence)
        if _CITATION_MARKER_RE.search(sentence):
            cited.append(sentence)
    return assertions, cited


async def faithfulness(
    claims: list[Claim], evidence_texts: list[str], judge: LLMProvider
) -> float:
    """Entailed claims / total claims, judged one claim at a time."""
    return (await judge_claims(claims, evidence_texts, judge)).value


async def judge_claims(
    claims: list[Claim], evidence_texts: list[str], judge: LLMProvider
) -> FaithfulnessResult:
    """Judge every claim; a judge failure scores 0.5 and is marked."""
    if not claims:
        return FaithfulnessResult(value=0.0)
    evidence_block = "\n".join(f"- {text}" for text in evidence_texts) or "- （无证据）"
    verdicts: list[FaithfulnessVerdict] = []
    score = 0.0
    failures = 0
    for claim in claims:
        prompt = _JUDGE_PROMPT.format(claim=claim.text, evidence=evidence_block)
        try:
            raw = await judge.complete(prompt, json_mode=True)
            payload = parse_json_payload(raw)
            entailed = (
                payload.get("entailed") if isinstance(payload, dict) else None
            )
            if not isinstance(entailed, bool):
                entailed = None
        except Exception:  # noqa: BLE001 -- judge failure is a scored outcome
            entailed = None
        if entailed is None:
            failures += 1
            verdicts.append(
                FaithfulnessVerdict(claim.claim_id, None, "judge failure")
            )
            score += _JUDGE_FAILURE_SCORE
        else:
            verdicts.append(FaithfulnessVerdict(claim.claim_id, entailed))
            score += 1.0 if entailed else 0.0
    return FaithfulnessResult(
        value=score / len(claims), verdicts=verdicts, judge_failures=failures
    )


def summarize(values: list[float]) -> MetricSummary:
    """Mean / p50 / p95 (linear interpolation) / n over one metric."""
    ordered = sorted(values)
    if not ordered:
        return MetricSummary(mean=0.0, p50=0.0, p95=0.0, n=0)
    return MetricSummary(
        mean=sum(ordered) / len(ordered),
        p50=_percentile(ordered, 0.5),
        p95=_percentile(ordered, 0.95),
        n=len(ordered),
    )


def aggregate(
    metric_values: dict[str, list[float]],
) -> dict[str, MetricSummary]:
    """Summarize every metric list independently."""
    return {name: summarize(values) for name, values in metric_values.items()}


def _percentile(ordered: list[float], fraction: float) -> float:
    if len(ordered) == 1:
        return ordered[0]
    rank = fraction * (len(ordered) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    weight = rank - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight
