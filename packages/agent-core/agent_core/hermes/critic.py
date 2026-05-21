"""A-08: Self-Critique evaluator — scores execution quality."""
from __future__ import annotations

import structlog
from pydantic import BaseModel, Field

from agent_core.hermes.executor import ExecutionState, StepStatus

logger = structlog.get_logger(__name__)


class CritiqueResult(BaseModel):
    """Result of self-critique evaluation."""

    score: float = Field(ge=0.0, le=1.0)
    passed: bool = False
    feedback: str = ""
    suggestions: list[str] = Field(default_factory=list)


class SelfCritic:
    """Evaluates execution quality and provides feedback.

    Scores based on:
    - Step completion rate
    - Retry count (fewer is better)
    - Replan count (fewer is better)
    - Final output quality indicators
    """

    def __init__(self, pass_threshold: float = 0.7) -> None:
        self._threshold = pass_threshold

    async def evaluate(
        self,
        state: ExecutionState,
        expected_output: dict[str, str] | None = None,
    ) -> CritiqueResult:
        """Evaluate execution quality.

        Args:
            state: Final execution state.
            expected_output: Optional expected output indicators.

        Returns:
            CritiqueResult with score and feedback.
        """
        scores: list[float] = []
        suggestions: list[str] = []

        # 1. Completion rate
        total_steps = len(state.step_states)
        if total_steps > 0:
            completed = sum(
                1
                for s in state.step_states.values()
                if s == StepStatus.COMPLETED
            )
            completion_rate = completed / total_steps
            scores.append(completion_rate)

            if completion_rate < 1.0:
                failed = [
                    sid
                    for sid, s in state.step_states.items()
                    if s == StepStatus.FAILED
                ]
                if failed:
                    suggestions.append(
                        f"Steps failed: {', '.join(failed)}"
                    )
        else:
            scores.append(0.0)
            suggestions.append("No steps were executed")

        # 2. Retry penalty
        total_retries = sum(
            o.retry_count for o in state.observations
        )
        if total_retries == 0:
            scores.append(1.0)
        elif total_retries <= 2:
            scores.append(0.8)
        else:
            scores.append(0.5)
            suggestions.append(
                f"High retry count ({total_retries}), "
                "consider more robust tool arguments"
            )

        # 3. Replan penalty
        if state.replan_count == 0:
            scores.append(1.0)
        elif state.replan_count == 1:
            scores.append(0.7)
        else:
            scores.append(0.4)
            suggestions.append(
                f"Multiple replans ({state.replan_count}), "
                "initial plan quality needs improvement"
            )

        # 4. Task status
        if state.task_status == "completed":
            scores.append(1.0)
        elif state.task_status == "failed":
            scores.append(0.0)
            suggestions.append("Task failed to complete")
        else:
            scores.append(0.5)

        # Compute weighted average
        final_score = sum(scores) / len(scores) if scores else 0.0
        passed = final_score >= self._threshold

        feedback = self._generate_feedback(
            final_score, state, suggestions
        )

        logger.info(
            "self_critique_complete",
            score=round(final_score, 3),
            passed=passed,
            session_id=state.session_id,
        )

        return CritiqueResult(
            score=round(final_score, 3),
            passed=passed,
            feedback=feedback,
            suggestions=suggestions,
        )

    def _generate_feedback(
        self,
        score: float,
        state: ExecutionState,
        suggestions: list[str],
    ) -> str:
        """Generate human-readable feedback."""
        if score >= 0.9:
            return "Excellent execution — all steps completed efficiently."
        if score >= 0.7:
            return (
                "Good execution with minor issues. "
                f"Suggestions: {'; '.join(suggestions)}"
                if suggestions
                else "Good execution."
            )
        if score >= 0.5:
            return (
                "Execution completed with significant issues. "
                f"Issues: {'; '.join(suggestions)}"
            )
        return (
            "Poor execution quality. "
            f"Critical issues: {'; '.join(suggestions)}"
        )
