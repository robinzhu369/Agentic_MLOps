"""A-01: Natural language intent understanding via LLM structured output."""
from __future__ import annotations

import json
from typing import Any

import anthropic
import structlog
from shared_lib.telemetry import trace_llm_call

from .config import AgentCoreSettings, get_agent_settings
from .schemas import IntentParseError, IntentResult, TaskType

logger = structlog.get_logger(__name__)

_INTENT_SYSTEM_PROMPT = (
    "You are an MLOps intent parser. "
    "Given a user message, extract the structured intent.\n\n"
    "Output a JSON object with these fields:\n"
    '- task_type: one of "train_model", "run_experiment", '
    '"query_data", "deploy_model", "analyze_features", "unknown"\n'
    "- entities: dict of key entities "
    "(e.g. model_type, dataset, target_column, feature_source)\n"
    "- constraints: dict of constraints "
    "(e.g. metric_threshold, time_limit, framework)\n"
    "- confidence: float 0.0-1.0 how confident you are\n"
    "- clarification_needed: boolean, true if ambiguous "
    "or missing critical info\n"
    "- missing_fields: list of field names needed but not provided\n\n"
    "Rules:\n"
    "- training/building a model → task_type = \"train_model\"\n"
    "- running/executing an experiment → task_type = \"run_experiment\"\n"
    "- querying/exploring/profiling data → task_type = \"query_data\"\n"
    "- deploying/serving a model → task_type = \"deploy_model\"\n"
    "- analyzing/engineering features → task_type = \"analyze_features\"\n"
    "- unclear or no match → task_type = \"unknown\", "
    "clarification_needed = true\n"
    "- If critical info is missing (e.g. no dataset for training), "
    "set clarification_needed = true and list missing fields\n"
    "- Support Chinese, English, and mixed-language input equally\n"
    "- Be conservative with confidence: "
    "only use >0.9 for very clear, complete instructions\n\n"
    "Output ONLY valid JSON, no markdown fences or extra text."
)


class IntentParser:
    """Parse natural language into structured IntentResult using Claude API.

    Implements A-01 spec: LangGraph-compatible node that converts user messages
    into structured intent objects for downstream planning.
    """

    def __init__(self, settings: AgentCoreSettings | None = None) -> None:
        self._settings = settings or get_agent_settings()
        self._client = anthropic.AsyncAnthropic(
            api_key=self._settings.anthropic_api_key
        )

    async def parse(
        self,
        user_message: str,
        session_context: dict[str, Any] | None = None,
    ) -> IntentResult:
        """Parse natural language input into a structured IntentResult.

        Args:
            user_message: Raw user input string (Chinese/English/mixed).
            session_context: Optional prior conversation context for disambiguation.

        Returns:
            IntentResult with task_type, entities, constraints, and confidence.

        Raises:
            IntentParseError: If LLM call fails or response is malformed.
        """
        log = logger.bind(user_message=user_message[:100])
        log.info("intent_parse_start")

        messages = self._build_messages(user_message, session_context)

        raw_response: str | None = None
        last_error: Exception | None = None

        for attempt in range(self._settings.intent_max_retries + 1):
            try:
                raw_response = await self._call_llm(messages)
                result = self._parse_response(raw_response, user_message)

                if result.confidence < self._settings.intent_confidence_threshold:
                    log.warning(
                        "intent_low_confidence",
                        confidence=result.confidence,
                        threshold=self._settings.intent_confidence_threshold,
                    )

                log.info(
                    "intent_parse_success",
                    task_type=result.task_type,
                    confidence=result.confidence,
                    clarification_needed=result.clarification_needed,
                    attempt=attempt,
                )
                return result

            except (json.JSONDecodeError, KeyError, ValueError) as e:
                last_error = e
                log.warning(
                    "intent_parse_retry",
                    attempt=attempt,
                    error=str(e),
                )
                continue

        raise IntentParseError(
            f"Failed to parse intent after {self._settings.intent_max_retries + 1} "
            f"attempts: {last_error}",
            raw_response=raw_response,
        )

    def _build_messages(
        self,
        user_message: str,
        session_context: dict[str, Any] | None,
    ) -> list[dict[str, str]]:
        """Build the message list for the LLM call."""
        content = user_message
        if session_context:
            context_str = json.dumps(session_context, ensure_ascii=False)
            content = (
                f"Previous context: {context_str}\n\n"
                f"Current message: {user_message}"
            )
        return [{"role": "user", "content": content}]

    @trace_llm_call  # type: ignore[untyped-decorator]
    async def _call_llm(self, messages: list[dict[str, str]]) -> str:
        """Call Claude API with structured output request."""
        response = await self._client.messages.create(
            model=self._settings.anthropic_model,
            max_tokens=1024,
            system=_INTENT_SYSTEM_PROMPT,
            messages=messages,  # type: ignore[arg-type]
        )
        # Extract text content from response
        text_block = response.content[0]
        if hasattr(text_block, "text"):
            return text_block.text
        raise IntentParseError("LLM response has no text content")

    def _parse_response(self, raw: str, original_message: str) -> IntentResult:
        """Parse raw LLM JSON response into IntentResult."""
        data = json.loads(raw)

        # Normalize task_type
        task_type_raw = data.get("task_type", "unknown")
        try:
            task_type = TaskType(task_type_raw)
        except ValueError:
            task_type = TaskType.UNKNOWN

        return IntentResult(
            task_type=task_type,
            entities=data.get("entities", {}),
            constraints=data.get("constraints", {}),
            raw_intent=original_message,
            confidence=float(data.get("confidence", 0.0)),
            clarification_needed=bool(data.get("clarification_needed", False)),
            missing_fields=data.get("missing_fields", []),
        )
