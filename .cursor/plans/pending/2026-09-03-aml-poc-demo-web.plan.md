---
name: "P10 金融 AML 首场景 POC Demo：智能问询 + 关联图谱 + 溯源面板 Web 应用"
overview: "POC 阶段的可演示 Web 交付物：FastAPI 后端桥接引擎（P03/P04/P05）+ React 前端三栏应用（问答带引用、证据溯源抽屉、团伙关联图可视化、评测报告页），含 AML 种子数据、一键启动与演示剧本。P07/P08/P09 可选增强。"
todos: []
isProject: false
---

# P10 金融 AML 首场景 POC Demo Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
>
> Planned-with: glm 5.3
> Suggested-Impl-Model: 代码专精中档（后端是桥接层、逻辑全在引擎包；前端是结构化三栏布局 + d3-force 图，组件树与数据流已在 plan 写全）

**Goal:** 交付 `docs/enterprise-landing.md` 阶段一（POC）的核心交付物「一个可演示的场景 Demo（Web 端）」：银行反洗钱场景——自然语言提问 → OAG 答案（每句带引用脚标）→ 点击引用展开证据原文与来源 → 可疑交易团伙多跳关联图可视化 → 评测报告页（P06 产物）→（治理增强，可选）冻结提案走 Harness 四层校验 + 审批流演示。**本 Demo 是 POC 主线 P02→P03→P04→P05 的收口交付物，也是 P06 评测数据的展示出口。**

**Architecture:** 后端 `apps/demo/backend/` 为 FastAPI 薄桥接层：不实现任何引擎逻辑，只做依赖装配（AGE DSN / LLMProvider mock 或真实）与 HTTP 编排，调用 `agenticx_oag` 包（P03 本体、P04 AGEGraphStore、P05 Pipeline+Generator、P06 报告文件）。前端 `apps/demo/frontend/` 为 React+Vite 三栏 SPA：左对话、中答案+引用、右图/溯源，状态用 zustand。治理能力（P07 gRPC / P08 CLI / P09 库）通过环境变量开关 `OAG_DEMO_GOVERNANCE=1` 启用，未启用时对应端点返回 501 且 UI 隐藏入口——**POC 只主打一个象限（检索型：KG Schema + OAG），治理是叠加演示而非主线**（enterprise-landing.md 落地红线）。

**Tech Stack:** Python 3.11 / FastAPI / uvicorn / httpx（调 P07 gRPC 用 grpcio，可选 extra）/ React 18 + Vite + TypeScript / zustand / d3-force（图布局，SVG 自绘）/ pnpm

---

## 背景与动机（证据链）

- `docs/enterprise-landing.md` 阶段一交付物四件套：可演示场景 Demo（本 plan）、评测报告（P06）、场景本体模型（P03 的 templates/finance/aml/ontology.yaml）、四象定位报告（P01 物料产出）——本 plan 是其中工程量最大的一件。
- `docs/enterprise-landing.md` 阶段一「怎么做」：接入客户真实数据或脱敏样本（本 plan 用虚构种子数据替代）、跑通「提问 → OAG 检索 → 生成答案 + 来源追溯」全链路、拿评测指标说话（报告页）。
- `docs/roadmap.md` Phase 3 验收标准：「bank-aml 场景可以走完『可疑交易识别 → 风险评估 → 冻结提案 → 审批 → 执行冻结 → 审计记录』全链路」——治理增强模式对应此验收。
- P06 plan 已声明：QA 数据集「P10 未完成前先用 `prototype/scenes/bank-aml.json` 的 20 节点出题」——即本 plan 需交付扩展版 AML 种子数据（图数据 + 文档），供 P06 出题与 Demo 共用。
- P04 plan FR-7 的 `examples/kg_build_demo.py` 已建立「3 篇 AML 示例文档 → AGE」的管道；本 plan 扩充数据并做 Web 化。P05 plan 的 `build_pack(question)` / Generator / `CitationValidator` 是问答链路的引擎侧实现。

## 需求定义

### FR（Functional Requirements）

