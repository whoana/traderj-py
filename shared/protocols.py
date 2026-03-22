"""Shared protocol definitions for traderj.

All protocols use @runtime_checkable for isinstance() checks.
All methods are async unless noted.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from shared.enums import (
    OrderSide,
    OrderType,
)
from shared.models import (
    BacktestResult,
    BotCommand,
    BotStateModel,
    Candle,
    DailyPnL,
    MacroSnapshot,
    Order,
    PaperBalance,
    Position,
    RiskState,
    Signal,
)


@runtime_checkable
class ExchangeClient(Protocol):
    async def fetch_ticker(self, symbol: str) -> dict[str, Any]: ...
    async def fetch_ohlcv(
        self, symbol: str, timeframe: str, limit: int = 200
    ) -> list[Candle]: ...
    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        amount: Decimal,
        price: Decimal | None = None,
    ) -> dict[str, Any]: ...
    async def cancel_order(self, order_id: str, symbol: str) -> dict[str, Any]: ...
    async def fetch_balance(self) -> dict[str, Decimal]: ...


@runtime_checkable
class WebSocketStream(Protocol):
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def subscribe(self, channels: list[str]) -> None: ...
    async def on_message(self, handler: Any) -> None: ...


@runtime_checkable
class DataStore(Protocol):
    # Candles
    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> list[Candle]: ...
    async def upsert_candles(self, candles: list[Candle]) -> int: ...

    # Signals
    async def save_signal(self, signal: Signal) -> None: ...
    async def get_signals(
        self,
        strategy_id: str | None = None,
        limit: int = 50,
    ) -> list[Signal]: ...

    # Orders
    async def save_order(self, order: Order) -> None: ...
    async def get_orders(
        self,
        strategy_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Order]: ...

    # Positions
    async def save_position(self, position: Position) -> None: ...
    async def get_positions(
        self,
        strategy_id: str | None = None,
        status: str | None = None,
    ) -> list[Position]: ...

    # Risk State
    async def get_risk_state(self, strategy_id: str) -> RiskState | None: ...
    async def save_risk_state(self, risk_state: RiskState) -> None: ...

    # Bot State
    async def get_bot_state(self, strategy_id: str) -> BotStateModel | None: ...
    async def save_bot_state(self, bot_state: BotStateModel) -> None: ...

    # Paper Balance
    async def get_paper_balance(self, strategy_id: str) -> PaperBalance | None: ...
    async def save_paper_balance(self, balance: PaperBalance) -> None: ...

    # Daily PnL
    async def get_daily_pnl(
        self,
        strategy_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[DailyPnL]: ...
    async def save_daily_pnl(self, pnl: DailyPnL) -> None: ...

    # Macro
    async def get_latest_macro(self) -> MacroSnapshot | None: ...
    async def save_macro_snapshot(self, snapshot: MacroSnapshot) -> None: ...

    # Bot Commands
    async def save_bot_command(self, command: BotCommand) -> None: ...
    async def get_pending_commands(
        self, strategy_id: str | None = None
    ) -> list[BotCommand]: ...
    async def mark_command_processed(self, command_id: str) -> None: ...

    # Lifecycle
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...


@runtime_checkable
class AnalyticsStore(Protocol):
    async def query_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]: ...
    async def save_backtest_result(self, result: BacktestResult) -> None: ...
    async def get_backtest_results(
        self,
        strategy_id: str | None = None,
        limit: int = 20,
    ) -> list[BacktestResult]: ...


@runtime_checkable
class ScorePlugin(Protocol):
    @property
    def name(self) -> str: ...
    def compute(self, candles: list[Candle], indicators: dict[str, Any]) -> float: ...


@runtime_checkable
class Notifier(Protocol):
    async def send_trade_alert(
        self,
        strategy_id: str,
        side: OrderSide,
        amount: Decimal,
        price: Decimal,
    ) -> None: ...
    async def send_risk_alert(
        self,
        strategy_id: str,
        alert_type: str,
        message: str,
    ) -> None: ...
    async def send_daily_summary(
        self,
        strategy_id: str,
        pnl: DailyPnL,
    ) -> None: ...
    async def send_error(self, message: str) -> None: ...
