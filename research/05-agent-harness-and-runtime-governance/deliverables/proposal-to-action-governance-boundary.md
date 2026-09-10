# 从 Agent 提案到 Action：运行时治理边界

> **状态：公开来源复核完成，项目接口建议待 Maintainer 确认。**
>
> 本文只使用公开标准、官方资料和本仓库既有设计形成结论。受限参考资料只用于发现
> 研究问题，不作为本文事实、规则或接口设计的证据。

## 一、结论

`AgenticX-OAG` 应把以下判定拆开，并保留每一步的独立结果：

```text
提案结构校验
  -> P08 语义/规则/流程/工具门禁
  -> P09 主体与对象级授权
  -> P07 权威审批状态机
  -> P07 Action 前置条件、执行和后置验证
  -> P09 审计与回放
```

任何前一步通过，都不能代替后一步：

- JSON Schema 通过只表示实例满足结构约束，不表示主体获得工具或对象权限。[1]
- 工具在白名单且参数合法，不表示当前主体可以执行该操作。MCP 将输入校验、访问控制
  和敏感操作确认列为不同安全要求。[2]
- 业务规则要求“两级审批”，不表示审批已经发生；审批必须由权威状态机记录不同审批
  主体及其授权结果。
- P09 授权成功不表示 Action 前置条件成立，也不表示执行后的业务状态正确。
- 审批人有 `approve` 权限不表示其审批意见为同意，更不能替代执行人的 `write` 权限。

因此，P08、P09 和 P07 不是三个互相替代的门，而是一条必须防绕过的串联执行链。

## 二、公开依据核验

| 公开依据 | 可支持的结论 | 不能从中推出的结论 | 来源等级 |
|---|---|---|---|
| JSON Schema 2020-12 | Schema 对 JSON instance 施加 assertions 并产生校验结果 | 校验通过即已授权、已审批或业务正确 | S2 |
| MCP Tools 2025-06-18 | 工具有 `inputSchema`；服务端必须校验输入并实施访问控制；客户端应对敏感操作确认并记录工具使用 | MCP 协议自动提供对象级权限、审批状态机或企业审计 | S2 |
| NIST RBAC | 主体只能通过已授权角色执行被该角色授权的 transaction，并允许叠加额外约束 | RBAC 自动定义对象条件、故障降级或审批流程 | S2 |
| NIST AI RMF 1.0 | 治理应贯穿风险映射、测量、管理和系统生命周期，责任与过程需要明确记录 | 某个固定 Harness 层数或具体 DSL 是标准要求 | S2 |
| W3C PROV-O | 可用 Entity、Activity、Agent 及 `used`、`wasAssociatedWith` 等关系表达来源与责任 | 记录 PROV-O 就证明决策正确或授权有效 | S2 |
| Palantir Action 官方文档 | Action 是改变对象、属性或链接的单个 transaction，可包含参数、规则、校验、授权检查和提交副作用 | 公开概览足以证明所有事务隔离、跨系统补偿或策略冲突细节 | S2 |
| P07/P08/P09 现有计划 | 项目已设计四层门禁、四权授权、审批状态机、Action 执行和回放 | 这些路线图能力已经实现并通过生产验证 | S1 |

公开核验支持“各门职责独立且需串联”的总体结论，但下面的收据字段、错误码和跨服务
组合方式属于项目工程建议（S4），不是外部标准的直接要求。

## 三、职责与信任边界

| 阶段 | 权威输入 | 输出 | 明确不负责 | 归属 |
|---|---|---|---|---|
| 提案结构校验 | Proposal Schema、原始提案 | 结构化 Proposal 或 `INVALID_PROPOSAL` | 身份、授权、审批、业务执行 | P08 入口 |
| 概念检查 | 本体版本、允许对象/意图 | 概念层 check | 对象级权限 | P08 |
| 业务规则检查 | 规则集版本、对象事实、Proposal | 规则命中、BLOCK 或义务 | 审批是否已经发生 | P08 |
| 流程检查 | SOP 版本、权威流程状态 | 缺失步骤、BLOCK 或通过 | 仅凭客户端数组认定步骤完成 | P08 |
| 工具检查 | 工具目录、白名单、输入 Schema | 工具与参数检查结果 | 调用者授权 | P08 |
| 对象级授权 | 认证主体、租户、角色/授权、对象及条件 | allow/deny、策略版本、matched grant | 业务规则和 Action 前置条件 | P09 |
| 审批 | Action 契约、授权审批人、审批事件 | 待审批、通过或拒绝状态 | 让提案参数充当审批记录 | P07 + P09 |
| Action 执行 | 已通过的门禁收据、授权、审批状态、Action 契约 | 状态变化、副作用引用、执行结果 | 接受 LLM 直接写存储 | P07 |
| 后置验证 | Action 契约、执行后权威状态 | 成功、补偿或人工接管 | 把“调用返回 200”直接记为业务成功 | P07 |
| 审计回放 | 各阶段不可变事件与版本 | 决策包和 PROV-O 表达 | 重新触发不可逆副作用 | P09 |

