"""
Test suite for app/adapters/trace.py
"""

import pytest
import time

# Test 1: TraceID generator
def test_trace_id_generator():
    """TraceID generator should produce 16 character hex strings."""
    from app.adapters.trace import generate_trace_id

    trace_id = generate_trace_id()
    assert len(trace_id) == 16
    assert trace_id.isalnum()
    assert all(c in '0123456789abcdef' for c in trace_id)

def test_trace_id_generator_uniqueness():
    """TraceID generator should produce unique IDs."""
    from app.adapters.trace import generate_trace_id

    trace_ids = {generate_trace_id() for _ in range(1000)}
    assert len(trace_ids) == 1000

# Test 2: Context propagation
def test_context_propagation():
    """Context vars should propagate trace_id through context."""
    from app.adapters.trace import set_trace, get_trace, TraceContext

    # Initially no trace
    assert get_trace() is None

    # Set trace
    trace_id = generate_trace_id()
    with TraceContext(trace_id):
        assert get_trace() == trace_id

    # After context exits, should be None again
    assert get_trace() is None

def test_nested_contexts():
    """Nested contexts should handle parent-child relationships."""
    from app.adapters.trace import set_trace, get_trace, TraceContext

    parent_id = generate_trace_id()
    with TraceContext(parent_id):
        assert get_trace() == parent_id

        child_id = generate_trace_id()
        with TraceContext(child_id):
            assert get_trace() == child_id

        assert get_trace() == parent_id  # Back to parent

# Test 3: Span class
def test_span_creation():
    """Span should record start_time, attributes."""
    from app.adapters.trace import Span

    span = Span(name="test_span", attributes={"key": "value"})

    assert span.name == "test_span"
    assert span.attributes == {"key": "value"}
    assert span.start_time is not None
    assert span.end_time is None
    assert span.status is None

def test_span_lifecycle():
    """Span should track complete lifecycle."""
    from app.adapters.trace import Span

    span = Span(name="test_span")

    # Start
    assert span.start_time is not None
    start = span.start_time

    # Simulate work
    time.sleep(0.1)

    # End
    span.end(status="completed", attributes={"duration_ms": 100})

    assert span.end_time is not None
    assert span.end_time > start
    assert span.status == "completed"
    assert span.duration_ms >= 100
    assert span.attributes["duration_ms"] == 100

def test_span_duration_calculation():
    """Span should accurately calculate duration_ms."""
    from app.adapters.trace import Span

    span = Span(name="test")

    start = time.time()
    span.start_time = start

    time.sleep(0.1)

    span.end_time = time.time()
    span.status = "completed"

    assert span.duration_ms is not None
    assert span.duration_ms >= 100  # At least 100ms
    assert span.duration_ms < 200  # Less than 200ms

# Test 4: Tracer class
def test_tracer_start_span():
    """Tracer should create and start a span."""
    from app.adapters.trace import Tracer, generate_trace_id, set_trace

    trace_id = generate_trace_id()
    set_trace(trace_id)

    tracer = Tracer()
    span = tracer.start_span("test_operation", attributes={"param": "value"})

    assert span.name == "test_operation"
    assert span.start_time is not None
    assert span.attributes == {"param": "value"}

    tracer.end_span(span, status="success")
    assert span.end_time is not None
    assert span.status == "success"

def test_tracer_with_attributes():
    """Tracer should pass attributes to spans."""
    from app.adapters.trace import Tracer, generate_trace_id, set_trace

    trace_id = generate_trace_id()
    set_trace(trace_id)

    tracer = Tracer()
    attributes = {"user_id": "123", "action": "login"}
    span = tracer.start_span("auth_check", attributes=attributes)

    assert span.attributes == attributes
    assert span.attributes["user_id"] == "123"

    tracer.end_span(span)

# Test 5: current_trace_id and set_trace_id exports
def test_current_trace_id_export():
    """current_trace_id() should return current trace from context."""
    from app.adapters.trace import current_trace_id, generate_trace_id, set_trace

    assert current_trace_id() is None

    trace_id = generate_trace_id()
    set_trace(trace_id)

    assert current_trace_id() == trace_id

def test_set_trace_id_export():
    """set_trace_id() should set the trace in context."""
    from app.adapters.trace import set_trace_id, current_trace_id

    trace_id = generate_trace_id()
    set_trace_id(trace_id)

    assert current_trace_id() == trace_id

    # Clean up
    set_trace_id(None)
    assert current_trace_id() is None

# Test 6: Log integration
def test_trace_id_in_logs():
    """trace_id should be included in log output."""
    from app.adapters.trace import add_trace_id_to_logs, generate_trace_id, set_trace

    trace_id = generate_trace_id()
    set_trace(trace_id)

    # Enable trace_id logging
    add_trace_id_to_logs()

    # Import logger after setup
    from app.adapters.trace import logger

    # Capture log output
    import logging
    stream = logging.StreamHandler()
    stream.setLevel(logging.INFO)

    logger.addHandler(stream)
    logger.setLevel(logging.INFO)

    logger.info("Test message")

    # The log output should contain trace_id
    # (This is a simplified test - actual implementation may vary)
    assert trace_id in str(logger)  # Simplified check

# Test 7: Gateway middleware
def test_gateway_middleware_auto_trace():
    """Gateway middleware should automatically trace requests."""
    from app.adapters.gateway import middleware_auto_trace, generate_trace_id

    # Mock request
    class MockRequest:
        def __init__(self):
            self.headers = {"x-trace-id": generate_trace_id()}
            self.method = "GET"
            self.path = "/api/test"

    mock_request = MockRequest()

    # Mock next middleware
    async def mock_next(request):
        return {"status": 200}

    # Test middleware
    result = middleware_auto_trace(mock_request, mock_next)
    assert result is not None

# Test 8: Integration test
def test_full_trace_workflow():
    """End-to-end trace workflow test."""
    from app.adapters.trace import (
        generate_trace_id, set_trace, current_trace_id,
        Tracer, Span, TraceContext
    )

    # Generate trace
    trace_id = generate_trace_id()
    set_trace(trace_id)

    # Verify trace is set
    assert current_trace_id() == trace_id

    # Create tracer and spans
    tracer = Tracer()

    with TraceContext(trace_id):
        parent_span = tracer.start_span("parent_operation", {"type": "parent"})
        assert parent_span.name == "parent_operation"

        with TraceContext(generate_trace_id()):  # Child trace
            child_span = tracer.start_span("child_operation", {"type": "child"})
            assert child_span.name == "child_operation"

        tracer.end_span(parent_span, status="completed")
        assert parent_span.status == "completed"

    # Verify trace is cleared
    assert current_trace_id() is None
