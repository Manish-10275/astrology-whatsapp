"""Deterministic, heading-aware chunking for curated Markdown sources."""
from __future__ import annotations

import re

from api.rag.schemas import TextChunk

_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")


def chunk_markdown(text: str, *, max_chars: int = 1800, overlap_chars: int = 180) -> list[TextChunk]:
    """Split Markdown into stable chunks while retaining heading context."""
    if max_chars < 100:
        raise ValueError("max_chars must be at least 100")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be >= 0 and smaller than max_chars")

    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    sections: list[tuple[str | None, str]] = []
    heading: str | None = None
    lines: list[str] = []
    for line in normalized.splitlines():
        match = _HEADING.match(line)
        if match:
            if lines:
                sections.append((heading, "\n".join(lines).strip()))
            heading = match.group(2).strip()
            lines = [line.strip()]
        else:
            lines.append(line)
    if lines:
        sections.append((heading, "\n".join(lines).strip()))

    result: list[TextChunk] = []
    for section_heading, section in sections:
        if not section:
            continue
        prefix = f"Section: {section_heading}\n" if section_heading else ""
        budget = max_chars - len(prefix)
        if budget <= 0:
            prefix, budget = "", max_chars
        start = 0
        while start < len(section):
            end = min(start + budget, len(section))
            if end < len(section):
                boundary = max(section.rfind("\n\n", start, end), section.rfind(". ", start, end))
                if boundary > start + int(budget * 0.55):
                    end = boundary + (2 if section[boundary : boundary + 2] == "\n\n" else 1)
            piece = section[start:end].strip()
            if piece:
                result.append(TextChunk(len(result), f"{prefix}{piece}".strip(), section_heading))
            if end >= len(section):
                break
            start = max(start + 1, end - overlap_chars)
    return result
