"""Unit tests for app.adapters.trace module.

Tests for:
- TraceID generation and propagation
- TraceContext context manager
- Span creation, timing, and status
- Tracer class operations
- TraceIdFormatter logging integration
- TraceMiddleware (when starlette is available)
- configure_trace_logging function
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from unittest.mock import MagicMock, patch
from typing import Optional

import pytest

from app.adapters.trace import (
    Span,
    TraceContext,
    TraceIdFormatter,
    TraceMiddleware,
    Tracer,
    _generate_id,
    _STARLETTE_AVAILABLE,
    configure_trace_logging,
    current_trace_id,
    set_trace_id,
)


class TestTraceIdGeneration:
    """Tests for trace ID generation and context management."""

    def setup_method(self):
        """Reset trace context before each test."""
        set_trace_id(None)

    def test_generate_id_returns_16_char_hex(self):
        """Test that _generate_id() returns exactly 16 hex characters."""
        trace_id = _generate_id()
        assert len(trace_id) == 16
        # Verify it's hexadecimal
        assert all(c in "0123456789abcdef" for c in trace_id)

    def test_generate_id_uniqueness(self):
        """Test that generated IDs are unique."""
        ids = {_generate_id() for _ in range(100)}
        assert len(ids) == 100  # All should be unique

    def test_current_trace_id_initially_none(self):
        """Test that current_trace_id() returns None initially."""
        assert current_trace_id() is None

    def test_set_and_get_trace_id(self):
        """Test setting and getting trace_id."""
        trace_id = _generate_id()
        set_trace_id(trace_id)
        assert current_trace_id() == trace_id

    def test_set_trace_id_none(self):
        """Test setting trace_id to None."""
        set_trace_id("test-id")
        assert current_trace_id() == "test-id"
        set_trace_id(None)
        assert current_trace_id() is None

    def test_trace_id_context_isolation(self):
        """Test that trace_id is properly isolated between contexts."""
        # This is more of an integration test, but we can verify the basic behavior
        set_trace_id("parent-trace")
        parent_trace = current_trace_id()
        assert parent_trace == "parent-trace"

        with TraceContext(trace_id="child-trace"):
            assert current_trace_id() == "child-trace"

        # After context manager, should restore to parent
        assert current_trace_id() == "parent-trace"


class TestTraceContext:
    """Tests for TraceContext context manager."""

    def setup_method(self):
        """Reset trace context before each test."""
        set_trace_id(None)

    def test_trace_context_sets_trace_id(self):
        """Test that TraceContext sets trace_id."""
        with TraceContext(trace_id="test-trace"):
            assert current_trace_id() == "test-trace"

    def test_trace_context_restores_on_exit(self):
        """Test that TraceContext restores previous trace_id on exit."""
        set_trace_id("original")
        with TraceContext(trace_id="temporary"):
            assert current_trace_id() == "temporary"
        assert current_trace_id() == "original"

    def test_trace_context_none_preserves_previous(self):
        """Test that TraceContext with None trace_id doesn't change context."""
        set_trace_id("original")
        with TraceContext(trace_id=None):
            assert current_trace_id() == "original"

    def test_trace_context_nested(self):
        """Test nested TraceContext usage."""
        set_trace_id("outer")
        with TraceContext(trace_id="inner"):
            assert current_trace_id() == "inner"
            with TraceContext(trace_id="deepest"):
                assert current_trace_id() == "deepest"
            assert current_trace_id() == "inner"
        assert current_trace_id() == "outer"

    def test_trace_context_exception_handling(self):
        """Test that TraceContext properly handles exceptions."""
        set_trace_id("before-exception")
        with pytest.raises(ValueError):
            with TraceContext(trace_id="during-exception"):
                assert current_trace_id() == "during-exception"
                raise ValueError("Test error")
        # Context should still be restored
        assert current_trace_id() == "before-exception"

    def test_trace_context_multiple_exits(self):
        """Test that TraceContext can be exited multiple times safely."""
        set_trace_id("original")
        ctx = TraceContext(trace_id="temporary")

        with ctx:
            assert current_trace_id() == "temporary"

        # Exiting twice should be safe
        ctx.__exit__(None, None, None)
        assert current_trace_id() == "original"


