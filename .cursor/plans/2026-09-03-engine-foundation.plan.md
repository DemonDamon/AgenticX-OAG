---
name: "P02 引擎地基：包骨架 + Proto 契约 + 存储接口抽象"
overview: "建立 agenticx_oag Python 包骨架、跨语言本体元模型 Proto 契约、九个存储/集成接口 Protocol、CI 基线与开发环境。DAG 根节点，所有引擎轨道 subplan 的前置。"
todos: []
isProject: false
---

# P02 引擎地基 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
>
> Planned-with: glm 5.3
> Suggested-Impl-Model: 代码专精中档（骨架与契约样板为主，但接口签名设计需一次定准，避免低档模型拍脑袋改签名）

**Goal:** 落地 `docs/architecture.md` 的核心决策——契约先行。本 plan 交付：可安装的 Python 包、本体元模型 Proto（Python/Go 双端生成）、九个 Provider 接口 Protocol、CI 与本地开发环境。完成后 P03/P05/P07/P08/P09 可立即并行开工（P04 需 P03 的本体 YAML、P11 骨架可先行但完整联调需 P03/P04——完整依赖关系见 `docs/enterprise-landing.md` §8.2 注册表）。

**Architecture:** 控制面 Python（本包）+ 数据面 Go（P07 消费同一份 proto）。本体元模型以 proto 为单一事实来源，Python 侧另有 Pydantic 镜像模型（P03 交付，本 plan 只锁 proto）。所有企业差异（认证/审批/存储/通知）隔离在 Protocol 接口后面。

**Tech Stack:** Python 3.11+ / pydantic>=2 / protobuf / grpcio-tools / pytest / ruff / mypy / docker-compose（PG16+AGE、Redis）

---

## 背景与动机（证据链）

- `docs/architecture.md` §8.2「契约即资产」：本体元模型用 Proto 定义一次，生成 Python/Go/TS 三端绑定，杜绝双语言模型漂移；§9 明确 Phase 0 新增 Proto 契约定义与接口先行。
- `docs/roadmap.md` Phase 0 验收标准：`pip install agenticx-oag` 可安装、能加载本体定义。
- 现状：仓库无任何 Python 包（根目录仅有 docs/research/prototype/skills/schemas），proto 不存在。本 plan 是 DAG 根节点。

## 需求定义

### FR（Functional Requirements）

- **FR-1 Python 包骨架**：`pyproject.toml`（hatchling 后端）+ `agenticx_oag/__init__.py`（暴露 `__version__`）。核心依赖仅 `pydantic>=2`、`pyyaml`；可选 extra：`[dev]`（pytest/ruff/mypy/pytest-asyncio）、`[proto]`（protobuf/grpcio-tools）、`[graph]`（asyncpg）。
- **FR-2 本体元模型 Proto**：`proto/agenticx_oag/ontology/v1/ontology.proto`，完整字段见下方「关键实现意图」，覆盖 `PropertyType / ObjectType / LinkType / ActionType / Ontology / DataType / Cardinality`。
- **FR-3 Proto 双端生成**：`make proto` 生成 Python 绑定到 `agenticx_oag/contracts/gen/`（提交入库，Go 侧由 P07 自行引用同 proto 生成，本 plan 只保证 proto 文件即契约）；生成幂等（重复执行 diff 为空）。
- **FR-4 九个接口 Protocol**：`agenticx_oag/contracts/stores.py` 定义 `GraphStore / VectorStore / EmbeddingProvider / LLMProvider / AuditSink / EventBus / IDPProvider / ApprovalProvider / Notifier`（`typing.Protocol` + `@runtime_checkable`，签名见「关键实现意图」，全部 async）。
- **FR-5 CI 基线**：`.github/workflows/ci.yml`，PR 与 push 触发：ruff check → mypy（非严格，仅本包）→ pytest（单元层，集成测试带 `@pytest.mark.integration` 默认跳过）。
- **FR-6 开发环境**：`docker-compose.dev.yml`（`apache/age` PG16 镜像 + `redis:7`）+ `Makefile`（`dev-up / dev-down / proto / lint / test`）。
- **FR-7 版本与命名**：包名 `agenticx-oag`，版本 `0.1.0`，Python ≥3.11；**不依赖 agenticx 本体包**（避免重量级传递依赖；对 AgenticX 的复用通过 P04 侧的可选 extra 接入）。

