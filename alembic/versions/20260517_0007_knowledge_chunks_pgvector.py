"""add knowledge_chunks table + pgvector extension

Revision ID: 20260517_0007
Revises: 20260517_0006
Create Date: 2026-05-17

RAG infrastructure: enable pgvector + tabel ``knowledge_chunks``. Embedding
dim 384 cocok dengan model default (FastEmbed all-MiniLM-L6-v2). Index ANN
pakai HNSW dengan cosine ops karena Embedder produce L2-normalized vector.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "20260517_0007"
down_revision: str | None = "20260517_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 384


def upgrade() -> None:
    bind = op.get_bind()
    # pgvector is Postgres-only; skip entirely on SQLite.
    if bind.dialect.name == "sqlite":
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_knowledge_chunks_project_id",
        "knowledge_chunks",
        ["project_id"],
    )
    op.create_index(
        "ix_knowledge_chunks_project_created",
        "knowledge_chunks",
        ["project_id", "created_at"],
    )
    # ANN index — cosine ops karena Embedder produce normalized vector.
    # HNSW (vs IVFFlat) lebih cocok untuk insert/query ratio yang variabel.
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_embedding_hnsw "
        "ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_embedding_hnsw", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_project_created", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_project_id", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    # Sengaja tidak DROP EXTENSION vector — ekstensi bisa shared dengan
    # tabel/index lain di future.
