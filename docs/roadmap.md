# AgenticX-OAG 产品路线图

> 目标：以 AgenticX 为基座，打造可对标 Palantir Foundry Ontology、能力覆盖并超越 Semantica 的开源本体增强生成系统。
>
> 版本：v0.1（2026-09）
> 维护者：AgenticX-OAG 团队

---

## 一、战略判断

### 1.1 我们的位置

当前仓库 `AgenticX-OAG` 是一个**研究方法论包 + 概念原型**：

- 6 个方向的深度研究笔记（基础/平台/检索/规则/治理/评测）
- 3 套前端原型（Orion、融合四场景、Near 时序）
- 1 份主调研报告 + 1 套 AGX Bundle（技能/记忆模板/角色预设）
- **没有真实引擎代码、没有持久化、没有 LLM 接入、没有 Action 闭环**

而基座 AgenticX 已经拥有大量可复用模块：

| AgenticX 模块 | 已有能力 | OAG 需要补什么 |
|---|---|---|
| `knowledge/graphers/` | SPO 抽取、Schema 生成、Neo4j 导出、社区发现、图谱构建器 | 本体层（OWL/SHACL）、对象类型系统、关系类型约束 |
| `knowledge/readers/` | PDF/Word/CSV/JSON/Web/PPT 等 8 种读取器 | 结构化数据源（数据库/API）接入、增量同步 |
| `knowledge/chunkers/` | 固定/递归/语义/Agentic 等分块策略 | 本体感知分块（按对象边界切） |
| `memory/graph/` | 图记忆存储、写入、嵌入、遗忘、恢复 | 本体对象作为一等记忆单元、Context Pack 记忆化 |
| `memory/` | 核心记忆/情景记忆/语义记忆/混合检索/知识底座 | 主张账本、方法记忆、分析模板 |
| `retrieval/` | 向量/BM25/图/混合检索、重排器、自动检索器 | 本体引导检索、多跳推理检索、来源追踪 |
| `safety/` | 安全框架 | 四权矩阵鉴权、Action 审批流、沙箱执行 |
| `agents/` | 多 Agent 编排 | 本体感知 Agent、治理 Agent、研究 Agent |
| `observability/` | 可观测性 | 决策溯源、审计回放、PROV-O 兼容 |

**核心结论：不要从零造引擎。AgenticX 已有 L1–L3 的大部分地基，AgenticX-OAG 专注做 L4 本体层 + L5 治理层 + L6 应用层——这三层是 Semantica 做不好、Palantir 最值钱的地方。**

### 1.2 对标框架

| 层 | Palantir Foundry | Semantica | AgenticX 现有 | AgenticX-OAG 目标 |
|---|---|---|---|---|
| L6 应用层 | Workshop / Quiver / Object Explorer | Explorer / MCP | Studio / Skills | **Ontology Workshop（低代码搭建）** |
| L5 治理层 | Actions / Functions / 动态安全 / 治理 | 无（MCP 无鉴权） | safety 框架 | **Action Gateway + 四权矩阵 + 审批流** |
| L4 本体层 | Object types / Link types / Properties | Ontology / OWL / SHACL | 无（只有 graph schema） | **Ontology Model + Context Pack + 方法记忆** |
| L3 检索层 | Foundry 检索 / Ontology 驱动查询 | GraphRAG / 多跳查询 | retrieval（图/向量/BM25/混合） | **本体引导混合检索 + 来源追踪** |
| L2 知识层 | Foundry 数据 + 本体映射 | KG / Context Graph | knowledge/graphers | **KG + 本体融合构建器** |
| L1 接入层 | 数据源 / Pipeline | ingest / parse / split | knowledge/readers | **本体感知接入 + 增量同步** |

**差异化护城河 = L5 治理闭环 + L4 方法记忆 + L6 低代码 Workshop**。这三样 Semantica 没有，Palantir 有但闭源。

---

## 二、分阶段路线图

### Phase 0：工程化奠基（2 周）

**目标：从「研究包」变成「可安装 Python 包」，建立开发基线。**

交付物：

1. **`agenticx_oag/` Python 包骨架**
   - `pyproject.toml`，依赖 AgenticX，不引入 torch/transformers 等重依赖
   - 包结构：`ontology/` `context/` `governance/` `retrieval/` `ingest/` `app/`
   - 与 AgenticX 通过 extension 机制集成（类似 bundle，但包含真实代码）

2. **Ontology 核心数据模型（Pydantic）**
   - `ObjectType` / `LinkType` / `PropertyType` / `ActionType`
   - `Ontology` 容器（命名空间、版本、元数据）
   - 序列化：YAML ↔ Python 对象 ↔ OWL Turtle（用 rdflib）
   - SHACL 校验（用 pyshacl）

