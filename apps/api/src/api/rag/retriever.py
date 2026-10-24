"""Similarity retrieval over reviewed, active public knowledge sources."""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.rag.embeddings import EmbeddingProvider
from api.rag.models import KnowledgeChunk, KnowledgeDocument
from api.rag.schemas import RAGQuery, RetrievedChunk


class KnowledgeRetriever:
    """Retrieve approved sources filtered by language and astrology tradition."""
    def __init__(self, embedder: EmbeddingProvider, *, default_top_k: int = 5):
        if not 1 <= default_top_k <= 20:
            raise ValueError("default_top_k must be between 1 and 20")
        self.embedder = embedder
        self.default_top_k = default_top_k

    async def retrieve(self, session: AsyncSession, query: RAGQuery) -> list[RetrievedChunk]:
        vectors = await self.embedder.embed([query.query])
        if len(vectors) != 1 or len(vectors[0]) != self.embedder.dimensions:
            raise RuntimeError("Embedding provider returned an unexpected vector shape")
        vector = vectors[0]
        distance_expr = KnowledgeChunk.embedding.cosine_distance(vector)
        stmt = (
            select(KnowledgeChunk, KnowledgeDocument, distance_expr.label("distance"))
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(
                KnowledgeDocument.is_active.is_(True),
                KnowledgeDocument.review_status == "approved",
                or_(
                    KnowledgeDocument.astrology_system == query.astrology_system,
                    KnowledgeDocument.astrology_system == "both",
                ),
                KnowledgeDocument.language == query.language,
            )
            .order_by(distance_expr)
            .limit(query.top_k or self.default_top_k)
        )
        rows = (await session.execute(stmt)).all()
        return [
            RetrievedChunk(
                chunk_id=str(chunk.id), source_id=document.source_id, title=document.title,
                text=chunk.text, language=document.language, astrology_system=document.astrology_system,
                topic=document.topic, source_uri=document.source_uri,
                score=max(0.0, min(1.0, 1.0 - float(distance))) if distance is not None else None,
            )
            for chunk, document, distance in rows
        ]
