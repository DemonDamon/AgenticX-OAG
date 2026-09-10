---
name: "P09 治理权限维度：四权矩阵 RBAC + 审计存储 + PROV-O 决策溯源回放"
overview: "实现治理双维度的权限维度：四权矩阵（read/write/approve/admin × ObjectType）策略引擎、P02 AuditSink 契约的 PG/JSONL 实现、决策记录 PROV-O 导出与审计回放。"
todos: []
isProject: false
---

# P09 四权矩阵权限 + 审计治理 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
>
> Planned-with: glm 5.3
> Suggested-Impl-Model: 代码专精中档（策略求值是确定性逻辑、结构在 plan 已写全；PROV-O 映射需对照 W3C PROV 本体词汇表仔细写，勿自造 URI）

**Goal:** 落地治理双维度的**权限维度**（`docs/enterprise-landing.md` §3.1）：四权矩阵——查看（read）/ 操作（write）/ 审批（approve）/ 管理（admin），基于 ObjectType 细粒度授权；配套审计事件存储（实现 P02 `AuditSink` 契约）、决策溯源链记录与 PROV-O 导出、审计回放。与 P08（语义约束维度）正交：P08 管「Agent 该不该这么说/这么做」，P09 管「这个人/这个 Agent 有没有权看/动这个对象」。

**Architecture:** 控制面 Python 库。策略（角色/授权）以 YAML 定义、编译为内存策略对象求值——对应 architecture.md §2「控制面编译、数据面执行」：本 plan 产出策略包与求值 API，P07 数据面后续可 watch 同一份策略 YAML（跨语言消费同一契约，Out of scope）。条件授权使用 `ObjectProvider` 从可信数据层取得对象属性快照；HTTP/CLI 请求中的 `object_props` 只能作为本地演示输入，生产求值不得直接信任。审计存储实现 P02 `AuditSink` Protocol（事件结构与 P07 逐迁移审计对齐：`action_id/from/to/actor/ts/payload_hash`），PG 为主、JSONL 兜底（借鉴 AgenticX 网关审计的 PG 主写 + JSONL 兜底模式）。决策溯源（DecisionRecord → PROV-O → 回放）只存储与组装，输入由调用方（P05 检索侧 / P07 执行侧）写入——本 plan 不依赖 P04/P05/P07 的实现，保持 DAG 上仅依赖 P02。

**Tech Stack:** Python 3.11 / pydantic v2 / pyyaml / rdflib（新增依赖）/ asyncpg（复用 P02 dev 环境 PG，可选 extra `graph` 之外新增 `governance` extra）/ pytest

---

## 背景与动机（证据链）

- `docs/enterprise-landing.md` §3.1 治理双维度：四权矩阵（权限维度）管「谁能做什么」——对应 Palantir Ontology 的安全维；§3.1 痛点表「AI 应用难治理，权限/安全/合规搞不定」→ 双维度治理。
- `docs/roadmap.md` Phase 3 交付物 2「四权矩阵鉴权」（查看/操作/审批/管理、基于 ObjectType 细粒度、OPA/Casbin 可选后端）、交付物 4「决策溯源 + 审计回放」（完整 provenance 链：数据 → 检索 → 推断 → 主张 → 决策 → Action；W3C PROV-O 兼容；审计回放重现任意决策完整上下文）。
- P02 plan 已锁定三个本 plan 消费的契约：`IDPProvider.verify_token` 返回 `{subject, roles, tenant_id, ...}`；`AuditSink.emit(event: dict)`；`ApprovalProvider.request/status`。
- P07 plan 的 `action_audit` 表与 `AuditEntry`（from_status/to_status/actor/payload_hash/ts_unix）是审计事件的产生源之一——本 plan 的 `AuditEvent` 模型与其字段一一对齐（统一 schema 见「关键实现意图」）。
- `docs/architecture.md` §4 存储选型：审计检索是企业刚需（PG FTS 起步 → OpenSearch）——本 plan PG 落库即满足 POC，OpenSearch 留后续。

### 本体工程演进约束

