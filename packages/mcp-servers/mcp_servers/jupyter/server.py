"""MCP Jupyter Server — Kernel management and code execution via MCP protocol."""
from __future__ import annotations

import json
from typing import Any

import structlog

from .kernel_manager import KernelError, KernelManager

logger = structlog.get_logger("mcp_servers.jupyter")

# MCP tool definitions
_TOOLS = [
    {
        "name": "execute_code",
        "description": (
            "Execute Python/R code in a Jupyter Kernel"
            " and return stdout, stderr, and result."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "kernel_id": {
                    "type": "string",
                    "description": "ID of the kernel to execute code in",
                },
                "code": {
                    "type": "string",
                    "description": "Code to execute",
                },
                "timeout_s": {
                    "type": "integer",
                    "description": "Execution timeout in seconds (default 300)",
                    "default": 300,
                },
            },
            "required": ["kernel_id", "code"],
        },
    },
    {
        "name": "create_kernel",
        "description": "Create a new Jupyter Kernel for code execution.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kernel_type": {
                    "type": "string",
                    "enum": ["python3", "ir"],
                    "description": "Kernel type (default: python3)",
                    "default": "python3",
                },
                "session_id": {
                    "type": "string",
                    "description": "Agent session ID for lifecycle management",
                },
            },
            "required": [],
        },
    },
    {
        "name": "list_variables",
        "description": (
            "List variables in the Kernel namespace"
            " with their types and shapes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "kernel_id": {
                    "type": "string",
                    "description": "ID of the kernel to inspect",
                },
            },
            "required": ["kernel_id"],
        },
    },
    {
        "name": "restart_kernel",
        "description": "Restart a Kernel and clear its namespace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kernel_id": {
                    "type": "string",
                    "description": "ID of the kernel to restart",
                },
            },
            "required": ["kernel_id"],
        },
    },
]


def _success_response(data: Any) -> dict[str, Any]:
    """Create a successful MCP response."""
    text = json.dumps(data, ensure_ascii=False, default=str)
    return {"content": [{"type": "text", "text": text}], "isError": False}


def _error_response(message: str) -> dict[str, Any]:
    """Create an error MCP response (no raw tracebacks)."""
    return {
        "content": [{"type": "text", "text": f"[ERROR] {message}"}],
        "isError": True,
    }


class MCPJupyterServer:
    """MCP Server for Jupyter Kernel operations."""

    def __init__(self, kernel_manager: KernelManager | None = None) -> None:
        self._km = kernel_manager or KernelManager()

    async def list_tools(self) -> dict[str, Any]:
        """Return MCP tool descriptors.

        Returns:
            Dict with 'tools' key containing list of tool schemas.
        """
        return {"tools": _TOOLS}

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Dispatch to the appropriate tool implementation.

        Args:
            name: Tool name.
            arguments: Tool arguments.

        Returns:
            MCP-format response dict.
        """
        handlers = {
            "execute_code": self._execute_code,
            "create_kernel": self._create_kernel,
            "list_variables": self._list_variables,
            "restart_kernel": self._restart_kernel,
        }

        handler = handlers.get(name)
        if handler is None:
            return _error_response(
                f"Unknown tool: {name}. "
                f"Available: {list(handlers.keys())}"
            )

        try:
            return await handler(arguments)
        except KernelError as e:
            logger.warning("tool_error", tool=name, error=str(e))
            return _error_response(str(e))
        except Exception as e:
            logger.error("tool_unexpected_error", tool=name, error=str(e))
            return _error_response(f"Internal error in {name}")

    async def _execute_code(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute code in a kernel."""
        kernel_id = arguments.get("kernel_id", "")
        code = arguments.get("code", "")
        timeout_s = arguments.get("timeout_s", 300)

        if not kernel_id:
            return _error_response("kernel_id is required")
        if not code:
            return _error_response("code is required")

        result = await self._km.execute_code(
            kernel_id=kernel_id, code=code, timeout_s=timeout_s
        )
        return _success_response(result)

    async def _create_kernel(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a new kernel."""
        kernel_type = arguments.get("kernel_type", "python3")
        session_id = arguments.get("session_id")

        kernel_info = await self._km.create_kernel(
            kernel_type=kernel_type, session_id=session_id
        )
        return _success_response(kernel_info)

    async def _list_variables(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """List variables in kernel namespace."""
        kernel_id = arguments.get("kernel_id", "")
        if not kernel_id:
            return _error_response("kernel_id is required")

        variables = await self._km.list_variables(kernel_id=kernel_id)
        return _success_response(variables)

    async def _restart_kernel(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Restart a kernel."""
        kernel_id = arguments.get("kernel_id", "")
        if not kernel_id:
            return _error_response("kernel_id is required")

        await self._km.restart_kernel(kernel_id=kernel_id)
        return _success_response(
            {"message": f"Kernel {kernel_id} restarted successfully"}
        )
