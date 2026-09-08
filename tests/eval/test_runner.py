"""P06 FR-2/FR-3/FR-4: datasets, targets, and the A/B runner."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from agenticx_oag.eval.runner import (
    EvalDataset,
    EvalItem,
    EvalRunner,
    load_dataset,
    load_scene,
)
from agenticx_oag.eval.targets import (
    EvalMockLLM,
    OAGTarget,
    RAGBaselineTarget,
    SceneRuntime,
)
from agenticx_oag.retrieval.ontology_hybrid import OntologyHybridRetriever

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASETS_DIR = REPO_ROOT / "eval" / "datasets"
SCENES_DIR = REPO_ROOT / "prototype" / "scenes"

MIN_ITEMS = {"bank-aml": 30, "supply-chain": 10, "power-grid": 10}
EXPECTED_METRICS = {
    "recall_at_k",
    "citation_correctness",
    "faithfulness",
    "hallucination_rate",
    "keyword_coverage",
}


# --- FR-2: dataset loading + golden id cross-validation ----------------------


@pytest.mark.parametrize("scenario", ["bank-aml", "supply-chain", "power-grid"])
def test_dataset_load_and_golden_ids(scenario: str) -> None:
    dataset = load_dataset(scenario, DATASETS_DIR)
    scene = json.loads((SCENES_DIR / f"{scenario}.json").read_text(encoding="utf-8"))
    node_ids = {str(node["id"]) for node in scene["nodes"]}

    assert dataset.scenario == scenario
    assert dataset.version >= 1
    assert len(dataset.items) >= MIN_ITEMS[scenario]

    item_ids = [item.id for item in dataset.items]
    assert len(item_ids) == len(set(item_ids)), "dataset item ids must be unique"
    for item in dataset.items:
        assert item.question.strip()
        assert item.golden_object_ids
        missing = set(item.golden_object_ids) - node_ids
        assert not missing, f"{item.id}: golden ids not in scene nodes: {missing}"
        assert item.golden_answer_keywords, f"{item.id}: keywords required in seed"


def test_load_dataset_scenario_mismatch(tmp_path: Path) -> None:
    """Loader rejects a dataset whose scenario field differs from the request."""
    # Copy supply-chain.yaml in as bank-aml.yaml: file loads, scenario check fails.
    shutil.copy(DATASETS_DIR / "supply-chain.yaml", tmp_path / "bank-aml.yaml")
    with pytest.raises(ValueError, match="does not match requested"):
        load_dataset("bank-aml", tmp_path)


def test_eval_item_requires_golden_ids() -> None:
    with pytest.raises(ValueError):
        EvalItem(id="qa-x", question="q", golden_object_ids=[])


def test_eval_dataset_requires_items() -> None:
    with pytest.raises(ValueError):
        EvalDataset.model_validate({"scenario": "s", "version": 1, "items": []})


# --- FR-3: targets under the mock runtime ------------------------------------


@pytest.mark.asyncio
async def test_oag_and_rag_targets_return_full_answers() -> None:
    scene = load_scene("bank-aml", SCENES_DIR)
    dataset = load_dataset("bank-aml", DATASETS_DIR)
    llm = EvalMockLLM(scene)
    runtime = await SceneRuntime.load(scene)
    retriever = OntologyHybridRetriever(runtime.graph, runtime.vectors, runtime.embedder)
    oag = OAGTarget("oag", llm, runtime.ontology, retriever)
    rag = RAGBaselineTarget("rag", llm, runtime.vectors, runtime.embedder)
    question = dataset.items[0].question

    oag_answer = await oag.answer(question)
    assert oag_answer.text
    assert oag_answer.citations  # [E{n}] / [C{n}] 引用
    assert oag_answer.retrieved_ids  # 检索到的对象 id
    assert oag_answer.claims  # Pack 主张
    assert oag_answer.evidence_ids and oag_answer.evidence_texts

    rag_answer = await rag.answer(question)
    assert rag_answer.text
    assert rag_answer.citations
    assert rag_answer.retrieved_ids
    assert rag_answer.claims  # 答案断言句投影为 Claim
    assert rag_answer.evidence_ids and rag_answer.evidence_texts


# --- FR-4: A/B runner ---------------------------------------------------------


@pytest.mark.asyncio
async def test_ab_run_mock_full_chain() -> None:
    scene = load_scene("bank-aml", SCENES_DIR)
    dataset = load_dataset("bank-aml", DATASETS_DIR)
    llm = EvalMockLLM(scene)
    runtime = await SceneRuntime.load(scene)
    retriever = OntologyHybridRetriever(runtime.graph, runtime.vectors, runtime.embedder)
    targets = [
        OAGTarget("oag", llm, runtime.ontology, retriever),
        RAGBaselineTarget("rag", llm, runtime.vectors, runtime.embedder),
    ]
    runner = EvalRunner(judge=EvalMockLLM(scene))

    result = await runner.run("bank-aml", targets, limit=5, dataset=dataset)

    assert result.scenario == "bank-aml"
    assert result.dataset_version == dataset.version
    assert len(result.items) == 10  # 5 QA x 2 targets
    assert {item.target for item in result.items} == {"oag", "rag"}
    for item in result.items:
        assert set(item.metrics) == EXPECTED_METRICS
        for value in item.metrics.values():
            assert 0.0 <= value <= 1.0
    assert result.failures == []

    assert set(result.summaries) == {"oag", "rag"}
    for metrics in result.summaries.values():
        assert EXPECTED_METRICS <= set(metrics)
        assert all(summary.n == 5 for summary in metrics.values())


@pytest.mark.asyncio
async def test_runner_limit_and_full_dataset() -> None:
    scene = load_scene("power-grid", SCENES_DIR)
    dataset = load_dataset("power-grid", DATASETS_DIR)
    llm = EvalMockLLM(scene)
    runtime = await SceneRuntime.load(scene)
    retriever = OntologyHybridRetriever(runtime.graph, runtime.vectors, runtime.embedder)
    targets = [OAGTarget("oag", llm, runtime.ontology, retriever)]
    runner = EvalRunner(judge=EvalMockLLM(scene))

    limited = await runner.run("power-grid", targets, 3, dataset=dataset)
    assert len(limited.items) == 3
    full = await runner.run("power-grid", targets, None, dataset=dataset)
    assert len(full.items) == len(dataset.items)


class FailingTarget:
    name = "boom"

    async def answer(self, question: str):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_failures_recorded_without_interrupt() -> None:
    scene = load_scene("bank-aml", SCENES_DIR)
    dataset = load_dataset("bank-aml", DATASETS_DIR)
    llm = EvalMockLLM(scene)
    runtime = await SceneRuntime.load(scene)
    retriever = OntologyHybridRetriever(runtime.graph, runtime.vectors, runtime.embedder)
    targets = [
        OAGTarget("oag", llm, runtime.ontology, retriever),
        FailingTarget(),
    ]
    runner = EvalRunner(judge=EvalMockLLM(scene))

    result = await runner.run("bank-aml", targets, limit=3, dataset=dataset)

    assert len(result.failures) == 3
    assert {failure.target for failure in result.failures} == {"boom"}
    assert all("RuntimeError" in failure.error for failure in result.failures)
    assert {failure.item_id for failure in result.failures} == {
        item.id for item in dataset.items[:3]
    }
    # 正常 target 的结果不受失败项影响
    assert len([item for item in result.items if item.target == "oag"]) == 3
    assert set(result.summaries) == {"oag"}
