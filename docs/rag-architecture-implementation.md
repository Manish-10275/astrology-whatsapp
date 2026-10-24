# Astrology WhatsApp RAG implementation plan

## Scope

This first slice establishes knowledge-RAG storage and retrieval primitives. It intentionally leaves the WhatsApp message flow unchanged. RAG is disabled by default until a source corpus has been reviewed, ingested and evaluated.

## Target request flow

1. Receive a message through the existing signature-verified WhatsApp webhook.
2. Preserve deterministic commands and existing multi-turn conversation flows.
3. Classify the request as general knowledge, personal-context question, calculation request, or missing-input question.
4. For general knowledge, retrieve approved source chunks filtered by language and astrology tradition.
5. For birth-chart or timing calculations, call the existing astrology engine using validated inputs; do not ask the language model to calculate planetary positions.
6. Generate a grounded answer from retrieved sources and tool results. Cite only source IDs returned by the retriever.
7. Store conversation history through the existing encrypted persistence path.

## Data boundaries

- Knowledge RAG contains reviewed, rights-cleared astrology reference material and source metadata only.
- The existing encrypted birth profile remains the source of truth for birth date, time and place.
- Conversation history remains in the existing tables and retention/deletion lifecycle.
- User memory is not implemented by this change. Keep MEMORY_ENABLED=false until explicit consent, inspection, deletion and retention behavior are implemented and tested.
- Calculation output must come from the existing deterministic astrology engine, not a generated guess.

Personal fields must not be added to the shared knowledge index or sent to the embedding provider. Never retrieve one user's messages for another user.

## Knowledge schema and ingestion

The migration adds knowledge_documents (source, license, language, astrology tradition, topic, version, content hash, review status and activation state) and knowledge_chunks (text, heading, metadata, content hash and a 1536-dimensional embedding). A cosine-distance HNSW index supports candidate retrieval.

Ingestion is a service primitive, not a public endpoint. It is idempotent for unchanged source content and version and replaces stale chunks within the caller's transaction. Only curated sources whose license and factual quality have been reviewed should be submitted with review_status=approved. Draft and rejected sources are not retrievable.

The initial embedding adapter targets OpenAI text-embedding-3-small with 1536 dimensions. Any model/dimension change must be paired with a schema migration and corpus re-embedding.

## Prompt and retrieval safety

Retrieved passages are reference data, not instructions. The future generator must ignore commands contained inside retrieved documents, use them only as evidence, and express uncertainty when evidence is missing or conflicting. Bound the context size, restrict retrieval to approved sources, and allow citations only from the retrieved source ID set. Do not expose arbitrary source text as trusted system instructions.

The initial retriever filters active/approved status, language and astrology tradition before similarity ranking. It does not yet implement lexical/hybrid search, reranking or final-response citation validation; the related configuration flag is reserved and remains off.

## Rollout

1. Apply the migration in a disposable development database with PostgreSQL and the pgvector server extension installed.
2. Ingest a small, manually reviewed corpus with sources tagged by language, tradition and topic.
3. Test duplicate ingestion, source updates, review-state changes, language/tradition filters and empty retrieval.
4. Measure retrieval relevance on a curated query set before enabling user-facing generation.
5. Add planner/orchestrator integration and deterministic tool routing behind RAG_ENABLED.
6. Implement consent-gated user memory separately, including forget/delete and cross-user isolation tests.
7. Enable for internal test numbers, evaluate failures, then roll out gradually.

## Validation checklist

- [ ] Migration upgrades and downgrades on disposable PostgreSQL + pgvector.
- [ ] Ingestion is idempotent and rolls back atomically on embedding/database errors.
- [ ] Draft, rejected and inactive sources never appear in retrieval.
- [ ] Vedic and Western queries do not cross retrieval boundaries.
- [ ] Prompt injection in retrieved passages cannot override system/developer instructions.
- [ ] No birth data or personal conversation content enters the shared knowledge corpus.
- [ ] Existing WhatsApp webhook and conversation-state tests still pass.
- [ ] The feature remains off until orchestration, citations, memory policy and integration tests are complete.
