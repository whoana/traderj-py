"""SQLite DataStore implementation for development and testing.

Uses aiosqlite for async in-memory or file-based SQLite.
Implements the shared DataStore Protocol.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

import aiosqlite

from shared.enums import (
    BotStateEnum,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionStatus,
    TradingMode,
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

_SCHEMA = """
CREATE TABLE IF NOT EXISTS candles (
    time TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    open TEXT NOT NULL,
    high TEXT NOT NULL,
    low TEXT NOT NULL,
    close TEXT NOT NULL,
    volume TEXT NOT NULL,
    UNIQUE(symbol, timeframe, time)
);

CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    score TEXT NOT NULL,
    components TEXT NOT NULL,
    details TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    order_type TEXT NOT NULL,
    amount TEXT NOT NULL,
    price TEXT NOT NULL,
    status TEXT NOT NULL,
    idempotency_key TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL,
    slippage_pct TEXT,
    filled_at TEXT
);

CREATE TABLE IF NOT EXISTS positions (
    id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    amount TEXT NOT NULL,
    entry_price TEXT NOT NULL,
    current_price TEXT NOT NULL,
    stop_loss TEXT,
    trailing_stop TEXT,
    unrealized_pnl TEXT NOT NULL,
    realized_pnl TEXT NOT NULL,
    status TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    closed_at TEXT
);

CREATE TABLE IF NOT EXISTS risk_state (
    strategy_id TEXT PRIMARY KEY,
    consecutive_losses INTEGER NOT NULL,
    daily_pnl TEXT NOT NULL,
    last_updated TEXT NOT NULL,
    cooldown_until TEXT
);

