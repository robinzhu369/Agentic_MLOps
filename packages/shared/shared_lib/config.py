"""Shared configuration loaded from environment variables."""
from __future__ import annotations

from pydantic_settings import BaseSettings


class PostgresSettings(BaseSettings):
    host: str = "localhost"
    port: int = 5432
    user: str = "agentic"
    password: str = "agentic_dev"
    db: str = "agentic_mlops"

    model_config = {"env_prefix": "POSTGRES_"}

    @property
    def dsn(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"


class RedisSettings(BaseSettings):
    url: str = "redis://localhost:6379/0"

    model_config = {"env_prefix": "REDIS_"}


class QdrantSettings(BaseSettings):
    host: str = "localhost"
    port: int = 6333

    model_config = {"env_prefix": "QDRANT_"}


class OpenSearchSettings(BaseSettings):
    host: str = "localhost"
    port: int = 9200
    user: str = "admin"
    password: str = "Admin@123"

    model_config = {"env_prefix": "OPENSEARCH_"}


class MCPGatewaySettings(BaseSettings):
    host: str = "localhost"
    port: int = 8100
    jwt_secret_key: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    model_config = {"env_prefix": "MCP_GATEWAY_", "extra": "ignore"}


class AgentSettings(BaseSettings):
    api_host: str = "localhost"
    api_port: int = 8000
    intent_confidence_threshold: float = 0.7
    max_plan_steps: int = 20
    max_retries_per_step: int = 3
    max_replans: int = 2

    model_config = {"env_prefix": "AGENT_", "extra": "ignore"}


class RAGSettings(BaseSettings):
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    reranker_model: str = "BAAI/bge-reranker-base"
    top_k: int = 10
    score_threshold: float = 0.5

    model_config = {"env_prefix": "RAG_"}


class LLMSettings(BaseSettings):
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    model_config = {"env_prefix": ""}


class Settings(BaseSettings):
    """Aggregate settings — instantiate once at app startup."""

    postgres: PostgresSettings = PostgresSettings()
    redis: RedisSettings = RedisSettings()
    qdrant: QdrantSettings = QdrantSettings()
    opensearch: OpenSearchSettings = OpenSearchSettings()
    mcp_gateway: MCPGatewaySettings = MCPGatewaySettings()
    agent: AgentSettings = AgentSettings()
    rag: RAGSettings = RAGSettings()
    llm: LLMSettings = LLMSettings()


def get_settings() -> Settings:
    """Get application settings (cached)."""
    return Settings()