“权威输入”不能由 LLM 或外部客户端自行声明。例如 `completed_steps`、对象属性、角色、
审批层级、策略版本和门禁结果如果来自请求体，只能作为待核对的主张，不能直接决定执行。
P08 应把 Proposal 与可信 `EvaluationContext` 分开；P09 的条件授权应从可信 ObjectProvider
读取绑定对象、租户和版本的属性快照。

## 四、P08、P09 与 P07 的接口

### 4.1 P08 输出门禁结果和义务

P08 的输出应保留每层检查结果，并区分两类结果：

- `BLOCK`：提案不得进入授权或执行链路。
- `ALLOW`：P08 没有发现语义、规则、流程或工具契约违规；它不代表 P09 授权成功。

某条业务规则可以产生执行义务，例如 `required_approval_policy=two_level`。义务不是审批
结果，P07 必须用权威审批状态机满足它。客户端参数 `approvalLevel=two_level` 不能作为
义务已经完成的证据。

Proposal 只应承载提案方可声明的意图、目标、参数、工具和依据主张。主体、租户、对象事实、
当前流程步骤和已完成步骤属于服务端上下文；Verdict 应同时绑定 `proposal_hash`、
`context_hash` 和 `context_version`。否则提案方可以通过伪造流程数组或对象事实绕过规则。

### 4.2 P09 独立求值每个受保护动作

P09 至少在以下位置求值：

1. `Propose`：发起主体对目标对象是否有 `write`/操作权。
2. `Decide`：审批主体对目标对象是否有 `approve` 权。
3. `Execute`：执行主体及其服务身份是否仍在有效租户、策略和对象范围内。
4. 读路径：按 `read` 权限单独求值，不能由写权限故障策略反向推导。

带对象条件的 grant 必须对可信对象快照求值。请求体或 Proposal 中与策略条件同名的属性
不得覆盖该快照；对象属性后端不可用应归类为 `GOVERNANCE_UNAVAILABLE`，不能退回使用
客户端值继续授权。

一次完整且成功的策略求值中，没有任何 grant 命中时返回 deny；治理服务不可用则返回
`GOVERNANCE_UNAVAILABLE`。二者不能使用同一个原因码，也不能把系统故障伪装成“用户
无权限”。生产模式的故障策略至少禁止写入、Action 和审批；读策略继续由部署配置明确
决定。上述故障处理是项目工程建议（S4）。

### 4.3 P07 必须防止绕过

P07 不能信任调用方提交的 `verdict=ALLOW`、角色、审批状态或策略版本。建议在信任边界
内采用下列任一模式：

1. P07 在 `Propose`、`Decide`、`Execute` 内部调用可信的 Harness/Policy 适配器；或
2. P07 验证由可信治理服务签发、与 Proposal 指纹绑定且短期有效的 Gate Receipt。

项目采用哪种模式可在实施时决定，但必须满足这些不变量：

- 收据绑定 `proposal_hash`、主体、租户、Action、目标对象和本体/规则/策略版本。
- P08 的 ALLOW 和 P09 的授权结果分别可验证，不能合并为无来源的布尔值。
- Proposal 内容发生变化后旧收据失效。
- `Decide` 必须重新校验审批主体的 `approve` 权限。
- `Execute` 必须确认审批义务已由 P07 权威状态机满足。
- 收据缺失、过期、签发方未知或哈希不匹配时不得产生写副作用。

## 五、审批语义

调整前的 P08 示例把 `parameters.approvalLevel == two_level` 当成 MUST 条件。这只能证明客户
端发来了一个字符串，不能证明有两名不同且有权的审批者完成批准，应调整为：

```text
规则命中 -> P08 输出 required_approval_policy=two_level
         -> P07 进入 PENDING_APPROVAL
         -> 每次 Decide 由 P09 检查 approve 权限
         -> P07 校验审批主体不同、数量满足、未被拒绝
         -> 才允许 Execute
```

审批策略来源也要有优先级。建议以 Action 契约为基线，P08 只能产生同等或更严格的动态
义务，不能降低契约要求。具体合并规则必须版本化，并在审计中记录“契约要求、规则义务、
最终有效策略”三项值。

## 六、稳定失败分类