CREATE TABLE IF NOT EXISTS bot_state (
    strategy_id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    trading_mode TEXT NOT NULL,
    last_updated TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_balances (
    strategy_id TEXT PRIMARY KEY,
    krw TEXT NOT NULL,
    btc TEXT NOT NULL,
    initial_krw TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_pnl (
    date TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    realized TEXT NOT NULL,
    unrealized TEXT NOT NULL,
    trade_count INTEGER NOT NULL,
    PRIMARY KEY(date, strategy_id)
);

CREATE TABLE IF NOT EXISTS macro_snapshots (
    timestamp TEXT PRIMARY KEY,
    fear_greed REAL NOT NULL,
    funding_rate REAL NOT NULL,
    btc_dominance REAL NOT NULL,
    btc_dom_7d_change REAL NOT NULL,
    dxy REAL NOT NULL,
    kimchi_premium REAL NOT NULL,
    market_score REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS bot_commands (
    id TEXT PRIMARY KEY,
    command TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    params TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    processed_at TEXT
);

CREATE TABLE IF NOT EXISTS backtest_results (
    id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    params_hash TEXT NOT NULL,
    config_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    equity_curve_json TEXT,
    trades_json TEXT,
    walk_forward_json TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bt_strategy ON backtest_results(strategy_id);
CREATE INDEX IF NOT EXISTS idx_bt_created ON backtest_results(created_at DESC);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""


def _dt(val: str | None) -> datetime | None:
    if val is None:
        return None
    return datetime.fromisoformat(val)


def _d(val: str | None) -> date | None:
    if val is None:
        return None
    return date.fromisoformat(val)


class SqliteDataStore:
    """SQLite-based DataStore for development and testing."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        if self._db_path != ":memory:":
            await self._db.execute("PRAGMA journal_mode=WAL")
            await self._db.execute("PRAGMA busy_timeout=5000")
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def disconnect(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        assert self._db is not None, "DataStore not connected"
        return self._db

    # --- Candles ---

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> list[Candle]:
        query = "SELECT * FROM candles WHERE symbol = ? AND timeframe = ?"
        params: list[str | int] = [symbol, timeframe]
        if start:
            query += " AND time >= ?"
            params.append(start.isoformat())
        if end:
            query += " AND time <= ?"
            params.append(end.isoformat())
        query += " ORDER BY time ASC LIMIT ?"
        params.append(limit)

        rows = await self.db.execute_fetchall(query, params)
        return [
            Candle(
                time=datetime.fromisoformat(r["time"]),
                symbol=r["symbol"],
                timeframe=r["timeframe"],
                open=Decimal(r["open"]),
                high=Decimal(r["high"]),
                low=Decimal(r["low"]),
                close=Decimal(r["close"]),
                volume=Decimal(r["volume"]),
            )
            for r in rows
        ]

    async def upsert_candles(self, candles: list[Candle]) -> int:
        count = 0
        for c in candles:
            await self.db.execute(
                """INSERT OR REPLACE INTO candles
                   (time, symbol, timeframe, open, high, low, close, volume)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    c.time.isoformat(),
                    c.symbol,
                    c.timeframe,
                    str(c.open),
                    str(c.high),
                    str(c.low),
                    str(c.close),
                    str(c.volume),
                ),
            )
            count += 1
        await self.db.commit()
        return count

    # --- Signals ---

    async def save_signal(self, signal: Signal) -> None:
        await self.db.execute(
            """INSERT OR REPLACE INTO signals
               (id, strategy_id, symbol, direction, score, components, details, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                signal.id,
                signal.strategy_id,
                signal.symbol,
                signal.direction.value,
                str(signal.score),
                json.dumps(signal.components),
                json.dumps(signal.details, default=str),
                signal.created_at.isoformat(),
            ),
        )
        await self.db.commit()

    async def get_signals(
        self,
        strategy_id: str | None = None,
        limit: int = 50,
    ) -> list[Signal]:
        query = "SELECT * FROM signals"
        params: list[str | int] = []
        if strategy_id:
            query += " WHERE strategy_id = ?"
            params.append(strategy_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = await self.db.execute_fetchall(query, params)
        return [
            Signal(
                id=r["id"],
                strategy_id=r["strategy_id"],
                symbol=r["symbol"],
                direction=r["direction"],
                score=Decimal(r["score"]),
                components=json.loads(r["components"]),
                details=json.loads(r["details"]),
                created_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in rows
        ]

    # --- Orders ---

    async def save_order(self, order: Order) -> None:
        await self.db.execute(
            """INSERT OR REPLACE INTO orders
               (id, strategy_id, symbol, side, order_type, amount, price, status,
                idempotency_key, created_at, slippage_pct, filled_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                order.id,
                order.strategy_id,
                order.symbol,
                order.side.value,
                order.order_type.value,
                str(order.amount),
                str(order.price),
                order.status.value,
                order.idempotency_key,
                order.created_at.isoformat(),
                str(order.slippage_pct) if order.slippage_pct else None,
                order.filled_at.isoformat() if order.filled_at else None,
            ),
        )
        await self.db.commit()

    async def get_orders(
        self,
        strategy_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Order]:
        query = "SELECT * FROM orders WHERE 1=1"
        params: list[str | int] = []
        if strategy_id:
            query += " AND strategy_id = ?"
            params.append(strategy_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = await self.db.execute_fetchall(query, params)
        return [
            Order(
                id=r["id"],
                strategy_id=r["strategy_id"],
                symbol=r["symbol"],
                side=OrderSide(r["side"]),
                order_type=OrderType(r["order_type"]),
                amount=Decimal(r["amount"]),
                price=Decimal(r["price"]),
                status=OrderStatus(r["status"]),
                idempotency_key=r["idempotency_key"],
                created_at=datetime.fromisoformat(r["created_at"]),
                slippage_pct=Decimal(r["slippage_pct"]) if r["slippage_pct"] else None,
                filled_at=_dt(r["filled_at"]),
            )
            for r in rows
        ]

    # --- Positions ---

    async def save_position(self, position: Position) -> None:
        await self.db.execute(
            """INSERT OR REPLACE INTO positions
               (id, strategy_id, symbol, side, amount, entry_price, current_price,
                stop_loss, trailing_stop, unrealized_pnl, realized_pnl, status,
                opened_at, closed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                position.id,
                position.strategy_id,
                position.symbol,
                position.side.value,
                str(position.amount),
                str(position.entry_price),
                str(position.current_price),
                str(position.stop_loss) if position.stop_loss else None,
                str(position.trailing_stop) if position.trailing_stop else None,
                str(position.unrealized_pnl),
                str(position.realized_pnl),
                position.status.value,
                position.opened_at.isoformat(),
                position.closed_at.isoformat() if position.closed_at else None,
            ),
        )
        await self.db.commit()

    async def get_positions(
        self,
        strategy_id: str | None = None,
        status: str | None = None,
    ) -> list[Position]:
        query = "SELECT * FROM positions WHERE 1=1"
        params: list[str] = []
        if strategy_id:
            query += " AND strategy_id = ?"
            params.append(strategy_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY opened_at DESC"

        rows = await self.db.execute_fetchall(query, params)
        return [
            Position(
                id=r["id"],
                strategy_id=r["strategy_id"],
                symbol=r["symbol"],
                side=OrderSide(r["side"]),
                amount=Decimal(r["amount"]),
                entry_price=Decimal(r["entry_price"]),
                current_price=Decimal(r["current_price"]),
                stop_loss=Decimal(r["stop_loss"]) if r["stop_loss"] else None,
                trailing_stop=Decimal(r["trailing_stop"]) if r["trailing_stop"] else None,
                unrealized_pnl=Decimal(r["unrealized_pnl"]),
                realized_pnl=Decimal(r["realized_pnl"]),
                status=PositionStatus(r["status"]),
                opened_at=datetime.fromisoformat(r["opened_at"]),
                closed_at=_dt(r["closed_at"]),
            )
            for r in rows
        ]

    # --- Risk State ---

    async def get_risk_state(self, strategy_id: str) -> RiskState | None:
        row = await self.db.execute_fetchall(
            "SELECT * FROM risk_state WHERE strategy_id = ?", (strategy_id,)
        )
        if not row:
            return None
        r = row[0]
        return RiskState(
            strategy_id=r["strategy_id"],
            consecutive_losses=r["consecutive_losses"],
            daily_pnl=Decimal(r["daily_pnl"]),
            last_updated=datetime.fromisoformat(r["last_updated"]),
            cooldown_until=_dt(r["cooldown_until"]),
        )

    async def save_risk_state(self, risk_state: RiskState) -> None:
        await self.db.execute(
            """INSERT OR REPLACE INTO risk_state
               (strategy_id, consecutive_losses, daily_pnl, last_updated, cooldown_until)
               VALUES (?, ?, ?, ?, ?)""",
            (
                risk_state.strategy_id,
                risk_state.consecutive_losses,
                str(risk_state.daily_pnl),
                risk_state.last_updated.isoformat(),
                risk_state.cooldown_until.isoformat() if risk_state.cooldown_until else None,
            ),
        )
        await self.db.commit()

    # --- Bot State ---

    async def get_bot_state(self, strategy_id: str) -> BotStateModel | None:
        row = await self.db.execute_fetchall(
            "SELECT * FROM bot_state WHERE strategy_id = ?", (strategy_id,)
        )
        if not row:
            return None
        r = row[0]
        return BotStateModel(
            strategy_id=r["strategy_id"],
            state=BotStateEnum(r["state"]),
            trading_mode=TradingMode(r["trading_mode"]),
            last_updated=datetime.fromisoformat(r["last_updated"]),
        )

    async def save_bot_state(self, bot_state: BotStateModel) -> None:
        await self.db.execute(
            """INSERT OR REPLACE INTO bot_state
               (strategy_id, state, trading_mode, last_updated)
               VALUES (?, ?, ?, ?)""",
            (
                bot_state.strategy_id,
                bot_state.state.value,
                bot_state.trading_mode.value,
                bot_state.last_updated.isoformat(),
            ),
        )
        await self.db.commit()

    # --- Paper Balance ---

    async def get_paper_balance(self, strategy_id: str) -> PaperBalance | None:
        row = await self.db.execute_fetchall(
            "SELECT * FROM paper_balances WHERE strategy_id = ?", (strategy_id,)
        )
        if not row:
            return None
        r = row[0]
        return PaperBalance(
            strategy_id=r["strategy_id"],
            krw=Decimal(r["krw"]),
            btc=Decimal(r["btc"]),
            initial_krw=Decimal(r["initial_krw"]),
        )

    async def save_paper_balance(self, balance: PaperBalance) -> None:
        await self.db.execute(
            """INSERT OR REPLACE INTO paper_balances
               (strategy_id, krw, btc, initial_krw)
               VALUES (?, ?, ?, ?)""",
            (
                balance.strategy_id,
                str(balance.krw),
                str(balance.btc),
                str(balance.initial_krw),
            ),
        )
        await self.db.commit()

    # --- Daily PnL ---

    async def get_daily_pnl(
        self,
        strategy_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[DailyPnL]:
        query = "SELECT * FROM daily_pnl WHERE strategy_id = ?"
        params: list[str] = [strategy_id]
        if start_date:
            query += " AND date >= ?"
            params.append(start_date.isoformat())
        if end_date:
            query += " AND date <= ?"
            params.append(end_date.isoformat())
        query += " ORDER BY date ASC"

        rows = await self.db.execute_fetchall(query, params)
        return [
            DailyPnL(
                date=date.fromisoformat(r["date"]),
                strategy_id=r["strategy_id"],
                realized=Decimal(r["realized"]),
                unrealized=Decimal(r["unrealized"]),
                trade_count=r["trade_count"],
            )
            for r in rows
        ]

    async def save_daily_pnl(self, pnl: DailyPnL) -> None:
        await self.db.execute(
            """INSERT OR REPLACE INTO daily_pnl
               (date, strategy_id, realized, unrealized, trade_count)
               VALUES (?, ?, ?, ?, ?)""",
            (
                pnl.date.isoformat(),
                pnl.strategy_id,
                str(pnl.realized),
                str(pnl.unrealized),
                pnl.trade_count,
            ),
        )
        await self.db.commit()

    # --- Macro ---

    async def get_latest_macro(self) -> MacroSnapshot | None:
        row = await self.db.execute_fetchall(
            "SELECT * FROM macro_snapshots ORDER BY timestamp DESC LIMIT 1"
        )
        if not row:
            return None
        r = row[0]
        return MacroSnapshot(
            timestamp=datetime.fromisoformat(r["timestamp"]),
            fear_greed=r["fear_greed"],
            funding_rate=r["funding_rate"],
            btc_dominance=r["btc_dominance"],
            btc_dom_7d_change=r["btc_dom_7d_change"],
            dxy=r["dxy"],
            kimchi_premium=r["kimchi_premium"],
            market_score=r["market_score"],
        )

    async def save_macro_snapshot(self, snapshot: MacroSnapshot) -> None:
        await self.db.execute(
            """INSERT OR REPLACE INTO macro_snapshots
               (timestamp, fear_greed, funding_rate, btc_dominance,
                btc_dom_7d_change, dxy, kimchi_premium, market_score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot.timestamp.isoformat(),
                snapshot.fear_greed,
                snapshot.funding_rate,
                snapshot.btc_dominance,
                snapshot.btc_dom_7d_change,
                snapshot.dxy,
                snapshot.kimchi_premium,
                snapshot.market_score,
            ),
        )
        await self.db.commit()

    # --- Bot Commands ---

    async def save_bot_command(self, command: BotCommand) -> None:
        await self.db.execute(
            """INSERT OR REPLACE INTO bot_commands
               (id, command, strategy_id, params, status, created_at, processed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                command.id,
                command.command,
                command.strategy_id,
                json.dumps(command.params, default=str),
                command.status,
                command.created_at.isoformat(),
                command.processed_at.isoformat() if command.processed_at else None,
            ),
        )
        await self.db.commit()

    async def get_pending_commands(
        self, strategy_id: str | None = None
    ) -> list[BotCommand]:
        query = "SELECT * FROM bot_commands WHERE status = 'pending'"
        params: list[str] = []
        if strategy_id:
            query += " AND strategy_id = ?"
            params.append(strategy_id)
        query += " ORDER BY created_at ASC"

        rows = await self.db.execute_fetchall(query, params)
        return [
            BotCommand(
                id=r["id"],
                command=r["command"],
                strategy_id=r["strategy_id"],
                params=json.loads(r["params"]),
                status=r["status"],
                created_at=datetime.fromisoformat(r["created_at"]),
                processed_at=_dt(r["processed_at"]),
            )
            for r in rows
        ]

    async def mark_command_processed(self, command_id: str) -> None:
        await self.db.execute(
            """UPDATE bot_commands SET status = 'processed',
               processed_at = ? WHERE id = ?""",
            (datetime.now(tz=None).isoformat(), command_id),
        )
        await self.db.commit()

    # --- Backtest Results ---

    async def save_backtest_result(self, result: BacktestResult, params_hash: str) -> None:
        await self.db.execute(
            """INSERT OR REPLACE INTO backtest_results
               (id, strategy_id, params_hash, config_json, metrics_json,
                equity_curve_json, trades_json, walk_forward_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.id,
                result.strategy_id,
                params_hash,
                json.dumps(result.config_json, default=str),
                json.dumps(result.metrics_json, default=str),
                json.dumps(result.equity_curve_json, default=str) if result.equity_curve_json else None,
                json.dumps(result.trades_json, default=str) if result.trades_json else None,
                json.dumps(result.walk_forward_json, default=str) if result.walk_forward_json else None,
                result.created_at.isoformat() if isinstance(result.created_at, datetime) else str(result.created_at),
            ),
        )
        await self.db.commit()

    async def get_backtest_results(
        self,
        strategy_id: str | None = None,
        limit: int = 20,
    ) -> list[BacktestResult]:
        if strategy_id:
            rows = await self.db.execute_fetchall(
                "SELECT * FROM backtest_results WHERE strategy_id = ? ORDER BY created_at DESC LIMIT ?",
                (strategy_id, limit),
            )
        else:
            rows = await self.db.execute_fetchall(
                "SELECT * FROM backtest_results ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        return [
            BacktestResult(
                id=r["id"],
                strategy_id=r["strategy_id"],
                config_json=json.loads(r["config_json"]),
                metrics_json=json.loads(r["metrics_json"]),
                equity_curve_json=json.loads(r["equity_curve_json"]) if r["equity_curve_json"] else [],
                trades_json=json.loads(r["trades_json"]) if r["trades_json"] else [],
                created_at=datetime.fromisoformat(r["created_at"]),
                walk_forward_json=json.loads(r["walk_forward_json"]) if r["walk_forward_json"] else None,
            )
            for r in rows
        ]
