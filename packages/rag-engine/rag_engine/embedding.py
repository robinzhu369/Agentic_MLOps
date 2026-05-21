"""R-03: Embedding generation using sentence-transformers."""
from __future__ import annotations

import structlog
from sentence_transformers import SentenceTransformer

from .config import RAGSettings, get_rag_settings

logger = structlog.get_logger(__name__)

_model: SentenceTransformer | None = None


def get_embedding_model(
    settings: RAGSettings | None = None,
) -> SentenceTransformer:
    """Get or initialize the embedding model (singleton).

    Args:
        settings: RAG settings with model name.

    Returns:
        Loaded SentenceTransformer model.
    """
    global _model  # noqa: PLW0603
    if _model is None:
        settings = settings or get_rag_settings()
        logger.info(
            "loading_embedding_model",
            model=settings.embedding_model,
        )
        _model = SentenceTransformer(settings.embedding_model)
    return _model


def embed_texts(
    texts: list[str],
    settings: RAGSettings | None = None,
) -> list[list[float]]:
    """Generate embeddings for a batch of texts.

    Args:
        texts: List of text strings to embed.
        settings: RAG settings.

    Returns:
        List of embedding vectors (list of floats).
    """
    model = get_embedding_model(settings)
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return embeddings.tolist()


def embed_query(
    query: str,
    settings: RAGSettings | None = None,
) -> list[float]:
    """Generate embedding for a single query.

    Args:
        query: Query text to embed.
        settings: RAG settings.

    Returns:
        Embedding vector as list of floats.
    """
    result = embed_texts([query], settings)
    return result[0]
