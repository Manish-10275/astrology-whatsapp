"""Tests for educational routing and source citation validation."""
from api.rag.schemas import RetrievedChunk
from api.services.knowledge_rag import (
    format_source_references,
    is_general_knowledge_question,
    validate_source_citations,
)


def test_educational_astrology_questions_use_rag():
    assert is_general_knowledge_question("What is a nakshatra?")
    assert is_general_knowledge_question("Explain Sade Sati")
    assert is_general_knowledge_question("Dasha ka matlab kya hai?")
    assert is_general_knowledge_question("What does the 7th house mean?")


def test_personal_or_action_requests_are_not_routed_to_knowledge_rag():
    assert not is_general_knowledge_question("When will I get my job?")
    assert not is_general_knowledge_question("What is my moon sign?")
    assert not is_general_knowledge_question("Calculate my kundli")
    assert not is_general_knowledge_question("Hello")
    assert not is_general_knowledge_question("What is the weather today?")


def test_citation_validation_requires_known_source_ids():
    assert validate_source_citations(
        "Nakshatras are lunar mansions [source:vedic-001].",
        {"vedic-001"},
    )
    assert not validate_source_citations("Nakshatras are lunar mansions.", {"vedic-001"})
    assert not validate_source_citations(
        "This is cited [source:made-up].",
        {"vedic-001"},
    )
    assert not validate_source_citations(
        "Good [source:vedic-001], bad [source:made-up].",
        {"vedic-001"},
    )


def test_source_references_only_include_cited_retrieved_sources_and_safe_urls():
    chunks = [
        RetrievedChunk(
            chunk_id="1", source_id="vedic-001", title="Nakshatra Primer",
            text="Reference", language="en", astrology_system="vedic", topic="nakshatra",
            source_uri="https://example.org/nakshatra",
        ),
        RetrievedChunk(
            chunk_id="2", source_id="vedic-002", title="Not cited",
            text="Other reference", language="en", astrology_system="vedic", topic="general",
            source_uri="javascript:alert(1)",
        ),
    ]
    result = format_source_references(chunks, ["vedic-001", "vedic-001", "not-retrieved"])
    assert result.count("vedic-001") == 1
    assert "https://example.org/nakshatra" in result
    assert "Not cited" not in result
    assert "javascript:" not in result