3. **测试框架 + CI 基线**
   - pytest + 覆盖率基线
   - GitHub Actions：lint + test + type check

4. **文档站骨架**
   - 概念文档、API 文档、快速开始
   - 复用现有研究笔记，从「研究产物」转为「产品文档」

验收标准：`pip install agenticx-oag` 可安装，能 `from agenticx_oag.ontology import Ontology` 并加载一个 YAML 本体定义。

---

### Phase 1：本体引擎 + 知识图谱构建（4 周）

**目标：L1 + L2 跑通，能把真实数据变成 KG + 本体，替代 Semantica 的核心功能。**

交付物：

1. **本体感知接入层**
   - 复用 AgenticX `knowledge/readers/` 支持的所有格式
   - 新增：数据库接入（SQL → 本体对象映射）
   - 本体引导抽取：给 LLM 提供本体 schema 约束，让抽取结果直接符合对象类型/关系类型定义
   - 增量同步：变更检测 + 版本追踪

2. **KG + 本体融合构建器**
   - 复用 AgenticX `knowledge/graphers/` 的 SPO 抽取 + builder
   - 在 KG 之上叠加本体层：实体 → ObjectType 实例，关系 → LinkType 实例
   - 实体消歧 / 实体对齐（先做基础版：基于属性匹配 + 嵌入相似度）
   - 存储后端：Oxigraph（RDF，本体友好）+ AgenticX 已有向量库

3. **本体管理 API**
   - CRUD ObjectType / LinkType / PropertyType
   - 本体版本管理（schema migration）
   - 从 KG 自动推断本体草案（LLM 辅助）
   - 导入/导出：OWL / Turtle / JSON-LD / YAML

4. **与 AgenticX Memory 的集成**
   - 本体对象作为 `MemoryGraph` 中的一等节点
   - Context Pack 作为记忆单元存入 `semantic_memory`
   - 复用 `memory/hybrid_search` 做对象检索

验收标准：输入一批文档 → 自动构建 KG + 本体 → 能按 ObjectType 查询实体 → 结果带来源追踪。用 bank-aml 场景做端到端 Demo。

---

### Phase 2：OAG 检索 + Context Pack（4 周）

**目标：L3 + L4 上半部分完成，GraphRAG + 本体增强检索，超越纯向量 RAG。**

交付物：

1. **本体引导混合检索器**
   - 基于 AgenticX `retrieval/hybrid_retriever` 扩展
   - 新增：本体类型约束过滤、关系路径扩展、多跳推理
   - 检索结果带完整 provenance（来源节点 + 置信度 + 推导路径）

2. **Context Pack 引擎**
   - Context Pack 数据结构：问题改写链 + 本体对象引用 + 证据片段 + 主张 + 不确定性
   - 复用现有 `schemas/claim-ledger.schema.json` 作为主张账本
   - Pack 生成流水线：检索 → 本体对齐 → 证据聚合 → 主张生成 → 置信度评估
   - Pack 序列化/反序列化，可缓存、可复用

3. **OAG Generator**
   - 接收 Context Pack + 本体 schema → 生成结构化回答
   - 生成约束：只能引用 Pack 中的证据和主张，禁止幻觉
   - 每段输出附 citation（指向具体来源节点）

4. **评测框架**
   - 复用 03 研究笔记的指标体系：Recall@k / Faithfulness / Citation correctness / Hallucination rate
   - 离线评测集：bank-aml + supply-chain + power-grid 三个场景
   - 与纯 RAG、纯 GraphRAG 做对照实验

验收标准：在 bank-aml 场景上，OAG 检索的 faithfulness 比纯向量 RAG 高 ≥20%，citation correctness ≥85%。有可复现的评测报告。

---

### Phase 3：治理闭环 + Action Gateway（6 周）

**目标：L5 完成，这是对标 Palantir、甩开 Semantica 的核心差异化。**

交付物：

1. **Action Gateway（行动网关）**
   - Action 生命周期：提案 → 审批 → 执行 → 验证 → 归档
   - 幂等性保障：每个 Action 有唯一 ID，重复执行不产生副作用
   - 回滚机制：Action 执行失败或审批驳回时的状态回退
   - 沙箱执行：复用 AgenticX `safety/` + `sandbox/`

2. **四权矩阵鉴权**
   - 查看权（read）/ 操作权（write）/ 审批权（approve）/ 管理权（admin）
   - 基于本体对象类型的细粒度权限（不同 ObjectType 有不同权限集）
   - 对接 AgenticX 已有权限体系
   - OPA / Casbin 作为可选后端

3. **审批流引擎**
   - 简单审批：单级审批人
   - 多级审批：按金额/风险等级路由
   - 审批策略可配置，与本体 ActionType 绑定
   - 审批记录完整审计

