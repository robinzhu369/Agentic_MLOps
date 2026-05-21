"""A-07: Skill Library — reusable task templates with semantic search."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class SkillStep(BaseModel):
    """A single step in a Skill template."""

    tool_name: str
    tool_args_template: dict[str, Any] = Field(default_factory=dict)
    description: str
    requires_confirm: bool = False


class Skill(BaseModel):
    """A reusable task template."""

    skill_id: str = Field(
        default_factory=lambda: f"skill_{uuid.uuid4().hex[:8]}"
    )
    name: str
    description: str
    task_type: str
    steps: list[SkillStep]
    parameters: list[str] = Field(default_factory=list)
    usage_count: int = 0
    created_by: str = "system"
    created_at: str = Field(
        default_factory=lambda: datetime.now(tz=UTC).isoformat()
    )
    is_public: bool = False


class SkillSearchResult(BaseModel):
    """A skill with its similarity score."""

    skill: Skill
    similarity: float


class SkillLibrary:
    """In-memory Skill Library with keyword-based search for MVP.

    Production would use pgvector for semantic search via A-06.
    """

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}
        self._load_builtin_skills()

    async def search(
        self,
        query: str,
        user_id: str = "",
        top_k: int = 3,
        similarity_threshold: float = 0.8,
    ) -> list[SkillSearchResult]:
        """Search for matching Skills by keyword similarity.

        Args:
            query: Task description to match against.
            user_id: Current user (for visibility filtering).
            top_k: Max results to return.
            similarity_threshold: Min similarity score.

        Returns:
            Skills sorted by similarity descending.
        """
        query_lower = query.lower()
        results: list[SkillSearchResult] = []

        for skill in self._skills.values():
            if not skill.is_public and skill.created_by != user_id:
                continue

            # Simple keyword overlap scoring
            score = self._compute_similarity(
                query_lower, skill
            )
            if score >= similarity_threshold:
                results.append(
                    SkillSearchResult(skill=skill, similarity=score)
                )

        results.sort(key=lambda r: r.similarity, reverse=True)
        return results[:top_k]

    async def get_skill(self, skill_id: str) -> Skill | None:
        """Retrieve a Skill by ID."""
        return self._skills.get(skill_id)

    async def create_skill(
        self,
        skill: Skill,
        user_id: str = "",
    ) -> str:
        """Store a new Skill in the library.

        Args:
            skill: Skill to store.
            user_id: Creator user ID.

        Returns:
            skill_id of the created skill.
        """
        if not skill.skill_id:
            skill.skill_id = f"skill_{uuid.uuid4().hex[:8]}"
        skill.created_by = user_id or skill.created_by
        self._skills[skill.skill_id] = skill

        logger.info(
            "skill_created",
            skill_id=skill.skill_id,
            name=skill.name,
            task_type=skill.task_type,
        )
        return skill.skill_id

    async def list_skills(
        self,
        user_id: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Skill], int]:
        """List skills visible to user (own + public).

        Returns:
            Tuple of (skills page, total count).
        """
        visible = [
            s
            for s in self._skills.values()
            if s.is_public or s.created_by == user_id
        ]
        total = len(visible)
        start = (page - 1) * page_size
        end = start + page_size
        return visible[start:end], total

    async def increment_usage(self, skill_id: str) -> None:
        """Increment usage_count when a Skill is applied."""
        skill = self._skills.get(skill_id)
        if skill:
            skill.usage_count += 1

    def _compute_similarity(
        self, query: str, skill: Skill
    ) -> float:
        """Compute keyword-based similarity score."""
        skill_text = (
            f"{skill.name} {skill.description} "
            f"{skill.task_type}"
        ).lower()

        query_words = set(query.split())
        skill_words = set(skill_text.split())

        if not query_words:
            return 0.0

        overlap = query_words & skill_words
        return len(overlap) / max(len(query_words), 1)

    def _load_builtin_skills(self) -> None:
        """Load pre-built skills for common MLOps tasks."""
        builtins = [
            Skill(
                skill_id="skill_data_profiling",
                name="Data Profiling",
                description=(
                    "数据探查 data profiling EDA 探索性分析 "
                    "统计 分布 缺失值"
                ),
                task_type="query_data",
                steps=[
                    SkillStep(
                        tool_name="data_catalog.get_schema",
                        tool_args_template={
                            "table_name": "{{table_name}}"
                        },
                        description="获取表 schema",
                    ),
                    SkillStep(
                        tool_name="data_catalog.sample_rows",
                        tool_args_template={
                            "table_name": "{{table_name}}",
                            "n": 10,
                        },
                        description="采样数据预览",
                    ),
                    SkillStep(
                        tool_name="jupyter.execute_code",
                        tool_args_template={
                            "code": (
                                "import pandas as pd\n"
                                "df.describe()"
                            ),
                            "kernel_id": "{{kernel_id}}",
                        },
                        description="计算统计摘要",
                    ),
                ],
                parameters=["table_name", "kernel_id"],
                is_public=True,
                created_by="system",
            ),
            Skill(
                skill_id="skill_fraud_model_training",
                name="Fraud Model Training",
                description=(
                    "反欺诈 fraud detection 模型训练 "
                    "LightGBM 信用卡 creditcard train model"
                ),
                task_type="train_model",
                steps=[
                    SkillStep(
                        tool_name="data_catalog.get_schema",
                        tool_args_template={
                            "table_name": "{{dataset}}"
                        },
                        description="获取数据集 schema",
                    ),
                    SkillStep(
                        tool_name="jupyter.execute_code",
                        tool_args_template={
                            "code": (
                                "import pandas as pd\n"
                                "df = pd.read_csv('{{dataset}}.csv')\n"
                                "print(df.shape)"
                            ),
                            "kernel_id": "{{kernel_id}}",
                        },
                        description="加载数据集",
                    ),
                    SkillStep(
                        tool_name="jupyter.execute_code",
                        tool_args_template={
                            "code": (
                                "from sklearn.model_selection "
                                "import train_test_split\n"
                                "X = df.drop('{{target}}', axis=1)\n"
                                "y = df['{{target}}']\n"
                                "X_train, X_test, y_train, y_test = "
                                "train_test_split(X, y, test_size=0.2)"
                            ),
                            "kernel_id": "{{kernel_id}}",
                        },
                        description="特征/标签分割",
                    ),
                    SkillStep(
                        tool_name="jupyter.execute_code",
                        tool_args_template={
                            "code": (
                                "import lightgbm as lgb\n"
                                "model = lgb.LGBMClassifier()\n"
                                "model.fit(X_train, y_train)"
                            ),
                            "kernel_id": "{{kernel_id}}",
                        },
                        description="训练 LightGBM 模型",
                    ),
                    SkillStep(
                        tool_name="jupyter.execute_code",
                        tool_args_template={
                            "code": (
                                "from sklearn.metrics "
                                "import roc_auc_score\n"
                                "y_pred = model.predict_proba"
                                "(X_test)[:, 1]\n"
                                "auc = roc_auc_score(y_test, y_pred)\n"
                                "print(f'AUC: {auc:.4f}')"
                            ),
                            "kernel_id": "{{kernel_id}}",
                        },
                        description="评估模型 AUC",
                    ),
                ],
                parameters=[
                    "dataset",
                    "target",
                    "kernel_id",
                ],
                is_public=True,
                created_by="system",
            ),
            Skill(
                skill_id="skill_feature_engineering",
                name="Feature Engineering",
                description=(
                    "特征工程 feature engineering 特征创建 "
                    "注册 feature view store"
                ),
                task_type="analyze_features",
                steps=[
                    SkillStep(
                        tool_name="data_catalog.get_schema",
                        tool_args_template={
                            "table_name": "{{source_table}}"
                        },
                        description="查看源表结构",
                    ),
                    SkillStep(
                        tool_name="jupyter.execute_code",
                        tool_args_template={
                            "code": "# Feature engineering code",
                            "kernel_id": "{{kernel_id}}",
                        },
                        description="计算特征",
                    ),
                    SkillStep(
                        tool_name=(
                            "feature_store.register_feature_view"
                        ),
                        tool_args_template={
                            "name": "{{view_name}}",
                            "entities": "{{entities}}",
                            "features": "{{features}}",
                            "source_table": "{{source_table}}",
                        },
                        description="注册特征视图",
                        requires_confirm=True,
                    ),
                ],
                parameters=[
                    "source_table",
                    "view_name",
                    "entities",
                    "features",
                    "kernel_id",
                ],
                is_public=True,
                created_by="system",
            ),
        ]

        for skill in builtins:
            self._skills[skill.skill_id] = skill
