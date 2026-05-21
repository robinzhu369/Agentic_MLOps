"""Unit tests for A-10 Streaming Output and A-03 Dual-loop Executor."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from agent_core.hermes.config import AgentCoreSettings
from agent_core.hermes.executor import (
    DualLoopExecutor,
    Observation,
    StepStatus,
)
from agent_core.hermes.mcp_client import MCPClient, MCPGatewayError
from agent_core.hermes.memory import ShortTermMemory
from agent_core.hermes.planner import Planner
from agent_core.hermes.schemas import Plan, PlanStep
from agent_core.hermes.stream import (
    EventStore,
    EventType,
    StreamEvent,
    StreamingOutput,
    _format_sse,
)

# --- StreamingOutput Tests ---


@pytest.mark.asyncio
async def test_stream_emit_increments_event_id() -> None:
    """Test that event_id is monotonically increasing."""
    stream = StreamingOutput("sess_1")

    e1 = await stream.emit(EventType.PLAN, {"plan_id": "p1"})
    e2 = await stream.emit(
        EventType.TOOL_CALL, {"step_id": "s1"}
    )
    e3 = await stream.emit(
        EventType.OBSERVATION, {"step_id": "s1"}
    )

    assert e1.event_id == 1
    assert e2.event_id == 2
    assert e3.event_id == 3


@pytest.mark.asyncio
async def test_stream_subscriber_receives_events() -> None:
    """Test that subscribers receive emitted events."""
    stream = StreamingOutput("sess_1")
    queue = stream.subscribe()

    await stream.emit(EventType.PLAN, {"plan_id": "p1"})

    event = queue.get_nowait()
    assert event is not None
    assert event.event == EventType.PLAN
    assert event.data["plan_id"] == "p1"

    stream.unsubscribe(queue)


@pytest.mark.asyncio
async def test_stream_close_signals_end() -> None:
    """Test that close() sends None to subscribers."""
    stream = StreamingOutput("sess_1")
    queue = stream.subscribe()

    await stream.close()

    event = queue.get_nowait()
    assert event is None


@pytest.mark.asyncio
async def test_event_store_keeps_max_events() -> None:
    """Test EventStore truncates to max_events."""
    store = EventStore(max_events=3)

    for i in range(5):
        event = StreamEvent(
            event_id=i + 1,
            event=EventType.OBSERVATION,
            data={"i": i},
            session_id="sess_1",
        )
        await store.append(event)

    all_events = await store.get_all("sess_1")
    assert len(all_events) == 3
    assert all_events[0].event_id == 3  # Oldest kept


@pytest.mark.asyncio
async def test_event_store_get_since() -> None:
    """Test EventStore returns events after given ID."""
    store = EventStore()

    for i in range(5):
        event = StreamEvent(
            event_id=i + 1,
            event=EventType.OBSERVATION,
            data={"i": i},
            session_id="sess_1",
        )
        await store.append(event)

    since = await store.get_since("sess_1", 3)
    assert len(since) == 2
    assert since[0].event_id == 4
    assert since[1].event_id == 5


def test_format_sse() -> None:
    """Test SSE wire format."""
    event = StreamEvent(
        event_id=42,
        event=EventType.TOOL_CALL,
        data={"step_id": "step_1", "tool_name": "jupyter.execute_code"},
        session_id="sess_1",
    )

    formatted = _format_sse(event)
    assert "id: 42\n" in formatted
    assert "event: tool_call\n" in formatted
    assert "data: " in formatted
    assert formatted.endswith("\n\n")

    # Verify data is valid JSON
    data_line = [
        line
        for line in formatted.split("\n")
        if line.startswith("data:")
    ][0]
    data_json = data_line[len("data: "):]
    parsed = json.loads(data_json)
    assert parsed["step_id"] == "step_1"


# --- DualLoopExecutor Tests ---


@pytest.fixture
def settings() -> AgentCoreSettings:
    return AgentCoreSettings(
        anthropic_api_key="test-key",
        max_retries_per_step=2,
        max_replans=2,
    )


@pytest.fixture
def mock_mcp() -> AsyncMock:
    mcp = AsyncMock(spec=MCPClient)
    mcp.call_tool.return_value = {
        "content": [{"type": "text", "text": "result"}],
        "is_error": False,
    }
    return mcp


@pytest.fixture
def mock_memory() -> AsyncMock:
    mem = AsyncMock(spec=ShortTermMemory)
    mem.save_execution_state = AsyncMock()
    return mem


@pytest.fixture
def mock_planner() -> AsyncMock:
    return AsyncMock(spec=Planner)


@pytest.fixture
def executor(
    mock_mcp: AsyncMock,
    mock_memory: AsyncMock,
    mock_planner: AsyncMock,
    settings: AgentCoreSettings,
) -> DualLoopExecutor:
    return DualLoopExecutor(
        mcp_client=mock_mcp,
        memory=mock_memory,
        planner=mock_planner,
        settings=settings,
    )


def _make_plan(steps: list[PlanStep]) -> Plan:
    return Plan(
        plan_id="plan_test",
        session_id="sess_test",
        steps=steps,
    )


@pytest.mark.asyncio
async def test_executor_runs_sequential_steps(
    executor: DualLoopExecutor, mock_mcp: AsyncMock
) -> None:
    """Test executor runs steps in order based on depends_on."""
    plan = _make_plan([
        PlanStep(
            step_id="step_1",
            tool_name="data_catalog.get_schema",
            tool_args={"table": "t1"},
            description="Get schema",
        ),
        PlanStep(
            step_id="step_2",
            tool_name="jupyter.execute_code",
            tool_args={"code": "x=1"},
            depends_on=["step_1"],
            description="Execute code",
        ),
    ])

    stream = StreamingOutput("sess_test")
    observations: list[Observation] = []

    async for obs in executor.execute(plan, "sess_test", stream):
        observations.append(obs)

    assert len(observations) == 2
    assert observations[0].step_id == "step_1"
    assert observations[0].status == StepStatus.COMPLETED
    assert observations[1].step_id == "step_2"
    assert observations[1].status == StepStatus.COMPLETED
    assert mock_mcp.call_tool.call_count == 2


@pytest.mark.asyncio
async def test_executor_retries_on_gateway_error(
    executor: DualLoopExecutor, mock_mcp: AsyncMock
) -> None:
    """Test inner loop retries on 5xx errors with backoff."""
    # First call fails, second succeeds
    mock_mcp.call_tool.side_effect = [
        MCPGatewayError(502, "Bad Gateway"),
        {
            "content": [{"type": "text", "text": "ok"}],
            "is_error": False,
        },
    ]

    plan = _make_plan([
        PlanStep(
            step_id="step_1",
            tool_name="jupyter.execute_code",
            tool_args={"code": "1"},
            description="Test",
        ),
    ])

    stream = StreamingOutput("sess_test")
    observations: list[Observation] = []

    async for obs in executor.execute(plan, "sess_test", stream):
        observations.append(obs)

    assert len(observations) == 1
    assert observations[0].status == StepStatus.COMPLETED
    assert observations[0].retry_count == 1


@pytest.mark.asyncio
async def test_executor_triggers_replan_after_max_retries(
    executor: DualLoopExecutor,
    mock_mcp: AsyncMock,
    mock_planner: AsyncMock,
) -> None:
    """Test that replan is triggered after all retries fail."""
    # All calls fail for first plan
    mock_mcp.call_tool.side_effect = [
        MCPGatewayError(500, "Error"),
        MCPGatewayError(500, "Error"),
        MCPGatewayError(500, "Error"),
        # After replan, succeed
        {
            "content": [{"type": "text", "text": "ok"}],
            "is_error": False,
        },
    ]

    original_plan = _make_plan([
        PlanStep(
            step_id="step_1",
            tool_name="jupyter.execute_code",
            tool_args={"code": "bad"},
            description="Failing step",
        ),
    ])

    # Replan returns a new plan
    mock_planner.replan.return_value = _make_plan([
        PlanStep(
            step_id="step_1_v2",
            tool_name="jupyter.execute_code",
            tool_args={"code": "good"},
            description="Fixed step",
        ),
    ])

    stream = StreamingOutput("sess_test")
    observations: list[Observation] = []

    async for obs in executor.execute(
        original_plan, "sess_test", stream
    ):
        observations.append(obs)

    # Should have replanned and succeeded
    assert mock_planner.replan.call_count == 1
    assert any(
        o.status == StepStatus.COMPLETED for o in observations
    )


@pytest.mark.asyncio
async def test_executor_confirm_step_approved(
    executor: DualLoopExecutor, mock_mcp: AsyncMock
) -> None:
    """Test HITL confirmation flow — approved."""
    plan = _make_plan([
        PlanStep(
            step_id="step_1",
            tool_name="feature_store.delete_feature_view",
            tool_args={"name": "old"},
            description="Delete feature view",
            requires_confirm=True,
        ),
    ])

    stream = StreamingOutput("sess_test")

    # Simulate user confirming after a short delay
    async def confirm_after_delay() -> None:
        await asyncio.sleep(0.1)
        await executor.confirm_step("sess_test", "step_1", True)

    asyncio.create_task(confirm_after_delay())

    observations: list[Observation] = []
    async for obs in executor.execute(plan, "sess_test", stream):
        observations.append(obs)

    assert len(observations) == 1
    assert observations[0].status == StepStatus.COMPLETED


@pytest.mark.asyncio
async def test_executor_confirm_step_rejected(
    executor: DualLoopExecutor, mock_mcp: AsyncMock
) -> None:
    """Test HITL confirmation flow — rejected skips step."""
    plan = _make_plan([
        PlanStep(
            step_id="step_1",
            tool_name="feature_store.delete_feature_view",
            tool_args={"name": "old"},
            description="Delete feature view",
            requires_confirm=True,
        ),
    ])

    stream = StreamingOutput("sess_test")

    async def reject_after_delay() -> None:
        await asyncio.sleep(0.1)
        await executor.confirm_step("sess_test", "step_1", False)

    asyncio.create_task(reject_after_delay())

    observations: list[Observation] = []
    async for obs in executor.execute(plan, "sess_test", stream):
        observations.append(obs)

    assert len(observations) == 1
    assert observations[0].status == StepStatus.SKIPPED
    # Tool should NOT have been called
    mock_mcp.call_tool.assert_not_called()


@pytest.mark.asyncio
async def test_executor_parallel_steps(
    executor: DualLoopExecutor, mock_mcp: AsyncMock
) -> None:
    """Test that independent steps run concurrently."""
    plan = _make_plan([
        PlanStep(
            step_id="step_1",
            tool_name="data_catalog.get_schema",
            tool_args={"table": "t1"},
            description="Schema 1",
        ),
        PlanStep(
            step_id="step_2",
            tool_name="data_catalog.get_schema",
            tool_args={"table": "t2"},
            description="Schema 2",
        ),
        PlanStep(
            step_id="step_3",
            tool_name="jupyter.execute_code",
            tool_args={"code": "merge"},
            depends_on=["step_1", "step_2"],
            description="Merge results",
        ),
    ])

    stream = StreamingOutput("sess_test")
    observations: list[Observation] = []

    async for obs in executor.execute(plan, "sess_test", stream):
        observations.append(obs)

    assert len(observations) == 3
    # step_3 should be last (depends on 1 and 2)
    assert observations[2].step_id == "step_3"


@pytest.mark.asyncio
async def test_executor_emits_all_event_types(
    executor: DualLoopExecutor, mock_mcp: AsyncMock
) -> None:
    """Test that executor emits plan, tool_call, observation, task_complete."""
    plan = _make_plan([
        PlanStep(
            step_id="step_1",
            tool_name="jupyter.execute_code",
            tool_args={"code": "1"},
            description="Test",
        ),
    ])

    event_store = EventStore()
    stream = StreamingOutput("sess_test", event_store)

    async for _ in executor.execute(plan, "sess_test", stream):
        pass

    events = await event_store.get_all("sess_test")
    event_types = {e.event for e in events}

    assert EventType.PLAN in event_types
    assert EventType.TOOL_CALL in event_types
    assert EventType.OBSERVATION in event_types
    assert EventType.TASK_COMPLETE in event_types


@pytest.mark.asyncio
async def test_executor_persists_state(
    executor: DualLoopExecutor,
    mock_mcp: AsyncMock,
    mock_memory: AsyncMock,
) -> None:
    """Test that execution state is persisted to memory."""
    plan = _make_plan([
        PlanStep(
            step_id="step_1",
            tool_name="jupyter.execute_code",
            tool_args={"code": "1"},
            description="Test",
        ),
    ])

    stream = StreamingOutput("sess_test")

    async for _ in executor.execute(plan, "sess_test", stream):
        pass

    # State should be saved at least once
    mock_memory.save_execution_state.assert_called()
    call_args = mock_memory.save_execution_state.call_args
    assert call_args[0][0] == "sess_test"
