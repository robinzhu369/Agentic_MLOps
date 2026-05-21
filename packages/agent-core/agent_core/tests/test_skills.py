"""Tests for A-07 Skill Library and A-08 Self-Critique."""
from __future__ import annotations

import pytest

from agent_core.hermes.critic import SelfCritic
from agent_core.hermes.executor import (
    ExecutionState,
    Observation,
    StepStatus,
    TaskStatus,
)
from agent_core.skills.library import (
    Skill,
    SkillLibrary,
    SkillStep,
)

# --- Skill Library Tests ---


@pytest.fixture
def library() -> SkillLibrary:
    return SkillLibrary()


@pytest.mark.asyncio
async def test_library_has_builtin_skills(
    library: SkillLibrary,
) -> None:
    """Test that builtin skills are loaded."""
    skills, total = await library.list_skills()
    assert total == 3
    names = [s.name for s in skills]
    assert "Data Profiling" in names
    assert "Fraud Model Training" in names
    assert "Feature Engineering" in names


@pytest.mark.asyncio
async def test_library_search_finds_matching_skill(
    library: SkillLibrary,
) -> None:
    """Test semantic search finds relevant skills."""
    results = await library.search(
        query="fraud detection model train",
        similarity_threshold=0.3,
    )
    assert len(results) >= 1
    assert results[0].skill.name == "Fraud Model Training"


@pytest.mark.asyncio
async def test_library_search_no_match(
    library: SkillLibrary,
) -> None:
    """Test search returns empty for unrelated queries."""
    results = await library.search(
        query="completely unrelated xyz abc",
        similarity_threshold=0.8,
    )
    assert len(results) == 0


@pytest.mark.asyncio
async def test_library_create_skill(
    library: SkillLibrary,
) -> None:
    """Test creating a custom skill."""
    skill = Skill(
        name="Custom Pipeline",
        description="custom pipeline for testing",
        task_type="run_experiment",
        steps=[
            SkillStep(
                tool_name="jupyter.execute_code",
                tool_args_template={"code": "print('hi')"},
                description="Run code",
            ),
        ],
    )

    skill_id = await library.create_skill(skill, user_id="user_1")
    assert skill_id

    retrieved = await library.get_skill(skill_id)
    assert retrieved is not None
    assert retrieved.name == "Custom Pipeline"
    assert retrieved.created_by == "user_1"


@pytest.mark.asyncio
async def test_library_increment_usage(
    library: SkillLibrary,
) -> None:
    """Test usage count increment."""
    skill = await library.get_skill("skill_data_profiling")
    assert skill is not None
    assert skill.usage_count == 0

    await library.increment_usage("skill_data_profiling")

    skill = await library.get_skill("skill_data_profiling")
    assert skill is not None
    assert skill.usage_count == 1


@pytest.mark.asyncio
async def test_library_visibility_filtering(
    library: SkillLibrary,
) -> None:
    """Test that private skills are only visible to owner."""
    private_skill = Skill(
        name="Private Skill",
        description="private",
        task_type="query_data",
        steps=[],
        is_public=False,
    )
    await library.create_skill(private_skill, user_id="user_a")

    # user_a can see it
    skills_a, _ = await library.list_skills(user_id="user_a")
    names_a = [s.name for s in skills_a]
    assert "Private Skill" in names_a

    # user_b cannot see it (only public ones)
    skills_b, _ = await library.list_skills(user_id="user_b")
    names_b = [s.name for s in skills_b]
    assert "Private Skill" not in names_b


# --- Self-Critique Tests ---


@pytest.fixture
def critic() -> SelfCritic:
    return SelfCritic(pass_threshold=0.7)


@pytest.mark.asyncio
async def test_critic_perfect_execution(
    critic: SelfCritic,
) -> None:
    """Test high score for perfect execution."""
    state = ExecutionState(
        session_id="sess_1",
        plan_id="plan_1",
        task_status=TaskStatus.COMPLETED,
        step_states={
            "step_1": StepStatus.COMPLETED,
            "step_2": StepStatus.COMPLETED,
            "step_3": StepStatus.COMPLETED,
        },
        observations=[
            Observation(
                step_id="step_1",
                status=StepStatus.COMPLETED,
                retry_count=0,
            ),
            Observation(
                step_id="step_2",
                status=StepStatus.COMPLETED,
                retry_count=0,
            ),
            Observation(
                step_id="step_3",
                status=StepStatus.COMPLETED,
                retry_count=0,
            ),
        ],
    )

    result = await critic.evaluate(state)
    assert result.score >= 0.9
    assert result.passed is True


@pytest.mark.asyncio
async def test_critic_failed_execution(
    critic: SelfCritic,
) -> None:
    """Test low score for failed execution."""
    state = ExecutionState(
        session_id="sess_1",
        plan_id="plan_1",
        task_status=TaskStatus.FAILED,
        step_states={
            "step_1": StepStatus.COMPLETED,
            "step_2": StepStatus.FAILED,
        },
        observations=[
            Observation(
                step_id="step_1",
                status=StepStatus.COMPLETED,
                retry_count=0,
            ),
            Observation(
                step_id="step_2",
                status=StepStatus.FAILED,
                retry_count=3,
            ),
        ],
        replan_count=2,
    )

    result = await critic.evaluate(state)
    assert result.score < 0.7
    assert result.passed is False
    assert len(result.suggestions) > 0


@pytest.mark.asyncio
async def test_critic_partial_success(
    critic: SelfCritic,
) -> None:
    """Test moderate score for execution with retries."""
    state = ExecutionState(
        session_id="sess_1",
        plan_id="plan_1",
        task_status=TaskStatus.COMPLETED,
        step_states={
            "step_1": StepStatus.COMPLETED,
            "step_2": StepStatus.COMPLETED,
        },
        observations=[
            Observation(
                step_id="step_1",
                status=StepStatus.COMPLETED,
                retry_count=0,
            ),
            Observation(
                step_id="step_2",
                status=StepStatus.COMPLETED,
                retry_count=2,
            ),
        ],
        replan_count=1,
    )

    result = await critic.evaluate(state)
    assert 0.5 <= result.score <= 0.9
