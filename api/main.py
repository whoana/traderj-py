"""FastAPI application factory for traderj API server.

Supports two modes:
  - Standalone: `uvicorn api.main:app` — creates own DataStore + IPC
  - Embedded: `create_embedded_app()` — shares engine's components directly
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.deps import app_state
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
from api.routes import balance, config, control, engine, passkeys, version
from api.ws import handler as ws_handler
from api.ws.manager import manager as ws_manager

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    """Configure structured logging with sensitive data filter."""
    sensitive_filter = SensitiveDataFilter()
    for handler in logging.root.handlers:
        handler.addFilter(sensitive_filter)
    for name in ("uvicorn.access", "uvicorn.error", "api"):
        log = logging.getLogger(name)
        for h in log.handlers:
            h.addFilter(sensitive_filter)


@asynccontextmanager
async def _standalone_lifespan(app: FastAPI):
    """Standalone mode: create own DataStore + IPC client."""
    _setup_logging()

    from api.ipc_client import IPCClient
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

    heartbeat_task.cancel()
    await ipc.stop()
    if app_state.data_store is not None:
        close = getattr(app_state.data_store, "disconnect", None) or getattr(app_state.data_store, "close", None)
        if close and callable(close):
            await close()


@asynccontextmanager
async def _embedded_lifespan(app: FastAPI):
    """Embedded mode: components already injected, just manage WS heartbeat."""
    heartbeat_task = asyncio.create_task(ws_manager.heartbeat_loop())
    logger.info("API server started (embedded mode)")
    yield
    heartbeat_task.cancel()
    logger.info("API server stopped (embedded mode)")


def _get_cors_origins() -> list[str]:
    """Read allowed CORS origins from environment."""
    raw = os.environ.get("CORS_ORIGINS", "http://localhost:3000")
    return [o.strip() for o in raw.split(",") if o.strip()]


def _configure_app(app: FastAPI) -> FastAPI:
    """Add middleware, routes, and error handlers to a FastAPI app."""
    # ── Middleware ─────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_get_cors_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["X-API-Key", "Content-Type", "Authorization"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(PrometheusMiddleware)

    # ── Metrics ───────────────────────────────────────────────────
    app.add_api_route("/metrics", metrics_endpoint, methods=["GET"], include_in_schema=False)

    # ── Routes (existing) ─────────────────────────────────────────
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

    # ── Routes (new — Phase 2) ────────────────────────────────────
    app.include_router(balance.router, prefix="/api/v1")
    app.include_router(engine.router, prefix="/api/v1")
    app.include_router(control.router, prefix="/api/v1")
    app.include_router(config.router, prefix="/api/v1")
    app.include_router(version.router, prefix="/api/v1")
    app.include_router(passkeys.router, prefix="/api/v1")

    # ── WebSocket ─────────────────────────────────────────────────
    app.include_router(ws_handler.router)

    # ── Global error handler ──────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "code": "internal_error"},
        )

    return app


def create_app() -> FastAPI:
    """Build standalone FastAPI application (own DataStore + IPC)."""
    app = FastAPI(
        title="traderj API",
        version="0.2.0",
        description="BTC/KRW automated trading bot REST API",
        lifespan=_standalone_lifespan,
        docs_url="/api/v1/docs" if os.environ.get("TRADERJ_ENV") != "production" else None,
        redoc_url="/api/v1/redoc" if os.environ.get("TRADERJ_ENV") != "production" else None,
    )
    return _configure_app(app)


def create_embedded_app(
    data_store: Any,
    trading_loops: dict[str, Any],
    event_bus: Any,
    exchange: Any,
    settings: Any = None,
) -> FastAPI:
    """Build embedded FastAPI application sharing engine components.

    Used when API runs inside the engine process (Fly.io single-process mode).
    """
    # Inject shared components
    app_state.set_data_store(data_store)
    app_state.set_trading_loops(trading_loops)
    app_state.set_event_bus(event_bus)
    app_state.set_exchange(exchange)
    if settings:
        app_state.set_settings(settings)
    app_state.embedded = True

    app = FastAPI(
        title="traderj API",
        version="0.2.0",
        description="BTC/KRW automated trading bot REST API (embedded)",
        lifespan=_embedded_lifespan,
        docs_url="/api/v1/docs" if os.environ.get("TRADERJ_ENV") != "production" else None,
        redoc_url="/api/v1/redoc" if os.environ.get("TRADERJ_ENV") != "production" else None,
    )
    return _configure_app(app)


# Default app instance for `uvicorn api.main:app`
app = create_app()
