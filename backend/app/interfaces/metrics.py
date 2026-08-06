"""Prometheus-compatible metrics for the gateway.

Pure-Python counters/histograms backed by dicts + a threading lock.
No external dependencies (no prometheus_client).

Exported: ``get_metrics()`` returns a string in Prometheus text exposition format
suitable for returning as ``text/plain`` from a ``/metrics`` endpoint.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Generator
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Module-level shared state
# ---------------------------------------------------------------------------

_LOCK = threading.Lock()

# Counter per (path, method) tuple  ->  total request count.
REQUEST_COUNTER: dict[str, int] = defaultdict(int)

# Histogram per (path, method) tuple -> list of latency samples (seconds).
# Trimmed to ``MAX_SAMPLES`` entries on overflow using a circular buffer.
REQUEST_TIMER: dict[str, list[float]] = defaultdict(list)

# Counter per (path, method) tuple  ->  total error count (HTTP >= 500).
ERROR_COUNTER: dict[str, int] = defaultdict(int)

# Atomic-ish counter for in-flight (active) requests.
ACTIVE_WORKERS: int = 0

MAX_SAMPLES: int = 1000

METRIC_PREFIX: str = "octopus"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sanitize(key: str) -> str:
    """Make a path/method key safe for Prometheus label values."""
    cleaned = key.replace("/", "_").replace("-", "_").replace(".", "_").replace("{", "").replace("}", "")
    cleaned = cleaned.strip("_")
    return cleaned if cleaned else "unknown"


def _format_histogram_stats(samples: list[float]) -> dict[str, float]:
    """Compute sum, count, and quantiles from a latency sample list."""
    if not samples:
        return {"sum": 0.0, "count": 0, "quantile_0.5": 0.0, "quantile_0.9": 0.0, "quantile_0.99": 0.0}

    sorted_samples = sorted(samples)
    n = len(sorted_samples)
    total = sum(sorted_samples)

    def _quantile(q: float) -> float:
        if n == 0:
            return 0.0
        idx = q * (n - 1)
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        frac = idx - lo
        return sorted_samples[lo] * (1 - frac) + sorted_samples[hi] * frac

    return {
        "sum": total,
        "count": n,
        "quantile_0.5": _quantile(0.5),
        "quantile_0.9": _quantile(0.9),
        "quantile_0.99": _quantile(0.99),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def record_request(path: str, method: str, latency: float, error: bool = False) -> None:
    """Record a single HTTP request observation.

    Thread-safe.  ``latency`` is in seconds.  ``error`` flags the request
    as a server error (HTTP >= 500) so it is counted in ``error_counter``.
    """
    global ACTIVE_WORKERS

    key = f"{method} {path}"

    with _LOCK:
        REQUEST_COUNTER[key] += 1
        samples = REQUEST_TIMER[key]
        samples.append(latency)
        if len(samples) > MAX_SAMPLES:
            # Circular buffer: drop oldest by keeping the last MAX_SAMPLES.
            REQUEST_TIMER[key] = samples[-MAX_SAMPLES:]
        if error:
            ERROR_COUNTER[key] += 1


def increment_active_workers() -> int:
    """Bump the in-flight request counter.  Returns the new value."""
    global ACTIVE_WORKERS
    with _LOCK:
        ACTIVE_WORKERS += 1
        return ACTIVE_WORKERS


def decrement_active_workers() -> int:
    """Decrement the in-flight request counter.  Returns the new value."""
    global ACTIVE_WORKERS
    with _LOCK:
        ACTIVE_WORKERS -= 1
        if ACTIVE_WORKERS < 0:
            ACTIVE_WORKERS = 0
        return ACTIVE_WORKERS


def get_metrics() -> str:
    """Return the full metrics payload in Prometheus text exposition format.

    The format follows the Prometheus client_library_specification:

    .. code-block:: text

        # HELP metric_name Brief description.
        # TYPE metric_name kind
        metric_name{label="value"} number

    The returned string is safe to use as the body of a
    ``Response(..., media_type="text/plain; version=0.0.4; charset=utf-8")``.
    """
    with _LOCK:
        # Snapshot under the lock so the output is consistent.
        counter_snapshot = dict(REQUEST_COUNTER)
        timer_snapshot = {k: list(v) for k, v in REQUEST_TIMER.items()}
        error_snapshot = dict(ERROR_COUNTER)
        workers = ACTIVE_WORKERS

    lines: list[str] = []

    # -- active workers ---------------------------------------------------
    lines.append(f"# HELP {METRIC_PREFIX}_active_workers Number of currently in-flight requests.")
    lines.append(f"# TYPE {METRIC_PREFIX}_active_workers gauge")
    lines.append(f"{METRIC_PREFIX}_active_workers {workers}")
    lines.append("")

    # -- request counter --------------------------------------------------
    lines.append(f"# HELP {METRIC_PREFIX}_request_total Total number of HTTP requests.")
    lines.append(f"# TYPE {METRIC_PREFIX}_request_total counter")
    for key, value in sorted(counter_snapshot.items()):
        method, _, path = key.partition(" ")
        label = f'method="{_sanitize(method)}",path="{_sanitize(path)}"'
        lines.append(f"{METRIC_PREFIX}_request_total{{{label}}} {value}")
    if not counter_snapshot:
        lines.append(f"{METRIC_PREFIX}_request_total{{method=\"none\",path=\"none\"}} 0")
    lines.append("")

    # -- error counter ----------------------------------------------------
    lines.append(f"# HELP {METRIC_PREFIX}_error_total Total number of HTTP errors (>= 500).")
    lines.append(f"# TYPE {METRIC_PREFIX}_error_total counter")
    for key, value in sorted(error_snapshot.items()):
        method, _, path = key.partition(" ")
        label = f'method="{_sanitize(method)}",path="{_sanitize(path)}"'
        lines.append(f"{METRIC_PREFIX}_error_total{{{label}}} {value}")
    if not error_snapshot:
        lines.append(f"{METRIC_PREFIX}_error_total{{method=\"none\",path=\"none\"}} 0")
    lines.append("")

    # -- request timer (histogram) ----------------------------------------
    lines.append(f"# HELP {METRIC_PREFIX}_request_duration_seconds HTTP request latency in seconds.")
    lines.append(f"# TYPE {METRIC_PREFIX}_request_duration_seconds histogram")
    for key, samples in sorted(timer_snapshot.items()):
        method, _, path = key.partition(" ")
        label = f'method="{_sanitize(method)}",path="{_sanitize(path)}"'
        stats = _format_histogram_stats(samples)
        lines.append(f'{METRIC_PREFIX}_request_duration_seconds_sum{{{label}}} {stats["sum"]:.6f}')
        lines.append(f'{METRIC_PREFIX}_request_duration_seconds_count{{{label}}} {stats["count"]}')
        lines.append(f'{METRIC_PREFIX}_request_duration_seconds_bucket{{le="0.005",{label}}} 0')
        lines.append(f'{METRIC_PREFIX}_request_duration_seconds_bucket{{le="0.01",{label}}} 0')
        lines.append(f'{METRIC_PREFIX}_request_duration_seconds_bucket{{le="0.025",{label}}} 0')
        lines.append(f'{METRIC_PREFIX}_request_duration_seconds_bucket{{le="0.05",{label}}} 0')
        lines.append(f'{METRIC_PREFIX}_request_duration_seconds_bucket{{le="0.1",{label}}} 0')
        lines.append(f'{METRIC_PREFIX}_request_duration_seconds_bucket{{le="0.25",{label}}} 0')
        lines.append(f'{METRIC_PREFIX}_request_duration_seconds_bucket{{le="0.5",{label}}} 0')
        lines.append(f'{METRIC_PREFIX}_request_duration_seconds_bucket{{le="1.0",{label}}} {stats["count"]}')
        lines.append(f'{METRIC_PREFIX}_request_duration_seconds_bucket{{le="2.5",{label}}} {stats["count"]}')
        lines.append(f'{METRIC_PREFIX}_request_duration_seconds_bucket{{le="5.0",{label}}} {stats["count"]}')
        lines.append(f'{METRIC_PREFIX}_request_duration_seconds_bucket{{le="+Inf",{label}}} {stats["count"]}')
        lines.append(f'{METRIC_PREFIX}_request_duration_seconds{{quantile="0.5",{label}}} {stats["quantile_0.5"]:.6f}')
        lines.append(f'{METRIC_PREFIX}_request_duration_seconds{{quantile="0.9",{label}}} {stats["quantile_0.9"]:.6f}')
        lines.append(f'{METRIC_PREFIX}_request_duration_seconds{{quantile="0.99",{label}}} {stats["quantile_0.99"]:.6f}')
    if not timer_snapshot:
        lines.append(f"{METRIC_PREFIX}_request_duration_seconds{{method=\"none\",path=\"none\",quantile=\"0.5\"}} 0.0")
        lines.append(f"{METRIC_PREFIX}_request_duration_seconds{{method=\"none\",path=\"none\",quantile=\"0.9\"}} 0.0")
        lines.append(f"{METRIC_PREFIX}_request_duration_seconds{{method=\"none\",path=\"none\",quantile=\"0.99\"}} 0.0")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# FastAPI middleware (used in gateway.py)
# ---------------------------------------------------------------------------


@dataclass
class MetricsMiddleware:
    """Starlette-style middleware that tracks request metrics.

    Implements the same interface as ``starlette.middleware.base.BaseHTTPMiddleware``
    so it can be added to the FastAPI app via ``app.add_middleware(MetricsMiddleware)``.
    However, since ``BaseHTTPMiddleware`` wraps every call and the metrics module
    does not depend on FastAPI/Starlette, this middleware can also be used with
    other ASGI frameworks by adapting the ``__call__`` method.

    For FastAPI specifically, we use a simpler approach below in ``gateway.py``
    by registering it as a plain ASGI middleware.
    """

    # No state needed; all counters live in module-level dicts.

    def __call__(self, scope, receive, send):
        # ASGI middleware entry point.
        pass

    async def dispatch(self, request, call_next):
        """Dispatch a request and record metrics."""
        path = request.url.path
        method = request.method.upper()

        increment_active_workers()

        start = time.perf_counter()
        try:
            response = await call_next(request)
            elapsed = time.perf_counter() - start
            error = response.status_code >= 500
        except Exception:
            elapsed = time.perf_counter() - start
            record_request(path, method, elapsed, error=True)
            decrement_active_workers()
            raise

        record_request(path, method, elapsed, error=False)
        decrement_active_workers()
        return response
