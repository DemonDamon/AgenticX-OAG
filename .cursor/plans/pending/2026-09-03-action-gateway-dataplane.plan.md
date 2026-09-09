---
name: "P07 Action Gateway：Go 数据面行动网关（状态机+幂等+回滚+审计）"
overview: "实现数据面 Go 服务的 Action 运行时：gRPC 服务、生命周期状态机、幂等执行、审批编排、SQL/Cypher 执行器与回滚、审计事件流。消费 P02 proto 契约并新增 action.proto。"
todos: []
isProject: false
---

# P07 Action Gateway（Go 数据面）Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
>
> Planned-with: glm 5.3
> Suggested-Impl-Model: 代码专精中档偏强（Go 状态机与 DB 事务一致性需严谨；proto 与 SQL 契约已在 plan 写全，但并发/幂等细节需实施模型自行保证正确）

**Goal:** 落地 L5 执行层的核心——Palantir 式 Action Gateway：Action 生命周期「提案 → 审批 → 执行 → 验证 → 归档」全链路，带幂等、回滚、逐迁移审计。这是「甩开 Semantica」的执行闭环能力，也是 P10 治理演示与 P11 Workshop Action 按钮的数据面后端。

**Architecture:** 控制面 Python / 数据面 Go 的语言分界落在本 plan（architecture.md §2-§3）：Go 服务消费 P02 的 `ontology.proto`（ActionType 定义）生成 Go 绑定，本 plan 新增 `action.proto` 定义运行时协议。状态机为单一事实：所有迁移走 `transition()` 函数（合法性表驱动），每次迁移写 PG `action_audit` 表（事件溯源语义）。执行器与审批源均为 Go interface，默认实现内置（SQL 模板执行器 + PG 审批单），企业差异（外部审批系统/工单）留在接口后面。

**Tech Stack:** Go 1.22 / protobuf + protoc-gen-go + protoc-gen-go-grpc / pgx v5（PG+AGE 同库直连）/ testify / docker-compose（复用 P02 的 dev 环境）

---

## 背景与动机（证据链）

- `docs/architecture.md` §2 总体架构：数据面（Go）明确列出「Action Gateway（事务/幂等）」；§2 关键模式「控制面编译、数据面执行」——本体 schema/审批策略在控制面定义（P03 的 `ActionType.approval_policy`），数据面 watch 执行。本 plan 落地数据面第一块。
- `docs/architecture.md` §3 语言选型：Action Gateway、实时规则引擎归 Go——写路径吞吐 Go 10-20k TPS vs Python 2-5k TPS。
- `docs/roadmap.md` Phase 3 交付物 1：Action 生命周期（提案→审批→执行→验证→归档）、幂等性（唯一 ID 重复执行无副作用）、回滚机制、沙箱执行。验收标准：bank-aml 场景走完「可疑交易识别 → 风险评估 → 冻结提案 → 审批 → 执行冻结 → 审计记录」全链路。
- P02 plan 已锁定：`AuditSink.emit` 的事件结构与本 plan 对齐（`action_id/from/to/actor/ts/payload_hash`）；P03 的 `ActionType.preconditions` 是规则 ID 引用（P08 Harness 校验用，本 plan 不校验语义，只透传）。
- 现状：仓库无任何 Go 代码。本 plan 建立第一个 Go module。

### 本体工程演进约束

本节依据项目 Phase 3 路线、控制面/数据面分离原则和公开的幂等设计方法，补充 P07 的实施约束。

- `ActionType` 不只是 SQL 模板名：以 P02 `ontology.proto` 中的 ActionType 为定义源，在 `action.proto` 的提案快照、`action_instances` 与 `templates/finance/aml/actions.yaml` 中显式承载或解析 `preconditions`、`postconditions`、`state_changes`、`side_effects`、`idempotency_scope` 与 `compensation_action`。这些字段必须带 `ontology_version/action_contract_version`，禁止只藏在执行器代码中。
- `action_id` 继续作为数据库主键和协议幂等键，由调用方生成、网关按 `action_type + target_object_id + idempotency_scope + canonical(parameters_json)` 校验其载荷指纹。相同 action_id、相同指纹是安全重放；相同 action_id、不同指纹返回 `AlreadyExists`/冲突错误且零副作用。
- 执行前校验前置条件，执行后校验后置条件与声明的状态变化；后置条件失败必须进入 FAILED，再依据 `compensation_action` 或 `rollback_sql` 补偿，不能把“SQL 返回成功”直接等价为业务成功。
- 每次审批、规则判断、迁移、执行和补偿都记录 `reason_code`、`rule_ids`、`evidence_ids` 与主体信息，使 P09 能解释“为何允许/拒绝/回滚”，并能沿同一 action 重放完整决策链。
- 增补契约/存储/执行器测试：Action 字段 round-trip；同 action_id 不同参数冲突；同幂等键并发只执行一次；前置条件失败零副作用；后置条件失败触发补偿；无补偿能力时保留可人工处置的 FAILED 状态。

