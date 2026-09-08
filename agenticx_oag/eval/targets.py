"""Eval targets (P06 FR-3): OAG full chain vs pure-RAG baseline.

The in-memory graph/vector stores and the prompt-dispatched mock LLM live here
because the evaluation must run without Docker or external providers (mock is
the default). Both built-in targets are assembled from the same injected
components, so an A/B run only differs in whether the Pack constraints are in
play (the plan's fairness constraint).
"""

from __future__ import annotations

import json
import math
import re
import zlib
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from agenticx_oag.context.pack import Claim, LedgerEvidence
from agenticx_oag.context.pipeline import ContextPackPipeline
from agenticx_oag.contracts.stores import (
    EmbeddingProvider,
    LLMProvider,
    VectorStore,
)
from agenticx_oag.eval.metrics import JUDGE_PROMPT_MARKER, split_assertions
from agenticx_oag.generation.oag import OAGGenerator, parse_citations
from agenticx_oag.ontology.model import ObjectType, Ontology
from agenticx_oag.retrieval.ontology_hybrid import OntologyHybridRetriever


class EvalAnswer(BaseModel):
    """One target's answer plus the retrieval context it was based on.

    Beyond the four plan fields, ``evidence_ids`` (legal citation targets)
    and ``evidence_texts`` (faithfulness judge input) let the runner compute
    every metric without knowing target internals.
    """

    text: str
    citations: list[str] = Field(default_factory=list)  # "E1" / "claim:1"
    retrieved_ids: list[str] = Field(default_factory=list)  # retrieved object ids
    claims: list[Claim] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)  # legal citation ids
    evidence_texts: list[str] = Field(default_factory=list)  # judge input


class EvalTarget(Protocol):
    """A system under test; third-party RAG stacks can implement this."""

    name: str

    async def answer(self, question: str) -> EvalAnswer: ...


class OAGTarget:
    """The full OAG chain: ContextPackPipeline + OAGGenerator (P04/P05)."""

    def __init__(
        self,
        name: str,
        llm: LLMProvider,
        ontology: Ontology,
        retriever: OntologyHybridRetriever,
        generator: OAGGenerator | None = None,
    ) -> None:
        self.name = name
        self._pipeline = ContextPackPipeline(llm, ontology, retriever)
        self._generator = generator or OAGGenerator(llm)

    async def answer(self, question: str) -> EvalAnswer:
        pack = await self._pipeline.build_pack(question)
        oag_answer = await self._generator.generate(pack)
        citations = [
            citation.evidence_id
            if citation.evidence_id is not None
            else (citation.claim_id or citation.marker)
            for citation in oag_answer.citations
        ]
        return EvalAnswer(
            text=oag_answer.text,
            citations=citations,
            retrieved_ids=[ref.id for ref in pack.object_refs],
            claims=list(pack.claims),
            evidence_ids=[ev.id for ev in pack.evidence]
            + [claim.claim_id for claim in pack.claims],
            evidence_texts=[ev.text for ev in pack.evidence],
        )


RAG_BASELINE_SYSTEM = (
    "你是基于检索片段的问答助手。规则：\n"
    "1. 只能使用下方检索片段中的信息作答，禁止引入外部知识。\n"
    "2. 每个陈述句后紧跟 [E{n}] 引用标记，编号对应片段编号。\n"
    "3. 片段不足以回答时必须说明证据不足。"
)


class RAGBaselineTarget:
    """Pure vector retrieval + the same LLM, without Pack constraints."""

    def __init__(
        self,
        name: str,
        llm: LLMProvider,
        vectors: VectorStore,
        embedder: EmbeddingProvider,
        *,
        collection: str = "objects",
        top_k: int = 8,
    ) -> None:
        self.name = name
        self._llm = llm
        self._vectors = vectors
        self._embedder = embedder
        self._collection = collection
        self._top_k = top_k

    async def answer(self, question: str) -> EvalAnswer:
        vector = (await self._embedder.embed([question]))[0]
        hits = await self._vectors.search(self._collection, vector, self._top_k)
        chunk_ids = [f"E{index}" for index in range(1, len(hits) + 1)]
        texts = [
            str((hit.get("meta") or {}).get("text", "")) for hit in hits
        ]
        chunks_block = "\n".join(
            f"[{chunk_id}] {text}" for chunk_id, text in zip(chunk_ids, texts)
        )
        prompt = (
            f"检索片段：\n{chunks_block or '（无）'}\n\n"
            f"问题：{question}\n\n"
            "请基于上述片段回答，每个陈述句后用 [E{n}] 标注引用来源。"
        )
        text = await self._llm.complete(prompt, system=RAG_BASELINE_SYSTEM)
        citations = [
            citation.evidence_id
            for citation in parse_citations(text)
            if citation.evidence_id is not None
        ]
        return EvalAnswer(
            text=text,
            citations=citations,
            retrieved_ids=[str(hit.get("id", "")) for hit in hits],
            claims=_claims_from_answer(text),
            evidence_ids=chunk_ids,
            evidence_texts=texts,
        )


