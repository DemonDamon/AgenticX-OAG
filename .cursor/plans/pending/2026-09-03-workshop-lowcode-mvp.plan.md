---
name: "P11 Ontology Workshop 低代码平台 MVP：Object View 生成器 + App Builder + Explorer"
overview: "落地应用层（第三层）：engine-api 薄服务（FastAPI 通用端点）+ TypeScript 全栈 Workshop（tRPC），实现本体驱动的 Object View 自动生成、页面搭建器与渲染运行时、图谱浏览器与全局搜索。业务人员 30 分钟搭建业务应用。"
todos: []
isProject: false
---

# P11 Ontology Workshop 低代码平台 MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
>
> Planned-with: glm 5.3
> Suggested-Impl-Model: 代码专精中档偏强（全栈双服务 + 生成器确定性规则 + 拖拽交互；ViewSchema 生成规则与 app JSON 契约已写全，交互实现自由度大但需对照原型骨架）

**Goal:** 交付 `docs/enterprise-landing.md` 第三层「Ontology Workshop」的 MVP 与 `docs/roadmap.md` Phase 5 验收：「非技术用户能在 30 分钟内，基于 bank-aml 本体搭建一个『可疑交易监控看板』应用，包含列表、详情、审批操作」。三个子能力：**Object View 生成器**（本体 YAML → 列表/详情/表单页 schema 自动生成）、**App Builder**（拖拽编排页面 → app JSON → 渲染运行时）、**Explorer**（schema 级图谱浏览 + 跨类型全局搜索）。所有组件绑定本体对象，天然结构化可追溯——「企业买的不是引擎，是用引擎搭出来的业务应用」。

**Architecture:** 双服务：① `apps/engine-api/`（FastAPI 薄服务）——引擎包（P03/P04）的通用 HTTP 门面：`/ontology`、`/objects`、`/graph`、`/perm`、`/action`（代理 P07）。通用端点与 P10 Demo 后端同构但不共享代码（Demo 是演示应用、engine-api 是平台地基；参考 P10 的 `deps.py` 装配模式实现）。② `workshop/`（TS 全栈，复用 `prototype/ontology-gateway-prototype/` 的 pnpm+tRPC+drizzle 骨架结构，**拷贝骨架起步、不在 prototype 目录内改动**）——tRPC BFF 转发 engine-api，前端 React 三区（搭建器/运行时/Explorer）。跨语言契约：`make proto-ts` 从 P02 的 ontology.proto 生成 TS 类型到 `workshop/shared/gen/`，Object View 生成器与前端共用类型。

**Tech Stack:** Python 3.11 / FastAPI（engine-api）；TypeScript / React 18 / Vite / tRPC v11 / zustand / d3-force / pnpm（workshop）；protoc-gen-ts（proto → TS）

---

## 背景与动机（证据链）

- `docs/enterprise-landing.md` 第三层 Ontology Workshop：拖拽式搭建本体驱动业务应用；Object View 生成器（基于对象类型自动生成列表/详情/表单页）；组件库全部绑定本体对象；搭建的应用直接继承本体权限、审批、审计能力。「关键认知：企业买的不是引擎，是『用引擎搭出来的业务应用』。」
- `docs/enterprise-landing.md` 阶段三（平台化推广）：「推广 Workshop 低代码，让业务部门自己搭应用」。
- `docs/roadmap.md` Phase 5 交付物 1（Ontology Manager UI 的图谱浏览部分）、3（App Builder：Object View 生成器 + 组件库 + 拖拽 + 权限继承）、4（Explorer Dashboard：全局搜索 + 决策看板 + 审计追踪——本 plan 取全局搜索与图谱浏览，决策看板/审计追踪依赖 P09 数据流留后续）。「复用现有 `prototype/ontology-gateway-prototype/` 的 React + tRPC 全栈代码」。
- P02 plan Out of scope 已声明：「不做 proto 的 TS 生成（P11 需要时再加）」——本 plan 是该决策的执行方。
- P02 plan：「P03/P04/P05/P07/P08/P09/P11 均可并行开工」——本 plan 对 P03 的依赖是**软依赖**：TS 包骨架、proto-ts、Explorer 的 schema 图可先行；本体加载与对象数据端点联调需 P03/P04 交付。DAG 注册表已如实标注（见 enterprise-landing.md §8）。

