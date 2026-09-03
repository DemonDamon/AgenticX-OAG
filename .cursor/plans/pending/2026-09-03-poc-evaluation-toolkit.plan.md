---
name: "P06 POC 评测工具包：指标 + 数据集 + A/B 对照 + 一键报告"
overview: "实现 faithfulness/citation/hallucination 等指标、三场景 QA 数据集、OAG vs 纯 RAG 的 A/B 评测框架与一键 Markdown/HTML 报告，作为 POC 的量化证据工具兼销售物料。"
todos: []
isProject: false
---

# P06 POC 评测工具包 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
>
> Planned-with: glm 5.3
> Suggested-Impl-Model: 代码专精中档（指标计算是确定性函数，数据集/报告是结构化样板；LLM judge 的 prompt 已在 plan 给出）

**Goal:** POC 阶段的核心武器：跑一条命令得到「OAG vs 纯 RAG」的量化对比报告。指标定义来自仓库 03 研究笔记；报告兼作售前物料（客户容量规划查表 + 效果对比一页纸）。

**Architecture:** 指标层（纯函数，可单测）→ 数据集层（YAML QA 集，golden evidence 引用图节点 id）→ Runner（注入被测系统：OAG 全链 vs RAG baseline）→ 报告层（模板渲染）。被测系统通过 `EvalTarget` Protocol 注入，评测框架不 import 具体实现（可插第三方 RAG 做对照）。

**Tech Stack:** Python 3.11 / pydantic / jinja2（报告模板）/（LLM judge 走 LLMProvider 注入）

---

## 背景与动机（证据链）

- `docs/enterprise-landing.md` §二阶段一交付物：一份评测报告（vs 纯 RAG / vs 纯 Agent）；§七调整建议 2「Phase 2 增加 POC 工具包：一键生成 POC 报告、评测对比报告，降低销售成本」。
- `docs/roadmap.md` Phase 2 交付物 4：评测框架（Recall@k / Faithfulness / Citation correctness / Hallucination rate；离线评测集：bank-aml + supply-chain + power-grid；与纯 RAG、纯 GraphRAG 对照）+ 验收标准「faithfulness 比纯向量 RAG 高 ≥20%、citation correctness ≥85%」。
- `docs/architecture.md` §7.3：基准测试门禁是 Phase 2 交付物，兼作销售工具。

## 需求定义

### FR（Functional Requirements）

- **FR-1 指标实现**：`agenticx_oag/eval/metrics.py`，全部为纯函数：
  - `recall_at_k(retrieved_ids: list[str], golden_ids: list[str], k: int) -> float`：top-k 命中 golden 的比例。
  - `citation_correctness(answer_citations: list[str], pack_evidence_ids: list[str]) -> float`：合法引用数 / 总引用数（合法=存在于 Pack evidence）。
  - `faithfulness(claims: list[Claim], evidence_texts: list[str], judge: LLMProvider) -> float`：LLM judge 逐条判定 claim 是否被 evidence 蕴含（prompt：「判断以下陈述是否能由给定证据推出，仅输出 JSON {"entailed": true/false, "reason": "..."}」），faithfulness = 被蕴含数 / 总主张数；judge 失败按 0.5 计入并标记。
  - `hallucination_rate(answer_sentences: list[str], cited_sentences: list[str]) -> float`：无引用断言句数 / 总断言句数（句切分复用 P05 的规则常量）。
  - 汇总函数 `aggregate(metric_values: dict[str, list[float]]) -> dict[str, MetricSummary{mean, p50, p95, n}]`。
- **FR-2 数据集格式与种子**：`eval/datasets/<scenario>.yaml`：
  ```yaml
  scenario: bank-aml
  version: 1
  items:
    - id: qa-001
      question: 哪些客户与制裁名单关联？
      golden_object_ids: [C-001, C-003]      # 图中应被检索命中的对象
      golden_answer_keywords: [制裁, 关联]    # 答案覆盖度辅助检查（弱指标，可选）
  ```
  本 plan 交付 `bank-aml.yaml` 种子（≥30 条 QA，基于 P10 模板示例数据的确定性问题；P10 未完成前先用 `prototype/scenes/bank-aml.json` 的 20 节点出题）+ `supply-chain.yaml`、`power-grid.yaml` 各 ≥10 条（同样源自对应 scene JSON）。数据集文件是**产品资产**，提交入库。
- **FR-3 被测目标抽象**：`agenticx_oag/eval/targets.py` 定义 `EvalTarget(Protocol)`：
  ```python
  class EvalTarget(Protocol):
      name: str
      async def answer(self, question: str) -> EvalAnswer: ...   # EvalAnswer{text, citations, retrieved_ids, claims}
  ```
  内置实现两个：`OAGTarget`（组装 P04 store + P05 pipeline/generator，依赖注入 mock 或真实 LLM）、`RAGBaselineTarget`（纯向量检索 + 同一 LLM 直接生成，无 Pack 约束——作为对照组）。