def _claims_from_answer(text: str) -> list[Claim]:
    """Project answer assertion sentences onto ledger-shaped Claim models."""
    assertions, _cited = split_assertions(text)
    return [
        Claim(
            claim_id=f"claim:{index}",
            text=sentence,
            entities=["entity:rag-baseline"],
            evidence=[
                LedgerEvidence(
                    source_id="src:rag-baseline",
                    locator="rag-baseline",
                    excerpt=sentence,
                )
            ],
        )
        for index, sentence in enumerate(assertions, start=1)
    ]


# ---------------------------------------------------------------------------
# In-memory mock runtime over a prototype scene JSON (no Docker required).
# ---------------------------------------------------------------------------


def _scene_labels(scene: dict[str, Any]) -> dict[str, str]:
    return {
        str(type_name): str((config or {}).get("label", type_name))
        for type_name, config in (scene.get("types") or {}).items()
    }


def _node_text(node: dict[str, Any], label: str = "") -> str:
    parts = [part for part in (label, str(node.get("name", ""))) if part]
    props = "、".join(
        f"{key}={value}" for key, value in (node.get("props") or {}).items()
    )
    if props:
        parts.append(props)
    return "｜".join(parts)


def _ontology_from_scene(scene: dict[str, Any]) -> Ontology:
    """Minimal ontology for entity linking (object types + display names)."""
    labels = _scene_labels(scene)
    object_types = [
        ObjectType(api_name=type_name, display_name=labels[type_name])
        for type_name in labels
    ]
    scene_id = str(scene.get("id") or "scene")
    return Ontology(
        namespace=f"eval.{scene_id.replace('-', '.')}",
        version="0.1.0",
        object_types=object_types,
    )


