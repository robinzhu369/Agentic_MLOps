"""R-01/R-02: Document ingestion and chunking."""
from __future__ import annotations

import hashlib
import re
from enum import StrEnum
from typing import Any

import structlog
from pydantic import BaseModel, Field

from .config import RAGSettings, get_rag_settings

logger = structlog.get_logger(__name__)


class DocumentType(StrEnum):
    """Supported document types."""

    PDF = "pdf"
    MARKDOWN = "markdown"
    WIKI = "wiki"


class Chunk(BaseModel):
    """A single text chunk from a document."""

    chunk_id: str
    document_id: str
    text: str
    section_title: str = ""
    domain: str = "general"
    metadata: dict[str, Any] = Field(default_factory=dict)
    chunk_index: int = 0


class DocumentRecord(BaseModel):
    """Metadata for an ingested document."""

    document_id: str
    title: str
    source_type: DocumentType
    domain: str
    chunk_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)


def generate_document_id(source: str, domain: str) -> str:
    """Generate deterministic document ID for idempotency."""
    content = f"{source}:{domain}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def parse_markdown(content: str, title: str = "") -> list[dict[str, str]]:
    """Parse Markdown into sections by heading.

    Args:
        content: Raw Markdown text.
        title: Document title (used if no H1 found).

    Returns:
        List of dicts with 'title' and 'text' keys.
    """
    sections: list[dict[str, str]] = []
    current_title = title or "Introduction"
    current_text: list[str] = []

    for line in content.split("\n"):
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            # Save previous section
            if current_text:
                text = "\n".join(current_text).strip()
                if text:
                    sections.append({
                        "title": current_title,
                        "text": text,
                    })
            current_title = heading_match.group(2).strip()
            current_text = []
        else:
            current_text.append(line)

    # Save last section
    if current_text:
        text = "\n".join(current_text).strip()
        if text:
            sections.append({"title": current_title, "text": text})

    return sections


def chunk_text(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
) -> list[str]:
    """Split text into overlapping chunks by character count.

    Tries to split on sentence boundaries when possible.

    Args:
        text: Input text to chunk.
        chunk_size: Target chunk size in characters.
        chunk_overlap: Overlap between consecutive chunks.

    Returns:
        List of text chunks.
    """
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end < len(text):
            # Try to break at sentence boundary
            boundary = text.rfind("。", start, end)
            if boundary == -1:
                boundary = text.rfind(". ", start, end)
            if boundary == -1:
                boundary = text.rfind("\n", start, end)
            if boundary > start:
                end = boundary + 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - chunk_overlap

    return chunks


def ingest_markdown(
    content: str,
    title: str,
    domain: str,
    source: str = "",
    metadata: dict[str, Any] | None = None,
    settings: RAGSettings | None = None,
) -> tuple[DocumentRecord, list[Chunk]]:
    """Ingest a Markdown document into chunks.

    Args:
        content: Raw Markdown content.
        title: Document title.
        domain: Knowledge domain (compliance, aml, feature-template).
        source: Source identifier for document ID generation.
        metadata: Additional metadata to attach.
        settings: RAG settings (uses defaults if None).

    Returns:
        Tuple of (DocumentRecord, list of Chunks).
    """
    settings = settings or get_rag_settings()
    doc_id = generate_document_id(source or title, domain)
    extra_meta = metadata or {}

    sections = parse_markdown(content, title)
    chunks: list[Chunk] = []
    chunk_idx = 0

    for section in sections:
        text_chunks = chunk_text(
            section["text"],
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
        for text in text_chunks:
            chunk = Chunk(
                chunk_id=f"{doc_id}_c{chunk_idx:04d}",
                document_id=doc_id,
                text=text,
                section_title=section["title"],
                domain=domain,
                metadata=extra_meta,
                chunk_index=chunk_idx,
            )
            chunks.append(chunk)
            chunk_idx += 1

    record = DocumentRecord(
        document_id=doc_id,
        title=title,
        source_type=DocumentType.MARKDOWN,
        domain=domain,
        chunk_count=len(chunks),
        metadata=extra_meta,
    )

    logger.info(
        "document_ingested",
        document_id=doc_id,
        title=title,
        domain=domain,
        chunk_count=len(chunks),
    )
    return record, chunks
