"""Pydantic v2 response schemas for API endpoints."""

from __future__ import annotations

from datetime import date, datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


# ── Pagination ───────────────────────────────────────────────────────


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int
    pages: int


# ── Health ───────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str
    uptime: float
    db: str
    engine: str
    version: str = "0.1.0"


# ── Bot ──────────────────────────────────────────────────────────────


class BotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    strategy_id: str
    state: str
    trading_mode: str
    started_at: datetime | None = None
    updated_at: datetime


class BotControlResponse(BaseModel):
    strategy_id: str
    action: str
    success: bool
    message: str = ""


# ── Position ─────────────────────────────────────────────────────────


class PositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    symbol: str
    side: str
    entry_price: str
    amount: str
    current_price: str
    stop_loss: str | None
    unrealized_pnl: str
    realized_pnl: str
    status: str
    strategy_id: str
    opened_at: datetime
    closed_at: datetime | None = None


# ── Order ────────────────────────────────────────────────────────────


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    symbol: str
    side: str
    order_type: str
    amount: str
    price: str
    status: str
    strategy_id: str
    idempotency_key: str
    slippage_pct: str | None = None
    created_at: datetime
    filled_at: datetime | None = None


# ── Candle ───────────────────────────────────────────────────────────


class CandleResponse(BaseModel):
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


# ── Signal ───────────────────────────────────────────────────────────


class SignalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    symbol: str
    strategy_id: str
    direction: str
    score: float
    components: dict[str, float]
    details: dict[str, object]
    created_at: datetime


# ── PnL ──────────────────────────────────────────────────────────────


class DailyPnLResponse(BaseModel):
    date: str
    strategy_id: str
    realized: str
    unrealized: str
    trade_count: int


class PnLSummaryResponse(BaseModel):
    strategy_id: str
    total_realized: str
    total_trades: int
    win_rate: float
    avg_pnl: str
    max_drawdown: str


# ── Risk ─────────────────────────────────────────────────────────────


class RiskStateResponse(BaseModel):
    strategy_id: str
    consecutive_losses: int
    daily_pnl: str
    cooldown_until: datetime | None = None
    last_updated: datetime


# ── Macro ────────────────────────────────────────────────────────────


class MacroSnapshotResponse(BaseModel):
    timestamp: datetime
    fear_greed: float
    funding_rate: float
    btc_dominance: float
    btc_dom_7d_change: float
    dxy: float
    kimchi_premium: float
    market_score: float


# ── Error ────────────────────────────────────────────────────────────


class ErrorResponse(BaseModel):
    detail: str
    code: str = "error"
