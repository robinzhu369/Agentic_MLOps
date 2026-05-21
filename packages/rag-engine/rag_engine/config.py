"""RAG Engine configuration via pydantic-settings."""
from __future__ import annotations

from pydantic_settings import BaseSettings


class RAGSettings(BaseSettings):
    """RAG Engine settings loaded from environment variables."""

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "rag_chunks"

    # Embedding
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dimension: int = 512

    # Chunking
    chunk_size: int = 512
    chunk_overlap: int = 64

    # Search
    default_top_k: int = 10
    score_threshold: float = 0.5
    max_context_tokens: int = 4096

    model_config = {"env_prefix": "RAG_", "extra": "ignore"}


_settings: RAGSettings | None = None


def get_rag_settings() -> RAGSettings:
    """Get RAG settings (cached singleton)."""
    global _settings  # noqa: PLW0603
    if _settings is None:
        _settings = RAGSettings()
    return _settings
