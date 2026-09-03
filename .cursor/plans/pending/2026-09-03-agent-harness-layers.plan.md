---
name: "P08 Agent Harness：四层语义约束引擎（概念/规则/流程/技能，先校验后执行）"
overview: "实现治理 LLM 决策过程的四层校验引擎：概念层认知边界、规则层 MUST/MUST_NOT/MAY、流程层 SOP 步骤、技能层工具白名单+IO 契约；LLM 提案先过四层校验，任何一层 BLOCK 即拦截。规则用 YAML DSL 定义。"
todos: []
isProject: false
---

# P08 Agent Harness 四层语义约束 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
>
> Planned-with: glm 5.3
> Suggested-Impl-Model: 代码专精中档偏强（DSL 语义必须一次定准无歧义；条件求值器需完备单测；校验顺序与短路语义是正确性关键）

**Goal:** 落地治理双维度中的**语义约束维度**（`docs/enterprise-landing.md` §3.1，源自紫皮书 6.1）：Agent/LLM 生成的「提案」（Proposal）在执行前必须依次通过概念层 → 规则层 → 流程层 → 技能层四道校验，任何一层 BLOCK 即拦截，实现「先校验后执行」。这是对 Semantica 的核心代差——治理的是 LLM 的生成过程，不是确定性代码。

**Architecture:** 纯 Python 库（控制面），无 IO 依赖：输入是结构化 `Proposal`（pydantic）+ 规则集（YAML DSL），输出是 `Verdict`（ALLOW/BLOCK + 命中违规明细）。四层校验器各自独立成模块，`HarnessEngine` 按固定顺序编排并短路。规则 ID 与 P03 `ActionType.preconditions` 对齐（P03 做格式校验，本 plan 提供规则本体与交叉校验工具）。校验通过的 Proposal 由调用方（P10 Demo / 未来 Agent Runtime）提交给 P07 Action Gateway 执行——本 plan 不调用 P07，两者通过 Proposal JSON schema 契约解耦、可并行开发。

**Tech Stack:** Python 3.11 / pydantic v2 / pyyaml / jsonschema（新增依赖，加入 `pyproject.toml` 核心依赖）/ pytest

---

## 背景与动机（证据链）

- `docs/enterprise-landing.md` §3.1 治理双维度：Agent Harness 四层（语义约束维度）——概念层（认知边界：Agent 能讨论什么）/ 规则层（MUST·MUST_NOT·MAY 行为准则）/ 流程层（SOP 步骤不可跳过不可乱序）/ 技能层（工具白名单 + 输入输出契约 + 超时重试）。LLM 提案先过四层校验，任何一层 BLOCK 即拦截。
- `docs/enterprise-landing.md`：紫皮书对「Palantir 治理执行（管确定性代码）vs Agent Ontology 治理生成（管概率性 LLM）」的精确切分，是本 plan 的存在理由。
- `docs/roadmap.md` Phase 3 交付物 5「规则引擎集成」：确定性规则与本体绑定（某类对象必须满足某条件才能执行某 Action），轻量 forward chaining 优先。
- P02 plan 已锁定：proto 中 `ActionType.preconditions` 是规则 ID 列表（P08 Harness 规则）；P03 plan 的 FR-3 声明 preconditions「允许前向引用 P08 规则 ID，仅做格式校验」——即本 plan 是这些 ID 的定义方。
- 紫皮书案例（维修工卡 Agent / 用药禁忌拦截）验证「先校验后执行」是 Agent Ontology 象限的落地形态；bank-aml 场景的 VIP 冻结人工复核、大额两级审批是首批规则集素材。

## 需求定义

### FR（Functional Requirements）

