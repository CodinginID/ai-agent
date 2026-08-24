"""Structured JSON logging for Octopus Core.

Provides:
- ``setup_json_logging(log_dir)`` — configure root logger with JSON file handler
  + text stdout handler (for docker logs).
- ``json_logger(name)`` — return a logger that carries an auto-generated trace_id.

Trace ID is managed by ``app.adapters.trace`` (contextvars-based propagation).
"""
from __future__ import annotations

import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.adapters.trace import _TRACE_ID, TraceIdFormatter, current_trace_id

__all__ = [
    "setup_json_logging",
    "json_logger",
    "_TRACE_ID",
    "current_trace_id",
    "TraceIdFormatter",
]


class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record with trace_id injected."""

    def format(self, record: logging.LogRecord) -> str:
        extra = getattr(record, "extra", None) or {}
        payload = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": current_trace_id(),
            "extra": extra,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_json_logging(log_dir: Path) -> None:
    """Configure the root logger with JSON rotating file handler + text stdout."""
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Remove handlers already added by uvicorn (so we don't double-emit).
    root.handlers.clear()

    json_fmt = _JsonFormatter()

    file_handler = RotatingFileHandler(
        log_dir / "server.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(json_fmt)
    root.addHandler(file_handler)

    stdout = logging.StreamHandler(sys.stdout)
    stdout.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    ))
    root.addHandler(stdout)


def json_logger(name: str) -> logging.Logger:
    """Return a named logger; trace_id is auto-filled from context on each emit."""
    return logging.getLogger(name)
