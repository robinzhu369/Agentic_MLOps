# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Agentic MLOps Platform — Code-First 智能体驱动机器学习建模平台。MVP 锚定信用卡反欺诈场景：用户在 Web-IDE 输入"为信用卡交易表构建反欺诈模型"，Agent 自主完成数据探查、合规检查、特征工程、模型训练，所有工具通过 MCP 协议统一调用，最终返回 AUC ≥ 0.90 的基线模型。

权威需求文档：`docs/MVP_SPEC.md`

## 技术栈

| 层级 | 选型 |
| --- | --- |
| LLM | Anthropic Claude API (claude-sonnet-4) |
| Agent 框架 | LangGraph 0.2+ (Hermes 风格循环) |
| MCP | Anthropic MCP Python SDK |
| 后端 | FastAPI + Uvicorn (异步) |
| 任务队列 | Celery + Redis |
| 向量库 | Qdrant 1.10+ |
| 全文检索 | OpenSearch 2.x (中文分词) |
| Embedding | bge-small-zh-v1.5 |
| 关系库 | PostgreSQL 16 + pgvector |
| 缓存 | Redis 7.x |
| Feature Store | Feast 0.40+ |
| 训练框架 | LightGBM + scikit-learn |
| 实验追踪 | MLflow 2.14+ |
| 前端 | Next.js 14 + TypeScript |
| 编辑器 | Monaco Editor |
| UI 组件 | shadcn/ui + Tailwind CSS |
| 可观测性 | OpenTelemetry + Langfuse |
| 容器化 | Docker + Docker Compose |

## 架构（5 大模块）

1. **Agent 核心 + Hermes Skill 库** (`packages/agent-core/`) — Planner → Executor（双循环）→ Self-Critique。Memory Hub (pgvector) 提供长期记忆检索。Skill Library 以 JSON + Jinja2 模板存储可复用原子能力，通过语义 Embedding 召回。

2. **MCP Gateway** (`packages/mcp-gateway/`) — 所有工具调用的唯一入口。负责 JWT 认证、RBAC（admin/scientist）、路由分发、结构化审计日志、PII 脱敏、调用熔断。

3. **MCP Servers** (`packages/mcp-servers/`) — Gateway 后面挂 3 个 Server：
   - `mcp-jupyter` — 代码执行、Kernel 生命周期管理
   - `mcp-feature-store` — Feast 特征视图 CRUD、物化、在线特征获取
   - `mcp-data-catalog` — Schema 发现、数据 Profiling、采样

4. **RAG 知识库引擎** (`packages/rag-engine/`) — 混合检索（Qdrant 向量 + OpenSearch BM25）+ bge-reranker 重排序。预置反欺诈合规文档、AML 规则、特征工程模板。

5. **Web-IDE / Copilot 面板** (`apps/web/`) — Next.js 14 应用，集成 Monaco 编辑器、Agent 对话面板（WebSocket/SSE 流式）、思考链可视化、HITL 确认弹窗。

## 常用命令

```bash
# 全栈本地启动
docker-compose up

# 初始化（建库、加载数据、灌入知识库）
scripts/bootstrap.sh
scripts/load_sample_data.py
scripts/seed_knowledge_base.py

# Python 代码质量
ruff check .
black .
mypy .

# 测试
pytest                                    # 全量测试
pytest packages/agent-core/tests/         # 单模块测试
pytest tests/e2e/test_fraud_demo.py       # 黄金路径 E2E

# 前端
cd apps/web && npm run dev                # 开发服务器
cd apps/web && npm run build              # 生产构建
```

## 核心设计决策

- **所有工具调用必须经过 MCP Gateway** — Agent 不直连任何工具，统一走网关实现认证、审计、PII 脱敏。
- **双循环执行** — 外循环遍历 Plan 步骤；内循环在单步失败时重试/调整。
- **Skill 自动蒸馏** — 高分实验完成后，Agent 将流程抽象为新 Skill 写入库（Learning Loop）。
- **关键步骤 HITL** — 写操作（注册特征、删除数据）需用户在 UI 点击确认。
- **流式输出** — Agent 通过 SSE 推送 Plan/ToolCall/Observation 事件，前端实时渲染思考链。

