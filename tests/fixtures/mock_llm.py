"""Deterministic mock LLM / embedder (fixed JSON responses, P04 plan).

``MockLLM`` defaults to the canonical response from the P04 plan and cycles
through a scripted response list (one per ``complete`` call) when given.
``MockEmbedder`` returns preset vectors positionally, cycling if the batch is
longer than the preset list.
"""

from __future__ import annotations

import json
from typing import Any

PLAN_MOCK_RESPONSE = json.dumps(
    {
        "objects": [
            {
                "type": "Customer",
                "id": "C-001",
                "properties": {"name": "张三", "riskLevel": "high"},
                "source_span": "客户张三……",
                "confidence": 0.95,
            },
            {
                "type": "SanctionHit",
                "id": "S-001",
                "properties": {"list": "OFAC", "score": 0.87},
                "source_span": "命中OFAC名单……",
                "confidence": 0.9,
            },
        ],
        "links": [
            {
                "type": "hitsSanction",
                "source_id": "C-001",
                "target_id": "S-001",
                "source_span": "张三命中OFAC",
                "confidence": 0.85,
            }
        ],
    },
    ensure_ascii=False,
)


class MockLLM:
    """LLMProvider fake with a scripted, cycling response list."""

    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = [PLAN_MOCK_RESPONSE] if responses is None else list(responses)
        self.calls: list[dict[str, Any]] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    async def complete(
        self, prompt: str, *, system: str | None = None, json_mode: bool = False
    ) -> str:
        self.calls.append({"prompt": prompt, "system": system, "json_mode": json_mode})
        response = self._responses[(len(self.calls) - 1) % len(self._responses)]
        return response


class MockEmbedder:
    """EmbeddingProvider fake returning preset vectors positionally."""

    def __init__(self, vectors: list[list[float]]) -> None:
        self._vectors = vectors
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [self._vectors[i % len(self._vectors)] for i in range(len(texts))]
