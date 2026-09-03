# AgenticX-OAG 生产架构设计（v1.0）

> 定位：可横跨 10+ 企业、多领域复用的本体增强生成平台的生产架构。
> 本文档是 docs/roadmap.md 的架构落地篇，修订了此前「纯 Python」的初步结论。
>
> 日期：2026-09-03

---

## 0. 设计原则（先立规矩）

1. **控制面与数据面分离**：管理/编排类组件求迭代速度，执行类组件求性能与稳定。两者用契约（gRPC/Proto）缝合，各自选最优语言。
2. **一切热路径可替换**：存储、检索、LLM、审批、认证全部走接口抽象，任何组件可在不同企业环境替换实现（含国产化替换）。
3. **容量诚实**：先给出每条路径的性能预算和量化估算，Phase 2 设基准测试门禁，用数据验证，不拍脑袋。
4. **演进式多语言**：不为性能提前全面重写，也不让单一语言成为终态天花板。语言选型跟随路径特征，不跟随偏好。
5. **多租户从第一天进核心**：tenant_id 贯穿所有记录与索引，Row-Level Security 落在 PG。这是「一套产品服务多个企业/多个业务线」的前提。

---

## 1. 此前结论的修订（先认账）

| 原结论 | 问题 | 修订 |
|---|---|---|
| 「Python 胶水 + 现成 Rust/C 引擎即可」 | 对 PoC 成立；对高并发在线路径（Action 写路径 10k+ TPS、实时规则评估、MCP 高并发服务）不成立，Python 单实例吞吐比 Go 低 5-10 倍，且 GIL 限制 CPU 密集扩展 | 引入 Go 数据面服务（§3），控制面保持 Python |
| 「Oxigraph 作生产图存储」 | Oxigraph 是嵌入式单机 RDF 库，无分布式能力，撑不住企业生产 | 生产图存储改为 PG + Apache AGE 起步，超大规模切 NebulaGraph/TuGraph；Oxigraph 降级为嵌入式语义校验组件 |
| 未考虑分布式 HA / 容量数字 | 缺部署拓扑、故障降级、容量规划 | 本文档 §4-§7 补齐 |

---

## 2. 总体架构：控制面 / 数据面分离

```
                    ┌──────────────── 多可用区 Kubernetes 集群 ────────────────┐
                    │                                                        │
 用户/Agent ──► LB ──► APISIX Ingress（鉴权/限流/路由，Go/Lua 插件）          │
                    │                                                        │
        ┌───────────┼──────────────────────────────┐                         │
   API Gateway(Go)   MCP Server(Go)           Workshop BFF(Go/TS)             │
        │ gRPC + mTLS                                                        │
   ┌────┴─────────────────────────┐   ┌──────────────────────────────┐       │
   │ 控制面（Python，随 AgenticX）│   │ 数据面（Go）                  │       │
   │ · Ontology Manager           │   │ · Action Gateway（事务/幂等）  │       │
   │ · KG Builder（Ray fan-out）  │   │ · 实时规则引擎               │       │
   │ · Context Pack Engine        │   │ · Ingestion Worker           │       │
   │ · Agent/LLM 编排             │   │ · WebSocket Hub（Workshop）  │       │
   │ · 评测框架                    │   │                              │       │
   └────┬─────────────────────────┘   └──────────┬───────────────────┘       │
        │  编译产物：本体 Schema 策略包（版本化、watch 热更新，OPA 模式）      │
        └──────────────────┬─────────────────────┘                           │
   ┌─────────────────────┴─────── 存储层 ─────────────────────────────┐      │
   │ PG 16 + AGE（Patroni HA，同步副本）── CDC(Debezium) ──► Kafka     │      │
   │ Redis Cluster（缓存/幂等键/限流）                                 │      │
   │ Qdrant / Milvus（向量）   MinIO（对象/Context Pack）              │      │
   │ NebulaGraph / TuGraph（可选，超大图）  OpenSearch（审计/全文）      │      │
   └──────────────────────────────────────────────────────────────────┘      │
   可观测：OpenTelemetry → Prometheus / Grafana / Loki / Tempo               │
   LLM 出口：AI Gateway（多 Provider 故障切换、按租户限流计费）               │
                    └────────────────────────────────────────────────────────┘
```