class TestSpan:
    """Tests for Span dataclass."""

    def setup_method(self):
        """Reset trace context before each test."""
        set_trace_id(None)

    def test_span_creation(self):
        """Test basic Span creation."""
        set_trace_id("test-trace")
        span = Span(name="test-operation")
        assert span.name == "test-operation"
        assert span.trace_id == "test-trace"
        assert span.span_id  # Should be auto-generated
        assert span.parent_span_id is None
        assert span.attributes == {}
        assert span.start_time is None
        assert span.end_time is None
        assert span.status is None

    def test_span_explicit_attributes(self):
        """Test Span creation with explicit attributes."""
        attributes = {"key": "value", "count": 42}
        span = Span(
            name="test",
            trace_id="explicit-trace",
            span_id="explicit-span",
            parent_span_id="parent-span",
            attributes=attributes,
        )
        assert span.trace_id == "explicit-trace"
        assert span.span_id == "explicit-span"
        assert span.parent_span_id == "parent-span"
        assert span.attributes == attributes

    def test_span_start(self):
        """Test Span.start() method."""
        span = Span(name="test")
        assert span.start_time is None
        span.start()
        assert span.start_time is not None
        assert isinstance(span.start_time, float)

    def test_span_end(self):
        """Test Span.end() method."""
        span = Span(name="test")
        span.start()
        assert span.end_time is None
        span.end()
        assert span.end_time is not None
        assert span.end_time > span.start_time

    def test_span_end_with_status(self):
        """Test Span.end() with status parameter."""
        span = Span(name="test")
        span.start()
        span.end(status="OK")
        assert span.status == "OK"

    def test_span_duration_ms(self):
        """Test Span.duration_ms calculation."""
        span = Span(name="test")
        span.start()
        time.sleep(0.01)  # Sleep for 10ms
        span.end()
        assert span.duration_ms is not None
        assert span.duration_ms >= 10  # At least 10ms
        assert span.duration_ms < 1000  # Less than 1 second

    def test_span_duration_ms_before_end(self):
        """Test that duration_ms is None before span ends."""
        span = Span(name="test")
        span.start()
        assert span.duration_ms is None

    def test_span_auto_fill_trace_id(self):
        """Test that span auto-fills trace_id from context."""
        set_trace_id("context-trace")
        span = Span(name="test")
        assert span.trace_id == "context-trace"

    def test_span_auto_fill_span_id(self):
        """Test that span auto-generates span_id."""
        span = Span(name="test")
        assert len(span.span_id) > 0
        # Verify it's not empty or None
        assert span.span_id is not None
        assert span.span_id != ""

    def test_span_multiple_starts(self):
        """Test that span can be started multiple times (overwrites start_time)."""
        span = Span(name="test")
        span.start()
        first_start = span.start_time
        time.sleep(0.01)
        span.start()  # Start again
        assert span.start_time > first_start


class TestTracer:
    """Tests for Tracer class."""

    def setup_method(self):
        """Reset trace context before each test."""
        set_trace_id(None)

    def test_tracer_start_span(self):
        """Test Tracer.start_span() method."""
        tracer = Tracer()
        span = tracer.start_span("test-operation")
        assert span.name == "test-operation"
        assert span.start_time is not None
        assert span.trace_id is not None

    def test_tracer_start_span_with_attributes(self):
        """Test Tracer.start_span() with attributes."""
        tracer = Tracer()
        attributes = {"user_id": "123"}
        span = tracer.start_span("operation", attributes=attributes)
        assert span.attributes == attributes

    def test_tracer_end_span(self):
        """Test Tracer.end_span() method."""
        tracer = Tracer()
        span = tracer.start_span("test")
        tracer.end_span(span, status="OK")
        assert span.status == "OK"
        assert span.end_time is not None

    def test_tracer_end_span_without_status(self):
        """Test Tracer.end_span() without status."""
        tracer = Tracer()
        span = tracer.start_span("test")
        tracer.end_span(span)
        assert span.status is None
        assert span.end_time is not None

    def test_tracer_multiple_spans(self):
        """Test creating multiple spans."""
        tracer = Tracer()
        span1 = tracer.start_span("span1")
        span2 = tracer.start_span("span2")
        span3 = tracer.start_span("span3")

        assert span1.name == "span1"
        assert span2.name == "span2"
        assert span3.name == "span3"

        # All should have different span_ids
        assert span1.span_id != span2.span_id
        assert span2.span_id != span3.span_id

    def test_tracer_span_timing(self):
        """Test that traced spans have proper timing."""
        tracer = Tracer()
        span = tracer.start_span("timed-operation")
        time.sleep(0.05)  # Sleep 50ms
        tracer.end_span(span, status="OK")

        assert span.duration_ms is not None
        assert span.duration_ms >= 50  # At least 50ms
        assert span.duration_ms < 500  # Less than 500ms


