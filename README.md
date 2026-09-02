# AgenticX-OAG

> **面向 AgenticX 的本体增强生成（Ontology Augmented Generation, OAG）深度调研包。**

`AgenticX-OAG` 将深度调研从“搜集并总结网页”扩展为可验证的**对象、关系、证据、推断与行动边界**。其目标是把复杂议题沉淀为可审计、可复用、可由 AgenticX 调用的研究资产，而非只生成一次性的文本结论。

Palantir 将 OAG 描述为一种以本体为锚点、较 RAG 更强调决策的方式：模型可结合数据、确定性逻辑与受控行动，同时将结论追溯至业务对象与来源。[1] AgenticX 支持以 AGX Bundle 打包技能、记忆模板、角色预设和 MCP 配置，因此本仓库以无外部密钥、可离线审计的 Bundle 形式发布研究方法。[2] [3]

| 维度 | 本仓库的约定 |
|---|---|
| **研究单位** | 研究问题、对象、关系、主张、证据、推断、行动边界 |
| **核心产出** | 来源清单、主张账本、轻量本体、研究报告与质量审查记录 |
| **证据要求** | 每项关键主张必须链接可定位来源，并标记证据强度和时效性 |
| **安全边界** | 区分“事实”“模型推断”“待验证假设”；不把检索结果直接变成可执行行动 |
| **AgenticX 接入** | 以 AGX Bundle 安装研究技能、记忆模板和研究员角色预设 |

## 适用场景

本项目适合研究需要跨来源综合、实体关系梳理和结论可审计性的主题。例如，企业战略、产品生态、产业链、公共政策、技术路线或竞争情报。它不提供某一领域的事实数据库，也不替代高风险场景中的专业判断。

## 研究闭环

```text
问题界定 → 候选对象/关系 → 检索与来源筛选 → 证据抽取
    → 主张账本 → 轻量本体 → 推断与行动边界 → 研究报告 → 质量审查
```

每轮研究均应记录“哪些信息已被证实、哪些关系只是推断、还缺少什么证据”。高级研究任务可将知识缺口重新转化为下一轮查询，从而与 AgenticX-DeepResearch 的规划、搜索、总结、反思和收敛模式对齐。[4]

## 快速使用

### 作为 AgenticX Bundle 使用

本仓库根目录的 `agx-bundle.yaml` 遵循 AgenticX 的 Bundle 清单格式。安装器会将技能安装到 `~/.agenticx/skills/bundles/<bundle-name>/`，并将记忆模板安装到 `~/.agenticx/workspace/memory_templates/<bundle-name>/`。[2] [3]

```python
from pathlib import Path
from agenticx.extensions.installer import install_bundle

result = install_bundle(Path("/path/to/agenticx-oag"))
assert result.success, result.error
```

安装后，为研究任务加载 `agenticx-oag` 技能；任务运行期间可使用 `memory/oag-research-memory.md` 保存对象、关系、主张和未决问题。具体的研究执行协议见 [`skills/agenticx-oag/SKILL.md`](skills/agenticx-oag/SKILL.md)。

### 作为独立研究规范使用

无需安装任何软件。复制 [`examples/research-case-template.md`](examples/research-case-template.md)，依次完成研究范围、证据记录、轻量本体、主张账本与质量门控。机器可读主张结构由 [`schemas/claim-ledger.schema.json`](schemas/claim-ledger.schema.json) 定义。

## 仓库结构

```text
.
├── agx-bundle.yaml                       # AgenticX AGX Bundle 清单
├── skills/agenticx-oag/SKILL.md     # 可执行的 OAG 调研方法
├── memory/oag-research-memory.md         # 研究工作记忆模板
├── avatars/oag-researcher.yaml           # 研究员角色预设
├── schemas/claim-ledger.schema.json      # 主张账本 JSON Schema
├── examples/research-case-template.md    # 可复制的调研个案模板
├── docs/research-method/oag-research-protocol.md
└── .conclusions/                         # 面向人类与智能体的模块摘要
```

## 贡献原则

欢迎提交新的领域本体、研究模板或评价用例。请避免提交未授权的受限数据、机密信息或含有密钥的连接配置。所有新增研究结论应尽量提供一手来源、清晰的时间范围与可复核引用。

## 许可证

本项目采用 [Apache License 2.0](LICENSE)。

## 参考资料

[1] [Palantir, *Building with Palantir AIP: Data Tools for RAG / OAG*](https://blog.palantir.com/building-with-palantir-aip-data-tools-for-rag-oag-b3b509c8b0f3)

[2] [AgenticX, AGX Bundle manifest implementation](https://github.com/DemonDamon/AgenticX/blob/main/agenticx/extensions/bundle.py)

[3] [AgenticX, AGX Bundle installer implementation](https://github.com/DemonDamon/AgenticX/blob/main/agenticx/extensions/installer.py)

[4] [AgenticX-DeepResearch](https://github.com/DemonDamon/AgenticX-DeepResearch)
