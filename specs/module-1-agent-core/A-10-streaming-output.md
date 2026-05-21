---
id: "A-10"
module: "agent-core"
title: "思考链可视化输出"
priority: P0
status: done
owner: ""
dependencies: ["A-03"]
milestone: "W3"
---

# [A-10] 思考链可视化输出

## 概述

通过 Server-Sent Events（SSE）将 Agent 的思考过程实时推送给客户端，包括规划步骤、工具调用、观察结果和任务状态变更。可视化输出使用户能够实时了解 Agent 执行进度，并在需要确认时及时响应，是 Web IDE 前端（Module 4）的数据来源。

## 验收标准

- [ ] AC-1: WebSocket 连接建立后，Agent 执行期间的所有关键事件必须在 500ms 内推送到客户端
- [ ] AC-2: SSE 事件类型覆盖：`plan`、`tool_call`、`observation`、`confirm_required`、`thinking`、`task_complete`、`error`
- [ ] AC-3: 每个 SSE 事件包含 `event_id`（单调递增）、`timestamp`、`event` 类型和 `data` JSON 字段
- [ ] AC-4: 客户端断线重连后，通过 `Last-Event-ID` 请求头可从断点续传，补发最多 100 条历史事件
- [ ] AC-5: `WS /api/v1/agent/sessions/{id}/stream` 端点支持 WebSocket 和 SSE 两种协议，由客户端 Accept 头决定

## 接口定义

```python
from enum import Enum
from typing import Any, AsyncIterator
from pydantic import BaseModel
from datetime import datetime


class EventType(str, Enum):
    PLAN = "plan"
    TOOL_CALL = "tool_call"
    OBSERVATION = "observation"
    CONFIRM_REQUIRED = "confirm_required"
    THINKING = "thinking"
    TASK_COMPLETE = "task_complete"
    ERROR = "error"


class StreamEvent(BaseModel):
    event_id: int                         # Monotonically increasing per session
    event: EventType
    timestamp: datetime
    data: dict[str, Any]
    session_id: str


# SSE wire format per event:
# id: {event_id}
# event: {event_type}
# data: {json_encoded_data}
# (blank line)

# Event data schemas:
PLAN_DATA = {
    "plan_id": "str",
    "steps": "list[PlanStep.model_dump()]",
}

TOOL_CALL_DATA = {
    "step_id": "str",
    "tool_name": "str",
    "tool_args": "dict",
}

OBSERVATION_DATA = {
    "step_id": "str",
    "status": "StepStatus",
    "output": "Any",
    "error": "str | None",
    "duration_ms": "int | None",
}

CONFIRM_REQUIRED_DATA = {
    "step_id": "str",
    "description": "str",
    "tool_name": "str",
    "tool_args": "dict",
}

TASK_COMPLETE_DATA = {
    "status": "completed | failed",
    "summary": "str",
    "total_steps": "int",
    "duration_ms": "int",
}


class StreamingOutput:
    def __init__(self, session_id: str, event_store: "EventStore"):
        ...

    async def emit(self, event_type: EventType, data: dict) -> StreamEvent:
        """
        Emit a streaming event to all connected clients for this session.

        Assigns monotonically increasing event_id, persists to EventStore
        for reconnect replay, and pushes to active SSE/WebSocket connections.
        """
        ...

    async def stream(
        self,
        session_id: str,
        last_event_id: int | None = None,
    ) -> AsyncIterator[str]:
        """
        Async generator yielding SSE-formatted strings.

        If last_event_id is provided, replays missed events first,
        then continues with live events.
        """
        ...


class EventStore:
    """Persists recent events in Redis for reconnect replay."""

    async def append(self, event: StreamEvent) -> None:
        """Store event; keep last 100 per session."""
        ...

    async def get_since(
        self,
        session_id: str,
        last_event_id: int,
    ) -> list[StreamEvent]:
        """Return events with event_id > last_event_id."""
        ...
```

## 技术约束

- SSE 端点使用 FastAPI `StreamingResponse`，Content-Type: `text/event-stream`
- WebSocket 端点使用 FastAPI WebSocket，消息格式与 SSE data 字段相同（JSON）
- 事件持久化使用 Redis List，Key 格式：`session:{id}:events`，最大保留 100 条
- 事件推送使用 Redis Pub/Sub，多实例部署时所有实例订阅同一 channel
- `thinking` 事件用于推送 LLM 中间思考文本（如有），内容长度限制 1000 字符

## 测试策略

- 单元测试：验证 SSE 格式化输出（id/event/data 字段）；测试 event_id 单调递增；测试 EventStore 的 100 条上限截断
- 集成测试：模拟客户端连接 SSE 端点，验证执行期间所有事件类型均被接收；测试断线重连后的事件补发
- E2E：前端 Web IDE 连接 SSE 流，验证规划和执行过程的实时可视化

## 依赖关系

- 被阻塞：[A-03]
- 阻塞：[]

## 参考

- MVP_SPEC.md Section 3.1
