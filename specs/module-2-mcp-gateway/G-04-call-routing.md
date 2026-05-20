---
id: "G-04"
module: "mcp-gateway"
title: "调用路由"
priority: P0
status: draft
owner: ""
dependencies: ["G-01"]
milestone: "W2"
---

# [G-04] 调用路由

## 概述

MCP Gateway 的核心路由层，接收来自 Agent Core 的工具调用请求，根据 tool_name 前缀将请求路由到对应的 MCP Server，并将响应标准化后返回。路由层是 Gateway 的流量枢纽，所有工具调用必须经过此层，确保认证、RBAC、审计和熔断等横切关注点统一执行。

## 验收标准

- [ ] AC-1: 根据 `tool_name` 的 server 前缀（如 `jupyter.`）正确路由到对应 MCP Server，路由延迟（不含工具执行时间）≤ 10ms
- [ ] AC-2: 目标 MCP Server 不存在或不可达时，返回 HTTP 502，响应体符合 MCP 错误格式
- [ ] AC-3: 路由前依次执行：JWT 验证（G-02）→ RBAC 检查（G-03）→ PII 脱敏（G-08）→ 审计日志写入（G-05）→ 熔断检查（G-06）
- [ ] AC-4: 工具调用响应经过 PII 脱敏（G-08）后再返回给调用方
- [ ] AC-5: 每次路由请求生成唯一 `trace_id`（UUID v4），贯穿整个调用链，包含在响应头 `X-Trace-ID` 中

## 接口定义

```python
from pydantic import BaseModel
from typing import Any


class ToolCallRequest(BaseModel):
    tool_name: str                       # "{server}.{tool}"
    arguments: dict[str, Any]
    session_id: str
    dry_run: bool = False


class ToolCallResponse(BaseModel):
    tool_name: str
    content: list[dict]                  # MCP Spec content array
    is_error: bool = False
    error_code: str | None = None
    error_message: str | None = None
    trace_id: str
    duration_ms: int


# REST API
# POST /mcp/tools/call  (body: ToolCallRequest) -> ToolCallResponse
# Headers:
#   Authorization: Bearer <jwt>
#   X-Trace-ID: <uuid>  (response header)


class ToolRouter:
    def __init__(
        self,
        capability_registry: "CapabilityRegistry",
        mcp_server_clients: dict[str, "MCPServerClient"],
    ):
        ...

    async def route(
        self,
        request: ToolCallRequest,
        user_id: str,
        user_role: str,
    ) -> ToolCallResponse:
        """
        Route a tool call to the appropriate MCP Server.

        Middleware execution order:
        1. Validate tool_name exists in Capability Manifest (G-01)
        2. RBAC check (G-03)
        3. PII masking on arguments (G-08)
        4. Circuit breaker check (G-06)
        5. Forward to MCP Server
        6. PII masking on response (G-08)
        7. Write audit log (G-05)

        Returns:
            Standardized ToolCallResponse per MCP Spec.

        Raises:
            ToolNotFoundError: tool_name not in Capability Manifest.
            PermissionDeniedError: RBAC check failed.
            CircuitOpenError: Circuit breaker is open for this session.
            MCPServerError: Upstream MCP Server returned error.
        """
        ...

    def _resolve_server(self, tool_name: str) -> str:
        """Extract server name from tool_name prefix."""
        ...
```

## 技术约束

- 使用 FastAPI 中间件链实现横切关注点，每个关注点为独立中间件，顺序固定
- 向 MCP Server 转发请求使用 `httpx.AsyncClient`，超时配置：connect=3s, read=120s（工具执行可能耗时较长）
- trace_id 在请求入口生成，通过 Python `contextvars.ContextVar` 在整个请求生命周期传递
- dry_run 请求通过请求头 `X-Dry-Run: true` 转发给 MCP Server，不修改路由逻辑
- 路由表从 Capability Manifest 动态构建，Manifest 刷新时自动更新路由表

## 测试策略

- 单元测试：mock MCP Server 响应，验证 server 前缀解析逻辑；测试中间件执行顺序（通过 mock 验证调用顺序）；测试 tool_name 不存在时的 502 响应
- 集成测试：与 G-01、G-02、G-03 联调，验证完整中间件链；测试 trace_id 在响应头中正确返回
- E2E：Agent Core 通过 A-04 发起工具调用，验证请求正确路由到目标 MCP Server 并返回结果

## 依赖关系

- 被阻塞：[G-01]
- 阻塞：[G-05, G-06, G-07, G-08, A-04, MCP-S1, MCP-S2, MCP-S3]

## 参考

- MVP_SPEC.md Section 3.2
- Anthropic MCP Specification
