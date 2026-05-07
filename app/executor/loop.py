"""ExecutionLoop — agentic observe/think/decide/execute/reflect/retry cycle.

Dipakai untuk request yang kompleks atau multi-step. Request simpel (cek
memori, docker ps, dsb.) tetap lewat flow intent→action yang sudah ada di
``HandleMessageUseCase``.

Flow:
    1. OBSERVE  : kumpulkan environment context (git, docker, hostname, dsb.)
    2. THINK    : kirim prompt + context ke LLM, minta keputusan JSON
    3. DECIDE   : parse JSON action dari LLM
    4. EXECUTE  : jalankan action (terminal command, file read, dsb.)
    5. REFLECT  : tanya LLM apakah hasilnya sudah menjawab request asal
    6. RETRY    : kalau belum, loop ulang dengan informasi tambahan (max 3x)
    7. FINALIZE : stream teks final

Loop tidak pernah melempar exception ke caller — semua error di-capture
ke ``LoopEvent`` dengan ``type="error"`` supaya SSE stream tidak putus.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.executor.context import ContextCollector, EnvironmentContext
from app.executor.runner import DEFAULT_TIMEOUT, run_safe
from app.ports.ai_provider import AIProvider

logger = logging.getLogger(__name__)

MAX_RETRIES: int = 3
MAX_OUTPUT_CHARS: int = 2000   # cap action output sent back to LLM

# ── Events emitted by the loop ────────────────────────────────────────────────

_VALID_EVENT_TYPES: frozenset[str] = frozenset({
    "observing",
    "thinking",
    "action_started",
    "action_result",
    "reflecting",
    "retrying",
    "text_chunk",
    "final",
    "error",
})


@dataclass(frozen=True)
class LoopEvent:
    type: str     # one of _VALID_EVENT_TYPES
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.type not in _VALID_EVENT_TYPES:
            raise ValueError(f"Unknown LoopEvent type: {self.type!r}")


# ── LLM decision / reflection schemas ────────────────────────────────────────

@dataclass(frozen=True)
class LLMDecision:
    """Parsed structured output from the LLM think step."""

    action: str                     # "terminal" | "file_read" | "respond" | "multi_step"
    command: str = ""               # for "terminal"
    text: str = ""                  # for "respond"
    path: str = ""                  # for "file_read"
    steps: list[str] = field(default_factory=list)  # for "multi_step"
    raw: str = ""                   # original LLM output for debugging


@dataclass(frozen=True)
class ReflectionResult:
    satisfied: bool
    reason: str = ""
    next_action: dict[str, Any] = field(default_factory=dict)


# ── Prompt templates ──────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are Octopus, an AI engineering assistant that controls a Linux server.

## Environment Context
{env_context}

## Available Actions
Respond ONLY with valid JSON (no markdown, no explanation) — pick one:

1. Run a shell command:
   {{"action": "terminal", "command": "<safe shell command>"}}

2. Read a file:
   {{"action": "file_read", "path": "<absolute path>"}}

3. Answer directly (no tool needed):
   {{"action": "respond", "text": "<your answer>"}}

4. Multi-step plan (list of commands):
   {{"action": "multi_step", "steps": ["cmd1", "cmd2"]}}

## Rules
- Only use terminal commands that are safe and non-destructive.
- Use "respond" when you have enough info to answer without running anything.
- Never use rm -rf, shutdown, or other destructive commands.
- Keep answers concise.
"""

_THINK_PROMPT = """\
{system}

## Conversation history
{history}

## User request
{prompt}

Respond with JSON action:"""

_REFLECT_PROMPT = """\
You evaluated whether an action result satisfied the original request.

Original request: {original_prompt}
Action taken: {action_taken}
Result (truncated): {result}

Did this fully address the request?
- If yes:  {{"satisfied": true}}
- If no:   {{"satisfied": false, "reason": "<short reason>", "next_action": {{"action": "terminal", "command": "..."}}}}

Respond ONLY with valid JSON:"""


# ── Helper functions ──────────────────────────────────────────────────────────

