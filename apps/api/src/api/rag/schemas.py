"""Typed contracts for curated astrology knowledge ingestion and retrieval."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AstrologyTradition = Literal["vedic", "western", "both"]


class KnowledgeDocumentInput(BaseModel):
    """A reviewed-source candidate submitted to the ingestion service."""
    model_config = ConfigDict(str_strip_whitespace=True)
    source_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=2_000_000)
    language: str = Field(default="en", min_length=2, max_length=10)
    astrology_system: AstrologyTradition = "both"
    topic: str = Field(default="general", min_length=1, max_length=100)
    source_type: str = Field(default="curated", min_length=1, max_length=50)
    license_name: str = Field(default="internal-review-required", max_length=255)
    source_uri: str | None = Field(default=None, max_length=2048)
    document_version: str = Field(default="1", max_length=64)
    review_status: Literal["draft", "approved", "rejected"] = "draft"


class RetrievedChunk(BaseModel):
    """A retrieved chunk and source provenance."""
    chunk_id: str
    source_id: str
    title: str
    text: str
    language: str
    astrology_system: AstrologyTradition
    topic: str
    source_uri: str | None = None
    score: float | None = None


class RAGQuery(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    language: str = Field(default="en", min_length=2, max_length=10)
    astrology_system: Literal["vedic", "western"] = "vedic"
    top_k: int | None = Field(default=None, ge=1, le=20)


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    text: str
    heading: str | None = None
