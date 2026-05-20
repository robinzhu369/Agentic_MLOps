---
id: "A-09"
module: "agent-core"
title: "Skill 自动抽象（Learning Loop）"
priority: P1
status: draft
owner: ""
dependencies: ["A-07", "A-08"]
milestone: "W7"
---

# [A-09] Skill 自动抽象（Learning Loop）

## 概述

当 A-08 Self-Critique 判定任务执行质量足够高（should_abstract_skill=True）时，自动将执行路径抽象为可复用的 Skill 并存入 A-07 Skill Library。Learning Loop 是 Agent 持续改进的核心机制，使系统随使用积累领域知识，逐步减少重复规划开销。

## 验收标准

- [ ] AC-1: 收到 should_abstract_skill=True 的 CritiqueResult 后，系统在 10 秒内完成 Skill 抽象并写入 Skill Library
- [ ] AC-2: 抽象出的 Skill 必须将具体参数值替换为 `{{variable}}` 占位符（如数据集路径、模型名称），不硬编码会话特定值
- [ ] AC-3: 若 Skill Library 中已存在相似度 ≥ 0.9 的 Skill，不创建重复 Skill，而是更新现有 Skill 的 usage_count
- [ ] AC-4: 自动抽象的 Skill 默认 is_public=False，需管理员审核后才可设为公开
- [ ] AC-5: 抽象过程中的错误不影响已完成任务的状态，失败时记录错误日志并跳过

## 接口定义

```python
from pydantic import BaseModel
from typing import Any


class AbstractionResult(BaseModel):
    action: str                           # "created" | "merged" | "skipped" | "failed"
    skill_id: str | None = None          # Set if created or merged
    merged_with: str | None = None       # Existing skill_id if merged
    reason: str | None = None            # Explanation for skipped/failed


class SkillAbstractor:
    def __init__(
        self,
        skill_library: "SkillLibrary",
        long_term_memory: "LongTermMemory",
    ):
        ...

    async def abstract_from_execution(
        self,
        critique_result: "CritiqueResult",
        plan: "Plan",
        observations: list["Observation"],
    ) -> AbstractionResult:
        """
        Extract a reusable Skill from a successful execution.

        Steps:
        1. Use LLM to identify parameterizable values in PlanSteps.
        2. Replace concrete values with {{variable}} placeholders.
        3. Check for duplicate Skills (similarity >= 0.9).
        4. Create new Skill or increment usage_count of existing.

        Args:
            critique_result: Must have should_abstract_skill=True.
            plan: Executed plan from A-02.
            observations: Step results for context.

        Returns:
            AbstractionResult indicating what action was taken.
        """
        ...

    async def _identify_parameters(
        self,
        steps: list["PlanStep"],
    ) -> tuple[list["SkillStep"], list[str]]:
        """
        Use LLM to identify session-specific values and replace with placeholders.
        Returns (parameterized_steps, parameter_names).
        """
        ...
```

## 技术约束

- 参数识别使用 LLM 调用，提示词明确要求识别：文件路径、模型名称、数据集名称、时间戳等会话特定值
- 重复检测使用 A-07 SkillLibrary.search()，阈值 0.9，高于普通检索阈值（0.8）
- 抽象过程完全异步，不阻塞任何用户可见操作
- 自动创建的 Skill 的 created_by 字段设为 `"system:learning_loop"`
- 单次抽象操作超时 20 秒，超时记录日志并返回 action="failed"

## 测试策略

- 单元测试：mock LLM 和 SkillLibrary，验证参数化替换逻辑（路径、名称被正确替换为占位符）；测试重复检测触发 merge 而非 create；测试 should_abstract_skill=False 时不触发抽象
- 集成测试：与 A-07、A-08 联调，验证完整 Critique→抽象→存储链路
- E2E：执行相同类型任务两次，验证第二次执行时 Planner 检索到第一次抽象的 Skill

## 依赖关系

- 被阻塞：[A-07, A-08]
- 阻塞：[]

## 参考

- MVP_SPEC.md Section 3.1