## 需求定义

### FR（Functional Requirements）

- **FR-1 Go module 骨架**：`dataplane/go.mod`（module `github.com/agenticx/oag-dataplane`，Go 1.22，依赖仅 `google.golang.org/grpc`、`google.golang.org/protobuf`、`github.com/jackc/pgx/v5`）。目录：`dataplane/cmd/gateway/`（入口）、`dataplane/internal/{action,store,executor,approval,audit,auth}/`、`dataplane/proto/`。
- **FR-2 action.proto 契约**：`proto/agenticx_oag/action/v1/action.proto`（完整定义见「关键实现意图」），`ActionProposal` 除调用参数外携带 `ontology_version / action_contract_version / action_contract_json / idempotency_scope`，其中 contract JSON 固化本次执行解析到的前置/后置条件、状态变化、副作用与补偿声明。服务 `ActionGateway` 含 `Propose / Decide / Execute / GetStatus` 四个 RPC。`make proto-go` 生成 Go 绑定到 `dataplane/proto/gen/`（提交入库，幂等）。
- **FR-3 状态机**：`internal/action/machine.go` 定义 9 态状态机与合法迁移表（见「关键实现意图」）。所有状态变更经 `transition(actionID, to, actor)`，非法迁移返回 `ErrIllegalTransition`（不落库）。
- **FR-4 PG 存储**：`internal/store/pg.go` 建表 `action_instances`（`action_id` 主键即幂等键，保存请求指纹与 Action 契约快照）与 `action_audit`（事件溯源，保存原因、规则和证据引用）。DDL 见「关键实现意图」，由 `store.EnsureSchema()` 在启动时执行（`CREATE TABLE IF NOT EXISTS`）。
- **FR-5 幂等**：`action_id` 为协议幂等键，入库同时保存 `request_fingerprint = sha256(action_type + target_object_id + idempotency_scope + canonical(parameters_json))`。重复 `Propose` 同一 `action_id` 且指纹一致 → 返回已存在记录且 `already_exists=true`，不重复执行、不重复审计；同一 `action_id` 但指纹不同 → 返回 `AlreadyExists`/冲突错误且不泄露原参数。
- **FR-6 审批编排**：按 `ActionType.approval_policy`（从 P02 proto 的本体定义加载，控制面传入本体 JSON）路由——`none`：Propose 后自动进入 APPROVED；`single`：进入 PENDING_APPROVAL，`Decide(approve=true)` 一次即 APPROVED；`two_level`：需两次不同 approver 的 `Decide(approve=true)`，任一 `Decide(approve=false)` → REJECTED 终态。
- **FR-7 执行器**：`internal/executor/` 定义 `Executor` interface（`Execute` / `Rollback`）。内置 `TemplateExecutor`：从 `templates/finance/aml/actions.yaml` 读 action_type → SQL 模板映射（模板可为普通 SQL 或 AGE 的 `SELECT * FROM cypher(...)` 包装 SQL，PG+AGE 同库直跑），参数占位符 `$1` 绑定 `parameters_json` 解析值。执行前运行只读 `precondition_sql`，执行后运行 `postcondition_sql`；任一条件不满足均记录稳定 `reason_code`。执行和后置条件均成功 → SUCCEEDED 并写 `result_json`；失败 → FAILED；再调用 `compensation_action` 或 `rollback_sql`（配置存在时成功补偿 → ROLLED_BACK；未配置则停在 FAILED）。
- **FR-8 审计**：每次状态迁移写一条 `action_audit`（from/to/actor/payload_hash/reason_code/rule_ids/evidence_ids/ts）；`GetStatus` 返回记录含迁移历史。审计即事件流，供 P09 审计查询与 P10 溯源面板消费。
- **FR-9 gRPC 服务**：`cmd/gateway/main.go` 启动 gRPC server（默认 `:7570`），`Propose` 前经 `auth.Authorizer` interface 校验 actor token（默认 `StaticTokenAuth`，token 从环境变量 `OAG_GATEWAY_TOKEN` 读；P09 完成后可替换实现，接口已留）。健康检查 `grpc_health_v1`。
- **FR-10 首个 Action 模板**：`templates/finance/aml/actions.yaml` 定义 `freezeAccount`（`UPDATE customer SET status='frozen', updated_at=now() WHERE id=$1`，rollback `UPDATE customer SET status='active' WHERE id=$1`）与 `flagTransaction`（无 rollback，演示 FAILED 停留路径）。

