"""Unit tests for A-05 Short-term Memory."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_core.hermes.memory import (
    Message,
    ShortTermMemory,
)


@pytest.fixture
def mock_redis() -> MagicMock:
    """Create a mock Redis client."""
    redis = AsyncMock()
    # pipeline() is synchronous in redis.asyncio
    pipe = MagicMock()
    pipe.execute = AsyncMock(return_value=[])
    pipe.hset = MagicMock(return_value=pipe)
    pipe.expire = MagicMock(return_value=pipe)
    pipe.rpush = MagicMock(return_value=pipe)
    pipe.ltrim = MagicMock(return_value=pipe)
    pipe.zadd = MagicMock(return_value=pipe)
    pipe.set = MagicMock(return_value=pipe)
    pipe.delete = MagicMock(return_value=pipe)
    pipe.zrem = MagicMock(return_value=pipe)
    redis.pipeline = MagicMock(return_value=pipe)
    return redis


@pytest.fixture
def memory(mock_redis: MagicMock) -> ShortTermMemory:
    """Create ShortTermMemory with mocked Redis."""
    mem = ShortTermMemory.__new__(ShortTermMemory)
    mem._redis = mock_redis
    return mem


@pytest.mark.asyncio
async def test_create_session(
    memory: ShortTermMemory, mock_redis: MagicMock
) -> None:
    """Test session creation stores metadata in Redis."""
    session_id = await memory.create_session(
        user_id="user_1",
        initial_context={"dataset": "creditcard"},
    )

    assert session_id.startswith("sess_")
    pipe = mock_redis.pipeline.return_value
    pipe.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_session_returns_none_when_missing(
    memory: ShortTermMemory, mock_redis: MagicMock
) -> None:
    """Test get_session returns None for non-existent session."""
    mock_redis.hgetall.return_value = {}

    result = await memory.get_session("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_get_session_returns_full_state(
    memory: ShortTermMemory, mock_redis: MagicMock
) -> None:
    """Test get_session reconstructs full SessionMemory."""
    mock_redis.hgetall.side_effect = [
        # First call: meta
        {
            "session_id": "sess_abc",
            "user_id": "user_1",
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:01:00+00:00",
        },
        # Second call: vars
        {"dataset": json.dumps("creditcard")},
    ]
    msg = Message(role="user", content="hello")
    mock_redis.lrange.return_value = [msg.model_dump_json()]

    result = await memory.get_session("sess_abc")

    assert result is not None
    assert result.session_id == "sess_abc"
    assert result.user_id == "user_1"
    assert len(result.messages) == 1
    assert result.messages[0].content == "hello"
    assert result.variables == {"dataset": "creditcard"}


@pytest.mark.asyncio
async def test_append_message_uses_pipeline(
    memory: ShortTermMemory, mock_redis: MagicMock
) -> None:
    """Test append_message uses atomic pipeline with LTRIM."""
    msg = Message(role="user", content="test message")

    await memory.append_message("sess_abc", msg)

    pipe = mock_redis.pipeline.return_value
    pipe.rpush.assert_called_once()
    pipe.ltrim.assert_called_once()
    pipe.execute.assert_called_once()


@pytest.mark.asyncio
async def test_set_and_get_variable(
    memory: ShortTermMemory, mock_redis: MagicMock
) -> None:
    """Test variable storage and retrieval."""
    await memory.set_variable("sess_abc", "model_path", "/tmp/model.pkl")

    pipe = mock_redis.pipeline.return_value
    pipe.hset.assert_called()

    # Test get
    mock_redis.hget.return_value = json.dumps("/tmp/model.pkl")
    result = await memory.get_variable("sess_abc", "model_path")
    assert result == "/tmp/model.pkl"


@pytest.mark.asyncio
async def test_get_variable_returns_none_when_missing(
    memory: ShortTermMemory, mock_redis: MagicMock
) -> None:
    """Test get_variable returns None for missing key."""
    mock_redis.hget.return_value = None
    result = await memory.get_variable("sess_abc", "missing")
    assert result is None


@pytest.mark.asyncio
async def test_save_and_get_execution_state(
    memory: ShortTermMemory, mock_redis: MagicMock
) -> None:
    """Test execution state persistence."""
    state = {"task_status": "running", "step_states": {}}

    await memory.save_execution_state("sess_abc", state)
    pipe = mock_redis.pipeline.return_value
    pipe.set.assert_called_once()

    # Test retrieval
    mock_redis.get.return_value = json.dumps(state)
    result = await memory.get_execution_state("sess_abc")
    assert result == state


@pytest.mark.asyncio
async def test_delete_session(
    memory: ShortTermMemory, mock_redis: MagicMock
) -> None:
    """Test session deletion removes all keys."""
    mock_redis.hgetall.return_value = {
        "session_id": "sess_abc",
        "user_id": "user_1",
    }

    await memory.delete_session("sess_abc")

    pipe = mock_redis.pipeline.return_value
    pipe.delete.assert_called_once()
    pipe.execute.assert_called_once()


@pytest.mark.asyncio
async def test_list_sessions(
    memory: ShortTermMemory, mock_redis: MagicMock
) -> None:
    """Test listing sessions for a user."""
    mock_redis.zrevrange.return_value = ["sess_1", "sess_2"]
    mock_redis.hgetall.side_effect = [
        {"session_id": "sess_1", "user_id": "user_1"},
        {"session_id": "sess_2", "user_id": "user_1"},
    ]

    sessions = await memory.list_sessions("user_1", limit=10)
    assert len(sessions) == 2
    assert sessions[0]["session_id"] == "sess_1"