依据项目多租户原则、NIST RBAC 与 W3C PROV-O，权限判断、规则判断和 Action 执行应形成一条可验证的决策链。P09 在既有 FR 基础上增加以下约束：

- 四权矩阵始终按 `subject × tenant × ObjectType/ObjectId × permission × condition` 求值，`read/write/approve/admin` 权限正交；一次权限求值中无授权 grant 命中则 deny。该规则只定义 P09 权限引擎的授权语义，不定义 P11 在权限服务不可用时的运行策略。`admin` 是否蕴含其他权限必须由策略显式声明，禁止代码隐式放大授权。
- 条件中的对象属性必须来自可信 `ObjectProvider` 或等价数据层快照，并绑定对象 ID、租户和版本；不得把请求体或 LLM Proposal 中的同名属性直接作为授权事实。
- P07 的三个受保护操作分别求值：Propose/Execute 检查对应主体的 `write`，Decide 检查审批主体的 `approve`。P08 ALLOW、参数 Schema 合法或持有网关 token 均不能替代这些授权结果；同一主体不能通过重复 Decide 满足 two-level 审批。
- 完成策略求值但无 grant 命中返回 `AUTHZ_DENIED`；策略、绑定或治理服务无法取得可信结果时返回/抛出 `GOVERNANCE_UNAVAILABLE`。二者必须分开审计，调用方不得把系统故障解释为用户无权限。
- `DecisionRecord` 的最小链路为 `retrieval → evidence → claim → rule verdict → proposal → authorization → approval → action transition → outcome`；每个节点保存稳定 ID、发生时间、主体、输入摘要哈希、ontology/rule/policy 版本和来源引用。
- PROV-O 映射应覆盖 Entity/Activity/Agent 及 `used`、`wasGeneratedBy`、`wasDerivedFrom`、`wasAssociatedWith`、`wasInformedBy`；自定义关系放在 OAG namespace，不能冒充标准 PROV-O 词汇。
- 证据写入时标注来源等级（原始记录/受控文档/推导结果/模型生成）与可信度；回放必须显示来源等级、缺失节点和版本不可用警告，不能把模型生成内容展示为已验证事实。
- 增补 AC：对象级条件授权与租户隔离；默认拒绝；同一决策按时间序完整回放；缺失证据/规则版本时可降级回放并显式报警；PROV Turtle 可由 rdflib 解析且关键边数量符合预期。

### 来源分级与适用边界

来源等级定义见 `docs/ontology-evolution-backlog.md`：

| 决策 | 来源等级 | 适用边界 |
|---|---|---|
| 无授权 grant 命中时 deny | S1/S2/S3 | 仅适用于 P09 收到完整求值输入并完成策略求值的情况 |
| 四权正交、admin 不隐含其他权限 | S1 | 项目既有治理设计 |
| tenant/ObjectId/condition 参与求值 | S1/S4 | 多租户是既有原则；对象级条件细化是待 Maintainer 确认的工程建议 |
| 权限服务不可用时如何处理读取 | S4 | 不属于 P09 策略求值结论，由 P11 的运行策略单独决定 |

## 需求定义

### FR（Functional Requirements）

