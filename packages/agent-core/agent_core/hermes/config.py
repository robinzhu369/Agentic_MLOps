"""Agent Core configuration via pydantic-settings."""
from __future__ import annotations

from pydantic_settings import BaseSettings


class AgentCoreSettings(BaseSettings):
    """Agent Core specific settings loaded from environment variables."""

    # LLM
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    # Intent parsing
    intent_confidence_threshold: float = 0.7
    intent_max_retries: int = 2

    # Planning
    max_plan_steps: int = 20
    max_replans: int = 2
    plan_max_retries: int = 2

    # Execution
    max_retries_per_step: int = 3
    max_concurrent_steps: int = 3

    # MCP Gateway
    mcp_gateway_base_url: str = "http://localhost:8100"

    model_config = {"env_prefix": "AGENT_", "extra": "ignore"}


_settings: AgentCoreSettings | None = None


def get_agent_settings() -> AgentCoreSettings:
    """Get agent core settings (cached singleton)."""
    global _settings  # noqa: PLW0603
    if _settings is None:
        _settings = AgentCoreSettings()
    return _settings