## 需求定义

### FR（Functional Requirements）

- **FR-1 engine-api 服务**：`apps/engine-api/app/main.py`（FastAPI）——`GET /ontology`（YAML 解析为 JSON：object_types/link_types/action_types）、`GET /objects/{object_type}?q=&limit=&offset=`、`GET /objects/{object_type}/{object_id}`（含 2 跳邻居摘要）、`GET /graph/schema`、`GET /graph?object_id=&hops=`（全部桥接 P03/P04 引擎包，装配模式参照 P10 `deps.py`）；`GET /health`。鉴权：静态 Bearer token（`OAG_ENGINE_API_TOKEN`），未带 token 401。
- **FR-2 proto-ts 生成**：根 Makefile 增 `proto-ts` 目标——`protoc --plugin=protoc-gen-ts --ts_out=workshop/shared/gen -I proto proto/agenticx_oag/ontology/v1/ontology.proto`；生成 `workshop/shared/gen/ontology/v1/ontology.ts`（含 ObjectType/LinkType/ActionType/Ontology 接口）；幂等（二次执行 diff 为空）。生成产物提交入库。
- **FR-3 Object View 生成器**：`workshop/server/src/objectview/generate.ts`——输入 `ObjectType`（proto-ts 类型）+ `LinkType[]`，输出 `ViewSchema`（契约见「关键实现意图」）。生成规则（确定性，逐条照写）：① `listView.columns` = primary_key 属性在前 + 其余前 5 个非描述属性；`primaryField` = primary_key[0]；② 枚举属性（`enum_values` 非空）→ `listView.filters` 一项（op: eq, options: enum_values）且 `formView` 用 `select` widget；③ `detailView.relations` = 以该类型为 source 或 target 的全部 link_types（标注方向）；④ `required: true` 属性 → formView 必填；⑤ `data_type` → widget 映射：STRING→input、DOUBLE/INT64→number、BOOL→switch、TIMESTAMP→datepicker、JSON→textarea。提供 `workshop/server/src/objectview/generate.test.ts` 快照测试（bank-aml Customer 的 ViewSchema 与 plan 给出的期望一致）。
- **FR-4 tRPC BFF**：`workshop/server/src/trpc/`——routers：`ontologyRouter`（`list: /ontology`、`getViewSchema(objectType)`：调 FR-3 生成器并缓存）、`objectsRouter`（list/get/search 代理 engine-api）、`graphRouter`（schema/instance 代理）、`appRouter`（`saveApp / listApps / getApp`：app JSON 存 drizzle SQLite `apps` 表——复用原型 drizzle 栈）。engine-api 地址经环境变量 `ENGINE_API_URL` 注入（默认 `http://localhost:7581`）。
- **FR-5 组件库**：`workshop/src/components/blocks/`——`ObjectTable`（列/筛选按 ViewSchema 渲染，行点击进详情）、`ObjectDetail`（属性分区 + relations 列表，关联对象可点击跳转）、`ObjectForm`（按 formView 渲染，提交仅本地状态——写回留 P07 集成，本 MVP 表单提交弹「已记录（写回需接 Action Gateway）」提示）、`StatCard`（对某 object_type 的 count 或某枚举值计数）、`SectionCard`（静态文本容器）。全部组件 props 声明 `bind: {objectType, viewRef}`，数据从 tRPC 拉。
- **FR-6 App Builder（搭建器）**：`workshop/src/builder/`——三区布局：左「组件面板」（blocks 列表 + 本体对象类型列表，拖入画布即生成该类型的 ObjectTable/Detail/Form 实例）；中「画布」（垂直堆叠布局，块可上下移/删除/属性微调——属性面板仅标题与数据条数限制）；右「属性面板」。输出 app JSON（契约见「关键实现意图」）保存到 `appRouter.saveApp`。**不做自由网格拖拽**（垂直堆叠 + 顺序调整即满足「监控看板」验收，复杂布局后续）。
- **FR-7 渲染运行时**：`workshop/src/runtime/AppRenderer.tsx`——输入 app JSON，按 pages/blocks 递归渲染组件树；顶部 tab 切换 pages。运行时入口路由 `#/app/{appId}` 与搭建器 `#/builder/{appId}` 共用一套 blocks 组件。
- **FR-8 Explorer**：`workshop/src/explorer/`——① Schema 图谱：`GET /graph/schema` → d3-force SVG，ObjectType 为节点、LinkType 为边（类型着色图例），点击节点显示属性表；② 实例浏览：选 ObjectType → ObjectTable → 行点击展开 2 跳邻居子图（复用 GraphCanvas 思路）；③ 全局搜索框：`objectsRouter.search`（跨类型关键词，engine-api `/objects?q=` 按类型并发查询合并）。
- **FR-9 权限标注**：app JSON 每个 block 附 `requires: {objectType, permission}`（生成器自动填 `read`；ObjectForm 自动填 `write`）；运行时渲染前经 `permRouter.check`（engine-api `/perm` 代理 P09，P09 未接入时 engine-api 返回 `{available: false}` → 前端全量渲染 + 顶栏黄条提示「治理未接入」）。
- **FR-10 Action 集成（可选）**：ObjectDetail 的 relations 区与 ObjectForm 提交按钮支持配置「绑定 ActionType」；配置后点击 → `actionRouter.propose`（engine-api `/action` 代理 P07，P07 未启用时同样走 `available: false` 降级提示）。
- **FR-11 30 分钟走查文档**：`docs/workshop-walkthrough.md`——以「可疑交易监控看板」为样例的搭建步骤手册（创建 App → 拖入 Transaction ObjectTable（riskLevel=high 筛选）→ 拖入 StatCard（可疑交易数）→ 拖入 Customer ObjectDetail → 保存 → 运行时查看），含每步截图位。这是 Phase 5 验收的复现脚本。

