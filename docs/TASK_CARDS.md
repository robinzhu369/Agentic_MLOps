# 系统任务卡 — Agentic MLOps MVP

> 遵循软件工程原则：自底向上构建、接口先行、持续集成、增量交付
>
> 执行规则：
> 1. 按 TASK 编号顺序执行，除非依赖关系允许并行
> 2. 每个 TASK 完成后必须通过其「完成标志」验证
> 3. 每个 TASK 对应一个 git 分支（`feat/TASK-XX-简述`）和一个 PR
> 4. 不得跳过测试步骤

---

## TASK-01: 项目骨架初始化

**目标**：建立 monorepo 基础结构，使所有后续开发有统一的依赖管理和构建入口。

**依赖**：无

**交付物**：
- `pyproject.toml`（uv workspace，Python 3.11+）
- `packages/agent-core/pyproject.toml`
- `packages/mcp-gateway/pyproject.toml`
- `packages/mcp-servers/pyproject.toml`
- `packages/rag-engine/pyproject.toml`
- `packages/feature-store-adapter/pyproject.toml`
- `apps/web/package.json`（Next.js 14 + TypeScript）
- `apps/api/pyproject.toml`（FastAPI 入口）
- `.gitignore`、`.python-version`、`README.md`

**完成标志**：
- [ ] `uv sync` 成功安装所有 Python 依赖
- [ ] `cd apps/web && npm install` 成功
- [ ] 项目根目录 `pytest --collect-only` 无报错
- [ ] `git init` + 首次 commit 完成

---

## TASK-02: Docker Compose 基础设施

**目标**：一键拉起所有外部依赖服务，开发者无需手动安装数据库。

**依赖**：TASK-01

**Spec 关联**：NFR-02

**交付物**：
- `deploy/docker-compose.yml`（PostgreSQL 16、Redis 7、Qdrant 1.10、OpenSearch 2.x）
- `deploy/docker-compose.dev.yml`（开发模式覆盖，热重载）
- `.env.example`
- `Makefile`（`make up`、`make down`、`make logs`、`make reset`）
- `scripts/wait-for-services.sh`（健康检查等待脚本）

**完成标志**：
- [ ] `make up` 后所有容器 healthy（< 90s）
- [ ] PostgreSQL 可连接（`psql -h localhost -U postgres`）
- [ ] Redis 可连接（`redis-cli ping` → PONG）
- [ ] Qdrant API 可访问（`curl localhost:6333/collections`）
- [ ] `make down` 清理干净

---

## TASK-03: CI 流水线 + 代码质量门禁

**目标**：建立自动化质量保障，每次 PR 自动运行 lint + test。

**依赖**：TASK-01

**交付物**：
- `.github/workflows/ci.yml`（lint → type-check → test → coverage）
- `ruff.toml`（select=["E","F","I","W","UP","B","SIM"]）
- `mypy.ini`（strict=true）
- `apps/web/.eslintrc.json` + `prettier.config.js`

**完成标志**：
- [ ] 推送到任意分支触发 CI
- [ ] `ruff check .` 零错误
- [ ] `mypy packages/` 零错误（空包通过）
- [ ] CI 在 GitHub Actions 中绿色通过

---

## TASK-04: 可观测性基础

**目标**：埋入 tracing 基础设施，后续所有模块自动获得链路追踪能力。

**依赖**：TASK-02

**Spec 关联**：NFR-01

**交付物**：
- `packages/shared/telemetry.py`（`setup_telemetry()`、`@trace_llm_call`、`@trace_mcp_tool` 装饰器）
- Docker Compose 中增加 OTEL Collector + Langfuse
- `packages/shared/logging.py`（structlog 配置，JSON 格式，自动注入 trace_id）

**完成标志**：
- [ ] `setup_telemetry()` 调用后，span 数据发送到 OTEL Collector
- [ ] Langfuse UI 可在 `localhost:3000` 访问
- [ ] 日志输出包含 `trace_id` 和 `span_id` 字段
- [ ] 装饰器单元测试通过

---

## TASK-05: MCP Gateway 骨架

**目标**：实现 MCP Gateway 的核心中间件链，为所有 MCP Server 提供统一入口。

**依赖**：TASK-01, TASK-04

**Spec 关联**：G-01, G-02, G-03, G-04, G-05, G-08

**交付物**：
- `packages/mcp-gateway/gateway.py`（FastAPI app）
- `packages/mcp-gateway/auth.py`（JWT 验证，HS256）
- `packages/mcp-gateway/rbac.py`（admin / scientist 两角色）
- `packages/mcp-gateway/router.py`（按 tool_name 前缀路由）
- `packages/mcp-gateway/audit.py`（JSON Lines 审计日志）
- `packages/mcp-gateway/pii.py`（正则 + Luhn 校验脱敏）
- `packages/mcp-gateway/registry.py`（Capability Manifest 缓存）
- `packages/mcp-gateway/tests/`

