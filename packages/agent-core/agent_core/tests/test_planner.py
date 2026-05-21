"""Unit tests for A-02 Planner — schema validation, tool whitelist, replan."""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_core.hermes.config import AgentCoreSettings
from agent_core.hermes.planner import (
    Planner,
)
from agent_core.hermes.schemas import (
    IntentResult,
    Plan,
    PlanningError,
    PlanStep,
    TaskType,
    UnknownToolError,
)

AVAILABLE_TOOLS = [
    "data_catalog.get_schema",
    "data_catalog.profile_table",
    "data_catalog.sample_data",
    "jupyter.execute_code",
    "feature_store.list_feature_views",
    "feature_store.get_features",
    "feature_store.register_feature_view",
    "feature_store.delete_feature_view",
    "feature_store.materialize_production",
]


@pytest.fixture
def settings() -> AgentCoreSettings:
    return AgentCoreSettings(
        anthropic_api_key="test-key",
        max_plan_steps=20,
        max_replans=2,
        plan_max_retries=2,
    )


@pytest.fixture
def planner(settings: AgentCoreSettings) -> Planner:
    return Planner(settings=settings)


@pytest.fixture
def fraud_intent() -> IntentResult:
    return IntentResult(
        task_type=TaskType.TRAIN_MODEL,
        entities={
            "dataset": "creditcard",
            "model_type": "LightGBM",
            "target_column": "Class",
        },
        constraints={"metric_threshold": "AUC >= 0.90"},
        raw_intent="为信用卡交易表构建反欺诈模型",
        confidence=0.92,
    )


def _mock_plan_response(steps: list[dict[str, Any]]) -> MagicMock:
    """Create a mock Anthropic API response with plan steps."""
    text_block = MagicMock()
    text_block.text = json.dumps({"steps": steps})
    response = MagicMock()
    response.content = [text_block]
    response.usage = MagicMock(input_tokens=200, output_tokens=300)
    return response


VALID_PLAN_STEPS = [
    {
        "step_id": "step_1",
        "tool_name": "data_catalog.get_schema",
        "tool_args": {"table_name": "creditcard"},
        "depends_on": [],
        "description": "获取信用卡交易表的 schema 信息",
        "estimated_duration_s": 5,
    },
    {
        "step_id": "step_2",
        "tool_name": "data_catalog.profile_table",
        "tool_args": {"table_name": "creditcard"},
        "depends_on": ["step_1"],
        "description": "对数据表进行 profiling 分析",
        "estimated_duration_s": 30,
    },
    {
        "step_id": "step_3",
        "tool_name": "jupyter.execute_code",
        "tool_args": {"code": "import lightgbm as lgb\n# training code"},
        "depends_on": ["step_2"],
        "description": "使用 LightGBM 训练反欺诈模型",
        "estimated_duration_s": 120,
    },
    {
        "step_id": "step_4",
        "tool_name": "jupyter.execute_code",
        "tool_args": {"code": "# evaluate model AUC"},
        "depends_on": ["step_3"],
        "description": "评估模型 AUC 指标",
        "estimated_duration_s": 10,
    },
]


