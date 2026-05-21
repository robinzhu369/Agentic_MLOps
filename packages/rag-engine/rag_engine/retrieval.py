"""R-04/R-07: Vector search via Qdrant with metadata filtering."""
from __future__ import annotations

import time
from typing import Any

import structlog
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from .config import RAGSettings, get_rag_settings
from .embedding import embed_query, embed_texts
from .ingestion import Chunk

logger = structlog.get_logger(__name__)


# --- Models ---


class SearchResult(BaseModel):
    """A single search result."""

    chunk_id: str
    document_id: str
    text: str
    score: float
    section_title: str | None = None
    domain: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """Search response with results and metadata."""

    query: str
    results: list[SearchResult]
    total_found: int
    latency_ms: float
    retrieval_type: str = "vector"


# --- Retrieval ---


class VectorStore:
    """Qdrant-backed vector store for RAG chunks.

    Handles collection management, indexing, and search.
    """

    def __init__(self, settings: RAGSettings | None = None) -> None:
        self._settings = settings or get_rag_settings()
        self._client = QdrantClient(
            host=self._settings.qdrant_host,
            port=self._settings.qdrant_port,
        )
        self._collection = self._settings.qdrant_collection

    def ensure_collection(self) -> None:
        """Create collection if it doesn't exist."""
        collections = self._client.get_collections().collections
        names = [c.name for c in collections]

        if self._collection not in names:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(
                    size=self._settings.embedding_dimension,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(
                "collection_created",
                name=self._collection,
                dimension=self._settings.embedding_dimension,
            )

    def index_chunks(self, chunks: list[Chunk]) -> int:
        """Index chunks into Qdrant.

        Args:
            chunks: List of Chunk objects to index.

        Returns:
            Number of chunks indexed.
        """
        if not chunks:
            return 0

        texts = [c.text for c in chunks]
        embeddings = embed_texts(texts, self._settings)

        points = [
            PointStruct(
                id=idx,
                vector=embedding,
                payload={
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "text": chunk.text,
                    "section_title": chunk.section_title,
                    "domain": chunk.domain,
                    "chunk_index": chunk.chunk_index,
                    **chunk.metadata,
                },
            )
            for idx, (chunk, embedding) in enumerate(
                zip(chunks, embeddings, strict=True)
            )
        ]

        # Upsert in batches of 100
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            self._client.upsert(
                collection_name=self._collection,
                points=batch,
            )

        logger.info(
            "chunks_indexed",
            count=len(chunks),
            collection=self._collection,
        )
        return len(chunks)

    def search(
        self,
        query: str,
        top_k: int | None = None,
        score_threshold: float | None = None,
        domain: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> SearchResponse:
        """Search for relevant chunks.

        Args:
            query: Natural language query.
            top_k: Number of results to return.
            score_threshold: Minimum similarity score.
            domain: Filter by knowledge domain.
            filters: Additional metadata filters.

        Returns:
            SearchResponse with ranked results.
        """
        start = time.time()
        top_k = top_k or self._settings.default_top_k
        score_threshold = (
            score_threshold
            if score_threshold is not None
            else self._settings.score_threshold
        )

        # Build query vector
        query_vector = embed_query(query, self._settings)

        # Build filter
        qdrant_filter = self._build_filter(domain, filters)

        # Execute search
        results = self._client.search(  # type: ignore[attr-defined]
            collection_name=self._collection,
            query_vector=query_vector,
            limit=top_k,
            score_threshold=score_threshold,
            query_filter=qdrant_filter,
        )

        latency_ms = (time.time() - start) * 1000

        search_results = [
            SearchResult(
                chunk_id=hit.payload.get("chunk_id", ""),
                document_id=hit.payload.get("document_id", ""),
                text=hit.payload.get("text", ""),
                score=hit.score,
                section_title=hit.payload.get("section_title"),
                domain=hit.payload.get("domain", ""),
                metadata={
                    k: v
                    for k, v in (hit.payload or {}).items()
                    if k
                    not in {
                        "chunk_id",
                        "document_id",
                        "text",
                        "section_title",
                        "domain",
                    }
                },
            )
            for hit in results
        ]

        logger.info(
            "search_completed",
            query=query[:50],
            results=len(search_results),
            latency_ms=round(latency_ms, 1),
            domain=domain,
        )

        return SearchResponse(
            query=query,
            results=search_results,
            total_found=len(search_results),
            latency_ms=round(latency_ms, 2),
        )

    def delete_document(self, document_id: str) -> None:
        """Delete all chunks for a document."""
        self._client.delete(
            collection_name=self._collection,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id),
                    )
                ]
            ),
        )
        logger.info(
            "document_deleted", document_id=document_id
        )

    def get_stats(self) -> dict[str, Any]:
        """Get collection statistics."""
        try:
            info = self._client.get_collection(self._collection)
            return {
                "total_chunks": info.points_count or 0,
                "collection": self._collection,
                "status": info.status.value,
            }
        except Exception:
            return {
                "total_chunks": 0,
                "collection": self._collection,
                "status": "not_found",
            }

    def _build_filter(
        self,
        domain: str | None,
        filters: dict[str, Any] | None,
    ) -> Filter | None:
        """Build Qdrant filter from domain and extra filters."""
        conditions = []

        if domain:
            conditions.append(
                FieldCondition(
                    key="domain",
                    match=MatchValue(value=domain),
                )
            )

        if filters:
            for key, value in filters.items():
                conditions.append(
                    FieldCondition(
                        key=key,
                        match=MatchValue(value=value),
                    )
                )

        if conditions:
            return Filter(must=conditions)  # type: ignore[arg-type]
        return None
