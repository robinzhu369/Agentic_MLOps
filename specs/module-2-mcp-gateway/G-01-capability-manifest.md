---
id: "G-01"
module: "mcp-gateway"
title: "工具能力发现（Capability Manifest）"
priority: P0
status: draft
owner: ""
dependencies: []
milestone: "W2"
---

# [G-01] 工具能力发现（Capability Manifest）

## 概述

MCP Gateway 聚合所有已注册 MCP Server 的工具列表，生成统一的 Capability Manifest，供 Agent Core（A-02、A-04）查询可用工具。Manifest 定期刷新并缓存，确保 Agent 规划时使用的工具列表与实际可用能力保持一致。

## 验收标准

- [ ] AC-1: `GET /mcp/capabilities` 在 200ms 内返回所有在线 MCP Server 的工具列表，包含 tool_name、description、input_schema 字段
- [ ] AC-2: Manifest 缓存 TTL 为 60 秒，过期后异步刷新，刷新期间返回旧缓存（stale-while-revalidate）
- [ ] AC-3: 某个 MCP Server 不可达时，该 Server 的工具从 Manifest 中移除，其他 Server 工具不受影响，并记录警告日志
- [ ] AC-4: 每个工具的 tool_name 格式为 `{server_name}.{tool_name}`（如 `jupyter.execute_code`），全局唯一
- [ ] AC-5: 支持 MCP Server 动态注册（`POST /mcp/servers`）和注销（`DELETE /mcp/servers/{name}`），注册后 60 秒内出现在 Manifest 中

## 接口定义

```python
from pydantic import BaseModel
from typing import Any


class ToolSchema(BaseModel):
    tool_name: str                        # "{server}.{tool}", e.g. "jupyter.execute_code"
    description: str
    input_schema: dict[str, Any]         # JSON Schema for tool arguments
    server_name: str
    is_available: bool = True


class CapabilityManifest(BaseModel):
    tools: list[ToolSchema]
    generated_at: str                    # ISO 8601
    server_count: int
    tool_count: int


class MCPServerRegistration(BaseModel):
    name: str                            # Unique server identifier
    base_url: str                        # e.g. "http://mcp-jupyter:8001"
    health_check_path: str = "/health"


# REST API
# GET  /mcp/capabilities          -> CapabilityManifest
# POST /mcp/servers               -> {"name": str, "status": "registered"}
# DELETE /mcp/servers/{name}      -> 204 No Content
# GET  /mcp/servers               -> list[MCPServerRegistration]


class CapabilityRegistry:
    async def get_manifest(self) -> CapabilityManifest:
        """
        Return cached Capability Manifest.
        Triggers async refresh if cache is stale (> 60s).
        """
        ...

    async def refresh(self) -> CapabilityManifest:
        """
        Poll all registered MCP Servers via list_tools().
        Removes unreachable servers from manifest (does not deregister).
        """
        ...

    async def register_server(
        self,
        registration: MCPServerRegistration,
    ) -> None:
        """Register a new MCP Server and trigger immediate manifest refresh."""
        ...

    async def deregister_server(self, name: str) -> None:
        """Remove a server from registry and update manifest."""
        ...
```

## 技术约束

- Manifest 缓存存储于 Redis，Key：`mcp:capability_manifest`，TTL 60 秒
- 刷新时并发调用所有 MCP Server 的 `list_tools()`，单个 Server 超时 5 秒
- tool_name 命名规范强制校验：必须匹配 `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`
- MCP Server 注册信息持久化到 PostgreSQL，服务重启后自动恢复
- 健康检查每 30 秒执行一次，连续 3 次失败才从 Manifest 移除（避免抖动）

## 测试策略

- 单元测试：mock MCP Server HTTP 响应，验证 tool_name 格式化逻辑；测试单个 Server 不可达时其他工具正常返回；测试缓存 stale-while-revalidate 行为
- 集成测试：启动真实 mcp-jupyter Server，验证工具出现在 Manifest 中；测试动态注册/注销
- E2E：Agent 规划时调用 `list_available_tools()`，验证返回的工具名与 Manifest 一致

## 依赖关系

- 被阻塞：[]
- 阻塞：[G-04, A-02, A-04, MCP-S1, MCP-S2, MCP-S3]

## 参考

- MVP_SPEC.md Section 3.2
- Anthropic MCP Specification
