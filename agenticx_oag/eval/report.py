"""Report rendering (P06 FR-5): Markdown + HTML from one EvalResult.

Structure: meta / reproducibility -> metric comparison matrix -> per-metric
win/lose -> failures -> reproduce command. Jinja2 templates live in
``agenticx_oag/eval/templates``.
"""

from __future__ import annotations

from typing import Any

from jinja2 import Environment, PackageLoader
from pydantic import BaseModel

from agenticx_oag.eval.metrics import MetricSummary
from agenticx_oag.eval.runner import EvalResult

METRIC_ORDER = (
    "recall_at_k",
    "citation_correctness",
    "faithfulness",
    "hallucination_rate",
    "keyword_coverage",
)

METRIC_LABELS: dict[str, str] = {
    "recall_at_k": "Recall@k 检索召回率",
    "citation_correctness": "Citation 正确率",
    "faithfulness": "Faithfulness 忠实度",
    "hallucination_rate": "Hallucination 幻觉率",
    "keyword_coverage": "关键词覆盖率",
}

_HIGHER_IS_BETTER = {
    "recall_at_k",
    "citation_correctness",
    "faithfulness",
    "keyword_coverage",
}


class EvalMeta(BaseModel):
    """Reproducibility metadata for one report."""

    scenario: str
    dataset_version: int
    targets: dict[str, str]  # name -> config summary
    llm: str
    ran_at: str
    git_sha: str
    fairness_note: str = ""
    reproduce_command: str = ""


class MetricComparison(BaseModel):
    """Win/lose verdict for one metric across targets."""

    metric: str
    direction: str  # "higher" | "lower"
    values: dict[str, float]
    winner: str
    delta: float


class MetricRow(BaseModel):
    """One row of the comparison matrix (metric -> per-target summary)."""

    metric: str
    label: str
    cells: dict[str, MetricSummary | None]


def compare_metrics(result: EvalResult) -> list[MetricComparison]:
    """Pairwise-free winner detection: best target per metric (delta to 2nd)."""
    comparisons: list[MetricComparison] = []
    for metric in METRIC_ORDER:
        values = {
            target: summary[metric].mean
            for target, summary in result.summaries.items()
            if metric in summary
        }
        if len(values) < 2:
            continue
        higher = metric in _HIGHER_IS_BETTER
        ordered = sorted(values.items(), key=lambda pair: pair[1], reverse=higher)
        winner, best = ordered[0]
        delta = best - ordered[1][1]
        comparisons.append(
            MetricComparison(
                metric=metric,
                direction="higher" if higher else "lower",
                values=values,
                winner=winner,
                delta=delta,
            )
        )
    return comparisons


def matrix_rows(result: EvalResult) -> list[MetricRow]:
    """Comparison matrix rows in METRIC_ORDER, present metrics only."""
    rows: list[MetricRow] = []
    for metric in METRIC_ORDER:
        cells = {
            target: summary.get(metric)
            for target, summary in result.summaries.items()
        }
        if any(cell is not None for cell in cells.values()):
            rows.append(
                MetricRow(
                    metric=metric,
                    label=METRIC_LABELS.get(metric, metric),
                    cells=cells,
                )
            )
    return rows


def render_report(result: EvalResult, meta: EvalMeta) -> tuple[str, str]:
    """Render the same content as (markdown, html)."""
    context: dict[str, Any] = {
        "result": result,
        "meta": meta,
        "comparisons": compare_metrics(result),
        "rows": matrix_rows(result),
        "labels": METRIC_LABELS,
        "higher_is_better": _HIGHER_IS_BETTER,
        "failure_count": len(result.failures),
        "item_count": len(result.items),
    }
    markdown = _environment(autoescape=False).get_template("report.md.j2").render(
        **context
    )
    html = _environment(autoescape=True).get_template("report.html.j2").render(
        **context
    )
    return markdown, html


def _environment(*, autoescape: bool) -> Environment:
    return Environment(
        loader=PackageLoader("agenticx_oag.eval", "templates"),
        autoescape=autoescape,
        trim_blocks=True,
        lstrip_blocks=True,
    )
