# AgenticX-OAG 任务计划

> 目标：以 AgenticX 为基座，参考 Palantir Foundry Ontology 与 Semantica 的公开能力，构建开源本体增强生成系统，并重点补齐 Agent 提案运行时治理闭环。
>
> 详细路线图见 [docs/roadmap.md](docs/roadmap.md)

---

## 当前阶段

**Phase 0：工程化奠基** — 预计 2 周

---

## 阶段进度

| # | 阶段 | 状态 | 预计工期 | 交付物 |
|---|---|---|---|---|
| 0 | 工程化奠基 | `not_started` | 2 周 | Python 包骨架 + 本体数据模型 + 测试基线 |
| 1 | 本体引擎 + KG 构建 | `not_started` | 4 周 | 本体感知接入 + KG/本体融合构建器 + 存储 |
| 2 | OAG 检索 + Context Pack | `not_started` | 4 周 | 本体引导检索 + Context Pack 引擎 + OAG Generator + 评测 |
| 3 | 治理闭环 + Action Gateway | `not_started` | 6 周 | Action Gateway + 四权鉴权 + 审批流 + 溯源 |
| 4 | 方法记忆 + 分析模板 | `not_started` | 4 周 | 分析模板 + 方法记忆 + Analysis Lookup |
| 5 | Ontology Workshop 低代码 | `not_started` | 8 周 | Ontology Manager + Action Builder + App Builder |
| 6 | 生态 + 规模化 | `not_started` | 持续 | MCP + 多 Agent + 模板市场 + 企业级 |

---

## Phase 0 任务拆解

### 0.1 Python 包骨架
- [ ] 创建 `agenticx_oag/` 目录结构
- [ ] 写 `pyproject.toml`（依赖 agenticx，轻量依赖）
- [ ] 初始化各子模块 `__init__.py`
- [ ] `pip install -e .` 可安装验证

### 0.2 Ontology 核心数据模型
- [ ] `ObjectType` / `LinkType` / `PropertyType` / `ActionType` Pydantic 模型
- [ ] `Ontology` 容器（命名空间、版本、元数据）
- [ ] YAML 序列化/反序列化
- [ ] OWL Turtle 导出（rdflib）
- [ ] SHACL 校验（pyshacl）

### 0.3 测试 + CI 基线
- [ ] pytest 配置
- [ ] 核心模型单元测试
- [ ] GitHub Actions：lint + test
- [ ] 覆盖率基线

### 0.4 文档
- [ ] 快速开始（Quick Start）
- [ ] 核心概念文档
- [ ] API 文档骨架

---

## 关键决策记录

| 决策 | 结论 | 理由 | 日期 |
|---|---|---|---|
| 主语言 | Python | 与 AgenticX 同语言，进程内集成，AI 生态全 | 2026-09-02 |
| 图存储 | Oxigraph（Rust，pyoxigraph 绑定） | RDF/SPARQL 原生，本体友好，性能好 | 2026-09-02 |
| 向量存储 | 复用 AgenticX 已有后端 | 不造轮子，保持轻量 | 2026-09-02 |
| 是否基于 Semantica | 否，参考但自研 | 完整依赖面较重、与 AgenticX 进程内扩展边界不同；企业治理闭环需由本项目独立实现和验证 | 2026-09-02 |
| 计划差异化 | 治理闭环 + 方法记忆 + 低代码 Workshop | Semantica 已公开知识、本体、检索与决策记录等能力；本项目重点验证运行时门禁和受控写回 | 2026-09-02 |

---

## 风险与应对

| 风险 | 概率 | 影响 | 应对 |
|---|---|---|---|
| AgenticX API 变动导致集成困难 | 中 | 高 | 锁定 AgenticX 版本，封装适配层 |
| Oxigraph / pyoxigraph 功能不够 | 低 | 中 | 预留 Neo4j 后端切换能力 |
| 本体自动构建质量不达标 | 中 | 高 | Phase 1 先做人工定义 + 半自动，逐步提升自动化 |
| 评测指标设计不合理 | 中 | 中 | 多轮迭代，参考学术界 SOTA 评测方法 |

---

## 已完成

- [x] 项目重命名：oag-deep-research → AgenticX-OAG（2026-09-02）
- [x] GitHub 仓库重命名 + 推送（2026-09-02）
- [x] 完成路线图文档 v0.1（2026-09-02）
