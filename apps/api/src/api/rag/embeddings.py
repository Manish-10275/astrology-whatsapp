"""Embedding-provider protocol and OpenAI implementation."""
from __future__ import annotations

from typing import Protocol, Sequence


class EmbeddingProvider(Protocol):
    @property
    def dimensions(self) -> int: ...

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class OpenAIEmbeddingProvider:
    """Async OpenAI embedding adapter for the fixed pgvector schema."""
    def __init__(self, api_key: str, model: str = "text-embedding-3-small", dimensions: int = 1536):
        if not api_key:
            raise ValueError("An embedding API key is required")
        if dimensions != 1536:
            raise ValueError("The current schema supports 1536-dimensional embeddings only")
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        from openai import AsyncOpenAI

        async with AsyncOpenAI(api_key=self._api_key) as client:
            result = await client.embeddings.create(
                model=self._model, input=list(texts), dimensions=self._dimensions
            )
        ordered = sorted(result.data, key=lambda item: item.index)
        vectors = [item.embedding for item in ordered]
        if len(vectors) != len(texts) or any(len(vector) != self._dimensions for vector in vectors):
            raise RuntimeError("Embedding provider returned an unexpected vector shape")
        return vectors