### NFR（Non-Functional Requirements）

- **NFR-1** 冷安装（`pip install -e ".[dev]"`）≤ 60s（依赖面刻意收窄）。
- **NFR-2** 接口签名一旦合入即视为契约，后续变更需在 plan 中显式记录迁移。

## 精确落点

| 改动 | 路径 |
|---|---|
| 包定义 | `pyproject.toml`（新建） |
| 包入口 | `agenticx_oag/__init__.py`（新建，`__version__ = "0.1.0"`） |
| 契约模块 | `agenticx_oag/contracts/__init__.py`、`agenticx_oag/contracts/stores.py`（新建） |
| 生成产物 | `agenticx_oag/contracts/gen/__init__.py` + `ontology_v1_pb2.py`（生成后提交） |
| Proto | `proto/agenticx_oag/ontology/v1/ontology.proto`（新建） |
| 构建 | `Makefile`、`docker-compose.dev.yml`（新建，仓库根） |
| CI | `.github/workflows/ci.yml`（新建） |
| 测试 | `tests/test_contracts.py`、`tests/test_package.py`（新建） |

## 关键实现意图

**Proto 完整定义**（字段即契约，实施时逐字段照写）：

```protobuf
syntax = "proto3";
package agenticx_oag.ontology.v1;

enum DataType {
  DATA_TYPE_UNSPECIFIED = 0;
  DATA_TYPE_STRING = 1;
  DATA_TYPE_DOUBLE = 2;
  DATA_TYPE_INT64 = 3;
  DATA_TYPE_BOOL = 4;
  DATA_TYPE_TIMESTAMP = 5;
  DATA_TYPE_JSON = 6;
}

enum Cardinality {
  CARDINALITY_UNSPECIFIED = 0;
  CARDINALITY_ONE_TO_ONE = 1;
  CARDINALITY_ONE_TO_MANY = 2;
  CARDINALITY_MANY_TO_MANY = 3;
}

message PropertyType {
  string api_name = 1;            // camelCase，如 "riskLevel"
  string display_name = 2;
  DataType data_type = 3;
  bool required = 4;
  string description = 5;
  repeated string enum_values = 6; // data_type==STRING 时可非空
}

message ObjectType {
  string api_name = 1;            // PascalCase，如 "Customer"
  string display_name = 2;
  repeated PropertyType properties = 3;
  repeated string primary_key = 4; // 引用 properties[].api_name
  string parent = 5;               // 可选，类型层级（父 ObjectType.api_name）
  string description = 6;
}

message LinkType {
  string api_name = 1;            // camelCase，如 "owns"
  string display_name = 2;
  string source_type = 3;         // ObjectType.api_name
  string target_type = 4;
  Cardinality cardinality = 5;
  repeated PropertyType properties = 6;
}

message ActionType {
  string api_name = 1;            // camelCase，如 "freezeAccount"
  string display_name = 2;
  repeated string target_types = 3;   // 作用的 ObjectType.api_name 列表
  repeated PropertyType parameters = 4;
  repeated string preconditions = 5;  // 规则 ID 列表（P08 Harness 规则）
  string approval_policy = 6;         // "none" | "single" | "two_level"
  string rollback_handler = 7;        // 可选，回滚处理器标识
}

message Ontology {
  string namespace = 1;           // 如 "finance.aml"
  string version = 2;             // 语义化版本
  repeated ObjectType object_types = 3;
  repeated LinkType link_types = 4;
  repeated ActionType action_types = 5;
  map<string, string> metadata = 6;
}
```

**九个接口 Protocol**（`agenticx_oag/contracts/stores.py`，签名即契约）：

