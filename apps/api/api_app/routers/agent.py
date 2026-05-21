"""Agent HTTP/SSE router — session management and execution endpoints."""
from __future__ import annotations

from typing import Any

import structlog
from agent_core.hermes.config import get_agent_settings
from agent_core.hermes.executor import DualLoopExecutor
from agent_core.hermes.intent import IntentParser
from agent_core.hermes.mcp_client import MCPClient
from agent_core.hermes.memory import Message, ShortTermMemory
from agent_core.hermes.planner import Planner
from agent_core.hermes.stream import EventStore, StreamingOutput
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])

# --- Singletons (initialized on first use) ---

_memory: ShortTermMemory | None = None
_mcp_client: MCPClient | None = None
_intent_parser: IntentParser | None = None
_planner: Planner | None = None
_event_store: EventStore | None = None
_executors: dict[str, DualLoopExecutor] = {}
_streams: dict[str, StreamingOutput] = {}


def _get_memory() -> ShortTermMemory:
    global _memory  # noqa: PLW0603
    if _memory is None:
        _memory = ShortTermMemory()
    return _memory


def _get_mcp_client() -> MCPClient:
    global _mcp_client  # noqa: PLW0603
    if _mcp_client is None:
        _mcp_client = MCPClient()
    return _mcp_client


def _get_intent_parser() -> IntentParser:
    global _intent_parser  # noqa: PLW0603
    if _intent_parser is None:
        _intent_parser = IntentParser()
    return _intent_parser


def _get_planner() -> Planner:
    global _planner  # noqa: PLW0603
    if _planner is None:
        _planner = Planner()
    return _planner


def _get_event_store() -> EventStore:
    global _event_store  # noqa: PLW0603
    if _event_store is None:
        _event_store = EventStore()
    return _event_store


# --- Request/Response Models ---


class CreateSessionRequest(BaseModel):
    user_id: str
    initial_context: dict[str, Any] | None = None


class CreateSessionResponse(BaseModel):
    session_id: str


class SendMessageRequest(BaseModel):
    content: str


class SendMessageResponse(BaseModel):
    session_id: str
    message_id: str = ""
    status: str = "processing"


class ConfirmStepRequest(BaseModel):
    step_id: str
    approved: bool = True


class SessionStatusResponse(BaseModel):
    session_id: str
    task_status: str
    step_count: int = 0
    completed_steps: int = 0
    replan_count: int = 0


class SessionListResponse(BaseModel):
    sessions: list[dict[str, Any]] = Field(default_factory=list)


# --- Endpoints ---


@router.post("/sessions", response_model=CreateSessionResponse)
async def create_session(
    req: CreateSessionRequest,
) -> CreateSessionResponse:
    """Create a new Agent session."""
    memory = _get_memory()
    session_id = await memory.create_session(
        user_id=req.user_id,
        initial_context=req.initial_context,
    )
    return CreateSessionResponse(session_id=session_id)


@router.post(
    "/sessions/{session_id}/messages",
    response_model=SendMessageResponse,
)
async def send_message(
    session_id: str,
    req: SendMessageRequest,
) -> SendMessageResponse:
    """Send a message to the Agent and trigger execution.

    The Agent will parse intent, create a plan, and begin execution.
    Results are streamed via the /stream endpoint.
    """
    memory = _get_memory()
    session = await memory.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Store user message
    await memory.append_message(
        session_id,
        Message(role="user", content=req.content),
    )

    # Parse intent
    parser = _get_intent_parser()
    intent = await parser.parse(
        user_message=req.content,
        session_context=(
            {"messages": [m.model_dump() for m in session.messages[-5:]]}
            if session.messages
            else None
        ),
    )

    # Check if clarification needed
    if intent.clarification_needed:
        clarification_msg = (
            f"I need more information. "
            f"Missing: {', '.join(intent.missing_fields)}"
        )
        await memory.append_message(
            session_id,
            Message(role="assistant", content=clarification_msg),
        )
        return SendMessageResponse(
            session_id=session_id,
            status="clarification_needed",
        )

    # Get available tools and create plan
    mcp = _get_mcp_client()
    available_tools = await mcp.list_available_tools()

    planner = _get_planner()
    plan = await planner.create_plan(
        intent=intent,
        session_id=session_id,
        available_tools=available_tools,
    )

    # Set up streaming and executor
    event_store = _get_event_store()
    stream = StreamingOutput(session_id, event_store)
    _streams[session_id] = stream

    settings = get_agent_settings()
    executor = DualLoopExecutor(
        mcp_client=mcp,
        memory=memory,
        planner=planner,
        settings=settings,
    )
    _executors[session_id] = executor

    # Start execution in background
    import asyncio

    asyncio.create_task(
        _run_execution(executor, plan, session_id, stream, memory)
    )

    return SendMessageResponse(
        session_id=session_id,
        status="processing",
    )


