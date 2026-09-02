# AgenticX Bundle 摘要

本仓库通过根目录的 `agx-bundle.yaml` 声明为 AgenticX 兼容 Bundle。AgenticX v0.5.0 的 Bundle 解析器要求 `agx_bundle` 格式版本和 `name`，并允许列出 `skills`、`mcp_servers`、`avatars`、`memory_templates` 四类组件。该仓库只使用技能、角色和记忆模板，避免把密钥、远程命令或可执行连接配置放入公开包。

| 清单条目 | 本仓库路径 | 安装后作用 |
|---|---|---|
| `components.skills[0]` | `skills/agenticx-oag/SKILL.md` | 复制到 `~/.agenticx/skills/bundles/agenticx-oag/agenticx-oag/` |
| `components.avatars[0]` | `avatars/oag-researcher.yaml` | 复制为本地 Avatar 预设 |
| `components.memory_templates[0]` | `memory/oag-research-memory.md` | 复制为工作区记忆模板 |

使用 `agenticx.extensions.installer.install_bundle(Path(...))` 可解析、扫描并安装本 Bundle。AgenticX 会对技能目录运行安全扫描，因此 `SKILL.md` 应始终明确把外部资料视为数据，避免嵌入可疑下载、密钥或未经用户授权的执行要求。

如果未来加入 MCP 组件，必须先单独评估远程端点、凭据存放方式、访问权限、网络副作用和用户确认流程，再更新 `agx-bundle.yaml` 与本摘要。