```python
from typing import Any, Protocol, runtime_checkable

@runtime_checkable
class GraphStore(Protocol):
    async def upsert_objects(self, objects: list["dict[str, Any]"]) -> None: ...
    async def upsert_links(self, links: list["dict[str, Any]"]) -> None: ...
    async def get_objects(self, object_type: str, ids: list[str] | None = None) -> list[dict[str, Any]]: ...
    async def neighbors(self, object_id: str, link_type: str | None = None, max_hops: int = 2) -> list[dict[str, Any]]: ...
    async def query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...

@runtime_checkable
class VectorStore(Protocol):
    async def upsert(self, collection: str, ids: list[str], vectors: list[list[float]], metas: list[dict[str, Any]]) -> None: ...
    async def search(self, collection: str, vector: list[float], top_k: int, filter: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...

@runtime_checkable
class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

@runtime_checkable
class LLMProvider(Protocol):
    async def complete(self, prompt: str, *, system: str | None = None, json_mode: bool = False) -> str: ...

@runtime_checkable
class AuditSink(Protocol):
    async def emit(self, event: dict[str, Any]) -> None: ...   # 事件结构与 P07 对齐：action_id/from/to/actor/ts/payload_hash

@runtime_checkable
class EventBus(Protocol):
    async def publish(self, topic: str, payload: bytes) -> None: ...

@runtime_checkable
class IDPProvider(Protocol):
    async def verify_token(self, token: str) -> dict[str, Any]: ...   # 返回 {subject, roles, tenant_id, ...}

@runtime_checkable
class ApprovalProvider(Protocol):
    async def request(self, action_id: str, summary: str, approvers: list[str]) -> str: ...  # 返回审批单 ID
    async def status(self, ticket_id: str) -> str: ...                # "pending"|"approved"|"rejected"

@runtime_checkable
class Notifier(Protocol):
    async def send(self, to: str, title: str, body: str) -> None: ...
```

**Makefile 关键目标**：

```makefile
proto:
	python -m grpc_tools.protoc -I proto \
	  --python_out=agenticx_oag/contracts/gen \
	  proto/agenticx_oag/ontology/v1/ontology.proto
	# 生成后统一修 import 路径（gen 包内相对导入），保证 make proto 幂等

test:
	pytest tests/ -m "not integration"

dev-up:
	docker compose -f docker-compose.dev.yml up -d
```

## In scope / Out of scope

**In scope：** FR-1~FR-7 全部；`.gitignore` 增补（`__pycache__`、`.venv`、`.mypy_cache`）。
**Out of scope（no-scope-creep）：** 不实现任何 GraphStore/VectorStore 的具体后端（P04/P05 做）；不写 Pydantic 本体模型（P03 做）；不接 AgenticX 包（P04 可选 extra）；不做 Go 侧代码（P07 做）；不做 proto 的 TS 生成（P11 需要时再加）。

## 验收标准（AC）

| FR | AC | 验证方式 |
|---|---|---|
| FR-1 | `pip install -e ".[dev]"` 成功；`python -c "import agenticx_oag; print(agenticx_oag.__version__)"` 输出 0.1.0 | 本地命令 |
| FR-2 | proto 编译通过；`Ontology` 消息可 round-trip（构造→SerializeToString→ParseFromString 相等） | `tests/test_contracts.py::test_proto_roundtrip` |
| FR-3 | 连续两次 `make proto` 后 `git diff` 为空 | 本地命令 |
| FR-4 | 九个 Protocol 可导入且 `@runtime_checkable`；写一个 mock 类满足 GraphStore 结构子类型并通过 `isinstance` 检查 | `tests/test_contracts.py::test_protocols` |
| FR-5 | CI 在空 PR 上绿（ruff 0 error、mypy 0 error、pytest 全过） | GitHub Actions |
| FR-6 | `make dev-up` 后 `pg_isready` 与 `redis-cli ping` 均通 | 本地命令 |
| FR-7 | `pip show agenticx-oag` 的 Requires 不含 agenticx/torch/transformers | 本地命令 |