4. **决策溯源 + 审计回放**
   - 每个决策有完整 provenance 链：数据 → 检索 → 推断 → 主张 → 决策 → Action
   - W3C PROV-O 兼容
   - 审计回放：可以重现任意决策的完整上下文
   - 复用 AgenticX `observability/`

5. **规则引擎集成**
   - 确定性规则与本体绑定（某类对象必须满足某条件才能执行某 Action）
   - 用 rete 算法或简单 forward chaining（先轻量实现）
   - 规则版本管理 + 测试

验收标准：bank-aml 场景可以走完「可疑交易识别 → 风险评估 → 冻结提案 → 审批 → 执行冻结 → 审计记录」全链路。每一步都可溯源、可回放、权限可控。

---

### Phase 4：方法记忆 + 分析模板（4 周）

**目标：L4 下半部分，这是 Semantica 和 Palantir 都没有的差异化能力。**

灵感来源：Palantir AIP Analyst 的 Skills + Analysis Lookup 更新（2026-08）。

交付物：

1. **分析模板（Analysis Template）**
   - 模板结构：分析目标 + 适用对象类型 + 改写链模板 + 工具调用结构 + 输出 schema
   - 模板从历史分析中自动提炼（LLM 辅助）
   - 模板库管理：分类、标签、版本、适用场景

2. **方法记忆（Method Memory）**
   - 复用 AgenticX `memory/sop_registry.py` 的 SOP 注册机制
   - 将成功的分析路径保存为可复用方法
   - 检索时：不仅检索知识，也检索「怎么做这类分析」的方法
   - 方法复用：加载模板 → 填入当前数据 → 执行分析 → 输出结果

3. **Analysis Lookup 服务**
   - 给定新问题 → 匹配最相似的历史分析模板 → 作为起点执行
   - 只复用「方法和路径」，基于当前数据重新执行（不携带旧结果）
   - 结果对比：新分析 vs 历史分析的差异

4. **与 Skill 体系的打通**
   - 稳定的方法模板 → 自动生成 Skill
   - AgenticX Skill 运行时产生的新经验 → 回流到方法记忆
   - 形成「实践 → 沉淀 → 复用 → 优化」的闭环

验收标准：在 3 个场景中各保存 2 个分析模板后，新问题能自动匹配到合适模板（top-1 准确率 ≥70%），并基于模板完成分析，人工只需少量修正。

---

### Phase 5：Ontology Workshop 低代码平台（8 周）

**目标：L6 完成，对标 Palantir Workshop，让非技术用户能搭建本体应用。**

交付物：

1. **Ontology Manager UI**
   - 本体可视化编辑器：对象类型、关系类型、属性的拖拽编辑
   - 本体版本对比 + 迁移
   - 数据图谱浏览：实体/关系的图可视化
   - 复用现有 `prototype/ontology-gateway-prototype/` 的 React + tRPC 全栈代码

2. **Action Builder**
   - 可视化配置 Action 类型：输入 schema、输出 schema、权限、审批流
   - Action 测试沙箱
   - Action 发布/版本管理

3. **App Builder（类 Workshop）**
   - 基于本体对象的页面搭建：Object View 生成器
   - 组件库：表格、卡片、图表、表单，全部绑定本体对象
   - 无需代码，拖拽搭建业务应用
   - 应用权限继承自本体四权矩阵

4. **Explorer Dashboard**
   - 全局搜索：跨对象类型的自然语言搜索
   - 决策看板：待审批、已执行、异常告警
   - 审计追踪：决策链路可视化

验收标准：非技术用户能在 30 分钟内，基于 bank-aml 本体搭建一个「可疑交易监控看板」应用，包含列表、详情、审批操作。

---

### Phase 6：生态 + 规模化（持续）

**目标：从「产品」变成「生态」，对标 Palantir 的平台地位。**

1. **MCP Server**：AgenticX-OAG 作为 MCP 服务，供任何 MCP 客户端（Claude Desktop、Cursor、VS Code）调用
2. **多 Agent 协作**：基于 AgenticX `agents/` + `flow/`，构建研究 Agent、治理 Agent、执行 Agent 等专业角色协作
3. **市场/模板库**：预置行业本体模板（金融、制造、能源、供应链），降低上手门槛
4. **企业级特性**：SSO、审计日志、高可用部署、多租户
5. **Benchmark 发布**：发布 OAG-Bench 评测基准，建立行业话语权

---

## 三、与 Semantica 的对标策略

### 3.1 哪些可以借鉴 Semantica

