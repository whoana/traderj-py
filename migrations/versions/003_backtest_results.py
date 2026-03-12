"""Backtest results table (P1 preview).

Revision ID: 003
Revises: 002
Create Date: 2026-03-03
"""
from __future__ import annotations

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE backtest_results (
        id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
        strategy_id         TEXT            NOT NULL,
        params_hash         TEXT            NOT NULL,
        config_json         JSONB           NOT NULL,
        metrics_json        JSONB           NOT NULL,
        equity_curve_json   JSONB,
        trades_json         JSONB,
        walk_forward_json   JSONB,
        created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
    );

    CREATE INDEX idx_bt_strategy ON backtest_results(strategy_id);
    CREATE INDEX idx_bt_created ON backtest_results(created_at DESC);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS backtest_results CASCADE;")
