"""FR-3 AC: ontology-guided extraction with defensive parsing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fixtures.mock_llm import PLAN_MOCK_RESPONSE, MockLLM

from agenticx_oag.extract.guided_extractor import GuidedExtractor
from agenticx_oag.ontology.io import load_ontology

REPO_ROOT = Path(__file__).resolve().parents[2]
AML_ONTOLOGY = REPO_ROOT / "templates" / "finance" / "aml" / "ontology.yaml"


@pytest.fixture()
def ontology():
    return load_ontology(AML_ONTOLOGY)


@pytest.mark.asyncio
async def test_plan_mock_response_converts(ontology) -> None:
    llm = MockLLM()
    extractor = GuidedExtractor(llm, ontology)

    objects, links = await extractor.extract(["客户张三……命中OFAC名单……"])

    assert len(objects) == 2
    customer, sanction = objects
    assert customer.object_type == "Customer"
    assert customer.id == "C-001"
    assert customer.properties == {"name": "张三", "riskLevel": "high"}
    assert customer.prov.span == "客户张三……"
    assert customer.prov.confidence == 0.95
    assert customer.prov.extracted_at != ""
    assert sanction.object_type == "SanctionHit"
    assert sanction.id == "S-001"

    assert len(links) == 1
    link = links[0]
    assert link.link_type == "hitsSanction"
    assert (link.source_id, link.target_id) == ("C-001", "S-001")
    assert link.prov.confidence == 0.85

    # json mode requested and ontology schema injected into the system prompt
    assert llm.calls[0]["json_mode"] is True
    assert "Customer" in llm.calls[0]["system"]
    assert "hitsSanction" in llm.calls[0]["system"]
    assert "riskLevel" in llm.calls[0]["system"]
    assert "客户张三……命中OFAC名单……" == llm.calls[0]["prompt"]
    assert extractor.warning_count == 0


@pytest.mark.asyncio
async def test_undefined_types_dropped_with_warning(ontology) -> None:
    response = json.dumps(
        {
            "objects": [
                {"type": "Customer", "id": "C-001", "properties": {"name": "张三"},
                 "source_span": "客户张三", "confidence": 0.9},
                {"type": "Foo", "id": "F-001", "properties": {}, "source_span": "…",
                 "confidence": 0.5},
                {"type": "Customer", "properties": {"name": "无ID"}, "source_span": "…",
                 "confidence": 0.5},
            ],
            "links": [
                {"type": "notALink", "source_id": "C-001", "target_id": "C-002",
                 "source_span": "…", "confidence": 0.5},
                {"type": "owns", "source_id": "C-001", "target_id": "",
                 "source_span": "…", "confidence": 0.5},
            ],
        },
        ensure_ascii=False,
    )
    extractor = GuidedExtractor(MockLLM([response]), ontology)

    objects, links = await extractor.extract(["chunk"])

    # legal entries all converted; undefined types / bad ids dropped
    assert [o.id for o in objects] == ["C-001"]
    assert links == []
    # Foo object + notALink link + id-less Customer + empty target link
    assert extractor.warning_count == 4


@pytest.mark.asyncio
async def test_json_failure_retries_once_then_skips(ontology) -> None:
    llm = MockLLM(["这不是 JSON"])
    extractor = GuidedExtractor(llm, ontology)

    objects, links = await extractor.extract(["chunk-1", "chunk-2"])

    assert objects == [] and links == []
    # one warning per failed attempt: 2 attempts x 2 chunks
    assert extractor.warning_count == 4
    assert llm.call_count == 4


@pytest.mark.asyncio
async def test_json_failure_retry_recovers(ontology) -> None:
    llm = MockLLM(["oops not json", PLAN_MOCK_RESPONSE])
    extractor = GuidedExtractor(llm, ontology)

    objects, links = await extractor.extract(["chunk"])

    assert len(objects) == 2
    assert len(links) == 1
    assert extractor.warning_count == 1
    assert llm.call_count == 2


@pytest.mark.asyncio
async def test_code_fenced_json_accepted(ontology) -> None:
    fenced = f"```json\n{PLAN_MOCK_RESPONSE}\n```"
    extractor = GuidedExtractor(MockLLM([fenced]), ontology)

    objects, _links = await extractor.extract(["chunk"])

    assert [o.id for o in objects] == ["C-001", "S-001"]


@pytest.mark.asyncio
async def test_system_prompt_injects_enum_domain(ontology) -> None:
    extractor = GuidedExtractor(MockLLM(), ontology)
    system = extractor.system_prompt
    for enum_value in ("low", "medium", "high"):
        assert enum_value in system
    assert "primary_key" in system
    assert "finance.aml" not in system  # only schema content, not namespace noise
