"""PostgreSQL DataStore implementation for production.

Uses asyncpg for high-performance async PostgreSQL access.
Implements the shared DataStore Protocol with the same interface as SqliteDataStore.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import asyncpg

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

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS candles (
    time TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    open NUMERIC NOT NULL,
    high NUMERIC NOT NULL,
    low NUMERIC NOT NULL,
    close NUMERIC NOT NULL,
    volume NUMERIC NOT NULL,
    UNIQUE(symbol, timeframe, time)
);

CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    score NUMERIC NOT NULL,
    components JSONB NOT NULL,
    details JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    order_type TEXT NOT NULL,
    amount NUMERIC NOT NULL,
    price NUMERIC NOT NULL,
    status TEXT NOT NULL,
    idempotency_key TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    slippage_pct NUMERIC,
    filled_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS positions (
    id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    amount NUMERIC NOT NULL,
    entry_price NUMERIC NOT NULL,
    current_price NUMERIC NOT NULL,
    stop_loss NUMERIC,
    trailing_stop NUMERIC,
    unrealized_pnl NUMERIC NOT NULL,
    realized_pnl NUMERIC NOT NULL,
    status TEXT NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS risk_state (
    strategy_id TEXT PRIMARY KEY,
    consecutive_losses INTEGER NOT NULL,
    daily_pnl NUMERIC NOT NULL,
    last_updated TIMESTAMPTZ NOT NULL,
    cooldown_until TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS bot_state (
    strategy_id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    trading_mode TEXT NOT NULL,
    last_updated TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_balances (
    strategy_id TEXT PRIMARY KEY,
    krw NUMERIC NOT NULL,
    btc NUMERIC NOT NULL,
    initial_krw NUMERIC NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_pnl (
    date DATE NOT NULL,
    strategy_id TEXT NOT NULL,
    realized NUMERIC NOT NULL,
    unrealized NUMERIC NOT NULL,
    trade_count INTEGER NOT NULL,
    PRIMARY KEY(date, strategy_id)
);

CREATE TABLE IF NOT EXISTS macro_snapshots (
    timestamp TIMESTAMPTZ PRIMARY KEY,
    fear_greed DOUBLE PRECISION NOT NULL,
    funding_rate DOUBLE PRECISION NOT NULL,
    btc_dominance DOUBLE PRECISION NOT NULL,
    btc_dom_7d_change DOUBLE PRECISION NOT NULL,
    dxy DOUBLE PRECISION NOT NULL,
    kimchi_premium DOUBLE PRECISION NOT NULL,
    market_score DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS bot_commands (
    id TEXT PRIMARY KEY,
    command TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    params JSONB NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    processed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS backtest_results (
    id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    params_hash TEXT NOT NULL,
    config_json JSONB NOT NULL,
    metrics_json JSONB NOT NULL,
    equity_curve_json JSONB,
    trades_json JSONB,
    walk_forward_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_candles_symbol_tf_time ON candles(symbol, timeframe, time);
CREATE INDEX IF NOT EXISTS idx_signals_strategy ON signals(strategy_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_strategy ON orders(strategy_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_positions_strategy ON positions(strategy_id);
CREATE INDEX IF NOT EXISTS idx_daily_pnl_strategy ON daily_pnl(strategy_id, date);
CREATE INDEX IF NOT EXISTS idx_bot_commands_pending ON bot_commands(strategy_id, status);
CREATE INDEX IF NOT EXISTS idx_bt_strategy ON backtest_results(strategy_id);
CREATE INDEX IF NOT EXISTS idx_bt_created ON backtest_results(created_at DESC);

CREATE TABLE IF NOT EXISTS tuning_history (
    id              SERIAL PRIMARY KEY,
    tuning_id       TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL,
    strategy_id     TEXT NOT NULL,
    tier            TEXT NOT NULL,
    parameter_name  TEXT NOT NULL,
    old_value       DOUBLE PRECISION NOT NULL,
    new_value       DOUBLE PRECISION NOT NULL,
    change_pct      DOUBLE PRECISION NOT NULL,
    reason          TEXT NOT NULL,
    eval_window     TEXT NOT NULL,
    eval_pf         DOUBLE PRECISION,
    eval_mdd        DOUBLE PRECISION,
    eval_winrate    DOUBLE PRECISION,
    validation_pf   DOUBLE PRECISION,
    validation_mdd  DOUBLE PRECISION,
    llm_provider    TEXT,
    llm_model       TEXT,
    llm_diagnosis   JSONB,
    llm_confidence  TEXT,
    status          TEXT NOT NULL DEFAULT 'applied',
    rollback_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_th_strategy ON tuning_history(strategy_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_th_status ON tuning_history(status);

CREATE TABLE IF NOT EXISTS tuning_report (
    id              SERIAL PRIMARY KEY,
    tuning_id       TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL,
    eval_window     TEXT NOT NULL,
    strategy_id     TEXT NOT NULL,
    regime          TEXT,
    total_trades    INTEGER,
    win_rate        DOUBLE PRECISION,
    profit_factor   DOUBLE PRECISION,
    max_drawdown    DOUBLE PRECISION,
    avg_r_multiple  DOUBLE PRECISION,
    signal_accuracy DOUBLE PRECISION,
    recommendations JSONB,
    applied_changes JSONB
);
CREATE INDEX IF NOT EXISTS idx_tr_strategy ON tuning_report(strategy_id, created_at DESC);
"""


