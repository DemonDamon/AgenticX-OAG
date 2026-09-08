"""Ontology-typed entity linking (P05 FR-1)."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel

from agenticx_oag.contracts.stores import LLMProvider
from agenticx_oag.ontology.model import Ontology

_MAX_PROPERTIES_PER_TYPE = 8

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")


class LinkedEntity(BaseModel):
    """An entity from the question classified to an ObjectType."""

    name: str  # surface form in the question
    object_type: str  # ObjectType.api_name


def parse_json_payload(raw: str) -> Any:
    """Parse an LLM JSON reply, tolerating markdown code fences.

    Returns ``None`` when the reply is not valid JSON.
    """
    stripped = _FENCE_RE.sub("", raw.strip())
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except ValueError:
        return None


class EntityLinker:
    """Links question entities to ontology object types via an LLM.

    Entities the LLM cannot classify into a known ObjectType are dropped
    (no guessing); an unusable reply yields an empty list.
    """

    def __init__(self, llm: LLMProvider, ontology: Ontology) -> None:
        self._llm = llm
        self._ontology = ontology
        self._known_types = {obj.api_name for obj in ontology.object_types}

    def build_prompt(self, question: str) -> str:
        lines = ["可用对象类型（api_name / 显示名 / 关键属性）："]
        for obj in self._ontology.object_types:
            props = ", ".join(prop.api_name for prop in obj.properties[:_MAX_PROPERTIES_PER_TYPE])
            lines.append(f"- {obj.api_name}（{obj.display_name}）: {props or '无'}")
        lines += [
            "",
            f"用户问题：{question}",
            "",
            "从问题中识别实体并归类。规则：",
            '1. 只输出 JSON 数组，每项形如 {"name": "实体原文", "object_type": "api_name"}。',
            "2. 只能归类到上面列出的对象类型；无法归类的实体直接忽略，禁止猜测。",
            "3. 问题中没有可识别实体时输出 []。",
        ]
        return "\n".join(lines)

    async def link(self, question: str) -> list[LinkedEntity]:
        prompt = self.build_prompt(question)
        raw = await self._llm.complete(prompt, json_mode=True)
        payload = parse_json_payload(raw)
        if not isinstance(payload, list):
            return []
        linked: list[LinkedEntity] = []
        seen: set[tuple[str, str]] = set()
        for item in payload:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            object_type = str(item.get("object_type", "")).strip()
            if not name or object_type not in self._known_types:
                continue  # unclassifiable entity: drop instead of guessing
            key = (name, object_type)
            if key in seen:
                continue
            seen.add(key)
            linked.append(LinkedEntity(name=name, object_type=object_type))
        return linked
