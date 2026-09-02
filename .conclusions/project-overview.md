# 项目概览

`agenticx-oag` 是一个公开的、无密钥依赖的 AgenticX AGX Bundle。它不实现搜索服务或独立运行时，而是提供一套将深度调研组织为可审计资产的方法：研究简报、轻量本体、来源登记、主张账本、推断记录、报告与质量审查。

核心理念是把 OAG（Ontology Augmented Generation）用于研究：对象和关系形成语义结构；来源、定位和证据等级形成可复核基础；事实、推断、争议和未验证项必须分离；对现实世界的行动始终处于显式审批边界之外。

| 模块 | 角色 | 主要消费者 |
|---|---|---|
| `agx-bundle.yaml` | 声明可安装的 Bundle 组件 | AgenticX Bundle parser/installer |
| `skills/` | 可执行的研究工作流与质量约束 | AgenticX Skill runtime 或人工研究者 |
| `memory/` | 研究会话的结构化持续状态 | AgenticX workspace memory |
| `avatars/` | 研究员角色与输出职责 | AgenticX avatar registry |
| `schemas/` | 主张账本的机器可读数据契约 | 验证、索引、后续工作流 |
| `docs/` 与 `examples/` | 方法说明与可复制起点 | 人类研究者和贡献者 |

第一版刻意不包含 MCP 服务器配置、API 密钥、抓取脚本或自动化行动。因此它可被审计、安全共享，并能与 AgenticX-DeepResearch 的 Basic/Advanced 流程组合：后者负责规划、检索、抓取、总结和收敛；本包负责输出的语义化、可追溯和行动边界。