### NFR（Non-Functional Requirements）

- **NFR-1** ViewSchema 生成纯函数、确定性（同输入同输出），快照测试锁定。
- **NFR-2** engine-api 与 workshop 均可 `make` 一键起（`make engine-api` / `make workshop`）；与 P02 dev 环境共用 docker PG+AGE。
- **NFR-3** 前端构建产物 gzip < 500KB；d3-force 按需 import。
- **NFR-4** app JSON 是版本化契约（`version: 1`），渲染器向后兼容 v1。

## 精确落点

| 改动 | 路径 |
|---|---|
| engine-api | `apps/engine-api/app/{main.py,deps.py,routers/{ontology,objects,graph,perm,action}.py}`、`requirements.txt`、`tests/test_api.py`（新建） |
| proto-ts | Makefile `proto-ts` 目标；`workshop/shared/gen/ontology/v1/ontology.ts`（生成后提交）（修改+新建） |
| ViewSchema 生成器 | `workshop/server/src/objectview/generate.ts` + `generate.test.ts`（新建） |
| tRPC BFF | `workshop/server/src/trpc/{trpc.ts,routers/{ontology,objects,graph,app,perm,action}.ts}`（新建） |
| drizzle | `workshop/server/src/db/schema.ts` 增 `apps` 表（id/title/json/updated_at）（骨架拷贝后修改） |
| 组件库 | `workshop/src/components/blocks/{ObjectTable,ObjectDetail,ObjectForm,StatCard,SectionCard}.tsx`（新建） |
| 搭建器 | `workshop/src/builder/{BuilderPage,ComponentPalette,Canvas,PropertyPanel}.tsx`（新建） |
| 运行时 | `workshop/src/runtime/AppRenderer.tsx`（新建） |
| Explorer | `workshop/src/explorer/{ExplorerPage,SchemaGraph,InstanceGraph,GlobalSearch}.tsx`（新建） |
| 走查文档 | `docs/workshop-walkthrough.md`（新建） |
| 构建 | 根 Makefile 增 `engine-api / workshop / proto-ts`（修改）；README 快速开始增补（修改） |
| 骨架来源 | `cp -r prototype/ontology-gateway-prototype/{package.json,pnpm-lock.yaml,vite.config.ts,tsconfig.json,server,shared,drizzle*} workshop/` 后裁剪（demo/todo 相关 router 删除） |

