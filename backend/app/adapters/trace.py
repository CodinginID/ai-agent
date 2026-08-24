"""Lightweight OpenTelemetry-compatible tracing (no OTLP export).

Pure Python implementation using contextvars for context propagation.
Compatible with OpenTelemetry concepts: trace_id, span_id, attributes, parent/child spans.

No external dependencies — uses only Python stdlib + starlette for middleware.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Optional

try:
    from starlette.middleware.base import BaseHTTPMiddleware
except ImportError:  # pragma: no cover
    BaseHTTPMiddleware = None  # type: ignore

__all__ = [
    "current_trace_id",
    "set_trace_id",
    "TraceContext",
    "Span",
    "Tracer",
    "TraceIdFormatter",
    "TraceMiddleware",
]


# ---------------------------------------------------------------------------
# Context propagation (contextvars)
# ---------------------------------------------------------------------------

_TRACE_ID: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)


def _generate_id() -> str:
    """Generate a 16-character hex ID from UUID4."""
    return uuid.uuid4().hex[:16]


def current_trace_id() -> Optional[str]:
    """Return the current active trace_id from context, or None."""
    return _TRACE_ID.get()


def set_trace_id(trace_id: Optional[str]) -> None:
    """Set the trace_id for the current context."""
    _TRACE_ID.set(trace_id)


# ---------------------------------------------------------------------------
# TraceContext: manual context propagation
# ---------------------------------------------------------------------------


class TraceContext:
    """Context manager for trace context propagation via contextvars.

    Usage::

        ctx = TraceContext(trace_id="abc-123", span_id="span-1")
        with ctx:
            # trace_id and span_id are available in this scope
            pass
        # context is restored
    """

    def __init__(
        self,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
    ):
        self._trace_id = trace_id
        self._span_id = span_id
        self._parent_span_id = parent_span_id
        self._prev_trace: Optional[str] = None
        self._prev_span: Optional[str] = None
        self._prev_parent: Optional[str] = None

    def __enter__(self) -> "TraceContext":
        self._prev_trace = _TRACE_ID.get()
        if self._trace_id is not None:
            _TRACE_ID.set(self._trace_id)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        _TRACE_ID.set(self._prev_trace)


# ---------------------------------------------------------------------------
# Span
# ---------------------------------------------------------------------------


@dataclass
class Span:
    """A single tracing span.

    Records timing, status, and attributes. Parent-child relationships
    are tracked via span_id and parent_span_id.
    """

    name: str
    trace_id: str = ""
    span_id: str = ""
    parent_span_id: Optional[str] = None
    attributes: dict[str, Any] = field(default_factory=dict)

    start_time: Optional[float] = None
    end_time: Optional[float] = None
    status: Optional[str] = None

    def __post_init__(self) -> None:
        """Auto-fill trace_id and span_id from context if not provided."""
        if not self.trace_id:
            self.trace_id = current_trace_id() or _generate_id()
        if not self.span_id:
            self.span_id = _generate_id()

    def start(self) -> None:
        """Mark this span as started."""
        self.start_time = time.monotonic()

    def end(self, status: Optional[str] = None) -> None:
        """Mark this span as ended with an optional status."""
        self.end_time = time.monotonic()
        if status is not None:
            self.status = status

    @property
    def duration_ms(self) -> Optional[float]:
        """Duration in milliseconds. None if span not ended."""
        if self.start_time is None or self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000.0


# ---------------------------------------------------------------------------
# Tracer
# ---------------------------------------------------------------------------


class Tracer:
    """Create and manage spans with automatic context propagation.

    Usage::

        tracer = Tracer()
        span = tracer.start_span("process_request", {"user_id": "123"})
        # ... do work ...
        tracer.end_span(span, status="OK")
    """

    def start_span(
        self,
        name: str,
        attributes: Optional[dict[str, Any]] = None,
    ) -> Span:
        """Start a new span. Inherits trace_id from current context."""
        span = Span(
            name=name,
            parent_span_id=current_trace_id(),  # type: ignore[arg-type]
            attributes=attributes or {},
        )
        span.start()
        return span

    def end_span(self, span: Span, status: Optional[str] = None) -> None:
        """End a span with an optional status."""
        span.end(status=status)


# ---------------------------------------------------------------------------
# Logging integration
# ---------------------------------------------------------------------------


class TraceIdFormatter(logging.Formatter):
    """Formatter that injects trace_id into every log line.

    Format: ``%(message)s  trace_id=<id>``

    Usage::

        handler.setFormatter(TraceIdFormatter("%(asctime)s %(levelname)s %(message)s"))
    """

    def format(self, record: logging.LogRecord) -> str:
        trace_id = current_trace_id() or "-"
        return f"{super().format(record)}  trace_id={trace_id}"


def configure_trace_logging(
    logger_name: str = "octopus",
    log_format: Optional[str] = None,
) -> None:
    """Configure logging to inject trace_id into every log line.

    Idempotent: safe to call multiple times.
    """
    if log_format is None:
        log_format = "%(asctime)s %(levelname)-8s %(name)s  %(message)s"

    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)

    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler) and isinstance(
            handler.formatter, TraceIdFormatter
        ):
            return

    handler = logging.StreamHandler()
    handler.setFormatter(TraceIdFormatter(log_format))
    logger.addHandler(handler)


# ---------------------------------------------------------------------------
# Starlette middleware for auto-tracing HTTP requests
# ---------------------------------------------------------------------------


if BaseHTTPMiddleware is not None:  # pragma: no cover - starlette only

    class TraceMiddleware(BaseHTTPMiddleware):
        """Auto-trace every HTTP request.

        Features:
        - Generates trace_id (or uses x-trace-id header if present)
        - Starts a root span per request
        - Propagates trace context to nested operations
        - Injects trace_id into logs

        Usage::

            app = FastAPI()
            app.add_middleware(TraceMiddleware)
        """

        async def dispatch(self, request: Any, call_next: Any) -> Any:
            trace_id = request.headers.get("x-trace-id") or _generate_id()
            set_trace_id(trace_id)

            span = Span(
                name=f"{request.method} {request.url.path}",
                attributes={
                    "http.method": request.method,
                    "http.url": str(request.url),
                    "http.host": request.headers.get("host", ""),
                },
            )
            span.start()

            try:
                response = await call_next(request)
                span.end(status=str(response.status_code))
                span.attributes["http.status_code"] = response.status_code
                return response
            except Exception as exc:
                span.end(status="ERROR")
                span.attributes["error.message"] = str(exc)
                span.attributes["error.type"] = type(exc).__name__
                raise

else:
    TraceMiddleware = None  # type: ignore[assignment]
