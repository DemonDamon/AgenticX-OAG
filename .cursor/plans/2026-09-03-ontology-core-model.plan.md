---
name: "P03 本体核心数据模型：Pydantic 镜像 + YAML/OWL/SHACL + 场景转换器"
overview: "在 P02 Proto 契约之上实现 Python 侧本体模型（Pydantic v2）、YAML 读写、OWL Turtle 导出（仅 TBox）、SHACL 校验，以及 prototype 场景 JSON → 本体 YAML 转换器。"
todos: []
isProject: false
---

# P03 本体核心数据模型 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
>
> Planned-with: glm 5.3
> Suggested-Impl-Model: 代码专精中档（Pydantic 建模 + rdflib/pyshacl 集成，签名与校验规则已在 plan 中写全，中档模型可稳妥落地）

**Goal:** 让「本体」成为一等 Python 对象：YAML 定义 → 校验 → 内存模型 → OWL 导出/SHACL 校验，并能把现有 `prototype/scenes/*.json` 的类型定义迁移为正式本体 YAML。P04/P05/P08/P10/P11 全部消费本模块。

**Architecture:** Pydantic 模型与 P02 proto 字段一一镜像（proto 是跨语言契约，Pydantic 是 Python 侧人体工学层）；OWL 导出**仅 TBox（概念层）**，实例层归图存储，以保持概念层级与实例关联分模型管理。

**Tech Stack:** pydantic v2 / pyyaml / rdflib / pyshacl（`[owl]` extra 引入 rdflib+pyshacl）

---

## 背景与动机（证据链）

- `docs/roadmap.md` Phase 0 交付物 2：ObjectType/LinkType/PropertyType/ActionType Pydantic 模型、YAML 序列化、OWL Turtle 导出（rdflib）、SHACL 校验（pyshacl）。
- `docs/enterprise-landing.md` §一点五：Semantic Ontology 象限不自研、只留 RDF 接口——OWL 导出/导入即该接口的出口/入口。
- 现状：`prototype/scenes/bank-aml.json` 已有 8 个对象类型（Customer/Account/Transaction/SuspiciousTxn/LoanApplication/Collateral/SanctionHit/DueDiligence）与 8 个关系关键词（owns/initiates/flaggedAs/applies/securedBy/hitsSanction/reviewedBy/risk），是首个转换输入。

## 需求定义

### FR（Functional Requirements）

- **FR-1 Pydantic 模型**：`agenticx_oag/ontology/model.py` 定义 `PropertyType / ObjectType / LinkType / ActionType / Ontology`，字段与 P02 proto 逐一对齐（api_name/display_name/…/metadata）。
- **FR-2 命名校验**：ObjectType.api_name 匹配 `^[A-Z][A-Za-z0-9]*$`；PropertyType/LinkType/ActionType.api_name 匹配 `^[a-z][A-Za-z0-9_]*$`；违反抛 `OntologyValidationError`（`agenticx_oag/ontology/errors.py`）。
- **FR-3 引用完整性**：`Ontology.validate()` 检查——LinkType.source_type/target_type 必须存在于 object_types；ObjectType.primary_key 引用的属性必须存在且 `required=True`；ObjectType.parent 若非空必须存在且无环；ActionType.target_types/preconditions 引用有效（preconditions 允许前向引用 P08 规则 ID，仅做格式校验 `^[a-z0-9_.:-]+$`）。
- **FR-4 类型约束**：`PropertyType.enum_values` 非空时 data_type 必须为 STRING；DataType 为 TIMESTAMP/JSON 的属性不得作为 primary_key。
- **FR-5 YAML 读写**：`agenticx_oag/ontology/io.py` 提供 `load_ontology(path) -> Ontology` 与 `dump_ontology(ontology, path)`；YAML 顶层键 `namespace/version/object_types/link_types/action_types/metadata`；round-trip 后模型相等。
- **FR-6 OWL 导出（仅 TBox）**：`agenticx_oag/ontology/owl_export.py` 的 `to_turtle(ontology) -> str`：ObjectType→`owl:Class`（parent 用 `rdfs:subClassOf`）；PropertyType→`owl:DatatypeProperty`（带 `rdfs:domain/rdfs:range`）；LinkType→`owl:ObjectProperty`；输出可被 rdflib 重新解析且三元组数 > 0。提供 `to_jsonld(ontology) -> str`。
- **FR-7 SHACL 校验**：`agenticx_oag/ontology/shacl.py` 的 `build_shapes(ontology) -> str`（Turtle）：每个 ObjectType 一个 `sh:NodeShape`，属性形状含 datatype 与 cardinality（required→`sh:minCount 1`）。`validate_graph(data_graph: str, ontology) -> list[str]` 返回违规消息列表（空列表=通过）。
- **FR-8 场景转换器**：`scripts/scene_to_ontology.py`：读取 `prototype/scenes/<name>.json` 的 `types`（dict，值为属性列表）与 `relKeywords`（dict，关系→类型对），生成合法本体 YAML 到 stdout 或 `--out` 路径；属性类型映射规则：数值键（amount/risk/score 等）→DOUBLE，含 date/time→TIMESTAMP，bool→BOOL，其余→STRING；primary_key 默认 `id`（不存在时取首个 required 属性并打 WARNING）。

### NFR（Non-Functional Requirements）

