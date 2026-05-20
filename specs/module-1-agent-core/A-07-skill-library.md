---
id: "A-07"
module: "agent-core"
title: "Skill Library 检索"
priority: P0
status: draft
owner: ""
dependencies: ["A-06"]
milestone: "W7"
---

# [A-07] Skill Library 检索

## 概述

Skill Library 是可复用任务模板的存储与检索系统。当 Agent 成功完成一类任务后，可将执行路径抽象为 Skill（由 A-09 触发）；在新任务规划时，A-02 Planner 通过语义检索找到匹配 Skill，直接复用而非重新规划，提升执行效率和一致性。

## 验收标准

- [ ] AC-1: 给定任务描述，语义检索在 Skill Library 中返回相似度 ≥ 0.8 的 Skill，检索延迟 ≤ 100ms
- [ ] AC-2: 无匹配 Skill（相似度 < 0.8）时返回空列表，不影响正常规划流程
- [ ] AC-3: Skill 包含完整的 PlanStep 模板列表，支持参数化替换（使用 `{{variable}}` 占位符）
- [ ] AC-4: `GET /api/v1/skills` 返回当前用户可见的所有 Skill 列表（含分页）
- [ ] AC-5: `POST /api/v1/skills` 支持手动创建 Skill，需通过 JSON Schema 验证

## 接口定义

```python
from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime


class SkillStep(BaseModel):
    tool_name: str
    tool_args_template: dict[str, Any]   # Supports "{{variable}}" placeholders
    description: str
    requires_confirm: bool = False


class Skill(BaseModel):
    skill_id: str
    name: str
    description: str                      # Used for semantic embedding
    task_type: str                        # e.g. "train_model", "run_experiment"
    steps: list[SkillStep]
    parameters: list[str] = Field(default_factory=list)  # Required placeholder names
    usage_count: int = 0
    created_by: str                       # "system" | user_id
    created_at: datetime
    is_public: bool = False              # Public skills visible to all users


class SkillSearchResult(BaseModel):
    skill: Skill
    similarity: float


class SkillLibrary:
    def __init__(self, long_term_memory: "LongTermMemory"):
        ...

    async def search(
        self,
        query: str,
        user_id: str,
        top_k: int = 3,
        similarity_threshold: float = 0.8,
    ) -> list[SkillSearchResult]:
        """
        Semantic search for matching Skills.

        Searches both user-owned and public skills.
        Uses A-06 LongTermMemory with memory_type=SKILL.

        Returns:
            Skills sorted by similarity descending, filtered by threshold.
        """
        ...

    async def get_skill(self, skill_id: str) -> Skill | None:
        """Retrieve a Skill by ID."""
        ...

    async def create_skill(
        self,
        skill: Skill,
        user_id: str,
    ) -> str:
        """
        Store a new Skill in the library.

        Embeds skill.description for future semantic search.
        Returns skill_id.
        """
        ...

    async def list_skills(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Skill], int]:
        """
        List skills visible to user (own + public).
        Returns (skills, total_count).
        """
        ...

    async def increment_usage(self, skill_id: str) -> None:
        """Increment usage_count when a Skill is applied."""
        ...
```

## 技术约束

- Skill 向量存储复用 A-06 LongTermMemory，memory_type=SKILL，不引入额外向量数据库
- 参数化替换使用 Jinja2 模板引擎，`{{variable}}` 语法，渲染时验证所有必需参数已提供
- 公开 Skill（is_public=True）由系统管理员通过 `POST /api/v1/skills` 创建，普通用户只读
- Skill 步骤中的 tool_name 在创建时验证是否存在于 MCP Capability Manifest
- 单个 Skill 最多包含 20 个步骤

## 测试策略

- 单元测试：mock A-06，验证相似度阈值过滤；测试 Jinja2 参数替换逻辑；测试缺少必需参数时的错误
- 集成测试：创建 Skill→语义检索→参数化实例化完整流程；验证公开 Skill 对所有用户可见
- E2E：通过 API 创建 Skill，在新会话中触发相同类型任务，验证 Planner 复用该 Skill

## 依赖关系

- 被阻塞：[A-06]
- 阻塞：[A-09]

## 参考

- MVP_SPEC.md Section 3.1
