"""FR-1: EntityLinker (mock LLM; unclassifiable entities are never guessed)."""

from __future__ import annotations

import pytest

from agenticx_oag.ontology.model import ObjectType, Ontology, PropertyType
from agenticx_oag.retrieval import EntityLinker


class FakeLLM:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[str] = []

    async def complete(
        self, prompt: str, *, system: str | None = None, json_mode: bool = False
    ) -> str:
        self.calls.append(prompt)
        return self.reply


@pytest.fixture()
def ontology() -> Ontology:
    return Ontology(
        namespace="test.aml",
        version="0.1.0",
        object_types=[
            ObjectType(
                api_name="Customer",
                display_name="客户",
                properties=[
                    PropertyType(api_name="name", display_name="名称", required=True),
                    PropertyType(api_name="riskLevel", display_name="风险等级"),
                ],
            ),
            ObjectType(
                api_name="Transaction",
                display_name="交易",
                properties=[PropertyType(api_name="amount", display_name="金额")],
            ),
        ],
    )


@pytest.mark.asyncio
async def test_link_classifies_into_known_types(ontology: Ontology) -> None:
    llm = FakeLLM(
        '[{"name": "张三", "object_type": "Customer"}, '
        '{"name": "转账", "object_type": "Transaction"}]'
    )
    linked = await EntityLinker(llm, ontology).link("张三最近有哪些转账？")
    assert [(entity.name, entity.object_type) for entity in linked] == [
        ("张三", "Customer"),
        ("转账", "Transaction"),
    ]


@pytest.mark.asyncio
async def test_link_prompt_injects_all_types_and_key_properties(
    ontology: Ontology,
) -> None:
    llm = FakeLLM("[]")
    await EntityLinker(llm, ontology).link("张三")
    prompt = llm.calls[0]
    assert "Customer" in prompt
    assert "Transaction" in prompt
    assert "riskLevel" in prompt and "amount" in prompt
    assert "张三" in prompt


@pytest.mark.asyncio
async def test_link_drops_entities_with_unknown_type(ontology: Ontology) -> None:
    llm = FakeLLM(
        '[{"name": "张三", "object_type": "Customer"}, '
        '{"name": "火星", "object_type": "Planet"}]'
    )
    linked = await EntityLinker(llm, ontology).link("张三住在火星")
    assert [(entity.name, entity.object_type) for entity in linked] == [
        ("张三", "Customer")
    ]


@pytest.mark.asyncio
async def test_link_returns_empty_when_nothing_classifiable(
    ontology: Ontology,
) -> None:
    llm = FakeLLM("[]")
    assert await EntityLinker(llm, ontology).link("今天天气如何") == []


@pytest.mark.asyncio
async def test_link_garbage_reply_returns_empty(ontology: Ontology) -> None:
    llm = FakeLLM("抱歉，这不是 JSON")
    assert await EntityLinker(llm, ontology).link("任意问题") == []


@pytest.mark.asyncio
async def test_link_tolerates_fenced_json(ontology: Ontology) -> None:
    llm = FakeLLM('```json\n[{"name": "李四", "object_type": "Customer"}]\n```')
    linked = await EntityLinker(llm, ontology).link("李四")
    assert [(entity.name, entity.object_type) for entity in linked] == [
        ("李四", "Customer")
    ]
