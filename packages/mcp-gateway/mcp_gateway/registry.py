"""Capability Registry — manages MCP Server registrations and tool manifest."""
from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from .schemas import CapabilityManifest, MCPServerRegistration, ToolSchema

logger = structlog.get_logger("mcp_gateway.registry")

_CACHE_TTL_SECONDS = 60


class CapabilityRegistry:
    """Manages MCP Server registrations and provides cached tool manifest."""

    def __init__(self) -> None:
        self._servers: dict[str, MCPServerRegistration] = {}
        self._cached_manifest: CapabilityManifest | None = None
        self._cache_time: float = 0

    async def register_server(
        self, registration: MCPServerRegistration
    ) -> None:
        """Register a new MCP Server.

        Args:
            registration: Server registration details.
        """
        self._servers[registration.name] = registration
        self._invalidate_cache()
        logger.info(
            "server_registered",
            name=registration.name,
            base_url=registration.base_url,
        )

    async def deregister_server(self, name: str) -> None:
        """Remove an MCP Server registration.

        Args:
            name: Server name to remove.
        """
        self._servers.pop(name, None)
        self._invalidate_cache()
        logger.info("server_deregistered", name=name)

    def get_servers(self) -> list[MCPServerRegistration]:
        """Get all registered servers."""
        return list(self._servers.values())

    async def get_manifest(self) -> CapabilityManifest:
        """Get the capability manifest (cached with stale-while-revalidate).

        Returns:
            CapabilityManifest with all available tools.
        """
        now = time.time()
        if (
            self._cached_manifest is not None
            and (now - self._cache_time) < _CACHE_TTL_SECONDS
        ):
            return self._cached_manifest

        # Refresh in foreground (MVP simplification)
        manifest = await self._build_manifest()
        self._cached_manifest = manifest
        self._cache_time = now
        return manifest

    def resolve_server(self, tool_name: str) -> str | None:
        """Resolve tool_name to server base_url.

        Args:
            tool_name: Full tool name (e.g., "jupyter.execute_code").

        Returns:
            Server base_url or None if not found.
        """
        server_name = tool_name.split(".")[0] if "." in tool_name else ""
        server = self._servers.get(server_name)
        return server.base_url if server else None

    async def _build_manifest(self) -> CapabilityManifest:
        """Query all registered servers for their tools."""
        all_tools: list[ToolSchema] = []

        async with httpx.AsyncClient(timeout=5.0) as client:
            for name, server in self._servers.items():
                try:
                    tools = await self._fetch_server_tools(
                        client, name, server
                    )
                    all_tools.extend(tools)
                except Exception as e:
                    logger.warning(
                        "server_unreachable",
                        name=name,
                        error=str(e),
                    )

        return CapabilityManifest(
            tools=all_tools,
            generated_at=datetime.now(tz=UTC).isoformat(),
            server_count=len(self._servers),
            tool_count=len(all_tools),
        )

    async def _fetch_server_tools(
        self,
        client: httpx.AsyncClient,
        server_name: str,
        server: MCPServerRegistration,
    ) -> list[ToolSchema]:
        """Fetch tools from a single MCP Server.

        Args:
            client: HTTP client.
            server_name: The server's registered name.
            server: Server registration info.

        Returns:
            List of ToolSchema from this server.
        """
        url = f"{server.base_url}/mcp/list_tools"
        response = await client.post(url)
        response.raise_for_status()
        data: dict[str, Any] = response.json()

        tools: list[ToolSchema] = []
        for tool_data in data.get("tools", []):
            tools.append(
                ToolSchema(
                    tool_name=f"{server_name}.{tool_data['name']}",
                    description=tool_data.get("description", ""),
                    input_schema=tool_data.get("inputSchema", {}),
                    server_name=server_name,
                )
            )
        return tools

    def _invalidate_cache(self) -> None:
        """Invalidate the manifest cache."""
        self._cache_time = 0
