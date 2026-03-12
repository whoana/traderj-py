"""Validate database schema after migration.

Usage: python scripts/validate_schema.py
"""
from __future__ import annotations

import asyncio
import os
import sys


EXPECTED_TABLES = [
    "candles",
    "signals",
    "orders",
    "positions",
    "risk_state",
    "bot_state",
    "paper_balances",
    "daily_pnl",
    "macro_snapshots",
    "bot_commands",
    "backtest_results",
]

EXPECTED_INDEXES = [
    "idx_candles_symbol_tf_time",
    "idx_signals_strategy_ts",
    "idx_signals_symbol_ts",
    "idx_orders_strategy_ts",
    "idx_orders_status",
    "idx_positions_open",
    "idx_positions_strategy_ts",
    "idx_macro_ts",
    "idx_bot_commands_pending",
    "idx_bt_strategy",
    "idx_bt_created",
]


async def validate() -> bool:
    import asyncpg

    dsn = "postgresql://{}:{}@{}:{}/{}".format(
        os.getenv("DB_USER", "traderj"),
        os.getenv("DB_PASSWORD", "changeme"),
        os.getenv("DB_HOST", "localhost"),
        os.getenv("DB_PORT", "5432"),
        os.getenv("DB_NAME", "traderj"),
    )

    conn = await asyncpg.connect(dsn)
    ok = True

    # Check tables
    rows = await conn.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
    )
    existing_tables = {r["tablename"] for r in rows}

    for table in EXPECTED_TABLES:
        if table in existing_tables:
            print(f"  [OK] Table: {table}")
        else:
            print(f"  [MISSING] Table: {table}")
            ok = False

    # Check indexes
    rows = await conn.fetch(
        "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"
    )
    existing_indexes = {r["indexname"] for r in rows}

    for index in EXPECTED_INDEXES:
        if index in existing_indexes:
            print(f"  [OK] Index: {index}")
        else:
            print(f"  [MISSING] Index: {index}")
            ok = False

    await conn.close()
    return ok


def main() -> None:
    print("Validating traderj schema...")
    result = asyncio.run(validate())
    if result:
        print("\nAll validations passed!")
    else:
        print("\nValidation FAILED — some tables or indexes are missing.")
        sys.exit(1)


if __name__ == "__main__":
    main()
