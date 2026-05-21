"""A-03: Dual-loop executor — outer loop + inner loop with retry/replan."""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import AsyncIterator
from enum import StrEnum
from typing import Any

import structlog
from pydantic import BaseModel, Field

from .config import AgentCoreSettings, get_agent_settings
from .mcp_client import MCPClient, MCPError, MCPGatewayError
from .memory import ShortTermMemory
from .planner import Planner
from .schemas import Plan, PlanStep
from .stream import EventType, StreamingOutput

logger = structlog.get_logger(__name__)


# --- Enums & Models ---


class StepStatus(StrEnum):
    """Status of a single plan step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING_CONFIRM = "waiting_confirm"


class TaskStatus(StrEnum):
    """Overall task execution status."""

    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class Observation(BaseModel):
    """Result of executing a single plan step."""

    step_id: str
    status: StepStatus
    output: Any = None
    error: str | None = None
    retry_count: int = 0
    duration_ms: int | None = None


class ExecutionState(BaseModel):
    """Persisted execution state for a session."""

    session_id: str
    plan_id: str
    task_status: TaskStatus = TaskStatus.RUNNING
    step_states: dict[str, StepStatus] = Field(default_factory=dict)
    observations: list[Observation] = Field(default_factory=list)
    replan_count: int = 0


# --- Executor ---


CONFIRM_TIMEOUT_S = 1800  # 30 minutes


class DualLoopExecutor:
    """Hermes-style dual-loop execution engine.

    Outer loop: iterates Plan steps in topological order,
    handles dependencies and overall task state.

    Inner loop: executes a single step with retry logic
    (exponential backoff: 1s, 2s, 4s).
    """

    def __init__(
        self,
        mcp_client: MCPClient,
        memory: ShortTermMemory,
        planner: Planner,
        settings: AgentCoreSettings | None = None,
    ) -> None:
        self._mcp = mcp_client
        self._memory = memory
        self._planner = planner
        self._settings = settings or get_agent_settings()
        self._confirm_events: dict[
            str, asyncio.Event
        ] = defaultdict(asyncio.Event)
        self._confirm_results: dict[str, bool] = {}

    async def execute(
        self,
        plan: Plan,
        session_id: str,
        stream: StreamingOutput,
    ) -> AsyncIterator[Observation]:
        """Execute a Plan using dual-loop architecture.

        Args:
            plan: Plan from A-02 Planner.
            session_id: Current session for state persistence.
            stream: SSE emitter for real-time events.

        Yields:
            Observation for each completed step.
        """
        log = logger.bind(
            session_id=session_id, plan_id=plan.plan_id
        )
        log.info("execution_start", step_count=len(plan.steps))

        state = ExecutionState(
            session_id=session_id,
            plan_id=plan.plan_id,
            step_states={
                s.step_id: StepStatus.PENDING for s in plan.steps
            },
        )

        # Emit plan event
        await stream.emit(
            EventType.PLAN,
            {
                "plan_id": plan.plan_id,
                "steps": [s.model_dump() for s in plan.steps],
            },
        )

        current_plan = plan
        replan_count = 0

        while True:
            try:
                async for obs in self._outer_loop(
                    current_plan, state, stream, log
                ):
                    yield obs

                # All steps completed successfully
                state.task_status = TaskStatus.COMPLETED
                break

            except _ReplanNeeded as e:
                replan_count += 1
                if replan_count > self._settings.max_replans:
                    state.task_status = TaskStatus.FAILED
                    await stream.emit(
                        EventType.ERROR,
                        {
                            "message": (
                                "Max replans exceeded"
                            ),
                            "failed_step": e.step_id,
                        },
                    )
                    break

                log.info(
                    "replanning",
                    attempt=replan_count,
                    failed_step=e.step_id,
                )
                state.replan_count = replan_count

                current_plan = await self._planner.replan(
                    original_plan=current_plan,
                    failed_step_id=e.step_id,
                    error_context=e.error,
                )

                # Reset step states for new plan
                state.step_states = {
                    s.step_id: StepStatus.PENDING
                    for s in current_plan.steps
                }
                state.plan_id = current_plan.plan_id

                await stream.emit(
                    EventType.PLAN,
                    {
                        "plan_id": current_plan.plan_id,
                        "steps": [
                            s.model_dump()
                            for s in current_plan.steps
                        ],
                        "is_replan": True,
                        "replan_count": replan_count,
                    },
                )

        # Emit completion event
        total_duration = sum(
            o.duration_ms or 0 for o in state.observations
        )
        await stream.emit(
            EventType.TASK_COMPLETE,
            {
                "status": state.task_status.value,
                "summary": (
                    f"Executed {len(state.observations)} steps"
                ),
                "total_steps": len(state.observations),
                "duration_ms": total_duration,
            },
        )

        # Persist final state
        await self._memory.save_execution_state(
            session_id, state.model_dump()
        )

        await stream.close()
        log.info(
            "execution_complete",
            status=state.task_status,
            steps_executed=len(state.observations),
        )

    async def confirm_step(
        self,
        session_id: str,
        step_id: str,
        approved: bool,
    ) -> None:
        """Resume execution after human confirmation.

        Args:
            session_id: Session containing the paused step.
            step_id: Step awaiting confirmation.
            approved: Whether the user approved the step.
        """
        key = f"{session_id}:{step_id}"
        self._confirm_results[key] = approved
        event = self._confirm_events.get(key)
        if event:
            event.set()

    async def get_status(
        self, session_id: str
    ) -> ExecutionState | None:
        """Get current execution state for a session."""
        raw = await self._memory.get_execution_state(session_id)
        if raw is None:
            return None
        return ExecutionState.model_validate(raw)

    # --- Internal ---

    async def _outer_loop(
        self,
        plan: Plan,
        state: ExecutionState,
        stream: StreamingOutput,
        log: Any,
    ) -> AsyncIterator[Observation]:
        """Outer loop: execute steps in topological order."""
        steps_by_id = {s.step_id: s for s in plan.steps}
        completed: set[str] = set()

        # Build dependency graph
        dependents: dict[str, set[str]] = defaultdict(set)
        for step in plan.steps:
            for dep in step.depends_on:
                dependents[dep].add(step.step_id)

        # Find initial ready steps (no dependencies)
        ready: list[str] = [
            s.step_id
            for s in plan.steps
            if not s.depends_on
        ]

        max_concurrent = 3

        while ready or (
            len(completed) < len(plan.steps)
            and state.task_status == TaskStatus.RUNNING
        ):
            if not ready:
                # Check if we're stuck (all remaining have unmet deps)
                remaining = set(steps_by_id.keys()) - completed
                if remaining:
                    # Deadlock or all remaining steps failed
                    break
                break

            # Execute batch of ready steps (up to max_concurrent)
            batch = ready[:max_concurrent]
            ready = ready[max_concurrent:]

            tasks = [
                self._execute_step(
                    steps_by_id[sid], state, stream, log
                )
                for sid in batch
            ]
            results = await asyncio.gather(
                *tasks, return_exceptions=True
            )

            for sid, result in zip(batch, results, strict=True):
                if isinstance(result, _ReplanNeeded):
                    raise result
                if isinstance(result, BaseException):
                    state.task_status = TaskStatus.FAILED
                    raise result

                obs: Observation = result
                state.observations.append(obs)
                yield obs

                if obs.status == StepStatus.COMPLETED:
                    completed.add(sid)
                    # Unlock dependent steps
                    for dep_id in dependents.get(sid, set()):
                        step = steps_by_id[dep_id]
                        if all(
                            d in completed
                            for d in step.depends_on
                        ):
                            ready.append(dep_id)
                elif obs.status == StepStatus.SKIPPED:
                    completed.add(sid)

            # Persist intermediate state
            await self._memory.save_execution_state(
                state.session_id, state.model_dump()
            )

    async def _execute_step(
        self,
        step: PlanStep,
        state: ExecutionState,
        stream: StreamingOutput,
        log: Any,
    ) -> Observation:
        """Inner loop: execute a single step with retry."""
        step_log = log.bind(step_id=step.step_id)

        # Handle HITL confirmation
        if step.requires_confirm:
            state.step_states[step.step_id] = (
                StepStatus.WAITING_CONFIRM
            )
            state.task_status = TaskStatus.PAUSED

            await stream.emit(
                EventType.CONFIRM_REQUIRED,
                {
                    "step_id": step.step_id,
                    "description": step.description,
                    "tool_name": step.tool_name,
                    "tool_args": step.tool_args,
                },
            )

            approved = await self._wait_for_confirm(
                state.session_id, step.step_id
            )

            state.task_status = TaskStatus.RUNNING

            if not approved:
                state.step_states[step.step_id] = (
                    StepStatus.SKIPPED
                )
                step_log.info("step_skipped_by_user")
                return Observation(
                    step_id=step.step_id,
                    status=StepStatus.SKIPPED,
                    output=None,
                    error="Rejected by user",
                )

        # Execute with retry
        state.step_states[step.step_id] = StepStatus.RUNNING
        max_retries = self._settings.max_retries_per_step
        last_error: str | None = None

        for attempt in range(max_retries + 1):
            start = time.time()

            await stream.emit(
                EventType.TOOL_CALL,
                {
                    "step_id": step.step_id,
                    "tool_name": step.tool_name,
                    "tool_args": step.tool_args,
                    "attempt": attempt,
                },
            )

            try:
                result = await self._mcp.call_tool(
                    tool_name=step.tool_name,
                    arguments=step.tool_args,
                    session_id=state.session_id,
                )
                duration_ms = int((time.time() - start) * 1000)

                # Check if tool returned an error
                if result.get("is_error"):
                    last_error = result.get(
                        "error_message", "Tool returned error"
                    )
                    raise MCPError(last_error)

                obs = Observation(
                    step_id=step.step_id,
                    status=StepStatus.COMPLETED,
                    output=result.get("content"),
                    retry_count=attempt,
                    duration_ms=duration_ms,
                )

                state.step_states[step.step_id] = (
                    StepStatus.COMPLETED
                )

                await stream.emit(
                    EventType.OBSERVATION,
                    {
                        "step_id": step.step_id,
                        "status": StepStatus.COMPLETED.value,
                        "output": result.get("content"),
                        "duration_ms": duration_ms,
                    },
                )

                step_log.info(
                    "step_completed",
                    attempt=attempt,
                    duration_ms=duration_ms,
                )
                return obs

            except MCPGatewayError as e:
                last_error = str(e)
                step_log.warning(
                    "step_retry",
                    attempt=attempt,
                    error=last_error,
                )
                if attempt < max_retries:
                    backoff = 2**attempt  # 1s, 2s, 4s
                    await asyncio.sleep(backoff)
                continue

            except MCPError as e:
                last_error = str(e)
                # Non-retryable client errors
                if not isinstance(e, MCPGatewayError):
                    step_log.warning(
                        "step_retry",
                        attempt=attempt,
                        error=last_error,
                    )
                    if attempt < max_retries:
                        backoff = 2**attempt
                        await asyncio.sleep(backoff)
                    continue

        # All retries exhausted — trigger replan
        duration_ms = int((time.time() - start) * 1000)
        state.step_states[step.step_id] = StepStatus.FAILED

        await stream.emit(
            EventType.OBSERVATION,
            {
                "step_id": step.step_id,
                "status": StepStatus.FAILED.value,
                "error": last_error,
                "duration_ms": duration_ms,
            },
        )

        step_log.error(
            "step_failed_all_retries",
            error=last_error,
        )
        raise _ReplanNeeded(step.step_id, last_error or "Unknown")

    async def _wait_for_confirm(
        self, session_id: str, step_id: str
    ) -> bool:
        """Wait for human confirmation with timeout."""
        key = f"{session_id}:{step_id}"
        event = asyncio.Event()
        self._confirm_events[key] = event

        try:
            await asyncio.wait_for(
                event.wait(), timeout=CONFIRM_TIMEOUT_S
            )
            return self._confirm_results.get(key, False)
        except TimeoutError:
            logger.warning(
                "confirm_timeout",
                session_id=session_id,
                step_id=step_id,
            )
            return False
        finally:
            self._confirm_events.pop(key, None)
            self._confirm_results.pop(key, None)


class _ReplanNeeded(Exception):
    """Internal signal that replanning is needed."""

    def __init__(self, step_id: str, error: str) -> None:
        super().__init__(f"Replan needed: step {step_id}")
        self.step_id = step_id
        self.error = error
