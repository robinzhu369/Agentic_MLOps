"""A-05: Redis-based short-term session memory."""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis
import structlog
from pydantic import BaseModel, Field

from .config import AgentCoreSettings, get_agent_settings

logger = structlog.get_logger(__name__)

SESSION_TTL = 86400  # 24 hours
MAX_MESSAGES = 100


# --- Models ---


class Message(BaseModel):
    """A single message in session history."""

    role: str  # "user" | "assistant" | "tool"
    content: str
    timestamp: str = Field(
        default_factory=lambda: datetime.now(tz=UTC).isoformat()
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionMemory(BaseModel):
    """Full session state stored in Redis."""

    session_id: str
    user_id: str
    messages: list[Message] = Field(default_factory=list)
    variables: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(
        default_factory=lambda: datetime.now(tz=UTC).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(tz=UTC).isoformat()
    )


# --- Short-term Memory ---


class ShortTermMemory:
    """Redis-backed session-level short-term memory.

    Stores message history, execution state, and intermediate variables.
    All operations are atomic using Redis transactions.
    TTL is 24 hours, reset on every write.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        settings: AgentCoreSettings | None = None,
    ) -> None:
        settings = settings or get_agent_settings()
        url = redis_url or "redis://localhost:6379/0"
        self._redis: aioredis.Redis = aioredis.from_url(
            url, decode_responses=True
        )

    def _key(self, session_id: str, suffix: str) -> str:
        """Build Redis key for a session component."""
        return f"session:{session_id}:{suffix}"

    async def create_session(
        self,
        user_id: str,
        initial_context: dict[str, Any] | None = None,
    ) -> str:
        """Create a new session and return session_id.

        Args:
            user_id: Owner of the session.
            initial_context: Optional initial variables.

        Returns:
            Generated session_id string.
        """
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        now = datetime.now(tz=UTC).isoformat()

        meta = {
            "session_id": session_id,
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
        }

        pipe = self._redis.pipeline()
        pipe.hset(self._key(session_id, "meta"), mapping=meta)
        pipe.expire(self._key(session_id, "meta"), SESSION_TTL)

        if initial_context:
            pipe.hset(
                self._key(session_id, "vars"),
                mapping={
                    k: json.dumps(v, ensure_ascii=False)
                    for k, v in initial_context.items()
                },
            )
            pipe.expire(self._key(session_id, "vars"), SESSION_TTL)

        # Track session in user's session list
        pipe.zadd(
            f"user:{user_id}:sessions",
            {session_id: datetime.now(tz=UTC).timestamp()},
        )

        await pipe.execute()

        logger.info(
            "session_created",
            session_id=session_id,
            user_id=user_id,
        )
        return session_id

    async def get_session(
        self, session_id: str
    ) -> SessionMemory | None:
        """Retrieve full session memory.

        Returns:
            SessionMemory or None if not found/expired.
        """
        meta = await self._redis.hgetall(  # type: ignore[misc]
            self._key(session_id, "meta")
        )
        if not meta:
            return None

        # Get messages
        raw_messages = await self._redis.lrange(  # type: ignore[misc]
            self._key(session_id, "messages"), 0, -1
        )
        messages = [
            Message.model_validate_json(m) for m in raw_messages
        ]

        # Get variables
        raw_vars = await self._redis.hgetall(  # type: ignore[misc]
            self._key(session_id, "vars")
        )
        variables = {
            k: json.loads(v) for k, v in raw_vars.items()
        }

        return SessionMemory(
            session_id=meta["session_id"],
            user_id=meta["user_id"],
            messages=messages,
            variables=variables,
            created_at=meta["created_at"],
            updated_at=meta["updated_at"],
        )

    async def append_message(
        self,
        session_id: str,
        message: Message,
    ) -> None:
        """Atomically append a message to session history.

        Maintains max 100 messages (LTRIM). Resets TTL.
        """
        pipe = self._redis.pipeline()
        msg_key = self._key(session_id, "messages")

        pipe.rpush(msg_key, message.model_dump_json())
        pipe.ltrim(msg_key, -MAX_MESSAGES, -1)
        pipe.expire(msg_key, SESSION_TTL)

        # Update timestamp
        pipe.hset(
            self._key(session_id, "meta"),
            "updated_at",
            datetime.now(tz=UTC).isoformat(),
        )
        pipe.expire(self._key(session_id, "meta"), SESSION_TTL)

        await pipe.execute()

    async def set_variable(
        self,
        session_id: str,
        key: str,
        value: Any,
    ) -> None:
        """Store an intermediate variable in session scope."""
        pipe = self._redis.pipeline()
        var_key = self._key(session_id, "vars")

        pipe.hset(var_key, key, json.dumps(value, ensure_ascii=False))
        pipe.expire(var_key, SESSION_TTL)
        pipe.hset(
            self._key(session_id, "meta"),
            "updated_at",
            datetime.now(tz=UTC).isoformat(),
        )

        await pipe.execute()

    async def get_variable(
        self,
        session_id: str,
        key: str,
    ) -> Any | None:
        """Retrieve a session-scoped variable."""
        raw = await self._redis.hget(  # type: ignore[misc]
            self._key(session_id, "vars"), key
        )
        if raw is None:
            return None
        return json.loads(raw)

    async def save_execution_state(
        self,
        session_id: str,
        state: dict[str, Any],
    ) -> None:
        """Persist execution state for recovery."""
        pipe = self._redis.pipeline()
        state_key = self._key(session_id, "exec_state")

        pipe.set(state_key, json.dumps(state, ensure_ascii=False))
        pipe.expire(state_key, SESSION_TTL)

        await pipe.execute()

    async def get_execution_state(
        self,
        session_id: str,
    ) -> dict[str, Any] | None:
        """Retrieve persisted execution state."""
        raw = await self._redis.get(
            self._key(session_id, "exec_state")
        )
        if raw is None:
            return None
        return json.loads(raw)  # type: ignore[no-any-return]

    async def list_sessions(
        self,
        user_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return recent session summaries for a user.

        Args:
            user_id: Filter sessions by this user.
            limit: Max sessions to return (default 20).

        Returns:
            List of session summary dicts (session_id, created_at, updated_at).
        """
        session_ids = await self._redis.zrevrange(
            f"user:{user_id}:sessions", 0, limit - 1
        )

        sessions: list[dict[str, Any]] = []
        for sid in session_ids:
            meta = await self._redis.hgetall(  # type: ignore[misc]
                self._key(sid, "meta")
            )
            if meta:
                sessions.append(meta)

        return sessions

    async def delete_session(self, session_id: str) -> None:
        """Explicitly delete a session and all its data."""
        meta = await self._redis.hgetall(  # type: ignore[misc]
            self._key(session_id, "meta")
        )

        pipe = self._redis.pipeline()
        pipe.delete(
            self._key(session_id, "meta"),
            self._key(session_id, "messages"),
            self._key(session_id, "vars"),
            self._key(session_id, "exec_state"),
        )

        if meta and "user_id" in meta:
            pipe.zrem(
                f"user:{meta['user_id']}:sessions", session_id
            )

        await pipe.execute()
        logger.info("session_deleted", session_id=session_id)

    async def close(self) -> None:
        """Close Redis connection."""
        await self._redis.aclose()