class PostgresDataStore:
    """PostgreSQL-based DataStore for production use."""

    def __init__(
        self,
        dsn: str | None = None,
        *,
        host: str = "localhost",
        port: int = 5432,
        user: str = "traderj",
        password: str = "",
        database: str = "traderj",
        min_size: int = 2,
        max_size: int = 10,
    ) -> None:
        self._dsn = dsn
        self._conn_kwargs: dict[str, Any] = {}
        if dsn is None:
            self._conn_kwargs = {
                "host": host,
                "port": port,
                "user": user,
                "password": password,
                "database": database,
            }
        self._min_size = min_size
        self._max_size = max_size
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self._dsn:
            self._pool = await asyncpg.create_pool(
                self._dsn, min_size=self._min_size, max_size=self._max_size
            )
        else:
            self._pool = await asyncpg.create_pool(
                min_size=self._min_size,
                max_size=self._max_size,
                **self._conn_kwargs,
            )
        async with self._pool.acquire() as conn:
            await conn.execute(_SCHEMA)
        logger.info("PostgresDataStore connected (pool %d-%d)", self._min_size, self._max_size)

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("PostgresDataStore disconnected")

    @property
    def pool(self) -> asyncpg.Pool:
        assert self._pool is not None, "DataStore not connected"
        return self._pool

    # --- Candles ---

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> list[Candle]:
        query = "SELECT * FROM candles WHERE symbol = $1 AND timeframe = $2"
        params: list[Any] = [symbol, timeframe]
        idx = 3
        if start:
            query += f" AND time >= ${idx}"
            params.append(start)
            idx += 1
        if end:
            query += f" AND time <= ${idx}"
            params.append(end)
            idx += 1
        query += f" ORDER BY time DESC LIMIT ${idx}"
        params.append(limit)

        async with self.pool.acquire() as conn:
            rows = list(reversed(await conn.fetch(query, *params)))
        return [
            Candle(
                time=r["time"],
                symbol=r["symbol"],
                timeframe=r["timeframe"],
                open=Decimal(str(r["open"])),
                high=Decimal(str(r["high"])),
                low=Decimal(str(r["low"])),
                close=Decimal(str(r["close"])),
                volume=Decimal(str(r["volume"])),
            )
            for r in rows
        ]

    async def upsert_candles(self, candles: list[Candle]) -> int:
        if not candles:
            return 0
        async with self.pool.acquire() as conn:
            await conn.executemany(
                """INSERT INTO candles (time, symbol, timeframe, open, high, low, close, volume)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                   ON CONFLICT (symbol, timeframe, time)
                   DO UPDATE SET open=$4, high=$5, low=$6, close=$7, volume=$8""",
                [
                    (c.time, c.symbol, c.timeframe, c.open, c.high, c.low, c.close, c.volume)
                    for c in candles
                ],
            )
        return len(candles)

    # --- Signals ---

    async def save_signal(self, signal: Signal) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO signals (id, strategy_id, symbol, direction, score, components, details, created_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                   ON CONFLICT (id) DO UPDATE SET score=$5, components=$6, details=$7""",
                signal.id,
                signal.strategy_id,
                signal.symbol,
                signal.direction.value,
                signal.score,
                json.dumps(signal.components),
                json.dumps(signal.details, default=str),
                signal.created_at,
            )

    async def get_signals(
        self,
        strategy_id: str | None = None,
        limit: int = 50,
    ) -> list[Signal]:
        if strategy_id:
            rows = await self.pool.fetch(
                "SELECT * FROM signals WHERE strategy_id = $1 ORDER BY created_at DESC LIMIT $2",
                strategy_id,
                limit,
            )
        else:
            rows = await self.pool.fetch(
                "SELECT * FROM signals ORDER BY created_at DESC LIMIT $1", limit
            )
        return [
            Signal(
                id=r["id"],
                strategy_id=r["strategy_id"],
                symbol=r["symbol"],
                direction=r["direction"],
                score=Decimal(str(r["score"])),
                components=json.loads(r["components"]) if isinstance(r["components"], str) else r["components"],
                details=json.loads(r["details"]) if isinstance(r["details"], str) else r["details"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    # --- Orders ---

    async def save_order(self, order: Order) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO orders
                   (id, strategy_id, symbol, side, order_type, amount, price, status,
                    idempotency_key, created_at, slippage_pct, filled_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                   ON CONFLICT (id) DO UPDATE SET status=$8, slippage_pct=$11, filled_at=$12""",
                order.id,
                order.strategy_id,
                order.symbol,
                order.side.value,
                order.order_type.value,
                order.amount,
                order.price,
                order.status.value,
                order.idempotency_key,
                order.created_at,
                order.slippage_pct,
                order.filled_at,
            )

    async def get_orders(
        self,
        strategy_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Order]:
        query = "SELECT * FROM orders WHERE TRUE"
        params: list[Any] = []
        idx = 1
        if strategy_id:
            query += f" AND strategy_id = ${idx}"
            params.append(strategy_id)
            idx += 1
        if status:
            query += f" AND status = ${idx}"
            params.append(status)
            idx += 1
        query += f" ORDER BY created_at DESC LIMIT ${idx}"
        params.append(limit)

        rows = await self.pool.fetch(query, *params)
        return [
            Order(
                id=r["id"],
                strategy_id=r["strategy_id"],
                symbol=r["symbol"],
                side=OrderSide(r["side"]),
                order_type=OrderType(r["order_type"]),
                amount=Decimal(str(r["amount"])),
                price=Decimal(str(r["price"])),
                status=OrderStatus(r["status"]),
                idempotency_key=r["idempotency_key"],
                created_at=r["created_at"],
                slippage_pct=Decimal(str(r["slippage_pct"])) if r["slippage_pct"] else None,
                filled_at=r["filled_at"],
            )
            for r in rows
        ]

    # --- Positions ---

    async def save_position(self, position: Position) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO positions
                   (id, strategy_id, symbol, side, amount, entry_price, current_price,
                    stop_loss, trailing_stop, unrealized_pnl, realized_pnl, status,
                    opened_at, closed_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                   ON CONFLICT (id) DO UPDATE SET
                    current_price=$7, stop_loss=$8, trailing_stop=$9,
                    unrealized_pnl=$10, realized_pnl=$11, status=$12, closed_at=$14""",
                position.id,
                position.strategy_id,
                position.symbol,
                position.side.value,
                position.amount,
                position.entry_price,
                position.current_price,
                position.stop_loss,
                position.trailing_stop,
                position.unrealized_pnl,
                position.realized_pnl,
                position.status.value,
                position.opened_at,
                position.closed_at,
            )

    async def get_positions(
        self,
        strategy_id: str | None = None,
        status: str | None = None,
    ) -> list[Position]:
        query = "SELECT * FROM positions WHERE TRUE"
        params: list[Any] = []
        idx = 1
        if strategy_id:
            query += f" AND strategy_id = ${idx}"
            params.append(strategy_id)
            idx += 1
        if status:
            query += f" AND status = ${idx}"
            params.append(status)
            idx += 1
        query += " ORDER BY opened_at DESC"

        rows = await self.pool.fetch(query, *params)
        return [
            Position(
                id=r["id"],
                strategy_id=r["strategy_id"],
                symbol=r["symbol"],
                side=OrderSide(r["side"]),
                amount=Decimal(str(r["amount"])),
                entry_price=Decimal(str(r["entry_price"])),
                current_price=Decimal(str(r["current_price"])),
                stop_loss=Decimal(str(r["stop_loss"])) if r["stop_loss"] else None,
                trailing_stop=Decimal(str(r["trailing_stop"])) if r["trailing_stop"] else None,
                unrealized_pnl=Decimal(str(r["unrealized_pnl"])),
                realized_pnl=Decimal(str(r["realized_pnl"])),
                status=PositionStatus(r["status"]),
                opened_at=r["opened_at"],
                closed_at=r["closed_at"],
            )
            for r in rows
        ]

    # --- Risk State ---

    async def get_risk_state(self, strategy_id: str) -> RiskState | None:
        row = await self.pool.fetchrow(
            "SELECT * FROM risk_state WHERE strategy_id = $1", strategy_id
        )
        if not row:
            return None
        return RiskState(
            strategy_id=row["strategy_id"],
            consecutive_losses=row["consecutive_losses"],
            daily_pnl=Decimal(str(row["daily_pnl"])),
            last_updated=row["last_updated"],
            cooldown_until=row["cooldown_until"],
        )

    async def save_risk_state(self, risk_state: RiskState) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO risk_state
                   (strategy_id, consecutive_losses, daily_pnl, last_updated, cooldown_until)
                   VALUES ($1, $2, $3, $4, $5)
                   ON CONFLICT (strategy_id) DO UPDATE SET
                    consecutive_losses=$2, daily_pnl=$3, last_updated=$4, cooldown_until=$5""",
                risk_state.strategy_id,
                risk_state.consecutive_losses,
                risk_state.daily_pnl,
                risk_state.last_updated,
                risk_state.cooldown_until,
            )

    # --- Bot State ---

    async def get_bot_state(self, strategy_id: str) -> BotStateModel | None:
        row = await self.pool.fetchrow(
            "SELECT * FROM bot_state WHERE strategy_id = $1", strategy_id
        )
        if not row:
            return None
        return BotStateModel(
            strategy_id=row["strategy_id"],
            state=BotStateEnum(row["state"]),
            trading_mode=TradingMode(row["trading_mode"]),
            last_updated=row["last_updated"],
        )

    async def save_bot_state(self, bot_state: BotStateModel) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO bot_state (strategy_id, state, trading_mode, last_updated)
                   VALUES ($1, $2, $3, $4)
                   ON CONFLICT (strategy_id) DO UPDATE SET state=$2, trading_mode=$3, last_updated=$4""",
                bot_state.strategy_id,
                bot_state.state.value,
                bot_state.trading_mode.value,
                bot_state.last_updated,
            )

    # --- Paper Balance ---

    async def get_paper_balance(self, strategy_id: str) -> PaperBalance | None:
        row = await self.pool.fetchrow(
            "SELECT * FROM paper_balances WHERE strategy_id = $1", strategy_id
        )
        if not row:
            return None
        return PaperBalance(
            strategy_id=row["strategy_id"],
            krw=Decimal(str(row["krw"])),
            btc=Decimal(str(row["btc"])),
            initial_krw=Decimal(str(row["initial_krw"])),
        )

    async def save_paper_balance(self, balance: PaperBalance) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO paper_balances (strategy_id, krw, btc, initial_krw)
                   VALUES ($1, $2, $3, $4)
                   ON CONFLICT (strategy_id) DO UPDATE SET krw=$2, btc=$3""",
                balance.strategy_id,
                balance.krw,
                balance.btc,
                balance.initial_krw,
            )

    # --- Daily PnL ---

    async def get_daily_pnl(
        self,
        strategy_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[DailyPnL]:
        query = "SELECT * FROM daily_pnl WHERE strategy_id = $1"
        params: list[Any] = [strategy_id]
        idx = 2
        if start_date:
            query += f" AND date >= ${idx}"
            params.append(start_date)
            idx += 1
        if end_date:
            query += f" AND date <= ${idx}"
            params.append(end_date)
            idx += 1
        query += " ORDER BY date ASC"

        rows = await self.pool.fetch(query, *params)
        return [
            DailyPnL(
                date=r["date"],
                strategy_id=r["strategy_id"],
                realized=Decimal(str(r["realized"])),
                unrealized=Decimal(str(r["unrealized"])),
                trade_count=r["trade_count"],
            )
            for r in rows
        ]

    async def save_daily_pnl(self, pnl: DailyPnL) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO daily_pnl (date, strategy_id, realized, unrealized, trade_count)
                   VALUES ($1, $2, $3, $4, $5)
                   ON CONFLICT (date, strategy_id) DO UPDATE SET
                    realized=$3, unrealized=$4, trade_count=$5""",
                pnl.date,
                pnl.strategy_id,
                pnl.realized,
                pnl.unrealized,
                pnl.trade_count,
            )

    # --- Macro ---

    async def get_latest_macro(self) -> MacroSnapshot | None:
        row = await self.pool.fetchrow(
            "SELECT * FROM macro_snapshots ORDER BY timestamp DESC LIMIT 1"
        )
        if not row:
            return None
        return MacroSnapshot(
            timestamp=row["timestamp"],
            fear_greed=row["fear_greed"],
            funding_rate=row["funding_rate"],
            btc_dominance=row["btc_dominance"],
            btc_dom_7d_change=row["btc_dom_7d_change"],
            dxy=row["dxy"],
            kimchi_premium=row["kimchi_premium"],
            market_score=row["market_score"],
        )

    async def save_macro_snapshot(self, snapshot: MacroSnapshot) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO macro_snapshots
                   (timestamp, fear_greed, funding_rate, btc_dominance,
                    btc_dom_7d_change, dxy, kimchi_premium, market_score)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                   ON CONFLICT (timestamp) DO UPDATE SET
                    fear_greed=$2, funding_rate=$3, btc_dominance=$4,
                    btc_dom_7d_change=$5, dxy=$6, kimchi_premium=$7, market_score=$8""",
                snapshot.timestamp,
                snapshot.fear_greed,
                snapshot.funding_rate,
                snapshot.btc_dominance,
                snapshot.btc_dom_7d_change,
                snapshot.dxy,
                snapshot.kimchi_premium,
                snapshot.market_score,
            )

    # --- Bot Commands ---

    async def save_bot_command(self, command: BotCommand) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO bot_commands
                   (id, command, strategy_id, params, status, created_at, processed_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)
                   ON CONFLICT (id) DO UPDATE SET status=$5, processed_at=$7""",
                command.id,
                command.command,
                command.strategy_id,
                json.dumps(command.params, default=str),
                command.status,
                command.created_at,
                command.processed_at,
            )

    async def get_pending_commands(
        self, strategy_id: str | None = None
    ) -> list[BotCommand]:
        if strategy_id:
            rows = await self.pool.fetch(
                "SELECT * FROM bot_commands WHERE status = 'pending' AND strategy_id = $1 ORDER BY created_at ASC",
                strategy_id,
            )
        else:
            rows = await self.pool.fetch(
                "SELECT * FROM bot_commands WHERE status = 'pending' ORDER BY created_at ASC"
            )
        return [
            BotCommand(
                id=r["id"],
                command=r["command"],
                strategy_id=r["strategy_id"],
                params=json.loads(r["params"]) if isinstance(r["params"], str) else r["params"],
                status=r["status"],
                created_at=r["created_at"],
                processed_at=r["processed_at"],
            )
            for r in rows
        ]

    async def mark_command_processed(self, command_id: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE bot_commands SET status = 'processed', processed_at = NOW() WHERE id = $1",
                command_id,
            )

    # --- Backtest Results ---

    async def save_backtest_result(self, result: BacktestResult, params_hash: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO backtest_results
                   (id, strategy_id, params_hash, config_json, metrics_json,
                    equity_curve_json, trades_json, walk_forward_json, created_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                   ON CONFLICT (id) DO UPDATE SET
                    metrics_json=$5, equity_curve_json=$6, trades_json=$7, walk_forward_json=$8""",
                result.id,
                result.strategy_id,
                params_hash,
                json.dumps(result.config_json, default=str),
                json.dumps(result.metrics_json, default=str),
                json.dumps(result.equity_curve_json, default=str) if result.equity_curve_json else None,
                json.dumps(result.trades_json, default=str) if result.trades_json else None,
                json.dumps(result.walk_forward_json, default=str) if result.walk_forward_json else None,
                result.created_at,
            )

    async def get_backtest_results(
        self,
        strategy_id: str | None = None,
        limit: int = 20,
    ) -> list[BacktestResult]:
        if strategy_id:
            rows = await self.pool.fetch(
                "SELECT * FROM backtest_results WHERE strategy_id = $1 ORDER BY created_at DESC LIMIT $2",
                strategy_id,
                limit,
            )
        else:
            rows = await self.pool.fetch(
                "SELECT * FROM backtest_results ORDER BY created_at DESC LIMIT $1",
                limit,
            )
        return [
            BacktestResult(
                id=r["id"],
                strategy_id=r["strategy_id"],
                config_json=json.loads(r["config_json"]) if isinstance(r["config_json"], str) else r["config_json"],
                metrics_json=json.loads(r["metrics_json"]) if isinstance(r["metrics_json"], str) else r["metrics_json"],
                equity_curve_json=json.loads(r["equity_curve_json"]) if isinstance(r["equity_curve_json"], str) else r["equity_curve_json"],
                trades_json=json.loads(r["trades_json"]) if isinstance(r["trades_json"], str) else r["trades_json"],
                created_at=r["created_at"],
                walk_forward_json=json.loads(r["walk_forward_json"]) if r["walk_forward_json"] and isinstance(r["walk_forward_json"], str) else r["walk_forward_json"],
            )
            for r in rows
        ]
