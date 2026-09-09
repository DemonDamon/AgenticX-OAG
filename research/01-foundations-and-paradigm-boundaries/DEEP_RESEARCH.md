# 01 · 概念基础与范式边界：深度研究笔记

**研究状态：第一轮完成。** 本文仅以可核验的一手标准、厂商架构材料与公开实现为证据，回答“本体”在语义 Web、属性图、操作型企业平台与 Agent 运行时四种语境中各指什么。受限资料不纳入仓库；由其启发的问题必须通过公开来源或项目实验独立复核后才能形成工程结论。

## 结论摘要

“本体”不是一个单一技术名词。RDF/OWL 的主对象是可交换的语义陈述与形式语义；SHACL 的主对象是当前 RDF 数据是否满足可执行约束；属性图 Schema 的主对象是应用内节点、关系、属性、索引与约束；Palantir Ontology 的主对象是连接数据、逻辑、行动与安全的组织操作层；Agent 运行时约束则着眼于模型、工具、状态与行动的可允许范围。它们可相互补充，却不能互换。[1] [2] [3] [4]

| 范式 | 核心数据模型 | 主操作 | 最适合的问题 | 不应替代 |
|---|---|---|---|---|
| RDF / OWL | 三元组、类、属性、个体 | 蕴含、一致性、实例检索 | 跨源术语对齐与形式语义 | 事务前置校验与业务写回 |
| SHACL | shapes graph + data graph | 验证与结果报告 | 数据交付、接口与治理门禁 | 通用递归生产规则系统 |
| 属性图 Schema | 节点、关系、标签、键值属性 | 遍历、查询、图分析 | 业务实体关系与高频图查询 | 标准化形式语义互操作 |
| 操作型本体 | 对象、链接、逻辑、Action、安全 | 受治理读写与决策闭环 | 企业业务模型、应用与行动编排 | 可移植的公共语义标准 |
| Agent 运行时约束 | 状态、工具 Schema、策略与轨迹 | 计划、调用、审批与审计 | 工具使用边界和自治治理 | OWL/SHACL 的形式语义 |

## 证据与分析

RDF 1.1 将 RDF graph 定义为主语、谓词、宾语三元组组成的集合，RDF dataset 再组织默认图与命名图。[1] OWL 2 则提供 Direct Semantics 和 RDF-Based Semantics，支持以一致性、蕴含、类层级和实例检索为中心的推理问题。[2] 这意味着“语义本体”首先是对领域概念化的机器可解释规约，而不是所有业务对象表的统称。

SHACL 同时规定 shapes graph、data graph 和 RDF 结果图，目标是检查给定数据是否符合声明约束。[3] 因此一个实用分工是：用 OWL 表示概念和可蕴含关系，用 SHACL 表示交付、接口或写入前必须满足的约束。把 OWL 的开放世界可满足性直接当成闭世界业务合规检查，会遗漏必填、唯一性和时效等工程条件。

Neo4j 的属性图中，节点与关系均可携带键值属性；节点可有多个 label，关系具有方向和一个 type，schema 可按需求通过索引和约束逐步加入。[4] 它优先服务实体关联、局部遍历和应用工程，而 RDF/OWL 更擅长跨源标识、词汇对齐和可交换的形式语义。是否选属性图，不应仅由“是否有关系”决定，而应看查询工作负载、互操作诉求、推理深度和写入事务模型。

Palantir 的官方架构把 Ontology 描述为集成 data、logic、action、security 的 operational layer，因而它与 RDF 语法的根本差异不是“节点和边的名字不同”，而是对象模型与受权行动、函数和数据写回的紧耦合。[5] 该抽象可迁移为“语义对象图 + 受治理命令 + 可组合逻辑 + 安全策略 + 类型化开发接口”，但 Foundry 的 backing data source、动态安全求值与产品工具链不能被假定为公开标准。

Agent 本体目前没有统一标准。已有预印本尝试将领域本体编译为 Agent 必须通过的工具接口，从而在运行时而非事后对知识图谱修改施加约束；它证明了研究方向的可行性，但尚不足以替代事务、权限或人工审批机制。[6]

## 可复现基线

| 资产 | 用途 | 归档建议 |
|---|---|---|
| [Apache Jena](https://jena.apache.org/) | RDF、RDFS/OWL、SPARQL 基线 | 固定版本与示例 Turtle 数据 |
| [pySHACL](https://github.com/RDFLib/pySHACL) | shapes/data graph 验证与结果图 | 保存 shapes、输入快照和验证报告 |
| [Neo4j](https://github.com/neo4j/neo4j) | 属性图与 Cypher 对照实验 | 记录 RDF 映射假设和约束定义 |
| [W3C SHACL 测试套件](https://w3c.github.io/data-shapes/data-shapes-test-suite/) | 跨实现一致性验证 | 作为 CI 兼容性样本 |

## 未决问题与下一轮实验

需要构造同一领域的 RDF/OWL、SHACL、属性图和操作型对象模型，比较语义对齐成本、约束覆盖率、查询/推理延迟、写入失败可解释性和权限审计。对 Agent 约束还需额外测量越权工具调用、约束绕过、多 Agent 并发写入和事前/事后校验的差异；这些尚不是现有公开资料能够保证的结论。

## 参考资料

[1] [RDF 1.1 Concepts and Abstract Syntax](https://www.w3.org/TR/rdf11-concepts/)

[2] [OWL 2 Web Ontology Language: Document Overview](https://www.w3.org/TR/owl2-overview/)

[3] [Shapes Constraint Language (SHACL)](https://www.w3.org/TR/shacl/)

[4] [Neo4j Graph Database Concepts](https://neo4j.com/docs/getting-started/appendix/graphdb-concepts/)

[5] [Palantir Foundry: The Ontology System](https://palantir.com/docs/foundry/architecture-center/ontology-system/)

[6] [Ontology-to-tools Compilation for Executable Semantic Constraint Enforcement in LLM Agents](https://arxiv.org/abs/2602.03439)