- **FR-1 后端骨架**：`apps/demo/backend/app/main.py` 创建 FastAPI 应用，启动时装配：加载本体 YAML（P03 `load_ontology`）→ 连 AGE（P04 `AGEGraphStore`，DSN 从 `OAG_AGE_DSN`，默认 `postgresql://oag:oag@localhost:5432/oag`）→ 构造 P05 `Pipeline` 与 `Generator`（LLMProvider：`OAG_LLM_MODE=mock` 默认 mock 固定应答；`=real` 走注入的真实 provider）。`GET /api/health` 返回 `{status, ontology_ns, graph_ok, llm_mode}`。
- **FR-2 问答端点**：`POST /api/ask` `{question}` → `{answer, citations: [{marker, evidence_id, object_id, text, score, provenance}], pack_id}`——调 P05 `build_pack` + Generator；`OAG_LLM_MODE=mock` 时返回固定剧本应答（见 FR-9 演示剧本）以便离线演示。记录 `pack_id`（Pack 序列化到内存 dict，TTL 30min）。
- **FR-3 证据端点**：`GET /api/pack/{pack_id}` → 完整 Context Pack JSON（P05 模型 `model_dump`）——供前端 EvidenceDrawer 展示改写链、对象引用、证据、主张、不确定性。
- **FR-4 图端点**：`GET /api/graph?object_id={id}&hops={n}` → `{nodes: [{id, object_type, label, props}], edges: [{source, target, link_type}]}`——调 P04 `GraphStore.neighbors`，默认 hops=2；`GET /api/graph/schema` → 本体 ObjectType/LinkType 关系图（schema 级，P03 模型导出）。
- **FR-5 对象端点**：`GET /api/objects/{object_type}?q={keyword}&limit=50` → 对象列表（P04 `get_objects` + 关键词前端过滤可）；`GET /api/objects/{object_type}/{object_id}` → 详情 + 2 跳邻居摘要。
- **FR-6 报告端点**：`GET /api/report` → 读 P06 最新报告产物（`eval/reports/` 下最新 `*.html`，`text/html` 直出；无报告时 404 + 提示先生成）。
- **FR-7 治理端点（可选增强）**：`OAG_DEMO_GOVERNANCE=1` 时启用：`POST /api/action/propose`（接收 Proposal JSON → P08 `HarnessEngine.evaluate` → BLOCK 则 403 返回 Verdict；ALLOW 则经 P07 gRPC `Propose` 返回 ActionRecord）、`GET /api/action/{action_id}`（P07 GetStatus 透传）、`GET /api/perm/check`（P09 PolicyEngine 直评）。开关关闭时上述端点统一 501 `{detail: "治理能力未启用：OAG_DEMO_GOVERNANCE=1 开启"}`。
- **FR-8 种子数据与脚本**：`apps/demo/backend/scripts/seed.py`——① 调 P04 摄入管道处理 `apps/demo/data/docs/*.md`（≥8 篇虚构 AML 调查报告，含客户背景、可疑交易叙事、团伙线索；每篇 ≥3 个可抽取实体）；② 直接注入 `apps/demo/data/seed_objects.json`（≥30 实例：8 Customer、12 Transaction、6 Account、4 Company，含一个 5 节点可疑团伙：C-001 通过 A-001→T-101→A-002→T-205→A-003→C-007 的 3 跳链路）；③ 幂等（按 namespace 重建 AGE graph）。`--wipe` 参数清空重建。
- **FR-9 演示剧本**：`docs/demo-script.md`——5 个标准演示问题与预期效果：Q1 单跳事实（「C-001 的风险等级？」）、Q2 多跳团伙（「T-101 的资金最终流向了哪个客户？」，需 ≥3 跳）、Q3 统计（「高风险客户有几个？」）、Q4 溯源验证（「这个结论的依据是什么？」→ 展示 EvidenceDrawer）、Q5 治理演示（冻结提案 → Harness 拦截 VIP 案例，仅治理模式）。mock 模式固定应答文案覆盖 Q1-Q4。
- **FR-10 前端三栏应用**：`apps/demo/frontend/`——
  - 布局：左栏 `ChatPanel`（提问输入 + 历史问题列表）；中栏 `AnswerCard`（答案文本，引用脚标 `[E1]` 内联可点）；右栏 Tab 切换 `GraphCanvas` / `EvidenceDrawer` / `ReportViewer`。
  - `CitationChip`：点击引用脚标 → EvidenceDrawer 定位到对应证据（高亮），GraphCanvas 同步高亮该证据的 object_id 节点。
  - `GraphCanvas`：d3-force 布局 + SVG 自绘（节点按 object_type 着色，图例；点击节点 → 调 /api/graph 展开该节点 2 跳；hover 显示 props tooltip）。
  - `ReportViewer`：iframe 嵌 `/api/report`。
  - 治理模式：左栏底部出现「处置提案」入口 → 弹窗表单（action_type/target/参数）→ 调 /api/action/propose → 展示 Verdict（ALLOW 显示审批流状态，BLOCK 显示违规明细）。
  - 顶栏：健康状态（/api/health 轮询 30s）+ `OAG_LLM_MODE` 徽标。