| 原因码 | 含义 | 是否重试 | 是否属于权限拒绝 |
|---|---|---|---|
| `INVALID_PROPOSAL` | Proposal 不符合结构契约 | 修正输入后 | 否 |
| `HARNESS_BLOCKED` | 概念、业务规则、流程或工具层阻断 | 修改提案或规则后 | 否 |
| `AUTHZ_DENIED` | P09 完成求值但无授权 grant 命中 | 权限/上下文改变后 | 是 |
| `APPROVAL_REQUIRED` | 授权允许发起，但审批义务尚未满足 | 完成审批后 | 否 |
| `APPROVAL_DENIED` | 有权审批者明确拒绝 | 新业务流程决定 | 否 |
| `GOVERNANCE_UNAVAILABLE` | 无法取得可信的门禁或授权结果 | 服务恢复后 | 否 |
| `PRECONDITION_FAILED` | Action 执行前业务条件不成立 | 状态改变后 | 否 |
| `EXECUTION_FAILED` | 写入或外部副作用执行失败 | 按副作用策略 | 否 |
| `POSTCONDITION_FAILED` | 执行完成但业务结果未满足契约 | 补偿或人工接管 | 否 |
| `COMPENSATION_FAILED` | 补偿未恢复到声明状态 | 人工接管 | 否 |

稳定分类使调用方知道应修改输入、申请权限、等待审批、恢复依赖还是处理业务故障，也使
P09 回放不会把不同风险压缩成一个 `BLOCK`。

## 七、验收矩阵

| 场景 | 预期结果 | 关键断言 |
|---|---|---|
| 参数 Schema 非法 | `INVALID_PROPOSAL` | P09/P07 未调用，无副作用 |
| 工具不在白名单 | `HARNESS_BLOCKED` | P08 记录 skill check；无授权或执行事件 |
| 参数合法但无对象权限 | `AUTHZ_DENIED` | P08 可为 ALLOW；P09 有稳定 deny 原因；P07 无实例 |
| 有权限但需审批 | `APPROVAL_REQUIRED` | P07 为 `PENDING_APPROVAL`，不能 Execute |
| 请求体伪造 `approvalLevel` | 仍待审批 | 不增加审批计数，不改变有效审批策略 |
| Proposal 伪造 `completed_steps` | `INVALID_PROPOSAL` | 严格输入模型拒绝权威字段；流程只读取 EvaluationContext |
| 请求体伪造对象条件属性 | 授权结果不变 | P09 只读取可信对象快照，记录其版本 |
| 无 `approve` 权限调用 Decide | `AUTHZ_DENIED` | 审批计数不变，记录访问拒绝 |
| 两级审批使用同一主体 | 仍待审批或拒绝 | 不满足 two-level 不同主体约束 |
| 修改 Proposal 后复用收据 | 拒绝 | 哈希不匹配，零副作用 |
| 绕过 P08/P09 直接 Propose | 拒绝 | 缺可信门禁/授权证明，零写入 |
| 治理服务不可用时写入 | `GOVERNANCE_UNAVAILABLE` | 不误报 AUTHZ_DENIED，不创建副作用 |
| 全部门禁通过但前置条件失败 | `PRECONDITION_FAILED` | 权限结果保留，Action 未执行 |
| 执行成功但后置条件失败 | `POSTCONDITION_FAILED` | 不记 SUCCEEDED，进入补偿或人工接管 |
| 决策回放 | 重建全部阶段 | 可见 Proposal 指纹、版本、各门结果、审批和执行事件 |

## 八、对当前计划的影响

公开复核确认总体分层方向正确，但现有计划需要三处接口收紧：

1. P08 不再用客户端 `approvalLevel` 参数冒充审批完成状态；规则只产生审批义务。
2. P08 把 Proposal 与可信 EvaluationContext 分开；流程状态和对象事实不再由提案方自证。
3. P07 增加不可绕过的执行门接口/收据，并在 Propose、Decide、Execute 的正确时点调用
   P09；静态 token 只能证明调用者持有网关凭证，不能替代对象级授权。

P09 的“无 grant 命中则 deny”保持不变，但只适用于使用可信对象快照并成功完成策略求值
的情况；客户端属性不得改变授权事实，服务不可用使用独立失败状态。P11 的只读降级策略
仍不由该规则推导。

## 九、来源等级

| 等级 | 本文用法 |
|---|---|
| S1 | P07/P08/P09、架构与路线图中的既有项目设计 |
| S2 | JSON Schema、MCP、NIST RBAC/AI RMF、PROV-O 和官方 Action 文档 |
| S3 | 不作为本文结论依据；受限资料只触发研究问题 |
| S4 | Gate Receipt、原因码、审批义务合并和故障行为等新增工程建议 |

## 参考资料

[1] [JSON Schema Core 2020-12](https://json-schema.org/draft/2020-12/json-schema-core.html)，访问于 2026-09-10。

[2] [Model Context Protocol, Tools 2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)，访问于 2026-09-10。

[3] [NIST Role Based Access Control FAQ](https://csrc.nist.gov/projects/role-based-access-control/faqs)，访问于 2026-09-10；该项目页已归档，本文只采用其 RBAC 基础定义。

[4] [NIST AI Risk Management Framework 1.0 Core](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/)，访问于 2026-09-10。

[5] [W3C PROV-O](https://www.w3.org/TR/prov-o/)，访问于 2026-09-10。

[6] [Palantir Foundry, Action types](https://palantir.com/docs/foundry/action-types/overview/)，访问于 2026-09-10。
