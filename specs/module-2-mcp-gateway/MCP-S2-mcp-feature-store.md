---
id: "MCP-S2"
module: "mcp-gateway"
title: "mcp-feature-store Server"
priority: P0
status: draft
owner: ""
dependencies: ["G-01", "G-04", "F-01"]
milestone: "W5"
---

# [MCP-S2] mcp-feature-store Server

## 概述

封装 Feature Store（Module 5）操作为 MCP 标准工具，提供特征视图管理、特征物化和在线特征获取能力。mcp-feature-store 使 Agent 能够通过自然语言指令完成特征工程工作流，是 MLOps 平台特征管理能力的 MCP 接入层。

## 验收标准

- [ ] AC-1: `list_tools()` 返回 5 个工具的完整 MCP Spec 描述
- [ ] AC-2: `list_feature_views` 返回所有已注册特征视图的名称、实体、特征列表和数据源信息
- [ ] AC-3: `register_feature_view` 接受特征视图定义（YAML 或 JSON），注册到 Feature Store 并返回确认
- [ ] AC-4: `materialize` 触发指定特征视图的物化任务，返回任务 ID，支持异步查询任务状态
- [ ] AC-5: `get_online_features` 根据实体键批量获取在线特征，延迟 ≤ 100ms（P99，批量 ≤ 100 个实体）
- [ ] AC-6: `compute_feature_stats` 计算指定特征的统计信息（均值、方差、分位数、缺失率），返回 JSON 格式统计报告

## 接口定义

```python
from typing import Any


class MCPFeatureStoreServer:
    async def list_tools(self) -> list[dict]:
        """Return MCP tool descriptors for all 5 tools."""
        ...

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> dict:
        """
        Dispatch to tool implementation.

        Valid names: list_feature_views, register_feature_view,
                     materialize, get_online_features, compute_feature_stats
        """
        ...


# Tool signatures:

async def list_feature_views(
    project: str | None = None,
) -> dict:
    """
    List all registered feature views.

    Returns:
        {"content": [{"type": "text", "text": JSON array of feature view summaries}]}
    """
    ...


async def register_feature_view(
    definition: dict,                    # Feature view definition (Feast-compatible)
    project: str = "default",
) -> dict:
    """
    Register a new feature view in the Feature Store.

    Returns:
        {"content": [{"type": "text", "text": JSON with feature_view_name, status}]}
    """
    ...


async def materialize(
    feature_view_name: str,
    start_date: str,                     # ISO 8601 date
    end_date: str,                       # ISO 8601 date
    project: str = "default",
) -> dict:
    """
    Trigger feature materialization for a date range.

    Returns:
        {"content": [{"type": "text", "text": JSON with job_id, status, estimated_duration_s}]}
    """
    ...


async def get_online_features(
    feature_view_name: str,
    entity_keys: list[dict],             # e.g. [{"user_id": "u1"}, {"user_id": "u2"}]
    feature_names: list[str] | None = None,  # None = all features
) -> dict:
    """
    Fetch online features for entity keys.

    Returns:
        {"content": [{"type": "text", "text": JSON with features per entity}]}
    """
    ...


async def compute_feature_stats(
    feature_view_name: str,
    feature_names: list[str],
    sample_size: int = 10000,
) -> dict:
    """
    Compute statistical profile for specified features.

    Returns:
        {"content": [{"type": "text", "text": JSON with stats per feature}]}
    """
    ...
```

## 技术约束

- 底层调用 Module 5 Feature Store 的 Python SDK（Feast 兼容接口），不直接访问数据库
- `materialize` 为异步操作，返回 job_id 后可通过 Feature Store API 查询状态
- `get_online_features` 使用 Feature Store 的 Redis 在线存储，批量大小限制 100 个实体
- 特征视图定义验证使用 Feature Store SDK 的 Schema 验证，不在 MCP Server 层重复实现
- 所有错误响应符合 MCP Spec 格式，Feature Store SDK 异常转换为 MCP 错误响应

## 测试策略

- 单元测试：mock Feature Store SDK，验证 list_tools() Schema；测试各工具参数验证；测试错误响应格式
- 集成测试：连接真实 Feature Store（Module 5），验证特征视图注册和在线特征获取；测试物化任务触发
- E2E：通过 MCP Gateway 调用 `mcp_feature_store.get_online_features`，验证特征数据正确返回给 Agent

## 依赖关系

- 被阻塞：[G-01, G-04, F-01]
- 阻塞：[]

## 参考

- MVP_SPEC.md Section 3.2
- Anthropic MCP Specification
