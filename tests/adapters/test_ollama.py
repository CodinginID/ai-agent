"""Unit tests for OllamaAdapter — requests calls are mocked."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.adapters.ollama import OllamaAdapter

_URL = "http://localhost:11434/api/generate"
_MODEL = "qwen2.5:14b"


def _adapter() -> OllamaAdapter:
    return OllamaAdapter(url=_URL, model=_MODEL, timeout=10)


def _resp(data: object, status_code: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = data
    if status_code >= 400:
        r.raise_for_status.side_effect = requests.HTTPError(response=r)
    return r


def _stream_resp(lines: list[str]) -> MagicMock:
    r = MagicMock()
    r.__enter__ = MagicMock(return_value=r)
    r.__exit__ = MagicMock(return_value=False)
    r.iter_lines.return_value = iter(lines)
    return r


# ── chat() ────────────────────────────────────────────────────────────────────

def test_chat_returns_response_string() -> None:
    with patch("requests.post", return_value=_resp({"response": "Hello!", "done": True})):
        assert _adapter().chat("say hello") == "Hello!"


def test_chat_strips_whitespace() -> None:
    with patch("requests.post", return_value=_resp({"response": "  trimmed  "})):
        assert _adapter().chat("hi") == "trimmed"


def test_chat_sends_correct_payload() -> None:
    with patch("requests.post", return_value=_resp({"response": "ok"})) as mock_post:
        _adapter().chat("my prompt")
    _, kwargs = mock_post.call_args
    body = kwargs["json"]
    assert body["model"] == _MODEL
    assert body["prompt"] == "my prompt"
    assert body["stream"] is False


def test_chat_passes_timeout() -> None:
    with patch("requests.post", return_value=_resp({"response": "ok"})) as mock_post:
        _adapter().chat("x")
    _, kwargs = mock_post.call_args
    assert kwargs["timeout"] == 10


def test_chat_raises_on_http_error() -> None:
    with patch("requests.post", return_value=_resp({}, status_code=500)), pytest.raises(requests.HTTPError):
        _adapter().chat("oops")


def test_chat_returns_empty_string_when_response_key_missing() -> None:
    with patch("requests.post", return_value=_resp({"done": True})):
        assert _adapter().chat("no key") == ""


def test_chat_raises_on_connection_error() -> None:
    with patch("requests.post", side_effect=requests.ConnectionError("offline")), pytest.raises(requests.ConnectionError):
        _adapter().chat("offline")


# ── chat_stream() ─────────────────────────────────────────────────────────────

def test_chat_stream_yields_chunks() -> None:
    lines = [
        json.dumps({"response": "Hello", "done": False}),
        json.dumps({"response": " world", "done": False}),
        json.dumps({"response": "!", "done": True}),
    ]
    with patch("requests.post", return_value=_stream_resp(lines)):
        chunks = list(_adapter().chat_stream("stream me"))
    assert chunks == ["Hello", " world", "!"]


def test_chat_stream_stops_after_done_true() -> None:
    lines = [
        json.dumps({"response": "first", "done": False}),
        json.dumps({"response": "second", "done": True}),
        json.dumps({"response": "third", "done": False}),
    ]
    with patch("requests.post", return_value=_stream_resp(lines)):
        chunks = list(_adapter().chat_stream("stop"))
    assert chunks == ["first", "second"]
    assert "third" not in chunks


def test_chat_stream_skips_empty_lines() -> None:
    lines = ["", json.dumps({"response": "ok", "done": True}), ""]
    with patch("requests.post", return_value=_stream_resp(lines)):
        chunks = list(_adapter().chat_stream("empty"))
    assert chunks == ["ok"]


def test_chat_stream_skips_invalid_json() -> None:
    lines = [
        "not {{ valid json",
        json.dumps({"response": "good", "done": True}),
    ]
    with patch("requests.post", return_value=_stream_resp(lines)):
        chunks = list(_adapter().chat_stream("bad json"))
    assert chunks == ["good"]


def test_chat_stream_skips_falsy_response_chunk() -> None:
    lines = [
        json.dumps({"response": "", "done": False}),
        json.dumps({"response": None, "done": False}),
        json.dumps({"response": "real", "done": True}),
    ]
    with patch("requests.post", return_value=_stream_resp(lines)):
        chunks = list(_adapter().chat_stream("falsy"))
    assert chunks == ["real"]


def test_chat_stream_sends_correct_payload() -> None:
    lines = [json.dumps({"done": True})]
    with patch("requests.post", return_value=_stream_resp(lines)) as mock_post:
        list(_adapter().chat_stream("stream prompt"))
    _, kwargs = mock_post.call_args
    body = kwargs["json"]
    assert body["stream"] is True
    assert body["prompt"] == "stream prompt"
    assert body["model"] == _MODEL


def test_chat_stream_raises_on_http_error() -> None:
    r = _stream_resp([])
    r.raise_for_status.side_effect = requests.HTTPError()
    with patch("requests.post", return_value=r), pytest.raises(requests.HTTPError):
        list(_adapter().chat_stream("error"))
