---
id: "A-02"
module: "agent-core"
title: "多步任务规划（Planner）"
priority: P0
status: draft
owner: ""
dependencies: ["A-01"]
milestone: "W3"
---

# [A-02] 多步任务规划（Planner）

## 概述

基于 A-01 解析的意图，将复杂 MLOps 任务分解为有序的 PlanStep 列表。Planner 作为 LangGraph 节点运行，输出 JSON 格式的执行计划，供 A-03 双循环执行器逐步执行。规划质量直接影响任务成功率，是 Agent 智能的核心体现。

## 验收标准

- [ ] AC-1: 给定 IntentResult，Planner 在 5 秒内输出包含至少 1 个 PlanStep 的有效 Plan 对象
- [ ] AC-2: 每个 PlanStep 必须包含 step_id、tool_name、tool_args、depends_on、description 字段，且 tool_name 必须存在于当前 MCP Capability Manifest 中
- [ ] AC-3: 对于需要人工确认的高风险步骤（如删除数据、部署到生产），PlanStep.requires_confirm 必须为 True
- [ ] AC-4: 当 Skill Library（A-07）返回匹配 Skill 时，Planner 优先复用 Skill 步骤而非重新规划
- [ ] AC-5: 规划结果通过 SSE 以 `event: plan` 类型推送给客户端（A-10）

## 接口定义

```python
from pydantic import BaseModel, Field
from typing import Any


class PlanStep(BaseModel):
    step_id: str                          # e.g. "step_1"
    tool_name: str                        # MCP tool identifier, e.g. "jupyter.execute_code"
    tool_args: dict[str, Any]             # Arguments passed to the tool
    depends_on: list[str] = Field(default_factory=list)  # step_ids this step waits for
    description: str                      # Human-readable description for UI
    requires_confirm: bool = False        # True for destructive/production operations
    estimated_duration_s: int | None = None


class Plan(BaseModel):
    plan_id: str
    session_id: str
    steps: list[PlanStep]
    created_at: str                       # ISO 8601
    skill_id: str | None = None           # Set if plan was derived from a Skill


class Planner:
    async def create_plan(
        self,
        intent: "IntentResult",
        session_id: str,
        available_tools: list[str],
        skill_hint: "Skill | None" = None,
    ) -> Plan:
        """
        Decompose an intent into an ordered list of PlanSteps.

        Args:
            intent: Structured intent from A-01 IntentParser.
            session_id: Current session identifier.
            available_tools: Tool names from MCP Capability Manifest (G-01).
            skill_hint: Optional matching Skill from A-07 for plan reuse.

        Returns:
            Plan with ordered PlanStep list.

        Raises:
            PlanningError: If LLM fails to produce a valid plan after 2 retries.
            UnknownToolError: If planned tool_name is not in available_tools.
        """
        ...

    async def replan(
        self,
        original_plan: Plan,
        failed_step_id: str,
        error_context: str,
    ) -> Plan:
        """
        Generate a revised plan after a step failure, used by A-03 outer loop.
        """
        ...
```

## 技术约束

- Planner 必须以 LangGraph 节点形式实现，状态通过 `AgentState` TypedDict 传递
- LLM 输出必须强制为 JSON Schema 验证的 Plan 对象，使用 Pydantic `model_validate` 解析
- tool_name 必须在调用前与 MCP Capability Manifest 做白名单校验，不合法的 tool_name 触发重规划（最多 2 次）
- 规划时不得执行任何实际工具调用，仅生成计划
- 单次规划 P99 延迟 ≤ 8 秒

## 测试策略

- 单元测试：mock IntentResult 和 available_tools，验证输出 Plan 的 JSON Schema 合规性；测试 requires_confirm 在高风险工具上正确置 True；测试 replan 逻辑
- 集成测试：与 A-01 联调，验证完整意图→计划链路；与 G-01 联调，验证 tool_name 白名单校验
- E2E：通过 SSE 流验证 `event: plan` 事件在用户消息后 10 秒内到达

## 依赖关系

- 被阻塞：[A-01]
- 阻塞：[A-03]

## 参考

- MVP_SPEC.md Section 3.1