- **FR-1 权限模型**：`agenticx_oag/governance/model.py` 定义 `Permission`（Literal `read|write|approve|admin`）、`Grant`（`tenant_id: str|*`、`object_type: str`（支持 `*`）、`object_ids: list[str] | None`、`permissions: list[Permission]`、`condition: Cond | None`）、`Role`（`id` + `grants`）、`RoleBinding`（`user_id` + `tenant_id` + `role_ids`）、`ObjectSnapshot`（`tenant_id/object_type/object_id/version/props`）和 `Decision`（`allowed: bool / matched_grant / reason_code / reason / evaluated_at / policy_version / snapshot_version`）。`Cond` 复用 P08 的条件结构语义（`path/op/value`，path 相对可信快照的 `props.*`）。
- **FR-2 策略 YAML**：`agenticx_oag/governance/policy.py` 加载校验 `policy.yaml`（pydantic，schema 见「关键实现意图」）。默认拒绝原则：无任何 grant 命中 → deny。
- **FR-3 策略引擎**：`engine.py` 的 `PolicyEngine(policy, bindings, object_provider).check(user_id, tenant_id, object_type, permission, object_id=None) -> Decision`——求值顺序：① 只汇总同 tenant 的角色 grants；② 显式对象 ID、`object_type` 匹配优先于通配；③ 同一 grant 内 `permission` 必须显式列出（admin 不隐含其余三权，四权正交）；④ 带 `condition` 的 grant 通过 `ObjectProvider.get_snapshot(tenant_id, object_type, object_id)` 取得绑定对象、租户和版本的可信属性快照，仅当条件求值为真才命中；⑤ 命中任一 grant → allow（记录 matched_grant 与 snapshot_version），否则以 `AUTHZ_DENIED` 默认拒绝。新增 `check_action_operation(operation=propose|approve|execute, ...)` 映射为 `write|approve|write`，供 P07 `GateAuthorizer` 适配层消费；策略、绑定或对象属性后端不可用时抛 `PolicyUnavailableError(reason_code="GOVERNANCE_UNAVAILABLE")`，不返回普通 deny。可额外提供显式命名的 `check_with_snapshot(...)` 纯函数供单测和本地 CLI 使用，但生产适配器不得把客户端请求体或 Proposal 属性直接包装成可信快照。
- **FR-4 角色绑定存储**：`RoleBindingStore` Protocol（`get_bindings(user_id) / put_binding(...)`）+ `JSONFileBindingStore`（`~/.agenticx_oag/bindings.json` 或环境变量 `OAG_GOVERNANCE_BINDINGS` 指定路径；文件不存在返回空绑定）。外部 IDP 对接由调用方先经 P02 `IDPProvider.verify_token` 取 roles，再以 `PolicyEngine.check_roles(roles, ...)` 重载入口传入（引擎两个入口：by user_id 走 Store、by roles 直评）。
- **FR-5 审计事件模型**：`model.py` 定义 `AuditEvent`（pydantic，字段与 P07 AuditEntry 对齐 + `reason_code/rule_ids/evidence_ids/ontology_version/rule_set_version/policy_version/source_level/confidence` 通用扩展位，见「关键实现意图」）。来源等级限定为 `source_record|controlled_document|derived|model_generated`。
- **FR-6 AuditSink 实现**：`audit.py`——`JsonlAuditSink(path)` 与 `PgAuditSink(dsn)`，两者都实现 P02 `AuditSink` Protocol（`async emit(event: dict)`）。PgAuditSink 建表 `governance_audit`（DDL 见「关键实现意图」），写入失败降级写 JSONL（文件路径 `audit_fallback.jsonl`）并 log warning——审计不允许丢事件。`AuditQuery.filter(actor=..., action_id=..., decision_id=..., ts_from=..., ts_to=...) -> list[AuditEvent]`（JSONL 实现全扫；PG 实现走 SQL WHERE）。
- **FR-7 决策记录**：`replay.py` 定义 `DecisionNode`（`node_id/kind/ts/actor/input_hash/source_refs/ontology_version/rule_set_version/policy_version/detail`）与 `DecisionRecord`（`decision_id / question / actor / ts / evidence_ids / claims / pack_ref / proposal_id / action_id / outcome / ontology_ns / nodes`）。`nodes.kind` 允许 `retrieval|evidence|claim|rule_verdict|proposal|authorization|approval|action_transition|outcome`。配套 `DecisionStore` Protocol + `JsonlDecisionStore` / `PgDecisionStore`；`record_decision(dr)` 写入并同发一条 `AuditEvent(kind="decision")`。
- **FR-8 PROV-O 导出**：`prov.py` 的 `export_prov_ttl(dr: DecisionRecord, audit_events: list[AuditEvent]) -> str`——映射规则见「关键实现意图」（Entity/Activity/Agent 与 `used / wasGeneratedBy / wasDerivedFrom / wasAssociatedWith / wasInformedBy`）。自定义节点属性仅使用 OAG namespace，输出必须可被 rdflib 回读。
- **FR-9 审计回放**：`replay.py` 的 `ReplayBundle`（`decision / evidence_timeline / action_history / warnings / prov_ttl`）+ `replay(...)`——按 ts 升序组装该决策的全部审计事件。证据或版本缺失时保留可用链路并写稳定 warning，不伪造节点或静默失败。
- **FR-10 AML 策略样例**：`templates/finance/aml/policy.yaml`（完整内容见「关键实现意图」）：analyst（只读 + 区域条件）、compliance_officer（读/写/审批）、admin（四权全量）。
- **FR-11 CLI**：`python -m agenticx_oag.governance` 支持 `check <user> <object_type> <permission> [--snapshot '{}']` 与 `replay <decision_id>`，供 P10 Demo 与售前演示；输出必须标注 `snapshot_source=demo_cli`，避免把手工属性误认成生产授权事实。

