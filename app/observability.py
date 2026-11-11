"""
Prometheus observability instrumentation and /metrics endpoint for CortexCICD.

Registers HTTP request counters/latency histograms matching the PromQL queries
used by ``app/integrations/prometheus_client.py`` (`flask_http_request_total`),
plus domain counters for pipeline runs and self-healing actions.
"""

from __future__ import annotations

import time
from flask import Response, g, request

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )

    HTTP_REQUESTS_TOTAL = Counter(
        "flask_http_request_total",
        "Total HTTP requests processed by CortexCICD",
        ["method", "endpoint", "status"],
    )
    HTTP_REQUEST_DURATION = Histogram(
        "flask_http_request_duration_seconds",
        "HTTP request latency in seconds",
        ["method", "endpoint"],
    )
    PIPELINE_RUNS_TOTAL = Counter(
        "cortex_pipeline_runs_total",
        "Total pipeline runs triggered or updated",
        ["status", "triggered_by"],
    )
    HEALING_EVENTS_TOTAL = Counter(
        "cortex_healing_events_total",
        "Total autonomous healing executions",
        ["strategy", "outcome"],
    )
    SSE_SUBSCRIBERS_GAUGE = Gauge(
        "cortex_sse_subscribers",
        "Active SSE subscriber connections",
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:  # pragma: no cover — fallback if prometheus_client omitted
    _PROMETHEUS_AVAILABLE = False


def record_pipeline_event(status: str, triggered_by: str) -> None:
    """Increment the pipeline run Prometheus counter if enabled."""
    if _PROMETHEUS_AVAILABLE:
        PIPELINE_RUNS_TOTAL.labels(
            status=status or "unknown",
            triggered_by=triggered_by or "unknown",
        ).inc()


def record_healing_event(strategy: str, outcome: str) -> None:
    """Increment the self-healing Prometheus counter if enabled."""
    if _PROMETHEUS_AVAILABLE:
        HEALING_EVENTS_TOTAL.labels(
            strategy=strategy or "unknown",
            outcome=outcome or "unknown",
        ).inc()


def init_observability(app) -> None:
    """Attach HTTP metrics hooks and expose GET /metrics on the Flask app."""

    @app.before_request
    def _metrics_start_timer():
        g._cortex_req_start = time.perf_counter()

    @app.after_request
    def _metrics_record_response(response):
        if not _PROMETHEUS_AVAILABLE:
            return response
        if request.path == "/metrics":
            return response
        endpoint = request.endpoint or "unknown"
        method = request.method
        HTTP_REQUESTS_TOTAL.labels(
            method=method,
            endpoint=endpoint,
            status=str(response.status_code),
        ).inc()
        start = getattr(g, "_cortex_req_start", None)
        if start is not None:
            HTTP_REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(
                max(time.perf_counter() - start, 0.0)
            )
        return response

    @app.route("/metrics")
    def prometheus_metrics():
        """Expose Prometheus text exposition metrics."""
        if not _PROMETHEUS_AVAILABLE:
            return Response(
                "# prometheus_client package not installed\n",
                status=200,
                mimetype="text/plain; charset=utf-8",
            )
        try:
            from app.events import subscriber_count
            SSE_SUBSCRIBERS_GAUGE.set(subscriber_count())
        except Exception:
            pass
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

