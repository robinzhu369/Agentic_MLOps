---
id: "A-03"
module: "agent-core"
title: "双循环执行（Outer + Inner Loop）"
priority: P0
status: draft
owner: ""
dependencies: ["A-02", "A-04"]
milestone: "W3"
---

# [A-03] 双循环执行（Outer + Inner Loop）

## 概述

实现 Hermes 风格的双循环执行架构：外循环（Outer Loop）按顺序迭代 Plan 中的 PlanStep，处理步骤间依赖和整体任务状态；内循环（Inner Loop）负责单个步骤的执行与重试，隔离单步失败影响。该架构是 Agent 可靠执行复杂多步 MLOps 任务的核心保障。

## 验收标准

- [ ] AC-1: 外循环按 PlanStep.depends_on 拓扑顺序执行步骤，无依赖的步骤可并发执行（最大并发数可配置，默认 3）
- [ ] AC-2: 内循环在单步失败时自动重试，最大重试次数为 3，重试间隔指数退避（1s, 2s, 4s）
- [ ] AC-3: 单步连续失败超过重试上限后，外循环触发 Planner.replan()，最多重规划 2 次；重规划仍失败则整体任务标记为 FAILED
- [ ] AC-4: 遇到 PlanStep.requires_confirm=True 的步骤时，外循环暂停并通过 SSE 推送 `event: confirm_required`，等待 `POST /api/v1/agent/sessions/{id}/confirm` 响应后继续
- [ ] AC-5: 每个步骤执行结果（Observation）通过 SSE 推送 `event: observation`，包含 step_id、status、output 字段
- [ ] AC-6: 任务整体状态（RUNNING/PAUSED/COMPLETED/FAILED）可通过会话查询接口获取

## 接口定义

```python
from enum import Enum
from typing import Any, AsyncIterator
from pydantic import BaseModel


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING_CONFIRM = "waiting_confirm"


class TaskStatus(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class Observation(BaseModel):
    step_id: str
    status: StepStatus
    output: Any                           # Tool call result from A-04
    error: str | None = None
    retry_count: int = 0
    duration_ms: int | None = None


class ExecutionState(BaseModel):
    session_id: str
    plan_id: str
    task_status: TaskStatus
    step_states: dict[str, StepStatus]
    observations: list[Observation]
    replan_count: int = 0


class DualLoopExecutor:
    async def execute(
        self,
        plan: "Plan",
        session_id: str,
    ) -> AsyncIterator[dict]:
        """
        Execute a Plan using dual-loop architecture.

        Yields SSE-compatible event dicts:
          {"event": "observation", "data": Observation.model_dump_json()}
          {"event": "confirm_required", "data": {"step_id": ..., "description": ...}}
          {"event": "task_complete", "data": {"status": "completed"|"failed"}}

        Args:
            plan: Plan from A-02 Planner.
            session_id: Current session for state persistence (A-05).

        Raises:
            ExecutionError: Unrecoverable error after all replanning attempts.
        """
        ...

    async def confirm_step(
        self,
        session_id: str,
        step_id: str,
        approved: bool,
    ) -> None:
        """
        Resume execution after human confirmation.
        Called by POST /api/v1/agent/sessions/{id}/confirm handler.
        """
        ...
```

## 技术约束

- 外循环和内循环均以 LangGraph 节点实现，状态存储于 `AgentState`，通过 A-05 Redis 持久化
- 并发步骤执行使用 `asyncio.gather`，不使用线程池
- 所有工具调用必须通过 A-04（MCP Gateway 客户端），禁止直接调用工具
- 重规划计数 `replan_count` 存入会话状态，防止无限循环
- confirm 等待超时为 30 分钟，超时后步骤标记为 SKIPPED 并继续执行

## 测试策略

- 单元测试：mock A-04 工具调用，验证重试退避逻辑；测试 depends_on 拓扑排序；测试 confirm 暂停/恢复流程；测试重规划触发条件
- 集成测试：与 A-02、A-04 联调，执行包含 3+ 步骤的真实计划；验证并发步骤执行正确性
- E2E：完整任务从用户消息到 `event: task_complete` 的全链路测试，验证所有 SSE 事件顺序正确

## 依赖关系

- 被阻塞：[A-02, A-04]
- 阻塞：[A-08, A-10]

## 参考

- MVP_SPEC.md Section 3.1
