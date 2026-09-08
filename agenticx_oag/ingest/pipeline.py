"""End-to-end ingest pipeline (FR-5/FR-6).

read -> sliding-window chunks (10% overlap) -> per-chunk extraction ->
two-level disambiguation -> link redirection over the alias map -> upsert.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from agenticx_oag.contracts.stores import EmbeddingProvider, GraphStore, LLMProvider
from agenticx_oag.extract.guided_extractor import GuidedExtractor
from agenticx_oag.graph.records import LinkRecord, ObjectRecord
from agenticx_oag.graph.resolve import EntityResolver
from agenticx_oag.ontology.io import load_ontology

logger = logging.getLogger(__name__)

_TEXT_SUFFIXES = {".md", ".txt", ".json"}


@dataclass
class IngestReport:
    """Run counters asserted by the pipeline tests (FR-6 AC)."""

    docs: int
    chunks: int
    extracted_objects: int
    extracted_links: int
    merged: int
    dropped: int


class IngestPipeline:
    async def run(
        self,
        docs: list[Path],
        ontology_path: Path,
        store: GraphStore,
        llm: LLMProvider,
        embedder: EmbeddingProvider | None = None,
        chunk_size: int = 1200,
    ) -> IngestReport:
        ontology = load_ontology(ontology_path)
        extractor = GuidedExtractor(llm, ontology)
        resolver = EntityResolver(embedder)

        objects: list[ObjectRecord] = []
        links: list[LinkRecord] = []
        chunks_total = 0
        docs_ok = 0
        for doc in docs:
            if doc.suffix.lower() not in _TEXT_SUFFIXES:
                logger.warning("skipping unsupported doc %s", doc)
                continue
            text = doc.read_text(encoding="utf-8")
            chunks = _sliding_chunks(text, chunk_size)
            chunks_total += len(chunks)
            doc_objects, doc_links = await extractor.extract(chunks)
            for obj in doc_objects:
                if not obj.prov.source_doc:
                    obj.prov.source_doc = doc.name
            objects.extend(doc_objects)
            links.extend(doc_links)
            docs_ok += 1

        resolved, alias_map = await resolver.resolve(objects)

        # FR-5: redirect link endpoints, then drop links left dangling.
        known_ids = {record.id for record in resolved}
        final_links: list[LinkRecord] = []
        dropped = extractor.warning_count
        for link in links:
            link.source_id = alias_map.get(link.source_id, link.source_id)
            link.target_id = alias_map.get(link.target_id, link.target_id)
            if link.source_id in known_ids and link.target_id in known_ids:
                final_links.append(link)
            else:
                dropped += 1
                logger.warning("dropping dangling link %s", link)

        await store.upsert_objects([record.to_dict() for record in resolved])
        await store.upsert_links([link.to_dict() for link in final_links])

        return IngestReport(
            docs=docs_ok,
            chunks=chunks_total,
            extracted_objects=len(objects),
            extracted_links=len(links),
            merged=len(objects) - len(resolved),
            dropped=dropped,
        )


def _sliding_chunks(text: str, chunk_size: int) -> list[str]:
    """Character-level sliding window with 10% overlap."""
    if not text.strip():
        return []
    if len(text) <= chunk_size:
        return [text]
    overlap = max(1, chunk_size // 10)
    step = chunk_size - overlap
    return [text[i : i + chunk_size] for i in range(0, len(text) - overlap, step)]