- **FR-4 A/B Runner**：`agenticx_oag/eval/runner.py` 的 `EvalRunner`：
  - `run(scenario: str, targets: list[EvalTarget], limit: int | None) -> EvalResult`：逐 QA 并发（asyncio.gather，并发 5）调用各 target，逐条计算四指标 + 覆盖率（golden_answer_keywords 命中率）。
  - 失败项记入 `EvalResult.failures`（不中断），报告标注。
- **FR-5 报告生成**：`agenticx_oag/eval/report.py`：`render_report(result: EvalResult, meta: EvalMeta) -> tuple[str, str]`（Markdown + HTML 同内容）。
  - `EvalMeta{scenario, dataset_version, targets 配置摘要, llm 标识, ran_at, git_sha}`——可复现性字段必须齐全。
  - 报告结构：① 指标对比总表（target × metric）② 逐指标 win/lose 判定 ③ 失败项列表 ④ 复现命令。jinja2 模板放 `agenticx_oag/eval/templates/report.md.j2` 与 `report.html.j2`。
- **FR-6 CLI 入口**：`agenticx_oag/cli.py`（新建，argparse 即可，不引 click）：
  ```
  agenticx-oag eval --scenario bank-aml --targets oag,rag --limit 30 --out reports/poc/
  ```
  console_scripts 注册 `agenticx-oag = agenticx_oag.cli:main`。产物：`reports/poc/bank-aml-<date>.md` + `.html`。`reports/` 目录 gitignore（报告按需另存），数据集入库。

### NFR（Non-Functional Requirements）

- **NFR-1** 30 QA × 2 target，mock LLM 下全量 < 10s。
- **NFR-2** 指标函数全部确定性可单测（faithfulness 的 judge 走注入，测试用固定响应 mock）。

## 精确落点

| 改动 | 路径 |
|---|---|
| 指标 | `agenticx_oag/eval/metrics.py`（新建） |
| 数据集 | `eval/datasets/bank-aml.yaml`（≥30）、`supply-chain.yaml`（≥10）、`power-grid.yaml`（≥10）（新建） |
| 目标抽象 | `agenticx_oag/eval/targets.py`（新建） |
| Runner | `agenticx_oag/eval/runner.py`（新建） |
| 报告 | `agenticx_oag/eval/report.py`、`agenticx_oag/eval/templates/report.md.j2`、`report.html.j2`（新建） |
| CLI | `agenticx_oag/cli.py`（新建；pyproject 增 `[project.scripts]`） |
| 测试 | `tests/eval/test_metrics.py`、`test_runner.py`、`test_report.py`（新建） |
| gitignore | `.gitignore` 追加 `reports/` |

## 关键实现意图

**指标手算 fixture（单测基准，实施者照此断言）**：

```
recall_at_k(retrieved=["A","B","C"], golden=["B","D"], k=2) == 0.5     # top2={A,B} 命中 B
citation_correctness(citations=["E1","E9"], evidence=["E1","E2"]) == 0.5
hallucination_rate(sentences=["a[E1]。","b。","c[E2]。"], cited=["a[E1]。","c[E2]。"]) == 1/3
```

**RAGBaselineTarget 与 OAGTarget 的公平性约束**：同一 LLMProvider 实例、同一嵌入模型、同一 chunk 池；唯一差异 = 是否经过 Pack 约束（检索融合与引用校验）。报告 meta 中记录该对齐声明。

## In scope / Out of scope

**In scope：** FR-1~FR-6；`pyproject.toml` 增 `[eval]` extra（jinja2）与 console_scripts。
**Out of scope（no-scope-creep）：** 不做 GraphRAG 第三对照（接口已留，后续加）；不做容量/性能压测（那是 architecture.md §7.3 的 k6 基准，独立 plan）；不做数据集自动生成（LLM 出题需人工审核，不做自动化）；不做报告的飞书/邮件推送。

## 验收标准（AC）

| FR | AC | 验证方式 |
|---|---|---|
| FR-1 | 四指标手算 fixture 全部断言通过；faithfulness 用固定 judge mock（2/3 蕴含 → 0.667） | `tests/eval/test_metrics.py` |
| FR-2 | 三个数据集 YAML 可被 loader 解析；bank-aml ≥30 条且 golden_object_ids 均存在于对应 scene JSON 节点 | `test_runner.py::test_dataset_load`（加载 `prototype/scenes/*.json` 交叉校验） |
| FR-3 | RAGBaselineTarget 在 mock 下返回 EvalAnswer 四字段齐全 | `test_runner.py` |
| FR-4 | 30 QA × 2 target mock 跑通，EvalResult 指标矩阵完整、failures 可注入测试 | `test_runner.py::test_ab_run` |
| FR-5 | 报告含对比总表 + meta 复现字段（git_sha 非空）；HTML 无模板错误残留 `{{` | `test_report.py` |
| FR-6 | `agenticx-oag eval --scenario bank-aml --targets oag,rag --limit 5`（mock 模式 `--mock-llm` 开关）退出码 0，产出两份报告文件 | 本地命令 |
