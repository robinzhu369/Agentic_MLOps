# Agentic MLOps Platform

> Code-First 智能体驱动机器学习建模平台

用户在 Web-IDE 输入自然语言指令（如"为信用卡交易表构建反欺诈模型"），Agent 自主完成数据探查、合规检查、特征工程、模型训练，所有工具通过 MCP 协议统一调用，最终返回 AUC ≥ 0.90 的基线模型。

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        Web-IDE (Next.js)                         │
│   Monaco Editor  │  Agent Chat (SSE)  │  Thinking Chain View    │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP / SSE
┌────────────────────────────▼────────────────────────────────────┐
│                      FastAPI Backend                              │
│   POST /api/v1/agent/sessions/{id}/messages                      │
│   GET  /api/v1/agent/sessions/{id}/stream                        │
│   POST /api/v1/agent/sessions/{id}/confirm                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                     Agent Core (LangGraph)                        │
│                                                                   │
│  ┌──────────┐   ┌──────────┐   ┌──────────────────────┐         │
│  │  Intent  │──▶│ Planner  │──▶│  Dual-Loop Executor  │         │
│  │  Parser  │   │          │   │  (Outer + Inner)     │         │
│  └──────────┘   └──────────┘   └──────────┬───────────┘         │
│                       ▲                     │                     │
│                       │                     ▼                     │
│              ┌────────┴───┐        ┌──────────────┐              │
│              │   Skill    │        │ Self-Critique │              │
│              │  Library   │        │  Evaluator   │              │
│              └────────────┘        └──────────────┘              │
└────────────────────────────┬────────────────────────────────────┘
                             │ MCP Protocol
┌────────────────────────────▼────────────────────────────────────┐
│                      MCP Gateway                                  │
│   JWT Auth │ RBAC │ PII Masking │ Audit Log │ Circuit Breaker    │
└───────┬────────────────┬───────────────────┬────────────────────┘
        │                │                   │
   ┌────▼────┐    ┌──────▼──────┐    ┌──────▼──────┐
   │  mcp-   │    │    mcp-     │    │    mcp-     │
   │ jupyter │    │feature-store│    │data-catalog │
   └─────────┘    └─────────────┘    └─────────────┘
```

## 技术栈

| 层级 | 选型 |
|------|------|
| LLM | Anthropic Claude (claude-sonnet-4) |
| Agent 框架 | LangGraph 0.2+ |
| MCP | Anthropic MCP Python SDK |
| 后端 | FastAPI + Uvicorn |
| 向量库 | Qdrant 1.10+ |
| Embedding | bge-small-zh-v1.5 |
| 关系库 | PostgreSQL 16 |
| 缓存/会话 | Redis 7.x |
| Feature Store | Feast 0.40+ |
| 训练框架 | LightGBM + scikit-learn |
| 前端 | Next.js 14 + TypeScript + Monaco Editor |
| 可观测性 | OpenTelemetry + Langfuse |
| 包管理 | uv (workspace monorepo) |

## 快速开始

```bash
# 前置条件: Python 3.11+, uv, Docker, Node.js 18+

# 1. 安装依赖
uv sync

# 2. 启动基础设施 (PostgreSQL, Redis, Qdrant)
make up

# 3. 初始化环境
scripts/bootstrap.sh

# 4. 启动后端 API
uv run uvicorn api_app.main:app --reload --app-dir apps/api

# 5. 启动前端 (另一个终端)
cd apps/web && npm install && npm run dev
```

## 项目结构

```
agentic_mlops/
├── apps/
│   ├── api/                    # FastAPI 后端入口
│   │   └── api_app/
│   │       ├── main.py         # App + lifespan + CORS
│   │       └── routers/
│   │           └── agent.py    # Agent 会话/消息/确认/流式 API
│   └── web/                    # Next.js 14 前端 (Web-IDE)
│
├── packages/
│   ├── agent-core/             # Agent 核心引擎
│   │   └── agent_core/
│   │       ├── hermes/         # Hermes Agent 实现
│   │       │   ├── intent.py       # A-01: 意图解析 (Claude API)
│   │       │   ├── planner.py      # A-02: 多步规划 + 工具白名单
│   │       │   ├── executor.py     # A-03: 双循环执行器
│   │       │   ├── mcp_client.py   # A-04: MCP 工具调用客户端
│   │       │   ├── memory.py       # A-05: Redis 短期记忆
│   │       │   ├── stream.py       # A-10: SSE 流式输出
│   │       │   ├── critic.py       # A-08: Self-Critique 评估
│   │       │   ├── schemas.py      # 核心数据模型
│   │       │   └── config.py       # 配置 (pydantic-settings)
│   │       ├── skills/
│   │       │   └── library.py      # A-07: Skill Library + 3 内置 Skill
│   │       └── tests/              # 90+ 单元测试
│   │
│   ├── mcp-gateway/            # MCP 统一网关
│   │   └── mcp_gateway/
│   │       ├── gateway.py          # FastAPI 网关应用
│   │       ├── auth.py             # JWT 认证
│   │       ├── rbac.py             # 角色权限控制
│   │       ├── router.py           # 工具调用路由
│   │       ├── registry.py         # Capability Manifest
│   │       ├── audit.py            # 审计日志
│   │       ├── pii.py              # PII 脱敏
│   │       └── schemas.py          # 网关数据模型
│   │
│   ├── mcp-servers/            # MCP 工具服务
│   │   └── mcp_servers/
│   │       ├── jupyter/            # 代码执行 (4 tools)
│   │       ├── feature_store/      # 特征管理 (5 tools)
│   │       └── data_catalog/       # 数据目录 (4 tools)
│   │
│   ├── rag-engine/             # RAG 知识库引擎
│   │   └── rag_engine/
│   │       ├── ingestion.py        # 文档解析 + Chunk 切分
│   │       ├── embedding.py        # bge-small-zh 向量化
│   │       ├── retrieval.py        # Qdrant 向量检索
│   │       └── context.py          # Agent 上下文注入
│   │
│   ├── feature-store-adapter/  # Feast 集成适配器
│   └── shared/                 # 公共库
│       └── shared_lib/
│           ├── config.py           # 全局配置
│           ├── logging.py          # structlog JSON 日志
│           └── telemetry.py        # OpenTelemetry 链路追踪
│
├── deploy/                     # Docker Compose 编排
├── specs/                      # OpenSpec 需求规格 (52 specs)
├── scripts/                    # 工具脚本
├── tests/                      # E2E 测试
└── docs/                       # 项目文档
```

## 核心工作流

```
用户: "为信用卡交易表构建反欺诈模型"
  │
  ▼
