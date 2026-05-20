---
id: "NFR-02"
module: "cross-cutting"
title: "Docker Compose 一键启动"
priority: P0
status: draft
owner: ""
dependencies: []
milestone: "W1"
---

# [NFR-02] Docker Compose 一键启动

## 概述

提供单一 `docker-compose.yml` 文件，通过 `docker compose up -d` 一条命令启动完整的 Agentic MLOps 平台，包括所有后端服务、数据库、向量数据库、特征存储和前端应用。支持开发环境的热重载，并提供健康检查确保服务启动顺序正确。

## 验收标准

- [ ] AC-1: `docker compose up -d` 从零启动全栈，所有服务在 5 分钟内达到 healthy 状态
- [ ] AC-2: 所有服务定义健康检查（`healthcheck`），依赖服务通过 `depends_on: condition: service_healthy` 控制启动顺序
- [ ] AC-3: 提供 `.env.example` 文件，列出所有必需的环境变量及说明
- [ ] AC-4: `docker compose down -v` 清理所有容器和数据卷，不留残留
- [ ] AC-5: 开发模式（`docker compose -f docker-compose.yml -f docker-compose.dev.yml up`）支持代码热重载
- [ ] AC-6: 所有服务日志通过 `docker compose logs -f` 统一查看
- [ ] AC-7: 提供 `make up`、`make down`、`make logs` 等 Makefile 快捷命令

## 接口定义

```yaml
# docker-compose.yml 服务清单
services:
  # 基础设施
  postgres:
    image: postgres:16
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 5s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]

  qdrant:
    image: qdrant/qdrant:v1.10.0
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:6333/healthz"]

  opensearch:
    image: opensearchproject/opensearch:2.13.0
    environment:
      - discovery.type=single-node
      - OPENSEARCH_JAVA_OPTS=-Xms1g -Xmx1g

  # LLM 追踪
  langfuse:
    image: langfuse/langfuse:2
    depends_on:
      postgres:
        condition: service_healthy

  # OpenTelemetry
  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.100.0

  # 应用服务
  agent-core:
    build: ./packages/agent-core
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
      qdrant: { condition: service_healthy }

  mcp-gateway:
    build: ./packages/mcp-gateway
    depends_on:
      agent-core: { condition: service_healthy }

  rag-engine:
    build: ./packages/rag-engine
    depends_on:
      qdrant: { condition: service_healthy }
      opensearch: { condition: service_healthy }

  feature-store:
    build: ./packages/feature-store-adapter
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }

  web:
    build: ./apps/web
    ports:
      - "3001:3000"
    depends_on:
      agent-core: { condition: service_healthy }

# 端口映射汇总
# 3001: Web-IDE (Next.js)
# 3000: Langfuse UI
# 6333: Qdrant HTTP
# 6334: Qdrant gRPC
# 9200: OpenSearch HTTP
# 5432: PostgreSQL
# 6379: Redis
# 4317: OTLP gRPC
# 8888: Feast UI
```

```makefile
# Makefile 快捷命令
# make up      - 启动全栈
# make down    - 停止并清理
# make logs    - 查看所有日志
# make ps      - 查看服务状态
# make restart service=<name>  - 重启指定服务
# make seed    - 加载初始数据（欺诈检测数据集 + RAG 文档）
```

## 技术约束

- Docker Compose 版本：v2.24+（使用 `docker compose` 而非 `docker-compose`）
- 所有镜像使用固定版本标签，不使用 `latest`
- 数据卷命名规范：`agentic_mlops_{service}_{data_type}`
- 网络：所有服务在同一 Docker 网络 `agentic_mlops_net`
- 资源限制：OpenSearch 内存 2GB，其他服务无硬性限制（开发环境）
- 环境变量通过 `.env` 文件注入，敏感值（API Key）不提交到 Git

## 测试策略

- 集成测试：在 CI 环境执行 `docker compose up -d`，等待所有服务 healthy，执行 smoke test（各服务健康检查接口）
- 幂等测试：执行 `docker compose up -d` 两次，验证第二次无错误（已运行的服务不重启）
- 清理测试：执行 `docker compose down -v`，验证所有容器和数据卷被删除

## 依赖关系

- 被阻塞：[]
- 阻塞：[]

## 参考

- MVP_SPEC.md Section 5（部署）
