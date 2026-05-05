"""Chat free-text → POST /chat/send (SSE) → render ke output area."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.config import settings
from app.tui import _state
from app.tui._http import CHAT_TIMEOUT_SEC, fmt_http_error
from app.tui._output import println


async def render_sse(lines: AsyncIterator[str]) -> None:
    event = ""
    data_lines: list[str] = []
    chat_started = False

    def flush() -> None:
        nonlocal chat_started
        if not event:
            return
        try:
            payload = json.loads("\n".join(data_lines)) if data_lines else {}
        except json.JSONDecodeError:
            payload = {}

        if event == "intent_classified":
            intent = payload.get("intent", "?")
            conf = payload.get("confidence", 0)
            println("class:dim", f"  > intent: {intent} ({conf:.0%})")
        elif event == "thinking":
            println("class:dim", f"  > {payload.get('message', '')}")
        elif event == "approval_required":
            println("class:warn", f"  butuh approval — plan_id={payload.get('plan_id')}")
            println("", payload.get("summary", ""))
        elif event == "action_started":
            println("class:dim", f"  > running {payload.get('action')}...")
        elif event == "action_result":
            println("", payload.get("output", ""))
        elif event == "text_chunk":
            chunk = payload.get("text", "")
            if not chat_started:
                _state.output.append(("class:ai", "  "))
                chat_started = True
            _state.output.append(("class:ai", chunk))
            if _state.app is not None:
                _state.app.invalidate()
        elif event == "final":
            if chat_started:
                _state.output.append(("", "\n"))
                if _state.app is not None:
                    _state.app.invalidate()
                chat_started = False
            else:
                final_text = payload.get("text", "")
                if final_text:
                    println("class:ai", f"  {final_text}")
        elif event == "error":
            if chat_started:
                _state.output.append(("", "\n"))
                chat_started = False
            println("class:err", f"  error: {payload.get('message', '')}")

    async for raw in lines:
        if raw == "":
            flush()
            event = ""
            data_lines = []
            continue
        if raw.startswith("event: "):
            event = raw[len("event: "):].strip()
        elif raw.startswith("data: "):
            data_lines.append(raw[len("data: "):])
    flush()


async def send_chat(text: str) -> None:
    session = _state.active_session
    if session is None:
        println("class:warn", "  belum login. Ketik /login dulu.")
        return
    headers = {
        "Authorization": f"Bearer {session.token}",
        "User-Agent": "octopus-tui/0.1.0",
        "Accept": "text/event-stream",
    }
    try:
        async with httpx.AsyncClient(
            base_url=settings.app_url,
            timeout=httpx.Timeout(CHAT_TIMEOUT_SEC, connect=5.0),
            headers=headers,
            trust_env=False,
        ) as c, c.stream("POST", "/chat/send", json={"text": text}) as resp:
            if resp.status_code == 401:
                println("class:err", "  session expired. Ketik /login lagi.")
                return
            if resp.status_code != 200:
                body_bytes = await resp.aread()
                body = body_bytes.decode("utf-8", errors="replace")
                println("class:err", f"  HTTP {resp.status_code}: {body[:200]}")
                return
            await render_sse(resp.aiter_lines())
    except httpx.HTTPError as exc:
        println("class:err", f"  request gagal: {fmt_http_error(exc)}")