### NFR（Non-Functional Requirements）

- **NFR-1** `PolicyEngine.check`（≤50 grants）P95 < 1ms（纯内存）。
- **NFR-2** 审计写入不可丢：PG 失败必须落 JSONL 且不留静默（返回值/日志二选一可观测）。
- **NFR-3** 策略 YAML 与绑定 JSON 是契约文件：变更需版本递增（policy.version）。

## 精确落点

| 改动 | 路径 |
|---|---|
| 模型 | `agenticx_oag/governance/model.py`（新建） |
| 策略 | `agenticx_oag/governance/policy.py`（新建） |
| 引擎 | `agenticx_oag/governance/engine.py`（新建） |
| 对象快照 | `agenticx_oag/governance/object_provider.py`（新建：`ObjectProvider` Protocol + 内存测试实现） |
| 审计 | `agenticx_oag/governance/audit.py`（新建） |
| 溯源/回放 | `agenticx_oag/governance/replay.py`（新建） |
| PROV-O | `agenticx_oag/governance/prov.py`（新建） |
| CLI | `agenticx_oag/governance/__main__.py`（新建） |
| 策略样例 | `templates/finance/aml/policy.yaml`（新建） |
| 依赖 | `pyproject.toml`：核心依赖增 `rdflib>=7`；可选 extra 增 `governance = ["asyncpg"]`（修改） |
| 测试 | `tests/governance/test_policy.py`、`test_engine.py`、`test_audit.py`、`test_replay.py`、`test_prov.py`（新建） |

## 关键实现意图

**policy.yaml（templates/finance/aml/policy.yaml 完整内容）**：

```yaml
namespace: finance.aml
version: 1.0.0
roles:
  - id: analyst
    grants:
      - {object_type: "*", permissions: [read]}
      - {object_type: "Transaction", permissions: [read],
         condition: {path: props.region, op: eq, value: CN}}
  - id: compliance_officer
    grants:
      - {object_type: "*", permissions: [read, write, approve]}
  - id: admin
    grants:
      - {object_type: "*", permissions: [read, write, approve, admin]}
default: deny
```

注意：analyst 的第一条 grant（`*` + read）与第二条（Transaction + read + 条件）并存时，`*` grant 无条件命中——**条件收紧必须靠显式收紧通配**。求值语义按 FR-3 ④：本样例中 analyst 对任意对象类型可 read（`*` grant 生效）；第二条演示「带条件 grant」形态。若要表达「仅 CN 区域可见」，策略应写成 `*` 无 read + `Transaction` 带条件 read。此语义在 `policy.py` docstring 中显式写明，防止实施误解。

**AuditEvent 统一 schema（对齐 P07 AuditEntry + 扩展）**：

```python
class AuditEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: uuid4().hex)
    kind: str                      # "action_transition" | "decision" | "access"
    ts: str                        # ISO8601
    actor: str
    tenant_id: str = ""
    action_id: str | None = None   # P07 事件必有
    decision_id: str | None = None
    from_status: str | None = None # P07 事件
    to_status: str | None = None
    payload_hash: str | None = None
    object_type: str | None = None
    reason_code: str = ""
    rule_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    ontology_version: str = ""
    rule_set_version: str = ""
    policy_version: str = ""
    source_level: Literal["source_record", "controlled_document", "derived", "model_generated"] | None = None
    confidence: float | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
```