### NFR（Non-Functional Requirements）

- **NFR-1** `Propose` + `Execute`（approval=none）在本地 docker PG 下端到端 P95 < 50ms（不含审批等待）。
- **NFR-2** 状态机迁移与审计写入在同一 PG 事务中（迁移成功但审计缺失视为 bug）。
- **NFR-3** 单二进制交付：`go build ./cmd/gateway` 产出无 CGO 依赖二进制（architecture.md §3：静态编译对 10 企业交付友好）。

## 精确落点

| 改动 | 路径 |
|---|---|
| Proto | `proto/agenticx_oag/action/v1/action.proto`（新建） |
| Go 绑定 | `dataplane/proto/gen/actionv1/`（生成后提交） |
| Module | `dataplane/go.mod`、`dataplane/go.sum`（新建） |
| 入口 | `dataplane/cmd/gateway/main.go`（新建） |
| 状态机 | `dataplane/internal/action/machine.go`（新建） |
| 服务实现 | `dataplane/internal/action/service.go`（新建，gRPC handler + 编排） |
| 存储 | `dataplane/internal/store/pg.go`、`dataplane/internal/store/schema.sql`（新建） |
| 执行器 | `dataplane/internal/executor/executor.go`、`dataplane/internal/executor/template.go`（新建） |
| 审批 | `dataplane/internal/approval/policy.go`（新建） |
| 鉴权 | `dataplane/internal/auth/auth.go`（新建） |
| Action 模板 | `templates/finance/aml/actions.yaml`（新建，与 P03 的 ontology.yaml 同目录） |
| 构建 | 根 `Makefile` 增 `proto-go`、`gateway` 目标 |
| 测试 | `dataplane/internal/action/machine_test.go`、`service_test.go`、`executor/template_test.go`、`testdata/`（新建） |

## 关键实现意图

**action.proto（完整契约，逐字段照写）**：

```protobuf
syntax = "proto3";
package agenticx_oag.action.v1;

enum ActionStatus {
  ACTION_STATUS_UNSPECIFIED = 0;
  ACTION_STATUS_PROPOSED = 1;
  ACTION_STATUS_PENDING_APPROVAL = 2;
  ACTION_STATUS_APPROVED = 3;
  ACTION_STATUS_REJECTED = 4;
  ACTION_STATUS_EXECUTING = 5;
  ACTION_STATUS_SUCCEEDED = 6;
  ACTION_STATUS_FAILED = 7;
  ACTION_STATUS_ROLLED_BACK = 8;
  ACTION_STATUS_ARCHIVED = 9;
}

message ActionProposal {
  string action_id = 1;        // 调用方生成，全局唯一，幂等键
  string action_type = 2;      // 本体 ActionType.api_name
  string object_type = 3;
  string target_object_id = 4;
  string parameters_json = 5;  // JSON 编码；字段由 ActionType.parameters 定义
  string actor = 6;            // 发起者（user id 或 agent id）
  string justification = 7;    // 提案依据（引用 P05 主张 ID / 证据 ID）
  string ontology_version = 8;
  string action_contract_version = 9;
  string action_contract_json = 10; // resolved snapshot: pre/post/state changes/side effects/compensation
  string idempotency_scope = 11;
}

message ActionRecord {
  string action_id = 1;
  ActionStatus status = 2;
  string result_json = 3;
  string error = 4;
  int64 created_at_unix = 5;
  int64 updated_at_unix = 6;
  repeated AuditEntry history = 7;
}

message AuditEntry {
  string from_status = 1;
  string to_status = 2;
  string actor = 3;
  string payload_hash = 4;
  int64 ts_unix = 5;
  string reason_code = 6;
  repeated string rule_ids = 7;
  repeated string evidence_ids = 8;
}

message ProposeRequest { ActionProposal proposal = 1; }
message ProposeResponse { ActionRecord record = 1; bool already_exists = 2; }
message DecideRequest { string action_id = 1; string approver = 2; bool approve = 3; string comment = 4; }
message ExecuteRequest { string action_id = 1; string caller = 2; }
message GetStatusRequest { string action_id = 1; }

service ActionGateway {
  rpc Propose(ProposeRequest) returns (ProposeResponse);
  rpc Decide(DecideRequest) returns (ActionRecord);
  rpc Execute(ExecuteRequest) returns (ActionRecord);
  rpc GetStatus(GetStatusRequest) returns (ActionRecord);
}
```