## 开发规范

- Commit 遵循 Conventional Commits。
- PR 必须关联 Issue。
- 新增 MCP Server 必须补充集成测试。
- 核心模块改动至少 1 位 Reviewer 批准。
- Python：Black + Ruff + mypy strict。前端：TypeScript strict mode。
- 每个 `packages/*` 目录需有独立 README。
- 架构决策记录在 `docs/adr/`。

## 数据

MVP 使用 Kaggle Credit Card Fraud Detection 公开数据集（284,807 笔交易，492 笔欺诈）。特征 V1–V28 为 PCA 变换后的脱敏数据，无真实 PII。

---

## 开发纪律（Superpowers）

以下规则在每次 Claude Code 会话中强制执行。

### MCP 协议合规

- Agent Core 禁止直接 import 工具库。`packages/agent-core/` 中不得出现 `import jupyter_client`、`import feast`、`from feast`、`import sqlalchemy`（用于直连数据库）。
- 所有工具交互必须通过 MCP Gateway 客户端发起。
- 每个 MCP Server 必须实现 `list_tools()` 和 `call_tool()` 方法，严格遵循 Anthropic MCP Spec。
- MCP 工具响应使用标准信封格式：`{ "content": [...], "isError": bool }`。不得从 MCP handler 中抛出裸异常。
- Tool name 使用 snake_case：`execute_code`、`list_feature_views`、`get_schema`。
- 每次 MCP 调用必须在 metadata 中携带 `audit_id`。

### 禁止模式

- NO `print()` 用于日志 — 使用 `structlog` 并绑定上下文
- NO `from X import *` — 必须显式导入
- NO bare `except:` — 必须捕获具体异常类型
- NO `datetime.now()` 无时区 — 使用 `datetime.now(tz=timezone.utc)`
- NO 可变默认参数（`def f(x=[])`）
- NO 硬编码密钥或连接字符串 — 通过 pydantic-settings 加载环境变量
- NO 异步代码路径中的同步阻塞调用

### 模块边界

- `packages/X` 不得直接 import `packages/Y`。跨模块通信通过定义好的 API 或消息传递。
- Agent Core → MCP Servers 的唯一路径是 MCP Gateway。在 agent-core 代码中出现 `from packages.mcp_servers` 视为构建错误。
- 所有配置通过环境变量加载，每个 package 有独立的 `config.py`（使用 pydantic-settings）。
- 数据库 schema 变更通过 Alembic 迁移，不在应用代码中写裸 DDL。

### 测试要求

- 每个新模块文件必须有对应的测试文件（镜像目录结构）。
- 核心模块覆盖率 ≥70%，工具类 ≥50%。
- MCP Server 的每个 tool 至少一个集成测试（mock 后端）。
- Agent Core 的每个 Skill 必须有 input/output schema 合规测试。
- 使用 `pytest` + `pytest-asyncio`。测试文件命名：`test_{module}.py`。
- 测试数据使用 factory 模式，不使用有副作用的 fixture。

### 代码风格

- Python：Black (line-length=88) + Ruff (select=["E","F","I","W","UP","B","SIM"]) + mypy (strict=true)
- TypeScript：strict mode，禁止 `any` 类型，ESLint + Prettier
- 所有函数必须有类型注解（参数 + 返回值）
- 所有 public 函数必须有 docstring（Google style）
- API 请求/响应 schema 使用 Pydantic model，禁止裸 dict 跨模块边界
- 所有 Python 文件顶部：`from __future__ import annotations`

### Git 纪律

- Commit message：Conventional Commits（`feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`）
- 模块变更必须带 scope：`feat(agent-core): add skill retrieval`
- 一个 commit 一个逻辑变更，不混合功能代码与格式化
- 分支命名：`feat/A-01-intent-understanding`、`fix/G-03-rbac-deny`

### Spec 驱动开发

- 实现任何功能前，先查 `specs/` 目录下对应的 spec 文件。
- 实现必须满足 spec 中列出的所有验收标准。
- 如果 spec 缺失或不清晰，先创建/更新 spec 再写代码。
- 实现完成后，更新 spec 的 status 为 `done`，勾选验收标准。
- 总索引：`specs/_index.md`。
