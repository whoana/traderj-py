"""Shared data models for traderj.

All models are frozen (immutable) dataclasses.
Monetary values use Decimal for precision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from shared.enums import (
    BotStateEnum,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionStatus,
    SignalDirection,
    TradingMode,
)


@dataclass(frozen=True)
class Candle:
    time: datetime
    symbol: str
    timeframe: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True)
class Order:
    id: str
    strategy_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    amount: Decimal
    price: Decimal
    status: OrderStatus
    idempotency_key: str
    created_at: datetime
    slippage_pct: Decimal | None = None
    filled_at: datetime | None = None


@dataclass(frozen=True)
class Position:
    id: str
    strategy_id: str
    symbol: str
    side: OrderSide
    amount: Decimal
    entry_price: Decimal
    current_price: Decimal
    stop_loss: Decimal | None
    trailing_stop: Decimal | None
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    status: PositionStatus
    opened_at: datetime
    closed_at: datetime | None = None
    take_profit: Decimal | None = None


@dataclass(frozen=True)
class Signal:
    id: str
    strategy_id: str
    symbol: str
    direction: SignalDirection
    score: Decimal
    components: dict[str, float]
    details: dict[str, object]
    created_at: datetime


@dataclass(frozen=True)
class RiskState:
    strategy_id: str
    consecutive_losses: int
    daily_pnl: Decimal
    last_updated: datetime
    cooldown_until: datetime | None = None


@dataclass(frozen=True)
class PaperBalance:
    strategy_id: str
    krw: Decimal
    btc: Decimal
    initial_krw: Decimal


@dataclass(frozen=True)
class DailyPnL:
    date: date
    strategy_id: str
    realized: Decimal
    unrealized: Decimal
    trade_count: int


@dataclass(frozen=True)
class MacroSnapshot:
    timestamp: datetime
    fear_greed: float
    funding_rate: float
    btc_dominance: float
    btc_dom_7d_change: float
    dxy: float
    kimchi_premium: float
    market_score: float


@dataclass(frozen=True)
class BotStateModel:
    strategy_id: str
    state: BotStateEnum
    trading_mode: TradingMode
    last_updated: datetime


@dataclass(frozen=True)
class BacktestResult:
    id: str
    strategy_id: str
    config_json: dict[str, object]
    metrics_json: dict[str, object]
    equity_curve_json: list[dict[str, object]]
    trades_json: list[dict[str, object]]
    created_at: datetime
    walk_forward_json: dict[str, object] | None = None


@dataclass(frozen=True)
class BotCommand:
    id: str
    command: str
    strategy_id: str
    params: dict[str, object]
    status: str
    created_at: datetime
    processed_at: datetime | None = None