P07 侧事件字典（`action_id/from/to/actor/ts/payload_hash`）经 `AuditEvent.from_action_event(dict)` 归一化（`from`→`from_status`，`to`→`to_status`）。

**PG DDL（PgAuditSink / PgDecisionStore，EnsureSchema 幂等）**：

```sql
CREATE TABLE IF NOT EXISTS governance_audit (
  event_id    TEXT PRIMARY KEY,
  kind        TEXT NOT NULL,
  ts          TIMESTAMPTZ NOT NULL,
  actor       TEXT NOT NULL,
  tenant_id   TEXT NOT NULL DEFAULT '',
  action_id   TEXT,
  decision_id TEXT,
  from_status TEXT,
  to_status   TEXT,
  payload_hash TEXT,
  object_type TEXT,
  reason_code TEXT NOT NULL DEFAULT '',
  rule_ids TEXT[] NOT NULL DEFAULT '{}',
  evidence_ids TEXT[] NOT NULL DEFAULT '{}',
  ontology_version TEXT NOT NULL DEFAULT '',
  rule_set_version TEXT NOT NULL DEFAULT '',
  policy_version TEXT NOT NULL DEFAULT '',
  source_level TEXT,
  confidence DOUBLE PRECISION,
  detail      JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_gov_audit_action ON governance_audit(action_id, ts);
CREATE INDEX IF NOT EXISTS idx_gov_audit_decision ON governance_audit(decision_id, ts);

CREATE TABLE IF NOT EXISTS decision_records (
  decision_id TEXT PRIMARY KEY,
  question    TEXT NOT NULL,
  actor       TEXT NOT NULL,
  ts          TIMESTAMPTZ NOT NULL,
  evidence_ids TEXT[] NOT NULL DEFAULT '{}',
  claims      TEXT[] NOT NULL DEFAULT '{}',
  pack_ref    TEXT,
  proposal_id TEXT,
  action_id   TEXT,
  outcome     TEXT,
  ontology_ns TEXT NOT NULL DEFAULT '',
  nodes       JSONB NOT NULL DEFAULT '[]'
);
```

**PROV-O 映射（prov.py，URI 规则固定）**：

```python
# 命名空间
OAG = Namespace("https://agenticx.dev/oag/")     # 资源前缀
PROV = Namespace("http://www.w3.org/ns/prov#")

# 映射（URI 末段用 decision_id / evidence_id / action_id 保证可寻址回放）
question   → OAG[f"question-{dr.decision_id}"]   a prov:Entity
evidence   → OAG[f"evidence-{eid}"]              a prov:Entity
retrieval  → OAG[f"retrieval-{dr.decision_id}"]  a prov:Activity ; prov:used question ; prov:generatedEvidence? → prov:used 与 prov:wasGeneratedBy 连接
claim      → OAG[f"claim-{cid}"]                 a prov:Entity ; prov:wasDerivedFrom evidence
decision   → OAG[f"decision-{dr.decision_id}"]   a prov:Activity ; prov:used claim(s) ; prov:wasAssociatedWith actor
actor      → OAG[f"agent-{dr.actor}"]            a prov:Agent
action     → OAG[f"action-{dr.action_id}"]       a prov:Activity ; prov:wasInformedBy decision（action_id 非空时）
# 审计事件附时间：action Activity 上 prov:startedAtTime / prov:endedAtTime 取首尾事件 ts
```

**replay 组装（伪代码）**：

```python
async def replay(decision_id, decision_store, audit_query) -> ReplayBundle:
    dr = await decision_store.get(decision_id)
    events = await audit_query.filter(decision_id=decision_id)
    if dr.action_id:
        events += await audit_query.filter(action_id=dr.action_id)
    events = sorted(set(events), key=lambda e: e.ts)          # 去重（跨两键关联）+ 时间序
    prov_ttl = export_prov_ttl(dr, [e for e in events if e.kind == "action_transition"])
    return ReplayBundle(decision=dr, evidence_timeline=events, action_history=..., prov_ttl=prov_ttl)
```

