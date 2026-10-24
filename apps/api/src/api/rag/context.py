"""Bounded formatting of retrieved evidence for a downstream generator."""
from __future__ import annotations

from api.rag.schemas import RetrievedChunk


def format_retrieved_context(chunks: list[RetrievedChunk], *, max_chars: int = 9000) -> str:
    """Format evidence with source IDs; callers must treat it as untrusted input."""
    if max_chars < 500:
        raise ValueError("max_chars must be at least 500")
    blocks: list[str] = []
    used = 0
    for chunk in chunks:
        title = chunk.title.replace("\n", " ").replace("\r", " ")
        source_id = chunk.source_id.replace("\n", " ").replace("\r", " ")
        block = (
            f"[SOURCE {source_id} | {title} | system={chunk.astrology_system} "
            f"| language={chunk.language}]\n{chunk.text.strip()}"
        )
        remaining = max_chars - used
        if remaining <= 0:
            break
        if len(block) > remaining:
            block = block[:remaining].rstrip()
        if block:
            blocks.append(block)
            used += len(block) + 2
    return "\n\n".join(blocks)


def allowed_source_ids(chunks: list[RetrievedChunk]) -> set[str]:
    """Return the source IDs an answer may cite for a given retrieval."""
    return {chunk.source_id for chunk in chunks}
