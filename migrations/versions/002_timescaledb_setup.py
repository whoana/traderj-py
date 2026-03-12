"""TimescaleDB hypertable, continuous aggregate, retention policy.

Revision ID: 002
Revises: 001
Create Date: 2026-03-03
"""
from __future__ import annotations

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("""
    -- Convert candles to hypertable
    SELECT create_hypertable('candles', by_range('time'), if_not_exists => TRUE);

    -- Retention policy: 2 years
    SELECT add_retention_policy('candles', INTERVAL '2 years', if_not_exists => TRUE);

    -- Continuous aggregate: 1-day OHLCV summary from 1h candles
    CREATE MATERIALIZED VIEW IF NOT EXISTS candles_1d_summary
    WITH (timescaledb.continuous) AS
    SELECT time_bucket('1 day', time) AS bucket,
           symbol,
           first(open, time) AS open,
           max(high) AS high,
           min(low) AS low,
           last(close, time) AS close,
           sum(volume) AS volume
    FROM candles
    WHERE timeframe = '1h'
    GROUP BY bucket, symbol;

    -- Refresh policy for continuous aggregate
    SELECT add_continuous_aggregate_policy('candles_1d_summary',
        start_offset => INTERVAL '3 days',
        end_offset => INTERVAL '1 hour',
        schedule_interval => INTERVAL '1 hour',
        if_not_exists => TRUE);
    """)


def downgrade() -> None:
    op.execute("""
    SELECT remove_continuous_aggregate_policy('candles_1d_summary', if_exists => TRUE);
    DROP MATERIALIZED VIEW IF EXISTS candles_1d_summary;
    SELECT remove_retention_policy('candles', if_exists => TRUE);
    """)
