"""FastAPI application factory for traderj API server."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.deps import app_state
from api.ipc_client import IPCClient
from api.middleware.metrics import PrometheusMiddleware, metrics_endpoint
from api.middleware.security import SecurityHeadersMiddleware, SensitiveDataFilter
from api.routes import (
    analytics,
    bots,
    candles,
    health,
    macro,
    orders,
    pnl,
    positions,
    risk,
    signals,
)
from api.ws import handler as ws_handler
from api.ws.manager import manager as ws_manager

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    """Configure structured logging with sensitive data filter."""
    sensitive_filter = SensitiveDataFilter()
    for handler in logging.root.handlers:
        handler.addFilter(sensitive_filter)
    # Also apply to uvicorn access logger
    for name in ("uvicorn.access", "uvicorn.error", "api"):
        log = logging.getLogger(name)
        for h in log.handlers:
            h.addFilter(sensitive_filter)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    _setup_logging()

    # ── Startup ──────────────────────────────────────────────────
    from engine.config.settings import DatabaseSettings
    from engine.data import create_data_store

    store = create_data_store(DatabaseSettings())
    await store.connect()
    app_state.set_data_store(store)

    heartbeat_task = asyncio.create_task(ws_manager.heartbeat_loop())
    ipc = IPCClient()
    await ipc.start()
    if app_state.engine_client is None:
        app_state.set_engine_client(ipc)

    yield

    # ── Shutdown ─────────────────────────────────────────────────
    heartbeat_task.cancel()
    await ipc.stop()
    if app_state.data_store is not None:
        close = getattr(app_state.data_store, "disconnect", None) or getattr(app_state.data_store, "close", None)
        if close and callable(close):
            await close()


def _get_cors_origins() -> list[str]:
    """Read allowed CORS origins from environment."""
    raw = os.environ.get("CORS_ORIGINS", "http://localhost:3000")
    return [o.strip() for o in raw.split(",") if o.strip()]


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="traderj API",
        version="0.1.0",
        description="BTC/KRW automated trading bot REST API",
        lifespan=lifespan,
        docs_url="/api/v1/docs" if os.environ.get("TRADERJ_ENV") != "production" else None,
        redoc_url="/api/v1/redoc" if os.environ.get("TRADERJ_ENV") != "production" else None,
    )

    # ── Middleware (order: last added = first executed) ───────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_get_cors_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["X-API-Key", "Content-Type", "Authorization"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(PrometheusMiddleware)

    # ── Metrics endpoint ─────────────────────────────────────────
    app.add_api_route("/metrics", metrics_endpoint, methods=["GET"], include_in_schema=False)

    # ── Routes ───────────────────────────────────────────────────
    app.include_router(health.router)
    app.include_router(bots.router, prefix="/api/v1")
    app.include_router(positions.router, prefix="/api/v1")
    app.include_router(orders.router, prefix="/api/v1")
    app.include_router(candles.router, prefix="/api/v1")
    app.include_router(signals.router, prefix="/api/v1")
    app.include_router(pnl.router, prefix="/api/v1")
    app.include_router(risk.router, prefix="/api/v1")
    app.include_router(macro.router, prefix="/api/v1")
    app.include_router(analytics.router, prefix="/api/v1")

    # ── WebSocket ────────────────────────────────────────────────
    app.include_router(ws_handler.router)

    # ── Global error handler ─────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "code": "internal_error"},
        )

    return app


# Default app instance for `uvicorn api.main:app`
app = create_app()
