"""Tool Router — routes tool calls to the correct MCP Server."""
from __future__ import annotations

import time
import uuid
from typing import Any

import httpx
import structlog

from .audit import AuditLogger
from .pii import PIIMasker
from .rbac import PermissionDeniedError, RBACService
from .registry import CapabilityRegistry
from .schemas import AuditStatus, ToolCallRequest, ToolCallResponse

logger = structlog.get_logger("mcp_gateway.router")


class RoutingError(Exception):
    """Raised when tool cannot be routed."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ToolRouter:
    """Routes tool calls through the middleware chain to MCP Servers."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        rbac: RBACService,
        masker: PIIMasker,
        audit: AuditLogger,
    ) -> None:
        self._registry = registry
        self._rbac = rbac
        self._masker = masker
        self._audit = audit

    async def route(
        self,
        request: ToolCallRequest,
        user_id: str,
        user_role: str,
    ) -> ToolCallResponse:
        """Route a tool call through the full middleware chain.

        Execution order:
        1. RBAC check
        2. PII mask request arguments
        3. Resolve server + forward call
        4. PII mask response
        5. Audit log

        Args:
            request: The tool call request.
            user_id: Authenticated user ID.
            user_role: User's role.

        Returns:
            ToolCallResponse with masked content.

        Raises:
            PermissionDeniedError: If RBAC check fails.
            RoutingError: If server is unreachable.
        """
        trace_id = str(uuid.uuid4())
        start_time = time.time()

        # 1. RBAC check
        try:
            self._rbac.check_permission(request.tool_name, user_role)
        except PermissionDeniedError:
            await self._audit.log(
                self._audit.create_entry(
                    trace_id=trace_id,
                    user_id=user_id,
                    session_id=request.session_id,
                    tool_name=request.tool_name,
                    arguments=request.arguments,
                    status=AuditStatus.PERMISSION_DENIED,
                )
            )
            raise

        # 2. PII mask request arguments
        masked_args, _ = self._masker.mask_dict(request.arguments)

        # 3. Dry run — validate only, don't execute
        if request.dry_run:
            duration_ms = int((time.time() - start_time) * 1000)
            await self._audit.log(
                self._audit.create_entry(
                    trace_id=trace_id,
                    user_id=user_id,
                    session_id=request.session_id,
                    tool_name=request.tool_name,
                    arguments=request.arguments,
                    status=AuditStatus.DRY_RUN,
                    duration_ms=duration_ms,
                    dry_run=True,
                )
            )
            return ToolCallResponse(
                tool_name=request.tool_name,
                content=[{"type": "text", "text": "dry_run: validated"}],
                trace_id=trace_id,
                duration_ms=duration_ms,
            )

        # 4. Resolve server and forward
        base_url = self._registry.resolve_server(request.tool_name)
        if base_url is None:
            raise RoutingError(
                f"No server registered for tool: {request.tool_name}"
            )

        try:
            response = await self._forward_to_server(
                base_url, request.tool_name, masked_args
            )
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            await self._audit.log(
                self._audit.create_entry(
                    trace_id=trace_id,
                    user_id=user_id,
                    session_id=request.session_id,
                    tool_name=request.tool_name,
                    arguments=request.arguments,
                    status=AuditStatus.FAILED,
                    duration_ms=duration_ms,
                    error_code="server_error",
                    error_message=str(e),
                )
            )
            raise RoutingError(
                f"MCP Server unreachable: {e}", status_code=502
            ) from e

        # 5. Build response
        duration_ms = int((time.time() - start_time) * 1000)
        tool_response = ToolCallResponse(
            tool_name=request.tool_name,
            content=response.get("content", []),
            is_error=response.get("isError", False),
            trace_id=trace_id,
            duration_ms=duration_ms,
        )

        # 6. PII mask response
        tool_response = self._masker.mask_response(tool_response)

        # 7. Audit log
        status = (
            AuditStatus.FAILED if tool_response.is_error else AuditStatus.SUCCESS
        )
        await self._audit.log(
            self._audit.create_entry(
                trace_id=trace_id,
                user_id=user_id,
                session_id=request.session_id,
                tool_name=request.tool_name,
                arguments=request.arguments,
                status=status,
                duration_ms=duration_ms,
            )
        )

        return tool_response

    async def _forward_to_server(
        self,
        base_url: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Forward tool call to MCP Server.

        Args:
            base_url: Server base URL.
            tool_name: Full tool name (server.tool).
            arguments: Masked arguments.

        Returns:
            Raw response dict from server.
        """
        # Extract the tool-local name (after the server prefix)
        local_tool_name = (
            tool_name.split(".", 1)[1] if "." in tool_name else tool_name
        )

        url = f"{base_url}/mcp/call_tool"
        payload = {"name": local_tool_name, "arguments": arguments}

        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            result: dict[str, Any] = resp.json()
            return result
