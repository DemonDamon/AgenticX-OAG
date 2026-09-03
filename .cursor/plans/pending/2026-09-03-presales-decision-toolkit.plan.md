---
name: "P01 售前决策工具包：本体四象决策树 + 场景匹配表"
overview: "把《本体论紫皮书》四象框架做成可交互单文件 HTML 售前物料 + 配套话术手册，用于第一次客户会议的需求定位。"
todos: []
isProject: false
---

# P01 售前决策工具包 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
>
> Planned-with: glm 5.3
> Suggested-Impl-Model: 便宜档（静态页样板，如 Composer/Fast 档或代码专精便宜档）——纯 HTML/CSS/vanilla JS 单文件，无构建链路，无需强推理

**Goal:** 第一次客户会议不谈产品，先用决策树四问定位客户需求落在哪个本体象限。本 plan 把该开场工具做成可离线使用、可打印导出的交互物料，并配套一份话术手册。

**Architecture:** 单文件 HTML（内联 CSS/JS，零依赖零构建）+ 一份 Markdown 话术手册。内容源为仓库根目录《刘焕勇.老刘说NLP技术社区.本体论紫皮书：四.md》第 7/8 章（四维对比矩阵、决策树、16 场景表、组合模式、选型误区）与 `docs/enterprise-landing.md` v0.2 的四象定位表。

**Tech Stack:** HTML5 / CSS3 / vanilla JS（无框架、无构建）

---

## 背景与动机（证据链）

- `docs/enterprise-landing.md` v0.2 §一点五规定：售前对话先过决策树四问，POC 只主打一个象限；§二阶段一将「决策树+16 场景表做成售前物料」列为 POC 第 0 步交付物。
- 紫皮书 8.1 决策树（逐层二分：逻辑推理→Semantic / 多跳关联→KG Schema / 操作闭环→Palantir 式执行层 / Agent 约束→治理层）、8.2 十六场景表、8.4 四大误区是物料的内容源；紫皮书解析版已落盘仓库根目录（153 页全量）。
- 该物料无任何后端依赖，不阻塞引擎开发，是**唯一可立即启动**的 subplan（DAG 独立轨道）。

## 需求定义

### FR（Functional Requirements）

- **FR-1 决策树四问交互**：单页依次呈现 Q1~Q4（Q1 需要逻辑推理吗 / Q2 需要多跳关联查询吗 / Q3 需要操作执行闭环吗 / Q4 需要约束 Agent 行为吗），每问只有 是/否 两个按钮；任一问答「是」即终止并输出对应象限推荐（Q1→Semantic Ontology、Q2→KG Schema、Q3→执行层、Q4→治理层）；四问全「否」输出兜底建议（默认治理层，按紫皮书决策树）。
- **FR-2 象限结果页**：每个象限展示——核心命题（一句话）、典型技术栈、我们的角色映射（`docs/enterprise-landing.md` §一点五表格内容：卖什么/不卖什么/走生态接口）、推荐 POC 类型（检索型/操作闭环型/治理型/转生态合作）。
- **FR-3 16 场景匹配表**：完整呈现紫皮书 8.2 的 16 行场景表（业务场景/核心需求/推荐本体论/选型理由），支持按象限 tab 筛选 + 顶部关键词搜索框（前端过滤，子串匹配即可）。
- **FR-4 组合模式说明区**：展示紫皮书 8.3 三种组合模式（知识层+查询层 / 数据层+执行层 / 业务层+治理层）的文字流程图，与「组合是演进而来的，不是设计出来的」演进原则。
- **FR-5 四大红线区**：紫皮书 8.4 四大误区逐条呈现，每条配「售前话术：遇到该诉求如何回应」。
- **FR-6 打印/PDF 友好**：`@media print` 下隐藏交互按钮与搜索框、展开全部 16 行、单色打印无背景色破碎；浏览器「打印→存为 PDF」产出可直接发客户的物料。
- **FR-7 话术手册**：`docs/presales/four-quadrant-playbook.md`，含开场白模板（四问引导词）、每象限 3 分钟讲解稿、组合演进路径图（mermaid 或 ASCII）、四红线应答话术、常见客户异议 Q&A（≥8 条）。

