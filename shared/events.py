"""Shared event definitions for traderj EventBus.

All events are frozen (immutable) dataclasses with a timestamp field.
13 event types covering the full trading pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from time import time

from shared.enums import (
    AlertSeverity,
    BotStateEnum,
    OrderSide,
    OrderType,
    RegimeType,
    SignalDirection,
)
from shared.models import Candle


@dataclass(frozen=True)
class MarketTickEvent:
    symbol: str
    price: Decimal
    bid: Decimal
    ask: Decimal
    volume_24h: Decimal
    timestamp: float = field(default_factory=time)


@dataclass(frozen=True)
class OHLCVUpdateEvent:
    symbol: str
    timeframe: str
    candles: list[Candle]
    timestamp: float = field(default_factory=time)


@dataclass(frozen=True)
class SignalEvent:
    strategy_id: str
    symbol: str
    direction: SignalDirection
    score: float
    components: dict[str, float]
    details: dict[str, object]
    timestamp: float = field(default_factory=time)


@dataclass(frozen=True)
class OrderRequestEvent:
    strategy_id: str
    symbol: str
    side: OrderSide
    amount: Decimal
    order_type: OrderType
    idempotency_key: str
    timestamp: float = field(default_factory=time)


@dataclass(frozen=True)
class OrderFilledEvent:
    order_id: str
    strategy_id: str
    symbol: str
    side: OrderSide
    amount: Decimal
    actual_price: Decimal
    slippage_pct: float
    timestamp: float = field(default_factory=time)


@dataclass(frozen=True)
class PositionOpenedEvent:
    position_id: str
    strategy_id: str
    symbol: str
    entry_price: Decimal
    amount: Decimal
    timestamp: float = field(default_factory=time)
    stop_loss: Decimal | None = None


@dataclass(frozen=True)
class PositionClosedEvent:
    position_id: str
    strategy_id: str
    symbol: str
    realized_pnl: Decimal
    exit_reason: str
    timestamp: float = field(default_factory=time)


@dataclass(frozen=True)
class StopLossTriggeredEvent:
    position_id: str
    strategy_id: str
    trigger_price: Decimal
    stop_loss_price: Decimal
    timestamp: float = field(default_factory=time)


@dataclass(frozen=True)
class TakeProfitTriggeredEvent:
    position_id: str
    strategy_id: str
    trigger_price: Decimal
    take_profit_price: Decimal
    timestamp: float = field(default_factory=time)


@dataclass(frozen=True)
class TrailingStopUpdatedEvent:
    position_id: str
    strategy_id: str
    old_stop: Decimal
    new_stop: Decimal
    current_price: Decimal
    timestamp: float = field(default_factory=time)


@dataclass(frozen=True)
class RiskAlertEvent:
    strategy_id: str
    alert_type: str
    message: str
    severity: AlertSeverity
    timestamp: float = field(default_factory=time)


@dataclass(frozen=True)
class BotStateChangeEvent:
    strategy_id: str
    old_state: BotStateEnum
    new_state: BotStateEnum
    reason: str
    timestamp: float = field(default_factory=time)


@dataclass(frozen=True)
class RegimeChangeEvent:
    strategy_id: str
    old_regime: RegimeType | None
    new_regime: RegimeType
    overrides: dict[str, object]
    timestamp: float = field(default_factory=time)


@dataclass(frozen=True)
class RiskStateEvent:
    strategy_id: str
    consecutive_losses: int
    daily_pnl: float
    position_pct: float
    atr_pct: float
    volatility_status: str
    timestamp: float = field(default_factory=time)
    cooldown_until: datetime | None = None


@dataclass(frozen=True)
class MarketDataEvent:
    symbol: str
    ohlcv_by_tf: dict[str, list[Candle]]
    timestamp: float = field(default_factory=time)


# All event types for EventBus type registration
EVENT_TYPES = (
    MarketTickEvent,
    OHLCVUpdateEvent,
    SignalEvent,
    OrderRequestEvent,
    OrderFilledEvent,
    PositionOpenedEvent,
    PositionClosedEvent,
    StopLossTriggeredEvent,
    TakeProfitTriggeredEvent,
    TrailingStopUpdatedEvent,
    RiskAlertEvent,
    BotStateChangeEvent,
    RegimeChangeEvent,
    RiskStateEvent,
    MarketDataEvent,
)
