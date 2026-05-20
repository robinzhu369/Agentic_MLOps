# OpenSpec Index — Agentic MLOps MVP

> 状态看板：所有功能 Spec 的追踪索引

## Module 1: Agent Core (`packages/agent-core/`) — W3/W7

| ID | 标题 | 优先级 | 状态 | 里程碑 | Owner |
| --- | --- | --- | --- | --- | --- |
| A-01 | 自然语言意图理解 | P0 | draft | W3 | |
| A-02 | 多步任务规划（Planner） | P0 | draft | W3 | |
| A-03 | 双循环执行（Outer + Inner Loop） | P0 | draft | W3 | |
| A-04 | 工具调用（通过 MCP） | P0 | draft | W3 | |
| A-05 | 短期记忆（会话内） | P0 | draft | W3 | |
| A-06 | 长期记忆（向量检索） | P0 | draft | W7 | |
| A-07 | Skill Library 检索 | P0 | draft | W7 | |
| A-08 | Self-Critique 评估 | P1 | draft | W7 | |
| A-09 | Skill 自动抽象（Learning Loop） | P1 | draft | W7 | |
| A-10 | 思考链可视化输出 | P0 | draft | W3 | |

## Module 2: MCP Gateway (`packages/mcp-gateway/`) — W2/W5

| ID | 标题 | 优先级 | 状态 | 里程碑 | Owner |
| --- | --- | --- | --- | --- | --- |
| G-01 | 工具能力发现（Capability Manifest） | P0 | draft | W2 | |
| G-02 | 统一认证（JWT） | P0 | draft | W2 | |
| G-03 | 基础 RBAC（admin / scientist） | P0 | draft | W2 | |
| G-04 | 调用路由 | P0 | draft | W2 | |
| G-05 | 结构化审计日志 | P0 | draft | W2 | |
| G-06 | 调用熔断 | P1 | draft | W2 | |
| G-07 | dry_run 支持 | P1 | draft | W5 | |
| G-08 | PII 脱敏 | P0 | draft | W2 | |
| MCP-S1 | mcp-jupyter Server | P0 | draft | W2 | |
| MCP-S2 | mcp-feature-store Server | P0 | draft | W5 | |
| MCP-S3 | mcp-data-catalog Server | P0 | draft | W5 | |

## Module 3: RAG Engine (`packages/rag-engine/`) — W4

| ID | 标题 | 优先级 | 状态 | 里程碑 | Owner |
| --- | --- | --- | --- | --- | --- |
| R-01 | 文档接入（PDF/Markdown/Wiki） | P0 | draft | W4 | |
| R-02 | Chunk 切分（章节+滑窗） | P0 | draft | W4 | |
| R-03 | Embedding 生成（bge-small-zh） | P0 | draft | W4 | |
| R-04 | 向量检索（Qdrant） | P0 | draft | W4 | |
| R-05 | 混合检索（向量+BM25） | P1 | draft | W4 | |
| R-06 | Re-ranking（bge-reranker） | P1 | draft | W4 | |
| R-07 | 元数据过滤（按域） | P0 | draft | W4 | |
| R-08 | 增量更新 | P1 | draft | W4 | |
| R-09 | Context 注入 Agent | P0 | draft | W4 | |

## Module 4: Web-IDE (`apps/web/`) — W6/W8

| ID | 标题 | 优先级 | 状态 | 里程碑 | Owner |
| --- | --- | --- | --- | --- | --- |
| U-01 | 项目管理（创建/切换） | P0 | draft | W6 | |
| U-02 | 代码编辑器（Monaco） | P0 | draft | W6 | |
| U-03 | Notebook 视图 | P0 | draft | W6 | |
| U-04 | Agent Chat 面板 | P0 | draft | W6 | |
| U-05 | 思考链可视化 | P0 | draft | W6 | |
| U-06 | HITL 确认弹窗 | P0 | draft | W6 | |
| U-07 | 实验对比看板 | P1 | draft | W8 | |
| U-08 | 特征/模型列表侧边栏 | P1 | draft | W8 | |
| U-09 | 文件浏览器 | P0 | draft | W6 | |
| U-10 | 暗色/亮色主题切换 | P2 | draft | W8 | |

## Module 5: Feature Store (`packages/feature-store-adapter/`) — W5/W8

| ID | 标题 | 优先级 | 状态 | 里程碑 | Owner |
| --- | --- | --- | --- | --- | --- |
| F-01 | Feast 部署与初始化 | P0 | draft | W5 | |
| F-02 | 离线存储（PostgreSQL） | P0 | draft | W5 | |
| F-03 | 在线存储（Redis） | P0 | draft | W5 | |
| F-04 | 特征视图注册（通过 MCP） | P0 | draft | W5 | |
| F-05 | 特征物化（materialize） | P0 | draft | W5 | |
| F-06 | 实时特征写入（流式） | P1 | draft | W8 | |
| F-07 | 特征质量监控（IV/PSI） | P1 | draft | W8 | |
| F-08 | 特征血缘 | P1 | draft | W8 | |

## Cross-cutting — W1/W8

| ID | 标题 | 优先级 | 状态 | 里程碑 | Owner |
| --- | --- | --- | --- | --- | --- |
| NFR-01 | 可观测性（OpenTelemetry + Langfuse） | P0 | draft | W1 | |
| NFR-02 | Docker Compose 一键启动 | P0 | draft | W1 | |
| NFR-03 | 测试覆盖率 ≥70% | P0 | draft | W8 | |
| E2E-01 | 黄金路径端到端测试 | P0 | draft | W8 | |

## 统计

- 总计：52 个 Spec
- P0：38 个
- P1：12 个
- P2：2 个
- 状态：draft 52 / ready 0 / in-progress 0 / done 0