class InMemoryGraphStore:
    """Undirected in-memory GraphStore over scene nodes/edges (mock eval)."""

    def __init__(self) -> None:
        self._objects: dict[str, dict[str, Any]] = {}
        self._adjacency: dict[str, list[tuple[str, str]]] = {}

    @classmethod
    def from_scene(cls, scene: dict[str, Any]) -> InMemoryGraphStore:
        store = cls()
        labels = _scene_labels(scene)
        objects = [
            {
                "id": str(node.get("id", "")),
                "object_type": str(node.get("type", "")),
                "text": _node_text(node, labels.get(str(node.get("type", "")), "")),
                "properties": dict(node.get("props") or {}),
            }
            for node in scene.get("nodes") or []
        ]
        links = [
            {
                "link_type": str(edge.get("rel", "")),
                "source_id": str(edge.get("source", "")),
                "target_id": str(edge.get("target", "")),
            }
            for edge in scene.get("edges") or []
        ]
        store._store_objects(objects)
        store._store_links(links)
        return store

    async def upsert_objects(self, objects: list[dict[str, Any]]) -> None:
        self._store_objects(objects)

    async def upsert_links(self, links: list[dict[str, Any]]) -> None:
        self._store_links(links)

    async def get_objects(
        self, object_type: str, ids: list[str] | None = None
    ) -> list[dict[str, Any]]:
        found = [
            dict(obj)
            for obj in self._objects.values()
            if obj["object_type"] == object_type
        ]
        if ids is None:
            return found
        wanted = set(ids)
        return [obj for obj in found if obj["id"] in wanted]

    async def neighbors(
        self,
        object_id: str,
        link_type: str | None = None,
        max_hops: int = 2,
    ) -> list[dict[str, Any]]:
        visited = {object_id}
        frontier = [object_id]
        result: list[dict[str, Any]] = []
        for _hop in range(max_hops):
            next_frontier: list[str] = []
            for node_id in frontier:
                for other, rel in self._adjacency.get(node_id, []):
                    if link_type is not None and rel != link_type:
                        continue
                    if other in visited:
                        continue
                    visited.add(other)
                    next_frontier.append(other)
                    obj = self._objects.get(other)
                    if obj is not None:
                        result.append(dict(obj))
            frontier = next_frontier
            if not frontier:
                break
        return result

    async def query(
        self, cypher: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        return []  # not used by the evaluation

    def _store_objects(self, objects: list[dict[str, Any]]) -> None:
        for obj in objects:
            object_id = str(obj.get("id") or obj.get("object_id") or "")
            if object_id:
                self._objects[object_id] = dict(obj)

    def _store_links(self, links: list[dict[str, Any]]) -> None:
        for link in links:
            source = str(link.get("source_id") or link.get("source") or "")
            target = str(link.get("target_id") or link.get("target") or "")
            link_type = str(link.get("link_type") or link.get("rel") or "")
            if source in self._objects and target in self._objects:
                self._adjacency.setdefault(source, []).append((target, link_type))
                self._adjacency.setdefault(target, []).append((source, link_type))


class InMemoryVectorStore:
    """Cosine-similarity vector store over the scene chunk pool (mock eval)."""

    def __init__(self) -> None:
        self._collections: dict[str, dict[str, tuple[list[float], dict[str, Any]]]] = {}

    async def upsert(
        self,
        collection: str,
        ids: list[str],
        vectors: list[list[float]],
        metas: list[dict[str, Any]],
    ) -> None:
        store = self._collections.setdefault(collection, {})
        for object_id, vector, meta in zip(ids, vectors, metas):
            store[str(object_id)] = (list(vector), dict(meta))

    async def search(
        self,
        collection: str,
        vector: list[float],
        top_k: int,
        filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        store = self._collections.get(collection, {})
        scored = [
            (self._cosine(vector, stored), object_id, meta)
            for object_id, (stored, meta) in store.items()
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [
            {"id": object_id, "score": score, "meta": meta}
            for score, object_id, meta in scored[:top_k]
        ]

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if not norm_a or not norm_b:
            return 0.0
        return dot / (norm_a * norm_b)


class HashingEmbedder:
    """Deterministic char n-gram hashing embedder (mock embedding model)."""

    _DIMENSIONS = 384

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self._DIMENSIONS
        for token in self._tokens(text):
            vector[zlib.crc32(token.encode("utf-8")) % self._DIMENSIONS] = 1.0
        return vector

    @staticmethod
    def _tokens(text: str) -> set[str]:
        compact = "".join(text.split())
        tokens = set(compact)
        tokens.update(compact[i : i + 2] for i in range(len(compact) - 1))
        return tokens


class SceneRuntime:
    """In-memory mock runtime assembled from a prototype scene JSON.

    Both targets share one runtime (same embedder, same chunk pool, same
    graph), matching the plan's fairness constraint.
    """

    def __init__(self, scene: dict[str, Any]) -> None:
        self.scene = scene
        self.graph = InMemoryGraphStore.from_scene(scene)
        self.embedder = HashingEmbedder()
        self.vectors = InMemoryVectorStore()
        self.ontology = _ontology_from_scene(scene)

    @classmethod
    async def load(
        cls, scene: dict[str, Any], *, collection: str = "objects"
    ) -> SceneRuntime:
        runtime = cls(scene)
        labels = _scene_labels(scene)
        nodes = [node for node in scene.get("nodes") or [] if node.get("id")]
        texts = [
            _node_text(node, labels.get(str(node.get("type", "")), ""))
            for node in nodes
        ]
        vectors = await runtime.embedder.embed(texts)
        metas = [
            {
                "object_type": str(node.get("type", "")),
                "text": text,
                "prov": f"scene:{node.get('id', '')}",
            }
            for node, text in zip(nodes, texts)
        ]
        await runtime.vectors.upsert(
            collection, [str(node.get("id", "")) for node in nodes], vectors, metas
        )
        return runtime


# ---------------------------------------------------------------------------
# Prompt-dispatched mock LLM covering every eval stage.
# ---------------------------------------------------------------------------

_EVIDENCE_LINE_RE = re.compile(r"^- (E\d+) \| object=(\S+) \| (.*)$", re.MULTILINE)
_CHUNK_LINE_RE = re.compile(r"^\[(E\d+)\] (.*)$", re.MULTILINE)
_MARKER_STRIP_RE = re.compile(r"\[[EC]\d+\]")
_PUNCT_RE = re.compile(r"[\s，。：；、！？·“”‘’'\"（）()\[\]{}]")


class EvalMockLLM:
    """Deterministic mock LLM dispatched by prompt markers.

    Stages: rewrite -> entity link -> claim generation -> uncertainty ->
    OAG generation (Context Pack) -> RAG generation -> faithfulness judge.
    """

    def __init__(self, scene: dict[str, Any] | None = None) -> None:
        self.scene = scene or {}
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self, prompt: str, *, system: str | None = None, json_mode: bool = False
    ) -> str:
        self.calls.append({"prompt": prompt, "system": system, "json_mode": json_mode})
        if JUDGE_PROMPT_MARKER in prompt:
            return self._judge(prompt)
        if "生成 1~2 个澄清改写" in prompt:
            return "[]"
        if "从问题中识别实体并归类" in prompt:
            return self._link_entities(prompt)
        if "基于且仅基于上述证据生成主张" in prompt:
            return self._generate_claims(prompt)
        if "总结当前研究的不确定性" in prompt:
            return "证据覆盖以检索到的对象与关系为准，低置信结论需人工复核。"
        if "Context Pack（JSON）" in prompt:
            return self._oag_answer(prompt)
        return self._rag_answer(prompt)

    def _link_entities(self, prompt: str) -> str:
        question = ""
        for line in prompt.splitlines():
            if line.startswith("用户问题："):
                question = line[len("用户问题：") :].strip()
        entities: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for node in self.scene.get("nodes") or []:
            name = str(node.get("name", ""))
            object_type = str(node.get("type", ""))
            if name and name in question and (name, object_type) not in seen:
                seen.add((name, object_type))
                entities.append({"name": name, "object_type": object_type})
        for type_name, label in _scene_labels(self.scene).items():
            if label and label in question and (label, type_name) not in seen:
                seen.add((label, type_name))
                entities.append({"name": label, "object_type": type_name})
        return json.dumps(entities[:4], ensure_ascii=False)

    def _generate_claims(self, prompt: str) -> str:
        claims = [
            {"text": text, "evidence_ids": [evidence_id], "confidence": 0.9}
            for evidence_id, _object_id, text in _EVIDENCE_LINE_RE.findall(prompt)[:5]
        ]
        return json.dumps(claims, ensure_ascii=False)

    def _oag_answer(self, prompt: str) -> str:
        pack = self._extract_pack(prompt)
        evidence = pack.get("evidence") or []
        claims = pack.get("claims") or []
        lines = ["针对该问题，根据 Context Pack 中的证据作答："]
        for item in evidence[:3]:
            lines.append(f"{item.get('text', '')}[{item.get('id', '')}]。")
        for index, claim in enumerate(claims[:2], start=1):
            lines.append(f"主张{index}：{claim.get('text', '')}[C{index}]。")
        lines.append(f"综上，共引用 {len(evidence)} 条证据支撑上述结论。")
        return "\n".join(lines)

    def _extract_pack(self, prompt: str) -> dict[str, Any]:
        marker = "Context Pack（JSON）：\n"
        raw = prompt[prompt.find(marker) + len(marker) :] if marker in prompt else prompt
        end = raw.find("\n\n引用图例")
        if end >= 0:
            raw = raw[:end]
        try:
            payload = json.loads(raw)
        except ValueError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _rag_answer(self, prompt: str) -> str:
        chunks = _CHUNK_LINE_RE.findall(prompt)
        lines = [f"{text}[{chunk_id}]。" for chunk_id, text in chunks[:3]]
        lines.append(f"综上，以上内容来自 {len(chunks)} 个检索片段。")
        return "\n".join(lines)

    def _judge(self, prompt: str) -> str:
        claim = _extract_after(prompt, "陈述：")
        evidence_lines: list[str] = []
        collecting = False
        for line in prompt.splitlines():
            if line.startswith("证据："):
                collecting = True
                continue
            if collecting and line.startswith("- "):
                evidence_lines.append(line[2:])
        claim_norm = _normalize(claim)
        entailed = any(
            claim_norm
            and (
                claim_norm in _normalize(evidence)
                or _overlap_ratio(claim_norm, _normalize(evidence)) >= 0.7
            )
            for evidence in evidence_lines
        )
        return json.dumps(
            {"entailed": entailed, "reason": "mock judge heuristic"},
            ensure_ascii=False,
        )


def _extract_after(prompt: str, prefix: str) -> str:
    for line in prompt.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def _normalize(text: str) -> str:
    return _PUNCT_RE.sub("", _MARKER_STRIP_RE.sub("", text))


def _overlap_ratio(claim: str, evidence: str) -> float:
    claim_ngrams = _ngrams(claim)
    if not claim_ngrams:
        return 0.0
    return len(claim_ngrams & _ngrams(evidence)) / len(claim_ngrams)


def _ngrams(text: str) -> set[str]:
    return {text[i : i + 2] for i in range(len(text) - 1)} | set(text)


def load_scene_json(path: str | Path) -> dict[str, Any]:
    """Read a prototype scene JSON file."""
    return json.loads(Path(path).read_text(encoding="utf-8"))
