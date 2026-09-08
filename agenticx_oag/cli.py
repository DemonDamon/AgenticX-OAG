"""AgenticX-OAG CLI (P06 FR-6), argparse only (no click).

``agenticx-oag eval --scenario bank-aml --targets oag,rag --limit 30
--out reports/poc/ [--mock-llm]`` runs the A/B evaluation and writes a
Markdown + HTML report pair.
"""

from __future__ import annotations

import argparse
import asyncio
import shlex
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agenticx_oag.eval.report import EvalMeta, render_report
from agenticx_oag.eval.runner import EvalRunner, load_dataset, load_scene
from agenticx_oag.eval.targets import (
    EvalMockLLM,
    OAGTarget,
    RAGBaselineTarget,
    SceneRuntime,
)
from agenticx_oag.retrieval.ontology_hybrid import (
    DEFAULT_TOP_K,
    OntologyHybridRetriever,
)

TARGET_DESCRIPTIONS = {
    "oag": (
        "OAG 全链：ContextPackPipeline（改写/实体链接/混合检索/主张生成）"
        "+ OAGGenerator 引用约束生成（Pack 约束）"
    ),
    "rag": (
        "RAG baseline：纯向量检索 top-{top_k} + 同一 LLM 直接生成"
        "（无 Pack 约束：无检索融合、无引用校验）"
    ),
}

FAIRNESS_NOTE = (
    "两个 target 使用同一 LLMProvider 实例、同一嵌入模型与同一 chunk 池"
    "（场景节点文本），唯一差异为是否经过 Context Pack 约束"
    "（检索融合与引用校验）。"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agenticx-oag", description="AgenticX-OAG engine CLI."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    eval_parser = subparsers.add_parser(
        "eval", help="Run the POC A/B evaluation and generate reports."
    )
    eval_parser.add_argument("--scenario", required=True, help="e.g. bank-aml")
    eval_parser.add_argument(
        "--targets",
        default="oag,rag",
        help="comma-separated target names: oag,rag (default: oag,rag)",
    )
    eval_parser.add_argument(
        "--limit", type=int, default=None, help="evaluate only the first N QA items"
    )
    eval_parser.add_argument(
        "--out", default="reports/poc/", help="output directory for the reports"
    )
    eval_parser.add_argument(
        "--mock-llm",
        action="store_true",
        help="use the deterministic mock LLM (no external provider needed)",
    )
    eval_parser.add_argument(
        "--recall-k",
        type=int,
        default=8,
        help="k for recall@k (default: 8)",
    )
    eval_parser.add_argument(
        "--datasets-dir", default=None, help="override eval/datasets directory"
    )
    eval_parser.add_argument(
        "--scenes-dir", default=None, help="override prototype/scenes directory"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "eval":
        return asyncio.run(_run_eval(args))
    return 2


async def _run_eval(args: argparse.Namespace) -> int:
    if not args.mock_llm:
        print(
            "错误：真实 LLMProvider 尚未接入 CLI，当前仅支持 --mock-llm。",
            file=sys.stderr,
        )
        return 2
    try:
        dataset = load_dataset(args.scenario, args.datasets_dir)
        scene = load_scene(args.scenario, args.scenes_dir)
    except (FileNotFoundError, ValueError) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 2

    llm = EvalMockLLM(scene)
    runtime = await SceneRuntime.load(scene)
    retriever = OntologyHybridRetriever(runtime.graph, runtime.vectors, runtime.embedder)
    factories: dict[str, Any] = {
        "oag": lambda: OAGTarget("oag", llm, runtime.ontology, retriever),
        "rag": lambda: RAGBaselineTarget(
            "rag", llm, runtime.vectors, runtime.embedder, top_k=DEFAULT_TOP_K
        ),
    }
    targets = []
    for name in [part.strip() for part in args.targets.split(",") if part.strip()]:
        if name not in factories:
            print(
                f"错误：未知 target {name!r}（可选：{', '.join(sorted(factories))}）。",
                file=sys.stderr,
            )
            return 2
        targets.append(factories[name]())
    if not targets:
        print("错误：--targets 不能为空。", file=sys.stderr)
        return 2

    runner = EvalRunner(judge=llm, recall_k=args.recall_k)
    result = await runner.run(args.scenario, targets, args.limit, dataset=dataset)

    meta = EvalMeta(
        scenario=args.scenario,
        dataset_version=dataset.version,
        targets={
            target.name: TARGET_DESCRIPTIONS.get(target.name, target.name).format(
                top_k=DEFAULT_TOP_K
            )
            for target in targets
        },
        llm="mock:EvalMockLLM（prompt 分发式确定性 mock）",
        ran_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        git_sha=_git_sha(),
        fairness_note=FAIRNESS_NOTE,
        reproduce_command=_reproduce_command(args),
    )
    markdown, html = render_report(result, meta)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    markdown_path = out_dir / f"{args.scenario}-{stamp}.md"
    html_path = out_dir / f"{args.scenario}-{stamp}.html"
    markdown_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")

    evaluated = len(dataset.items if args.limit is None else dataset.items[: args.limit])
    print(
        f"评测完成：scenario={args.scenario}，{evaluated} 条 QA × "
        f"{len(targets)} 个 target，{len(result.failures)} 个失败项"
    )
    for name, metrics in result.summaries.items():
        headline = ", ".join(
            f"{metric}={summary.mean:.3f}" for metric, summary in metrics.items()
        )
        print(f"  {name}: {headline}")
    print(f"报告：{markdown_path}")
    print(f"报告：{html_path}")
    return 0


def _reproduce_command(args: argparse.Namespace) -> str:
    parts = [
        "agenticx-oag",
        "eval",
        "--scenario",
        args.scenario,
        "--targets",
        args.targets,
    ]
    if args.limit is not None:
        parts += ["--limit", str(args.limit)]
    if args.mock_llm:
        parts.append("--mock-llm")
    parts += ["--out", args.out]
    return shlex.join(parts)


def _git_sha() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return completed.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


if __name__ == "__main__":
    sys.exit(main())