- **FR-11 一键启动**：根 `Makefile` 增 `demo` 目标：`dev-up → python scripts/seed.py → uvicorn apps.demo.backend.app.main:app --port 7580`；`demo-frontend` 目标：`cd apps/demo/frontend && pnpm install && pnpm dev`（Vite 5790 端口，`AGX` 风格 strictPort）。README 快速开始一节同步。

### NFR（Non-Functional Requirements）

- **NFR-1** mock 模式下全程离线可演示（无任何外网依赖），/api/ask P95 < 800ms。
- **NFR-2** 前端构建产物 gzip < 300KB（d3-force 仅布局模块，按需 import，不引整包 d3）。
- **NFR-3** 后端桥接层不出现任何引擎逻辑复述（检索/生成/校验一律 import 引擎包）——桥接层被删掉不影响引擎单测。

## 精确落点

| 改动 | 路径 |
|---|---|
| 后端应用 | `apps/demo/backend/app/main.py`、`app/deps.py`（装配）、`app/routers/{ask,graph,objects,report,governance}.py`（新建） |
| 种子脚本 | `apps/demo/backend/scripts/seed.py`（新建） |
| 种子数据 | `apps/demo/data/docs/*.md`（≥8 篇新建）、`apps/demo/data/seed_objects.json`（新建） |
| 前端 | `apps/demo/frontend/`：`package.json`、`vite.config.ts`、`index.html`、`src/main.tsx`、`src/App.tsx`、`src/store.ts`、`src/api.ts`、`src/components/{ChatPanel,AnswerCard,CitationChip,EvidenceDrawer,GraphCanvas,ReportViewer,GovernanceModal,TopBar}.tsx`（新建） |
| 演示剧本 | `docs/demo-script.md`（新建） |
| 构建 | 根 `Makefile` 增 `demo / demo-frontend`（修改）；根 `README.md` 增快速开始（修改） |
| 依赖 | 后端依赖声明于 `apps/demo/backend/requirements.txt`（fastapi/uvicorn/httpx；grpcio 仅注释行注明治理模式需要）；不进 `pyproject.toml` 核心（Demo 是应用不是库） |
| 测试 | `apps/demo/backend/tests/test_api.py`（新建，引擎依赖全 mock） |

## 关键实现意图

**deps.py 装配（依赖注入中心，测试替换点）**：

```python
@lru_cache
def get_deps() -> Deps:
    ontology = load_ontology("templates/finance/aml/ontology.yaml")       # P03
    graph = AGEGraphStore(os.environ.get("OAG_AGE_DSN", DEFAULT_DSN))     # P04
    llm = MockAMLProvider() if os.environ.get("OAG_LLM_MODE", "mock") == "mock" else build_real_provider()
    pipeline = Pipeline(graph=graph, vectors=..., llm=llm, embedder=...)  # P05
    generator = Generator(llm=llm)                                        # P05
    return Deps(ontology=ontology, graph=graph, pipeline=pipeline, generator=generator,
                governance=GovernanceKit.load() if governance_enabled() else None)
```

**ask 路由（桥接，不含逻辑）**：

```python
@router.post("")
async def ask(body: AskBody, deps = Depends(get_deps)):
    pack = await deps.pipeline.build_pack(body.question)                  # P05
    answer = await deps.generator.generate(pack)                          # P05（含引用约束）
    _PACKS[pack.pack_id] = pack                                           # 内存缓存 TTL 30min
    return {"answer": answer.text, "citations": answer.citations, "pack_id": pack.pack_id}
```

**seed_objects.json 团伙链路（演示核心，必含）**：

```json
{"namespace": "finance.aml", "objects": [
  {"object_type": "Customer", "id": "C-001", "props": {"name": "王某", "riskLevel": "high", "region": "CN", "accountTier": "vip"}},
  {"object_type": "Account",  "id": "A-001", "props": {"iban": "CN***1001", "status": "active"}},
  {"object_type": "Transaction", "id": "T-101", "props": {"amount": 1500000, "currency": "CNY", "flagged": false}},
  {"object_type": "Account",  "id": "A-002", "props": {"iban": "CN***2002", "status": "active"}},
  {"object_type": "Transaction", "id": "T-205", "props": {"amount": 1480000, "currency": "CNY"}},
  {"object_type": "Account",  "id": "A-003", "props": {"iban": "CN***3003"}},
  {"object_type": "Customer", "id": "C-007", "props": {"name": "李某", "riskLevel": "high", "region": "US"}}
], "links": [
  {"link_type": "owns",  "source": "C-001", "target": "A-001"},
  {"link_type": "conducted", "source": "A-001", "target": "T-101"},
  {"link_type": "transfersTo", "source": "T-101", "target": "A-002"},
  {"link_type": "conducted", "source": "A-002", "target": "T-205"},
  {"link_type": "transfersTo", "source": "T-205", "target": "A-003"},
  {"link_type": "owns",  "source": "C-007", "target": "A-003"}
]}
```

