# 第一轮深度调研来源登记

> **范围**：本登记簿汇总六个方向在第一轮深度调研中实际使用的主要公开来源。所有条目都应在后续写入 Skill 或生成可执行规则前再次访问并核验版本、许可与适用范围。

| ID | 主方向 | 来源 | 类型 | 主要用途 |
|---|---|---|---|---|
| SRC-R1-01 | 01 | [RDF 1.1 Concepts](https://www.w3.org/TR/rdf11-concepts/) | W3C Recommendation | RDF 图、数据集和命名图的数据模型 |
| SRC-R1-02 | 01 | [OWL 2 Overview](https://www.w3.org/TR/owl2-overview/) | W3C Recommendation | 形式语义、推理和 Profile 边界 |
| SRC-R1-03 | 01 / 04 | [SHACL](https://www.w3.org/TR/shacl/) | W3C Recommendation | RDF 约束、验证与结果图 |
| SRC-R1-04 | 01 | [Neo4j Graph Concepts](https://neo4j.com/docs/getting-started/appendix/graphdb-concepts/) | 官方文档 | 属性图、标签、关系、属性和约束 |
| SRC-R1-05 | 02 | [Foundry Ontology Overview](https://palantir.com/docs/foundry/ontology/overview/) | 厂商官方文档 | 操作型本体的语义/动力学元素 |
| SRC-R1-06 | 02 | [Foundry Ontology System](https://palantir.com/docs/foundry/architecture-center/ontology-system/) | 厂商官方架构文档 | data、logic、action、security 的集成 |
| SRC-R1-07 | 02 | [Action Types Overview](https://palantir.com/docs/foundry/action-types/overview/) | 厂商官方文档 | 受治理写回、规则与副作用 |
| SRC-R1-08 | 02 | [Ontology SDK Overview](https://palantir.com/docs/foundry/ontology-sdk/overview/) | 厂商官方文档 | 类型化开发接口与 SDK 工作流 |
| SRC-R1-09 | 03 | [RAG 原始论文](https://proceedings.neurips.cc/paper_files/paper/2020/hash/6b493230205f780e1bc26945df7481e5-Abstract.html) | NeurIPS 2020 | 检索器与生成器基线 |
| SRC-R1-10 | 03 | [OG-RAG](https://aclanthology.org/2025.emnlp-main.1674/) | EMNLP 2025 | 本体约束超图上下文构造 |
| SRC-R1-11 | 03 | [HyDE](https://aclanthology.org/2023.acl-long.99/) | ACL 2023 | 假设文档与 dense retrieval 组合 |
| SRC-R1-12 | 03 | [Palantir OAG](https://palantir.com/docs/foundry/ontology/ontology-augmented-generation/) | 厂商官方文档 | 企业 OAG 术语与检索策略 |
| SRC-R1-13 | 03 | [Text2Cypher Schema Filtering](https://arxiv.org/html/2505.05118v2) | arXiv 预印本 | schema linking 的成本—召回权衡 |
| SRC-R1-14 | 04 | [SWRL](https://www.w3.org/submissions/SWRL/) | W3C Member Submission | OWL 与 Horn-like 规则的组合 |
| SRC-R1-15 | 04 | [OMG DMN](https://www.omg.org/dmn/) | 标准组织资料 | 业务决策、决策表与命中策略 |
| SRC-R1-16 | 04 | [Soufflé Tutorial](https://souffle-lang.github.io/tutorial) | 项目官方文档 | Datalog 终止性和方言扩展边界 |
| SRC-R1-17 | 04 | [Datalog Provenance Debugging](https://dl.acm.org/doi/10.1145/3379446) | ACM 2020 | 规则结果解释与调试 |
| SRC-R1-18 | 05 | [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence) | 项目官方文档 | 短期状态、长期记忆和恢复 |
| SRC-R1-19 | 05 | [OpenAI Agents SDK Guide](https://developers.openai.com/api/docs/guides/agents) | 官方文档 | 工具循环、handoff、状态和审批 |
| SRC-R1-20 | 05 | [OpenAI Guardrails](https://openai.github.io/openai-agents-python/guardrails/) | 官方 SDK 文档 | 输入/输出/工具层控制点 |
| SRC-R1-21 | 05 | [MCP Specification](https://modelcontextprotocol.io/specification/2026-07-28) | 协议规范 | Host/Client/Server、Tools 与明确同意 |
| SRC-R1-22 | 05 | [MCP Security Best Practices](https://modelcontextprotocol.io/specification/draft/basic/security_best_practices) | 协议草案 | OAuth、confused deputy 与逐客户端同意 |
| SRC-R1-23 | 06 | [NIST AI RMF 1.0](https://doi.org/10.6028/NIST.AI.100-1) | NIST 技术报告 | Govern/Map/Measure/Manage 风险框架 |
| SRC-R1-24 | 06 | [NIST GenAI Profile](https://doi.org/10.6028/NIST.AI.600-1) | NIST 技术报告 | 生成式 AI 特有风险与行动 |
| SRC-R1-25 | 06 | [RAGAs](https://aclanthology.org/2024.eacl-demo.16/) | EACL 2024 | 检索、忠实性和回答质量指标 |
| SRC-R1-26 | 06 | [ARES](https://aclanthology.org/2024.naacl-long.20/) | NAACL 2024 | 自动化多维 RAG 评估 |
| SRC-R1-27 | 06 | [AgentBench](https://proceedings.iclr.cc/paper_files/paper/2024/hash/e9df36b21df4ee211a8b71ee8b7e9f57-Paper-Conference.pdf) | ICLR 2024 | 交互式 Agent 评估 |
| SRC-R1-28 | 06 | [OWASP GenAI LLM Top 10](https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/) | 安全风险基线 | 注入、供应链、敏感信息和过度自治 |

## 复现代码索引

| 方向 | 项目 | 研究用途 |
|---|---|---|
| 01 / 04 | [Apache Jena](https://jena.apache.org/)、[pySHACL](https://github.com/RDFLib/pySHACL)、[Soufflé](https://github.com/souffle-lang/souffle) | 语义、验证与逻辑规则基线 |
| 02 | [OSDK TypeScript](https://github.com/palantir/osdk-ts)、[Foundry Python SDK](https://github.com/palantir/foundry-platform-python) | Foundry 开发接口研究 |
| 03 | [OG-RAG](https://github.com/microsoft/ograg2)、[GraphRAG](https://github.com/microsoft/graphrag)、[HyDE](https://github.com/texttron/hyde) | 本体/图/检索增强实验 |
| 05 | [LangGraph](https://github.com/langchain-ai/langgraph)、[OpenAI Agents SDK](https://github.com/openai/openai-agents-python)、[MCP Spec](https://github.com/modelcontextprotocol/specification) | Harness、工具与协议基线 |
| 06 | [OpenAI Evals](https://github.com/openai/evals)、[Ragas](https://github.com/explodinggradients/ragas)、[Langfuse](https://github.com/langfuse/langfuse) | 离线评测、线上观测和回归门禁 |

## 证据等级

W3C、OMG、NIST 和正式会议/期刊论文可用于定义与方法主张；厂商文档用于陈述该厂商公开能力；预印本、项目 README 和社区资料只用于提出假设或复现实验，不可单独支持通用结论。受限资料不进入仓库，也不得作为工程结论的唯一证据；相关问题须由公开来源或项目实验独立复核。
