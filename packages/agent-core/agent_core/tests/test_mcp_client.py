"""Unit tests for A-04 MCP Client."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from agent_core.hermes.config import AgentCoreSettings
from agent_core.hermes.mcp_client import (
    MCPAuthError,
    MCPClient,
    MCPGatewayError,
    MCPResponseError,
    MCPToolNotFoundError,
    TokenProvider,
)


@pytest.fixture
def settings() -> AgentCoreSettings:
    return AgentCoreSettings(
        anthropic_api_key="test-key",
        mcp_gateway_base_url="http://localhost:8100",
    )


@pytest.fixture
def mock_token_provider() -> AsyncMock:
    provider = AsyncMock(spec=TokenProvider)
    provider.get_token.return_value = "test-jwt-token"
    provider.close = AsyncMock()
    return provider


@pytest.fixture
def client(
    settings: AgentCoreSettings, mock_token_provider: AsyncMock
) -> MCPClient:
    return MCPClient(
        settings=settings, token_provider=mock_token_provider
    )


@pytest.mark.asyncio
async def test_call_tool_success(client: MCPClient) -> None:
    """Test successful tool call through MCP Gateway."""
    mock_response = httpx.Response(
        200,
        json={
            "tool_name": "jupyter.execute_code",
            "content": [{"type": "text", "text": "2"}],
            "is_error": False,
            "trace_id": "trace_123",
            "duration_ms": 50,
        },
    )

    with patch.object(
        client._client, "post", new_callable=AsyncMock
    ) as mock_post:
        mock_post.return_value = mock_response
        result = await client.call_tool(
            tool_name="jupyter.execute_code",
            arguments={"code": "1+1"},
            session_id="sess_123",
        )

    assert result["content"] == [{"type": "text", "text": "2"}]
    assert result["is_error"] is False

    # Verify JWT was injected
    call_kwargs = mock_post.call_args.kwargs
    assert "Bearer test-jwt-token" in str(call_kwargs["headers"])


@pytest.mark.asyncio
async def test_call_tool_401_raises_auth_error(
    client: MCPClient,
) -> None:
    """Test that 401 response raises MCPAuthError."""
    mock_response = httpx.Response(401, json={"detail": "Unauthorized"})

    with patch.object(
        client._client, "post", new_callable=AsyncMock
    ) as mock_post:
        mock_post.return_value = mock_response
        with pytest.raises(MCPAuthError):
            await client.call_tool(
                tool_name="jupyter.execute_code",
                arguments={},
                session_id="sess_123",
            )


@pytest.mark.asyncio
async def test_call_tool_404_raises_not_found(
    client: MCPClient,
) -> None:
    """Test that 404 response raises MCPToolNotFoundError."""
    mock_response = httpx.Response(404, json={})

    with patch.object(
        client._client, "post", new_callable=AsyncMock
    ) as mock_post:
        mock_post.return_value = mock_response
        with pytest.raises(MCPToolNotFoundError) as exc_info:
            await client.call_tool(
                tool_name="nonexistent.tool",
                arguments={},
                session_id="sess_123",
            )
    assert exc_info.value.tool_name == "nonexistent.tool"


@pytest.mark.asyncio
async def test_call_tool_500_raises_gateway_error(
    client: MCPClient,
) -> None:
    """Test that 5xx response raises MCPGatewayError."""
    mock_response = httpx.Response(
        502, text="Bad Gateway"
    )

    with patch.object(
        client._client, "post", new_callable=AsyncMock
    ) as mock_post:
        mock_post.return_value = mock_response
        with pytest.raises(MCPGatewayError) as exc_info:
            await client.call_tool(
                tool_name="jupyter.execute_code",
                arguments={},
                session_id="sess_123",
            )
    assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_call_tool_missing_content_raises_response_error(
    client: MCPClient,
) -> None:
    """Test that response without 'content' raises MCPResponseError."""
    mock_response = httpx.Response(
        200, json={"tool_name": "test", "is_error": False}
    )

    with patch.object(
        client._client, "post", new_callable=AsyncMock
    ) as mock_post:
        mock_post.return_value = mock_response
        with pytest.raises(MCPResponseError):
            await client.call_tool(
                tool_name="jupyter.execute_code",
                arguments={},
                session_id="sess_123",
            )


@pytest.mark.asyncio
async def test_call_tool_dry_run_header(
    client: MCPClient,
) -> None:
    """Test that dry_run=True sends X-Dry-Run header."""
    mock_response = httpx.Response(
        200,
        json={
            "tool_name": "test",
            "content": [],
            "is_error": False,
        },
    )

    with patch.object(
        client._client, "post", new_callable=AsyncMock
    ) as mock_post:
        mock_post.return_value = mock_response
        await client.call_tool(
            tool_name="jupyter.execute_code",
            arguments={},
            session_id="sess_123",
            dry_run=True,
        )

    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["headers"]["X-Dry-Run"] == "true"


@pytest.mark.asyncio
async def test_list_available_tools(client: MCPClient) -> None:
    """Test fetching capability manifest."""
    mock_response = httpx.Response(
        200,
        json={
            "tools": [
                {"tool_name": "jupyter.execute_code"},
                {"tool_name": "data_catalog.get_schema"},
            ],
            "tool_count": 2,
        },
    )

    with patch.object(
        client._client, "get", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = mock_response
        tools = await client.list_available_tools()

    assert tools == [
        "jupyter.execute_code",
        "data_catalog.get_schema",
    ]


@pytest.mark.asyncio
async def test_token_provider_auto_refresh() -> None:
    """Test that TokenProvider refreshes token before expiry."""
    provider = TokenProvider(
        gateway_base_url="http://localhost:8100"
    )
    # Simulate an existing token that's about to expire
    provider._access_token = "old-token"
    provider._expires_at = time.time() + 30  # 30s left (< 60s)
    provider._refresh_token = "refresh-token"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": "new-token",
        "expires_in": 3600,
    }

    with patch.object(
        provider._client, "post", new_callable=AsyncMock
    ) as mock_post:
        mock_post.return_value = mock_response
        token = await provider.get_token()

    assert token == "new-token"
    await provider.close()