IntentParser → IntentResult(task_type=TRAIN_MODEL, entities={dataset: creditcard})
  │
  ▼
Planner → Plan(steps=[get_schema, profile_data, train_model, evaluate])
  │
  ▼
DualLoopExecutor:
  ├─ Outer Loop: 按依赖拓扑序执行步骤
  │   ├─ Inner Loop: 单步执行 + 重试 (max 3, 指数退避)
  │   ├─ HITL: requires_confirm=True 时暂停等待用户确认
  │   └─ Replan: 连续失败后重新规划 (max 2)
  │
  ▼
SSE Stream → 前端实时渲染思考链
  │
  ▼
SelfCritic → 评估执行质量 → 高分时蒸馏为新 Skill
```

## 开发命令

```bash
# 依赖管理
uv sync                              # 安装所有依赖
uv add <pkg> --package <workspace>   # 添加依赖到指定包

# 代码质量
uv run ruff check .                  # Lint (E/F/I/W/UP/B/SIM)
uv run ruff check . --fix            # 自动修复
uv run mypy packages/                # 类型检查 (strict)

# 测试
uv run pytest                        # 全量测试 (155 tests)
uv run pytest packages/agent-core/   # Agent Core 模块
uv run pytest packages/rag-engine/   # RAG 引擎
uv run pytest packages/mcp-servers/  # MCP 服务
uv run pytest --cov=packages/        # 覆盖率报告

# Docker
make up                              # 启动基础设施
make down                            # 停止
make logs                            # 查看日志
make reset                           # 重置数据

# 前端
cd apps/web && npm run dev           # 开发服务器
cd apps/web && npm run build         # 生产构建
```

## MCP 工具清单

Agent 通过 MCP Gateway 调用以下工具：

| Server | Tool | 描述 |
|--------|------|------|
| jupyter | `execute_code` | 在 Kernel 中执行 Python 代码 |
| jupyter | `create_kernel` | 创建新 Kernel |
| jupyter | `list_variables` | 列出 Kernel 变量 |
| jupyter | `restart_kernel` | 重启 Kernel |
| data_catalog | `list_tables` | 列出数据表 |
| data_catalog | `get_schema` | 获取表结构 |
| data_catalog | `sample_rows` | 采样数据 |
| data_catalog | `profile_column` | 列统计分析 |
| feature_store | `list_feature_views` | 列出特征视图 |
| feature_store | `register_feature_view` | 注册特征视图 |
| feature_store | `materialize` | 物化到在线存储 |
| feature_store | `get_online_features` | 获取在线特征 |
| feature_store | `compute_feature_stats` | 特征统计 |

## 环境变量

```bash
# LLM
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514

# Agent
AGENT_INTENT_CONFIDENCE_THRESHOLD=0.7
AGENT_MAX_PLAN_STEPS=20
AGENT_MAX_RETRIES_PER_STEP=3
AGENT_MAX_REPLANS=2

# MCP Gateway
MCP_GATEWAY_HOST=localhost
MCP_GATEWAY_PORT=8100
MCP_GATEWAY_JWT_SECRET_KEY=change-in-production

# 基础设施
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
REDIS_URL=redis://localhost:6379/0
QDRANT_HOST=localhost
QDRANT_PORT=6333

# RAG
RAG_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
RAG_CHUNK_SIZE=512
RAG_SCORE_THRESHOLD=0.5
```

## 设计决策

- **MCP 协议统一调用** — Agent 不直连任何工具，所有调用经 MCP Gateway 实现认证、审计、PII 脱敏
- **双循环执行** — 外循环遍历 Plan 步骤（支持并发），内循环处理单步重试（指数退避）
- **Skill 自动蒸馏** — 高分实验完成后，Agent 将流程抽象为新 Skill 写入库
- **HITL 关键步骤** — 写操作（注册特征、删除数据）需用户在 UI 点击确认
- **流式输出** — Agent 通过 SSE 推送 Plan/ToolCall/Observation 事件，前端实时渲染

## 数据

MVP 使用 [Kaggle Credit Card Fraud Detection](https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud) 公开数据集：
- 284,807 笔交易，492 笔欺诈 (0.17%)
- 特征 V1–V28 为 PCA 变换后的脱敏数据
- 目标列 `Class` (0=正常, 1=欺诈)

## 文档

- [MVP 需求规格](docs/MVP_SPEC.md)
- [任务卡](docs/TASK_CARDS.md)
- [OpenSpec 索引](specs/_index.md)
- [架构决策记录](docs/adr/)

## License

MIT
