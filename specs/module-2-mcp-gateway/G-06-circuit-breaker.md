---
id: "G-06"
module: "mcp-gateway"
title: "调用熔断"
priority: P1
status: draft
owner: ""
dependencies: ["G-04"]
milestone: "W2"
---

# [G-06] 调用熔断

## 概述

在单个会话维度实现熔断机制：当某会话在 1 分钟内工具调用失败次数超过 10 次时，该会话进入只读模式，只允许调用数据查询类工具，拒绝写入和执行类操作。熔断保护防止故障级联扩散，避免 Agent 在异常状态下持续执行破坏性操作。

## 验收标准

- [ ] AC-1: 单个会话在滑动 1 分钟窗口内失败次数 > 10 时，触发熔断，后续写入/执行类工具调用返回 HTTP 429，响应体包含 `{"error": "circuit_open", "session_id": "...", "reset_at": "ISO8601"}`
- [ ] AC-2: 熔断状态下，只读工具（list_*、get_*、sample_*、profile_*）仍可正常调用
- [ ] AC-3: 熔断自动在 5 分钟后重置（半开状态），重置后允许 1 次试探性调用，成功则完全恢复，失败则重新熔断
- [ ] AC-4: 熔断状态变更（open/half-open/closed）记录到审计日志（G-05），status 字段为 `circuit_open`
- [ ] AC-5: 熔断计数器和状态存储于 Redis，多实例部署时状态共享

## 接口定义

```python
from enum import Enum
from pydantic import BaseModel
from datetime import datetime


class CircuitState(str, Enum):
    CLOSED = "closed"                    # Normal operation
    OPEN = "open"                        # Blocking write/execute calls
    HALF_OPEN = "half_open"              # Allowing one probe call


class CircuitStatus(BaseModel):
    session_id: str
    state: CircuitState
    failure_count: int
    window_start: datetime
    reset_at: datetime | None = None     # Set when state is OPEN


# Read-only tool name patterns (allowed when circuit is OPEN):
READ_ONLY_PATTERNS = [
    "list_*",
    "get_*",
    "sample_*",
    "profile_*",
    "describe_*",
]


class CircuitBreaker:
    def __init__(
        self,
        redis_client,
        failure_threshold: int = 10,
        window_seconds: int = 60,
        reset_seconds: int = 300,
    ):
        ...

    async def check(
        self,
        session_id: str,
        tool_name: str,
    ) -> None:
        """
        Check if the call is allowed given current circuit state.

        Raises:
            CircuitOpenError: Circuit is OPEN and tool is not read-only.
        """
        ...

    async def record_failure(
        self,
        session_id: str,
        tool_name: str,
    ) -> CircuitStatus:
        """
        Increment failure counter for session.
        Transitions to OPEN if threshold exceeded.
        Returns updated CircuitStatus.
        """
        ...

    async def record_success(
        self,
        session_id: str,
    ) -> CircuitStatus:
        """
        Record successful call.
        If in HALF_OPEN state, transitions to CLOSED.
        """
        ...

    async def get_status(self, session_id: str) -> CircuitStatus:
        """Return current circuit status for a session."""
        ...

    def _is_read_only(self, tool_name: str) -> bool:
        """Check if tool matches read-only patterns."""
        ...
```

## 技术约束

- 失败计数使用 Redis Sorted Set，Key：`circuit:{session_id}:failures`，Score 为 Unix 时间戳，Value 为 trace_id
- 滑动窗口通过 `ZREMRANGEBYSCORE` 清除 1 分钟前的记录，`ZCARD` 获取当前计数
- 熔断状态 Key：`circuit:{session_id}:state`，TTL 与 reset_seconds 一致
- 只读工具判断基于 tool_name 的方法名部分（`.` 后的部分），使用 fnmatch 模式匹配
- 熔断阈值（10次/分钟）和重置时间（5分钟）通过环境变量可配置

## 测试策略

- 单元测试：mock Redis，验证滑动窗口计数逻辑；测试 OPEN 状态下只读工具通过、写入工具被拒绝；测试 HALF_OPEN 状态的试探性调用逻辑；测试自动重置
- 集成测试：与 G-04 联调，模拟连续失败触发熔断；验证熔断状态记录到审计日志
- E2E：在测试环境中模拟 MCP Server 连续返回错误，验证熔断触发和自动恢复

## 依赖关系

- 被阻塞：[G-04]
- 阻塞：[]

## 参考

- MVP_SPEC.md Section 3.2