**状态机合法迁移表**（表驱动，非法组合一律拒绝）：

```go
var transitions = map[ActionStatus][]ActionStatus{
    PROPOSED:          {PENDING_APPROVAL, APPROVED},      // 后者：approval_policy=none 自动放行
    PENDING_APPROVAL:  {APPROVED, REJECTED},
    APPROVED:          {EXECUTING},
    EXECUTING:         {SUCCEEDED, FAILED},
    FAILED:            {ROLLED_BACK},                     // 仅当模板配置 rollback_sql
    SUCCEEDED:         {ARCHIVED},
    ROLLED_BACK:       {ARCHIVED},
    REJECTED:          {},                                 // 终态
    ARCHIVED:          {},                                 // 终态
}
```

**PG DDL（schema.sql，启动幂等）**：

```sql
CREATE TABLE IF NOT EXISTS action_instances (
  action_id        TEXT PRIMARY KEY,
  action_type      TEXT NOT NULL,
  object_type      TEXT NOT NULL,
  target_object_id TEXT NOT NULL,
  parameters_json  JSONB NOT NULL DEFAULT '{}',
  actor            TEXT NOT NULL,
  justification    TEXT NOT NULL DEFAULT '',
  ontology_version TEXT NOT NULL,
  action_contract_version TEXT NOT NULL,
  action_contract_json JSONB NOT NULL,
  idempotency_scope TEXT NOT NULL DEFAULT '',
  request_fingerprint TEXT NOT NULL,
  status           TEXT NOT NULL,
  approval_policy  TEXT NOT NULL,
  approval_count   INT NOT NULL DEFAULT 0,      -- two_level 需累加到 2
  result_json      JSONB,
  error            TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS action_audit (
  id           BIGSERIAL PRIMARY KEY,
  action_id    TEXT NOT NULL,
  from_status  TEXT NOT NULL,
  to_status    TEXT NOT NULL,
  actor        TEXT NOT NULL,
  payload_hash TEXT NOT NULL,                  -- sha256(parameters_json)
  reason_code  TEXT NOT NULL DEFAULT '',
  rule_ids     TEXT[] NOT NULL DEFAULT '{}',
  evidence_ids TEXT[] NOT NULL DEFAULT '{}',
  ts           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_action ON action_audit(action_id, ts);
```

**actions.yaml（模板格式）**：

```yaml
namespace: finance.aml
actions:
  freezeAccount:
    sql: "UPDATE customer SET status = 'frozen', updated_at = now() WHERE id = $1"
    precondition_sql: "SELECT status = 'active' FROM customer WHERE id = $1"
    postcondition_sql: "SELECT status = 'frozen' FROM customer WHERE id = $1"
    rollback_sql: "UPDATE customer SET status = 'active' WHERE id = $1"
    state_changes: [{field: status, from: active, to: frozen}]
    side_effects: [customer_status_write]
    idempotency_scope: target
    compensation_action: unfreezeAccount
    params: ["target_object_id"]
  flagTransaction:
    sql: "UPDATE transaction SET flagged = true WHERE id = $1"
    rollback_sql: null
    params: ["target_object_id"]
```

**迁移+审计同事务**（伪代码，正确性关键）：

