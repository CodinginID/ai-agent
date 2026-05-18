"""PgVector-backed KnowledgeStore — production adapter.

Pakai SQLAlchemy ORM untuk insert/delete dan raw SQL untuk ANN query
(``<=>`` cosine distance operator dari pgvector). Wrap sync DB session di
``asyncio.to_thread`` supaya konsisten dengan port async signature.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy import text as sql_text

from app.adapters.database.models import KnowledgeChunkModel
from app.ports.knowledge_store import KnowledgeChunk, RecallResult

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


class PgVectorKnowledgeStore:
    """Postgres + pgvector adapter. Embeddings di-asumsikan L2-normalized.

    Pakai cosine distance (``<=>``) untuk ANN supaya cocok dengan default
    FastEmbed / Ollama nomic-embed-text yang produce normalized output.
    Score = ``1 - distance``, sehingga 1.0 = identik.
    """

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    async def index(
        self,
        project_id: str,
        text: str,
        embedding: list[float],
        meta: dict[str, Any] | None = None,
    ) -> str:
        chunk_id = str(uuid.uuid4())

        def _do() -> str:
            with self._factory() as session:
                row = KnowledgeChunkModel(
                    id=chunk_id,
                    project_id=project_id,
                    text=text,
                    embedding=embedding,
                    meta=dict(meta or {}),
                )
                session.add(row)
                session.commit()
            return chunk_id

        return await asyncio.to_thread(_do)

    async def recall(
        self,
        project_id: str,
        query_embedding: list[float],
        k: int = 5,
    ) -> list[RecallResult]:
        # Raw SQL untuk leverage pgvector ANN index (HNSW cosine_ops).
        # ``1 - (embedding <=> :q)`` menghasilkan similarity dalam range [0, 1]
        # ketika embedding L2-normalized.
        sql = sql_text(
            """
            SELECT id, project_id, text, meta,
                   1 - (embedding <=> CAST(:q AS vector)) AS score
            FROM knowledge_chunks
            WHERE project_id = :project_id
            ORDER BY embedding <=> CAST(:q AS vector)
            LIMIT :k
            """
        )

        def _do() -> list[RecallResult]:
            with self._factory() as session:
                # pgvector expects literal vector format ``[1,2,3]``
                q_literal = "[" + ",".join(repr(float(x)) for x in query_embedding) + "]"
                rows = session.execute(
                    sql,
                    {"q": q_literal, "project_id": project_id, "k": k},
                ).all()
            return [
                RecallResult(
                    chunk=KnowledgeChunk(
                        id=row.id,
                        project_id=row.project_id,
                        text=row.text,
                        meta=dict(row.meta or {}),
                    ),
                    score=float(row.score),
                )
                for row in rows
            ]

        return await asyncio.to_thread(_do)

    async def delete_project(self, project_id: str) -> int:
        def _do() -> int:
            with self._factory() as session:
                rows = list(
                    session.scalars(
                        select(KnowledgeChunkModel).where(
                            KnowledgeChunkModel.project_id == project_id
                        )
                    )
                )
                for r in rows:
                    session.delete(r)
                session.commit()
                return len(rows)

        return await asyncio.to_thread(_do)
