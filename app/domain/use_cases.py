"""HandleMessageUseCase — orchestrator pesan independen dari Telegram/HTTP/TUI.

Flow:
1. Classify intent via AI (``IntentParser``).
2. Kalau ``chat``/``unknown`` → stream chat reply dari AI.
3. Kalau action → generate plan, cek approval, eksekusi, ringkas hasil pakai AI.

Use case yield ``ChatEvent`` sehingga setiap medium (Telegram, TUI, HTTP/SSE)
render sesuai kemampuan mereka.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from app.domain.messaging import ChatEvent, MessageContext
from app.executor.actions import ActionRegistry
from app.intents.parser import IntentParser
from app.intents.schemas import EXECUTABLE_ACTIONS, Intent
from app.orchestrator.approval import PendingPlanStore
from app.orchestrator.plans import PlanGenerator
from app.ports.ai_provider import AIProvider
from app.ports.chat_history import ChatHistoryStore

_CHAT_PROMPT_TEMPLATE = (
    "Kamu adalah AI-Agent App, asisten pribadi yang berjalan via Telegram dan TUI.\n\n"
    "Peran:\n"
    "- Jawab sapaan, percakapan umum, dan pertanyaan teknis dengan natural.\n"
    "- Pakai bahasa yang sama dengan user.\n"
    "- Jawab singkat, langsung, praktis.\n"
    '- Kalau user mau aksi server, arahkan ke contoh seperti "cek status server",\n'
    '  "cek ram", "status docker", "git status", atau "/cmd <command>".\n'
    "- Jangan klaim sudah jalankan command server di mode chat — eksekusi action hanya\n"
    "  oleh handler khusus.\n\n"
    "Riwayat chat terakhir:\n{history}\n\n"
    "User:\n{user_text}\n\nAssistant:\n"
)

_SUMMARIZE_PROMPT = (
    "Ringkas output server berikut dalam bahasa Indonesia singkat (1-3 kalimat),\n"
    "tampilkan angka penting apa adanya:\n\n{output}"
)


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

    def handle(self, text: str, ctx: MessageContext) -> Iterator[ChatEvent]:
        """Pure synchronous generator — adapter layer adapts ke async kalau perlu."""
        text = text.strip()
        if not text:
            return

        # ── 1. Classify intent ────────────────────────────────────────────────
        try:
            intent = self.intent_parser.parse(text, ctx.project_id)
        except Exception as exc:
            yield ChatEvent.error(f"Gagal classify intent: {exc}")
            return

        yield ChatEvent.intent_classified(
            intent=intent.intent,
            confidence=intent.confidence,
            reason=intent.reason,
        )

        # ── 2. Chat path ──────────────────────────────────────────────────────
        if not intent.is_action():
            yield from self._handle_chat(text, ctx)
            return

        # ── 3. Action path ────────────────────────────────────────────────────
        yield from self._handle_action(text, intent, ctx)

    # ── private ───────────────────────────────────────────────────────────────

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
        except Exception as exc:
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
        except Exception as exc:
            yield ChatEvent.error(f"Action {intent.intent} gagal: {exc}")
            return

        yield ChatEvent.action_result(intent.intent, result)

        # whoami: tidak perlu summary AI, output sudah ringkas
        if intent.intent == "whoami":
            yield ChatEvent.final(result)
            return

        try:
            summary = self.ai.chat(_SUMMARIZE_PROMPT.format(output=result))
        except Exception:
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
