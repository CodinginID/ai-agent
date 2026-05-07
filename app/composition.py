"""Composition root — bangun ``HandleMessageUseCase`` dengan dependensi konkret.

Dipakai oleh adapter HTTP (``/chat/send``) dan nanti oleh Telegram setelah
migrasi Fase 6. Semua wiring DI ditempatkan di sini supaya domain layer
tidak ikut import adapter.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.adapters.chat_history import SqlAlchemyChatHistory
from app.adapters.database.session import (
    create_database_engine,
    create_session_factory,
)
from app.adapters.ollama import OllamaAdapter
from app.config import settings
from app.domain.use_cases import HandleMessageUseCase
from app.executor.actions import ActionRegistry
from app.executor.context import ContextCollector
from app.executor.loop import ExecutionLoop
from app.intents.parser import IntentParser
from app.orchestrator.approval import PendingPlanStore
from app.orchestrator.plans import PlanGenerator


@lru_cache(maxsize=1)
def _engine() -> Engine:
    return create_database_engine(settings.database_url)


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker:
    return create_session_factory(_engine())


@lru_cache(maxsize=1)
def _ollama() -> OllamaAdapter:
    return OllamaAdapter(
        url=settings.qwen_url,
        model=settings.qwen_model,
        timeout=settings.command_timeout * 3,
    )


def _build_action_registry() -> ActionRegistry:
    """Import bot.py module-level registry — Fase 6 akan ekstrak ke helper.

    Untuk sekarang, kita reuse registry yang sudah dibangun di bot.py supaya
    tidak duplikasi action definitions.
    """
    from app.bot import action_registry as _registry
    return _registry


def _build_pending_plans() -> PendingPlanStore:
    from app.bot import pending_plans as _store
    return _store


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
    )
