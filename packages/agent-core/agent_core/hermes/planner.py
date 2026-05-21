"""A-02: Multi-step task planning via LLM structured output."""
from __future__ import annotations

import json
import uuid
from typing import Any

import anthropic
import structlog
from shared_lib.telemetry import trace_llm_call

from .config import AgentCoreSettings, get_agent_settings
from .schemas import (
    IntentResult,
    Plan,
    PlanningError,
    PlanStep,
    UnknownToolError,
)

logger = structlog.get_logger(__name__)

# Tools that require human confirmation before execution
HIGH_RISK_TOOL_PREFIXES = (
    "deploy_",
    "delete_",
    "drop_",
    "remove_",
    "destroy_",
    "production_",
)

HIGH_RISK_TOOL_NAMES = frozenset({
    "jupyter.execute_code",  # when modifying production data
    "feature_store.delete_feature_view",
    "feature_store.materialize_production",
    "data_catalog.drop_table",
    "data_catalog.delete_dataset",
})

_PLANNER_SYSTEM_PROMPT = (
    "You are an MLOps task planner. Given a structured intent "
    "and a list of available tools, decompose the task into an "
    "ordered list of execution steps.\n\n"
    "Available tools (you MUST only use tools from this list):\n"
    "{available_tools}\n\n"
    "Output a JSON object with a single field \"steps\" "
    "containing an array of step objects.\n"
    "Each step must have:\n"
    "- step_id: string like \"step_1\", \"step_2\", etc.\n"
    "- tool_name: MUST be one of the available tools above\n"
    "- tool_args: dict of arguments to pass to the tool\n"
    "- depends_on: list of step_ids this step must wait for\n"
    "- description: human-readable description\n"
    "- estimated_duration_s: estimated seconds (integer or null)\n\n"
    "Rules:\n"
    "- Order logically: data exploration → feature engineering "
    "→ training → evaluation\n"
    "- Use depends_on for parallelism: independent steps can "
    "run in parallel\n"
    "- For training: data profiling, feature prep, training, "
    "evaluation\n"
    "- For queries: schema discovery, execution, formatting\n"
    "- Keep plans concise: max {max_steps} steps\n"
    "- tool_args: realistic placeholders from intent entities\n"
    "- Do NOT include tools not in the available list\n\n"
    "Output ONLY valid JSON, no markdown fences or extra text."
)

_REPLAN_SYSTEM_PROMPT = (
    "You are an MLOps task planner. A previous plan failed at "
    "a specific step. Generate a revised plan that works around "
    "the failure.\n\n"
    "Original plan:\n{original_plan}\n\n"
    "Failed step: {failed_step_id}\n"
    "Error: {error_context}\n\n"
    "Available tools:\n{available_tools}\n\n"
    "Generate a new plan that either:\n"
    "1. Retries the failed step with different parameters\n"
    "2. Uses an alternative approach to achieve the same goal\n"
    "3. Skips the failed step if not critical and adjusts "
    "downstream steps\n\n"
    "Output a JSON object with a single field \"steps\" "
    "containing the revised step array.\n"
    "Same format: step_id, tool_name, tool_args, depends_on, "
    "description, estimated_duration_s.\n\n"
    "Output ONLY valid JSON, no markdown fences or extra text."
)


