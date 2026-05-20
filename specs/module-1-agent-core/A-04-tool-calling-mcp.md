---
id: "A-04"
module: "agent-core"
title: "工具调用（通过 MCP）"
priority: P0
status: draft
owner: ""
dependencies: ["G-01", "G-04"]
milestone: "W3"
---

# [A-04] 工具调用（通过 MCP）

## 概述

封装 Agent 侧的 MCP 工具调用客户端，所有工具调用必须经由 MCP Gateway 路由，禁止 Agent Core 直接访问底层服务。该模块负责请求构造、JWT 认证头注入、响应解析和错误标准化，是 Agent 与外部能力之间的唯一通信层。

## 验收标准

- [ ] AC-1: 调用任意 MCP 工具时，请求必须携带有效 JWT Bearer Token，Token 过期前 60 秒自动刷新
- [ ] AC-2: 工具调用响应符合 MCP Spec 格式（包含 content 字段），非 MCP 格式响应触发 MCPResponseError
- [ ] AC-3: HTTP 4xx 错误不重试，直接返回错误给内循环；HTTP 5xx 错误由内循环（A-03）处理重试，本层不重试
- [ ] AC-4: 支持 dry_run 模式（G-07），当 `DRY_RUN=true` 时，调用 MCP Gateway 的 dry_run 端点，返回模拟结果而不执行实际操作
- [ ] AC-5: 每次工具调用记录 trace_id、tool_name、duration_ms 到结构化日志

## 接口定义

```python
from typing import Any
from pydantic import BaseModel


class MCPToolRequest(BaseModel):
    tool_name: str                        # e.g. "jupyter.execute_code"
    arguments: dict[str, Any]
    session_id: str
    dry_run: bool = False


class MCPToolResponse(BaseModel):
    tool_name: str
    content: list[dict]                   # MCP Spec content array
    is_error: bool = False
    error_code: str | None = None
    error_message: str | None = None
    duration_ms: int | None = None


class MCPClient:
    def __init__(self, gateway_base_url: str, jwt_token_provider: "TokenProvider"):
        ...

    async def call_tool(
        self,
        request: MCPToolRequest,
    ) -> MCPToolResponse:
        """
        Call a tool via MCP Gateway.

        Injects JWT auth header, routes to correct MCP Server via G-04,
        and parses the MCP Spec response.

        Args:
            request: Tool name, arguments, session context, and dry_run flag.

        Returns:
            MCPToolResponse with content array per MCP Spec.

        Raises:
            MCPAuthError: JWT invalid or expired and refresh failed.
            MCPToolNotFoundError: tool_name not in Capability Manifest.
            MCPResponseError: Response does not conform to MCP Spec format.
            MCPGatewayError: Gateway returned 5xx (caller should retry).
        """
        ...

    async def list_available_tools(self) -> list[str]:
        """
        Fetch current tool list from MCP Capability Manifest (G-01).
        Used by A-02 Planner to validate tool_name in plans.
        """
        ...


class TokenProvider:
    async def get_token(self) -> str:
        """Return a valid JWT, refreshing if expiry is within 60 seconds."""
        ...
```

## 技术约束

- 使用 `httpx.AsyncClient` 进行异步 HTTP 调用，连接池复用，超时配置：connect=5s, read=60s
- JWT Token 缓存于内存，使用 `python-jose` 解析过期时间，不依赖外部时钟
- 禁止在此层实现重试逻辑，重试由 A-03 内循环统一管理
- dry_run 标志通过请求头 `X-Dry-Run: true` 传递给 MCP Gateway
- 所有异常必须继承自 `MCPError` 基类，包含 `error_code` 字段

## 测试策略

- 单元测试：mock httpx 响应，验证 JWT 注入逻辑；测试 Token 自动刷新（模拟 Token 即将过期）；测试各类错误码映射到正确异常类型
- 集成测试：与真实 MCP Gateway（G-04）联调，验证完整调用链路；测试 dry_run 模式返回模拟结果
- E2E：在完整 Agent 执行流程中验证工具调用结果正确出现在 Observation 中

## 依赖关系

- 被阻塞：[G-01, G-04]
- 阻塞：[A-03]

## 参考

- MVP_SPEC.md Section 3.1
- Anthropic MCP Specification
