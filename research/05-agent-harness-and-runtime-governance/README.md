# 05 · Agent Harness 与运行时治理



本方向研究如何把本体、规则和检索结果变成 **Agent 在运行时可遵守、可观测、可审批的行为约束**。范围包括 Harness 架构、Graph / Loop 编排、工具接口与权限、状态和记忆、上下文退化、人工审批、轨迹审计、反思与自评估。



| 问题 | 预期交付 |

|---|---|

| Ontology、规则和 Context Pack 应分别在哪些运行时点位注入？ | 注入架构图 |

| Graph Engineering、Loop Engineering 与 Harness Engineering 的边界是什么？ | 编排模式对照与选型规则 |

| 工具白名单、参数约束、权限、审批和输出契约如何形成 Agent 本体？ | 工具治理策略模板 |

| 如何检测和缓解上下文累积造成的目标漂移、循环和“Agent 腐烂”？ | 状态/记忆卫生策略与指标 |

| 如何记录可复核轨迹，并进行自评估、反思和技能演化？ | 轨迹数据契约与审计清单 |



## 初始资料



用户提供了以下研究入口：



- [本体论落地中的 5 层 7 点错配及其注入 Agent Harness 的 4 个点位](https://mp.weixin.qq.com/s/MSBPwRx5PqqmwF0qwDq05Q?scene=1)
- 
- [3 Years of Graph Engineering with LangGraph](https://www.langchain.com/blog/3-years-of-graph-engineering-with-langgraph)
- 
- [Penguin Harness](https://github.com/Prism-Shadow/penguin-harness)
- 


其中本体注入 Harness 的文章目前是待核验线索；LangGraph 与 Penguin Harness 作为公开比较材料。后续不应把“使用图”直接等同于“已经治理 Agent”。



| 运行时点位 | 应注入的资产 | 关键审计记录 |

|---|---|---|

| 任务理解 | 领域术语、对象类型、允许问题范围 | Schema Linking 命中与拒答原因 |

| 规划与路由 | 任务状态、规则前置条件、可用工具 | 分支、循环次数和路由依据 |

| 工具调用 | 参数 Schema、权限和审批条件 | 调用前校验、审批事件与工具轨迹 |

| 上下文/记忆 | 已验证事实、未决问题、摘要 | 来源、版本、压缩和淘汰记录 |

| 结果与写回 | 规则检查、对象关系、输出契约 | 主张—来源映射、写回或拒绝记录 |



业务对象和 Action 的平台语义进入 `02`，Context Pack 的构造进入 `03`，领域规则的生产与执行进入 `04`。

## 已审核交付物

- [`deliverables/proposal-to-action-governance-boundary.md`](deliverables/proposal-to-action-governance-boundary.md)：基于公开标准和官方资料，明确 P08 提案门禁、P09 对象级授权、P07 审批与 Action 执行之间不可互相替代的职责；补充 Proposal/可信上下文分离、可信对象快照、防绕过接口和验收矩阵。
- [`deliverables/semantica-static-code-review.md`](deliverables/semantica-static-code-review.md)：固定公开源码版本的静态能力审阅与集成边界。
