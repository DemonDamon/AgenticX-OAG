"""Prompt construction for ontology-guided extraction (FR-3)."""

from __future__ import annotations

import json
from typing import Any

from agenticx_oag.ontology.model import Ontology

SYSTEM_TEMPLATE = """你是一个本体引导的知识图谱抽取器。本体 schema（JSON）：
{schema}

规则：
1. 只能输出上述 object_types / link_types 中已定义的类型（api_name 精确匹配）。
2. 属性名必须与 schema 中定义的属性名精确匹配，不得自造属性名。
3. 无法归类到已定义类型的内容直接丢弃，不要输出。
4. 每个输出条目必须带 source_span（chunk 内原文片段）与 confidence（0-1 浮点数）。
5. 只输出 JSON，不要任何解释文字。输出 schema：
{{"objects": [{{"type": "...", "id": "...", "properties": {{...}}, "source_span": "...", "confidence": 0.9}}], "links": [{{"type": "...", "source_id": "...", "target_id": "...", "source_span": "...", "confidence": 0.8}}]}}"""


def ontology_schema(ontology: Ontology) -> dict[str, Any]:
    """A compact JSON-serializable view of the ontology for prompt injection."""
    return {
        "object_types": [
            {
                "api_name": ot.api_name,
                "properties": [p.api_name for p in ot.properties],
                "property_enums": {
                    p.api_name: p.enum_values for p in ot.properties if p.enum_values
                },
                "primary_key": ot.primary_key,
            }
            for ot in ontology.object_types
        ],
        "link_types": [
            {
                "api_name": lt.api_name,
                "source_type": lt.source_type,
                "target_type": lt.target_type,
            }
            for lt in ontology.link_types
        ],
    }


def build_system_prompt(ontology: Ontology) -> str:
    schema_json = json.dumps(ontology_schema(ontology), ensure_ascii=False)
    return SYSTEM_TEMPLATE.format(schema=schema_json)
