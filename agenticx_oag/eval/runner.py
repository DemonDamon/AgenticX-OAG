"""A/B eval runner (P06 FR-4) plus dataset / scene loaders.

``EvalRunner.run`` executes every (QA, target) pair with bounded concurrency
(5 QAs in flight), computes the four metrics plus keyword coverage per item,
records failures without interrupting the run, and aggregates via
:func:`agenticx_oag.eval.metrics.aggregate`.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from agenticx_oag.contracts.stores import LLMProvider
from agenticx_oag.eval.metrics import (
    MetricSummary,
    aggregate,
    citation_correctness,
    hallucination_rate,
    judge_claims,
    keyword_coverage,
    recall_at_k,
    split_assertions,
)
from agenticx_oag.eval.targets import EvalAnswer, EvalTarget, load_scene_json

DEFAULT_CONCURRENCY = 5
DEFAULT_RECALL_K = 8


class EvalItem(BaseModel):
    """One QA of an eval dataset (golden ids reference scene node ids)."""

    id: str
    question: str
    golden_object_ids: list[str] = Field(min_length=1)
    golden_answer_keywords: list[str] = Field(default_factory=list)


class EvalDataset(BaseModel):
    """Parsed ``eval/datasets/<scenario>.yaml``."""

    scenario: str
    version: int = 1
    items: list[EvalItem] = Field(min_length=1)


class ItemResult(BaseModel):
    """Per-item metrics for one target."""

    item_id: str
    target: str
    metrics: dict[str, float]
    judge_failures: int = 0


class FailureRecord(BaseModel):
    """A target failure on one item; the run continues."""

    item_id: str
    target: str
    error: str


class EvalResult(BaseModel):
    """Full outcome of one A/B run."""

    scenario: str
    dataset_version: int
    items: list[ItemResult] = Field(default_factory=list)
    failures: list[FailureRecord] = Field(default_factory=list)
    summaries: dict[str, dict[str, MetricSummary]] = Field(default_factory=dict)


def repo_root() -> Path:
    """Locate the repository root (env override, else walk up from CWD)."""
    override = os.environ.get("AGENTICX_OAG_ROOT")
    if override:
        return Path(override)
    cwd = Path.cwd()
    for candidate in (cwd, *cwd.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "agenticx_oag").is_dir():
            return candidate
    return cwd


def load_dataset(
    scenario: str, datasets_dir: str | Path | None = None
) -> EvalDataset:
    """Load ``eval/datasets/<scenario>.yaml``."""
    directory = Path(datasets_dir) if datasets_dir is not None else repo_root() / "eval" / "datasets"
    path = directory / f"{scenario}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    dataset = EvalDataset.model_validate(data)
    if dataset.scenario != scenario:
        raise ValueError(
            f"dataset scenario {dataset.scenario!r} does not match requested {scenario!r}"
        )
    return dataset


def load_scene(scenario: str, scenes_dir: str | Path | None = None) -> dict[str, Any]:
    """Load ``prototype/scenes/<scenario>.json``."""
    directory = Path(scenes_dir) if scenes_dir is not None else repo_root() / "prototype" / "scenes"
    path = directory / f"{scenario}.json"
    scene = load_scene_json(path)
    if str(scene.get("id", "")) != scenario:
        raise ValueError(
            f"scene id {scene.get('id')!r} does not match requested {scenario!r}"
        )
    return scene


class EvalRunner:
    """Runs every target against a dataset and computes all metrics."""

    def __init__(
        self, judge: LLMProvider, *, recall_k: int = DEFAULT_RECALL_K,
        concurrency: int = DEFAULT_CONCURRENCY,
    ) -> None:
        self._judge = judge
        self._recall_k = recall_k
        self._concurrency = concurrency

    async def run(
        self,
        scenario: str,
        targets: list[EvalTarget],
        limit: int | None = None,
        *,
        dataset: EvalDataset | None = None,
        datasets_dir: str | Path | None = None,
    ) -> EvalResult:
        """Evaluate all targets over the scenario's dataset (limit optional)."""
        if dataset is None:
            dataset = load_dataset(scenario, datasets_dir)
        items = dataset.items if limit is None else dataset.items[:limit]
        semaphore = asyncio.Semaphore(self._concurrency)
        outcomes = await asyncio.gather(
            *(self._run_item(item, targets, semaphore) for item in items)
        )
        item_results = [result for pair in outcomes for result in pair[0]]
        failures = [failure for pair in outcomes for failure in pair[1]]
        return EvalResult(
            scenario=scenario,
            dataset_version=dataset.version,
            items=item_results,
            failures=failures,
            summaries=self._summarize(item_results),
        )

    async def _run_item(
        self,
        item: EvalItem,
        targets: list[EvalTarget],
        semaphore: asyncio.Semaphore,
    ) -> tuple[list[ItemResult], list[FailureRecord]]:
        async with semaphore:
            results: list[ItemResult] = []
            failures: list[FailureRecord] = []
            for target in targets:
                try:
                    answer = await target.answer(item.question)
                except Exception as error:  # noqa: BLE001 -- failure is recorded
                    failures.append(
                        FailureRecord(
                            item_id=item.id,
                            target=target.name,
                            error=f"{type(error).__name__}: {error}",
                        )
                    )
                    continue
                results.append(await self._metrics(item, target.name, answer))
            return results, failures

    async def _metrics(
        self, item: EvalItem, target_name: str, answer: EvalAnswer
    ) -> ItemResult:
        assertions, cited = split_assertions(answer.text)
        faith = await judge_claims(answer.claims, answer.evidence_texts, self._judge)
        metrics = {
            "recall_at_k": recall_at_k(
                answer.retrieved_ids, item.golden_object_ids, self._recall_k
            ),
            "citation_correctness": citation_correctness(
                answer.citations, answer.evidence_ids
            ),
            "faithfulness": faith.value,
            "hallucination_rate": hallucination_rate(assertions, cited),
        }
        if item.golden_answer_keywords:
            metrics["keyword_coverage"] = keyword_coverage(
                answer.text, item.golden_answer_keywords
            )
        return ItemResult(
            item_id=item.id,
            target=target_name,
            metrics=metrics,
            judge_failures=faith.judge_failures,
        )

    @staticmethod
    def _summarize(items: list[ItemResult]) -> dict[str, dict[str, MetricSummary]]:
        values: dict[str, dict[str, list[float]]] = {}
        for item in items:
            per_target = values.setdefault(item.target, {})
            for metric, value in item.metrics.items():
                per_target.setdefault(metric, []).append(value)
        return {
            target: aggregate(per_metric) for target, per_metric in values.items()
        }


__all__ = [
    "DEFAULT_CONCURRENCY",
    "DEFAULT_RECALL_K",
    "EvalDataset",
    "EvalItem",
    "EvalResult",
    "EvalRunner",
    "FailureRecord",
    "ItemResult",
    "load_dataset",
    "load_scene",
    "repo_root",
]
