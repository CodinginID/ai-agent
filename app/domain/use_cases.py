"""HandleMessageUseCase — orchestrator pesan independen dari Telegram/HTTP/TUI.

Flow:
1. Classify intent via AI (``IntentParser``).
2. Kalau ``chat``/``unknown`` → stream chat reply dari AI.
3. Kalau action → generate plan, cek approval, eksekusi, ringkas hasil pakai AI.
4. Kalau request kompleks → delegasi ke ``ExecutionLoop`` (observe/think/reflect/retry).

Use case yield ``ChatEvent`` sehingga setiap medium (Telegram, TUI, HTTP/SSE)
render sesuai kemampuan mereka.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from app.domain.exceptions import ActionExecutionError, AIProviderError, IntentParseError
from app.domain.messaging import ChatEvent, ChatEventType, MessageContext
from app.executor.actions import ActionRegistry
from app.intents.parser import IntentParser
from app.intents.schemas import EXECUTABLE_ACTIONS, Intent
from app.orchestrator.approval import PendingPlanStore
from app.orchestrator.plans import PlanGenerator
from app.ports.ai_provider import AIProvider
from app.ports.chat_history import ChatHistoryStore
from app.ports.execution_loop import ExecutionLoopPort

_CHAT_PROMPT_TEMPLATE = (
    "Kamu Octopus, AI orchestrator yang dipakai operator server lewat Telegram & TUI.\n"
    "Tugas kamu di mode ini: chat ringan, sapaan, atau pertanyaan teknis singkat.\n"
    "Tugas berat (eksekusi command, baca log, pakai Codex/Claude) di-handle modul lain — "
    "kamu cukup arahkan user ke command yang tepat.\n\n"
    "Aturan:\n"
    "1. Jawab dalam bahasa user. User pakai Indonesia → jawab Indonesia.\n"
    "2. SINGKAT. Untuk sapaan ('hi', 'halo'), balas 1 kalimat ramah saja.\n"
    "3. JANGAN klaim sudah eksekusi command — kamu tidak punya akses shell di mode chat.\n"
    "4. Kalau user minta aksi server, arahkan ke contoh natural seperti:\n"
    "   'cek status server', 'cek ram', 'cek disk', 'status docker',\n"
    "   'git status', atau langsung '/cmd <command>'.\n"
    "5. Untuk pertanyaan kompleks (refactor kode, debug deep), suruh pakai Codex/Claude\n"
    "   via /codex atau /claude.\n\n"
    "Riwayat chat terakhir:\n{history}\n\n"
    "User: {user_text}\nOctopus:"
)

_SUMMARIZE_PROMPT = (
    "Ringkas output server berikut dalam bahasa Indonesia singkat (1-3 kalimat),\n"
    "tampilkan angka penting apa adanya:\n\n{output}"
)


# Signals that indicate a request needs multi-step reasoning rather than a
# single predefined action. These are heuristic patterns — false positives are
# safe because the loop will still produce a result.
_COMPLEX_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bkenapa\b|\bwhy\b|\bpenyebab\b|\bcause\b", re.IGNORECASE),
    re.compile(r"\banalisa?\b|\banalyze?\b|\binvestigat\b", re.IGNORECASE),
    re.compile(r"\bdiagnos\b|\bdebug\b|\btrace\b|\btroubleshoot\b", re.IGNORECASE),
    re.compile(r"\bberapa\s+kali\b|\bhow\s+many\b|\bhow\s+much\b", re.IGNORECASE),
    re.compile(r"\bapa\s+yang\s+(terjadi|salah|error)\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+(happened|went\s+wrong|is\s+wrong)\b", re.IGNORECASE),
    re.compile(r"\bdan\s+kemudian\b|\bdan\s+juga\b|\blalu\b|\bthen\b", re.IGNORECASE),
    re.compile(r"\bstep\s+by\s+step\b|\blangkah\s+demi\s+langkah\b", re.IGNORECASE),
    re.compile(r"\bsetelah\s+itu\b|\bafter\s+that\b", re.IGNORECASE),
    re.compile(r"\berror\s+log\b|\blog\s+error\b", re.IGNORECASE),
    re.compile(r"\bjika\s+.+\s+maka\b|\bif\s+.+\s+then\b", re.IGNORECASE),
    re.compile(r"\bapa\s+isi\s+file\b|\bread\s+file\b|\bshow\s+file\b", re.IGNORECASE),
    re.compile(r"\bbandingkan?\b|\bcompare\b|\bdiff\b", re.IGNORECASE),
)

_EXPLICIT_SIMPLE_INTENTS: frozenset[str] = frozenset({
    "server_status", "memory", "disk", "processes",
    "docker_ps", "docker_images", "docker_stats", "docker_logs",
    "git_status", "list_files", "whoami",
})


def _is_complex_request(text: str, intent_name: str) -> bool:
    """Heuristic: return True if the request warrants multi-step execution loop.

    Simple direct action lookups (memory, docker ps, git status, dsb.) use the
    existing intent→action path. Everything else that matches complexity signals
    — or that resolved to ``unknown`` — goes through the loop.
    """
    if intent_name in _EXPLICIT_SIMPLE_INTENTS:
        return False
    if intent_name == "unknown":
        return True
    return any(p.search(text) for p in _COMPLEX_PATTERNS)


def _loop_event_to_chat_event(loop_event_type: str, loop_data: dict[str, Any]) -> ChatEvent | None:
    """Bridge a LoopEvent into a ChatEvent for the SSE stream.

    Returns None for event types that have no ChatEvent equivalent.
    """
    if loop_event_type == "observing":
        return ChatEvent.observing(str(loop_data.get("message", "")))
    if loop_event_type == "thinking":
        return ChatEvent.thinking(str(loop_data.get("message", "")))
    if loop_event_type == "action_started":
        action = str(loop_data.get("action", ""))
        cmd = str(loop_data.get("command", loop_data.get("path", "")))
        return ChatEvent.action_started(f"{action}: {cmd}" if cmd else action)
    if loop_event_type == "action_result":
        action = str(loop_data.get("action", ""))
        output = str(loop_data.get("output", ""))
        return ChatEvent.action_result(action, output)
    if loop_event_type == "reflecting":
        return ChatEvent.reflecting(str(loop_data.get("message", "")))
    if loop_event_type == "retrying":
        return ChatEvent.retrying(
            attempt=int(loop_data.get("attempt", 0)),
            reason=str(loop_data.get("reason", "")),
        )
    if loop_event_type == "text_chunk":
        return ChatEvent.text_chunk(str(loop_data.get("text", "")))
    if loop_event_type == "final":
        return ChatEvent.final(str(loop_data.get("text", "")))
    if loop_event_type == "error":
        return ChatEvent.error(str(loop_data.get("message", "")))
    return None


@dataclass
class HandleMessageUseCase:
    """Orchestrator: pesan masuk → events keluar.

    Dependencies di-inject lewat constructor (DI) supaya testable + bisa diganti
    implementasinya tanpa mengubah domain logic.
    """

    ai: AIProvider
    intent_parser: IntentParser
    plan_generator: PlanGenerator
    action_registry: ActionRegistry
    pending_plans: PendingPlanStore
    history: ChatHistoryStore
    history_limit: int = 6
    # Optional: when provided, complex requests are routed through the agentic loop.
    execution_loop: ExecutionLoopPort | None = field(default=None)

    def handle(self, text: str, ctx: MessageContext) -> Iterator[ChatEvent]:
        """Pure synchronous generator — adapter layer adapts ke async kalau perlu."""
        text = text.strip()
        if not text:
            return

        # ── 1. Classify intent ────────────────────────────────────────────────
        try:
            intent = self.intent_parser.parse(text, ctx.project_id)
        except IntentParseError as exc:
            yield ChatEvent.error(f"Gagal classify intent: {exc}")
            return

        yield ChatEvent.intent_classified(
            intent=intent.intent,
            confidence=intent.confidence,
            reason=intent.reason,
        )

        # ── 2. Agent delegation path ──────────────────────────────────────────
        # Intent agent_* tidak dijalanin di sini — handler luar (chat.py / bot.py)
        # yang ngerelay ke worker user via WS dispatcher. Use case cuma kasih
        # mapping intent → agent CLI + prompt yang udah dibersihin.
        if intent.is_agent():
            agent_name = _agent_for_intent(intent.intent, ctx.user_id)
            role = _role_for_intent(intent.intent)
            if agent_name is None:
                yield ChatEvent.error(
                    f"Belum ada agent yang assigned untuk role '{role}'. "
                    "Set via /agents di TUI atau Telegram."
                )
                return
            cleaned = _strip_command_prefix(text)
            # Hand-off antar role: kalau ini reviewer/architect, ambil output
            # role sebelumnya (engineer hasil terakhir) sebagai context tambahan.
            cleaned = _maybe_prepend_handoff(ctx.user_id, role, cleaned)
            yield ChatEvent.delegate_to_agent(
                agent=agent_name,
                prompt=cleaned,
                intent=intent.intent,
                role=role,
            )
            return

        # ── 3. Chat path ──────────────────────────────────────────────────────
        if not intent.is_action():
            yield from self._handle_chat(text, ctx)
            return

        # ── 4. Complex request → Execution Loop ──────────────────────────────
        if self.execution_loop is not None and _is_complex_request(text, intent.intent):
            yield from self._handle_loop(text, ctx)
            return

        # ── 5. Simple action path ─────────────────────────────────────────────
        yield from self._handle_action(text, intent, ctx)

    # ── private ───────────────────────────────────────────────────────────────

    def _handle_loop(self, text: str, ctx: MessageContext) -> Iterator[ChatEvent]:
        """Route complex request through ExecutionLoop. Bridge LoopEvents → ChatEvents."""
        assert self.execution_loop is not None  # caller checks before routing here

        history_lines: list[str] = []
        for msg in self.history.recent(ctx.user_id, self.history_limit):
            role = "User" if msg.role == "user" else "Assistant"
            history_lines.append(f"{role}: {msg.content}")
        history_text = "\n".join(history_lines)

        self.history.append(ctx.user_id, "user", text)

        final_text = ""
        try:
            for loop_ev in self.execution_loop.run(text, history=history_text):
                chat_ev = _loop_event_to_chat_event(loop_ev.type, loop_ev.data)
                if chat_ev is not None:
                    if chat_ev.type == ChatEventType.FINAL:
                        final_text = str(chat_ev.payload.get("text", ""))
                    yield chat_ev
        except (AIProviderError, ActionExecutionError) as exc:
            yield ChatEvent.error(f"Execution loop failed: {exc}")
            return
        except Exception as exc:
            yield ChatEvent.error(f"Execution loop failed: {exc}")
            return

        if final_text:
            self.history.append(ctx.user_id, "assistant", final_text)

    def _handle_chat(self, text: str, ctx: MessageContext) -> Iterator[ChatEvent]:
        history_lines = []
        for msg in self.history.recent(ctx.user_id, self.history_limit):
            role = "User" if msg.role == "user" else "Assistant"
            history_lines.append(f"{role}: {msg.content}")
        history_text = "\n".join(history_lines) if history_lines else "(kosong)"

        prompt = _CHAT_PROMPT_TEMPLATE.format(history=history_text, user_text=text)

        self.history.append(ctx.user_id, "user", text)

        collected: list[str] = []
        try:
            for chunk in self.ai.chat_stream(prompt):
                if not chunk:
                    continue
                collected.append(chunk)
                yield ChatEvent.text_chunk(chunk)
        except AIProviderError as exc:
            yield ChatEvent.error(f"AI provider gagal: {exc}")
            return

        full_reply = "".join(collected).strip()
        if full_reply:
            self.history.append(ctx.user_id, "assistant", full_reply)
        yield ChatEvent.final(full_reply)

    def _handle_action(
        self, text: str, intent: Intent, ctx: MessageContext
    ) -> Iterator[ChatEvent]:
        plan = self.plan_generator.generate(intent)

        if plan.requires_approval:
            action_context = self._build_action_context(intent, ctx)
            self.pending_plans.save(plan, _conv_id_to_int(ctx.conversation_id), text, action_context)
            yield ChatEvent.approval_required(
                plan_id=plan.plan_id,
                summary=plan.short_description(),
            )
            return

        if intent.intent not in EXECUTABLE_ACTIONS:
            yield ChatEvent.final(
                f"Intent '{intent.intent}' dikenali tapi belum ada handler.\n"
                f"Reason: {intent.reason}"
            )
            return

        yield ChatEvent.action_started(intent.intent)
        try:
            result = self.action_registry.execute(
                intent.intent, self._build_action_context(intent, ctx)
            )
        except ActionExecutionError as exc:
            yield ChatEvent.error(f"Action {intent.intent} gagal: {exc}")
            return

        yield ChatEvent.action_result(intent.intent, result)

        # whoami: tidak perlu summary AI, output sudah ringkas
        if intent.intent == "whoami":
            yield ChatEvent.final(result)
            return

        try:
            summary = self.ai.chat(_SUMMARIZE_PROMPT.format(output=result))
        except AIProviderError:
            summary = result

        final_text = (
            f"Action: {intent.intent} ({intent.confidence:.0%})\n\n{summary}"
        )
        yield ChatEvent.final(final_text)

    def _build_action_context(
        self, intent: Intent, ctx: MessageContext
    ) -> dict[str, object]:
        return {
            "telegram_user": {
                "id": ctx.telegram_user_id or "-",
                "username": ctx.extra.get("telegram_username", "-"),
            },
            "project_dir": ctx.project_root,
            "project_name": ctx.project_name,
            **intent.parameters,
        }


def _conv_id_to_int(conv_id: str) -> int:
    """PendingPlanStore butuh chat_id int. Kalau TUI pakai string UUID, hash ke int.

    Hash konsisten cukup — collision di scope pending plans (per user) sangat kecil
    karena disimpan dengan TTL pendek.
    """
    try:
        return int(conv_id)
    except ValueError:
        return abs(hash(conv_id)) % (2**31)


# ── Agent role → CLI mapping ─────────────────────────────────────────────────

# Mapping intent → role string (yang disimpan di DB).
_INTENT_TO_ROLE: dict[str, str] = {
    "agent_code":      "engineer",
    "agent_review":    "reviewer",
    "agent_architect": "architect",
}


def _role_for_intent(intent_name: str) -> str:
    return _INTENT_TO_ROLE.get(intent_name, "engineer")


def _agent_for_intent(intent_name: str, user_id: str) -> str | None:
    """Resolve intent → CLI agent name dari config DB per-user.

    Cari agent yang ``enabled=True`` dan ``role`` cocok. Return None kalau user
    belum config agent untuk role tersebut.
    """
    from app.adapters.agent_configs import UserAgentConfigRepository
    from app.adapters.database.session import (
        create_database_engine,
        create_session_factory,
    )
    from app.config import settings as _settings

    role = _role_for_intent(intent_name)
    factory = create_session_factory(create_database_engine(_settings.database_url))
    repo = UserAgentConfigRepository(factory)
    return repo.agent_for_role(user_id, role)


def _strip_command_prefix(text: str) -> str:
    """Buang prefix ``/code``, ``/review``, ``/architect``, ``/refactor`` kalau ada."""
    text = text.strip()
    for prefix in ("/code ", "/refactor ", "/review ", "/architect "):
        if text.lower().startswith(prefix):
            return text[len(prefix):].strip()
    for prefix in ("/code", "/refactor", "/review", "/architect"):
        if text.lower() == prefix:
            return ""
    return text


# Mapping role yang inherit context dari role sebelumnya. Reviewer biasanya
# review output engineer; architect bisa pakai output engineer juga.
_HANDOFF_FROM: dict[str, str] = {
    "reviewer":  "engineer",
    "architect": "engineer",
}


def _maybe_prepend_handoff(user_id: str, current_role: str, prompt: str) -> str:
    """Kalau current_role punya hand-off mapping, prepend hasil role sebelumnya."""
    prev_role = _HANDOFF_FROM.get(current_role)
    if not prev_role:
        return prompt

    import asyncio
    import concurrent.futures

    from app.adapters.agent_context import build_handoff_prefix, fetch_role

    def _run() -> dict[str, Any] | None:
        # New event loop in dedicated thread — safe regardless of outer loop state.
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(fetch_role(user_id, prev_role))
        finally:
            loop.close()

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            prev = pool.submit(_run).result(timeout=5)
    except Exception:
        return prompt

    if not prev:
        return prompt
    return build_handoff_prefix(prev, current_role) + prompt
