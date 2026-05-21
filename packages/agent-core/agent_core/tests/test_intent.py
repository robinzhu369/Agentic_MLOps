"""Unit tests for A-01 IntentParser — 20+ golden-set test cases."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_core.hermes.config import AgentCoreSettings
from agent_core.hermes.intent import IntentParser
from agent_core.hermes.schemas import IntentParseError, IntentResult, TaskType


@pytest.fixture
def settings() -> AgentCoreSettings:
    return AgentCoreSettings(
        anthropic_api_key="test-key",
        intent_confidence_threshold=0.7,
        intent_max_retries=2,
    )


@pytest.fixture
def parser(settings: AgentCoreSettings) -> IntentParser:
    return IntentParser(settings=settings)


def _mock_llm_response(data: dict) -> MagicMock:
    """Create a mock Anthropic API response."""
    text_block = MagicMock()
    text_block.text = json.dumps(data, ensure_ascii=False)
    response = MagicMock()
    response.content = [text_block]
    response.usage = MagicMock(input_tokens=100, output_tokens=50)
    return response


# --- Golden-set test cases ---

GOLDEN_SET = [
    # 1. Chinese: train fraud model
    {
        "input": "为信用卡交易表构建反欺诈模型",
        "expected_task_type": TaskType.TRAIN_MODEL,
        "expected_entities": {"dataset": "信用卡交易表", "model_type": "反欺诈"},
    },
    # 2. English: train XGBoost
    {
        "input": (
            "Train an XGBoost model using "
            "feature_store.user_features, target column is label"
        ),
        "expected_task_type": TaskType.TRAIN_MODEL,
        "expected_entities": {
            "model_type": "XGBoost",
            "feature_source": "feature_store.user_features",
            "target_column": "label",
        },
    },
    # 3. Chinese: query data
    {
        "input": "查看交易数据表的前100行",
        "expected_task_type": TaskType.QUERY_DATA,
    },
    # 4. English: deploy model
    {
        "input": "Deploy the fraud_model_v2 to production endpoint",
        "expected_task_type": TaskType.DEPLOY_MODEL,
        "expected_entities": {"model_name": "fraud_model_v2"},
    },
    # 5. Chinese: analyze features
    {
        "input": "分析用户特征表中各特征的分布和缺失率",
        "expected_task_type": TaskType.ANALYZE_FEATURES,
    },
    # 6. Mixed: run experiment
    {
        "input": "跑一个 LightGBM experiment，用 AUC 作为评估指标",
        "expected_task_type": TaskType.RUN_EXPERIMENT,
        "expected_entities": {"model_type": "LightGBM"},
        "expected_constraints": {"metric": "AUC"},
    },
    # 7. Ambiguous: missing critical info
    {
        "input": "训练一个模型",
        "expected_task_type": TaskType.TRAIN_MODEL,
        "expected_clarification": True,
        "expected_missing_fields": ["dataset"],
    },
    # 8. Very ambiguous
    {
        "input": "帮我做点什么",
        "expected_task_type": TaskType.UNKNOWN,
        "expected_clarification": True,
    },
    # 9. English: data profiling
    {
        "input": "Profile the transactions table and show me column statistics",
        "expected_task_type": TaskType.QUERY_DATA,
    },
    # 10. Chinese: feature engineering
    {
        "input": "基于交易金额和时间创建新特征",
        "expected_task_type": TaskType.ANALYZE_FEATURES,
    },
    # 11. English with constraints
    {
        "input": (
            "Train a model with AUC >= 0.90, "
            "use LightGBM, max training time 30 minutes"
        ),
        "expected_task_type": TaskType.TRAIN_MODEL,
        "expected_constraints": {"metric_threshold": "AUC >= 0.90"},
    },
    # 12. Chinese: schema discovery
    {
        "input": "列出数据库中所有可用的表和字段",
        "expected_task_type": TaskType.QUERY_DATA,
    },
    # 13. English: experiment comparison
    {
        "input": (
            "Run experiments comparing Random Forest vs "
            "LightGBM on the fraud dataset"
        ),
        "expected_task_type": TaskType.RUN_EXPERIMENT,
    },
    # 14. Chinese: deploy with version
    {
        "input": "将模型 v3.2 部署到线上服务",
        "expected_task_type": TaskType.DEPLOY_MODEL,
    },
    # 15. Mixed: feature store
    {
        "input": "把 transaction_amount_mean_7d 注册到 feature store",
        "expected_task_type": TaskType.ANALYZE_FEATURES,
    },
    # 16. English: unclear intent
    {
        "input": "What can you do?",
        "expected_task_type": TaskType.UNKNOWN,
        "expected_clarification": True,
    },
    # 17. Chinese: complete training request
    {
        "input": "用 creditcard 数据集训练 LightGBM 模型，目标列 Class，评估指标 AUC",
        "expected_task_type": TaskType.TRAIN_MODEL,
        "expected_entities": {
            "dataset": "creditcard",
            "model_type": "LightGBM",
            "target_column": "Class",
        },
    },
    # 18. English: data sampling
    {
        "input": (
            "Sample 1000 rows from the fraud_transactions "
            "table where amount > 1000"
        ),
        "expected_task_type": TaskType.QUERY_DATA,
    },
    # 19. Chinese: model evaluation
    {
        "input": "评估当前模型在测试集上的表现",
        "expected_task_type": TaskType.RUN_EXPERIMENT,
    },
    # 20. Mixed: complex request
    {
        "input": (
            "先做 EDA，然后用 V1-V28 特征训练 "
            "fraud detection model，要求 recall > 0.8"
        ),
        "expected_task_type": TaskType.TRAIN_MODEL,
        "expected_constraints": {"metric_threshold": "recall > 0.8"},
    },
    # 21. English: missing dataset
    {
        "input": "Train a model",
        "expected_task_type": TaskType.TRAIN_MODEL,
        "expected_clarification": True,
    },
    # 22. Chinese: feature importance
    {
        "input": "分析模型的特征重要性排名",
        "expected_task_type": TaskType.ANALYZE_FEATURES,
    },
]


@pytest.mark.parametrize(
    "case",
    GOLDEN_SET,
    ids=[f"golden_{i+1}" for i in range(len(GOLDEN_SET))],
)
@pytest.mark.asyncio
async def test_intent_parser_golden_set(
    parser: IntentParser, case: dict
) -> None:
    """Test IntentParser against golden-set cases with mocked LLM."""
    # Build mock response matching expected output
    mock_data = {
        "task_type": case["expected_task_type"].value,
        "entities": case.get("expected_entities", {}),
        "constraints": case.get("expected_constraints", {}),
        "confidence": 0.5 if case.get("expected_clarification") else 0.85,
        "clarification_needed": case.get("expected_clarification", False),
        "missing_fields": case.get("expected_missing_fields", []),
    }

    mock_response = _mock_llm_response(mock_data)

    with patch.object(
        parser._client.messages, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = mock_response
        result = await parser.parse(case["input"])

    assert isinstance(result, IntentResult)
    assert result.task_type == case["expected_task_type"]
    assert result.raw_intent == case["input"]

    if "expected_clarification" in case:
        assert result.clarification_needed == case["expected_clarification"]

    if "expected_missing_fields" in case:
        for field in case["expected_missing_fields"]:
            assert field in result.missing_fields


@pytest.mark.asyncio
async def test_intent_parser_retries_on_invalid_json(
    parser: IntentParser,
) -> None:
    """Test that parser retries on malformed LLM output."""
    # First call returns invalid JSON, second returns valid
    bad_block = MagicMock()
    bad_block.text = "not valid json {"
    bad_response = MagicMock()
    bad_response.content = [bad_block]
    bad_response.usage = MagicMock(input_tokens=50, output_tokens=20)

    good_data = {
        "task_type": "train_model",
        "entities": {},
        "constraints": {},
        "confidence": 0.8,
        "clarification_needed": False,
        "missing_fields": [],
    }
    good_response = _mock_llm_response(good_data)

    with patch.object(
        parser._client.messages, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.side_effect = [bad_response, good_response]
        result = await parser.parse("Train a model on creditcard data")

    assert result.task_type == TaskType.TRAIN_MODEL
    assert mock_create.call_count == 2


@pytest.mark.asyncio
async def test_intent_parser_raises_after_max_retries(
    parser: IntentParser,
) -> None:
    """Test that parser raises IntentParseError after exhausting retries."""
    bad_block = MagicMock()
    bad_block.text = "invalid"
    bad_response = MagicMock()
    bad_response.content = [bad_block]
    bad_response.usage = MagicMock(input_tokens=50, output_tokens=20)

    with patch.object(
        parser._client.messages, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = bad_response
        with pytest.raises(IntentParseError):
            await parser.parse("some input")

    # 1 initial + 2 retries = 3 calls
    assert mock_create.call_count == 3


@pytest.mark.asyncio
async def test_intent_parser_low_confidence_warning(
    parser: IntentParser,
) -> None:
    """Test that low confidence results are still returned (with warning logged)."""
    mock_data = {
        "task_type": "unknown",
        "entities": {},
        "constraints": {},
        "confidence": 0.3,
        "clarification_needed": True,
        "missing_fields": [],
    }
    mock_response = _mock_llm_response(mock_data)

    with patch.object(
        parser._client.messages, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = mock_response
        result = await parser.parse("hmm")

    assert result.confidence == 0.3
    assert result.clarification_needed is True


@pytest.mark.asyncio
async def test_intent_parser_with_session_context(
    parser: IntentParser,
) -> None:
    """Test that session context is included in the LLM call."""
    mock_data = {
        "task_type": "train_model",
        "entities": {"dataset": "creditcard"},
        "constraints": {},
        "confidence": 0.9,
        "clarification_needed": False,
        "missing_fields": [],
    }
    mock_response = _mock_llm_response(mock_data)

    context = {"previous_dataset": "creditcard", "user_role": "scientist"}

    with patch.object(
        parser._client.messages, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = mock_response
        result = await parser.parse(
            "用同样的数据集训练模型", session_context=context
        )

    assert result.task_type == TaskType.TRAIN_MODEL
    # Verify context was passed in the message
    call_kwargs = mock_create.call_args.kwargs
    user_msg = call_kwargs["messages"][0]["content"]
    assert "creditcard" in user_msg


@pytest.mark.asyncio
async def test_intent_parser_unknown_task_type_fallback(
    parser: IntentParser,
) -> None:
    """Test that unrecognized task_type falls back to UNKNOWN."""
    mock_data = {
        "task_type": "some_new_type_not_in_enum",
        "entities": {},
        "constraints": {},
        "confidence": 0.6,
        "clarification_needed": True,
        "missing_fields": [],
    }
    mock_response = _mock_llm_response(mock_data)

    with patch.object(
        parser._client.messages, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = mock_response
        result = await parser.parse("do something weird")

    assert result.task_type == TaskType.UNKNOWN
