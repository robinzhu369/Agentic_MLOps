---
id: "A-05"
module: "agent-core"
title: "短期记忆（会话内）"
priority: P0
status: draft
owner: ""
dependencies: []
milestone: "W3"
---

# [A-05] 短期记忆（会话内）

## 概述

基于 Redis 实现会话级短期记忆，存储当前会话的消息历史、执行状态和中间变量。短期记忆为 A-01 意图解析提供上下文消歧能力，为 A-03 执行器提供状态持久化，确保会话在服务重启后可恢复。

## 验收标准

- [ ] AC-1: 会话消息历史写入 Redis，TTL 为 24 小时，超时自动清理
- [ ] AC-2: 同一会话的并发读写操作保证原子性，使用 Redis 事务（MULTI/EXEC）
- [ ] AC-3: 单次读取会话完整历史（最多 100 条消息）延迟 ≤ 50ms（P99）
- [ ] AC-4: 会话状态（ExecutionState）序列化为 JSON 存储，支持完整反序列化恢复
- [ ] AC-5: 提供会话列表查询接口，支持按 user_id 过滤，返回最近 20 个会话摘要

## 接口定义

```python
from typing import Any
from pydantic import BaseModel
from datetime import datetime


class Message(BaseModel):
    role: str                             # "user" | "assistant" | "tool"
    content: str
    timestamp: datetime
    metadata: dict[str, Any] = {}


class SessionMemory(BaseModel):
    session_id: str
    user_id: str
    messages: list[Message]
    variables: dict[str, Any]            # Intermediate results, e.g. {"dataset_path": "..."}
    created_at: datetime
    updated_at: datetime


class ShortTermMemory:
    def __init__(self, redis_url: str):
        ...

    async def create_session(
        self,
        user_id: str,
        initial_context: dict | None = None,
    ) -> str:
        """Create a new session and return session_id."""
        ...

    async def get_session(self, session_id: str) -> SessionMemory | None:
        """Retrieve full session memory. Returns None if not found or expired."""
        ...

    async def append_message(
        self,
        session_id: str,
        message: Message,
    ) -> None:
        """Atomically append a message to session history."""
        ...

    async def set_variable(
        self,
        session_id: str,
        key: str,
        value: Any,
    ) -> None:
        """Store an intermediate variable in session scope."""
        ...

    async def get_variable(
        self,
        session_id: str,
        key: str,
    ) -> Any | None:
        """Retrieve a session-scoped variable."""
        ...

    async def list_sessions(
        self,
        user_id: str,
        limit: int = 20,
    ) -> list[dict]:
        """Return recent session summaries for a user."""
        ...

    async def delete_session(self, session_id: str) -> None:
        """Explicitly delete a session (e.g., on user logout)."""
        ...
```

## 技术约束

- 使用 `redis.asyncio` 客户端，连接池大小默认 20，可通过 `REDIS_POOL_SIZE` 配置
- 会话 Key 格式：`session:{session_id}:memory`，消息列表使用 Redis List，变量使用 Redis Hash
- TTL 统一为 86400 秒（24 小时），每次写操作重置 TTL
- 消息列表最大长度 100 条，超出时自动 LTRIM 保留最新 100 条
- 禁止在 Redis 中存储明文密码或 JWT Token

## 测试策略

- 单元测试：使用 `fakeredis` mock Redis，验证 TTL 设置、LTRIM 截断、并发写入原子性
- 集成测试：连接真实 Redis 实例，验证会话创建→消息追加→状态恢复完整流程；测试 TTL 过期后 get_session 返回 None
- E2E：验证服务重启后会话状态可从 Redis 恢复，Agent 继续执行未完成任务

## 依赖关系

- 被阻塞：[]
- 阻塞：[A-06]

## 参考

- MVP_SPEC.md Section 3.1
