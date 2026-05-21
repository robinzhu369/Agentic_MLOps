"""Tests for MCP Data Catalog and Feature Store servers."""
from __future__ import annotations

import json

import pytest
from mcp_servers.data_catalog.server import (
    MCPDataCatalogServer,
)
from mcp_servers.feature_store.server import (
    MCPFeatureStoreServer,
)

# --- Data Catalog Tests ---


@pytest.fixture
def catalog_server() -> MCPDataCatalogServer:
    return MCPDataCatalogServer()


@pytest.mark.asyncio
async def test_catalog_list_tools(
    catalog_server: MCPDataCatalogServer,
) -> None:
    """Test list_tools returns 4 tools."""
    result = await catalog_server.list_tools()
    assert len(result["tools"]) == 4
    names = [t["name"] for t in result["tools"]]
    assert "list_tables" in names
    assert "get_schema" in names
    assert "sample_rows" in names
    assert "profile_column" in names


@pytest.mark.asyncio
async def test_catalog_list_tables(
    catalog_server: MCPDataCatalogServer,
) -> None:
    """Test listing tables returns creditcard."""
    result = await catalog_server.call_tool("list_tables", {})
    assert result["isError"] is False
    data = json.loads(result["content"][0]["text"])
    assert len(data["tables"]) >= 1
    assert data["tables"][0]["table_name"] == "creditcard"


@pytest.mark.asyncio
async def test_catalog_get_schema(
    catalog_server: MCPDataCatalogServer,
) -> None:
    """Test getting schema for creditcard table."""
    result = await catalog_server.call_tool(
        "get_schema", {"table_name": "creditcard"}
    )
    assert result["isError"] is False
    data = json.loads(result["content"][0]["text"])
    assert data["table_name"] == "creditcard"
    assert data["row_count"] == 284807
    col_names = [c["name"] for c in data["columns"]]
    assert "Amount" in col_names
    assert "Class" in col_names
    assert "V1" in col_names


@pytest.mark.asyncio
async def test_catalog_get_schema_not_found(
    catalog_server: MCPDataCatalogServer,
) -> None:
    """Test getting schema for non-existent table."""
    result = await catalog_server.call_tool(
        "get_schema", {"table_name": "nonexistent"}
    )
    assert result["isError"] is True


@pytest.mark.asyncio
async def test_catalog_sample_rows(
    catalog_server: MCPDataCatalogServer,
) -> None:
    """Test sampling rows from a table."""
    result = await catalog_server.call_tool(
        "sample_rows", {"table_name": "creditcard", "n": 5}
    )
    assert result["isError"] is False
    data = json.loads(result["content"][0]["text"])
    assert data["count"] == 5


@pytest.mark.asyncio
async def test_catalog_profile_column(
    catalog_server: MCPDataCatalogServer,
) -> None:
    """Test profiling a column."""
    result = await catalog_server.call_tool(
        "profile_column",
        {"table_name": "creditcard", "column_name": "Amount"},
    )
    assert result["isError"] is False
    data = json.loads(result["content"][0]["text"])
    assert data["column_name"] == "Amount"
    assert data["type"] == "float64"


@pytest.mark.asyncio
async def test_catalog_unknown_tool(
    catalog_server: MCPDataCatalogServer,
) -> None:
    """Test calling unknown tool returns error."""
    result = await catalog_server.call_tool("unknown_tool", {})
    assert result["isError"] is True


# --- Feature Store Tests ---


@pytest.fixture
def fs_server() -> MCPFeatureStoreServer:
    return MCPFeatureStoreServer()


@pytest.mark.asyncio
async def test_fs_list_tools(
    fs_server: MCPFeatureStoreServer,
) -> None:
    """Test list_tools returns 5 tools."""
    result = await fs_server.list_tools()
    assert len(result["tools"]) == 5
    names = [t["name"] for t in result["tools"]]
    assert "list_feature_views" in names
    assert "register_feature_view" in names
    assert "materialize" in names
    assert "get_online_features" in names
    assert "compute_feature_stats" in names


@pytest.mark.asyncio
async def test_fs_register_and_list(
    fs_server: MCPFeatureStoreServer,
) -> None:
    """Test registering and listing feature views."""
    # Register
    reg_result = await fs_server.call_tool(
        "register_feature_view",
        {
            "name": "user_fraud_features",
            "entities": ["user_id"],
            "features": [
                {"name": "txn_count_7d", "dtype": "int64"},
                {"name": "avg_amount_7d", "dtype": "float64"},
            ],
            "source_table": "creditcard",
        },
    )
    assert reg_result["isError"] is False
    data = json.loads(reg_result["content"][0]["text"])
    assert data["status"] == "registered"

    # List
    list_result = await fs_server.call_tool(
        "list_feature_views", {}
    )
    assert list_result["isError"] is False
    data = json.loads(list_result["content"][0]["text"])
    assert len(data["feature_views"]) == 1
    assert data["feature_views"][0]["name"] == "user_fraud_features"


@pytest.mark.asyncio
async def test_fs_materialize(
    fs_server: MCPFeatureStoreServer,
) -> None:
    """Test materializing a feature view."""
    # Register first
    await fs_server.call_tool(
        "register_feature_view",
        {
            "name": "test_view",
            "entities": ["id"],
            "features": [{"name": "f1", "dtype": "float64"}],
            "source_table": "creditcard",
        },
    )

    result = await fs_server.call_tool(
        "materialize", {"view_name": "test_view"}
    )
    assert result["isError"] is False
    data = json.loads(result["content"][0]["text"])
    assert data["status"] == "completed"


@pytest.mark.asyncio
async def test_fs_materialize_not_found(
    fs_server: MCPFeatureStoreServer,
) -> None:
    """Test materializing non-existent view."""
    result = await fs_server.call_tool(
        "materialize", {"view_name": "nonexistent"}
    )
    assert result["isError"] is True


@pytest.mark.asyncio
async def test_fs_get_online_features(
    fs_server: MCPFeatureStoreServer,
) -> None:
    """Test getting online features."""
    # Register first
    await fs_server.call_tool(
        "register_feature_view",
        {
            "name": "online_view",
            "entities": ["user_id"],
            "features": [{"name": "score", "dtype": "float64"}],
            "source_table": "creditcard",
        },
    )

    result = await fs_server.call_tool(
        "get_online_features",
        {
            "view_name": "online_view",
            "entity_keys": [{"user_id": "u1"}, {"user_id": "u2"}],
        },
    )
    assert result["isError"] is False
    data = json.loads(result["content"][0]["text"])
    assert data["count"] == 2


@pytest.mark.asyncio
async def test_fs_compute_stats(
    fs_server: MCPFeatureStoreServer,
) -> None:
    """Test computing feature stats."""
    await fs_server.call_tool(
        "register_feature_view",
        {
            "name": "stats_view",
            "entities": ["id"],
            "features": [
                {"name": "f1", "dtype": "float64"},
                {"name": "f2", "dtype": "int64"},
            ],
            "source_table": "creditcard",
        },
    )

    result = await fs_server.call_tool(
        "compute_feature_stats", {"view_name": "stats_view"}
    )
    assert result["isError"] is False
    data = json.loads(result["content"][0]["text"])
    assert len(data["stats"]) == 2