**接口契约**：
```
POST /mcp/tools/call    — 统一工具调用入口
GET  /mcp/capabilities  — 返回所有已注册工具清单
POST /mcp/servers       — 动态注册 MCP Server
```

**完成标志**：
- [ ] 无 JWT → 401；无效角色 → 403
- [ ] `GET /mcp/capabilities` 返回已注册工具列表（< 200ms）
- [ ] 审计日志写入文件，包含 audit_id、user、tool、timestamp
- [ ] PII 脱敏：身份证号、银行卡号在响应中被掩码
- [ ] 单元测试覆盖率 ≥ 70%

---

## TASK-06: mcp-jupyter Server

**目标**：实现代码执行能力，Agent 可通过 MCP 协议在 Jupyter Kernel 中运行 Python 代码。

**依赖**：TASK-05

**Spec 关联**：MCP-S1

**交付物**：
- `packages/mcp-servers/jupyter/server.py`（MCPJupyterServer）
- `packages/mcp-servers/jupyter/kernel_manager.py`
- `packages/mcp-servers/jupyter/tests/`
- Docker Compose 中增加 Jupyter Kernel Gateway

**工具清单**：
```python
execute_code(code: str, kernel_id: str) -> ExecuteResult
create_kernel(language: str = "python3") -> KernelInfo
list_variables(kernel_id: str) -> list[Variable]
restart_kernel(kernel_id: str) -> bool
```

**完成标志**：
- [ ] `list_tools()` 返回 4 个工具的完整 MCP Schema
- [ ] `execute_code("1+1", kernel_id)` 返回 `{"result": "2"}`
- [ ] 代码执行超时（300s）返回 MCP 格式错误，不崩溃
- [ ] 通过 MCP Gateway 调用成功（端到端）
- [ ] 集成测试通过

---

## TASK-07: Agent Core — 意图解析 + Planner

**目标**：实现 Agent 的"大脑"——理解用户意图并生成执行计划。

**依赖**：TASK-05（需要 Capability Manifest 做工具白名单校验）

**Spec 关联**：A-01, A-02

**交付物**：
- `packages/agent-core/hermes/intent.py`（IntentParser）
- `packages/agent-core/hermes/planner.py`（Planner，LangGraph node）
- `packages/agent-core/hermes/schemas.py`（IntentResult, PlanStep, Plan）
- `packages/agent-core/tests/`

**接口契约**：
```python
IntentParser.parse(user_message, session_context) -> IntentResult
Planner.create_plan(intent: IntentResult, capabilities: list[Tool]) -> Plan
Planner.replan(plan: Plan, failed_step: PlanStep, error: str) -> Plan
```

**完成标志**：
- [ ] 给定"为信用卡交易表构建反欺诈模型"，输出包含 ≥3 步的 Plan
- [ ] Plan 中 tool_name 全部在 Capability Manifest 白名单内
- [ ] 歧义输入返回 `clarification_needed=True`
- [ ] 高风险步骤自动标记 `requires_confirm=True`
- [ ] 20 条 golden-set 测试通过率 ≥ 95%

---

## TASK-08: Agent Core — 双循环执行器

**目标**：实现 Plan 的自动执行引擎，支持重试、replan、HITL 暂停。

**依赖**：TASK-07, TASK-06

**Spec 关联**：A-03, A-04, A-05, A-10

**交付物**：
- `packages/agent-core/hermes/executor.py`（DualLoopExecutor）
- `packages/agent-core/hermes/memory.py`（Redis 短期记忆）
- `packages/agent-core/hermes/stream.py`（SSE 事件发射器）
- `apps/api/routers/agent.py`（Agent HTTP/WS 路由）
- `packages/agent-core/tests/`

**接口契约**：
```python
DualLoopExecutor.execute(plan: Plan, session_id: str) -> AsyncGenerator[StreamEvent]
DualLoopExecutor.confirm_step(session_id: str, step_id: int) -> None

# SSE 事件类型
event: plan          — 计划生成
event: tool_call     — 工具调用开始
event: observation   — 步骤结果
event: confirm_required — 需要人工确认
event: completed     — 全部完成
event: error         — 执行失败
```

**完成标志**：
- [ ] 3 步 Plan 按序执行，每步通过 MCP Gateway 调用工具
- [ ] 步骤失败自动重试（最多 3 次，指数退避）
- [ ] 3 次重试后触发 replan（最多 2 次）
- [ ] `requires_confirm=True` 步骤暂停，等待 confirm 后继续
- [ ] SSE 流正确推送所有事件类型
- [ ] Redis 中可查询当前 session 状态

