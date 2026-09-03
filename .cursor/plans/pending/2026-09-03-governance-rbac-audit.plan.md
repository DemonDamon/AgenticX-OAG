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

**Architecture:** 控制面 Python 库。策略（角色/授权）以 YAML 定义、编译为内存策略对象求值——对应 architecture.md §2「控制面编译、数据面执行」：本 plan 产出策略包与求值 API，P07 数据面后续可 watch 同一份策略 YAML（跨语言消费同一契约，Out of scope）。审计存储实现 P02 `AuditSink` Protocol（事件结构与 P07 逐迁移审计对齐：`action_id/from/to/actor/ts/payload_hash`），PG 为主、JSONL 兜底（借鉴 AgenticX 网关审计的 PG 主写 + JSONL 兜底模式）。决策溯源（DecisionRecord → PROV-O → 回放）只存储与组装，输入由调用方（P05 检索侧 / P07 执行侧）写入——本 plan 不依赖 P04/P05/P07 的实现，保持 DAG 上仅依赖 P02。

**Tech Stack:** Python 3.11 / pydantic v2 / pyyaml / rdflib（新增依赖）/ asyncpg（复用 P02 dev 环境 PG，可选 extra `graph` 之外新增 `governance` extra）/ pytest

---

## 背景与动机（证据链）

- `docs/enterprise-landing.md` §3.1 治理双维度：四权矩阵（权限维度）管「谁能做什么」——对应 Palantir Ontology 的安全维；§3.1 痛点表「AI 应用难治理，权限/安全/合规搞不定」→ 双维度治理。
- `docs/roadmap.md` Phase 3 交付物 2「四权矩阵鉴权」（查看/操作/审批/管理、基于 ObjectType 细粒度、OPA/Casbin 可选后端）、交付物 4「决策溯源 + 审计回放」（完整 provenance 链：数据 → 检索 → 推断 → 主张 → 决策 → Action；W3C PROV-O 兼容；审计回放重现任意决策完整上下文）。
- P02 plan 已锁定三个本 plan 消费的契约：`IDPProvider.verify_token` 返回 `{subject, roles, tenant_id, ...}`；`AuditSink.emit(event: dict)`；`ApprovalProvider.request/status`。
- P07 plan 的 `action_audit` 表与 `AuditEntry`（from_status/to_status/actor/payload_hash/ts_unix）是审计事件的产生源之一——本 plan 的 `AuditEvent` 模型与其字段一一对齐（统一 schema 见「关键实现意图」）。
- `docs/architecture.md` §4 存储选型：审计检索是企业刚需（PG FTS 起步 → OpenSearch）——本 plan PG 落库即满足 POC，OpenSearch 留后续。

## 需求定义

### FR（Functional Requirements）

- **FR-1 权限模型**：`agenticx_oag/governance/model.py` 定义 `Permission`（Literal `read|write|approve|admin`）、`Grant`（`object_type: str`（支持 `*`）、`permissions: list[Permission]`、`condition: Cond | None`）、`Role`（`id` + `grants`）、`RoleBinding`（`user_id` + `role_ids`）、`Decision`（`allowed: bool / matched_grant / reason / evaluated_at`）。`Cond` 复用 P08 的条件结构语义（`path/op/value`，path 相对对象属性 `props.*`）。
- **FR-2 策略 YAML**：`agenticx_oag/governance/policy.py` 加载校验 `policy.yaml`（pydantic，schema 见「关键实现意图」）。默认拒绝原则：无任何 grant 命中 → deny。
- **FR-3 策略引擎**：`engine.py` 的 `PolicyEngine(policy, bindings).check(user_id, object_type, permission, object_props=None) -> Decision`——求值顺序：① 汇总 user 的全部角色 grants；② 显式 `object_type` 匹配优先于 `*` 通配；③ 同一 grant 内 `permission` 必须显式列出（admin 不隐含其余三权，四权正交）；④ 带 `condition` 的 grant 仅当条件对 `object_props` 求值为真才命中；⑤ 命中任一 grant → allow（记录 matched_grant），否则 deny。
- **FR-4 角色绑定存储**：`RoleBindingStore` Protocol（`get_bindings(user_id) / put_binding(...)`）+ `JSONFileBindingStore`（`~/.agenticx_oag/bindings.json` 或环境变量 `OAG_GOVERNANCE_BINDINGS` 指定路径；文件不存在返回空绑定）。外部 IDP 对接由调用方先经 P02 `IDPProvider.verify_token` 取 roles，再以 `PolicyEngine.check_roles(roles, ...)` 重载入口传入（引擎两个入口：by user_id 走 Store、by roles 直评）。
- **FR-5 审计事件模型**：`model.py` 定义 `AuditEvent`（pydantic，字段与 P07 AuditEntry 对齐 + 通用扩展位，见「关键实现意图」）。
- **FR-6 AuditSink 实现**：`audit.py`——`JsonlAuditSink(path)` 与 `PgAuditSink(dsn)`，两者都实现 P02 `AuditSink` Protocol（`async emit(event: dict)`）。PgAuditSink 建表 `governance_audit`（DDL 见「关键实现意图」），写入失败降级写 JSONL（文件路径 `audit_fallback.jsonl`）并 log warning——审计不允许丢事件。`AuditQuery.filter(actor=..., action_id=..., decision_id=..., ts_from=..., ts_to=...) -> list[AuditEvent]`（JSONL 实现全扫；PG 实现走 SQL WHERE）。
- **FR-7 决策记录**：`replay.py` 定义 `DecisionRecord`（pydantic：`decision_id / question / actor / ts / evidence_ids / claims / pack_ref / proposal_id / action_id / outcome / ontology_ns`）+ `DecisionStore` Protocol + `JsonlDecisionStore` / `PgDecisionStore`（PG 表 `decision_records`）。`record_decision(dr)` 写入并同发一条 `AuditEvent(kind="decision")` 到注入的 AuditSink。
- **FR-8 PROV-O 导出**：`prov.py` 的 `export_prov_ttl(dr: DecisionRecord, audit_events: list[AuditEvent]) -> str`——映射规则见「关键实现意图」（question→Entity、retrieval/generation→Activity、actor→Agent、action→Activity，`prov:wasDerivedFrom / prov:wasGeneratedBy / prov:wasAssociatedWith / prov:used` 连接）。输出必须可被 rdflib `parse(format="turtle")` 回读。
- **FR-9 审计回放**：`replay.py` 的 `ReplayBundle`（`decision: DecisionRecord / evidence_timeline: list[AuditEvent] / action_history: list[AuditEvent] / prov_ttl: str`）+ `replay(decision_id, decision_store, audit_query) -> ReplayBundle`——按 ts 升序组装该决策的全部审计事件（`decision_id` 或 `action_id` 关联），内嵌 PROV-O 导出。这是「审计回放：重现任意决策完整上下文」的落地。
- **FR-10 AML 策略样例**：`templates/finance/aml/policy.yaml`（完整内容见「关键实现意图」）：analyst（只读 + 区域条件）、compliance_officer（读/写/审批）、admin（四权全量）。
- **FR-11 CLI**：`python -m agenticx_oag.governance` 支持 `check <user> <object_type> <permission> [--props '{}']` 与 `replay <decision_id>`，供 P10 Demo 与售前演示。

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
  ontology_ns TEXT NOT NULL DEFAULT ''
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

