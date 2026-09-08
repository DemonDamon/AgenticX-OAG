"""Instance-graph record models with provenance (FR-1).

``ObjectRecord``/``LinkRecord`` are the in-flight units produced by the
extractor, deduplicated by the resolver and serialized into the graph store;
``ProvInfo`` rides along as the provenance payload stored under ``__prov``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProvInfo(BaseModel):
    """Provenance for one extraction/merge event.

    ``merged_via`` records which resolver level absorbed the record
    ("" | "embedding") and ``merged_provs`` keeps the provenance of records
    merged into this one (FR-4 "prov 链接追加").
    """

    source_doc: str = ""
    span: str = ""
    extracted_at: str = ""
    confidence: float = 0.0
    merged_via: str = ""
    merged_provs: list[dict[str, Any]] = Field(default_factory=list)


class ObjectRecord(BaseModel):
    """A typed entity instance; ``id`` holds the ObjectType primary-key value."""

    object_type: str
    id: str
    properties: dict[str, Any] = Field(default_factory=dict)
    prov: ProvInfo = Field(default_factory=ProvInfo)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ObjectRecord:
        return cls.model_validate(data)


class LinkRecord(BaseModel):
    """A typed relation instance between two object ids."""

    link_type: str
    source_id: str
    target_id: str
    properties: dict[str, Any] = Field(default_factory=dict)
    prov: ProvInfo = Field(default_factory=ProvInfo)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LinkRecord:
        return cls.model_validate(data)
