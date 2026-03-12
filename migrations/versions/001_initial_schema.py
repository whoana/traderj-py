"""Initial schema — 10 tables + bot_commands.

Revision ID: 001
Revises: None
Create Date: 2026-03-03
"""
from __future__ import annotations

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("""
    -- =========================================================================
    -- candles: OHLCV time-series (will become hypertable in 002)
    -- =========================================================================
    CREATE TABLE candles (
        time        TIMESTAMPTZ     NOT NULL,
        symbol      TEXT            NOT NULL,
        timeframe   TEXT            NOT NULL,
        open        NUMERIC(18,8)   NOT NULL,
        high        NUMERIC(18,8)   NOT NULL,
        low         NUMERIC(18,8)   NOT NULL,
        close       NUMERIC(18,8)   NOT NULL,
        volume      NUMERIC(24,8)   NOT NULL,
        UNIQUE(symbol, timeframe, time)
    );

    CREATE INDEX idx_candles_symbol_tf_time ON candles(symbol, timeframe, time DESC);

    -- =========================================================================
    -- signals: strategy signal history
    -- =========================================================================
    CREATE TABLE signals (
        id              SERIAL          PRIMARY KEY,
        timestamp       TIMESTAMPTZ     NOT NULL,
        symbol          TEXT            NOT NULL,
        strategy_id     TEXT            NOT NULL,
        direction       TEXT            NOT NULL,
        score           REAL            NOT NULL,
        timeframe       TEXT            NOT NULL,
        components      JSONB           NOT NULL,
        details         JSONB           DEFAULT '{}',
        created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
    );

    CREATE INDEX idx_signals_strategy_ts ON signals(strategy_id, timestamp DESC);
    CREATE INDEX idx_signals_symbol_ts ON signals(symbol, timestamp DESC);

    -- =========================================================================
    -- orders: trade orders with idempotency
    -- =========================================================================
    CREATE TABLE orders (
        id              SERIAL          PRIMARY KEY,
        exchange_id     TEXT,
        symbol          TEXT            NOT NULL,
        side            TEXT            NOT NULL,
        order_type      TEXT            NOT NULL,
        amount          NUMERIC(18,8)   NOT NULL,
        price           NUMERIC(18,8),
        cost            NUMERIC(18,8),
        fee             NUMERIC(18,8)   NOT NULL DEFAULT 0,
        status          TEXT            NOT NULL DEFAULT 'pending',
        is_paper        BOOLEAN         NOT NULL DEFAULT TRUE,
        signal_id       INTEGER         REFERENCES signals(id),
        strategy_id     TEXT            NOT NULL,
        idempotency_key TEXT            NOT NULL UNIQUE,
        expected_price  NUMERIC(18,8),
        actual_price    NUMERIC(18,8),
        slippage_pct    REAL,
        retry_count     INTEGER         NOT NULL DEFAULT 0,
        error_message   TEXT,
        created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
        filled_at       TIMESTAMPTZ
    );

    CREATE INDEX idx_orders_strategy_ts ON orders(strategy_id, created_at DESC);
    CREATE INDEX idx_orders_status ON orders(status) WHERE status = 'pending';

    -- =========================================================================
    -- positions: open/closed positions
    -- =========================================================================
    CREATE TABLE positions (
        id              SERIAL          PRIMARY KEY,
        symbol          TEXT            NOT NULL,
        side            TEXT            NOT NULL DEFAULT 'long',
        entry_price     NUMERIC(18,8)   NOT NULL,
        amount          NUMERIC(18,8)   NOT NULL,
        current_price   NUMERIC(18,8)   NOT NULL DEFAULT 0,
        stop_loss       NUMERIC(18,8)   NOT NULL DEFAULT 0,
        unrealized_pnl  NUMERIC(18,2)   NOT NULL DEFAULT 0,
        realized_pnl    NUMERIC(18,2)   NOT NULL DEFAULT 0,
        status          TEXT            NOT NULL DEFAULT 'open',
        entry_order_id  INTEGER         REFERENCES orders(id),
        exit_order_id   INTEGER         REFERENCES orders(id),
        strategy_id     TEXT            NOT NULL,
        opened_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
        closed_at       TIMESTAMPTZ
    );

    CREATE INDEX idx_positions_open ON positions(strategy_id, status) WHERE status = 'open';
    CREATE INDEX idx_positions_strategy_ts ON positions(strategy_id, opened_at DESC);

    -- =========================================================================
    -- risk_state: per-strategy risk tracking (write-through persistence)
    -- =========================================================================
    CREATE TABLE risk_state (
        strategy_id         TEXT            PRIMARY KEY,
        consecutive_losses  INTEGER         NOT NULL DEFAULT 0,
        daily_pnl           NUMERIC(18,2)   NOT NULL DEFAULT 0,
        daily_date          DATE            NOT NULL DEFAULT CURRENT_DATE,
        cooldown_until      TIMESTAMPTZ,
        total_trades        INTEGER         NOT NULL DEFAULT 0,
        total_wins          INTEGER         NOT NULL DEFAULT 0,
        last_atr            REAL,
        updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
    );

    -- =========================================================================
    -- bot_state: bot lifecycle state machine
    -- =========================================================================
    CREATE TABLE bot_state (
        strategy_id     TEXT            PRIMARY KEY,
        state           TEXT            NOT NULL DEFAULT 'IDLE',
        trading_mode    TEXT            NOT NULL DEFAULT 'paper',
        started_at      TIMESTAMPTZ,
        updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
    );

    -- =========================================================================
    -- paper_balances: virtual balances for paper trading
    -- =========================================================================
    CREATE TABLE paper_balances (
        strategy_id     TEXT            PRIMARY KEY,
        krw             NUMERIC(18,2)   NOT NULL DEFAULT 10000000,
        btc             NUMERIC(18,8)   NOT NULL DEFAULT 0,
        initial_krw     NUMERIC(18,2)   NOT NULL DEFAULT 10000000,
        updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
    );

    -- =========================================================================
    -- daily_pnl: daily profit/loss tracking
    -- =========================================================================
    CREATE TABLE daily_pnl (
        id              SERIAL          PRIMARY KEY,
        date            DATE            NOT NULL,
        strategy_id     TEXT            NOT NULL,
        realized        NUMERIC(18,2)   NOT NULL DEFAULT 0,
        unrealized      NUMERIC(18,2)   NOT NULL DEFAULT 0,
        total_value     NUMERIC(18,2)   NOT NULL DEFAULT 0,
        trade_count     INTEGER         NOT NULL DEFAULT 0,
        win_count       INTEGER         NOT NULL DEFAULT 0,
        loss_count      INTEGER         NOT NULL DEFAULT 0,
        UNIQUE(date, strategy_id)
    );

    -- =========================================================================
    -- macro_snapshots: macro indicator snapshots
    -- =========================================================================
    CREATE TABLE macro_snapshots (
        id              SERIAL          PRIMARY KEY,
        timestamp       TIMESTAMPTZ     NOT NULL,
        fear_greed      REAL,
        btc_dominance   REAL,
        dxy             REAL,
        nasdaq          REAL,
        kimchi_premium  REAL,
        funding_rate    REAL,
        btc_dom_7d_change REAL,
        market_score    REAL,
        created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
    );

    CREATE INDEX idx_macro_ts ON macro_snapshots(timestamp DESC);

    -- =========================================================================
    -- bot_commands: IPC fallback queue (DB-based)
    -- =========================================================================
    CREATE TABLE bot_commands (
        id              SERIAL          PRIMARY KEY,
        strategy_id     TEXT            NOT NULL,
        command         TEXT            NOT NULL,
        payload         JSONB           DEFAULT '{}',
        status          TEXT            NOT NULL DEFAULT 'pending',
        created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
        processed_at    TIMESTAMPTZ
    );

    CREATE INDEX idx_bot_commands_pending ON bot_commands(status, created_at)
        WHERE status = 'pending';
    """)


def downgrade() -> None:
    op.execute("""
    DROP TABLE IF EXISTS bot_commands CASCADE;
    DROP TABLE IF EXISTS macro_snapshots CASCADE;
    DROP TABLE IF EXISTS daily_pnl CASCADE;
    DROP TABLE IF EXISTS paper_balances CASCADE;
    DROP TABLE IF EXISTS bot_state CASCADE;
    DROP TABLE IF EXISTS risk_state CASCADE;
    DROP TABLE IF EXISTS positions CASCADE;
    DROP TABLE IF EXISTS orders CASCADE;
    DROP TABLE IF EXISTS signals CASCADE;
    DROP TABLE IF EXISTS candles CASCADE;
    """)
