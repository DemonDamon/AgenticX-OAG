---
name: "P04 KG 构建器 + 图存储（PG/AGE）"
overview: "实现 GraphStore 的 PG+AGE 后端、本体引导 LLM 抽取、实体消歧与端到端摄入管道：文档 → 读取 → 抽取 → 消歧 → 入图（带溯源）。"
todos: []
isProject: false
---

# P04 KG 构建器 + 图存储 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
>
> Planned-with: glm 5.3
> Suggested-Impl-Model: 代码专精中档（asyncpg/AGE 集成与 openCypher 模板属常规后端实施；抽取 prompt 结构已在 plan 写全）

**Goal:** 打通 L1+L2：给定本体 YAML 与一批文档，产出带类型、带溯源的实例图，存入 PG+AGE，可通过 GraphStore 接口按类型查询、按关系扩展。这是「替代被动原型数据」的第一步。

**Architecture:** GraphStore 接口（P02 契约）的 AGE 实现；抽取为「本体引导」——把 ObjectType/LinkType 的 schema 注入 LLM prompt，要求输出仅含已定义类型（JSON mode）；消歧分两级（属性精确匹配 → 嵌入相似度阈值）；溯源（provenance）挂在节点/边的 `__prov` JSON 属性上。图按本体 namespace 隔离（每 namespace 一个 AGE graph）。

**Tech Stack:** Python 3.11 / asyncpg / AGE openCypher /（可选 extra `agenticx`：复用其 readers；不可用时降级直接读 `.md/.txt/.json`）/ numpy（嵌入余弦）

---

## 背景与动机（证据链）

- `docs/architecture.md` §1.1/§4：图存储 PG16+Apache AGE 起步（中小规模一个库搞定，运维减半），Oxigraph 降级为嵌入组件；`docs/roadmap.md` Phase 1 交付物 1/2。
- `docs/enterprise-landing.md` 四象定位：KG Schema 象限自建、复用 AgenticX graphers 思路；CWA（封闭世界假设）与 PG 选型天然匹配（§七点五红线 3）。
- 现状：原型数据是前端硬编码 JSON（`prototype/scenes/bank-aml.json` 20 节点/18 边），无真实抽取链路。

## 需求定义

### FR（Functional Requirements）

- **FR-1 记录模型**：`agenticx_oag/graph/records.py` 定义 `ObjectRecord`（object_type/api_name、id、properties: dict、prov: ProvInfo）、`LinkRecord`（link_type、source_id、target_id、properties、prov）、`ProvInfo`（source_doc: str、span: str、extracted_at: str、confidence: float）。
- **FR-2 AGE 存储**：`agenticx_oag/graph/age_store.py` 的 `AGEGraphStore` 实现 P02 `GraphStore` 全部五个方法：
  - `upsert_objects`：MERGE 语义（按 primary_key 属性匹配已存在则更新）；节点 label = ObjectType.api_name；系统属性 `__prov` 存 JSON 字符串、`__ns` 存 namespace。
  - `upsert_links`：openCypher MERGE 关系；关系 type = LinkType.api_name。
  - `get_objects(object_type, ids)`：label 过滤 + 可选 id 列表过滤，返回原始 dict（含 properties，剥离 `__prov/__ns` 并解析回 ProvInfo 结构）。
  - `neighbors(object_id, link_type, max_hops)`：可变长路径 `MATCH p=(n)-[r*1..{max_hops}]-(m) WHERE id(n)=...`，返回每跳 {node, rel, depth}。
  - `query(cypher, params)`：透传 openCypher（`SELECT * FROM ag_catalog.cypher('<graph>', $$ ... $$) ...` 包装由实现负责）。
  - 构造参数：`AGEGraphStore(dsn: str, namespace: str)`；graph 名 = `oag_<namespace 中 . 换 _>`；首次使用自动 `CREATE EXTENSION IF NOT EXISTS age` + `SELECT create_graph(...)`。
- **FR-3 本体引导抽取**：`agenticx_oag/extract/guided_extractor.py` 的 `GuidedExtractor(llm: LLMProvider, ontology: Ontology)`，方法 `extract(chunks: list[str]) -> tuple[list[ObjectRecord], list[LinkRecord]]`。Prompt 结构（`agenticx_oag/extract/prompts.py`）：
  - system：注入本体 JSON schema（object_types/link_types 的 api_name + 属性名 + enum 值域）+ 规则「只能输出已定义类型；属性名必须精确匹配；无法归类的内容丢弃；每个输出带 source_span（chunk 内原文片段）与 confidence(0-1)」。
  - user：chunk 原文。
  - 要求 JSON mode，输出 schema：`{"objects": [{"type": "...", "id": "...", "properties": {...}, "source_span": "...", "confidence": 0.9}], "links": [{"type": "...", "source_id": "...", "target_id": "...", "source_span": "...", "confidence": 0.8}]}`。
  - 解析防御：JSON 解析失败或含未定义类型 → 丢弃该条并记 WARNING（不抛异常中断整批）。
- **FR-4 实体消歧**：`agenticx_oag/graph/resolve.py` 的 `EntityResolver(embedder: EmbeddingProvider | None, threshold: float = 0.92)`，方法 `resolve(objects: list[ObjectRecord]) -> list[ObjectRecord]`：
  - 第一级：同 object_type 且 primary_key 属性完全相等 → 合并（属性并集，prov 链接追加）。
  - 第二级（embedder 提供时）：同类型节点的「展示名 + 关键属性」拼接串嵌入余弦 ≥ threshold → 合并，prov 记录 `merged_via: "embedding"`。
  - 被合并的旧 id 保留映射表（返回值附 `alias_map: dict[str, str]`，供链接重定向）。