**里程碑检查点**：TASK-08 完成后，Agent 能通过 MCP 调用 Jupyter 执行 Pandas 代码并返回结果。

---

## TASK-09: RAG 知识库引擎

**目标**：实现文档入库和语义检索，为 Agent 提供领域知识注入能力。

**依赖**：TASK-02（Qdrant、OpenSearch）

**Spec 关联**：R-01, R-02, R-03, R-04, R-07, R-09

**交付物**：
- `packages/rag-engine/ingestion.py`（文档解析 + Chunk 切分）
- `packages/rag-engine/embedding.py`（bge-small-zh-v1.5 封装）
- `packages/rag-engine/retrieval.py`（Qdrant 向量检索 + 元数据过滤）
- `packages/rag-engine/context.py`（Agent system prompt 注入）
- `apps/api/routers/rag.py`（RAG HTTP 路由）
- `scripts/seed_knowledge_base.py`（灌入预置知识）
- `data/knowledge_base/`（合规文档、AML 规则、特征模板）
- `packages/rag-engine/tests/`

**接口契约**：
```
POST /api/v1/rag/documents       — 文档入库
POST /api/v1/rag/search          — 检索（支持 domain 过滤）
GET  /api/v1/rag/stats           — 库统计
```

**完成标志**：
- [ ] Markdown 文档入库后可被检索到
- [ ] Top-10 检索延迟 < 100ms
- [ ] `domain="compliance"` 过滤只返回合规类文档
- [ ] `seed_knowledge_base.py` 灌入 ≥ 50 篇文档
- [ ] Agent 调用时 system prompt 自动拼接 Top-K 结果

---

## TASK-10: Feature Store 集成

**目标**：部署 Feast 并实现 MCP Server，Agent 可自主注册特征和获取在线特征。

**依赖**：TASK-02, TASK-05

**Spec 关联**：F-01, F-02, F-03, F-04, F-05, MCP-S2, MCP-S3

**交付物**：
- `packages/feature-store-adapter/feast_config.py`（Feast 初始化）
- `packages/feature-store-adapter/feature_store.yaml`
- `packages/mcp-servers/feature_store/server.py`（MCPFeatureStoreServer）
- `packages/mcp-servers/data_catalog/server.py`（MCPDataCatalogServer）
- `scripts/load_sample_data.py`（Kaggle 数据加载到 PostgreSQL）
- `packages/feature-store-adapter/tests/`

**工具清单**：
```python
# mcp-feature-store
list_feature_views() -> list[FeatureView]
register_feature_view(definition: dict, dry_run: bool) -> RegisterResult
materialize(view_name: str, start: datetime, end: datetime) -> Job
get_online_features(view_name: str, entity_keys: list) -> dict
compute_feature_stats(view_name: str) -> Stats

# mcp-data-catalog
list_tables(database: str) -> list[Table]
get_schema(table: str) -> Schema
sample_rows(table: str, n: int) -> list[dict]
profile_column(table: str, column: str) -> ColumnProfile
```

**完成标志**：
- [ ] Kaggle 数据（284,807 行）成功加载到 PostgreSQL
- [ ] `feast apply` 成功，registry 初始化
- [ ] 通过 MCP 注册特征视图 → `feast list-feature-views` 可见
- [ ] `materialize` 后 Redis 中有在线特征（查询 < 10ms）
- [ ] `get_schema` 返回正确的列名和类型
- [ ] 所有工具通过 MCP Gateway 端到端调用成功

---

## TASK-11: Web-IDE 前端主体

**目标**：实现 Web-IDE 核心交互界面，用户可与 Agent 对话并查看执行过程。

**依赖**：TASK-08（Agent SSE 流）

**Spec 关联**：U-01, U-02, U-03, U-04, U-05, U-06, U-09

**交付物**：
- `apps/web/app/` — Next.js 14 App Router
- `apps/web/components/agent-chat/` — Agent 对话面板
- `apps/web/components/code-editor/` — Monaco 编辑器
- `apps/web/components/thinking-chain/` — 思考链可视化
- `apps/web/components/file-explorer/` — 文件浏览器
- `apps/web/lib/sse-client.ts` — SSE 流消费
- `apps/web/lib/api.ts` — 后端 API 封装

**完成标志**：
- [ ] 双栏布局：左侧编辑器 + 右侧 Agent Chat，可拖拽调整比例
- [ ] 输入消息后 Agent 响应流式渲染
- [ ] 思考链分块展示（Plan → ToolCall → Observation），可折叠
- [ ] HITL 确认弹窗出现并可点击确认/拒绝
- [ ] 代码块有"插入到编辑器"按钮
- [ ] `Cmd+K` 聚焦聊天输入框
- [ ] `npm run build` 零错误

