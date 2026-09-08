"""P06 FR-5: report rendering (comparison matrix + meta + HTML integrity)."""

from __future__ import annotations

import pytest

from agenticx_oag.eval.metrics import MetricSummary, summarize
from agenticx_oag.eval.report import (
    EvalMeta,
    compare_metrics,
    matrix_rows,
    render_report,
)
from agenticx_oag.eval.runner import (
    EvalResult,
    FailureRecord,
    ItemResult,
)

REPRODUCE = "agenticx-oag eval --scenario bank-aml --targets oag,rag --limit 5 --mock-llm --out reports/poc/"


def _result() -> EvalResult:
    items = [
        ItemResult(
            item_id="qa-001",
            target="oag",
            metrics={
                "recall_at_k": 1.0,
                "citation_correctness": 1.0,
                "faithfulness": 1.0,
                "hallucination_rate": 0.0,
                "keyword_coverage": 1.0,
            },
        ),
        ItemResult(
            item_id="qa-002",
            target="oag",
            metrics={
                "recall_at_k": 0.5,
                "citation_correctness": 0.5,
                "faithfulness": 0.5,
                "hallucination_rate": 0.5,
                "keyword_coverage": 0.5,
            },
        ),
        ItemResult(
            item_id="qa-001",
            target="rag",
            metrics={
                "recall_at_k": 0.5,
                "citation_correctness": 0.5,
                "faithfulness": 0.5,
                "hallucination_rate": 0.5,
                "keyword_coverage": 0.5,
            },
        ),
        ItemResult(
            item_id="qa-002",
            target="rag",
            metrics={
                "recall_at_k": 0.0,
                "citation_correctness": 0.0,
                "faithfulness": 0.0,
                "hallucination_rate": 1.0,
                "keyword_coverage": 0.0,
            },
        ),
    ]
    summaries = {
        target: {
            metric: summarize([item.metrics[metric] for item in items
                               if item.target == target])
            for metric in items[0].metrics
        }
        for target in ("oag", "rag")
    }
    return EvalResult(
        scenario="bank-aml",
        dataset_version=1,
        items=items,
        failures=[
            FailureRecord(item_id="qa-003", target="rag", error="RuntimeError: boom")
        ],
        summaries=summaries,
    )


def _meta() -> EvalMeta:
    return EvalMeta(
        scenario="bank-aml",
        dataset_version=1,
        targets={
            "oag": "OAG 全链（Pack 约束生成）",
            "rag": "RAG baseline（纯向量检索 + 直接生成）",
        },
        llm="mock:EvalMockLLM",
        ran_at="2026-09-08T12:00:00+08:00",
        git_sha="abc1234",
        fairness_note="同一 LLM、同一嵌入模型、同一 chunk 池。",
        reproduce_command=REPRODUCE,
    )


def test_render_report_structure_and_meta() -> None:
    markdown, html = render_report(_result(), _meta())
    assert markdown and html

    # 元信息（可复现字段）齐全
    for field_value in (
        "bank-aml",
        "v1",
        "mock:EvalMockLLM",
        "2026-09-08T12:00:00+08:00",
        "abc1234",
        REPRODUCE,
    ):
        assert field_value in markdown
        assert field_value in html

    # 报告结构：对比总表 -> win/lose -> 失败项 -> 复现命令
    assert "指标对比总表" in markdown
    assert "win/lose" in markdown
    assert "失败项" in markdown
    assert "复现命令" in markdown
    assert "<table" in html and "<h2" in html

    # 总表包含两列 target 与全部指标行
    for target in ("oag", "rag"):
        assert f"| {target} " in markdown or target in markdown
    assert "Recall@k" in markdown
    assert "Faithfulness" in markdown
    assert "Hallucination" in markdown

    # 表格行必须各自成行（trim_blocks 不得吞掉行尾换行）
    assert "\n| Recall@k" in markdown
    assert "\n| Faithfulness" in markdown
    assert "\n| Hallucination" in markdown
    assert "\n| --- " in markdown

    # 失败项可见
    assert "qa-003" in markdown
    assert "RuntimeError: boom" in markdown
    assert "qa-003" in html


def test_html_has_no_template_residue() -> None:
    _markdown, html = render_report(_result(), _meta())
    assert "{{" not in html
    assert "{%" not in html
    assert "{#" not in html
    assert "jinja" not in html.lower()


def test_compare_metrics_directions_and_winners() -> None:
    comparisons = compare_metrics(_result())
    by_metric = {comparison.metric: comparison for comparison in comparisons}
    assert set(by_metric) == {
        "recall_at_k",
        "citation_correctness",
        "faithfulness",
        "hallucination_rate",
        "keyword_coverage",
    }
    assert by_metric["recall_at_k"].direction == "higher"
    assert by_metric["recall_at_k"].winner == "oag"
    assert by_metric["recall_at_k"].delta == pytest.approx(0.5)
    # 幻觉率越低越好
    assert by_metric["hallucination_rate"].direction == "lower"
    assert by_metric["hallucination_rate"].winner == "oag"
    assert by_metric["hallucination_rate"].delta == pytest.approx(-0.5)


def test_matrix_rows_cover_all_metrics() -> None:
    rows = matrix_rows(_result())
    assert [row.metric for row in rows] == [
        "recall_at_k",
        "citation_correctness",
        "faithfulness",
        "hallucination_rate",
        "keyword_coverage",
    ]
    row = rows[0]
    assert isinstance(row.cells["oag"], MetricSummary)
    assert row.cells["oag"].n == 2
    assert row.cells["rag"].mean == pytest.approx(0.25)


def test_compare_metrics_single_target_empty() -> None:
    single = EvalResult(
        scenario="s",
        dataset_version=1,
        items=[
            ItemResult(item_id="qa-1", target="oag", metrics={"recall_at_k": 1.0})
        ],
        summaries={"oag": {"recall_at_k": summarize([1.0])}},
    )
    assert compare_metrics(single) == []
    assert len(matrix_rows(single)) == 1
    assert set(matrix_rows(single)[0].cells) == {"oag"}