- **FR-1 Proposal 模型**：`agenticx_oag/harness/model.py` 定义 `Proposal`（pydantic，字段见「关键实现意图」）。Proposal 是四层校验的唯一输入，也是提交给 P07 的载荷来源（`action_type/target/parameters` 字段名与 P07 `ActionProposal` 对齐）。
- **FR-2 Verdict 模型**：`model.py` 定义 `Verdict`（`decision: ALLOW|BLOCK`、`violations: list[Violation]`、`evaluated_layers: list[str]`、`explanation: str`）与 `Violation`（`layer / rule_id / directive / message / evidence_path`）。
- **FR-3 规则 DSL**：`agenticx_oag/harness/dsl.py` 定义规则集 YAML schema（pydantic 加载 + 校验），四节：`concept / rules / procedures / skills / tool_allowlist`（完整 schema 见「关键实现意图」）。非法 directive / op / 层引用 → pydantic `ValidationError`，错误消息含行级字段路径。
- **FR-4 条件求值器**：`dsl.py` 提供 `resolve(proposal, path) -> Any`（点分路径，支持 `intent / target.object_type / target.object_id / parameters.* / tools / completed_steps / procedure_state`）与 `matches(when, proposal) -> bool`。操作符全集：`eq / ne / gt / gte / lt / lte / in / contains / exists`（数值比较仅接受双方可转 float；类型不符返回 False 而非抛错，并记 warning）。
- **FR-5 概念层**：`layers/concept.py`——校验 `target.object_type ∈ concept.allowed_object_types` 且 `intent ∈ concept.allowed_intents`；越界 → BLOCK（violation layer=concept）。
- **FR-6 规则层**：`layers/rules.py`——遍历全部 `rules`，`when` 命中后按 directive 判定：`MUST_NOT` 命中即 BLOCK；`MUST` 命中后 `then` 条件为假则 BLOCK（语义：「满足 when 的提案必须同时满足 then」）；`MAY` 命中仅记 violation（`severity: note`）不拦截。未命中 `when` 的规则跳过。
- **FR-7 流程层**：`layers/procedure.py`——按 `target.object_type` 匹配 procedure（无匹配则通过，视为该对象类型无 SOP 约束）：`procedure_state` 必须在该 procedure 的 `steps` 内；`order_strict: true` 时，`procedure_state` 的前驱步骤必须全部出现在 `completed_steps` 中（越级/跳步 → BLOCK）。
- **FR-8 技能层**：`layers/skill.py`——`tools` 必须 ⊆ `tool_allowlist`（越权工具 → BLOCK）；每个 tool 若在 `skills` 中定义了 `input_schema`，其 `tool_inputs[tool]` 必须通过 JSON Schema 校验（校验失败 → BLOCK）；`timeout_ms / max_retries` 仅承载于 DSL 供执行方读取，本层不做超时 enforcement。
- **FR-9 引擎编排**：`agenticx_oag/harness/engine.py` 的 `HarnessEngine(rule_set).evaluate(proposal) -> Verdict`——固定顺序 concept → rules → procedure → skill，**任一层 BLOCK 立即返回**（后续层不再评估，`evaluated_layers` 只含已评估层）；全部通过 → ALLOW。
- **FR-10 AML 规则集**：`templates/finance/aml/harness.yaml`（完整内容见「关键实现意图」）——含 VIP 冻结人工复核（MUST_NOT）、百万级处置两级审批（MUST）、可疑交易处置 SOP（5 步 order_strict）、graph.neighbors 工具契约。
- **FR-11 交叉校验工具**：`agenticx_oag/harness/crossref.py` 的 `check_preconditions(ontology_yaml, harness_yaml) -> list[str]`——返回本体中引用了但规则集中不存在的 preconditions ID（空列表=一致）。
- **FR-12 CLI**：`python -m agenticx_oag.harness` 支持 `validate <harness.yaml>`（DSL 自检）与 `check <proposal.json> <harness.yaml>`（输出 Verdict JSON），供 P10 Demo 与售前演示直接调用。

### NFR（Non-Functional Requirements）

- **NFR-1** 单次 `evaluate`（≤100 条规则）P95 < 5ms（纯内存求值，无 IO）。
- **NFR-2** 求值是纯函数：同一 (rule_set, proposal) 输入永远同输出（可重放，审计要求）。
- **NFR-3** DSL 字段一旦合入即视为契约（与 P02 接口同等地位），变更需显式版本化（rule_set.version 递增）。

## 精确落点

| 改动 | 路径 |
|---|---|
| 模型 | `agenticx_oag/harness/model.py`（新建） |
| DSL | `agenticx_oag/harness/dsl.py`（新建：RuleSet 加载/校验/路径求值/when 匹配） |
| 四层 | `agenticx_oag/harness/layers/__init__.py`、`concept.py`、`rules.py`、`procedure.py`、`skill.py`（新建） |
| 引擎 | `agenticx_oag/harness/engine.py`（新建） |
| 交叉校验 | `agenticx_oag/harness/crossref.py`（新建） |
| CLI 入口 | `agenticx_oag/harness/__main__.py`（新建） |
| 规则集 | `templates/finance/aml/harness.yaml`（新建） |
| 依赖 | `pyproject.toml` 核心依赖增 `jsonschema>=4`（修改） |
| 测试 | `tests/harness/test_dsl.py`、`test_layers.py`、`test_engine.py`、`test_crossref.py`、`testdata/proposal_*.json`（新建） |
| 示例 | `examples/harness_demo.py`（新建：构造 3 个提案展示 ALLOW/BLOCK/BLOCK） |