---

## TASK-12: Skill Library + 长期记忆 + Self-Critique

**目标**：实现 Agent 的学习和自我改进能力。

**依赖**：TASK-08, TASK-09

**Spec 关联**：A-06, A-07, A-08, A-09

**交付物**：
- `packages/agent-core/hermes/memory_long.py`（pgvector 长期记忆）
- `packages/agent-core/skills/library.py`（Skill 检索 + 注册）
- `packages/agent-core/skills/builtin/`（预置 Skills：data_profiling, feature_engineering, model_training）
- `packages/agent-core/hermes/critic.py`（Self-Critique 评估器）
- `packages/agent-core/hermes/distiller.py`（Skill 自动蒸馏）
- `packages/agent-core/tests/`

**完成标志**：
- [ ] 按语义相似度检索 Skill，Top-3 召回相关 Skill
- [ ] 预置 3 个 builtin Skill 可被正确触发
- [ ] Self-Critique 对偏离路径给出 < 0.7 分并建议修正
- [ ] 高分实验（AUC > 0.85）完成后自动蒸馏新 Skill 入库
- [ ] 长期记忆可检索历史相似项目上下文

---

## TASK-13: 端到端集成 + 黄金路径测试

**目标**：全链路打通，验证 MVP 核心命题。

**依赖**：TASK-06 ~ TASK-12 全部完成

**Spec 关联**：E2E-01

**交付物**：
- `tests/e2e/test_fraud_demo.py`（Playwright + pytest）
- `tests/e2e/conftest.py`（数据初始化 + 清理）
- `scripts/bootstrap.sh`（一键初始化全部环境）
- 修复集成过程中发现的所有 bug

**黄金路径**：
```
用户输入"为信用卡交易表构建反欺诈模型"
→ Agent 解析意图
→ RAG 召回合规规则
→ 生成 6 步 Plan，UI 展示
→ 用户确认
→ mcp-data-catalog 获取 Schema
→ mcp-jupyter 执行数据探查
→ mcp-feature-store 注册特征视图
→ mcp-jupyter 训练 LightGBM
→ Self-Critique 评估 AUC
→ Skill Library 蒸馏新 Skill
→ UI 展示最终指标
```

**完成标志**：
- [ ] `docker compose up` → `scripts/bootstrap.sh` → 黄金路径跑通
- [ ] 模型 AUC ≥ 0.90
- [ ] 全程工具调用通过 MCP Gateway（审计日志可验证）
- [ ] 思考链在 UI 完整可视化
- [ ] Skill Library 新增 ≥ 1 条蒸馏 Skill
- [ ] E2E 测试在 CI 中通过（< 15 分钟）
- [ ] 核心模块测试覆盖率 ≥ 70%

---

## 依赖关系图

```
TASK-01 ─┬─→ TASK-02 ─→ TASK-04 ─→ TASK-05 ─┬─→ TASK-06 ─┐
         │                                     │            │
         ├─→ TASK-03                           │            ▼
         │                                     ├─→ TASK-07 → TASK-08 ─┬─→ TASK-11
         │                                     │                       │
         │                          TASK-02 ───┼─→ TASK-09             ├─→ TASK-12
         │                                     │                       │
         │                          TASK-02 ───┴─→ TASK-10             │
         │                                                             │
         └─────────────────────────────────────────────────────────────┴─→ TASK-13
```

## 并行策略

| 阶段 | 可并行任务 | 预计耗时 |
| --- | --- | --- |
| Phase 0 | TASK-01 | 0.5d |
| Phase 1 | TASK-02, TASK-03（并行） | 1d |
| Phase 2 | TASK-04 | 1d |
| Phase 3 | TASK-05 | 2d |
| Phase 4 | TASK-06, TASK-09, TASK-10（并行） | 3d |
| Phase 5 | TASK-07 | 2d |
| Phase 6 | TASK-08 | 3d |
| Phase 7 | TASK-11, TASK-12（并行） | 4d |
| Phase 8 | TASK-13 | 3d |

---

## 执行纪律

1. **开始前**：阅读对应 Spec（`specs/` 目录），确认验收标准
2. **开发中**：遵循 CLAUDE.md 开发纪律，hooks 自动检查
3. **完成后**：
   - 运行 `pytest` 确认测试通过
   - 运行 `ruff check . && mypy packages/` 确认代码质量
   - 更新 `specs/_index.md` 中对应 Spec 状态为 `done`
   - 提交 PR，分支命名 `feat/TASK-XX-简述`
4. **检查点**：TASK-08 完成后做一次集成验证（Agent + MCP + Jupyter 端到端）