## 关键实现意图

**ViewSchema 契约（生成器输出，前后端共用类型）**：

```typescript
interface ViewSchema {
  objectType: string;
  listView: {
    columns: string[];              // primary_key 在前
    filters: { field: string; op: "eq"; options: string[] }[];
    primaryField: string;
    defaultLimit: number;           // 20
  };
  detailView: {
    sections: { title: string; fields: string[] }[];   // "基本信息"（前 6 属性）+ "其他属性"
    relations: { linkType: string; direction: "out" | "in"; targetType: string }[];
  };
  formView: {
    fields: { name: string; widget: "input" | "number" | "select" | "switch" | "datepicker" | "textarea";
              options?: string[]; required: boolean }[];
  };
}
```

**bank-aml Customer 期望快照（generate.test.ts 断言核心，属性以 P03 ontology.yaml 实际为准，实施时校正字段名）**：

```json
{
  "objectType": "Customer",
  "listView": {
    "columns": ["customerId", "name", "riskLevel", "region", "accountTier"],
    "filters": [{ "field": "riskLevel", "op": "eq", "options": ["high", "medium", "low"] }],
    "primaryField": "customerId",
    "defaultLimit": 20
  },
  "detailView": {
    "sections": [{ "title": "基本信息", "fields": ["customerId", "name", "riskLevel", "region", "accountTier", "status"] }],
    "relations": [
      { "linkType": "owns", "direction": "out", "targetType": "Account" }
    ]
  },
  "formView": {
    "fields": [
      { "name": "customerId", "widget": "input", "required": true },
      { "name": "riskLevel", "widget": "select", "options": ["high", "medium", "low"], "required": false }
    ]
  }
}
```

**app JSON 契约（Builder 输出 = Renderer 输入，version 1）**：

```json
{
  "version": 1,
  "id": "app-suspect-dashboard",
  "title": "可疑交易监控看板",
  "pages": [
    {
      "id": "page-main",
      "title": "总览",
      "blocks": [
        { "id": "b1", "component": "StatCard",
          "props": { "objectType": "Transaction", "metric": "count", "filter": { "field": "flagged", "op": "eq", "value": true }, "title": "可疑交易数" },
          "requires": { "objectType": "Transaction", "permission": "read" } },
        { "id": "b2", "component": "ObjectTable",
          "props": { "objectType": "Transaction", "viewRef": "auto", "filter": { "field": "riskLevel", "op": "eq", "value": "high" } },
          "requires": { "objectType": "Transaction", "permission": "read" } }
      ]
    },
    { "id": "page-detail", "title": "客户处置",
      "blocks": [
        { "id": "b3", "component": "ObjectDetail", "props": { "objectType": "Customer", "viewRef": "auto", "initialId": "" },
          "requires": { "objectType": "Customer", "permission": "read" } },
        { "id": "b4", "component": "ObjectForm", "props": { "objectType": "Customer", "viewRef": "auto", "boundAction": "freezeAccount" },
          "requires": { "objectType": "Customer", "permission": "write" } }
      ]
    }
  ]
}
```

**tRPC procedure 示例（ontologyRouter.getViewSchema，缓存键 `${objectType}@${ontologyVersion}`）**：

