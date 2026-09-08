"""Citation validation (P05 FR-6): every assertion must cite the pack.

- ``dangling``: the answer cites an evidence/claim id that does not exist in
  the pack.
- ``unsupported``: an assertion sentence without any citation marker.
  Questions, and sentences starting with a whitelisted lead-in
  (「根据现有证据」/「综上」/「如下」/「针对该问题」), are exempt.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Literal

from pydantic import BaseModel

from agenticx_oag.context.pack import ContextPack
from agenticx_oag.generation.oag import CITATION_RE, OAGAnswer

LEAD_WHITELIST: tuple[str, ...] = ("根据现有证据", "综上", "如下", "针对该问题")

_SENT_SPLIT_RE = re.compile(r"([。！？!?\n])")
_CITATION_RE = re.compile(CITATION_RE)
_QUESTION_DELIMS = ("？", "?")


def iter_sentences(text: str) -> Iterator[tuple[str, str]]:
    """Yield ``(fragment, terminator)`` pairs; terminator may be ``''``."""
    parts = _SENT_SPLIT_RE.split(text)
    for index in range(0, len(parts), 2):
        fragment = parts[index]
        terminator = parts[index + 1] if index + 1 < len(parts) else ""
        if fragment.strip():
            yield fragment, terminator


class CitationViolation(BaseModel):
    kind: Literal["dangling", "unsupported"]
    marker: str = ""  # offending citation marker (dangling)
    ref_id: str = ""  # missing evidence/claim id (dangling)
    sentence: str = ""  # offending sentence (unsupported)


class CitationValidator:
    """Strict post-generation citation checking against the pack."""

    def validate(self, answer: OAGAnswer, pack: ContextPack) -> list[CitationViolation]:
        violations: list[CitationViolation] = []
        known_evidence = {ev.id for ev in pack.evidence}
        known_claims = {claim.claim_id for claim in pack.claims}
        for citation in answer.citations:
            if citation.evidence_id is not None and citation.evidence_id not in known_evidence:
                violations.append(
                    CitationViolation(
                        kind="dangling", marker=citation.marker, ref_id=citation.evidence_id
                    )
                )
            if citation.claim_id is not None and citation.claim_id not in known_claims:
                violations.append(
                    CitationViolation(
                        kind="dangling", marker=citation.marker, ref_id=citation.claim_id
                    )
                )
        for fragment, terminator in iter_sentences(answer.text):
            if terminator in _QUESTION_DELIMS:
                continue  # questions are exempt
            sentence = fragment.strip()
            if _CITATION_RE.search(sentence):
                continue  # cited assertion
            if sentence.startswith(LEAD_WHITELIST):
                continue  # lead-in / disclaimer sentences are exempt
            violations.append(CitationViolation(kind="unsupported", sentence=sentence))
        return violations

    def is_valid(self, answer: OAGAnswer, pack: ContextPack) -> bool:
        return not self.validate(answer, pack)
