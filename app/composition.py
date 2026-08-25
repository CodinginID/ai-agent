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
from app.adapters.audit import JsonlAuditLogger
from app.adapters.chat_history import SqlAlchemyChatHistory
from app.adapters.database.session import (
    create_database_engine,
    create_session_factory,
)
from app.adapters.handoff_context import RedisHandoffContextProvider
from app.adapters.knowledge_store_memory import InMemoryKnowledgeStore
from app.adapters.rate_limit import RedisRateLimiter
from app.adapters.redis_client import get_sync_client
from app.adapters.worker_dispatch import WorkerDispatchAdapter
from app.agents.pm import PMAgent
from app.config import BASE_DIR, settings
from app.domain.use_cases import HandleMessageUseCase
from app.executor.actions import ActionRegistry
from app.executor.context import ContextCollector
from app.executor.loop import ExecutionLoop
from app.intents.parser import IntentParser
from app.memory.context_store import ProjectContextStore
from app.orchestrator.approval import PendingPlanStore
from app.orchestrator.plans import PlanGenerator
from app.orchestrator.task_runner import TaskRunner
from app.orchestrator.workflow import WorkflowOrchestrator
from app.ports.embedder import Embedder
from app.ports.knowledge_store import KnowledgeStore


@lru_cache(maxsize=1)
def _engine() -> Engine:
    return create_database_engine(settings.database_url)


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Any]:
    return create_session_factory(_engine())


@lru_cache(maxsize=1)
def _provider_resolver() -> Any:
    """Resolver AI provider per-user (BYOK) — dipakai use case / loop / task runner."""
    from app.adapters.ai_provider_db import DbAIProviderResolver
    from app.adapters.user_provider_config import UserProviderConfigRepository
    repo = UserProviderConfigRepository(_session_factory())
    return DbAIProviderResolver(repo, settings)


@lru_cache(maxsize=1)
def _default_provider() -> Any:
    """Provider default server-side (tanpa user), mis. workflow orchestrator.

    Butuh key sesuai ``AI_PROVIDER_DEFAULT``; kalau kosong, ``build_ai_provider``
    raise saat dipanggil (BYOK, tidak ada fallback lokal lagi).
    """
    from app.adapters.ai_provider_factory import build_ai_provider
    return build_ai_provider(settings.ai_provider_default, None, settings)


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
def _audit_logger() -> JsonlAuditLogger:
    return JsonlAuditLogger(path=BASE_DIR / "logs" / "audit.jsonl")


@lru_cache(maxsize=1)
def _execution_loop() -> ExecutionLoop:
    return ExecutionLoop(
        context_collector=_context_collector(),
        working_dir=settings.project_dir,
        worker_dispatch=WorkerDispatchAdapter(),
        provider_resolver=_provider_resolver(),
        audit=_audit_logger(),
    )


@lru_cache(maxsize=1)
def _context_store() -> ProjectContextStore:
    return ProjectContextStore(BASE_DIR / "data")


@lru_cache(maxsize=1)
def _rate_limiter() -> RedisRateLimiter:
    return RedisRateLimiter(
        redis_client=get_sync_client(),
        cooldown_seconds=settings.rate_limit_seconds,
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


@lru_cache(maxsize=1)
def _workflow_orchestrator() -> WorkflowOrchestrator:
    from app.adapters.workflow_artifacts import FileArtifactStore, RepoFileChecker
    from app.adapters.workflow_fallback import (
        PromptArchitect,
        PromptEngineer,
        PromptReviewer,
    )

    ai = _default_provider()
    return WorkflowOrchestrator(
        architect=PromptArchitect(ai=ai, model=settings.agent_role_architect),
        engineer=PromptEngineer(ai=ai, model=settings.agent_role_engineer),
        reviewer=PromptReviewer(ai=ai, model=settings.agent_role_reviewer),
        artifacts=FileArtifactStore(BASE_DIR / "data"),
        file_checker=RepoFileChecker(settings.project_dir),
        audit=_audit_logger(),
    )


def build_workflow_orchestrator() -> WorkflowOrchestrator:
    """Compose the architect→engineer→reviewer orchestrator (prompt fallback)."""
    return _workflow_orchestrator()


def build_task_runner() -> TaskRunner:
    """Compose the PM→Issue→Worker→Close task runner (orchestrator end-to-end).

    Raises ``GitHubUnavailableError`` when GITHUB_TOKEN/REPO are unset — the
    caller (endpoint) maps that to a 503 so the failure is explicit, not silent.
    """
    from app.adapters.github import GitHubAdapter
    from app.adapters.task_memory import RagTaskMemory
    from app.adapters.task_observer import LoggingTaskObserver

    github = GitHubAdapter(token=settings.github_token, repo=settings.github_repo)
    return TaskRunner(
        pm=PMAgent(),
        github=github,
        dispatch=WorkerDispatchAdapter(),
        observer=LoggingTaskObserver(),
        memory=RagTaskMemory(
            embedder=_embedder(),
            store=_knowledge_store(),
            recall_k=settings.rag_recall_k,
        ),
        provider_resolver=_provider_resolver(),
    )


def build_use_case() -> HandleMessageUseCase:
    """Compose use case dengan semua dependensi konkret."""
    return HandleMessageUseCase(
        intent_parser=IntentParser(),
        plan_generator=PlanGenerator(),
        action_registry=_build_action_registry(),
        pending_plans=_build_pending_plans(),
        history=SqlAlchemyChatHistory(_session_factory()),
        history_limit=settings.chat_history_limit,
        execution_loop=_execution_loop(),
        agent_resolver=SqlAgentRoleResolver(_session_factory()),
        handoff_provider=RedisHandoffContextProvider(),
        rate_limiter=_rate_limiter(),
        audit=_audit_logger(),
        context_provider=_context_store(),
        provider_resolver=_provider_resolver(),
    )
