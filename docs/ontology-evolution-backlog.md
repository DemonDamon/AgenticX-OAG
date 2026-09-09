# 本体工程演进待办

> 分支：`feat/oag-ontology-evolution`
>
> 目的：基于项目既有路线图、架构约束与公开标准，将下一阶段能力转化为
> `AgenticX-OAG` 可实施、可测试、可回放的工程任务。

## 当前判断

P02-P06 已完成，项目已经具备本体模型、知识图谱构建、OAG 检索、Context Pack、引用约束生成和离线评测基础。下一阶段的主要缺口不在概念覆盖，而在：

1. Action 的状态变化、审批、幂等、回滚和写回。
2. Agent 提案的概念、规则、流程、技能四层门禁。
3. 对象级权限、审计事件、决策溯源和回放。
4. 数据质量、来源等级、冲突消解和增量更新。
5. 场景模板、方法记忆和从 POC 到可复用应用的沉淀。

## 任务优先级

| ID | 任务 | 公开或项目依据 | 来源等级 | 对应计划 | 状态 |
|---|---|---|---|---|---|
| OE-01 | Action 契约补全：前后置条件、状态变化、幂等键、副作用、补偿动作 | `docs/architecture.md`、RFC 8785 | S1/S2/S4 | P07 | pending |
| OE-02 | Action Gateway：提案→审批→执行→验证→归档，迁移与审计同事务 | `docs/roadmap.md` Phase 3 | S1 | P07 | pending |
| OE-03 | Harness 四层门禁与确定性规则 DSL | `docs/enterprise-landing.md` §3.1、JSON Schema | S1/S2/S3 | P08 | pending |
| OE-04 | 四权矩阵、对象级授权和无授权命中时拒绝 | NIST RBAC、`docs/architecture.md` 多租户原则 | S1/S2/S3 | P09 | pending |
| OE-05 | 决策链：检索→主张→规则→提案→审批→Action→结果 | W3C PROV-O | S1/S2/S4 | P09 | pending |
| OE-06 | 数据卡、来源等级、冲突报告、增量同步和入库质量门禁 | W3C SHACL、P04/P06 现有能力 | S1/S2/S4 | 后续 P12+（基于 P04） | backlog |
| OE-07 | AML 场景包：ontology/actions/policy/harness/seed/golden set | `docs/architecture.md` Industry Pack | S1/S4 | P10 | pending |
| OE-08 | Object View、Action 绑定和权限继承的 Workshop MVP | `docs/roadmap.md` Phase 5 | S1/S4 | P11 | pending |
| OE-09 | 方法记忆：把成功的分析路径沉淀为可复用模板 | `docs/roadmap.md` Phase 4 | S1 | 后续 P12+ | backlog |
| OE-10 | 真实 Provider、持久化 Pack、检索路径溯源和生产可复现环境 | `docs/architecture.md`、P05 契约 | S1/S4 | 后续 P12+ | backlog |

## 公开依据与工程边界

| 依据 | 用于约束什么 | 工程边界 |
|---|---|---|
| [W3C OWL 2](https://www.w3.org/TR/owl2-overview/) / [SHACL](https://www.w3.org/TR/shacl/) | 本体语义与数据质量约束 | 不把离线语义校验等同于运行时授权 |
| [W3C PROV-O](https://www.w3.org/TR/prov-o/) | 决策、证据和 Action 的溯源关系 | 自定义属性使用 OAG namespace，不冒充标准词汇 |
| [NIST RBAC](https://csrc.nist.gov/projects/role-based-access-control) | 角色、权限和默认拒绝模型 | 产品的对象级条件与租户隔离作为显式扩展 |
| [JSON Schema](https://json-schema.org/specification) / [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785) | 输入输出契约与规范化请求指纹 | 契约变更必须版本化，禁止依赖非确定性序列化 |
| 项目 `architecture.md` / `roadmap.md` | 控制面/数据面、Industry Pack、阶段边界 | 不改变已登记依赖和 POC 非阻塞原则 |

### 来源等级

| 等级 | 含义 | 在公开交付中的使用规则 |
|---|---|---|
| S1 | 项目既有设计：已存在于 roadmap、architecture、enterprise-landing 或已登记 plan | 可作为项目决策依据 |
| S2 | 公开标准或官方技术资料 | 可引用可复核链接 |
| S3 | 受限社区资料的原则级直接依据 | 只作内部来源审计标签；不记录书名、章节、原文、图表或独特案例，且不能作为公开 PR 的唯一证据 |
| S4 | 本次新增工程建议 | 必须标记“待 Maintainer 确认”，不得写成既定结论 |

这里的“直接依据”仅表示某项原则受到受限资料明确启发，不表示可复制其具体表达。P09 的“策略引擎求值时无授权 grant 命中则 deny”和 P08 的工具白名单 BLOCK 原则属于 S3；P11 的治理服务故障策略属于 S4，两者不得相互推导。

## 贡献与来源边界

1. Plan、代码、测试、commit 和 PR 只引用可公开核验的标准、官方文档及本仓库已有设计。
2. 不提交未经授权的非公开正文、转写稿、截图、图表、章节映射、案例数据或代码；注明出处或改写措辞不能替代授权。
3. 工程需求必须独立表述，并能由公开依据和本项目自身需求完整解释，不依赖实施者接触任何非公开资料。
4. 引入外部代码、数据或模板前，逐项记录许可证、权利人、版本和允许的使用范围；无法确认时不纳入交付物。

## 实施顺序与验收原则

1. 先完成 P07-P09 的最小闭环，再把治理能力接入 P10。
2. 基于 P04/P06 的数据质量与评测增强不得被 P10 的演示页面掩盖；新增工作另拆 P12+，不回写已完成计划的状态。
3. 每项能力必须有确定性单测、失败路径和回放数据；只有 UI 演示不算完成。
4. 新增字段必须进入 YAML/Proto/Pydantic 的契约边界，并说明版本兼容策略。
5. 外部实现只作为设计参考；复用代码前必须核验许可证、版本和实际实现范围。

## 相关入口

- P07：[Action Gateway plan](../.cursor/plans/pending/2026-09-03-action-gateway-dataplane.plan.md)
- P08：[Agent Harness plan](../.cursor/plans/pending/2026-09-03-agent-harness-layers.plan.md)
- P09：[治理、审计与回放 plan](../.cursor/plans/pending/2026-09-03-governance-rbac-audit.plan.md)
- P10：[AML POC plan](../.cursor/plans/pending/2026-09-03-aml-poc-demo-web.plan.md)
- P11：[Workshop MVP plan](../.cursor/plans/pending/2026-09-03-workshop-lowcode-mvp.plan.md)
- 研究总索引：[research/README.md](../research/README.md)