@router.post("/sessions/{session_id}/confirm")
async def confirm_step(
    session_id: str,
    req: ConfirmStepRequest,
) -> dict[str, str]:
    """Confirm or reject a step requiring human approval."""
    executor = _executors.get(session_id)
    if executor is None:
        raise HTTPException(
            status_code=404, detail="No active execution"
        )

    await executor.confirm_step(
        session_id=session_id,
        step_id=req.step_id,
        approved=req.approved,
    )
    return {"status": "confirmed" if req.approved else "rejected"}


@router.get("/sessions/{session_id}/stream")
async def stream_events(
    session_id: str,
    last_event_id: int | None = None,
) -> StreamingResponse:
    """SSE stream for real-time Agent execution events."""
    stream = _streams.get(session_id)
    if stream is None:
        # Return empty stream if no active execution
        event_store = _get_event_store()
        stream = StreamingOutput(session_id, event_store)
        _streams[session_id] = stream

    return StreamingResponse(
        stream.stream(last_event_id=last_event_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/sessions/{session_id}/status",
    response_model=SessionStatusResponse,
)
async def get_session_status(
    session_id: str,
) -> SessionStatusResponse:
    """Get current execution status for a session."""
    executor = _executors.get(session_id)
    if executor:
        state = await executor.get_status(session_id)
        if state:
            completed = sum(
                1
                for s in state.step_states.values()
                if s == "completed"
            )
            return SessionStatusResponse(
                session_id=session_id,
                task_status=state.task_status.value,
                step_count=len(state.step_states),
                completed_steps=completed,
                replan_count=state.replan_count,
            )

    # Check memory for persisted state
    memory = _get_memory()
    raw_state = await memory.get_execution_state(session_id)
    if raw_state:
        return SessionStatusResponse(
            session_id=session_id,
            task_status=raw_state.get("task_status", "unknown"),
            step_count=len(raw_state.get("step_states", {})),
            completed_steps=sum(
                1
                for s in raw_state.get("step_states", {}).values()
                if s == "completed"
            ),
            replan_count=raw_state.get("replan_count", 0),
        )

    raise HTTPException(status_code=404, detail="Session not found")


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    user_id: str,
    limit: int = 20,
) -> SessionListResponse:
    """List recent sessions for a user."""
    memory = _get_memory()
    sessions = await memory.list_sessions(user_id, limit=limit)
    return SessionListResponse(sessions=sessions)


# --- Background execution ---


async def _run_execution(
    executor: DualLoopExecutor,
    plan: Any,
    session_id: str,
    stream: StreamingOutput,
    memory: ShortTermMemory,
) -> None:
    """Run plan execution in background task."""
    try:
        async for obs in executor.execute(plan, session_id, stream):
            # Store observation as assistant message
            await memory.append_message(
                session_id,
                Message(
                    role="tool",
                    content=str(obs.output) if obs.output else "",
                    metadata={
                        "step_id": obs.step_id,
                        "status": obs.status.value,
                    },
                ),
            )
    except Exception as e:
        logger.error(
            "execution_failed",
            session_id=session_id,
            error=str(e),
        )
        await stream.emit(
            "error",  # type: ignore[arg-type]
            {"message": str(e), "type": type(e).__name__},
        )
        await stream.close()
    finally:
        # Cleanup
        _executors.pop(session_id, None)
