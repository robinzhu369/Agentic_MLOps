"""MCP Data Catalog Server — Schema discovery, profiling, and sampling."""
from __future__ import annotations

import json
from typing import Any

import structlog

logger = structlog.get_logger("mcp_servers.data_catalog")

_TOOLS = [
    {
        "name": "list_tables",
        "description": "List all available tables in the data catalog.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "description": "Database name (default: main)",
                    "default": "main",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_schema",
        "description": (
            "Get the schema (columns, types, descriptions) "
            "for a specific table."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Name of the table to inspect",
                },
            },
            "required": ["table_name"],
        },
    },
    {
        "name": "sample_rows",
        "description": "Get a random sample of rows from a table.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Name of the table to sample",
                },
                "n": {
                    "type": "integer",
                    "description": "Number of rows to sample (max 1000)",
                    "default": 10,
                },
            },
            "required": ["table_name"],
        },
    },
    {
        "name": "profile_column",
        "description": (
            "Compute statistical profile for a column: "
            "type, nulls, unique, min, max, mean, percentiles."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Name of the table",
                },
                "column_name": {
                    "type": "string",
                    "description": "Name of the column to profile",
                },
            },
            "required": ["table_name", "column_name"],
        },
    },
]


def _success_response(data: Any) -> dict[str, Any]:
    """Create a successful MCP response."""
    text = json.dumps(data, ensure_ascii=False, default=str)
    return {
        "content": [{"type": "text", "text": text}],
        "isError": False,
    }


def _error_response(message: str) -> dict[str, Any]:
    """Create an error MCP response."""
    return {
        "content": [{"type": "text", "text": f"[ERROR] {message}"}],
        "isError": True,
    }


def _build_creditcard_columns() -> list[dict[str, str]]:
    """Build column definitions for creditcard dataset."""
    cols: list[dict[str, str]] = [
        {
            "name": "Time",
            "type": "float64",
            "description": "Seconds from first txn",
        },
    ]
    for i in range(1, 29):
        cols.append({
            "name": f"V{i}",
            "type": "float64",
            "description": f"PCA component {i}",
        })
    cols.append({
        "name": "Amount",
        "type": "float64",
        "description": "Transaction amount",
    })
    cols.append({
        "name": "Class",
        "type": "int64",
        "description": "Fraud label (0=normal, 1=fraud)",
    })
    return cols


class DataCatalogBackend:
    """Backend for data catalog operations.

    MVP uses in-memory catalog with pre-registered tables.
    Production would use SQLAlchemy async connections.
    """

    def __init__(self) -> None:
        # Pre-registered tables for MVP (Kaggle credit card dataset)
        self._tables: dict[str, dict[str, Any]] = {
            "creditcard": {
                "database": "main",
                "row_count": 284807,
                "columns": _build_creditcard_columns(),
            },
        }

    def list_tables(self, database: str = "main") -> list[dict[str, Any]]:
        """List tables in the catalog."""
        return [
            {
                "table_name": name,
                "database": info["database"],
                "row_count": info["row_count"],
                "column_count": len(info["columns"]),
            }
            for name, info in self._tables.items()
            if info["database"] == database
        ]

    def get_schema(self, table_name: str) -> dict[str, Any] | None:
        """Get schema for a table."""
        info = self._tables.get(table_name)
        if info is None:
            return None
        return {
            "table_name": table_name,
            "database": info["database"],
            "row_count": info["row_count"],
            "columns": info["columns"],
        }

    def sample_rows(
        self, table_name: str, n: int = 10
    ) -> list[dict[str, Any]] | None:
        """Get sample rows (MVP: returns synthetic sample)."""
        if table_name not in self._tables:
            return None
        # MVP: return placeholder sample
        columns = self._tables[table_name]["columns"]
        sample = []
        for i in range(min(n, 5)):
            row = {}
            for col in columns:
                if col["type"] == "float64":
                    row[col["name"]] = round(0.1 * (i + 1), 4)
                elif col["type"] == "int64":
                    row[col["name"]] = 0
            sample.append(row)
        return sample

    def profile_column(
        self, table_name: str, column_name: str
    ) -> dict[str, Any] | None:
        """Profile a column (MVP: returns static stats)."""
        info = self._tables.get(table_name)
        if info is None:
            return None
        col = next(
            (c for c in info["columns"] if c["name"] == column_name),
            None,
        )
        if col is None:
            return None
        return {
            "table_name": table_name,
            "column_name": column_name,
            "type": col["type"],
            "null_count": 0,
            "null_rate": 0.0,
            "unique_count": info["row_count"],
            "description": col["description"],
        }


class MCPDataCatalogServer:
    """MCP Server for data catalog operations."""

    def __init__(
        self, backend: DataCatalogBackend | None = None
    ) -> None:
        self._backend = backend or DataCatalogBackend()

    async def list_tools(self) -> dict[str, Any]:
        """Return MCP tool descriptors."""
        return {"tools": _TOOLS}

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Dispatch to the appropriate tool implementation."""
        handlers = {
            "list_tables": self._list_tables,
            "get_schema": self._get_schema,
            "sample_rows": self._sample_rows,
            "profile_column": self._profile_column,
        }

        handler = handlers.get(name)
        if handler is None:
            return _error_response(
                f"Unknown tool: {name}. "
                f"Available: {list(handlers.keys())}"
            )

        try:
            return await handler(arguments)
        except Exception as e:
            logger.error(
                "tool_error", tool=name, error=str(e)
            )
            return _error_response(f"Internal error in {name}")

    async def _list_tables(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """List available tables."""
        database = arguments.get("database", "main")
        tables = self._backend.list_tables(database)
        return _success_response({"tables": tables})

    async def _get_schema(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Get table schema."""
        table_name = arguments.get("table_name", "")
        if not table_name:
            return _error_response("table_name is required")

        schema = self._backend.get_schema(table_name)
        if schema is None:
            return _error_response(
                f"Table '{table_name}' not found"
            )
        return _success_response(schema)

    async def _sample_rows(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Sample rows from a table."""
        table_name = arguments.get("table_name", "")
        n = min(arguments.get("n", 10), 1000)

        if not table_name:
            return _error_response("table_name is required")

        rows = self._backend.sample_rows(table_name, n)
        if rows is None:
            return _error_response(
                f"Table '{table_name}' not found"
            )
        return _success_response({"rows": rows, "count": len(rows)})

    async def _profile_column(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Profile a column."""
        table_name = arguments.get("table_name", "")
        column_name = arguments.get("column_name", "")

        if not table_name or not column_name:
            return _error_response(
                "table_name and column_name are required"
            )

        profile = self._backend.profile_column(
            table_name, column_name
        )
        if profile is None:
            return _error_response(
                f"Column '{column_name}' not found "
                f"in table '{table_name}'"
            )
        return _success_response(profile)
