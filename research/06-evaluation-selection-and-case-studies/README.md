# 06 · 选型、评估与案例



本方向承载跨专题的“最后一公里”：**在特定业务、数据、治理和 Agent 约束下，应选择什么组合，如何验证其效果，以及如何交付到 AgenticX / Near。** 它只整合和评价 `01` 至 `05` 的结论，不重复开展原始平台、检索、规则或 Harness 机制研究。



| 问题 | 预期交付 |

|---|---|

| 四种本体范式在什么条件下应分别采用或组合？ | 场景—能力—成本选型矩阵 |

| OAG 如何同时评测检索、证据追溯、规则正确性、行动安全和人机协作？ | 分层评估框架与 EvalSet |

| 在制造、供应链、合规、医疗、科研等案例中，何时需要操作型本体或规则治理？ | 行业案例卡与反例库 |

| 如何把审核过的研究结论封装为 AgenticX Skill 并在 Near 安装、调用与验收？ | Near 集成验收清单 |

| 如何评估成本、延迟、治理风险、维护负担与组织适配度？ | TCO / 风险复盘模板 |



## AgenticX / Near 接入规则



只有各专题的已审核交付物才可进入 `agenticx-oag` Skill、角色预设或记忆模板。工作笔记、待核验网页和未分流线索不能被当作权威运行时上下文。每项进入技能的事实或规则必须保留来源、范围、版本与不确定性。



| 资产 | 进入 Near 前的最低条件 | 验收证据 |

|---|---|---|

| 概念或平台结论 | 来源、范围和相邻范式边界 | 术语审查与链接检查 |

| 检索策略 | 可复现配置、任务与失败案例 | 召回和证据定位评测 |

| 可执行规则 | 原文定位、版本、冲突和审批状态 | 回归用例与解释轨迹 |

| 工具 / Action 策略 | 参数 Schema、权限、审批与副作用 | 拒绝路径和人工审批演练 |

| 记忆或 Context Pack | 来源标记、保留/淘汰与时效规则 | 长任务退化与更新测试 |



四类本体的对比与选型必须以公开标准、公开实现和项目评测为依据。后续每个行业案例都须清楚注明公开来源、适用前提、失败边界和与 AgenticX / Near 的实际兼容性；受限资料不得作为唯一证据或随仓库分发。

## 已审核交付物

- [`deliverables/ontology-engineering-practice-synthesis.md`](deliverables/ontology-engineering-practice-synthesis.md)：将语义模型、受控执行、Agent 门禁、审计回放和生产质量门整理为项目内工程框架，并映射到 OE-01～OE-11。
- [`deliverables/enterprise-ontology-and-tooling-roadmap.md`](deliverables/enterprise-ontology-and-tooling-roadmap.md)：企业本体与工具层的参考架构和落地路线。
- [`deliverables/ontology-open-source-tool-landscape.md`](deliverables/ontology-open-source-tool-landscape.md)：公开开源实现的能力分层、选型边界和最小试验建议。
