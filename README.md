# Agentic MLOps Platform

> Code-First 智能体驱动机器学习建模平台

## Quick Start

```bash
# 1. 启动基础设施
make up

# 2. 初始化环境（加载数据、灌入知识库）
scripts/bootstrap.sh

# 3. 启动后端
cd apps/api && uvicorn main:app --reload

# 4. 启动前端
cd apps/web && npm run dev
```

## 项目结构

```
├── apps/
│   ├── api/          # FastAPI 后端
│   └── web/          # Next.js 前端
├── packages/
│   ├── agent-core/   # Agent 核心（Planner, Executor, Critic, Skills）
│   ├── mcp-gateway/  # MCP 网关（认证、路由、审计）
│   ├── mcp-servers/  # MCP 服务（jupyter, feature-store, data-catalog）
│   ├── rag-engine/   # RAG 引擎（向量检索、混合检索）
│   ├── feature-store-adapter/  # Feast 封装
│   └── shared/       # 公共工具（telemetry, logging, config）
├── deploy/           # Docker Compose 编排
├── specs/            # OpenSpec 需求规格
├── scripts/          # 工具脚本
├── tests/            # E2E / 集成测试
└── docs/             # 文档
```

## 开发

```bash
# 安装依赖
uv sync

# 代码质量
ruff check .
mypy packages/

# 测试
pytest
pytest packages/agent-core/tests/  # 单模块

# Docker
make up      # 启动
make down    # 停止
make logs    # 查看日志
make reset   # 重置数据
```

## 文档

- [MVP 需求规格](docs/MVP_SPEC.md)
- [任务卡](docs/TASK_CARDS.md)
- [OpenSpec 索引](specs/_index.md)