（团伙 5+ 节点、C-001→C-007 共 3 跳；Q2 多跳问题的数据基础。link_type 名称以 P03 ontology.yaml 实际定义为准，实施时对齐。）

**GraphCanvas 数据流**：`api.fetchGraph(objectId, 2)` → zustand `graphSlice` → `d3-force` simulation（forceLink/forceManyBody/forceCenter，300 ticks 预计算）→ SVG 渲染（`<g class="node">` circle+label）；点击节点 dispatch `expandNode(id)`；引用点击 dispatch `highlightNode(objectId)`（描边脉冲动画 CSS）。

**治理装配（可选）**：

```python
class GovernanceKit:
    harness: HarnessEngine          # P08
    policy: PolicyEngine            # P09
    action_stub: ActionGatewayClient  # P07 grpc（grpc.aio，OAG_GATEWAY_ADDR 默认 localhost:7570）
```

## In scope / Out of scope

**In scope：** FR-1~FR-11 全部；`.gitignore` 增 `apps/demo/frontend/node_modules`、`apps/demo/frontend/dist`。

**Out of scope（no-scope-creep）：** 不做多用户登录/session（治理演示用固定 actor 参数传入）；不做流式 SSE 应答（POC 演示同步返回足够）；不实现 Pack 持久化到 PG/MinIO（内存 TTL 缓存够演示，生产化后续）；不引 react-force-graph/cytoscape 等重图库（d3-force+SVG 自绘）；不做移动端适配；不接管 P06 的报告生成（只读渲染其产物）；不修改 prototype/ 目录任何文件（原型保持只读参照）。

## 验收标准（AC）

| FR | AC | 验证方式 |
|---|---|---|
| FR-1 | `make demo` 后 `curl localhost:7580/api/health` 返回 `status: ok` 且 `graph_ok: true`（AGE 已起） | 本地命令 |
| FR-2 | mock 模式 `POST /api/ask {"question": "C-001 的风险等级？"}` 返回非空 answer 且 citations ≥1；引擎 mock 注入（monkeypatch build_pack/generate）验证桥接不掺逻辑 | `test_api.py::test_ask` |
| FR-3 | ask 后 `GET /api/pack/{pack_id}` 返回 JSON 含 `evidence` 数组且首条 `object_id` 非空 | `test_api.py::test_pack` |
| FR-4 | seed 后 `GET /api/graph?object_id=C-001&hops=2` 返回 ≥6 nodes、≥5 edges，含 C-007 或 T-205（3 跳链路可分段展开）；`/api/graph/schema` 返回 8 个 object_type | integration + `test_api.py::test_graph` |
| FR-5 | `GET /api/objects/Customer` 返回 8 条；`GET /api/objects/Customer/C-001` 详情含邻居摘要 ≥2 | `test_api.py::test_objects` |
| FR-6 | `eval/reports/` 有产物时 200 text/html；无产物时 404 且 detail 含「先生成」提示 | `test_api.py::test_report` |
| FR-7 | 默认（开关关）propose 返回 501；开关开 + mock Harness（BLOCK）返回 403 + violations；mock ALLOW + mock gRPC stub 返回 ActionRecord | `test_api.py::test_governance_*`（3 用例） |
| FR-8 | `python apps/demo/backend/scripts/seed.py` 幂等（跑两次数据量不变）；`--wipe` 后重建成功；docs ≥8 篇且 P04 抽取实体 ≥10 入图（integration） | 本地命令 |
| FR-9 | demo-script.md 含 5 问及预期输出示例；Q1-Q4 在 mock 模式全部可复现 | 人工走查 + 演示记录 |
| FR-10 | `pnpm build` 通过；界面：中栏答案内 `[E1]` 可点 → 右栏 EvidenceDrawer 高亮对应证据且 GraphCanvas 高亮其 object_id 节点；图节点点击可展开；顶栏徽标显示 mock/real | 人工走查（截图存 `docs/demo-script.md` 附录） |
| FR-11 | `make demo` 与 `make demo-frontend` 两条命令按 README 快速开始可完整走通 demo-script Q1-Q4 | 本地命令 |
