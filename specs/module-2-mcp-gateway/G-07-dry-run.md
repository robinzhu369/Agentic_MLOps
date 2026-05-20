---
id: "G-07"
module: "mcp-gateway"
title: "dry_run 支持"
priority: P1
status: draft
owner: ""
dependencies: ["G-04"]
milestone: "W5"
---

# [G-07] dry_run 支持

## 概述

为所有工具调用提供 dry_run 模式，在不执行实际操作的情况下验证调用参数合法性并返回模拟结果。dry_run 使 Agent 在执行高风险操作前可以预演，也用于测试环境中的集成验证，避免对真实数据和系统产生副作用。

## 验收标准

- [ ] AC-1: 请求携带 `X-Dry-Run: true` 头或请求体 `dry_run=true` 时，工具调用不执行实际操作，返回模拟响应
- [ ] AC-2: dry_run 响应必须符合 MCP Spec 格式，content 数组中包含 `{"type": "text", "text": "[DRY RUN] ..."}`  前缀标识
- [ ] AC-3: dry_run 调用仍执行 JWT 验证、RBAC 检查和参数 Schema 验证，但跳过实际工具执行和熔断计数
- [ ] AC-4: dry_run 调用记录到审计日志，status 字段为 `dry_run`，不计入熔断失败计数
- [ ] AC-5: 每个 MCP Server 可提供工具专属的 dry_run 响应模板，未提供时使用通用模板

## 接口定义

```python
from pydantic import BaseModel
from typing import Any


class DryRunResponse(BaseModel):
    tool_name: str
    content: list[dict]                  # MCP Spec content, prefixed with "[DRY RUN]"
    is_error: bool = False
    dry_run: bool = True
    validation_passed: bool
    validation_errors: list[str] = []   # Schema validation errors if any


# Tool-specific dry_run templates (optional, per MCP Server):
# Each MCP Server can implement dry_run_tool() alongside call_tool()
# If not implemented, gateway uses generic template


class DryRunHandler:
    async def handle(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        mcp_server_client: "MCPServerClient",
    ) -> DryRunResponse:
        """
        Execute dry_run for a tool call.

        Steps:
        1. Validate arguments against tool's input_schema (from G-01).
        2. If MCP Server implements dry_run_tool(), delegate to it.
        3. Otherwise, return generic dry_run response.

        Args:
            tool_name: Full tool name including server prefix.
            arguments: Tool arguments to validate.
            mcp_server_client: Client for the target MCP Server.

        Returns:
            DryRunResponse with validation results and mock output.
        """
        ...

    def _validate_arguments(
        self,
        arguments: dict[str, Any],
        input_schema: dict,
    ) -> list[str]:
        """
        Validate arguments against JSON Schema.
        Returns list of validation error messages (empty if valid).
        """
        ...

    def _generic_response(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> list[dict]:
        """
        Generate generic dry_run content when server has no template.
        Format: [{"type": "text", "text": "[DRY RUN] Would call {tool_name} with {n} arguments"}]
        """
        ...
```

## 技术约束

- dry_run 标志优先级：请求体 `dry_run` 字段 > 请求头 `X-Dry-Run`
- 参数 Schema 验证使用 `jsonschema` 库，Schema 来自 G-01 Capability Manifest
- dry_run 调用不转发到 MCP Server 的 `call_tool()`，只在 Gateway 层处理
- 若 MCP Server 实现了 `dry_run_tool()` 方法，Gateway 可选择转发（需 MCP Server 明确声明支持）
- dry_run 模式下，PII 脱敏（G-08）仍然执行

## 测试策略

- 单元测试：验证 dry_run 响应包含 `[DRY RUN]` 前缀；测试参数 Schema 验证错误正确返回；测试 dry_run 不触发熔断计数；测试审计日志 status 为 `dry_run`
- 集成测试：与 G-04 联调，验证 dry_run 请求不到达 MCP Server；测试参数验证失败时的响应格式
- E2E：Agent 在 requires_confirm 步骤前执行 dry_run 预演，验证返回模拟结果

## 依赖关系

- 被阻塞：[G-04]
- 阻塞：[]

## 参考

- MVP_SPEC.md Section 3.2
