"""Hermes Agent schemas — IntentResult, PlanStep, Plan, and error types."""
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# --- Intent ---


class TaskType(StrEnum):
    """Supported MLOps task types."""

    TRAIN_MODEL = "train_model"
    RUN_EXPERIMENT = "run_experiment"
    QUERY_DATA = "query_data"
    DEPLOY_MODEL = "deploy_model"
    ANALYZE_FEATURES = "analyze_features"
    UNKNOWN = "unknown"


class IntentResult(BaseModel):
    """Structured output from intent parsing."""

    task_type: TaskType
    entities: dict[str, str] = Field(default_factory=dict)
    constraints: dict[str, str] = Field(default_factory=dict)
    raw_intent: str
    confidence: float = Field(ge=0.0, le=1.0)
    clarification_needed: bool = False
    missing_fields: list[str] = Field(default_factory=list)


# --- Plan ---


class PlanStep(BaseModel):
    """A single step in an execution plan."""

    step_id: str
    tool_name: str
    tool_args: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    description: str
    requires_confirm: bool = False
    estimated_duration_s: int | None = None


class Plan(BaseModel):
    """Ordered execution plan produced by the Planner."""

    plan_id: str
    session_id: str
    steps: list[PlanStep]
    created_at: str = Field(
        default_factory=lambda: datetime.now(tz=UTC).isoformat()
    )
    skill_id: str | None = None


# --- Errors ---


class IntentParseError(Exception):
    """Raised when intent parsing fails after retries."""

    def __init__(self, message: str, raw_response: str | None = None) -> None:
        super().__init__(message)
        self.raw_response = raw_response


class PlanningError(Exception):
    """Raised when the Planner fails to produce a valid plan."""

    def __init__(self, message: str, attempts: int = 0) -> None:
        super().__init__(message)
        self.attempts = attempts


class UnknownToolError(PlanningError):
    """Raised when a planned tool_name is not in the capability manifest."""

    def __init__(self, tool_name: str, available_tools: list[str]) -> None:
        super().__init__(
            f"Tool '{tool_name}' not in capability manifest. "
            f"Available: {available_tools[:10]}",
            attempts=0,
        )
        self.tool_name = tool_name
        self.available_tools = available_tools
