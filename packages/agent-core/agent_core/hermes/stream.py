"""A-10: SSE streaming output for real-time Agent execution visualization."""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class EventType(StrEnum):
    """SSE event types for Agent execution."""

    PLAN = "plan"
    TOOL_CALL = "tool_call"
    OBSERVATION = "observation"
    CONFIRM_REQUIRED = "confirm_required"
    THINKING = "thinking"
    TASK_COMPLETE = "task_complete"
    ERROR = "error"


class StreamEvent(BaseModel):
    """A single SSE event."""

    event_id: int
    event: EventType
    timestamp: str = Field(
        default_factory=lambda: datetime.now(tz=UTC).isoformat()
    )
    data: dict[str, Any]
    session_id: str


class EventStore:
    """In-memory event store for reconnect replay.

    Keeps last 100 events per session. In production, this would
    be backed by Redis List for multi-instance support.
    """

    def __init__(self, max_events: int = 100) -> None:
        self._events: dict[str, list[StreamEvent]] = defaultdict(list)
        self._max_events = max_events

    async def append(self, event: StreamEvent) -> None:
        """Store event; keep last max_events per session."""
        events = self._events[event.session_id]
        events.append(event)
        if len(events) > self._max_events:
            self._events[event.session_id] = events[
                -self._max_events :
            ]

    async def get_since(
        self,
        session_id: str,
        last_event_id: int,
    ) -> list[StreamEvent]:
        """Return events with event_id > last_event_id."""
        events = self._events.get(session_id, [])
        return [e for e in events if e.event_id > last_event_id]

    async def get_all(self, session_id: str) -> list[StreamEvent]:
        """Return all stored events for a session."""
        return list(self._events.get(session_id, []))

    def clear(self, session_id: str) -> None:
        """Clear events for a session."""
        self._events.pop(session_id, None)


class StreamingOutput:
    """SSE event emitter for Agent execution.

    Manages event_id sequencing, event persistence for replay,
    and broadcasting to connected clients via asyncio.Queue.
    """

    def __init__(
        self,
        session_id: str,
        event_store: EventStore | None = None,
    ) -> None:
        self._session_id = session_id
        self._event_store = event_store or EventStore()
        self._event_counter = 0
        self._subscribers: list[asyncio.Queue[StreamEvent | None]] = []
        self._lock = asyncio.Lock()

    async def emit(
        self, event_type: EventType, data: dict[str, Any]
    ) -> StreamEvent:
        """Emit a streaming event to all connected clients.

        Assigns monotonically increasing event_id, persists to
        EventStore for reconnect replay, and pushes to subscribers.

        Args:
            event_type: Type of event (plan, tool_call, etc.).
            data: Event payload dict.

        Returns:
            The created StreamEvent.
        """
        async with self._lock:
            self._event_counter += 1
            event = StreamEvent(
                event_id=self._event_counter,
                event=event_type,
                data=data,
                session_id=self._session_id,
            )

        await self._event_store.append(event)

        # Broadcast to all subscribers
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "subscriber_queue_full",
                    session_id=self._session_id,
                )

        return event

    def subscribe(self) -> asyncio.Queue[StreamEvent | None]:
        """Create a new subscriber queue.

        Returns:
            Queue that receives StreamEvents. None signals end of stream.
        """
        queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue(
            maxsize=256
        )
        self._subscribers.append(queue)
        return queue

    def unsubscribe(
        self, queue: asyncio.Queue[StreamEvent | None]
    ) -> None:
        """Remove a subscriber queue."""
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    async def close(self) -> None:
        """Signal end of stream to all subscribers."""
        import contextlib

        for queue in self._subscribers:
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(None)
        self._subscribers.clear()

    async def stream(
        self,
        last_event_id: int | None = None,
    ) -> AsyncIterator[str]:
        """Async generator yielding SSE-formatted strings.

        If last_event_id is provided, replays missed events first,
        then continues with live events.

        Yields:
            SSE-formatted strings ready for HTTP response.
        """
        # Replay missed events
        if last_event_id is not None:
            missed = await self._event_store.get_since(
                self._session_id, last_event_id
            )
            for event in missed:
                yield _format_sse(event)

        # Subscribe to live events
        queue = self.subscribe()
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield _format_sse(item)
        finally:
            self.unsubscribe(queue)


def _format_sse(event: StreamEvent) -> str:
    """Format a StreamEvent as SSE wire format."""
    data_json = json.dumps(event.data, ensure_ascii=False)
    return (
        f"id: {event.event_id}\n"
        f"event: {event.event}\n"
        f"data: {data_json}\n\n"
    )