## In scope / Out of scope

**In scope：** FR-1~FR-11 全部；`tests/governance/testdata/` 策略与事件样本。

**Out of scope（no-scope-creep）：** 不实现 IDPProvider 的真实后端（OIDC/LDAP 对接留后续，引擎入口已接受 roles 直评）；不做 OPA/Casbin 适配器（自研轻量求值，roadmap 定位为可选后端）；不做 OpenSearch 审计检索（PG 起步）；不在 Go 数据面重复实现策略语义，也不新增跨服务传输协议（P07 只强制 `GateAuthorizer` 接口）；不做审批流引擎本体（ApprovalProvider 的内置实现在 P07 侧，本 plan 只判断审批主体权限并记录审计）；不做审计 UI（P10/P11 消费 AuditQuery）。

## 验收标准（AC）

| FR | AC | 验证方式 |
|---|---|---|
| FR-2 | 非法 policy.yaml（未知 permission `delete`、grant 缺 object_type）→ `ValidationError` 且消息含字段路径 | `test_policy.py` |
| FR-3 | 覆盖显式 allow、默认 deny、条件 grant、四权正交、跨 tenant deny、object_ids 不含目标时 deny；所有 deny 有稳定 reason_code；篡改请求体或 Proposal 中与条件同名的属性不能改变 ObjectProvider 快照及授权结果 | `test_engine.py`（≥8 用例，含 `test_untrusted_props_cannot_override_snapshot`） |
| FR-3 | `check_action_operation` 对 propose/approve/execute 分别映射 write/approve/write；无 approve 权限不能批准；后端不可用抛 `PolicyUnavailableError/GOVERNANCE_UNAVAILABLE`，与无 grant 的 `AUTHZ_DENIED` 不同 | `test_engine.py::test_action_operation_mapping` + `test_policy_unavailable_is_not_deny` |
| FR-3 | `check_roles(roles=["analyst"], ...)` 与 `check(user_id→analyst)` 结果一致 | `test_engine.py::test_roles_entry` |
| FR-4 | 绑定文件不存在时 check 走空绑定 → deny 不抛错；put_binding 后 get 生效 | `test_engine.py::test_binding_store` |
| FR-5/6 | JsonlAuditSink emit 3 事件后 filter(actor=...) 命中 2；PG 断连（错误 DSN）时 emit 落 fallback JSONL 且返回/记录可观测降级信号 | `test_audit.py` |
| FR-6 | PgAuditSink 集成：emit → `governance_audit` 行数一致，字段 round-trip 相等（integration，docker PG） | `test_audit.py::test_pg` |
| FR-7 | record_decision 后：decision_store 可 get；AuditSink 收到 kind="decision" 事件且 decision_id 一致 | `test_replay.py` |
| FR-8 | export_prov_ttl 输出被 `rdflib.Graph().parse(data=ttl, format="turtle")` 解析无异常；图中 `prov:Activity` ≥2、`prov:Agent` ≥1、含至少一条 `prov:wasAssociatedWith`；action_id 非空时存在 `prov:wasInformedBy` 三元组 | `test_prov.py` |
| FR-9 | 完整九节点 DecisionRecord 回放按时间升序且无重复；删除 evidence 与 rule version 后仍返回其余链路，warnings 精确列出缺失项，prov_ttl 非空 | `test_replay.py::test_replay_bundle` + `test_replay_missing_refs` |
| FR-10 | AML policy.yaml 加载零错误；样例断言：compliance_officer 对 Transaction approve → allow、analyst 对 Transaction write → deny | `test_policy.py::test_aml_policy` |
| FR-11 | `python -m agenticx_oag.governance check analyst Customer read` 输出 JSON `allowed==true` 且标注 demo snapshot 来源；`... check analyst Customer write` 输出 `allowed==false` | 本地命令 |
