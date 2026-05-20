"""MCP Jupyter Server — HTTP interface for MCP Gateway integration."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from .server import MCPJupyterServer

app = FastAPI(title="mcp-jupyter", version="0.1.0")
_server = MCPJupyterServer()


@app.post("/mcp/list_tools")
async def list_tools() -> dict[str, Any]:
    """Return tool descriptors per MCP spec."""
    return await _server.list_tools()


@app.post("/mcp/call_tool")
async def call_tool(request: dict[str, Any]) -> dict[str, Any]:
    """Execute a tool call."""
    name = request.get("name", "")
    arguments = request.get("arguments", {})
    return await _server.call_tool(name, arguments)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check."""
    return {"status": "ok", "service": "mcp-jupyter"}