### NFR（Non-Functional Requirements）

- **NFR-1** 单文件 HTML ≤ 150KB，离线双击可开。
- **NFR-2** 深浅双主题，默认浅色（投屏售前场景）。
- **NFR-3** 移动端宽度 ≥ 375px 可用（客户手机查看）。

## 精确落点

| 改动 | 路径 | 说明 |
|---|---|---|
| 新建交互物料 | `presales/quadrant-decision-toolkit.html` | 单文件，全部内联 |
| 新建话术手册 | `docs/presales/four-quadrant-playbook.md` | 手册 |
| 内容源引用 | 仓库根《刘焕勇.老刘说NLP技术社区.本体论紫皮书：四.md》 | 只读，不修改 |
| 入口链接 | `docs/enterprise-landing.md` §一点五末尾 | 加一行物料链接（由 P01 实施时补） |

## 关键实现意图

决策树状态机（vanilla JS，示意）：

```js
const QUESTIONS = [
  { id: "Q1", text: "需要逻辑推理吗？", hint: "隐含知识派生 / 分类推理 / 概念间传递互斥", yes: "semantic" },
  { id: "Q2", text: "需要多跳关联查询吗？", hint: "实体间 N 跳路径发现，关联路径 > 2 跳", yes: "kg" },
  { id: "Q3", text: "需要操作执行闭环吗？", hint: "Action 改变业务对象状态 / 需要审批 / 需要回滚", yes: "execution" },
  { id: "Q4", text: "需要约束 Agent 行为吗？", hint: "权限约束 / 行为审计", yes: "governance" },
];
// state: { step: 0, answers: [] }；答「是」→ renderResult(QUADRANT[questions[step].yes])；
// 答「否」→ step+1；step 越界 → renderResult(QUADRANT.governance /* 默认兜底 */)
```

16 场景表数据结构（内嵌 JSON，与紫皮书 8.2 逐行对齐，行内容照抄解析版 page_0139）：

```js
const SCENARIOS = [
  { no: 1, scene: "临床术语标准化", need: "概念分类推理", quadrant: "semantic", reason: "SNOMED CT 本身即 OWL 本体，需要传递推理确定术语层级" },
  { no: 2, scene: "反欺诈关联分析", need: "多跳路径发现", quadrant: "kg", reason: "需要发现人-账户-设备-地址间的隐式团伙关联" },
  // ...共 16 行，第 16 行（智能客服）quadrant 为 "combo"
];
```

## In scope / Out of scope

**In scope：** 上述 FR-1~FR-7；物料内配色与 `docs/` 现有文档风格大致协调即可。
**Out of scope（no-scope-creep）：** 不做后端、不做用户行为埋点、不做多语言、不改紫皮书解析版与 enterprise-landing.md 既有章节内容（只加一行链接）、不做品牌视觉规范。

## 验收标准（AC）

| FR | AC | 验证方式 |
|---|---|---|
| FR-1 | 依次答 Q1~Q4 全「否」得到治理层兜底；Q2 答「是」得到 KG 象限 | 手动走查 `open presales/quadrant-decision-toolkit.html` |
| FR-2 | 四象限结果页各含「卖什么/不卖什么」映射 | 手动走查，对照 enterprise-landing.md §一点五表格 |
| FR-3 | 搜索「反欺诈」命中场景 2；点 KG tab 后仅剩 KG 行 | 手动走查 |
| FR-4 | 三种组合模式各有一行文字流程（A → B 说明箭头） | 手动走查 |
| FR-5 | 四红线各配售前话术段落 | 手动走查 |
| FR-6 | Chrome 打印预览：无按钮残影、16 行全展开 | 手动打印预览 |
| FR-7 | 手册含开场白、四象限讲解稿、Q&A≥8 条 | 评审 `docs/presales/four-quadrant-playbook.md` |