- **NFR-1** 100 类型规模的本体 `validate()` < 100ms。
- **NFR-2** OWL/SHACL 依赖放 `[owl]` extra，核心安装不引入 rdflib。

## 精确落点

| 改动 | 路径 |
|---|---|
| 模型 | `agenticx_oag/ontology/model.py`（新建） |
| 异常 | `agenticx_oag/ontology/errors.py`（新建：`OntologyValidationError(OntologyError)` 基类链） |
| IO | `agenticx_oag/ontology/io.py`（新建） |
| OWL | `agenticx_oag/ontology/owl_export.py`（新建） |
| SHACL | `agenticx_oag/ontology/shacl.py`（新建） |
| 包导出 | `agenticx_oag/ontology/__init__.py`（新建，re-export 公共符号） |
| 转换器 | `scripts/scene_to_ontology.py`（新建） |
| 首个本体 | `templates/finance/aml/ontology.yaml`（由转换器产出后人工微调，供 P10 扩展） |
| 测试 | `tests/ontology/test_model.py`、`test_io.py`、`test_owl_export.py`、`test_shacl.py`、`test_scene_convert.py`（新建目录） |

## 关键实现意图

**模型骨架**（pydantic v2，字段约束用 `Field` + `field_validator`）：

```python
class PropertyType(BaseModel):
    api_name: str = Field(..., pattern=r"^[a-z][A-Za-z0-9_]*$")
    display_name: str
    data_type: DataType = DataType.STRING
    required: bool = False
    description: str = ""
    enum_values: list[str] = Field(default_factory=list)

class LinkType(BaseModel):
    api_name: str = Field(..., pattern=r"^[a-z][A-Za-z0-9_]*$")
    display_name: str
    source_type: str
    target_type: str
    cardinality: Cardinality = Cardinality.MANY_TO_MANY
    properties: list[PropertyType] = Field(default_factory=list)

class Ontology(BaseModel):
    namespace: str = Field(..., pattern=r"^[a-z][a-z0-9_.]*$")   # 如 "finance.aml"
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$")
    object_types: list[ObjectType]
    link_types: list[LinkType] = Field(default_factory=list)
    action_types: list[ActionType] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)

    def validate(self) -> None: ...  # FR-3 全部检查，任一失败聚合为一条 OntologyValidationError（列出全部问题）
```

**转换器调用方式**（AC 复现命令）：

```bash
python scripts/scene_to_ontology.py prototype/scenes/bank-aml.json \
  --namespace finance.aml --version 0.1.0 --out templates/finance/aml/ontology.yaml
```

**YAML 样例片段**（bank-aml 转换预期产物，实施者对照自查）：

```yaml
namespace: finance.aml
version: 0.1.0
object_types:
  - api_name: Customer
    display_name: 客户
    primary_key: [id]
    properties:
      - { api_name: id, data_type: STRING, required: true }
      - { api_name: riskLevel, data_type: STRING, enum_values: [low, medium, high] }
  - api_name: SanctionHit
    display_name: 制裁命中
    primary_key: [id]
    properties:
      - { api_name: id, data_type: STRING, required: true }
      - { api_name: score, data_type: DOUBLE }
link_types:
  - api_name: hitsSanction
    display_name: 命中制裁
    source_type: Customer
    target_type: SanctionHit
    cardinality: ONE_TO_MANY
```

## In scope / Out of scope

**In scope：** FR-1~FR-8；`templates/finance/aml/ontology.yaml` 的生成与人工微调（微调仅限 display_name/description/enum，不改结构）。
**Out of scope（no-scope-creep）：** 不做 OWL 导入（仅导出；导入留待确有 Semantic 象限客户时再做）；不做实例数据（P04/P10）；不做 ActionType 的具体执行（P07）；不做本体版本迁移/diff 工具（后续独立 plan）；不改 `prototype/scenes/*.json` 原文件。

## 验收标准（AC）

| FR | AC | 验证方式 |
|---|---|---|
| FR-1 | 模型可构造且字段与 proto 镜像（人工对照 proto 逐字段核对） | code review + `tests/ontology/test_model.py` |
| FR-2 | `api_name="customer"`（ObjectType）抛 OntologyValidationError | `test_model.py::test_name_validation` |
| FR-3 | dangling link（target_type 不存在）validate() 抛错且消息含 `"SanctionHit2"`；primary_key 指向非 required 属性抛错；parent 成环抛错 | `test_model.py::test_reference_integrity` 三用例 |
| FR-4 | enum_values 非空 + DOUBLE 抛错；TIMESTAMP 作 primary_key 抛错 | `test_model.py::test_type_constraints` |
| FR-5 | load→dump→load 两轮后 `model_dump()` 相等 | `test_io.py::test_yaml_roundtrip` |
| FR-6 | to_turtle 输出可 `rdflib.Graph().parse(data=..., format="turtle")`，三元组数 ≥ 对象类型数×3 | `test_owl_export.py::test_turtle_parseable` |
| FR-7 | 用 shapes 校验一份缺 required 属性的实例数据图，返回违规消息且含属性名；合法数据返回空列表 | `test_shacl.py::test_validate_instances` |
| FR-8 | 转换 bank-aml.json 产出 ontology.yaml，`load_ontology` + `validate()` 通过，含 8 ObjectType / 8 LinkType | `test_scene_convert.py::test_bank_aml_conversion` + 本地命令复现 |