| Semantica 模块 | 我们的策略 | 原因 |
|---|---|---|
| `ingest` / `parse` / `split` | 复用 AgenticX 已有，不重写 | AgenticX readers/chunkers 已覆盖 |
| `kg` / `semantic_extract` | 复用 AgenticX graphers，加本体层 | graphers 已有 SPO 抽取和 builder |
| `ontology` | **自研，但参考 API 设计** | 这是核心，必须自己掌控 |
| `context` / `provenance` | **自研，加 Context Pack + 方法记忆** | 我们更强 |
| `reasoning` | 先轻量（forward chaining），后扩展 | 非 MVP 必须 |
| `storage` | 复用 AgenticX 存储 + Oxigraph | 不造轮子 |
| `mcp` | 后做，Phase 6 | 先有核心能力再暴露 |

### 3.2 我们比 Semantica 强在哪里

1. **Agent-native**：Semantica 是被动库，等 Agent 来调。我们是 AgenticX 原生能力，进程内访问 memory/safety/observability，零 RPC 开销。
2. **治理闭环**：Semantica 明确没有 Action 治理、没有鉴权、没有审批流。这是 Palantir 最值钱的部分，也是我们的护城河。
3. **方法记忆**：Semantica 的 decision record 只记「做了什么」，我们记「怎么做的」并且可以复用为模板。
4. **低代码应用层**：Semantica 只有 Explorer 仪表盘，我们有 Workshop 级别的应用搭建能力。
5. **研究方法论**：整个仓库的研究资产本身就是壁垒——知道「为什么这么设计」比「有代码」更难复制。

### 3.3 为什么不用 Semantica 做底座

- 依赖太重：`all` extra 含 torch/transformers 全家桶，AgenticX 是轻量依赖哲学
- 架构不匹配：Semantica 是独立服务思维，我们要进程内嵌入
- 治理层空白：Semantica 没有的恰恰是我们最核心的差异化
- 控制权：核心本体引擎不能依赖第三方项目的路线图

**正确姿势：参考 Semantica 的 API 设计和模块划分，但代码自己写，站在 AgenticX 肩膀上。**

---

## 四、为什么是 Python，不是 Go

| 维度 | Python | Go |
|---|---|---|
| 与 AgenticX 集成 | 进程内 import，天然一体 | 跨进程 gRPC，双语言维护 |
| AI 生态 | rdflib / pyshacl / pyoxigraph / FAISS / 全部 LLM SDK | 需自己绑或重写 |
| 性能瓶颈位置 | LLM 调用（秒级）> 图查询（毫秒级）> Python 逻辑（微秒级） | 优化微秒级开销是伪命题 |
| 开发效率 | 快速迭代、原型到生产平滑 | 静态类型 + 编译，慢但稳 |
| 招人 / 社区 | AI/本体社区基本全是 Python | Go 擅长 infra，但语义网生态弱 |

**Go 的唯一出场时机**：未来 Action Gateway 或 MCP Server 需要独立部署扛极高并发时，把那一层用 Go 重写。现在要做的准备是**架构留缝**——核心逻辑（本体模型、Context Pack、状态机）与 IO 层（存储/检索/LLM）清晰分离，接口抽干净。

---

## 五、里程碑总览

| 阶段 | 时长 | 核心交付 | 对标状态 |
|---|---|---|---|
| Phase 0 | 2 周 | Python 包骨架 + 本体数据模型 + 测试基线 | 工程化就绪 |
| Phase 1 | 4 周 | 本体引擎 + KG 构建 + Oxigraph 存储 | ≈ Semantica 核心能力 |
| Phase 2 | 4 周 | OAG 检索 + Context Pack + 评测框架 | > Semantica GraphRAG |
| Phase 3 | 6 周 | Action Gateway + 四权鉴权 + 审批 + 溯源 | **超越 Semantica，接近 Palantir 治理层** |
| Phase 4 | 4 周 | 方法记忆 + 分析模板 + Analysis Lookup | **Semantica 和 Palantir 都没有** |
| Phase 5 | 8 周 | Ontology Workshop 低代码平台 | 对标 Palantir Workshop |
| Phase 6 | 持续 | 生态 + 规模化 + 企业特性 | 平台级产品 |

**总计：28 周（约 7 个月）到 Phase 5，具备对标 Palantir 的完整产品形态。**

**最快验证路径：Phase 0 + Phase 1 + Phase 2 = 10 周，做出可用的 OAG 引擎并证明比 RAG 好。**

---

## 六、下一步行动（本周可以开始）

1. **建 `agenticx_oag/` 包骨架**，`pyproject.toml` + 目录结构 + 空模块
2. **写 Ontology 核心模型**（Pydantic），从 bank-aml 场景的 JSON 反推
3. **搭测试框架**，pytest + 第一个测试用例
4. **修正主调研报告**中 Semantica 已剔除的过时结论（它很活跃，v0.6.6）
5. **把 Phase 0 拆成具体任务**，分配到 issue / 看板

---

*本文档为活文档，随项目进展持续更新。*
