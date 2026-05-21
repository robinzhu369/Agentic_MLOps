"""MCP Feature Store Server — Feature view management and online features."""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger("mcp_servers.feature_store")

_TOOLS = [
    {
        "name": "list_feature_views",
        "description": "List all registered feature views.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "register_feature_view",
        "description": (
            "Register a new feature view definition. "
            "Requires HITL confirmation."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Feature view name",
                },
                "entities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Entity columns",
                },
                "features": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "dtype": {"type": "string"},
                        },
                    },
                    "description": "Feature definitions",
                },
                "source_table": {
                    "type": "string",
                    "description": "Source table name",
                },
                "ttl_hours": {
                    "type": "integer",
                    "description": "Feature TTL in hours",
                    "default": 24,
                },
            },
            "required": ["name", "entities", "features", "source_table"],
        },
    },
    {
        "name": "materialize",
        "description": (
            "Materialize a feature view from offline to online store."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "view_name": {
                    "type": "string",
                    "description": "Feature view to materialize",
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date (ISO 8601)",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date (ISO 8601)",
                },
            },
            "required": ["view_name"],
        },
    },
    {
        "name": "get_online_features",
        "description": (
            "Get online features for given entity keys."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "view_name": {
                    "type": "string",
                    "description": "Feature view name",
                },
                "entity_keys": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Entity key dicts",
                },
            },
            "required": ["view_name", "entity_keys"],
        },
    },
    {
        "name": "compute_feature_stats",
        "description": "Compute statistics for a feature view.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "view_name": {
                    "type": "string",
                    "description": "Feature view name",
                },
            },
            "required": ["view_name"],
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


class FeatureStoreBackend:
    """In-memory feature store backend for MVP.

    Production would integrate with Feast SDK.
    """

    def __init__(self) -> None:
        self._views: dict[str, dict[str, Any]] = {}
        self._materialization_jobs: dict[str, dict[str, Any]] = {}

    def list_feature_views(self) -> list[dict[str, Any]]:
        """List all registered feature views."""
        return [
            {
                "name": name,
                "entities": view["entities"],
                "feature_count": len(view["features"]),
                "source_table": view["source_table"],
                "created_at": view["created_at"],
            }
            for name, view in self._views.items()
        ]

    def register_feature_view(
        self, definition: dict[str, Any]
    ) -> dict[str, Any]:
        """Register a new feature view."""
        name = definition["name"]
        if name in self._views:
            return {"status": "exists", "name": name}

        self._views[name] = {
            **definition,
            "created_at": datetime.now(tz=UTC).isoformat(),
        }
        return {"status": "registered", "name": name}

    def materialize(
        self,
        view_name: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Start materialization job."""
        if view_name not in self._views:
            return {"status": "error", "message": f"View '{view_name}' not found"}

        job_id = f"job_{uuid.uuid4().hex[:8]}"
        self._materialization_jobs[job_id] = {
            "view_name": view_name,
            "status": "completed",
            "start_date": start_date,
            "end_date": end_date,
        }
        return {"status": "completed", "job_id": job_id}

    def get_online_features(
        self,
        view_name: str,
        entity_keys: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Get online features (MVP: returns placeholder)."""
        if view_name not in self._views:
            return {"status": "error", "message": f"View '{view_name}' not found"}

        view = self._views[view_name]
        features = view.get("features", [])

        # Return placeholder feature values
        results = []
        for key in entity_keys[:100]:  # Max 100 entities
            row = {**key}
            for feat in features:
                row[feat["name"]] = 0.0
            results.append(row)

        return {"features": results, "count": len(results)}

    def compute_feature_stats(
        self, view_name: str
    ) -> dict[str, Any]:
        """Compute stats for a feature view."""
        if view_name not in self._views:
            return {"status": "error", "message": f"View '{view_name}' not found"}

        view = self._views[view_name]
        stats = []
        for feat in view.get("features", []):
            stats.append({
                "name": feat["name"],
                "dtype": feat.get("dtype", "float64"),
                "null_rate": 0.0,
                "mean": 0.0,
                "std": 1.0,
            })
        return {"view_name": view_name, "stats": stats}


class MCPFeatureStoreServer:
    """MCP Server for feature store operations."""

    def __init__(
        self, backend: FeatureStoreBackend | None = None
    ) -> None:
        self._backend = backend or FeatureStoreBackend()

    async def list_tools(self) -> dict[str, Any]:
        """Return MCP tool descriptors."""
        return {"tools": _TOOLS}

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Dispatch to the appropriate tool implementation."""
        handlers = {
            "list_feature_views": self._list_feature_views,
            "register_feature_view": self._register_feature_view,
            "materialize": self._materialize,
            "get_online_features": self._get_online_features,
            "compute_feature_stats": self._compute_feature_stats,
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

    async def _list_feature_views(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """List feature views."""
        views = self._backend.list_feature_views()
        return _success_response({"feature_views": views})

    async def _register_feature_view(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Register a feature view."""
        required = ["name", "entities", "features", "source_table"]
        for field in required:
            if field not in arguments:
                return _error_response(f"{field} is required")

        result = self._backend.register_feature_view(arguments)
        return _success_response(result)

    async def _materialize(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Materialize a feature view."""
        view_name = arguments.get("view_name", "")
        if not view_name:
            return _error_response("view_name is required")

        result = self._backend.materialize(
            view_name=view_name,
            start_date=arguments.get("start_date"),
            end_date=arguments.get("end_date"),
        )
        if result.get("status") == "error":
            return _error_response(result["message"])
        return _success_response(result)

    async def _get_online_features(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Get online features."""
        view_name = arguments.get("view_name", "")
        entity_keys = arguments.get("entity_keys", [])

        if not view_name:
            return _error_response("view_name is required")
        if not entity_keys:
            return _error_response("entity_keys is required")

        result = self._backend.get_online_features(
            view_name, entity_keys
        )
        if result.get("status") == "error":
            return _error_response(result["message"])
        return _success_response(result)

    async def _compute_feature_stats(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Compute feature stats."""
        view_name = arguments.get("view_name", "")
        if not view_name:
            return _error_response("view_name is required")

        result = self._backend.compute_feature_stats(view_name)
        if result.get("status") == "error":
            return _error_response(result["message"])
        return _success_response(result)
