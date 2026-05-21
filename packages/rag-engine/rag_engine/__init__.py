"""RAG Engine — Document ingestion, embedding, retrieval, context injection."""
from __future__ import annotations

from .config import RAGSettings, get_rag_settings
from .context import ContextResult, format_context, rag_search, route_domain
from .embedding import embed_query, embed_texts
from .ingestion import (
    Chunk,
    DocumentRecord,
    DocumentType,
    chunk_text,
    ingest_markdown,
    parse_markdown,
)
from .retrieval import SearchResponse, SearchResult, VectorStore

__all__ = [
    "Chunk",
    "ContextResult",
    "DocumentRecord",
    "DocumentType",
    "RAGSettings",
    "SearchResponse",
    "SearchResult",
    "VectorStore",
    "chunk_text",
    "embed_query",
    "embed_texts",
    "format_context",
    "get_rag_settings",
    "ingest_markdown",
    "parse_markdown",
    "rag_search",
    "route_domain",
]