class TestTraceIdFormatter:
    """Tests for TraceIdFormatter logging formatter."""

    def setup_method(self):
        """Reset trace context before each test."""
        set_trace_id(None)

    def test_formatter_injects_trace_id(self):
        """Test that formatter injects trace_id into log messages."""
        set_trace_id("test-trace-id")
        fmt = TraceIdFormatter("%(message)s")

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        formatted = fmt.format(record)
        assert "trace_id=test-trace-id" in formatted
        assert "Test message" in formatted

    def test_formatter_with_no_trace_id(self):
        """Test formatter when no trace_id is set."""
        fmt = TraceIdFormatter("%(message)s")

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        formatted = fmt.format(record)
        assert "trace_id=" in formatted  # Should have trace_id= but with no value or dash

    def test_formatter_with_custom_format(self):
        """Test formatter with custom format string."""
        set_trace_id("custom-trace")
        fmt = TraceIdFormatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")

        record = logging.LogRecord(
            name="mylogger",
            level=logging.WARNING,
            pathname="test.py",
            lineno=1,
            msg="Warning message",
            args=(),
            exc_info=None,
        )
        formatted = fmt.format(record)
        assert "custom-trace" in formatted
        assert "mylogger" in formatted
        assert "Warning message" in formatted
        assert "WARNING" in formatted

    def test_formatter_with_exception(self):
        """Test formatter handles exceptions."""
        set_trace_id("exception-trace")
        fmt = TraceIdFormatter("%(message)s")

        try:
            raise ValueError("Test exception")
        except ValueError:
            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="test.py",
                lineno=1,
                msg="Error occurred",
                args=(),
                exc_info=sys.exc_info(),
            )
            formatted = fmt.format(record)
            assert "trace_id=exception-trace" in formatted
            assert "Error occurred" in formatted


class TestConfigureTraceLogging:
    """Tests for configure_trace_logging function."""

    def setup_method(self):
        """Reset trace context before each test."""
        set_trace_id(None)

    def test_configure_trace_logging_basic(self):
        """Test basic configuration of trace logging."""
        logger_name = "test_logger"
        configure_trace_logging(logger_name)

        logger = logging.getLogger(logger_name)
        assert len(logger.handlers) > 0
        assert isinstance(logger.handlers[0].formatter, TraceIdFormatter)

    def test_configure_trace_logging_with_custom_format(self):
        """Test configuration with custom log format."""
        logger_name = "custom_format_logger"
        custom_format = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
        configure_trace_logging(logger_name, log_format=custom_format)

        logger = logging.getLogger(logger_name)
        handler = logger.handlers[0]
        assert isinstance(handler.formatter, TraceIdFormatter)
        assert handler.formatter._fmt == custom_format + "  trace_id={trace_id}"

    def test_configure_trace_logging_multiple_times(self):
        """Test that configuring multiple times doesn't add duplicate handlers."""
        logger_name = "multi_config_logger"
        configure_trace_logging(logger_name)
        configure_trace_logging(logger_name)

        logger = logging.getLogger(logger_name)
        # Should not have duplicate handlers
        handler_count = sum(
            1 for h in logger.handlers
            if isinstance(h.formatter, TraceIdFormatter)
        )
        assert handler_count == 1


