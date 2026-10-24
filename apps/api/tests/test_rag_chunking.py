"""Offline tests for deterministic chunking and source-attributed context."""
import pytest

from api.rag.chunking import chunk_markdown
from api.rag.context import allowed_source_ids, format_retrieved_context
from api.rag.schemas import RetrievedChunk


def test_empty_markdown_returns_no_chunks():
    assert chunk_markdown("  \n ") == []


def test_chunking_preserves_heading_context_and_is_deterministic():
    source = "# Nakshatra\n\n" + ("Nakshatras are lunar mansions. Useful context.\n\n" * 30)
    first = chunk_markdown(source, max_chars=300, overlap_chars=30)
    second = chunk_markdown(source, max_chars=300, overlap_chars=30)
    assert first == second
    assert len(first) > 1
    assert all("Section: Nakshatra" in chunk.text for chunk in first)
    assert [chunk.chunk_index for chunk in first] == list(range(len(first)))
    assert all(len(chunk.text) <= 300 for chunk in first)


def test_chunking_rejects_invalid_limits():
    with pytest.raises(ValueError):
        chunk_markdown("hello", max_chars=50)
    with pytest.raises(ValueError):
        chunk_markdown("hello", max_chars=100, overlap_chars=100)


def test_context_is_bounded_and_has_source_provenance():
    chunks = [RetrievedChunk(
        chunk_id="chunk-1", source_id="vedic-001", title="Dasha basics",
        text="Dasha is a period in a Vedic astrology system.", language="en",
        astrology_system="vedic", topic="dasha",
    )]
    formatted = format_retrieved_context(chunks, max_chars=500)
    assert "SOURCE vedic-001" in formatted
    assert "Dasha basics" in formatted
    assert len(formatted) <= 500
    assert allowed_source_ids(chunks) == {"vedic-001"}