**关键模式——控制面编译、数据面执行**：本体 schema、权限矩阵、审批策略在控制面定义，编译为版本化策略包；Go 数据面服务 watch 并热更新。这正是 K8s/Envoy/OPA 的成熟模式，天然解决「Python 管理策略、Go 执行策略」的一致性问题。

---

## 3. 语言选型定论

| 组件 | 语言 | 理由 |
|---|---|---|
| Agent/OAG 编排、本体管理、KG 构建、评测 | **Python** | AgenticX 基座在此；LLM/本体/科研生态全在 Python；该路径延迟被 LLM 调用（秒级）支配，服务自身开销占比 <5% |
| Action Gateway、实时规则引擎、API/MCP Server、Ingestion、WS Hub | **Go** | 高并发（goroutine 2-8KB 栈 vs Python 进程模型）、静态编译单二进制（对 10 个不同企业环境交付极友好）、K8s 生态同源、国内基建人才池大 |
| 向量/图/嵌入等性能引擎 | **Rust/C++（用现成的）** | Qdrant(Rust)、AGE(C)、FAISS(C++)、TEI(Rust 嵌入推理)；不自研，除非 profile 证明必要 |
| Workshop 前端 | **TypeScript/React** | 已有原型基础 |

**为什么 Go 而不是 Rust/Java：**
- vs Rust：GC 停顿已到亚毫秒级，对 10-100ms 级在线路径无影响；Go 招聘与团队速度优势明显。Rust 留给引擎层（且直接消费现成 Rust 引擎）。
- vs Java：AI 生态在 Python、基座在 Python，JVM 增加运维重量；gRPC 契约保证客户强要求 JVM 时可加 Java 适配器而不动核心。

**写路径吞吐对比（单 4C8G pod，简单 PG 事务）：** Python(asyncio+asyncpg) 约 2-5k TPS；Go 约 10-20k TPS。读编排路径 Python 300-800 QPS/pod vs Go 5-10k QPS/pod。**差距真实存在，但只在高并发路径上花钱修——这是关键判断。**

**反模式警告：不要全面重写。** 控制面路径（LLM 编排）即使全部换成 Go，总延迟几乎不变——瓶颈在 LLM。语言优化只投向「写路径 + 实时评估 + 连接层」三处。

---

## 4. 存储与中间件选型

| 组件 | 默认选型 | 备选 | 选型理由 |
|---|---|---|---|
| 关系主库（对象/Action/审计/主张账本） | **PostgreSQL 16** | openGauss、PolarDB、GaussDB（PG 系国产） | JSONB 存本体 schema、RLS 做多租户、生态扩展（AGE/pgvector/pg_trgm）；PG 系国产化替换路径最顺（openGauss 即 PG 衍生） |
| 图存储 | **PG + Apache AGE** 起步 | NebulaGraph / TuGraph（十亿边级）、Memgraph | 中小规模一个库搞定（运维减半）；`GraphStore` 接口屏蔽差异，规模到了换实现 |
| 向量库 | **pgvector**（小）→ **Qdrant/Milvus**（中大） | — | 小规模不引入新组件；Milvus 国产分布式、Qdrant 性能好；同样走 `VectorStore` 接口 |
| 缓存/协调 | **Redis Cluster**（3主3从） | — | schema 缓存、幂等键（SETNX+TTL）、令牌桶限流、配置发布 pub/sub。**关键锁用 PG advisory lock 或 etcd**，不依赖 Redis 锁的正确性 |
| 事件主干 | **Kafka**（RF=3） | RocketMQ（事务消息强）、NATS（轻量） | CDC 入口（Debezium）、Action 事件溯源（审计=可重放日志）、跨服务集成事件 |
| 对象存储 | **MinIO / S3 兼容** | — | 原始文档、Context Pack、审计产物 |
| 全文/审计检索 | PG FTS 起步 → **OpenSearch** | — | 审计检索是企业刚需 |
| LLM 出口 | **AI Gateway**（自建 Go 或 LiteLLM） | One-API | 多 Provider 故障切换、按租户限流/计费、出网管控——企业安全合规硬需求 |
| 嵌入推理 | **TEI（Rust）sidecar** | Infinity | 嵌入从 Python 进程卸载，吞吐提升一个量级 |
| 编排部署 | **Kubernetes** + APISIX Ingress | Higress | 跨企业交付的统一底座；APISIX 国产、高性能、插件生态 |
| 可观测 | OTel → Prometheus/Grafana/Loki/Tempo | — | Python/Go 双端自动埋点统一 |