@pytest.mark.asyncio
async def test_planner_creates_valid_plan(
    planner: Planner, fraud_intent: IntentResult
) -> None:
    """Test that Planner produces a valid Plan with correct structure."""
    mock_response = _mock_plan_response(VALID_PLAN_STEPS)

    with patch.object(
        planner._client.messages, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = mock_response
        plan = await planner.create_plan(
            intent=fraud_intent,
            session_id="session_123",
            available_tools=AVAILABLE_TOOLS,
        )

    assert isinstance(plan, Plan)
    assert plan.session_id == "session_123"
    assert len(plan.steps) == 4
    assert plan.plan_id.startswith("plan_")
    assert plan.created_at  # ISO 8601 timestamp


@pytest.mark.asyncio
async def test_planner_step_schema_compliance(
    planner: Planner, fraud_intent: IntentResult
) -> None:
    """Test that each PlanStep has all required fields."""
    mock_response = _mock_plan_response(VALID_PLAN_STEPS)

    with patch.object(
        planner._client.messages, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = mock_response
        plan = await planner.create_plan(
            intent=fraud_intent,
            session_id="session_123",
            available_tools=AVAILABLE_TOOLS,
        )

    for step in plan.steps:
        assert isinstance(step, PlanStep)
        assert step.step_id
        assert step.tool_name
        assert isinstance(step.tool_args, dict)
        assert isinstance(step.depends_on, list)
        assert step.description


@pytest.mark.asyncio
async def test_planner_rejects_unknown_tools(
    planner: Planner, fraud_intent: IntentResult
) -> None:
    """Test that Planner raises UnknownToolError for invalid tool names."""
    bad_steps = [
        {
            "step_id": "step_1",
            "tool_name": "nonexistent_tool.do_something",
            "tool_args": {},
            "depends_on": [],
            "description": "Invalid tool",
        },
    ]
    # All retries return the same bad tool
    mock_response = _mock_plan_response(bad_steps)

    with patch.object(
        planner._client.messages, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = mock_response
        with pytest.raises(PlanningError):
            await planner.create_plan(
                intent=fraud_intent,
                session_id="session_123",
                available_tools=AVAILABLE_TOOLS,
            )


@pytest.mark.asyncio
async def test_planner_marks_high_risk_steps(
    planner: Planner, fraud_intent: IntentResult
) -> None:
    """Test that high-risk tools get requires_confirm=True."""
    steps_with_risk = [
        {
            "step_id": "step_1",
            "tool_name": "data_catalog.get_schema",
            "tool_args": {},
            "depends_on": [],
            "description": "Safe step",
        },
        {
            "step_id": "step_2",
            "tool_name": "feature_store.delete_feature_view",
            "tool_args": {"name": "old_view"},
            "depends_on": ["step_1"],
            "description": "Delete old feature view",
        },
        {
            "step_id": "step_3",
            "tool_name": "feature_store.materialize_production",
            "tool_args": {},
            "depends_on": ["step_2"],
            "description": "Materialize to production",
        },
    ]
    mock_response = _mock_plan_response(steps_with_risk)

    with patch.object(
        planner._client.messages, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = mock_response
        plan = await planner.create_plan(
            intent=fraud_intent,
            session_id="session_123",
            available_tools=AVAILABLE_TOOLS,
        )

    # Safe step
    assert plan.steps[0].requires_confirm is False
    # High-risk steps
    assert plan.steps[1].requires_confirm is True
    assert plan.steps[2].requires_confirm is True


@pytest.mark.asyncio
async def test_planner_retries_on_invalid_json(
    planner: Planner, fraud_intent: IntentResult
) -> None:
    """Test that Planner retries when LLM returns invalid JSON."""
    bad_block = MagicMock()
    bad_block.text = "not json"
    bad_response = MagicMock()
    bad_response.content = [bad_block]
    bad_response.usage = MagicMock(input_tokens=100, output_tokens=50)

    good_response = _mock_plan_response(VALID_PLAN_STEPS)

    with patch.object(
        planner._client.messages, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.side_effect = [bad_response, good_response]
        plan = await planner.create_plan(
            intent=fraud_intent,
            session_id="session_123",
            available_tools=AVAILABLE_TOOLS,
        )

    assert len(plan.steps) == 4
    assert mock_create.call_count == 2


@pytest.mark.asyncio
async def test_planner_raises_after_max_retries(
    planner: Planner, fraud_intent: IntentResult
) -> None:
    """Test that Planner raises PlanningError after exhausting retries."""
    bad_block = MagicMock()
    bad_block.text = "garbage"
    bad_response = MagicMock()
    bad_response.content = [bad_block]
    bad_response.usage = MagicMock(input_tokens=100, output_tokens=50)

    with patch.object(
        planner._client.messages, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = bad_response
        with pytest.raises(PlanningError) as exc_info:
            await planner.create_plan(
                intent=fraud_intent,
                session_id="session_123",
                available_tools=AVAILABLE_TOOLS,
            )

    assert exc_info.value.attempts == 3


@pytest.mark.asyncio
async def test_planner_replan(planner: Planner) -> None:
    """Test replan generates a revised plan after step failure."""
    original_plan = Plan(
        plan_id="plan_abc123",
        session_id="session_123",
        steps=[
            PlanStep(
                step_id="step_1",
                tool_name="data_catalog.get_schema",
                tool_args={"table_name": "creditcard"},
                description="Get schema",
            ),
            PlanStep(
                step_id="step_2",
                tool_name="jupyter.execute_code",
                tool_args={"code": "bad code"},
                depends_on=["step_1"],
                description="Execute training",
            ),
        ],
    )

    revised_steps = [
        {
            "step_id": "step_1",
            "tool_name": "data_catalog.get_schema",
            "tool_args": {"table_name": "creditcard"},
            "depends_on": [],
            "description": "Get schema (unchanged)",
        },
        {
            "step_id": "step_2",
            "tool_name": "jupyter.execute_code",
            "tool_args": {"code": "fixed code"},
            "depends_on": ["step_1"],
            "description": "Execute training with fix",
        },
    ]
    mock_response = _mock_plan_response(revised_steps)

    with patch.object(
        planner._client.messages, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = mock_response
        new_plan = await planner.replan(
            original_plan=original_plan,
            failed_step_id="step_2",
            error_context="SyntaxError: invalid syntax",
        )

    assert isinstance(new_plan, Plan)
    assert new_plan.session_id == "session_123"
    assert len(new_plan.steps) == 2


@pytest.mark.asyncio
async def test_planner_from_skill_hint(
    planner: Planner, fraud_intent: IntentResult
) -> None:
    """Test that Planner uses skill_hint steps when provided."""
    skill = MagicMock()
    skill.id = "skill_fraud_v1"
    skill.steps = [
        {
            "step_id": "step_1",
            "tool_name": "data_catalog.get_schema",
            "tool_args": {"table_name": "creditcard"},
            "depends_on": [],
            "description": "Schema discovery",
        },
        {
            "step_id": "step_2",
            "tool_name": "jupyter.execute_code",
            "tool_args": {"code": "# train"},
            "depends_on": ["step_1"],
            "description": "Train model",
        },
    ]

    plan = await planner.create_plan(
        intent=fraud_intent,
        session_id="session_456",
        available_tools=AVAILABLE_TOOLS,
        skill_hint=skill,
    )

    assert plan.skill_id == "skill_fraud_v1"
    assert len(plan.steps) == 2
    assert plan.steps[0].tool_name == "data_catalog.get_schema"


@pytest.mark.asyncio
async def test_planner_tool_whitelist_retry_then_success(
    planner: Planner, fraud_intent: IntentResult
) -> None:
    """Test that Planner retries with correction when tool is invalid, then succeeds."""
    # First response has invalid tool
    bad_steps = [
        {
            "step_id": "step_1",
            "tool_name": "invalid_tool.foo",
            "tool_args": {},
            "depends_on": [],
            "description": "Bad tool",
        },
    ]
    bad_response = _mock_plan_response(bad_steps)

    # Second response has valid tools
    good_response = _mock_plan_response(VALID_PLAN_STEPS)

    with patch.object(
        planner._client.messages, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.side_effect = [bad_response, good_response]
        plan = await planner.create_plan(
            intent=fraud_intent,
            session_id="session_123",
            available_tools=AVAILABLE_TOOLS,
        )

    assert len(plan.steps) == 4
    # Verify correction message was sent
    assert mock_create.call_count == 2


@pytest.mark.asyncio
async def test_planner_minimum_steps_for_fraud_model(
    planner: Planner, fraud_intent: IntentResult
) -> None:
    """AC-1: Given fraud model intent, plan has >= 3 steps."""
    mock_response = _mock_plan_response(VALID_PLAN_STEPS)

    with patch.object(
        planner._client.messages, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = mock_response
        plan = await planner.create_plan(
            intent=fraud_intent,
            session_id="session_123",
            available_tools=AVAILABLE_TOOLS,
        )

    assert len(plan.steps) >= 3


def test_high_risk_tool_detection() -> None:
    """Test that high-risk tool patterns are correctly identified."""
    planner = Planner(settings=AgentCoreSettings(anthropic_api_key="test"))

    steps = [
        PlanStep(
            step_id="s1",
            tool_name="data_catalog.get_schema",
            tool_args={},
            description="safe",
        ),
        PlanStep(
            step_id="s2",
            tool_name="feature_store.delete_feature_view",
            tool_args={},
            description="delete",
        ),
        PlanStep(
            step_id="s3",
            tool_name="feature_store.materialize_production",
            tool_args={},
            description="prod",
        ),
        PlanStep(
            step_id="s4",
            tool_name="data_catalog.drop_table",
            tool_args={},
            description="drop",
        ),
    ]

    planner._mark_high_risk_steps(steps)

    assert steps[0].requires_confirm is False
    assert steps[1].requires_confirm is True  # In HIGH_RISK_TOOL_NAMES
    assert steps[2].requires_confirm is True  # In HIGH_RISK_TOOL_NAMES
    assert steps[3].requires_confirm is True  # In HIGH_RISK_TOOL_NAMES


def test_validate_tools_raises_for_unknown() -> None:
    """Test _validate_tools raises UnknownToolError."""
    planner = Planner(settings=AgentCoreSettings(anthropic_api_key="test"))

    steps = [
        PlanStep(
            step_id="s1",
            tool_name="nonexistent.tool",
            tool_args={},
            description="bad",
        ),
    ]

    with pytest.raises(UnknownToolError) as exc_info:
        planner._validate_tools(steps, AVAILABLE_TOOLS)

    assert exc_info.value.tool_name == "nonexistent.tool"


def test_plan_step_depends_on_validation() -> None:
    """Test PlanStep dependency references are preserved."""
    step = PlanStep(
        step_id="step_3",
        tool_name="jupyter.execute_code",
        tool_args={"code": "x = 1"},
        depends_on=["step_1", "step_2"],
        description="Depends on two prior steps",
    )
    assert step.depends_on == ["step_1", "step_2"]


def test_plan_serialization() -> None:
    """Test Plan can be serialized to JSON (for SSE streaming)."""
    plan = Plan(
        plan_id="plan_test123",
        session_id="session_abc",
        steps=[
            PlanStep(
                step_id="step_1",
                tool_name="data_catalog.get_schema",
                tool_args={"table": "t1"},
                description="Get schema",
            ),
        ],
    )

    json_str = plan.model_dump_json()
    data = json.loads(json_str)

    assert data["plan_id"] == "plan_test123"
    assert data["session_id"] == "session_abc"
    assert len(data["steps"]) == 1
    assert data["steps"][0]["tool_name"] == "data_catalog.get_schema"
