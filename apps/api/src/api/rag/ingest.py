"""Transactional ingestion primitives for reviewed Markdown/text sources."""
from __future__ import annotations

import hashlib

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.rag.chunking import chunk_markdown
from api.rag.embeddings import EmbeddingProvider
from api.rag.models import KnowledgeChunk, KnowledgeDocument
from api.rag.schemas import KnowledgeDocumentInput


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def ingest_document(
    session: AsyncSession,
    document: KnowledgeDocumentInput,
    embedder: EmbeddingProvider,
    *,
    chunk_max_chars: int = 1800,
    chunk_overlap_chars: int = 180,
) -> int:
    """Upsert a source; the caller owns commit/rollback."""
    content_hash = sha256_text(document.text)
    stmt = select(KnowledgeDocument).where(KnowledgeDocument.source_id == document.source_id)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if (
        existing
        and existing.content_hash == content_hash
        and existing.document_version == document.document_version
        and existing.review_status == document.review_status
    ):
        count_stmt = select(func.count(KnowledgeChunk.id)).where(KnowledgeChunk.document_id == existing.id)
        return int((await session.execute(count_stmt)).scalar_one())

    pieces = chunk_markdown(document.text, max_chars=chunk_max_chars, overlap_chars=chunk_overlap_chars)
    vectors = await embedder.embed([piece.text for piece in pieces])
    if len(vectors) != len(pieces) or any(len(vector) != embedder.dimensions for vector in vectors):
        raise RuntimeError("Embedding provider returned an unexpected number or shape of vectors")

    if existing:
        await session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == existing.id))
        await session.delete(existing)
        await session.flush()

    record = KnowledgeDocument(
        source_id=document.source_id, title=document.title, source_uri=document.source_uri,
        source_type=document.source_type, license_name=document.license_name, language=document.language,
        astrology_system=document.astrology_system, topic=document.topic, document_version=document.document_version,
        content_hash=content_hash, review_status=document.review_status,
        is_active=document.review_status == "approved",
    )
    session.add(record)
    await session.flush()
    for piece, vector in zip(pieces, vectors, strict=True):
        session.add(KnowledgeChunk(
            document_id=record.id, chunk_index=piece.chunk_index, text=piece.text, heading=piece.heading,
            metadata_json={"language": document.language, "astrology_system": document.astrology_system, "topic": document.topic},
            content_hash=sha256_text(piece.text), embedding=vector,
        ))
    await session.flush()
    return len(pieces)