```go
func (s *Service) transition(ctx context.Context, actionID string, to ActionStatus, actor string) (*ActionRecord, error) {
    tx, _ := s.pool.Begin(ctx)
    defer tx.Rollback(ctx)
    rec, err := s.lockAndLoad(ctx, tx, actionID)   // SELECT ... FOR UPDATE，防并发迁移
    if err != nil { return nil, err }
    if !legal(rec.Status, to) { return nil, ErrIllegalTransition }
    s.updateStatus(ctx, tx, rec, to)
    s.insertAudit(ctx, tx, actionID, rec.Status, to, actor, rec.PayloadHash)
    if err := tx.Commit(ctx); err != nil { return nil, err }
    return rec, nil
}
```

**Makefile 增补**：

```makefile
proto-go:
	cd dataplane && protoc --go_out=. --go_opt=module=github.com/agenticx/oag-dataplane \
	  --go-grpc_out=. --go-grpc_opt=module=github.com/agenticx/oag-dataplane \
	  -I ../proto ../proto/agenticx_oag/ontology/v1/ontology.proto ../proto/agenticx_oag/action/v1/action.proto

gateway:
	cd dataplane && go build -o bin/gateway ./cmd/gateway
```

## In scope / Out of scope

**In scope：** FR-1~FR-10 全部；`dataplane/.gitignore`（bin/）；CI 增 Go job（`.github/workflows/ci.yml` 增 `cd dataplane && go vet ./... && go test ./...`）。

**Out of scope（no-scope-creep）：** 不实现 Harness 语义校验（P08——本 plan 只透传 `justification` 字符串）；不做 P09 的 RBAC 决策（`Authorizer` 接口默认静态 token）；不做 Kafka 事件发布（`EventBus` 留接口位，Out）；不做沙箱执行（roadmap 提及的复用 AgenticX `safety/`，后续独立 plan）；不做 Ingestion Worker / WebSocket Hub（architecture.md 数据面其他组件）；不消费 P03 的 YAML（本体定义由调用方以 proto 消息传入，格式互不依赖，保证 P07 与 P03 可并行）。

## 验收标准（AC）

| FR | AC | 验证方式 |
|---|---|---|
| FR-1 | `cd dataplane && go build ./... && go vet ./...` 零错误 | 本地命令 |
| FR-2 | `make proto-go` 后连续执行两次 `git diff` 为空；生成代码含 `ActionGatewayClient`，ActionProposal 契约快照字段和 AuditEntry 解释字段可 round-trip | 本地命令 + proto round-trip 单测 |
| FR-3 | 合法迁移全部通过；`SUCCEEDED → PENDING_APPROVAL`、`REJECTED → APPROVED` 等非法迁移返回 `ErrIllegalTransition` 且 DB 状态不变 | `machine_test.go` 表驱动用例 ≥12 条 |
| FR-4 | 服务启动后两张表存在；重复启动不报错 | integration 测试 |
| FR-5 | 同 `action_id` + 同 canonical payload Propose 两次：第二次 `already_exists=true` 且仅一条 PROPOSED 审计；同 `action_id` + 不同 payload 返回冲突；并发 20 次相同请求只产生一次业务执行 | `service_test.go` + integration |
| FR-6 | `none`：Propose 后可直接 Execute；`single`：未 Decide 时 Execute 返回错误，Decide(true) 后成功；`two_level`：一次 Approve 后仍不可执行，第二次（不同 approver）后可执行；任一 Decide(false) → REJECTED | `service_test.go` 四分支 |
| FR-7 | 前置条件失败时零写入；`freezeAccount` 执行且后置条件成立后 `customer.status='frozen'`；强制后置条件失败 → FAILED → 补偿成功后 ROLLED_BACK、状态还原；无补偿配置时停在 FAILED | `template_test.go` + integration |
| FR-8 | 任一完整链路（propose→decide→execute）后 `action_audit` 行数 = 状态迁移次数，每行含 payload hash、reason_code 及规则/证据引用；`GetStatus().history` 与表内容一致 | integration 断言 |
| FR-9 | 带 token 调用成功；错 token 返回 `PermissionDenied`；`grpcurl -plaintext localhost:7570 grpc.health.v1.Health/Check` 返回 SERVING | integration |
| FR-10 | `flagTransaction` 无 rollback：执行失败后停在 FAILED | integration |

**integration 测试统一前置**：`docker compose -f docker-compose.dev.yml up -d`（P02 交付的 PG16+AGE）；Go 测试用 build tag 或 `testing.Short()` 跳过（`go test -short` 跳集成）。
