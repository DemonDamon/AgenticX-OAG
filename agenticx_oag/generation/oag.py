"""OAG generator (P05 FR-5): answers strictly from a ContextPack."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from agenticx_oag.context.pack import ContextPack
from agenticx_oag.contracts.stores import LLMProvider

CITATION_RE = r"\[([EC])(\d+)\]"
"""Citation marker pattern: ``[E{n}]`` references evidence, ``[C{n}]`` claim n."""

GENERATION_SYSTEM = (
    "你是 OAG（Ontology-Augmented Generation）回答器。规则：\n"
    "1. 只能使用 Context Pack 内的 evidence 与 claims 作答，禁止引入外部知识。\n"
    "2. 每个陈述句后必须紧跟引用标记：证据用 [E1] 形式，主张用 [C1] 形式"
    "（编号对应 evidence.id 的数字部分 / claims 列表序号）。\n"
    "3. 无证据支撑的内容必须显式说明「根据现有证据无法判断」。"
)

_MARKER = re.compile(CITATION_RE)


class Citation(BaseModel):
    """A citation marker parsed from the answer text."""

    marker: str  # e.g. "[E1]"
    evidence_id: str | None = None  # set for [E{n}] markers
    claim_id: str | None = None  # set for [C{n}] markers -> "claim:{n}"


class OAGAnswer(BaseModel):
    """Generator output with parsed citations."""

    text: str
    citations: list[Citation] = Field(default_factory=list)


class OAGGenerator:
    """Generates answers constrained to the pack's evidence and claims."""

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    def build_prompt(self, pack: ContextPack) -> str:
        legend = (
            f"Context Pack（JSON）：\n{pack.to_json()}\n\n"
            "引用图例：evidence.id E{n} 用 [E{n}] 引用；"
            "claims 列表第 n 条（claim_id 为 claim:{n}）用 [C{n}] 引用。"
        )
        return legend

    async def generate(self, pack: ContextPack) -> OAGAnswer:
        text = await self._llm.complete(
            self.build_prompt(pack), system=GENERATION_SYSTEM
        )
        return OAGAnswer(text=text, citations=parse_citations(text))


def parse_citations(text: str) -> list[Citation]:
    """Parse ``[E{n}]`` / ``[C{n}]`` markers, deduplicated in order."""
    citations: list[Citation] = []
    seen: set[tuple[str | None, str | None]] = set()
    for match in _MARKER.finditer(text):
        kind, number = match.group(1), match.group(2)
        citation = (
            Citation(marker=match.group(0), evidence_id=f"E{number}")
            if kind == "E"
            else Citation(marker=match.group(0), claim_id=f"claim:{number}")
        )
        key = (citation.evidence_id, citation.claim_id)
        if key not in seen:
            seen.add(key)
            citations.append(citation)
    return citations