**Out of scope（no-scope-creep）：** 不实现 IDPProvider 的真实后端（OIDC/LDAP 对接留后续，引擎入口已接受 roles 直评）；不做 OPA/Casbin 适配器（自研轻量求值，roadmap 定位为可选后端）；不做 OpenSearch 审计检索（PG 起步）；不做 Go 数据面侧的策略执行（P07 后续独立 plan 消费同一 policy.yaml）；不做审批流引擎本体（ApprovalProvider 的内置实现在 P07 侧，本 plan 只管权限判定与审计）；不做审计 UI（P10/P11 消费 AuditQuery）。

## 验收标准（AC）

| FR | AC | 验证方式 |
|---|---|---|
| FR-2 | 非法 policy.yaml（未知 permission `delete`、grant 缺 object_type）→ `ValidationError` 且消息含字段路径 | `test_policy.py` |
| FR-3 | ① admin 对任意类型 admin 权 → allow；② analyst（仅 `*`+read）对 Customer write → deny（默认拒绝）；③ analyst 对 Customer read → allow（通配命中）；④ 带条件 grant：condition path `props.region` eq `CN`，对象 props region=US → deny、region=CN → allow；⑤ 四权正交：仅有 `[read]` grant 时 approve → deny | `test_engine.py`（≥5 用例） |
| FR-3 | `check_roles(roles=["analyst"], ...)` 与 `check(user_id→analyst)` 结果一致 | `test_engine.py::test_roles_entry` |
| FR-4 | 绑定文件不存在时 check 走空绑定 → deny 不抛错；put_binding 后 get 生效 | `test_engine.py::test_binding_store` |
| FR-5/6 | JsonlAuditSink emit 3 事件后 filter(actor=...) 命中 2；PG 断连（错误 DSN）时 emit 落 fallback JSONL 且返回/记录可观测降级信号 | `test_audit.py` |
| FR-6 | PgAuditSink 集成：emit → `governance_audit` 行数一致，字段 round-trip 相等（integration，docker PG） | `test_audit.py::test_pg` |
| FR-7 | record_decision 后：decision_store 可 get；AuditSink 收到 kind="decision" 事件且 decision_id 一致 | `test_replay.py` |
| FR-8 | export_prov_ttl 输出被 `rdflib.Graph().parse(data=ttl, format="turtle")` 解析无异常；图中 `prov:Activity` ≥2、`prov:Agent` ≥1、含至少一条 `prov:wasAssociatedWith`；action_id 非空时存在 `prov:wasInformedBy` 三元组 | `test_prov.py` |
| FR-9 | 构造 1 条 DecisionRecord + 5 条审计事件（3 条 decision 关联、2 条 action 关联）→ replay 返回 evidence_timeline 按时间升序、无重复、prov_ttl 非空 | `test_replay.py::test_replay_bundle` |
| FR-10 | AML policy.yaml 加载零错误；样例断言：compliance_officer 对 Transaction approve → allow、analyst 对 Transaction write → deny | `test_policy.py::test_aml_policy` |
| FR-11 | `python -m agenticx_oag.governance check analyst Customer read` 输出 JSON `allowed==true`；`... check analyst Customer write` 输出 `allowed==false` | 本地命令 |
