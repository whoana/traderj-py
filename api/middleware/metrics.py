"""Prometheus metrics middleware for FastAPI."""

from __future__ import annotations

import time

from fastapi import Request, Response
from prometheus_client import Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

# ── Metrics ─────────────────────────────────────────────────────────
REQUEST_COUNT = Counter(
    "traderj_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)

REQUEST_DURATION = Histogram(
    "traderj_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

REQUEST_ERRORS = Counter(
    "traderj_http_request_errors_total",
    "Total HTTP request errors (4xx/5xx)",
    ["method", "path", "status"],
)

WS_CONNECTIONS = Counter(
    "traderj_ws_connections_total",
    "Total WebSocket connections",
)


def _normalize_path(path: str) -> str:
    """Collapse dynamic path segments to reduce cardinality."""
    parts = path.strip("/").split("/")
    normalized = []
    for part in parts:
        # Collapse UUIDs and numeric IDs
        if len(part) > 20 or (part and part.replace("-", "").isalnum() and any(c.isdigit() for c in part) and len(part) > 8):
            normalized.append(":id")
        else:
            normalized.append(part)
    return "/" + "/".join(normalized)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Collect request metrics for Prometheus scraping."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path == "/metrics":
            return await call_next(request)

        method = request.method
        path = _normalize_path(request.url.path)

        start = time.perf_counter()
        response: Response = await call_next(request)
        duration = time.perf_counter() - start

        status = str(response.status_code)
        REQUEST_COUNT.labels(method=method, path=path, status=status).inc()
        REQUEST_DURATION.labels(method=method, path=path).observe(duration)

        if response.status_code >= 400:
            REQUEST_ERRORS.labels(method=method, path=path, status=status).inc()

        return response


async def metrics_endpoint(request: Request) -> StarletteResponse:
    """Expose /metrics for Prometheus scraping."""
    return StarletteResponse(
        content=generate_latest(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
