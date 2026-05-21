"""A-04: MCP tool calling client — Agent's interface to MCP Gateway."""
from __future__ import annotations

import time
from typing import Any

import httpx
import structlog
from shared_lib.telemetry import trace_mcp_tool

from .config import AgentCoreSettings, get_agent_settings

logger = structlog.get_logger(__name__)


# --- Exceptions ---


class MCPError(Exception):
    """Base exception for MCP client errors."""

    def __init__(self, message: str, error_code: str = "mcp_error") -> None:
        super().__init__(message)
        self.error_code = error_code


class MCPAuthError(MCPError):
    """JWT invalid or expired and refresh failed."""

    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message, error_code="auth_error")


class MCPToolNotFoundError(MCPError):
    """Tool name not in Capability Manifest."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(
            f"Tool '{tool_name}' not found",
            error_code="tool_not_found",
        )
        self.tool_name = tool_name


class MCPResponseError(MCPError):
    """Response does not conform to MCP Spec format."""

    def __init__(self, message: str = "Invalid MCP response") -> None:
        super().__init__(message, error_code="response_error")


class MCPGatewayError(MCPError):
    """Gateway returned 5xx — caller should retry."""

    def __init__(self, status_code: int, message: str = "") -> None:
        super().__init__(
            f"Gateway error {status_code}: {message}",
            error_code="gateway_error",
        )
        self.status_code = status_code


# --- Token Provider ---


class TokenProvider:
    """Manages JWT token lifecycle with auto-refresh."""

    def __init__(
        self,
        gateway_base_url: str,
        username: str = "admin",
        password: str = "admin",
    ) -> None:
        self._gateway_url = gateway_base_url
        self._username = username
        self._password = password
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at: float = 0.0
        self._client = httpx.AsyncClient(timeout=10.0)

    async def get_token(self) -> str:
        """Return a valid JWT, refreshing if expiry is within 60s."""
        now = time.time()
        if self._access_token and (self._expires_at - now) > 60:
            return self._access_token

        if self._refresh_token:
            try:
                return await self._refresh()
            except (httpx.HTTPError, MCPAuthError):
                pass

        return await self._login()

    async def _login(self) -> str:
        """Obtain new token pair via login."""
        resp = await self._client.post(
            f"{self._gateway_url}/auth/token",
            json={
                "username": self._username,
                "password": self._password,
            },
        )
        if resp.status_code != 200:
            raise MCPAuthError(
                f"Login failed: {resp.status_code}"
            )

        data = resp.json()
        self._access_token = data["access_token"]
        self._refresh_token = data["refresh_token"]
        self._expires_at = time.time() + data.get("expires_in", 3600)
        return self._access_token

    async def _refresh(self) -> str:
        """Refresh access token using refresh token."""
        resp = await self._client.post(
            f"{self._gateway_url}/auth/refresh",
            json={"refresh_token": self._refresh_token},
        )
        if resp.status_code != 200:
            self._refresh_token = None
            raise MCPAuthError("Token refresh failed")

        data = resp.json()
        self._access_token = data["access_token"]
        self._expires_at = time.time() + data.get("expires_in", 3600)
        return self._access_token

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()


# --- MCP Client ---


class MCPClient:
    """Agent-side MCP tool calling client.

    All tool calls route through MCP Gateway. This client handles
    JWT auth injection, request construction, and response parsing.
    No retry logic here — retries are managed by A-03 inner loop.
    """

    def __init__(
        self,
        settings: AgentCoreSettings | None = None,
        token_provider: TokenProvider | None = None,
    ) -> None:
        self._settings = settings or get_agent_settings()
        self._gateway_url = self._settings.mcp_gateway_base_url
        self._token_provider = token_provider or TokenProvider(
            gateway_base_url=self._gateway_url,
        )
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=60.0, write=5.0, pool=5.0),
        )

    @trace_mcp_tool  # type: ignore[untyped-decorator]
    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        session_id: str = "",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Call a tool via MCP Gateway.

        Args:
            tool_name: MCP tool identifier (e.g. "jupyter.execute_code").
            arguments: Arguments to pass to the tool.
            session_id: Current session for audit trail.
            dry_run: If True, validate without executing.

        Returns:
            Dict with 'content' list and metadata per MCP Spec.

        Raises:
            MCPAuthError: JWT invalid or expired and refresh failed.
            MCPToolNotFoundError: tool_name not in Capability Manifest.
            MCPResponseError: Response does not conform to MCP Spec.
            MCPGatewayError: Gateway returned 5xx (caller should retry).
        """
        log = logger.bind(tool_name=tool_name, session_id=session_id)
        start = time.time()

        token = await self._token_provider.get_token()
        headers: dict[str, str] = {
            "Authorization": f"Bearer {token}",
        }
        if dry_run:
            headers["X-Dry-Run"] = "true"

        payload = {
            "tool_name": tool_name,
            "arguments": arguments,
            "session_id": session_id,
            "dry_run": dry_run,
        }

        try:
            resp = await self._client.post(
                f"{self._gateway_url}/mcp/tools/call",
                json=payload,
                headers=headers,
            )
        except httpx.HTTPError as e:
            raise MCPGatewayError(500, str(e)) from e

        duration_ms = int((time.time() - start) * 1000)
        log = log.bind(duration_ms=duration_ms, status_code=resp.status_code)

        if resp.status_code == 401:
            log.warning("mcp_auth_failed")
            raise MCPAuthError()
        if resp.status_code == 404:
            log.warning("mcp_tool_not_found")
            raise MCPToolNotFoundError(tool_name)
        if resp.status_code >= 500:
            log.error("mcp_gateway_error")
            raise MCPGatewayError(resp.status_code, resp.text)
        if resp.status_code >= 400:
            log.warning("mcp_client_error")
            data = resp.json() if resp.content else {}
            raise MCPError(
                data.get("error_message", f"HTTP {resp.status_code}"),
                error_code=data.get("error_code", "client_error"),
            )

        data = resp.json()
        if "content" not in data:
            raise MCPResponseError(
                "Response missing 'content' field"
            )

        log.info("mcp_call_success", is_error=data.get("is_error", False))
        return data  # type: ignore[no-any-return]

    async def list_available_tools(self) -> list[str]:
        """Fetch current tool list from MCP Capability Manifest.

        Returns:
            List of tool_name strings available for planning.
        """
        token = await self._token_provider.get_token()
        resp = await self._client.get(
            f"{self._gateway_url}/mcp/capabilities",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code != 200:
            raise MCPGatewayError(
                resp.status_code, "Failed to fetch capabilities"
            )

        data = resp.json()
        tools = data.get("tools", [])
        return [t["tool_name"] for t in tools]

    async def close(self) -> None:
        """Close HTTP client and token provider."""
        await self._client.aclose()
        await self._token_provider.close()
