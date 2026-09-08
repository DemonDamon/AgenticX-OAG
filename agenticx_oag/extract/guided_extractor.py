"""Ontology-guided LLM extraction with defensive parsing (FR-3, NFR-2).

Malformed responses or entries referencing undefined types are dropped with a
WARNING instead of aborting the batch; each chunk gets one retry on failure.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from agenticx_oag.contracts.stores import LLMProvider
from agenticx_oag.extract.prompts import build_system_prompt
from agenticx_oag.graph.records import LinkRecord, ObjectRecord, ProvInfo
from agenticx_oag.ontology.model import Ontology

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 2  # initial call + 1 retry (NFR-2)


class GuidedExtractor:
    def __init__(self, llm: LLMProvider, ontology: Ontology) -> None:
        self._llm = llm
        self._ontology = ontology
        self._object_types = {ot.api_name for ot in ontology.object_types}
        self._link_types = {lt.api_name for lt in ontology.link_types}
        self._system = build_system_prompt(ontology)
        self.warning_count = 0

    @property
    def system_prompt(self) -> str:
        return self._system

    async def extract(
        self, chunks: list[str]
    ) -> tuple[list[ObjectRecord], list[LinkRecord]]:
        objects: list[ObjectRecord] = []
        links: list[LinkRecord] = []
        for chunk in chunks:
            data = await self._extract_chunk(chunk)
            for entry in _as_list(data.get("objects")):
                obj = self._to_object(entry)
                if obj is not None:
                    objects.append(obj)
            for entry in _as_list(data.get("links")):
                link = self._to_link(entry)
                if link is not None:
                    links.append(link)
        return objects, links

    async def _extract_chunk(self, chunk: str) -> dict[str, Any]:
        last_error: Exception | None = None
        for _attempt in range(_MAX_ATTEMPTS):
            try:
                raw = await self._llm.complete(chunk, system=self._system, json_mode=True)
                return self._parse_json(raw)
            except Exception as exc:  # noqa: BLE001 -- NFR-2: any LLM/parse failure must not abort the batch
                last_error = exc
                self._warn(f"chunk extraction failed: {exc}")
        logger.warning("skipping chunk after %d attempts: %s", _MAX_ATTEMPTS, last_error)
        return {}

    def _parse_json(self, raw: str) -> dict[str, Any]:
        text = raw.strip()
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("no JSON object found in LLM response")
        data = json.loads(text[start : end + 1])
        if not isinstance(data, dict):
            raise TypeError("LLM response is not a JSON object")
        return data

    def _to_object(self, entry: Any) -> ObjectRecord | None:
        if not isinstance(entry, dict):
            self._warn(f"dropping non-object entry: {entry!r}")
            return None
        object_type = entry.get("type")
        if object_type not in self._object_types:
            self._warn(f"dropping object with undefined type {object_type!r}")
            return None
        object_id = entry.get("id")
        if not isinstance(object_id, str) or not object_id:
            self._warn(f"dropping object without a valid id: {entry!r}")
            return None
        properties = entry.get("properties")
        if not isinstance(properties, dict):
            properties = {}
        return ObjectRecord(
            object_type=object_type,
            id=object_id,
            properties=properties,
            prov=ProvInfo(
                span=_as_str(entry.get("source_span")),
                extracted_at=_now_iso(),
                confidence=_as_float(entry.get("confidence")),
            ),
        )

    def _to_link(self, entry: Any) -> LinkRecord | None:
        if not isinstance(entry, dict):
            self._warn(f"dropping non-object link entry: {entry!r}")
            return None
        link_type = entry.get("type")
        if link_type not in self._link_types:
            self._warn(f"dropping link with undefined type {link_type!r}")
            return None
        source_id, target_id = entry.get("source_id"), entry.get("target_id")
        if (
            not isinstance(source_id, str)
            or not source_id
            or not isinstance(target_id, str)
            or not target_id
        ):
            self._warn(f"dropping link without valid endpoints: {entry!r}")
            return None
        properties = entry.get("properties")
        if not isinstance(properties, dict):
            properties = {}
        return LinkRecord(
            link_type=link_type,
            source_id=source_id,
            target_id=target_id,
            properties=properties,
            prov=ProvInfo(
                span=_as_str(entry.get("source_span")),
                extracted_at=_now_iso(),
                confidence=_as_float(entry.get("confidence")),
            ),
        )

    def _warn(self, message: str) -> None:
        self.warning_count += 1
        logger.warning("GuidedExtractor: %s", message)


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
