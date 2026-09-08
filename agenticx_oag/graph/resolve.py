"""Two-level entity disambiguation (FR-4).

Level 1: same object_type + same primary-key value (the record ``id``)
merges unconditionally (property union, provenance chained).
Level 2 (when an embedder is injected): same-type records whose
"display name + key attributes" embedding cosine is >= threshold merge,
with the survivor's provenance flagged ``merged_via: "embedding"``.

``resolve`` returns the deduplicated records plus an ``alias_map``
(merged-away id -> surviving id) for link redirection (FR-5).
"""

from __future__ import annotations

import numpy as np

from agenticx_oag.contracts.stores import EmbeddingProvider
from agenticx_oag.graph.records import ObjectRecord


class EntityResolver:
    def __init__(self, embedder: EmbeddingProvider | None, threshold: float = 0.92) -> None:
        self._embedder = embedder
        self._threshold = threshold

    async def resolve(
        self, objects: list[ObjectRecord]
    ) -> tuple[list[ObjectRecord], dict[str, str]]:
        survivors = self._resolve_by_primary_key(objects)
        alias_map: dict[str, str] = {}
        if self._embedder is not None and len(survivors) > 1:
            survivors, alias_map = await self._resolve_by_embedding(survivors)
        return survivors, alias_map

    # -- level 1: primary-key exact match --------------------------------------

    def _resolve_by_primary_key(self, objects: list[ObjectRecord]) -> list[ObjectRecord]:
        survivors: list[ObjectRecord] = []
        index_by_key: dict[tuple[str, str], int] = {}
        for record in objects:
            key = (record.object_type, record.id)
            found = index_by_key.get(key)
            if found is None:
                index_by_key[key] = len(survivors)
                survivors.append(record)
            else:
                _absorb(survivors[found], record)
        return survivors

    # -- level 2: embedding cosine ----------------------------------------------

    async def _resolve_by_embedding(
        self, records: list[ObjectRecord]
    ) -> tuple[list[ObjectRecord], dict[str, str]]:
        texts = [_record_text(r) for r in records]
        vectors = await self._embedder.embed(texts)  # type: ignore[union-attr]
        if len(vectors) != len(records):
            raise ValueError(
                f"embedder returned {len(vectors)} vectors for {len(records)} texts"
            )
        # union-find over record indices; pairs only within the same object_type
        parent = list(range(len(records)))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i in range(len(records)):
            for j in range(i + 1, len(records)):
                if records[i].object_type != records[j].object_type:
                    continue
                if _cosine(vectors[i], vectors[j]) >= self._threshold:
                    root_i, root_j = find(i), find(j)
                    if root_i != root_j:
                        parent[root_j] = root_i

        alias_map: dict[str, str] = {}
        merged_away: set[int] = set()
        groups: dict[int, list[int]] = {}
        for i in range(len(records)):
            groups.setdefault(find(i), []).append(i)
        for members in groups.values():
            if len(members) < 2:
                continue
            survivor = records[members[0]]
            for i in members[1:]:
                merged = records[i]
                _absorb(survivor, merged)
                survivor.prov.merged_via = "embedding"
                alias_map[merged.id] = survivor.id
                merged_away.add(i)
        survivors = [rec for i, rec in enumerate(records) if i not in merged_away]
        return survivors, alias_map


def _absorb(survivor: ObjectRecord, merged: ObjectRecord) -> None:
    """Union properties (later wins) and chain the merged record's provenance."""
    survivor.properties = {**survivor.properties, **merged.properties}
    survivor.prov.merged_provs.append(merged.prov.model_dump())


def _record_text(record: ObjectRecord) -> str:
    """Display name + key attributes, as the embedding input."""
    name = str(record.properties.get("name", record.id))
    parts = [name] + [
        f"{key}={value}" for key, value in sorted(record.properties.items()) if key != "id"
    ]
    return " | ".join(parts)


def _cosine(a: list[float] | np.ndarray, b: list[float] | np.ndarray) -> float:
    vec_a, vec_b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    norm = float(np.linalg.norm(vec_a) * np.linalg.norm(vec_b))
    if norm == 0.0:
        return 0.0
    return float(np.dot(vec_a, vec_b) / norm)