## 关键实现意图

**Proposal 模型（字段即 P07 契约）**：

```python
class ObjectRef(BaseModel):
    object_type: str
    object_id: str

class Proposal(BaseModel):
    proposal_id: str
    agent_id: str
    intent: str                      # 如 "risk_assessment" / "investigation"
    action_type: str | None = None   # 关联本体 ActionType.api_name；纯言论型提案可空
    target: ObjectRef | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    tools: list[str] = Field(default_factory=list)
    tool_inputs: dict[str, dict[str, Any]] = Field(default_factory=dict)  # tool -> 入参
    claims: list[str] = Field(default_factory=list)   # 依据主张 ID（P05 claim-ledger）
    completed_steps: list[str] = Field(default_factory=list)  # SOP 已完成步骤
    procedure_state: str | None = None                 # 当前 SOP 步骤
```

**规则 DSL（templates/finance/aml/harness.yaml 完整内容）**：

```yaml
namespace: finance.aml
version: 1.0.0
concept:
  allowed_object_types: [Customer, Transaction, Account]
  allowed_intents: [risk_assessment, investigation, reporting]
rules:
  - id: aml.rule.vip-freeze-manual
    directive: MUST_NOT
    severity: block
    message: "VIP 客户冻结必须人工复核，Agent 不得直接提案"
    when:
      all:
        - {path: target.object_type, op: eq, value: Customer}
        - {path: parameters.accountTier, op: eq, value: vip}
        - {path: action_type, op: eq, value: freezeAccount}
  - id: aml.rule.large-amount-two-level
    directive: MUST
    severity: block
    message: "百万以上处置必须两级审批"
    when:
      all:
        - {path: parameters.amount, op: gt, value: 1000000}
    then: {path: parameters.approvalLevel, op: eq, value: two_level}
procedures:
  - id: aml.proc.suspect-handling
    object_type: Transaction
    order_strict: true
    steps: [detect, assess, propose, approve, execute]
skills:
  - id: aml.skill.graph-query
    tool: graph.neighbors
    input_schema:
      type: object
      properties: {object_id: {type: string}, max_hops: {type: integer, minimum: 1, maximum: 3}}
      required: [object_id]
    timeout_ms: 3000
    max_retries: 2
tool_allowlist: [graph.neighbors, doc.render, llm.complete]
```

DSL 校验规则（`dsl.py`）：`directive ∈ {MUST, MUST_NOT, MAY}`；`severity ∈ {block, note}`；`op ∈ {eq,ne,gt,gte,lt,lte,in,contains,exists}`；`when` 结构为 `{all: [cond...]}` 或单 cond；`then` 仅 `directive: MUST` 时必填；`steps` 非空且无重复；`skills[].tool` 唯一。

**rules.py 判定核心（语义精确版）**：

```python
for rule in rule_set.rules:
    if not matches(rule.when, proposal):
        continue
    if rule.directive == "MUST_NOT":
        violations.append(Violation(layer="rules", rule_id=rule.id, directive=rule.directive,
                                    message=rule.message, evidence_path=rule.when))
    elif rule.directive == "MUST":
        if rule.then is None or not matches({"all": [rule.then]}, proposal):
            violations.append(Violation(layer="rules", rule_id=rule.id, ...))
    else:  # MAY
        notes.append(...)   # severity=note，不拦截
blocked = any(v for v in violations if v.severity == "block")
```

**procedure.py 前驱校验**：

```python
proc = next((p for p in rule_set.procedures if p.object_type == proposal.target.object_type), None)
if proc is None:
    return []                       # 无 SOP 约束
if proposal.procedure_state not in proc.steps:
    return [Violation(layer="procedure", rule_id=proc.id, message=f"步骤 {proposal.procedure_state} 不在 SOP 中")]
if proc.order_strict:
    idx = proc.steps.index(proposal.procedure_state)
    missing = [s for s in proc.steps[:idx] if s not in proposal.completed_steps]
    if missing:
        return [Violation(layer="procedure", rule_id=proc.id, message=f"跳步：未完成 {missing}")]
return []
```

