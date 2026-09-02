# OAG / Palantir Ontology 研究总索引



本目录是 `agenticx-oag` 的长期研究工作区。它围绕 **Palantir Ontology、Ontology-Augmented Generation（OAG）及其向 AgenticX / Near 技能转化的路径**组织资料、代码、论文、阅读笔记和已审核交付物。目录的首要原则是：**每个编号目录只有一个主研究对象，资料只选择一个主归档位置**；跨主题使用来源 ID 或链接引用，而不复制同一份结论。



> `research/` 原则上不存放未经确认可再分发的原文附件、付费资料或受限内容。用户明确要求将其提供的《本体论紫皮书》解析为 Markdown 后保存，故当前仓库保留该**文本层解析稿**，同时在文件首部明确标注来源、版权/再分发状态未核验及仅限研究引用。请勿将该解析稿视为开放许可材料或在未获得权利确认的情况下再分发。其余受限资料仍以来源登记、访问链接、可审计摘录和研究结论的方式归档。
> 


## 研究地图



| 目录 | 主问题 | 边界说明 |

|---|---|---|

| [`01-foundations-and-paradigm-boundaries`](01-foundations-and-paradigm-boundaries/) | “本体”在不同工程语境究竟指什么？ | 负责概念、范式、术语和四类本体的边界；不研究特定平台实施细节。 |

| [`02-palantir-ontology-platform`](02-palantir-ontology-platform/) | Palantir 如何以对象、链接、动作、函数和安全构成操作型本体？ | 负责平台对象模型、治理、开发接口和决策闭环；不研究通用检索算法。 |

| [`03-oag-retrieval-and-context-engineering`](03-oag-retrieval-and-context-engineering/) | OAG 如何检索、组织和注入可靠上下文？ | 负责分块、索引、检索、查询改写、混合检索、Ontology Query 与 Text2Cypher。 |

| [`04-rules-reasoning-and-knowledge-production`](04-rules-reasoning-and-knowledge-production/) | 如何生产、治理、执行和演化可执行规则知识库？ | 负责规则表示、抽取、冲突、更新、执行与审计；不负责 Agent 编排。 |

| [`05-agent-harness-and-runtime-governance`](05-agent-harness-and-runtime-governance/) | 如何把本体和规则注入 Agent Harness 并治理运行时行为？ | 负责工具、权限、审批、记忆、图/循环编排、轨迹和上下文治理。 |

| [`06-evaluation-selection-and-case-studies`](06-evaluation-selection-and-case-studies/) | 如何比较方案、验证价值并落地到 AgenticX / Near？ | 负责选型、评估、案例、复盘与验收；不承载新的底层机制研究。 |



## 第一轮深度研究成果



第一轮调研已经覆盖六个主方向。各方向的结论、证据边界、可复现实验入口与参考资料见下表；所有事实性结论均应回溯到文内的原始 URL 或标准/论文引用。



| 方向 | 深度研究笔记 | 主要覆盖 |

|---|---|---|

| 01 | [`DEEP_RESEARCH.md`](01-foundations-and-paradigm-boundaries/DEEP_RESEARCH.md) | RDF/OWL、SHACL、属性图、操作型本体和 Agent 约束的边界 |

| 02 | [`DEEP_RESEARCH.md`](02-palantir-ontology-platform/DEEP_RESEARCH.md) | Object/Link/Action/Function、OSDK、MCP 与可迁移抽象 |

| 03 | [`DEEP_RESEARCH.md`](03-oag-retrieval-and-context-engineering/DEEP_RESEARCH.md) | RAG、OG-RAG、HyDE、GraphRAG、Text2Cypher 与 Context Pack |

| 04 | [`DEEP_RESEARCH.md`](04-rules-reasoning-and-knowledge-production/DEEP_RESEARCH.md) | SHACL、SWRL、DMN、Datalog/Soufflé 与规则溯源 |

| 05 | [`DEEP_RESEARCH.md`](05-agent-harness-and-runtime-governance/DEEP_RESEARCH.md) | 状态、记忆、工具、审批、Guardrails、MCP 与 Trace |

| 06 | [`DEEP_RESEARCH.md`](06-evaluation-selection-and-case-studies/DEEP_RESEARCH.md) | RAG/Agent 评测、风险、成本、回滚与 Near 接入契约 |



用户提供 PDF 的完整文本层解析稿位于 [`01/.../sources/ontology-whitepaper-4/ontology-whitepaper-4-extracted.md`](01-foundations-and-paradigm-boundaries/sources/ontology-whitepaper-4/ontology-whitepaper-4-extracted.md)。六方向的结构化研究底稿（包含来源、论文、代码、已核验事实与限制）位于 [`_catalog/round-1-parallel-research.json`](_catalog/round-1-parallel-research.json)。



## 标准子树



每个编号目录采用相同的资料生命周期结构。`sources/` 记录来源与访问状态；`papers/` 记录论文和可再分发文件；`code/` 记录复现代码、外部仓库链接或子模块说明；`notes/` 存放带来源 ID 的阅读卡和问题树；`deliverables/` 仅存放经质量审查的专题报告、矩阵、图或可转化为 Skill 的资产。



```text

<direction>/

├── README.md

├── sources/

├── papers/

├── code/

├── notes/

└── deliverables/

```



## 共享目录



`_catalog/` 不是研究方向，而是全局基础设施。`source-register.md` 是唯一权威的来源登记簿；`taxonomy-and-boundaries.md` 给出归档裁决规则；`intake-backlog.md` 收录尚未完成专题落位或仅具背景相关性的线索。任何编号目录中的笔记都应优先引用 `SRC-*`，而不要重新复制完整书目信息。



## 新资料的收录流程



新资料先登记到 `_catalog/source-register.md`，记录来源、发布日期、访问日期、许可/再分发状态和建议主目录。随后在对应方向的 `sources/` 或 `notes/` 中写入带 `SRC-*` 的阅读卡。资料同时涉及多个方向时，按**研究问题的主要对象**归档：研究对象/动作/安全放入 `02`，检索与上下文放入 `03`，规则生产放入 `04`，运行时 Harness 放入 `05`，跨方案比较和验收放入 `06`。只有在形成新结论时，才将其提升到 `deliverables/`。



## 初始资料



首批资料包括用户提供的《本体论紫皮书》、两篇规则推理公众号文章、关于本体注入 Agent Harness 的文章线索，以及 Palantir 官方 Ontology、OAG 与 Action 文档。它们已在 [`_
