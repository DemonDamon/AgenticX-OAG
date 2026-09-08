"""Ontology-guided hybrid retrieval (P05 FR-2, FR-7).

Fusion of three channels:

1. Vector recall: embed the question, search the vector store (top_k x 3).
2. Type constraint: keep only hits whose ``meta.object_type`` is among the
   linked types (no filtering when ``linked`` is empty).
3. Graph expansion: neighbors (max_hops=2, at most 5 per object) of the
   surviving top objects complete the evidence set.

Fused score (FR-2): ``vector_score * 0.6 + graph_bonus * 0.4`` where the
bonus is 0.25 (capped at 1.0) when the object appears on a graph expansion
path. Objects that did not survive the type constraint (or were not recalled
by the vector channel) contribute no vector score, so graph-completion
evidence scores 0.1 and always ranks below vector-admitted evidence.

Degraded mode (FR-7): when the vector store is missing or raises, retrieval
falls back to pure graph traversal seeded from the linked entity types and
the result is flagged ``degraded=True``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agenticx_oag.context.pack import Evidence, ObjectRef
from agenticx_oag.contracts.stores import EmbeddingProvider, GraphStore, VectorStore
from agenticx_oag.retrieval.entity_link import LinkedEntity

VECTOR_WEIGHT = 0.6
GRAPH_WEIGHT = 0.4
GRAPH_ADJACENCY_BONUS = 0.25  # bonus for objects on a graph expansion path
GRAPH_BONUS_CAP = 1.0
MAX_NEIGHBORS_PER_OBJECT = 5
DEFAULT_TOP_K = 8
DEFAULT_MAX_EVIDENCE = 24  # NFR-2: evidence cap to prevent prompt bloat


class RetrievalResult(BaseModel):
    """Output of :meth:`OntologyHybridRetriever.retrieve`."""

    evidence: list[Evidence] = Field(default_factory=list)
    objects: list[ObjectRef] = Field(default_factory=list)
    degraded: bool = False  # FR-7: vector channel unavailable
    reranked: bool = False  # placeholder for a future reranker


class OntologyHybridRetriever:
    """Vector recall + ontology type constraint + graph expansion."""

    def __init__(
        self,
        graph: GraphStore,
        vectors: VectorStore | None = None,
        embedder: EmbeddingProvider | None = None,
        *,
        collection: str = "objects",
        max_evidence: int = DEFAULT_MAX_EVIDENCE,
    ) -> None:
        self._graph = graph
        self._vectors = vectors
        self._embedder = embedder
        self._collection = collection
        self._max_evidence = max_evidence

    async def retrieve(
        self,
        question: str,
        linked: list[LinkedEntity],
        top_k: int = DEFAULT_TOP_K,
    ) -> RetrievalResult:
        hits = await self._vector_recall(question, top_k)
        if hits is None:
            return await self._retrieve_graph_only(linked, top_k)

        allowed_types = {entity.object_type for entity in linked} or None
        filtered = [
            hit
            for hit in hits
            if allowed_types is None or hit["meta"].get("object_type") in allowed_types
        ]
        filtered.sort(key=lambda hit: hit["score"], reverse=True)
        seeds = filtered[:top_k]

        # Graph expansion over the surviving top objects.
        neighbor_objects: dict[str, dict[str, Any]] = {}
        for seed in seeds:
            neighbors = await self._graph.neighbors(seed["id"], max_hops=2)
            for nb in neighbors[:MAX_NEIGHBORS_PER_OBJECT]:
                nb_id = _object_id(nb)
                if nb_id and nb_id not in neighbor_objects:
                    nb = dict(nb)
                    nb.setdefault("provenance", f"graph:{seed['id']}")
                    neighbor_objects[nb_id] = nb

        candidates: dict[str, dict[str, Any]] = {}
        for seed in seeds:
            candidates[seed["id"]] = {
                "id": seed["id"],
                "object_type": seed["meta"].get("object_type", ""),
                "text": seed["meta"].get("text", ""),
                "provenance": seed["meta"].get("prov", seed["meta"].get("provenance", "")),
                "vector_score": seed["score"],
            }
        for nb_id, nb in neighbor_objects.items():
            if nb_id in candidates:
                continue  # vector-admitted objects keep their vector score
            candidates[nb_id] = {
                "id": nb_id,
                "object_type": _object_type(nb),
                "text": _object_text(nb),
                "provenance": str(nb.get("provenance", "")),
                "vector_score": 0.0,
            }

        return self._build_result(candidates, set(neighbor_objects), degraded=False)

    async def _vector_recall(
        self, question: str, top_k: int
    ) -> list[dict[str, Any]] | None:
        """Return parsed vector hits, or None when the channel is unavailable."""
        if self._vectors is None or self._embedder is None:
            return None
        try:
            vectors = await self._embedder.embed([question])
            hits = await self._vectors.search(
                self._collection, vectors[0], top_k * 3
            )
        except Exception:  # noqa: BLE001 -- FR-7: any vector-channel failure degrades
            return None  # FR-7: degrade to pure graph retrieval
        return [_parse_hit(hit) for hit in hits]

    async def _retrieve_graph_only(
        self, linked: list[LinkedEntity], top_k: int
    ) -> RetrievalResult:
        """FR-7 fallback: evidence from the neighborhood of linked-type objects.

        No vector scores exist, so every item scores ``0 * 0.6 + 0.25 * 0.4``.
        """
        candidates: dict[str, dict[str, Any]] = {}
        expansion_ids: set[str] = set()
        for entity in linked:
            objects = await self._graph.get_objects(entity.object_type)
            for obj in objects[:top_k]:
                obj_id = _object_id(obj)
                if not obj_id or obj_id in candidates:
                    continue
                seed = dict(obj)
                seed.setdefault("provenance", f"graph:{entity.object_type}")
                candidates[obj_id] = {
                    "id": obj_id,
                    "object_type": _object_type(obj),
                    "text": _object_text(obj),
                    "provenance": str(seed.get("provenance", "")),
                    "vector_score": 0.0,
                }
                expansion_ids.add(obj_id)  # seeds are anchored graph evidence
                neighbors = await self._graph.neighbors(obj_id, max_hops=2)
                for nb in neighbors[:MAX_NEIGHBORS_PER_OBJECT]:
                    nb_id = _object_id(nb)
                    if not nb_id or nb_id in candidates:
                        continue
                    nb = dict(nb)
                    nb.setdefault("provenance", f"graph:{obj_id}")
                    candidates[nb_id] = {
                        "id": nb_id,
                        "object_type": _object_type(nb),
                        "text": _object_text(nb),
                        "provenance": str(nb.get("provenance", "")),
                        "vector_score": 0.0,
                    }
                    expansion_ids.add(nb_id)
        return self._build_result(candidates, expansion_ids, degraded=True)

    def _build_result(
        self,
        candidates: dict[str, dict[str, Any]],
        expansion_ids: set[str],
        *,
        degraded: bool,
    ) -> RetrievalResult:
        scored: list[tuple[float, dict[str, Any]]] = []
        for candidate in candidates.values():
            bonus = (
                min(GRAPH_ADJACENCY_BONUS, GRAPH_BONUS_CAP)
                if candidate["id"] in expansion_ids
                else 0.0
            )
            score = min(candidate["vector_score"] * VECTOR_WEIGHT + bonus * GRAPH_WEIGHT, 1.0)
            scored.append((score, candidate))
        scored.sort(key=lambda pair: pair[0], reverse=True)

        evidence: list[Evidence] = []
        objects: list[ObjectRef] = []
        seen_objects: set[str] = set()
        for index, (score, candidate) in enumerate(scored[: self._max_evidence], start=1):
            evidence.append(
                Evidence(
                    id=f"E{index}",
                    object_id=candidate["id"],
                    text=candidate["text"],
                    score=score,
                    provenance=candidate["provenance"],
                )
            )
            if candidate["id"] not in seen_objects:
                seen_objects.add(candidate["id"])
                objects.append(
                    ObjectRef(id=candidate["id"], object_type=candidate["object_type"])
                )
        return RetrievalResult(evidence=evidence, objects=objects, degraded=degraded)


def _parse_hit(hit: dict[str, Any]) -> dict[str, Any]:
    """Normalize a VectorStore search result entry."""
    hit_id = hit.get("id") or hit.get("object_id") or ""
    meta = hit.get("meta") if isinstance(hit.get("meta"), dict) else {}
    return {"id": str(hit_id), "score": float(hit.get("score", 0.0)), "meta": meta}


def _object_id(obj: dict[str, Any]) -> str:
    return str(obj.get("id") or obj.get("object_id") or "")


def _object_type(obj: dict[str, Any]) -> str:
    return str(obj.get("object_type") or obj.get("type") or "")


def _object_text(obj: dict[str, Any]) -> str:
    for key in ("text", "content", "description", "name"):
        value = obj.get(key)
        if value:
            return str(value)
    properties = obj.get("properties")
    if isinstance(properties, dict) and properties:
        return "; ".join(f"{key}={value}" for key, value in properties.items())
    return ""
