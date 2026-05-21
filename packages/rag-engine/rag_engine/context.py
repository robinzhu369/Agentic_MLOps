"""R-09: Context injection — format RAG results for Agent LLM prompts."""
from __future__ import annotations

from typing import Any

import structlog
from pydantic import BaseModel, Field

from .retrieval import SearchResult, VectorStore

logger = structlog.get_logger(__name__)

# Domain routing rules (keyword-based, no LLM call)
DOMAIN_ROUTING_RULES: dict[str, list[str]] = {
    "compliance": [
        "合规", "监管", "法规", "KYC", "AML", "反洗钱", "compliance",
    ],
    "aml": [
        "洗钱", "可疑交易", "风险评分", "黑名单", "suspicious",
    ],
    "feature-template": [
        "特征", "feature", "特征工程", "特征视图", "feature view",
    ],
}

CONTEXT_TEMPLATE = """<context>
以下是从知识库检索到的相关文档片段，请参考这些信息回答问题：

{chunks}

来源：{sources}
</context>"""


class ContextResult(BaseModel):
    """Result of context injection."""

    context: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    chunk_count: int = 0
    domain_used: str = "general"
    truncated: bool = False


def route_domain(query: str) -> str:
    """Route query to appropriate knowledge domain.

    Uses keyword matching to determine the most relevant domain.
    Falls back to 'general' if no match.

    Args:
        query: User query text.

    Returns:
        Domain string (compliance, aml, feature-template, general).
    """
    query_lower = query.lower()
    scores: dict[str, int] = {}

    for domain, keywords in DOMAIN_ROUTING_RULES.items():
        score = sum(
            1 for kw in keywords if kw.lower() in query_lower
        )
        if score > 0:
            scores[domain] = score

    if scores:
        return max(scores, key=scores.get)  # type: ignore[arg-type]
    return "general"


def format_context(
    results: list[SearchResult],
    max_tokens: int = 4096,
) -> ContextResult:
    """Format search results into context for LLM injection.

    Truncates if total text exceeds max_tokens (estimated at 2 chars/token).

    Args:
        results: Search results to format.
        max_tokens: Maximum context tokens (approx 2 chars per token).

    Returns:
        ContextResult with formatted context string.
    """
    if not results:
        return ContextResult(
            context="",
            chunk_count=0,
            domain_used="general",
        )

    # Estimate: ~2 characters per token for Chinese/mixed text
    max_chars = max_tokens * 2
    chunks_text: list[str] = []
    sources: list[dict[str, Any]] = []
    total_chars = 0
    truncated = False

    for result in results:
        chunk_text = f"[{result.section_title or 'N/A'}]\n{result.text}"
        if total_chars + len(chunk_text) > max_chars:
            truncated = True
            break

        chunks_text.append(chunk_text)
        sources.append({
            "document_id": result.document_id,
            "section_title": result.section_title,
            "score": round(result.score, 3),
        })
        total_chars += len(chunk_text)

    formatted_chunks = "\n\n---\n\n".join(chunks_text)
    source_str = ", ".join(
        s.get("section_title", "unknown") for s in sources
    )

    context = CONTEXT_TEMPLATE.format(
        chunks=formatted_chunks,
        sources=source_str,
    )

    domain_used = results[0].domain if results else "general"

    return ContextResult(
        context=context,
        sources=sources,
        chunk_count=len(chunks_text),
        domain_used=domain_used,
        truncated=truncated,
    )


def rag_search(
    query: str,
    vector_store: VectorStore,
    domain: str = "auto",
    top_k: int = 5,
    max_context_tokens: int = 4096,
) -> ContextResult:
    """Execute RAG search and format context for Agent.

    This is the main entry point used by the MCP tool.

    Args:
        query: Natural language query.
        vector_store: Initialized VectorStore instance.
        domain: Knowledge domain ('auto' for automatic routing).
        top_k: Number of chunks to retrieve.
        max_context_tokens: Max tokens for context injection.

    Returns:
        ContextResult with formatted context and sources.
    """
    # Route domain if auto
    domain_resolved = route_domain(query) if domain == "auto" else domain

    # Search (use None for 'general' to skip domain filter)
    search_domain = (
        domain_resolved if domain_resolved != "general" else None
    )
    response = vector_store.search(
        query=query,
        top_k=top_k,
        domain=search_domain,
    )

    if not response.results:
        logger.info(
            "rag_search_empty",
            query=query[:50],
            domain=domain_resolved,
        )
        return ContextResult(
            context="未找到相关文档。",
            chunk_count=0,
            domain_used=domain_resolved,
        )

    result = format_context(
        response.results, max_tokens=max_context_tokens
    )
    result.domain_used = domain_resolved

    logger.info(
        "rag_context_injected",
        query=query[:50],
        domain=domain_resolved,
        chunk_count=result.chunk_count,
        truncated=result.truncated,
    )
    return result