---

## 5. 高可用设计

### 5.1 组件级 HA

| 组件 | 方案 |
|---|---|
| 无状态服务（Gateway/MCP/编排） | ≥3 副本跨 AZ，HPA（CPU+自定义 QPS 指标），PDB |
| PostgreSQL | Patroni + etcd 自动故障转移；Action 写路径走**同步副本**（RPO=0），分析走异步副本 |
| Redis | Cluster 模式，3主3从跨 AZ |
| Kafka | RF=3，min.insync.replicas=2，跨 AZ 机架感知 |
| MinIO | 纠删码，跨 AZ |
| 图库/向量库（分布式模式） | 副本因子 3 |

### 5.2 降级阶梯（比可用性数字更重要）

| 故障 | 降级行为 |
|---|---|
| 图存储不可用 | `GraphStore` 回退 PG 关系查询（慢但正确） |
| 向量库不可用 | 回退 BM25/PG FTS |
| LLM 不可用 | 返回缓存的 Context Pack + 规则引擎结果（只读服务不中断） |
| AI Gateway 单 Provider 限流 | 自动切换备用 Provider，租户级配额保护 |
| Kafka 不可用 | Ingestion 本地缓冲（磁盘队列），恢复后回放 |

### 5.3 容灾

- 标准：同城双 AZ（同步），异地异步 DR，RPO<5min，RTO<30min。
- 企业级：可选异地同步（银行/金融客户要求）。
- 每季度故障演练 + 混沌测试（chaos-mesh）。

---

## 6. 部署架构与网络拓扑

```
VPC 分层（企业标准网络）：
┌─ DMZ（公网/专线接入）：LB + WAF → APISIX（仅暴露必要路由）
├─ 应用区（K8s）：控制面/数据面 Pod；东西向 gRPC + mTLS；出网仅允许 AI Gateway
├─ 数据区：PG/Redis/Kafka/向量库/对象存储；仅应用区可达，双向白名单
└─ 管理区：跳板机、监控、日志；零信任接入
```

**三档部署 profile（对 10 企业复用至关重要）：**

| Profile | 形态 | 面向 |
|---|---|---|
| POC | docker-compose 单机（PG+Redis 内嵌） | Demo/小客户，30 分钟起环境 |
| Standard | 3 节点 K8s，组件单副本或 3 副本 | 中型企业 |
| Enterprise | 多 AZ K8s，全组件 HA，异地 DR，国产化适配 | 金融/能源/政务 |

网络补充：Workshop 用 WebSocket 长连接（Go Hub，单 pod 10万+ 连接）；Agent 走 gRPC/MCP；审计日志单独管道（Kafka → 冷存 MinIO + OpenSearch 热查）。

---

## 7. 容量规划（诚实版数字）

### 7.1 三条关键路径的延迟预算

**路径 A：Agent OAG 问答（含 LLM 生成）**
- 组成：改写(LLM) + 实体链接 + 图扩展 + 向量检索 + 重排 + 生成(LLM)
- 总延迟 3-15s，其中我方服务开销 <200ms（1-5%）
- **瓶颈 = LLM 算力**。8×A100 跑 32B（vLLM 连续批处理）单副本约 0.3-1 query/s → LLM 集群 10 副本 ≈ 5-10 QPS 持续。**加 QPS 先加 GPU，不加服务**

**路径 B：Context Pack 检索（无 LLM 合成）**
- 图查 10-50ms + 向量 5-20ms + 重排 10-50ms + 编排
- Python 编排 pod：300-800 QPS；Go pod：5-10k QPS

**路径 C：Action 写路径（提案/审批/执行）**
- 单条 PG 事务 5-20ms；Python pod 2-5k TPS，Go pod 10-20k TPS；PG 本身天花板 10-50k TPS
- 银行实时风控场景（每笔交易过检，10k+ TPS）→ 必须 Go + PG 分区；再往上走 Citus/TiDB/PolarDB-X 分片（同一 SQL 接口，无感切换）

### 7.2 三档 profile 容量承诺（待 Phase 2 基准验证）

| 指标 | POC | Standard | Enterprise |
|---|---|---|---|
| 检索 QPS（无 LLM） | 50 | 5-10k | 50k+（横向扩） |
| Action TPS | 200 | 2-5k | 10-20k（PG 分区后更高） |
| 并发 Agent 会话 | 10 | 200-500（LLM 算力约束） | 1000+（取决于 GPU 池） |
| 文档摄入 | 1k/h | 10-50k/h | 100k+/h |
| 事件流 | — | 10k/s | 100k+/s |

