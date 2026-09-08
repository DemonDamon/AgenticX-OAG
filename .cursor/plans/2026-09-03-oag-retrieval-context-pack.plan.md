---
name: "P05 OAG 检索 + Context Pack 引擎"
overview: "实现本体引导混合检索（类型约束+向量+图扩展）、Context Pack 流水线（对齐 claim-ledger schema）与带引用约束的 OAG 生成器。"
todos: []
isProject: false
---

# P05 OAG 检索 + Context Pack 引擎 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
>
> Planned-with: glm 5.3
> Suggested-Impl-Model: 代码专精中档偏强（检索融合与 Pack 结构有跨模块一致性要求；引用约束校验逻辑需严谨，建议中档以上的代码模型）

**Goal:** 落地 L3+L4 上半部：`build_pack(question)` 流水线产出结构化 Context Pack（改写链+对象引用+证据+主张+不确定性），生成器只能引用 Pack 内证据。这是「OAG 优于 RAG」的能力核心，也是 P06 评测与 P10 Demo 的直接依赖。

**Architecture:** 检索 = 向量召回（VectorStore）∩ 类型约束（问题实体链接到 ObjectType 后过滤）∪ 图扩展（对象 2 跳邻域作为证据补全）；Pack 是唯一生成上下文（防幻觉的物理边界）；主张（claims）复用仓库已有 `schemas/claim-ledger.schema.json` 的字段语义；生成后由 `CitationValidator` 强校验。

**Tech Stack:** Python 3.11 / pydantic / 接口注入（GraphStore/VectorStore/LLMProvider/EmbeddingProvider 均为 P02 契约，测试全 mock）

---

## 背景与动机（证据链）

- `docs/roadmap.md` Phase 2 交付物 1~3：本体引导混合检索、Context Pack 引擎（复用 claim-ledger schema 作为主张账本）、OAG Generator（只引用 Pack 证据、每段输出附 citation）。
- `docs/architecture.md` 路径 B：Context Pack 检索（无 LLM 合成）延迟预算 图查 10-50ms + 向量 5-20ms + 重排 10-50ms——本 plan 实现即按此预算设计（同步路径不做网络往返叠加）。
- 现状：`schemas/claim-ledger.schema.json` 已存在（仓库根 schemas/）；检索/生成链路无任何实现。

## 需求定义

### FR（Functional Requirements）

- **FR-1 实体链接**：`agenticx_oag/retrieval/entity_link.py` 的 `EntityLinker(llm, ontology)`，方法 `link(question: str) -> list[LinkedEntity]`：LLM 从问题中识别实体并归类到 ObjectType（prompt 注入全部对象类型名与关键属性名；无法归类返回空列表，不猜测）。
- **FR-2 混合检索器**：`agenticx_oag/retrieval/ontology_hybrid.py` 的 `OntologyHybridRetriever(graph: GraphStore, vectors: VectorStore, embedder: EmbeddingProvider)`，方法 `retrieve(question: str, linked: list[LinkedEntity], top_k: int = 8) -> RetrievalResult`，三路融合：
  1. **向量召回**：问题嵌入 → VectorStore.search（top_k×3）。
  2. **类型约束过滤**：召回结果中 meta 含 object_type 的，仅保留 linked 中出现过的类型（linked 为空则不过滤）。
  3. **图扩展**：对过滤后 top 命中对象的 `graph.neighbors(max_hops=2)`，邻域对象作为补全证据（每对象限 5 个邻居，防爆炸）。
  - 输出 `RetrievalResult{evidence: list[Evidence], objects: list[ObjectRef]}`；`Evidence{id: "E{n}", object_id, text, score, provenance}`；分数 = 向量分 × 0.6 + 图邻接加成（出现于图扩展路径 +0.25，截断到 1.0）× 0.4。
