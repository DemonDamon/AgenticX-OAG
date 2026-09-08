"""Context Pack pipeline (P05 FR-4): question -> structured ContextPack.

Steps: rewrite -> entity linking -> hybrid retrieval -> claim generation ->
uncertainty summary. The pack is a pure function product (no persistence).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from agenticx_oag.context.pack import (
    Claim,
    ClaimStatus,
    ContextPack,
    LedgerEvidence,
)
from agenticx_oag.contracts.stores import LLMProvider
from agenticx_oag.ontology.model import Ontology
from agenticx_oag.retrieval.entity_link import EntityLinker, parse_json_payload

if TYPE_CHECKING:
    from agenticx_oag.retrieval.ontology_hybrid import (
        OntologyHybridRetriever,
        RetrievalResult,
    )

_MAX_REWRITES = 2
_UNCERTAIN_CONFIDENCE = 0.5  # below this a claim is unverified (schema status)

_REWRITE_SYSTEM = "你是检索查询改写器，只输出 JSON。"
_CLAIM_SYSTEM = "你是基于证据的主张生成器，只输出 JSON。"
_UNCERTAINTY_SYSTEM = "你是不确定性分析器，用一段中文陈述总结。"


class ContextPackPipeline:
    """Orchestrates LLM rewriting/linking/claiming around the retriever."""

    def __init__(
        self, llm: LLMProvider, ontology: Ontology, retriever: OntologyHybridRetriever
    ) -> None:
        self._llm = llm
        self._retriever = retriever
        self._linker = EntityLinker(llm, ontology)

    async def build_pack(self, question: str) -> ContextPack:
        rewrites = await self._rewrite(question)
        linked = await self._linker.link(question)
        main_question = rewrites[1] if len(rewrites) > 1 else rewrites[0]
        result: RetrievalResult = await self._retriever.retrieve(
            main_question, linked
        )
        claims = await self._generate_claims(main_question, result)
        uncertainty = await self._summarize_uncertainty(claims, result)
        return ContextPack(
            question=question,
            rewrites=rewrites,
            object_refs=list(result.objects),
            evidence=list(result.evidence),
            claims=claims,
            uncertainty=uncertainty,
        )

    async def _rewrite(self, question: str) -> list[str]:
        prompt = (
            f"研究问题：{question}\n\n"
            "生成 1~2 个澄清改写（含指代消解），用于检索。"
            '只输出 JSON 字符串数组，例如 ["改写一", "改写二"]。'
        )
        raw = await self._llm.complete(prompt, system=_REWRITE_SYSTEM, json_mode=True)
        payload = parse_json_payload(raw)
        rewrites = [question]
        if isinstance(payload, list):
            extra = [str(item).strip() for item in payload if str(item).strip()]
            rewrites.extend(extra[:_MAX_REWRITES])
        return rewrites

    async def _generate_claims(
        self, question: str, result: RetrievalResult
    ) -> list[Claim]:
        if not result.evidence:
            return []
        evidence_lines = [
            f"- {ev.id} | object={ev.object_id} | {ev.text}" for ev in result.evidence
        ]
        prompt = (
            f"问题：{question}\n\n证据列表：\n" + "\n".join(evidence_lines) + "\n\n"
            "基于且仅基于上述证据生成主张。规则：\n"
            '1. 只输出 JSON 数组，每项形如 {"text": "主张", "evidence_ids": ["E1"], "confidence": 0.9}。\n'
            "2. 每条主张必须标注支撑 evidence_ids，禁止引入证据外知识。\n"
            "3. 证据不足时 confidence 必须低于 0.5。"
        )
        raw = await self._llm.complete(prompt, system=_CLAIM_SYSTEM, json_mode=True)
        payload = parse_json_payload(raw)
        if not isinstance(payload, list):
            return []

        valid_ids = {ev.id for ev in result.evidence}
        today = datetime.now(UTC).date().isoformat()
        claims: list[Claim] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "")).strip()
            evidence_ids = [
                str(ref) for ref in item.get("evidence_ids", []) if str(ref) in valid_ids
            ]
            if not text or not evidence_ids:
                continue  # claims without usable evidence are dropped
            supported = [ev for ev in result.evidence if ev.id in set(evidence_ids)]
            entities: list[str] = []
            for ev in supported:
                entity = f"entity:{ev.object_id}"
                if ev.object_id and entity not in entities:
                    entities.append(entity)
            if not entities:
                continue
            confidence = _clamp_confidence(item.get("confidence", _UNCERTAIN_CONFIDENCE))
            status = (
                ClaimStatus.SUPPORTED
                if confidence >= _UNCERTAIN_CONFIDENCE
                else ClaimStatus.UNVERIFIED
            )
            claims.append(
                Claim(
                    claim_id=f"claim:{len(claims) + 1}",
                    text=text,
                    status=status,
                    entities=entities,
                    evidence_ids=evidence_ids,
                    evidence=[
                        LedgerEvidence.from_evidence(ev, on_date=today)
                        for ev in supported
                    ],
                    confidence=confidence,
                )
            )
        return claims

    async def _summarize_uncertainty(
        self, claims: list[Claim], result: RetrievalResult
    ) -> str:
        claim_lines = [
            f"- {claim.claim_id}（status={claim.status.value}, confidence={claim.confidence:.2f}）"
            f" {claim.text}"
            for claim in claims
        ]
        prompt = (
            "基于以下主张与证据覆盖情况，用一段中文总结当前研究的不确定性"
            "（证据缺口、低置信主张、未覆盖方面）：\n"
            + "\n".join(claim_lines or ["- （无主张）"])
            + f"\n证据条数：{len(result.evidence)}"
        )
        try:
            raw = await self._llm.complete(prompt, system=_UNCERTAINTY_SYSTEM)
        except Exception:  # noqa: BLE001 -- rule-based fallback on LLM failure
            raw = ""
        text = raw.strip()
        if text:
            return text
        unverified = [c for c in claims if c.status is ClaimStatus.UNVERIFIED]
        return (
            f"共 {len(claims)} 条主张，其中 {len(unverified)} 条置信度低于 "
            f"{_UNCERTAIN_CONFIDENCE}；证据覆盖 {len(result.evidence)} 条，"
            "可能未覆盖问题的全部方面。"
        )


def _clamp_confidence(value: object) -> float:
    try:
        confidence = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        confidence = _UNCERTAIN_CONFIDENCE
    return max(0.0, min(1.0, confidence))
