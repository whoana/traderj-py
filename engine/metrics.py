"""Prometheus metrics for the trading engine.

Exposes an HTTP endpoint on PROMETHEUS_PORT (default 8001) for scraping.
"""

from __future__ import annotations

import os
from threading import Thread

from prometheus_client import Counter, Gauge, Histogram, start_http_server

# ── Trading Metrics ─────────────────────────────────────────────────
ORDER_TOTAL = Counter(
    "traderj_orders_total",
    "Total orders placed",
    ["strategy_id", "side", "status"],
)

ORDER_FAILURES = Counter(
    "traderj_order_failures_total",
    "Total order failures",
    ["strategy_id", "reason"],
)

POSITION_OPEN = Gauge(
    "traderj_positions_open",
    "Number of currently open positions",
    ["strategy_id"],
)

DAILY_PNL_KRW = Gauge(
    "traderj_daily_pnl_krw",
    "Current daily PnL in KRW",
    ["strategy_id"],
)

CONSECUTIVE_LOSSES = Gauge(
    "traderj_consecutive_losses",
    "Current consecutive loss count",
    ["strategy_id"],
)

CIRCUIT_BREAKER_STATE = Gauge(
    "traderj_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=half_open, 2=open)",
    ["strategy_id"],
)

# ── Data Pipeline Metrics ───────────────────────────────────────────
CANDLE_FETCH_DURATION = Histogram(
    "traderj_candle_fetch_duration_seconds",
    "Time to fetch candles from exchange",
    ["symbol", "timeframe"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

SIGNAL_GENERATED = Counter(
    "traderj_signals_total",
    "Total signals generated",
    ["strategy_id", "direction"],
)

# ── WebSocket / IPC ─────────────────────────────────────────────────
WS_CONNECTIONS = Gauge(
    "traderj_ws_connections",
    "Current active WebSocket connections",
)

# ── Infrastructure ──────────────────────────────────────────────────
DB_POOL_USED = Gauge(
    "traderj_db_pool_used",
    "Number of DB connections currently in use",
)

DB_POOL_MAX = Gauge(
    "traderj_db_pool_max",
    "Maximum DB pool size",
)


def start_metrics_server() -> None:
    """Start the Prometheus metrics HTTP server in a daemon thread."""
    port = int(os.environ.get("PROMETHEUS_PORT", "8001"))
    start_http_server(port)