```typescript
ontologyRouter.getViewSchema.input(z.object({ objectType: z.string() })).query(async ({ input }) => {
  const ontology = await fetchOntology();                      // GET engine-api /ontology
  const ot = ontology.objectTypes.find(t => t.apiName === input.objectType);
  if (!ot) throw new TRPCError({ code: "NOT_FOUND" });
  return generateViewSchema(ot, ontology.linkTypes);           // FR-3 纯函数
})
```

**降级链（治理/Action 缺席时的行为，统一模式）**：engine-api `/perm` 与 `/action` 探测失败或返回 `{available: false}` → BFF 包装为 `{ available: false }` → 前端对应 UI：权限黄条提示 / 表单提交改弹「写回需接 Action Gateway」toast。**禁止**在缺席时抛错白屏。

## In scope / Out of scope

**In scope：** FR-1~FR-11 全部；`workshop/.gitignore`（node_modules/dist）；CI 增 engine-api pytest job 与 workshop `pnpm test && pnpm build` job。

**Out of scope（no-scope-creep）：** 不做本体可视化编辑器（拖拽建模/版本对比/迁移——独立后续 plan，Explorer 只读浏览）；不做 Action Builder 可视化配置（Action 定义仍走 P03 YAML，本 plan 只做「绑定已有 ActionType」）；不做决策看板/审计追踪页（依赖 P09 数据流，后续）；不做 WebSocket 实时刷新、多租户、SSO 登录页（静态 token 过渡）；不做自由网格布局/主题定制；不修改 `prototype/` 任何文件（拷贝骨架后裁剪在 `workshop/` 内进行）；不做移动端。

## 验收标准（AC）

| FR | AC | 验证方式 |
|---|---|---|
| FR-1 | 无 token 401；带 token `GET /ontology` 返回 ≥8 object_types；`/objects/Customer`、`/graph/schema`、`/graph?object_id=C-001` 正常（AGE 已 seed，可复用 P10 种子脚本） | `apps/engine-api/tests/test_api.py` |
| FR-2 | `make proto-ts` 两次执行 `git diff` 为空；`ontology.ts` 导出 `ObjectType` 接口且被 generate.ts 引用编译通过 | 本地命令 + `pnpm build` |
| FR-3 | Customer ViewSchema 与「关键实现意图」快照一致（字段名按实际本体校正后固化快照）；Transaction 的 relations 含 conducted/transfersTo 双向 | `generate.test.ts` 快照 |
| FR-4 | BFF 四 router 的 tRPC 集成测试：mock fetch engine-api 返回固定 JSON，断言 getViewSchema/list/saveApp→getApp round-trip | `workshop/server/src/**/*.test.ts` |
| FR-5 | 各 block 组件在 Storybook 或测试页可独立渲染（ObjectTable 渲染 8 行 Customer 数据；ObjectForm select 选项来自 ViewSchema） | 组件测试（vitest + testing-library） |
| FR-6 | 搭建器：拖入 3 个块 → 保存 → `apps` 表有记录且 app JSON 结构符合契约（version: 1） | Playwright 或人工走查记录 |
| FR-7 | `#/app/{id}` 渲染保存的应用：StatCard 显示数值、ObjectTable 按 filter 过滤、page tab 切换正常 | 人工走查（workthrough 复现） |
| FR-8 | Explorer：schema 图显示 8 类型 + 8 关系（图例着色）；实例浏览从 Customer 展开含 Account/Transaction 邻居；全局搜索 "C-001" 跨类型返回 Customer 结果 | 人工走查 |
| FR-9 | P09 未接入：顶栏黄条「治理未接入」且页面全量渲染；接入后（mock `/perm` 返回 deny）对应 block 显示无权限占位 | 组件测试（mock 两态） |
| FR-10 | P07 未启用：表单提交弹 toast；启用后（mock propose）显示 ActionRecord 状态 | 组件测试（mock 两态） |
| FR-11 | 按 `docs/workshop-walkthrough.md` 完整搭建「可疑交易监控看板」≤30 分钟（含列表+详情+表单+统计），保存重开渲染一致 | 人工走查计时记录（截图入文档） |