@pytest.mark.skipif(not _STARLETTE_AVAILABLE, reason="Starlette not available")
class TestTraceMiddleware:
    """Tests for TraceMiddleware (requires starlette)."""

    def setup_method(self):
        """Reset trace context before each test."""
        set_trace_id(None)

    def test_middleware_creates_trace_id(self):
        """Test that middleware creates a trace_id."""
        middleware = TraceMiddleware(None)  # type: ignore[arg-type]

        # Create mock request
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.method = "GET"
        mock_request.url = MagicMock()
        mock_request.url.path = "/test"
        mock_request.url.__str__ = MagicMock(return_value="http://test/test")

        async def mock_call_next(request):
            return MagicMock(status_code=200)

        # Run middleware
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(middleware.dispatch(mock_request, mock_call_next))
        finally:
            loop.close()

        # Should have created a trace_id
        assert current_trace_id() is not None

    def test_middleware_uses_x_trace_id_header(self):
        """Test that middleware uses x-trace-id header if present."""
        middleware = TraceMiddleware(None)  # type: ignore[arg-type]

        mock_request = MagicMock()
        mock_request.headers = {"x-trace-id": "custom-trace-123"}
        mock_request.method = "POST"
        mock_request.url = MagicMock()
        mock_request.url.path = "/api/test"
        mock_request.url.__str__ = MagicMock(return_value="http://test/api/test")

        async def mock_call_next(request):
            return MagicMock(status_code=201)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(middleware.dispatch(mock_request, mock_call_next))
        finally:
            loop.close()

        assert current_trace_id() == "custom-trace-123"

    def test_middleware_records_span_attributes(self):
        """Test that middleware records HTTP attributes."""
        middleware = TraceMiddleware(None)  # type: ignore[arg-type]

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.method = "GET"
        mock_request.url = MagicMock()
        mock_request.url.path = "/users/123"
        mock_request.url.__str__ = MagicMock(return_value="http://localhost/users/123")

        async def mock_call_next(request):
            return MagicMock(status_code=200)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(middleware.dispatch(mock_request, mock_call_next))
        finally:
            loop.close()

        # The span should have been created (we can't easily access it,
        # but we can verify the trace was created)
        assert current_trace_id() is not None

    def test_middleware_handles_exceptions(self):
        """Test that middleware properly handles exceptions."""
        middleware = TraceMiddleware(None)  # type: ignore[arg-type]

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.method = "GET"
        mock_request.url = MagicMock()
        mock_request.url.path = "/error"
        mock_request.url.__str__ = MagicMock(return_value="http://test/error")

        async def mock_call_next(request):
            raise RuntimeError("Test error")

        loop = asyncio.new_event_loop()
        try:
            with pytest.raises(RuntimeError, match="Test error"):
                await middleware.dispatch(mock_request, mock_call_next)
        finally:
            loop.close()

        # Trace should still be set even after exception
        assert current_trace_id() is not None


class TestIntegration:
    """Integration tests for the trace module."""

    def setup_method(self):
        """Reset trace context before each test."""
        set_trace_id(None)

    def test_full_trace_workflow(self):
        """Test complete trace workflow: context -> tracer -> span -> log."""
        # Set up context
        set_trace_id("integration-trace")

        # Create tracer and span
        tracer = Tracer()
        span = tracer.start_span("integration-test", {"key": "value"})

        # Simulate work
        time.sleep(0.01)

        # End span
        tracer.end_span(span, status="OK")

        # Verify span
        assert span.status == "OK"
        assert span.duration_ms is not None
        assert span.duration_ms > 0

        # Test logging integration
        fmt = TraceIdFormatter("%(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Integration test message",
            args=(),
            exc_info=None,
        )
        formatted = fmt.format(record)
        assert "integration-trace" in formatted
        assert "Integration test message" in formatted

    def test_nested_tracing(self):
        """Test nested tracing with multiple spans."""
        set_trace_id("parent-trace")

        parent_tracer = Tracer()
        parent_span = parent_tracer.start_span("parent-operation")

        # Nested context
        with TraceContext(trace_id="child-trace"):
            child_tracer = Tracer()
            child_span = child_tracer.start_span("child-operation")
            time.sleep(0.01)
            child_tracer.end_span(child_span, status="OK")
            assert child_span.status == "OK"

        # Back to parent
        time.sleep(0.01)
        parent_tracer.end_span(parent_span, status="OK")
        assert parent_span.status == "OK"

    def test_trace_id_propagation_through_logging(self):
        """Test that trace_id propagates correctly through logging."""
        fmt = TraceIdFormatter("%(message)s")

        # Set trace_id
        set_trace_id("propagation-test")

        # Log a message
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Propagated message",
            args=(),
            exc_info=None,
        )
        output = fmt.format(record)

        # Verify trace_id is in the output
        assert "propagation-test" in output
        assert "Propagated message" in output

        # Change trace_id and verify it updates
        set_trace_id("new-trace-id")
        record2 = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Updated message",
            args=(),
            exc_info=None,
        )
        output2 = fmt.format(record2)
        assert "new-trace-id" in output2
        assert "propagation-test" not in output2