**engine.py 短路编排**：

```python
class HarnessEngine:
    def __init__(self, rule_set: RuleSet): self.rule_set = rule_set

    def evaluate(self, proposal: Proposal) -> Verdict:
        layers = [("concept", check_concept), ("rules", check_rules),
                  ("procedure", check_procedure), ("skill", check_skill)]
        evaluated, violations = [], []
        for name, fn in layers:
            evaluated.append(name)
            layer_violations = fn(self.rule_set, proposal)
            violations.extend(layer_violations)
            if any(v.severity == "block" for v in layer_violations):
                return Verdict(decision="BLOCK", violations=violations,
                               evaluated_layers=evaluated, explanation=...)
        return Verdict(decision="ALLOW", violations=violations,
                       evaluated_layers=evaluated, explanation="四层校验全部通过")
```

## In scope / Out of scope

**In scope：** FR-1~FR-12 全部；`tests/harness/testdata/` 至少 5 个 Proposal JSON 样本（覆盖各层 BLOCK 与 ALLOW）。

**Out of scope（no-scope-creep）：** 不调用 P07 执行 Action（引擎只出 Verdict，提交执行是调用方职责）；不做 CEL/OPA/ rete 表达式引擎（YAML DSL 的 9 个操作符够 MVP，复杂表达式后续独立 plan）；不做规则版本管理 UI；不校验 claims 的真实性（P05 的 CitationValidator 负责）；不做技能超时的运行时 enforcement（`timeout_ms` 仅作为契约传给执行方）；不改 P03 的 `Ontology.validate()`（preconditions 格式校验已在 P03 实现，交叉校验用独立工具）。

## 验收标准（AC）

| FR | AC | 验证方式 |
|---|---|---|
| FR-1/2 | `Proposal`/`Verdict` 可从 JSON round-trip（`model_validate_json` → `model_dump_json` 相等） | `test_model.py` |
| FR-3 | 未知 directive（`SHOULD`）、未知 op（`between`）、MUST 缺 `then` 三种非法 YAML 均抛 `ValidationError` 且消息含字段路径 | `test_dsl.py::test_invalid_dsl`（3 用例） |
| FR-4 | 9 个操作符各一正一反用例；`parameters.amount` 缺失时 `gt` 返回 False；数值字符串 `"1200000"` 与 int 比较为 True（可转 float） | `test_dsl.py::test_ops`（≥18 断言） |
| FR-5 | `object_type: "InternalMemo"`（不在 allowed）→ BLOCK layer=concept；合法类型通过 | `test_layers.py::test_concept` |
| FR-6 | VIP + freezeAccount 提案 → BLOCK（命中 vip-freeze-manual）；amount=1500000 且 approvalLevel=two_level → 该规则通过；amount=1500000 且无 approvalLevel → BLOCK（命中 large-amount-two-level） | `test_layers.py::test_rules`（3 用例） |
| FR-7 | Transaction 提案 procedure_state=execute 但 completed_steps=[detect] → BLOCK（跳步）；completed_steps=[detect,assess,propose,approve] → 通过；无 SOP 的 object_type（如 Account）→ 直接通过 | `test_layers.py::test_procedure`（3 用例） |
| FR-8 | tools 含 `bash.exec`（不在白名单）→ BLOCK；`graph.neighbors` 入参缺 `object_id` → BLOCK；入参 max_hops=5（超上限）→ BLOCK；合法入参 → 通过 | `test_layers.py::test_skill`（4 用例） |
| FR-9 | 概念层即 BLOCK 的提案，Verdict 的 `evaluated_layers == ["concept"]`（短路生效） | `test_engine.py::test_short_circuit` |
| FR-10 | AML 规则集加载零错误；`examples/harness_demo.py` 三个提案分别输出 ALLOW / BLOCK(rules) / BLOCK(skill) | `test_engine.py::test_aml_ruleset` + 运行示例 |
| FR-11 | 构造 preconditions 含 `aml.rule.not-exist` 的本体 → `check_preconditions` 返回该 ID；AML 本体（若 P03 已交付 templates/finance/aml/ontology.yaml）返回空列表；P03 未交付时用 testdata 本体样本 | `test_crossref.py` |
| FR-12 | `python -m agenticx_oag.harness check testdata/proposal_vip_freeze.json templates/finance/aml/harness.yaml` 输出 JSON 且 `decision=="BLOCK"` | 本地命令 |