- **FR-3 Context Pack 模型**：`agenticx_oag/context/pack.py` 的 `ContextPack`（pydantic）：
  - `pack_id: str`（`"pack_" + uuid4().hex[:12]`）、`question: str`、`rewrites: list[str]`（LLM 改写链，原问题为第 0 条）、`object_refs: list[ObjectRef]`、`evidence: list[Evidence]`、`claims: list[Claim]`、`uncertainty: str`、`created_at: datetime`。
  - `Claim{id: "C{n}", statement: str, evidence_ids: list[str], confidence: float(0-1), status: "asserted"|"uncertain"}`——字段名与 `schemas/claim-ledger.schema.json` 的 claim 结构对齐（实施前先读该 schema，以 schema 为准；若 schema 缺上述字段，以 schema 为准并回写本 plan 的 AC）。
  - 提供 `to_json() / from_json()`；`jsonschema.validate(pack.model_dump(), claim_ledger_schema)` 通过（以 schema 覆盖面为准，Pack 顶层即 ledger 一次会话快照）。
- **FR-4 Pack 流水线**：`agenticx_oag/context/pipeline.py` 的 `ContextPackPipeline(llm, ontology, retriever)`，方法 `async build_pack(question: str) -> ContextPack`：
  1. 改写：LLM 生成 1~2 个澄清改写（含指代消解意图），原问题保留为 rewrites[0]。
  2. 实体链接（FR-1）。
  3. 检索（FR-2，用改写后的主问题）。
  4. 主张生成：LLM 基于证据列表产出 claims（prompt 规则：每条主张必须标注支撑 evidence_ids；证据不足时 status=uncertain 且 confidence<0.5；禁止引入证据外知识）。
  5. 不确定性汇总：LLM 或规则汇总为一段中文陈述。
  - 全程不落库（Pack 是纯函数产物，缓存/持久化由调用方决定）。
- **FR-5 OAG 生成器**：`agenticx_oag/generation/oag.py` 的 `OAGGenerator(llm)`，方法 `async generate(pack: ContextPack) -> OAGAnswer`：
  - prompt = system（规则：仅可使用 Pack 内 evidence/claims；每个陈述句后附 `[E{id}]` 或 `[C{id}]` 引用标记；无证据支撑的内容必须显式说「根据现有证据无法判断」）+ Pack JSON。
  - 输出 `OAGAnswer{text: str, citations: list[Citation{marker, evidence_id|claim_id}]}`；解析正文中的引用标记。
- **FR-6 引用校验器**：`agenticx_oag/generation/validate.py` 的 `CitationValidator.validate(answer, pack) -> list[CitationViolation]`：
  - 引用了不存在的 evidence/claim id → violation(kind="dangling")。
  - 正文存在**无任何引用标记的断言句**（按句号切分、排除问句/引导句/免责句，引导句白名单：以「根据现有证据」「综上」「如下」开头的句子）→ violation(kind="unsupported")。
  - `is_valid = len(violations) == 0`。
- **FR-7 检索退化路径**：VectorStore 抛异常或未注入时，自动降级为纯图检索（linked 实体对象的邻域证据），并在 RetrievalResult 标记 `degraded: true`（对齐 architecture.md §5.2 降级阶梯）。

### NFR（Non-Functional Requirements）

- **NFR-1** mock 依赖下 build_pack 全程 < 300ms（不含真实 LLM 时延；真实场景预算 1-3s LLM 主导）。
- **NFR-2** Evidence 列表默认上限 24 条（超出按分数截断），防 prompt 膨胀。

## 精确落点

