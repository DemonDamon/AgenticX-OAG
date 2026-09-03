# Pending Plans（未实施）

本目录存放**新建落盘、尚未开工实施**的 plan，供全员共享 backlog。总规划（DAG 与 subplan 注册表）见 `docs/enterprise-landing.md`「Subplan 拆解与 DAG 执行路径」一节。

## 落盘规则（默认）

- **所有新写的 plan 必须先放到本目录**，不要直接写到 `.cursor/plans/` 根目录。
- 命名遵循：`YYYY-MM-DD-<feature-name>.plan.md`。
- plan 顶部（标题之后）记录规划模型：`Planned-with: <模型>`；并给出推荐实施模型 `Suggested-Impl-Model: <模型/档位>`。
- 定稿后随代码一起 commit。

## 与根目录的分工

| 位置 | 用途 |
|------|------|
| `.cursor/plans/pending/` | **新建 plan 的默认落点**；规划完成、暂不实施 backlog |
| `.cursor/plans/*.plan.md`（根目录） | 正在实施 / 已随代码提交的 plan |

## 开始实施时

1. 将对应 plan **移回** `.cursor/plans/` 根目录（便于 Cursor plan todo UI，以及 commit trailer `Plan-File: .cursor/plans/<name>.plan.md` 与既有约定一致）。
2. 按该 plan 开分支实施，commit 带 `Plan-Id` / `Plan-File` / `Plan-Model` / `Impl-Model` / `Made-with: Damon Li` trailer（白名单仅此五个，顺序自上而下）。

## 质量门槛

Plan 必须「Composer 2.5 可独立高质量实施」：精确落点（路径+类名+锚点）、before/after 代码意图、根因与证据链入正文、每条 FR 配可执行 AC、显式 In/Out scope、细节写全不留推断。判据：实施模型若需反问「改哪个文件/怎么验证」则不达标。

## 注意

- 勿在 plan 标题/正文/文件名中写入客户名称或可识别标识（用中性表述）。
- commit / PR 信息严禁第三方品牌与对标措辞；plan 正文作为内部文档可保留必要的调研引用。
- 勿把密钥、凭据写进 plan。
- 仅放「打算做」的 plan；纯草稿可先本地保留，定稿后再放入本目录并提交。
