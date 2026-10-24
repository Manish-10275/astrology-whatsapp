"""Add reviewed astrology knowledge documents and pgvector chunks.

Revision ID: 7e2c9a4b6d10
Revises: 4a7b9c1d2e3f
Create Date: 2026-10-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision: str = "7e2c9a4b6d10"
down_revision: Union[str, None] = "4a7b9c1d2e3f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("source_uri", sa.String(length=2048), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("license_name", sa.String(length=255), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("astrology_system", sa.String(length=16), nullable=False),
        sa.Column("topic", sa.String(length=100), nullable=False),
        sa.Column("document_version", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("review_status", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", name="uq_knowledge_documents_source_id"),
    )
    for column in ("language", "astrology_system", "topic", "review_status", "is_active"):
        op.create_index(f"ix_knowledge_documents_{column}", "knowledge_documents", [column])
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("heading", sa.String(length=500), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_knowledge_chunk_document_index"),
    )
    op.create_index("ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"])
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_embedding_hnsw "
        "ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_embedding_hnsw", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_document_id", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    for column in ("is_active", "review_status", "topic", "astrology_system", "language"):
        op.drop_index(f"ix_knowledge_documents_{column}", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
    # Do not drop vector: another feature may use the PostgreSQL extension.
