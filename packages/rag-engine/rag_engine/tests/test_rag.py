"""Unit tests for RAG Engine — ingestion, chunking, context injection."""
from __future__ import annotations

from unittest.mock import MagicMock

from rag_engine.config import RAGSettings
from rag_engine.context import (
    format_context,
    rag_search,
    route_domain,
)
from rag_engine.ingestion import (
    Chunk,
    DocumentRecord,
    chunk_text,
    generate_document_id,
    ingest_markdown,
    parse_markdown,
)
from rag_engine.retrieval import SearchResult

# --- Ingestion Tests ---


def test_parse_markdown_extracts_sections() -> None:
    """Test Markdown parsing splits by headings."""
    content = """# Title

Introduction text here.

## Section 1

Content of section 1.

## Section 2

Content of section 2.
"""
    sections = parse_markdown(content)
    assert len(sections) == 3
    assert sections[0]["title"] == "Title"
    assert "Introduction" in sections[0]["text"]
    assert sections[1]["title"] == "Section 1"
    assert sections[2]["title"] == "Section 2"


def test_parse_markdown_empty_content() -> None:
    """Test parsing empty content returns empty list."""
    sections = parse_markdown("")
    assert sections == []


def test_parse_markdown_no_headings() -> None:
    """Test parsing content without headings uses default title."""
    content = "Just some plain text\nwith multiple lines."
    sections = parse_markdown(content, title="Default")
    assert len(sections) == 1
    assert sections[0]["title"] == "Default"


def test_chunk_text_short_text() -> None:
    """Test that short text is returned as single chunk."""
    text = "Short text."
    chunks = chunk_text(text, chunk_size=512)
    assert len(chunks) == 1
    assert chunks[0] == "Short text."


def test_chunk_text_splits_long_text() -> None:
    """Test that long text is split into multiple chunks."""
    text = "A" * 1000
    chunks = chunk_text(text, chunk_size=300, chunk_overlap=50)
    assert len(chunks) > 1
    # Each chunk should be <= chunk_size
    for chunk in chunks:
        assert len(chunk) <= 300


def test_chunk_text_overlap() -> None:
    """Test that chunks have overlap."""
    text = "word " * 200  # 1000 chars
    chunks = chunk_text(text, chunk_size=200, chunk_overlap=50)
    assert len(chunks) > 1
    # Check overlap exists between consecutive chunks
    if len(chunks) >= 2:
        # Last part of chunk 0 should appear in start of chunk 1
        end_of_first = chunks[0][-50:]
        assert any(
            c in chunks[1] for c in end_of_first.split()
        )


def test_chunk_text_empty() -> None:
    """Test empty text returns empty list."""
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_generate_document_id_deterministic() -> None:
    """Test document ID is deterministic."""
    id1 = generate_document_id("source.md", "compliance")
    id2 = generate_document_id("source.md", "compliance")
    assert id1 == id2


def test_generate_document_id_unique() -> None:
    """Test different inputs produce different IDs."""
    id1 = generate_document_id("source1.md", "compliance")
    id2 = generate_document_id("source2.md", "compliance")
    assert id1 != id2


def test_ingest_markdown_produces_chunks() -> None:
    """Test full ingestion pipeline."""
    content = """# Anti-Money Laundering Rules

## Rule 1: Customer Due Diligence

Banks must verify customer identity before opening accounts.
This includes collecting government-issued ID and proof of address.

## Rule 2: Transaction Monitoring

All transactions above $10,000 must be reported.
Suspicious patterns should trigger alerts.
"""
    settings = RAGSettings(chunk_size=200, chunk_overlap=30)
    record, chunks = ingest_markdown(
        content=content,
        title="AML Rules",
        domain="aml",
        source="aml_rules.md",
        settings=settings,
    )

    assert isinstance(record, DocumentRecord)
    assert record.domain == "aml"
    assert record.chunk_count == len(chunks)
    assert record.chunk_count >= 2

    for chunk in chunks:
        assert isinstance(chunk, Chunk)
        assert chunk.document_id == record.document_id
        assert chunk.domain == "aml"
        assert chunk.text


# --- Context Injection Tests ---


def test_route_domain_compliance() -> None:
    """Test domain routing for compliance queries."""
    assert route_domain("什么是 KYC 要求？") == "compliance"
    assert route_domain("AML 合规检查流程") == "compliance"


def test_route_domain_aml() -> None:
    """Test domain routing for AML queries."""
    assert route_domain("如何识别可疑交易") == "aml"
    assert route_domain("黑名单筛查规则") == "aml"


def test_route_domain_feature() -> None:
    """Test domain routing for feature engineering queries."""
    assert route_domain("如何创建特征视图") == "feature-template"
    assert route_domain("feature engineering best practices") == "feature-template"


def test_route_domain_general() -> None:
    """Test domain routing falls back to general."""
    assert route_domain("hello world") == "general"
    assert route_domain("random question") == "general"


def test_format_context_empty_results() -> None:
    """Test formatting with no results."""
    result = format_context([])
    assert result.context == ""
    assert result.chunk_count == 0


def test_format_context_with_results() -> None:
    """Test formatting produces valid context."""
    results = [
        SearchResult(
            chunk_id="c1",
            document_id="d1",
            text="KYC requires identity verification.",
            score=0.92,
            section_title="KYC Rules",
            domain="compliance",
        ),
        SearchResult(
            chunk_id="c2",
            document_id="d1",
            text="Documents must be kept for 5 years.",
            score=0.85,
            section_title="Record Keeping",
            domain="compliance",
        ),
    ]

    result = format_context(results, max_tokens=4096)
    assert result.chunk_count == 2
    assert "<context>" in result.context
    assert "KYC" in result.context
    assert result.truncated is False
    assert len(result.sources) == 2


def test_format_context_truncation() -> None:
    """Test context truncation when exceeding max tokens."""
    results = [
        SearchResult(
            chunk_id=f"c{i}",
            document_id="d1",
            text="A" * 500,
            score=0.9 - i * 0.01,
            section_title=f"Section {i}",
            domain="compliance",
        )
        for i in range(20)
    ]

    # Very small token limit
    result = format_context(results, max_tokens=100)
    assert result.truncated is True
    assert result.chunk_count < 20


def test_rag_search_auto_domain() -> None:
    """Test rag_search with auto domain routing."""
    mock_store = MagicMock()
    mock_store.search.return_value = MagicMock(
        results=[
            SearchResult(
                chunk_id="c1",
                document_id="d1",
                text="KYC compliance text",
                score=0.9,
                section_title="KYC",
                domain="compliance",
            )
        ]
    )

    result = rag_search(
        query="什么是 KYC 合规要求",
        vector_store=mock_store,
        domain="auto",
    )

    assert result.domain_used == "compliance"
    assert result.chunk_count == 1
    mock_store.search.assert_called_once()


def test_rag_search_empty_results() -> None:
    """Test rag_search with no results."""
    mock_store = MagicMock()
    mock_store.search.return_value = MagicMock(results=[])

    result = rag_search(
        query="something obscure",
        vector_store=mock_store,
    )

    assert "未找到" in result.context
    assert result.chunk_count == 0
