"""Context Pack models (P05 FR-3).

Field naming follows ``schemas/claim-ledger.schema.json`` wherever the schema
and the plan disagree (the plan explicitly defers to the schema):

- ``Claim.claim_id`` / ``Claim.text`` / ``Claim.status`` / ``Claim.entities`` /
  ``Claim.evidence`` mirror the schema claim object. The plan's shorthand
  (``id``/``statement``/``status: asserted|uncertain``) maps to
  ``claim:...`` / ``text`` / ``supported``|``unverified``.
- ``Claim.evidence_ids`` is a Pack-internal link to :class:`Evidence` ids
  (``E{n}``) and is NOT part of the ledger projection (the schema claim object
  has ``additionalProperties: false``).
- The ledger schema only allows four top-level keys (``schema_version``,
  ``research_question``, ``generated_at``, ``claims``), so a full
  :class:`ContextPack` dump can never validate directly. The ledger snapshot
  is therefore exposed via :meth:`ContextPack.to_ledger` (nested projection).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

CLAIM_LEDGER_SCHEMA_VERSION = "0.1.0"

_CLAIM_ID_PATTERN = re.compile(r"^claim:[A-Za-z0-9._-]+$")
_ENTITY_REF_PATTERN = re.compile(r"^entity:[A-Za-z0-9._-]+$")
_SOURCE_ID_PATTERN = re.compile(r"^src:[A-Za-z0-9._-]+$")
_URL_SCHEME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")


class ObjectRef(BaseModel):
    """A reference to an ontology object involved in a pack."""

    id: str
    object_type: str = ""


class Evidence(BaseModel):
    """A retrieval evidence item (vector hit or graph-expanded object)."""

    id: str  # "E{n}", unique within a pack
    object_id: str
    text: str = ""
    score: float = 0.0
    provenance: str = ""


class ClaimStatus(str, Enum):
    """Mirrors the claim-ledger schema status enum."""

    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    INFERRED = "inferred"
    CONTESTED = "contested"
    UNVERIFIED = "unverified"


class EvidenceSourceType(str, Enum):
    """Mirrors the claim-ledger schema source_type enum."""

    PRIMARY = "primary"
    OFFICIAL = "official"
    PEER_REVIEWED = "peer_reviewed"
    DATASET = "dataset"
    SECONDARY = "secondary"
    OTHER = "other"


class EvidenceStrength(str, Enum):
    """Mirrors the claim-ledger schema strength enum."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class LedgerEvidence(BaseModel):
    """Evidence entry as defined by the claim-ledger schema."""

    source_id: str  # "src:..."
    url: str = ""
    locator: str = ""
    source_type: EvidenceSourceType = EvidenceSourceType.OTHER
    publication_date: str = ""  # ISO date
    accessed_at: str = ""  # ISO date
    strength: EvidenceStrength = EvidenceStrength.MEDIUM
    excerpt: str = ""

    @field_validator("source_id")
    @classmethod
    def _validate_source_id(cls, value: str) -> str:
        if not _SOURCE_ID_PATTERN.match(value):
            raise ValueError(f"source_id {value!r} must match 'src:<id>'")
        return value

    @classmethod
    def from_evidence(
        cls, evidence: Evidence, *, on_date: str, publication_date: str | None = None
    ) -> LedgerEvidence:
        """Project a retrieval :class:`Evidence` into the ledger structure.

        ``on_date`` (ISO ``YYYY-MM-DD``) is used for ``accessed_at`` and, when
        unknown, ``publication_date``. Strength derives from the fused score.
        """
        if _URL_SCHEME_PATTERN.match(evidence.provenance or ""):
            url = evidence.provenance
        else:
            url = f"urn:agenticx:evidence:{evidence.id}"
        return cls(
            source_id=f"src:{evidence.id}",
            url=url,
            locator=f"object:{evidence.object_id}" if evidence.object_id else evidence.id,
            source_type=EvidenceSourceType.OTHER,
            publication_date=publication_date or on_date,
            accessed_at=on_date,
            strength=strength_from_score(evidence.score),
            excerpt=evidence.text,
        )


def strength_from_score(score: float) -> EvidenceStrength:
    """Map a fused retrieval score to ledger evidence strength."""
    if score >= 2 / 3:
        return EvidenceStrength.HIGH
    if score >= 1 / 3:
        return EvidenceStrength.MEDIUM
    return EvidenceStrength.LOW


class ClaimScope(BaseModel):
    """Mirrors the claim-ledger schema scope object."""

    time_range: str = ""
    geography: str = ""
    conditions: str = ""


class Claim(BaseModel):
    """A claim aligned with the claim-ledger schema claim object."""

    claim_id: str  # "claim:1", "claim:2", ...
    text: str
    status: ClaimStatus = ClaimStatus.UNVERIFIED
    entities: list[str] = Field(min_length=1)  # "entity:<object_id>"
    relations: list[str] = Field(default_factory=list)
    scope: ClaimScope | None = None
    evidence: list[LedgerEvidence] = Field(min_length=1)
    reasoning: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    limitations: list[str] = Field(default_factory=list)
    # Pack-internal linkage to Evidence ids ("E{n}"); excluded from to_ledger().
    evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("claim_id")
    @classmethod
    def _validate_claim_id(cls, value: str) -> str:
        if not _CLAIM_ID_PATTERN.match(value):
            raise ValueError(f"claim_id {value!r} must match 'claim:<id>'")
        return value

    @field_validator("entities")
    @classmethod
    def _validate_entities(cls, value: list[str]) -> list[str]:
        for entity in value:
            if not _ENTITY_REF_PATTERN.match(entity):
                raise ValueError(f"entity ref {entity!r} must match 'entity:<id>'")
        return value

    def to_ledger_claim(self) -> dict[str, Any]:
        """Project this claim onto the schema claim object (no extra keys)."""
        claim: dict[str, Any] = {
            "claim_id": self.claim_id,
            "text": self.text,
            "status": self.status.value,
            "entities": list(self.entities),
            "relations": list(self.relations),
            "evidence": [item.model_dump(mode="json") for item in self.evidence],
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "limitations": list(self.limitations),
        }
        if self.scope is not None:
            claim["scope"] = self.scope.model_dump(mode="json")
        return claim


class ContextPack(BaseModel):
    """The single generation context produced by :class:`ContextPackPipeline`.

    The pack is a pure in-memory value object: no caching or storage backend
    (persisting it is the caller's decision).
    """

    pack_id: str = Field(default_factory=lambda: "pack_" + uuid4().hex[:12])
    question: str
    rewrites: list[str] = Field(default_factory=list)  # [0] is the original question
    object_refs: list[ObjectRef] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    uncertainty: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, raw: str) -> ContextPack:
        return cls.model_validate_json(raw)

    def to_ledger(self) -> dict[str, Any]:
        """One-session claim-ledger snapshot, valid against the repo schema."""
        return {
            "schema_version": CLAIM_LEDGER_SCHEMA_VERSION,
            "research_question": self.question,
            "generated_at": self.created_at.isoformat(),
            "claims": [claim.to_ledger_claim() for claim in self.claims],
        }