| 改动 | 路径 |
|---|---|
| 实体链接 | `agenticx_oag/retrieval/entity_link.py`（新建） |
| 混合检索 | `agenticx_oag/retrieval/ontology_hybrid.py`（新建） |
| Pack 模型 | `agenticx_oag/context/pack.py`（新建） |
| 流水线 | `agenticx_oag/context/pipeline.py`（新建） |
| 生成器 | `agenticx_oag/generation/oag.py`（新建） |
| 校验器 | `agenticx_oag/generation/validate.py`（新建） |
| 测试 | `tests/retrieval/test_entity_link.py`、`tests/retrieval/test_hybrid.py`、`tests/context/test_pack.py`、`tests/context/test_pipeline.py`、`tests/generation/test_oag.py`、`tests/generation/test_validate.py`（新建） |
| 参照 | `schemas/claim-ledger.schema.json`（只读；若发现字段语义冲突以 schema 为准并在 PR 描述记录） |

## 关键实现意图

**混合检索融合伪码**：

```python
async def retrieve(question, linked, top_k=8):
    vec_hits = await self.vectors.search(collection, await self.embedder.embed([question])[0], top_k * 3)
    allowed_types = {e.object_type for e in linked} or None
    filtered = [h for h in vec_hits if allowed_types is None or h.meta.get("object_type") in allowed_types]
    filtered.sort(key=lambda h: -h.score); top = filtered[:top_k]
    evidence, seen = [], set()
    for i, h in enumerate(top):
        ev = Evidence(id=f"E{i+1}", object_id=h.id, text=h.meta.get("text",""), score=h.score, provenance=h.meta.get("prov"))
        evidence.append(ev)
        for nb in await self.graph.neighbors(h.id, max_hops=2)[:5]:      # 每对象限 5 邻居
            if nb.id not in seen:
                seen.add(nb.id)
                evidence.append(Evidence(..., score=ev.score * 0.7))      # 图扩展证据衰减
    # 截断至 24 条后返回
```

**引用校验关键规则**（句级扫描）：

```python
SENT_SPLIT = re.compile(r"[。！？\n]+")
CITATION_RE = re.compile(r"\[([EC])(\d+)\]")
LEAD_WHITELIST = ("根据现有证据", "综上", "如下", "针对该问题")
for sent in (s for s in SENT_SPLIT.split(answer.text) if s.strip()):
    if not CITATION_RE.search(sent) and not sent.strip().startswith(LEAD_WHITELIST):
        violations.append(CitationViolation(kind="unsupported", sentence=sent))
```

## In scope / Out of scope

**In scope：** FR-1~FR-7；Pack 的 JSON 持久化辅助方法（to_json/from_json，不含存储后端）。
**Out of scope（no-scope-creep）：** 不做 Pack 缓存/存储后端（Phase 4 方法记忆再入库）；不做多 Pack 聚合；不做重排模型（reranker 留接口位：`RetrievalResult.reranked: bool` 字段占位）；不做真实 LLM 的 e2e 测试；不修改 claim-ledger.schema.json 本身（冲突时记录并上报，不改 schema）。

## 验收标准（AC）

| FR | AC | 验证方式 |
|---|---|---|
| FR-1 | mock LLM 返回类型归类；问题含未定义实体时返回空列表 | `test_entity_link.py` |
| FR-2 | fixture：8 条向量命中（6 条 Customer、2 条 Transaction），linked=[Customer] → 结果仅 Customer + 其图邻居；分数合成符合权重公式（手算 fixture 核对） | `test_hybrid.py` |
| FR-3 | Pack to_json/from_json 往返相等；`jsonschema.validate` 通过（对照 claim-ledger schema） | `test_pack.py` |
| FR-4 | mock LLM 链路：build_pack 产出 rewrites≥1、evidence 非空、claims 每条 evidence_ids ⊆ evidence ids | `test_pipeline.py` |
| FR-5 | mock 生成器输出含 `[E1]` 标记；OAGAnswer.citations 解析出对应条目 | `test_oag.py` |
| FR-6 | 构造含 dangling 引用与无引用断言的答案 → 两种 violation 各 ≥1；干净答案 is_valid=True | `test_validate.py` |
| FR-7 | VectorStore mock 抛 RuntimeError → 降级路径返回非空 evidence 且 degraded=True | `test_hybrid.py::test_degraded` |