- **FR-5 链接重定向**：管道在入图前用 alias_map 重写 LinkRecord 的 source_id/target_id。
- **FR-6 摄入管道**：`agenticx_oag/ingest/pipeline.py` 的 `IngestPipeline`：
  - 输入：`run(docs: list[Path], ontology_path: Path, store: GraphStore, llm, embedder=None, chunk_size=1200)`。
  - 步骤：读取（`.md/.txt/.json` 直读；安装了 agenticx extra 时走其 readers 处理更多格式）→ 按 chunk_size 滑窗分块（10% 重叠）→ 逐块抽取 → 合并批次 → 消歧 → 链接重定向 → upsert 入图。
  - 返回 `IngestReport`（chunks 数、抽取 objects/links 数、合并数、丢弃数）。
- **FR-7 端到端示例**：`examples/kg_build_demo.py`：读取 `examples/docs/*.md`（本 plan 新建 3 篇 AML 主题示例文档，共含 ≥10 个可抽取实体）+ `templates/finance/aml/ontology.yaml`（P03 产物），mock LLM（固定 JSON 响应，见 AC）跑通全管道入 AGE，再查询 Customer 全量打印。

### NFR（Non-Functional Requirements）

- **NFR-1** upsert_objects 500 节点批 < 5s（本地 PG）。
- **NFR-2** 抽取对单 chunk 的 LLM 失败重试 1 次后跳过，不中断整批。

## 精确落点

| 改动 | 路径 |
|---|---|
| 记录模型 | `agenticx_oag/graph/records.py`（新建） |
| AGE 实现 | `agenticx_oag/graph/age_store.py`（新建） |
| 消歧 | `agenticx_oag/graph/resolve.py`（新建） |
| 抽取 | `agenticx_oag/extract/guided_extractor.py`、`agenticx_oag/extract/prompts.py`（新建） |
| 管道 | `agenticx_oag/ingest/pipeline.py`（新建；`agenticx_oag/ingest/__init__.py` 导出 IngestPipeline） |
| 示例 | `examples/kg_build_demo.py`、`examples/docs/aml-*.md` ×3（新建） |
| 测试 | `tests/graph/test_age_store.py`（integration 标记）、`tests/graph/test_resolve.py`、`tests/extract/test_guided_extractor.py`（mock LLM）、`tests/ingest/test_pipeline.py`（mock 全链） |

## 关键实现意图

**upsert_objects 的 openCypher 模板**（示意，参数化防注入——属性值一律走 `$params`）：

```cypher
UNWIND $rows AS row
MERGE (n:Customer {id: row.id})   // label 需按类型拼接（AGE 不支持参数化 label，需白名单校验后 f-string）
SET n += row.props, n.__prov = row.prov_json, n.__ns = $ns
```

> label/关系 type 拼接前必须对照 ontology 白名单校验（`^[A-Za-z0-9_]+$` 且存在于类型定义），否则抛 `ValueError`——这是注入防线，不可省。

**mock LLM 固定响应**（测试与 demo 共用，放 `tests/fixtures/mock_llm.py`）：

```json
{
  "objects": [
    {"type": "Customer", "id": "C-001", "properties": {"name": "张三", "riskLevel": "high"}, "source_span": "客户张三……", "confidence": 0.95},
    {"type": "SanctionHit", "id": "S-001", "properties": {"list": "OFAC", "score": 0.87}, "source_span": "命中OFAC名单……", "confidence": 0.9}
  ],
  "links": [
    {"type": "hitsSanction", "source_id": "C-001", "target_id": "S-001", "source_span": "张三命中OFAC", "confidence": 0.85}
  ]
}
```

## In scope / Out of scope

**In scope：** FR-1~FR-7；`pyproject.toml` 增补 `[graph]` extra（asyncpg）与 `[ingest]` extra（numpy）。
**Out of scope（no-scope-creep）：** 不做 CDC/增量同步（后续独立 plan）；不做数据库直连源接入（SQL→对象映射，后续 plan）；不做 Neo4j/Nebula 后端（接口已隔离，按需再加）；不做嵌入模型训练/本地推理服务（EmbeddingProvider 注入为准）；不做真实 LLM 调用的 e2e 测试（integration 测试用 mock LLM + 真实 PG）。

## 验收标准（AC）

| FR | AC | 验证方式 |
|---|---|---|
| FR-1 | 记录模型构造与序列化往返 | `test_records` 单测 |
| FR-2 | 真实 PG（`make dev-up`）：upsert 两个同 id Customer 第二次属性被更新（MERGE 语义）；get_objects("Customer") 返回含 properties 与解析后 prov；neighbors 2 跳命中跨类型路径 | `tests/graph/test_age_store.py`（`@pytest.mark.integration`，需 `TEST_PG_DSN` 环境变量） |
| FR-3 | mock LLM 返回含未定义类型 "Foo" 的条目被丢弃且 WARNING 计数 +1；合法条目全部转成 ObjectRecord | `tests/extract/test_guided_extractor.py` |
| FR-4 | 两个「同名+属性全等」Customer 合并为 1；构造嵌入向量余弦 0.95 的两个节点合并且 prov 含 merged_via=embedding；alias_map 正确 | `tests/graph/test_resolve.py`（embedder 用确定性 mock：直接返回预设向量） |
| FR-5 | 合并后链接 source_id 已重定向，图中无悬挂引用 | `tests/ingest/test_pipeline.py` |
| FR-6 | mock 全链管道产出 IngestReport，各计数与 fixture 预期一致 | 同上 |
| FR-7 | `python examples/kg_build_demo.py`（TEST 环境变量指向本地 PG + mock LLM 开关）退出码 0，打印 ≥8 个 Customer 类节点 | 本地命令 |
