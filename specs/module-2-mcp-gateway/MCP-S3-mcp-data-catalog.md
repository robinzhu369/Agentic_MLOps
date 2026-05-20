---
id: "MCP-S3"
module: "mcp-gateway"
title: "mcp-data-catalog Server"
priority: P0
status: draft
owner: ""
dependencies: ["G-01", "G-04"]
milestone: "W5"
---

# [MCP-S3] mcp-data-catalog Server

## 概述

封装数据目录操作为 MCP 标准工具，提供数据表发现、Schema 查询、数据采样和列统计分析能力。mcp-data-catalog 使 Agent 能够在规划阶段自主探索可用数据资产，是数据驱动 MLOps 工作流的数据理解层。

## 验收标准

- [ ] AC-1: `list_tools()` 返回 4 个工具的完整 MCP Spec 描述
- [ ] AC-2: `list_tables` 返回数据目录中所有可访问表的名称、数据库、描述和行数估算
- [ ] AC-3: `get_schema` 返回指定表的完整列定义，包含列名、数据类型、可空性和注释
- [ ] AC-4: `sample_rows` 返回指定表的随机样本行（默认 10 行），以 JSON 数组格式返回，自动对 PII 列应用脱敏
- [ ] AC-5: `profile_column` 返回指定列的统计分布信息，包含基数、缺失率、Top-10 值频率（分类列）或分位数（数值列）
- [ ] AC-6: 所有工具调用遵循调用方的 RBAC 权限，scientist 角色只能访问已授权的数据库

## 接口定义

```python
from typing import Any


class MCPDataCatalogServer:
    async def list_tools(self) -> list[dict]:
        """Return MCP tool descriptors for all 4 tools."""
        ...

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> dict:
        """
        Dispatch to tool implementation.

        Valid names: list_tables, get_schema, sample_rows, profile_column
        """
        ...


# Tool signatures:

async def list_tables(
    database: str | None = None,
    search: str | None = None,           # Optional name filter (substring match)
) -> dict:
    """
    List available tables in the data catalog.

    Returns:
        {"content": [{"type": "text", "text": JSON array of table summaries}]}

    Table summary format:
        {"table_name": str, "database": str, "description": str,
         "estimated_rows": int, "last_updated": str}
    """
    ...


async def get_schema(
    table_name: str,
    database: str = "default",
) -> dict:
    """
    Get column definitions for a table.

    Returns:
        {"content": [{"type": "text", "text": JSON array of column definitions}]}

    Column definition format:
        {"column_name": str, "data_type": str, "nullable": bool,
         "comment": str | None, "is_pii": bool}
    """
    ...


async def sample_rows(
    table_name: str,
    database: str = "default",
    n_rows: int = 10,
    columns: list[str] | None = None,   # None = all columns
) -> dict:
    """
    Return random sample rows from a table.

    PII columns (is_pii=True in schema) are automatically masked.
    n_rows maximum: 100.

    Returns:
        {"content": [{"type": "text", "text": JSON array of row dicts}]}
    """
    ...


async def profile_column(
    table_name: str,
    column_name: str,
    database: str = "default",
    sample_size: int = 100000,
) -> dict:
    """
    Compute statistical profile for a column.

    Returns:
        {"content": [{"type": "text", "text": JSON with column statistics}]}

    Statistics format:
        {
            "column_name": str,
            "data_type": str,
            "null_rate": float,
            "cardinality": int,
            # For categorical columns:
            "top_values": [{"value": str, "count": int, "frequency": float}],
            # For numeric columns:
            "min": float, "max": float, "mean": float, "std": float,
            "percentiles": {"p25": float, "p50": float, "p75": float, "p95": float}
        }
    """
    ...
```

## 技术约束

- 底层使用 SQLAlchemy（异步）连接数据仓库（支持 PostgreSQL、Hive、Trino），连接配置通过环境变量注入
- `sample_rows` 使用 `ORDER BY RANDOM() LIMIT n` 或等效语法，不加载全表数据
- `profile_column` 对大表使用 TABLESAMPLE 或子查询限制扫描量，sample_size 参数控制采样行数
- PII 列标记来自数据目录元数据（`is_pii` 字段），`sample_rows` 自动对 PII 列调用 G-08 PIIMasker
- `list_tables` 结果按 RBAC 过滤，scientist 角色只返回其有权访问的数据库中的表

## 测试策略

- 单元测试：mock SQLAlchemy 连接，验证 list_tools() Schema；测试 PII 列自动脱敏逻辑；测试 n_rows 超过 100 时的截断；测试错误响应格式
- 集成测试：连接测试数据库，验证 get_schema 返回正确列定义；测试 profile_column 统计计算准确性
- E2E：Agent 在规划阶段调用 `mcp_data_catalog.list_tables` 和 `get_schema`，验证数据探索结果用于后续规划

## 依赖关系

- 被阻塞：[G-01, G-04]
- 阻塞：[]

## 参考

- MVP_SPEC.md Section 3.2
- Anthropic MCP Specification
