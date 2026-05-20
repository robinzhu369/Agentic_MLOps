---
id: "A-08"
module: "agent-core"
title: "Self-Critique 评估"
priority: P1
status: draft
owner: ""
dependencies: ["A-03"]
milestone: "W7"
---

# [A-08] Self-Critique 评估

## 概述

在任务执行完成后，使用独立 LLM 调用对执行路径进行自我评估，检测路径偏差、效率问题和潜在改进点。Self-Critique 结果用于触发 A-09 Skill 自动抽象，并作为质量信号反馈给用户。独立 LLM 调用确保评估视角与执行视角解耦，避免自我确认偏差。

## 验收标准

- [ ] AC-1: 任务完成（COMPLETED 或 FAILED）后自动触发 Self-Critique，不阻塞主执行流程（异步执行）
- [ ] AC-2: Critique 结果包含 overall_score（0-10）、path_deviation（bool）、efficiency_score（0-10）和 improvement_suggestions 列表
- [ ] AC-3: 当 path_deviation=True 时，系统记录偏差详情并通知 A-09 不抽象该路径为 Skill
- [ ] AC-4: Self-Critique LLM 调用使用独立的系统提示，不共享执行阶段的对话历史
- [ ] AC-5: Critique 结果存入长期记忆（A-06），关联原始 session_id，供后续分析

## 接口定义

```python
from pydantic import BaseModel, Field
from typing import Any


class ImprovementSuggestion(BaseModel):
    step_id: str | None = None           # None means task-level suggestion
    category: str                        # "efficiency" | "correctness" | "safety"
    description: str
    severity: str                        # "low" | "medium" | "high"


class CritiqueResult(BaseModel):
    session_id: str
    plan_id: str
    overall_score: float = Field(ge=0.0, le=10.0)
    path_deviation: bool
    deviation_description: str | None = None
    efficiency_score: float = Field(ge=0.0, le=10.0)
    improvement_suggestions: list[ImprovementSuggestion]
    should_abstract_skill: bool          # Derived: not path_deviation and overall_score >= 7.0
    raw_critique: str                    # Full LLM response for debugging


class SelfCritique:
    async def evaluate(
        self,
        session_id: str,
        plan: "Plan",
        observations: list["Observation"],
        final_status: "TaskStatus",
    ) -> CritiqueResult:
        """
        Evaluate task execution using an independent LLM call.

        Uses a separate LLM context (no shared conversation history).
        Runs asynchronously after task completion.

        Args:
            session_id: Session being evaluated.
            plan: Original plan from A-02.
            observations: All step observations from A-03.
            final_status: COMPLETED or FAILED.

        Returns:
            CritiqueResult with scores and improvement suggestions.

        Raises:
            CritiqueError: If LLM call fails (non-blocking, logged and skipped).
        """
        ...
```

## 技术约束

- Self-Critique 必须使用独立 LLM 调用，禁止复用执行阶段的 LangGraph 状态或对话历史
- 评估调用超时 30 秒，超时后记录警告日志并跳过（不影响任务状态）
- `should_abstract_skill` 字段由规则计算：`not path_deviation and overall_score >= 7.0`，不由 LLM 决定
- Critique 结果异步写入 A-06 长期记忆，不阻塞任务完成事件的 SSE 推送
- 每个会话最多触发一次 Self-Critique，重规划后的最终执行结果才触发

## 测试策略

- 单元测试：mock LLM 调用，验证 should_abstract_skill 规则逻辑；测试超时处理（不抛出异常）；测试 path_deviation 检测
- 集成测试：与 A-03 联调，验证任务完成后异步触发 Critique；与 A-06 联调，验证结果持久化
- E2E：完整任务执行后，通过长期记忆查询验证 Critique 结果已存储

## 依赖关系

- 被阻塞：[A-03]
- 阻塞：[A-09]

## 参考

- MVP_SPEC.md Section 3.1
