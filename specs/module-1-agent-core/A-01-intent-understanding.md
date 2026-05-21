---
id: "A-01"
module: "agent-core"
title: "自然语言意图理解"
priority: P0
status: done
owner: ""
dependencies: []
milestone: "W3"
---

# [A-01] 自然语言意图理解

## 概述

将用户输入的自然语言消息解析为结构化意图对象，提取任务类型、目标实体、约束条件和上下文参数。该功能是 Agent 执行链的入口，直接决定后续规划质量，对 MVP 的端到端可用性至关重要。

## 验收标准

- [x] AC-1: 给定标准 MLOps 指令（如"训练一个 XGBoost 模型，特征来自 feature_store.user_features，目标列 label"），系统能在 2 秒内返回包含 task_type、entities、constraints 字段的 IntentResult 对象
- [x] AC-2: 对歧义输入（缺少必要参数），系统返回 `clarification_needed=True` 并附带 `missing_fields` 列表，不进入规划阶段
- [x] AC-3: 意图置信度低于阈值（0.7）时，系统记录警告日志并触发二次确认流程
- [x] AC-4: 支持中英文混合输入，解析结果语言无关
- [x] AC-5: 单次解析 P99 延迟 ≤ 3 秒（不含网络传输）

## 接口定义

```python
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class TaskType(str, Enum):
    TRAIN_MODEL = "train_model"
    RUN_EXPERIMENT = "run_experiment"
    QUERY_DATA = "query_data"
    DEPLOY_MODEL = "deploy_model"
    ANALYZE_FEATURES = "analyze_features"
    UNKNOWN = "unknown"


class IntentResult(BaseModel):
    task_type: TaskType
    entities: dict[str, str] = Field(default_factory=dict)
    constraints: dict[str, str] = Field(default_factory=dict)
    raw_intent: str
    confidence: float = Field(ge=0.0, le=1.0)
    clarification_needed: bool = False
    missing_fields: list[str] = Field(default_factory=list)


class IntentParser:
    async def parse(
        self,
        user_message: str,
        session_context: dict | None = None,
    ) -> IntentResult:
        """
        Parse natural language input into a structured IntentResult.

        Args:
            user_message: Raw user input string (Chinese/English/mixed).
            session_context: Optional prior conversation context for disambiguation.

        Returns:
            IntentResult with task_type, entities, constraints, and confidence.

        Raises:
            IntentParseError: If LLM call fails or response is malformed.
        """
        ...
```

## 技术约束

- 使用 LangGraph 0.2+ 作为编排框架，意图解析作为独立 LangGraph 节点实现
- LLM 调用必须使用结构化输出（`response_format={"type": "json_object"}`），禁止正则解析 LLM 自由文本
- 不得直接调用任何 MCP 工具；若需要上下文补充，通过 A-05 短期记忆读取
- 置信度阈值 0.7 为可配置参数，存储于环境变量 `INTENT_CONFIDENCE_THRESHOLD`
- 解析结果必须可序列化为 JSON，用于 A-02 规划器输入

## 测试策略

- 单元测试：针对 20+ 标准 MLOps 指令的 golden-set 测试，验证 task_type 和 entities 正确率 ≥ 95%；mock LLM 调用，测试歧义检测逻辑
- 集成测试：与真实 LLM 端点联调，验证延迟 SLA；测试中英文混合输入场景
- E2E：通过 `POST /api/v1/agent/sessions/{id}/messages` 发送真实请求，验证 IntentResult 出现在 SSE 流的第一个事件中

## 依赖关系

- 被阻塞：[]
- 阻塞：[A-02]

## 参考

- MVP_SPEC.md Section 3.1
