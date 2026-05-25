"""Composition root — bangun ``HandleMessageUseCase`` dengan dependensi konkret.

Dipakai oleh adapter HTTP (``/chat/send``) dan nanti oleh Telegram setelah
migrasi Fase 6. Semua wiring DI ditempatkan di sini supaya domain layer
tidak ikut import adapter.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy import Engine
    from sqlalchemy.orm import sessionmaker

from app.adapters.agent_role_resolver import SqlAgentRoleResolver
from app.adapters.chat_history import SqlAlchemyChatHistory
from app.adapters.database.session import (
    create_database_engine,
    create_session_factory,
)
from app.adapters.handoff_context import RedisHandoffContextProvider
from app.adapters.knowledge_store_memory import InMemoryKnowledgeStore
from app.adapters.ollama import OllamaAdapter
from app.config import settings
from app.domain.use_cases import HandleMessageUseCase
from app.executor.actions import ActionRegistry
from app.executor.context import ContextCollector
from app.executor.loop import ExecutionLoop
from app.intents.parser import IntentParser
from app.orchestrator.approval import PendingPlanStore
from app.orchestrator.plans import PlanGenerator
from app.ports.embedder import Embedder
from app.ports.knowledge_store import KnowledgeStore


@lru_cache(maxsize=1)
def _engine() -> Engine:
    return create_database_engine(settings.database_url)


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Any]:
    return create_session_factory(_engine())


@lru_cache(maxsize=1)
def _ollama() -> OllamaAdapter:
    return OllamaAdapter(
        url=settings.qwen_url,
        model=settings.qwen_model,
        timeout=settings.command_timeout * 3,
    )


def _build_action_registry() -> ActionRegistry:
    from app.handlers.registry import action_registry
    return action_registry


def _build_pending_plans() -> PendingPlanStore:
    from app.handlers.approval import pending_plans
    return pending_plans


@lru_cache(maxsize=1)
def _context_collector() -> ContextCollector:
    return ContextCollector(working_dir=settings.project_dir)


@lru_cache(maxsize=1)
def _execution_loop() -> ExecutionLoop:
    return ExecutionLoop(
        ai=_ollama(),
        context_collector=_context_collector(),
        working_dir=settings.project_dir,
    )


# ── RAG factories ────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _embedder() -> Embedder | None:
    """Return embedder backend per ``EMBEDDER_BACKEND`` env. None = RAG disabled."""
    if not settings.rag_enabled:
        return None
    backend = settings.embedder_backend
    if backend == "none":
        return None
    if backend == "fastembed":
        from app.adapters.embedder_fastembed import FastEmbedAdapter
        return FastEmbedAdapter()
    if backend == "ollama":
        from app.adapters.embedder_ollama import OllamaEmbedder
        return OllamaEmbedder(url=settings.ollama_host, model=settings.ollama_embed_model)
    raise ValueError(f"Unknown EMBEDDER_BACKEND: {backend!r}")


@lru_cache(maxsize=1)
def _knowledge_store() -> KnowledgeStore:
    """Production: PgVectorKnowledgeStore. Test/dev SQLite: InMemoryKnowledgeStore.

    Dipilih berdasarkan DATABASE_URL — pgvector cuma jalan di Postgres.
    """
    if settings.database_url.startswith("postgresql"):
        from app.adapters.knowledge_store_pgvector import PgVectorKnowledgeStore
        return PgVectorKnowledgeStore(_session_factory())
    return InMemoryKnowledgeStore()


def build_use_case() -> HandleMessageUseCase:
    """Compose use case dengan semua dependensi konkret."""
    ollama = _ollama()
    return HandleMessageUseCase(
        ai=ollama,
        intent_parser=IntentParser(qwen_caller=ollama.chat),
        plan_generator=PlanGenerator(),
        action_registry=_build_action_registry(),
        pending_plans=_build_pending_plans(),
        history=SqlAlchemyChatHistory(_session_factory()),
        history_limit=settings.chat_history_limit,
        execution_loop=_execution_loop(),
        agent_resolver=SqlAgentRoleResolver(_session_factory()),
        handoff_provider=RedisHandoffContextProvider(),
    )