### 7.3 基准测试门禁（Phase 2 交付物）

- k6/Locust 压测套件，覆盖三条路径；发布各 profile 的实测数字
- 该基准同时是销售工具：客户容量规划直接查表

---

## 8. 跨企业复用的抽象设计（10 企业复用的核心）

### 8.1 四层产品包装

```
┌─ 4. Industry Pack：行业本体 + 应用模板 + 最佳实践（金融/制造/能源/政务）
├─ 3. Connectors：每企业的 DB/API/IDP/审批/通知 适配器（飞书审批、钉钉、OA…）
├─ 2. Core Services：本体引擎/检索/ContextPack/ActionGateway（零企业假设）
└─ 1. Contracts：Proto 契约 + 接口抽象（跨语言复用的真正载体）
```

### 8.2 契约即资产

- **本体元模型用 Proto 定义一次**，生成 Python/Go/TS 三端绑定——单一事实来源，杜绝双语言模型漂移
- Python 侧接口（Protocol/ABC）：`GraphStore` / `VectorStore` / `EmbeddingProvider` / `LLMProvider` / `IDPProvider` / `ApprovalProvider` / `Notifier` / `AuditSink` / `EventBus`
- 企业扩展：Python entry-point 插件（抽取器/连接器）；跨语言扩展走 gRPC sidecar

### 8.3 企业差异的隔离规则（什么绝不进核心）

| 企业差异 | 落点 |
|---|---|
| 认证（AD/OAuth2/LDAP/信创 IDP） | `IDPProvider` 适配器 |
| 审批系统（飞书/钉钉/自建 OA） | `ApprovalProvider` 适配器 |
| 数据库国产化（openGauss/OceanBase/达梦） | SQL 层兼容 profile + `GraphStore` 实现 |
| 部署环境（公有云/私有云/信创机房） | 部署 profile + K8s Operator（Phase 6） |
| 行业本体 | Industry Pack |

### 8.4 多租户

- tenant_id 贯穿所有表与索引，PG Row-Level Security 强制隔离
- 本体按命名空间隔离，共享基础本体（跨业务线复用建模成果）
- 配额与计费挂在 AI Gateway 与存储层

---

## 9. 对路线图的修订

| 阶段 | 修订内容 |
|---|---|
| Phase 0 | **新增**：Proto 契约定义（本体元模型 + 存储接口）；`GraphStore`/`VectorStore` 等接口先行 |
| Phase 1 | 图存储改为 PG+AGE（原 Oxigraph 降为嵌入组件）；嵌入推理走 TEI sidecar |
| Phase 2 | **新增**：基准测试门禁（三路径压测 + profile 容量表发布） |
| Phase 3 | **Action Gateway 改用 Go 实现**（第一个数据面服务，事务/幂等/审计的高标准场景，早验证多语言缝） |
| Phase 5 | Workshop BFF（Go）+ WebSocket Hub；Ingress 用 APISIX |
| Phase 6 | MCP Server（Go）、K8s Operator、多租户配额计费、信创适配 profile |

**总原则不变：Phase 0-2 用 Python 最快验证价值，但契约和接口从第一天就是跨语言的——这保证了后面任何局部重写都是小手术，而不是推倒重来。**

---

## 10. 风险与判断记录

| 风险/诱惑 | 判断 |
|---|---|
| 「全面用 Go/Rust 重写」 | 拒绝。控制面瓶颈在 LLM，重写无收益且拖死交付。语言优化只投向写路径/实时评估/连接层 |
| Python 性能天花板焦虑 | 用数据说话：路径 A 中服务开销占比 <5%；先把 GPU 池和检索缓存做对 |
| 多语言团队成本 | 真实存在。约束为「两语言纪律」：Python + Go，不引入第三门服务端语言；Rust 只作为被消费的引擎 |
| PG 成为单点瓶颈 | 预留分片逃生通道（Citus/TiDB/PolarDB-X 同接口切换）；Action 数据按租户+时间分区从第一天做起 |
| 契约漂移 | Proto 单一事实来源 + CI 双端契约测试 |

---

*活文档，随基准测试数据与企业落地反馈修订。*