class Planner:
    """Decompose structured intents into ordered execution plans.

    Implements A-02 spec: LangGraph-compatible node that produces validated
    Plan objects with tool whitelist enforcement and high-risk step detection.
    """

    def __init__(self, settings: AgentCoreSettings | None = None) -> None:
        self._settings = settings or get_agent_settings()
        self._client = anthropic.AsyncAnthropic(
            api_key=self._settings.anthropic_api_key
        )

    async def create_plan(
        self,
        intent: IntentResult,
        session_id: str,
        available_tools: list[str],
        skill_hint: Any | None = None,
    ) -> Plan:
        """Decompose an intent into an ordered list of PlanSteps.

        Args:
            intent: Structured intent from A-01 IntentParser.
            session_id: Current session identifier.
            available_tools: Tool names from MCP Capability Manifest (G-01).
            skill_hint: Optional matching Skill from A-07 for plan reuse.

        Returns:
            Plan with ordered PlanStep list.

        Raises:
            PlanningError: If LLM fails to produce a valid plan after retries.
            UnknownToolError: If planned tool_name is not in available_tools.
        """
        log = logger.bind(
            session_id=session_id,
            task_type=intent.task_type,
        )
        log.info("planning_start")

        # If a skill hint is provided, use its steps directly
        if skill_hint is not None and hasattr(skill_hint, "steps"):
            log.info("planning_from_skill", skill_id=getattr(skill_hint, "id", None))
            return self._plan_from_skill(skill_hint, session_id)

        prompt = self._build_plan_prompt(intent, available_tools)
        plan = await self._generate_plan(
            prompt, session_id, available_tools, log
        )

        log.info(
            "planning_success",
            step_count=len(plan.steps),
            plan_id=plan.plan_id,
        )
        return plan

    async def replan(
        self,
        original_plan: Plan,
        failed_step_id: str,
        error_context: str,
    ) -> Plan:
        """Generate a revised plan after a step failure.

        Args:
            original_plan: The plan that failed.
            failed_step_id: ID of the step that failed.
            error_context: Error message or context from the failure.

        Returns:
            Revised Plan with adjusted steps.

        Raises:
            PlanningError: If replanning fails after retries.
        """
        log = logger.bind(
            plan_id=original_plan.plan_id,
            failed_step_id=failed_step_id,
        )
        log.info("replan_start")

        # Extract available tools from original plan steps
        available_tools = list({step.tool_name for step in original_plan.steps})

        original_plan_json = original_plan.model_dump_json(indent=2)
        system = _REPLAN_SYSTEM_PROMPT.format(
            original_plan=original_plan_json,
            failed_step_id=failed_step_id,
            error_context=error_context,
            available_tools=json.dumps(available_tools),
        )

        messages = [{"role": "user", "content": "Generate a revised plan."}]

        plan = await self._call_and_validate(
            system, messages, original_plan.session_id, available_tools, log
        )

        log.info("replan_success", step_count=len(plan.steps))
        return plan

    def _build_plan_prompt(
        self,
        intent: IntentResult,
        available_tools: list[str],
    ) -> str:
        """Build the system prompt for plan generation."""
        return _PLANNER_SYSTEM_PROMPT.format(
            available_tools=json.dumps(available_tools, indent=2),
            max_steps=self._settings.max_plan_steps,
        )

    async def _generate_plan(
        self,
        system_prompt: str,
        session_id: str,
        available_tools: list[str],
        log: Any,
    ) -> Plan:
        """Generate and validate a plan with retry on tool validation failure."""
        user_content = (
            "Create an execution plan for the given intent. "
            "Use only the available tools listed in the system prompt."
        )
        messages = [{"role": "user", "content": user_content}]

        return await self._call_and_validate(
            system_prompt, messages, session_id, available_tools, log
        )

    async def _call_and_validate(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        session_id: str,
        available_tools: list[str],
        log: Any,
    ) -> Plan:
        """Call LLM and validate the plan, retrying on failures."""
        last_error: Exception | None = None

        for attempt in range(self._settings.plan_max_retries + 1):
            try:
                raw = await self._call_llm(system_prompt, messages)
                steps = self._parse_steps(raw)
                self._validate_tools(steps, available_tools)
                self._mark_high_risk_steps(steps)

                plan = Plan(
                    plan_id=f"plan_{uuid.uuid4().hex[:12]}",
                    session_id=session_id,
                    steps=steps,
                )
                return plan

            except UnknownToolError as e:
                last_error = e
                log.warning(
                    "planning_invalid_tool",
                    tool_name=e.tool_name,
                    attempt=attempt,
                )
                # Add correction hint to messages for retry
                messages.append({
                    "role": "assistant",
                    "content": raw if "raw" in dir() else "",  # noqa: F821
                })
                messages.append({
                    "role": "user",
                    "content": (
                        f"Error: tool '{e.tool_name}' is not available. "
                        f"Please use only these tools: {json.dumps(available_tools)}"
                    ),
                })
                continue

            except (json.JSONDecodeError, KeyError, ValueError) as e:
                last_error = e
                log.warning(
                    "planning_parse_error",
                    attempt=attempt,
                    error=str(e),
                )
                continue

        raise PlanningError(
            f"Failed to generate valid plan after "
            f"{self._settings.plan_max_retries + 1} attempts: {last_error}",
            attempts=self._settings.plan_max_retries + 1,
        )

    @trace_llm_call  # type: ignore[untyped-decorator]
    async def _call_llm(
        self, system_prompt: str, messages: list[dict[str, str]]
    ) -> str:
        """Call Claude API for plan generation."""
        response = await self._client.messages.create(
            model=self._settings.anthropic_model,
            max_tokens=4096,
            system=system_prompt,
            messages=messages,  # type: ignore[arg-type]
        )
        text_block = response.content[0]
        if hasattr(text_block, "text"):
            return text_block.text
        raise PlanningError("LLM response has no text content")

    def _parse_steps(self, raw: str) -> list[PlanStep]:
        """Parse raw LLM JSON into PlanStep list."""
        data = json.loads(raw)
        steps_data = data.get("steps", data) if isinstance(data, dict) else data

        if not isinstance(steps_data, list):
            raise ValueError(f"Expected list of steps, got {type(steps_data)}")

        steps: list[PlanStep] = []
        for i, step_data in enumerate(steps_data):
            step = PlanStep(
                step_id=step_data.get("step_id", f"step_{i + 1}"),
                tool_name=step_data["tool_name"],
                tool_args=step_data.get("tool_args", {}),
                depends_on=step_data.get("depends_on", []),
                description=step_data.get("description", ""),
                estimated_duration_s=step_data.get("estimated_duration_s"),
            )
            steps.append(step)

        return steps

    def _validate_tools(
        self, steps: list[PlanStep], available_tools: list[str]
    ) -> None:
        """Validate all tool_names against the capability manifest whitelist."""
        tool_set = set(available_tools)
        for step in steps:
            if step.tool_name not in tool_set:
                raise UnknownToolError(step.tool_name, available_tools)

    def _mark_high_risk_steps(self, steps: list[PlanStep]) -> None:
        """Mark steps that require human confirmation."""
        for step in steps:
            if "." in step.tool_name:
                tool_base = step.tool_name.split(".")[-1]
            else:
                tool_base = step.tool_name
            if (
                step.tool_name in HIGH_RISK_TOOL_NAMES
                or any(
                    tool_base.startswith(p)
                    for p in HIGH_RISK_TOOL_PREFIXES
                )
            ):
                step.requires_confirm = True

    def _plan_from_skill(self, skill: Any, session_id: str) -> Plan:
        """Create a Plan from a pre-existing Skill template."""
        steps = [
            PlanStep(
                step_id=s.get("step_id", f"step_{i + 1}"),
                tool_name=s["tool_name"],
                tool_args=s.get("tool_args", {}),
                depends_on=s.get("depends_on", []),
                description=s.get("description", ""),
                requires_confirm=s.get("requires_confirm", False),
                estimated_duration_s=s.get("estimated_duration_s"),
            )
            for i, s in enumerate(skill.steps)
        ]

        self._mark_high_risk_steps(steps)

        return Plan(
            plan_id=f"plan_{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            steps=steps,
            skill_id=getattr(skill, "id", None),
        )
