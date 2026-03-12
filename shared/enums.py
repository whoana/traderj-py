"""Shared enum definitions for traderj."""

from __future__ import annotations

from enum import StrEnum


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(StrEnum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"


class PositionStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class BotStateEnum(StrEnum):
    IDLE = "idle"
    STARTING = "starting"
    SCANNING = "scanning"
    VALIDATING = "validating"
    EXECUTING = "executing"
    LOGGING = "logging"
    MONITORING = "monitoring"
    PAUSED = "paused"
    SHUTTING_DOWN = "shutting_down"


class TradingMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"
    SIGNAL_ONLY = "signal_only"


class SignalDirection(StrEnum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class Timeframe(StrEnum):
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"


class RegimeType(StrEnum):
    TRENDING_HIGH_VOL = "trending_high_vol"
    TRENDING_LOW_VOL = "trending_low_vol"
    RANGING_HIGH_VOL = "ranging_high_vol"
    RANGING_LOW_VOL = "ranging_low_vol"


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ScoringMode(StrEnum):
    TREND_FOLLOW = "trend_follow"
    HYBRID = "hybrid"


class EntryMode(StrEnum):
    WEIGHTED = "weighted"
    MAJORITY = "majority"


class StrategyType(StrEnum):
    SIGNAL = "signal"
    DCA = "dca"
    GRID = "grid"