def _extract_json(raw: str) -> dict[str, Any] | None:
    """Extract first JSON object from raw LLM output. Return None on failure."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group())
        if not isinstance(data, dict):
            return None
        return data
    except json.JSONDecodeError:
        return None


def _parse_decision(raw: str) -> LLMDecision:
    data = _extract_json(raw)
    if data is None:
        # LLM returned plain text — treat as a direct text response.
        return LLMDecision(action="respond", text=raw.strip(), raw=raw)

    action = str(data.get("action", "respond"))
    return LLMDecision(
        action=action,
        command=str(data.get("command", "")),
        text=str(data.get("text", "")),
        path=str(data.get("path", "")),
        steps=[str(s) for s in data.get("steps", [])],
        raw=raw,
    )


def _parse_reflection(raw: str) -> ReflectionResult:
    data = _extract_json(raw)
    if data is None:
        # Assume satisfied if we can't parse — avoid infinite retries.
        return ReflectionResult(satisfied=True, reason="(reflection parse failed)")
    return ReflectionResult(
        satisfied=bool(data.get("satisfied", True)),
        reason=str(data.get("reason", "")),
        next_action=dict(data.get("next_action") or {}),
    )


def _execute_terminal(command: str, cwd: Path) -> tuple[str, int]:
    """Split command string and run via run_safe policy validator."""
    import shlex
    try:
        args = shlex.split(command)
    except ValueError as exc:
        return f"(invalid command: {exc})", -1
    return run_safe(args, cwd=cwd, timeout=DEFAULT_TIMEOUT)


def _execute_file_read(path: str) -> str:
    try:
        p = Path(path)
        if not p.exists():
            return f"(file not found: {path})"
        if not p.is_file():
            return f"(not a file: {path})"
        content = p.read_text(errors="replace")
        lines = content.splitlines()
        if len(lines) > 100:
            return "\n".join(lines[:100]) + f"\n... ({len(lines)} lines total, showing first 100)"
        return content
    except OSError as exc:
        return f"(cannot read file: {exc})"


# ── Main loop class ───────────────────────────────────────────────────────────

@dataclass
class ExecutionLoop:
    """Agentic loop: observe → think → decide → execute → reflect → retry."""

    ai: AIProvider
    context_collector: ContextCollector
    working_dir: Path

    def run(
        self,
        prompt: str,
        history: str = "",
    ) -> Iterator[LoopEvent]:
        """Run the full loop and yield LoopEvent items.

        This is a synchronous generator — caller wraps in asyncio.to_thread
        for non-blocking SSE streaming.
        """
        # ── 1. OBSERVE ────────────────────────────────────────────────────────
        yield LoopEvent("observing", {"message": "Collecting environment context..."})
        try:
            env_ctx = self.context_collector.collect()
        except Exception as exc:
            logger.warning("context collection failed: %s", exc)
            # Build minimal fallback context so we can still proceed.
            from datetime import datetime
            from app.executor.context import EnvironmentContext
            env_ctx = EnvironmentContext(
                git_status="(unavailable)",
                docker_ps="(unavailable)",
                repo_files="(unavailable)",
                hostname="(unknown)",
                working_dir=str(self.working_dir),
                collected_at=datetime.now(),
            )

        accumulated_context = ""   # grows with each retry iteration
        attempt = 0

        while attempt <= MAX_RETRIES:
            attempt += 1

            # ── 2. THINK ──────────────────────────────────────────────────────
            yield LoopEvent("thinking", {"message": f"Thinking (attempt {attempt})..."})

            system_block = _SYSTEM_PROMPT.format(env_context=env_ctx.render())
            if accumulated_context:
                system_block += f"\n## Previous attempt context\n{accumulated_context}\n"

            think_prompt = _THINK_PROMPT.format(
                system=system_block,
                history=history or "(none)",
                prompt=prompt,
            )

            try:
                raw_decision = self.ai.chat(think_prompt)
            except Exception as exc:
                yield LoopEvent("error", {"message": f"AI think failed: {exc}"})
                return

            # ── 3. DECIDE ─────────────────────────────────────────────────────
            decision = _parse_decision(raw_decision)

            # ── 4. EXECUTE ────────────────────────────────────────────────────
            if decision.action == "respond":
                # LLM has enough info — stream text and finish.
                for chunk in decision.text.split():
                    yield LoopEvent("text_chunk", {"text": chunk + " "})
                yield LoopEvent("final", {"text": decision.text})
                return

            if decision.action == "terminal":
                yield LoopEvent("action_started", {"action": "terminal", "command": decision.command})
                output, exit_code = _execute_terminal(decision.command, self.working_dir)
                result_text = output[:MAX_OUTPUT_CHARS]
                yield LoopEvent("action_result", {
                    "action": "terminal",
                    "command": decision.command,
                    "output": result_text,
                    "exit_code": exit_code,
                })

            elif decision.action == "file_read":
                yield LoopEvent("action_started", {"action": "file_read", "path": decision.path})
                result_text = _execute_file_read(decision.path)[:MAX_OUTPUT_CHARS]
                yield LoopEvent("action_result", {
                    "action": "file_read",
                    "path": decision.path,
                    "output": result_text,
                })

            elif decision.action == "multi_step":
                result_parts: list[str] = []
                for step_cmd in decision.steps:
                    yield LoopEvent("action_started", {"action": "terminal", "command": step_cmd})
                    step_out, step_code = _execute_terminal(step_cmd, self.working_dir)
                    step_text = step_out[:MAX_OUTPUT_CHARS]
                    result_parts.append(f"$ {step_cmd}\n{step_text}")
                    yield LoopEvent("action_result", {
                        "action": "terminal",
                        "command": step_cmd,
                        "output": step_text,
                        "exit_code": step_code,
                    })
                result_text = "\n\n".join(result_parts)

            else:
                yield LoopEvent("error", {"message": f"Unknown action type: {decision.action!r}"})
                return

            # ── 5. REFLECT ────────────────────────────────────────────────────
            if attempt >= MAX_RETRIES:
                # No more retries — synthesize a final answer from last result.
                break

            yield LoopEvent("reflecting", {"message": "Evaluating result..."})

            reflect_prompt = _REFLECT_PROMPT.format(
                original_prompt=prompt,
                action_taken=json.dumps({"action": decision.action, "command": decision.command or decision.path}),
                result=result_text[:1000],
            )

            try:
                raw_reflection = self.ai.chat(reflect_prompt)
            except Exception as exc:
                logger.warning("reflection call failed: %s", exc)
                break  # treat as satisfied, skip retry

            reflection = _parse_reflection(raw_reflection)

            if reflection.satisfied:
                break  # proceed to final synthesis

            # ── 6. RETRY ──────────────────────────────────────────────────────
            accumulated_context += (
                f"\nAttempt {attempt} result:\n{result_text[:500]}\n"
                f"Why it wasn't enough: {reflection.reason}\n"
            )
            yield LoopEvent("retrying", {"attempt": attempt, "reason": reflection.reason})

            # If LLM suggested a next action, seed the decision into next loop
            # iteration by embedding it in accumulated_context (the next THINK
            # prompt will see it), rather than directly running it here.
            if reflection.next_action:
                accumulated_context += (
                    f"Suggested next action: {json.dumps(reflection.next_action)}\n"
                )

        # ── 7. FINALIZE ───────────────────────────────────────────────────────
        # Ask LLM to synthesize a final answer from the last action output.
        yield LoopEvent("thinking", {"message": "Synthesizing final answer..."})

        final_prompt = (
            f"Original request: {prompt}\n\n"
            f"Action result:\n{result_text[:1500]}\n\n"
            "Summarize the result in concise Indonesian or English (match user's language). "
            "Be specific — include key numbers, names, and status values. "
            "Do NOT return JSON."
        )
        try:
            final_text = self.ai.chat(final_prompt)
        except Exception as exc:
            # Fallback: return raw action output if synthesis fails.
            final_text = result_text
            logger.warning("final synthesis failed: %s", exc)

        for chunk in final_text.split():
            yield LoopEvent("text_chunk", {"text": chunk + " "})
        yield LoopEvent("final", {"text": final_text})
