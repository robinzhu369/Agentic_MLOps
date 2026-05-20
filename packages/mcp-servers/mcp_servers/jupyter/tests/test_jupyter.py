"""Tests for mcp-jupyter server."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mcp_servers.jupyter.app import app
from mcp_servers.jupyter.server import MCPJupyterServer

# --- Unit Tests: MCPJupyterServer ---


class TestMCPJupyterServer:
    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self.server = MCPJupyterServer()

    @pytest.mark.asyncio
    async def test_list_tools_returns_4_tools(self) -> None:
        result = await self.server.list_tools()
        assert "tools" in result
        assert len(result["tools"]) == 4
        names = [t["name"] for t in result["tools"]]
        assert "execute_code" in names
        assert "create_kernel" in names
        assert "list_variables" in names
        assert "restart_kernel" in names

    @pytest.mark.asyncio
    async def test_list_tools_has_input_schema(self) -> None:
        result = await self.server.list_tools()
        for tool in result["tools"]:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool
            assert tool["inputSchema"]["type"] == "object"

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self) -> None:
        result = await self.server.call_tool("nonexistent", {})
        assert result["isError"] is True
        assert "Unknown tool" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_execute_code_missing_kernel_id(self) -> None:
        result = await self.server.call_tool(
            "execute_code", {"code": "1+1"}
        )
        assert result["isError"] is True
        assert "kernel_id" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_create_and_execute(self) -> None:
        # Create kernel
        create_result = await self.server.call_tool(
            "create_kernel", {"kernel_type": "python3"}
        )
        assert create_result["isError"] is False
        import json

        kernel_info = json.loads(create_result["content"][0]["text"])
        kernel_id = kernel_info["kernel_id"]

        # Execute code
        exec_result = await self.server.call_tool(
            "execute_code",
            {"kernel_id": kernel_id, "code": "1 + 1"},
        )
        assert exec_result["isError"] is False
        exec_data = json.loads(exec_result["content"][0]["text"])
        assert exec_data["result"] == "2"
        assert exec_data["execution_count"] == 1

    @pytest.mark.asyncio
    async def test_execute_with_print(self) -> None:
        create_result = await self.server.call_tool(
            "create_kernel", {}
        )
        import json

        kernel_id = json.loads(
            create_result["content"][0]["text"]
        )["kernel_id"]

        exec_result = await self.server.call_tool(
            "execute_code",
            {"kernel_id": kernel_id, "code": "print('hello')"},
        )
        exec_data = json.loads(exec_result["content"][0]["text"])
        assert "hello" in exec_data["stdout"]

    @pytest.mark.asyncio
    async def test_execute_with_error(self) -> None:
        create_result = await self.server.call_tool(
            "create_kernel", {}
        )
        import json

        kernel_id = json.loads(
            create_result["content"][0]["text"]
        )["kernel_id"]

        exec_result = await self.server.call_tool(
            "execute_code",
            {"kernel_id": kernel_id, "code": "1/0"},
        )
        assert exec_result["isError"] is False  # execution itself succeeds
        exec_data = json.loads(exec_result["content"][0]["text"])
        assert "ZeroDivisionError" in exec_data["stderr"]

    @pytest.mark.asyncio
    async def test_list_variables(self) -> None:
        import json

        create_result = await self.server.call_tool(
            "create_kernel", {}
        )
        kernel_id = json.loads(
            create_result["content"][0]["text"]
        )["kernel_id"]

        # Set some variables
        await self.server.call_tool(
            "execute_code",
            {"kernel_id": kernel_id, "code": "x = 42\ny = 'hello'"},
        )

        # List variables
        var_result = await self.server.call_tool(
            "list_variables", {"kernel_id": kernel_id}
        )
        assert var_result["isError"] is False
        variables = json.loads(var_result["content"][0]["text"])
        names = [v["name"] for v in variables]
        assert "x" in names
        assert "y" in names

    @pytest.mark.asyncio
    async def test_restart_kernel(self) -> None:
        import json

        create_result = await self.server.call_tool(
            "create_kernel", {}
        )
        kernel_id = json.loads(
            create_result["content"][0]["text"]
        )["kernel_id"]

        # Set variable
        await self.server.call_tool(
            "execute_code",
            {"kernel_id": kernel_id, "code": "x = 42"},
        )

        # Restart
        restart_result = await self.server.call_tool(
            "restart_kernel", {"kernel_id": kernel_id}
        )
        assert restart_result["isError"] is False

        # Variables should be cleared
        var_result = await self.server.call_tool(
            "list_variables", {"kernel_id": kernel_id}
        )
        variables = json.loads(var_result["content"][0]["text"])
        assert len(variables) == 0

    @pytest.mark.asyncio
    async def test_kernel_not_found(self) -> None:
        result = await self.server.call_tool(
            "execute_code",
            {"kernel_id": "nonexistent", "code": "1+1"},
        )
        assert result["isError"] is True
        assert "not found" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_unsupported_kernel_type(self) -> None:
        result = await self.server.call_tool(
            "create_kernel", {"kernel_type": "julia"}
        )
        assert result["isError"] is True
        assert "Unsupported" in result["content"][0]["text"]


# --- Integration Tests: HTTP API ---


class TestMCPJupyterHTTP:
    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_health(self) -> None:
        resp = self.client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["service"] == "mcp-jupyter"

    def test_list_tools_endpoint(self) -> None:
        resp = self.client.post("/mcp/list_tools")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["tools"]) == 4

    def test_call_tool_create_and_execute(self) -> None:
        # Create kernel
        resp = self.client.post(
            "/mcp/call_tool",
            json={"name": "create_kernel", "arguments": {}},
        )
        assert resp.status_code == 200
        import json

        kernel_id = json.loads(
            resp.json()["content"][0]["text"]
        )["kernel_id"]

        # Execute
        resp = self.client.post(
            "/mcp/call_tool",
            json={
                "name": "execute_code",
                "arguments": {"kernel_id": kernel_id, "code": "2**10"},
            },
        )
        assert resp.status_code == 200
        result = json.loads(resp.json()["content"][0]["text"])
        assert result["result"] == "1024"
