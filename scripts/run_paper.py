"""Run paper trading for a specific strategy locally (no Docker needed).

Uses the configured DataStore (SQLite by default) and Upbit Public API for market data.

Usage:
    python -m scripts.run_paper                    # default: STR-001, 연속 실행
    python -m scripts.run_paper STR-005            # specific strategy, 연속 실행
    python -m scripts.run_paper STR-001 STR-002    # multiple strategies
    python -m scripts.run_paper --ticks 10 STR-005 # 10회 실행 후 종료
    python -m scripts.run_paper --ticks 3 STR-001  # 3회 실행 후 종료

Ctrl+C로 안전하게 종료합니다.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from datetime import UTC, datetime

from engine.bootstrap import bootstrap
from engine.config.settings import AppSettings
from engine.data import create_data_store
from engine.loop.trading_loop import TradingLoop

from shared.logging_config import setup_logging

setup_logging(level="INFO")
logger = logging.getLogger("paper")


async def run_paper(strategy_ids: list[str], ticks: int = 0):
    """Run paper trading for given strategies.

    Args:
        strategy_ids: List of strategy IDs to run.
        ticks: Number of trading ticks to execute. 0 = 무한 반복 (Ctrl+C로 종료).
    """
    continuous = ticks == 0
    mode_label = "연속 실행 (Ctrl+C 종료)" if continuous else f"{ticks}회"

    print("=" * 70)
    print(f"  Paper Trading — {', '.join(strategy_ids)}")
    print(f"  Ticks: {mode_label} | Mode: paper | Symbol: BTC/KRW")
    print("=" * 70)
    print()

    # Setup
    settings = AppSettings()
    settings.trading.mode = "paper"
    if len(strategy_ids) > 1:
        settings.trading.strategy_ids = strategy_ids
    else:
        settings.trading.strategy_id = strategy_ids[0]
        settings.trading.strategy_ids = []

    store = create_data_store(settings.db)
    await store.connect()

    try:
        app = await bootstrap(settings=settings, data_store=store)
        trading_loops: dict[str, TradingLoop] = app.get("trading_loops")

        # Connect exchange
        exchange = app.get("exchange")
        await exchange.connect()

        # Start notifier
        notifier = app.get("notifier")
        await notifier.start()

        # Start event bus
        await app.event_bus.start()

        # Start all loops
        for sid, loop in trading_loops.items():
            await loop.start()
            logger.info("Started %s", sid)

        # Engine start notification
        await notifier._send(
            f"\U0001f680 <b>Engine Started</b>\n"
            f"Mode: paper\n"
            f"Strategies: {', '.join(strategy_ids)}\n"
            f"Ticks: {'continuous' if continuous else ticks}"
        )

        print()

        # Graceful shutdown via Ctrl+C
        stop_event = asyncio.Event()
        loop_ref = asyncio.get_running_loop()

        def _signal_handler():
            print("\n  Ctrl+C 감지 — 안전하게 종료 중...")
            stop_event.set()

        loop_ref.add_signal_handler(signal.SIGINT, _signal_handler)

        # Run ticks
        tick_num = 0
        max_ticks = ticks if not continuous else float("inf")

        while tick_num < max_ticks and not stop_event.is_set():
            tick_num += 1
            label = f"Tick {tick_num}" if continuous else f"Tick {tick_num}/{ticks}"
            print(f"── {label} ─{'─' * 50}")

            for sid, loop in trading_loops.items():
                try:
                    sig = await loop.tick()
                    if sig:
                        balance = await store.get_paper_balance(sid)
                        krw = float(balance.krw) if balance else 0
                        btc = float(balance.btc) if balance else 0

                        print(
                            f"  [{sid}] {sig.direction.value:>4} "
                            f"score={sig.score:+.4f} | "
                            f"KRW={krw:>13,.0f} BTC={btc:.8f}"
                        )
                    else:
                        print(f"  [{sid}] (skipped)")
                except Exception as e:
                    logger.error("[%s] tick error: %s", sid, e)

            if (continuous or tick_num < ticks) and not stop_event.is_set():
                wait_sec = 60 if continuous else 10
                print(f"  다음 tick까지 {wait_sec}s 대기...")
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=wait_sec)
                except asyncio.TimeoutError:
                    pass  # Normal: timeout means keep going

        # Final summary
        print()
        print("=" * 70)
        print("  Final Paper Balances")
        print("-" * 70)

        for sid, loop in trading_loops.items():
            balance = await store.get_paper_balance(sid)
            if balance:
                krw = float(balance.krw)
                btc = float(balance.btc)

                # Get current price for total value
                try:
                    ticker = await exchange.fetch_ticker("BTC/KRW")
                    price = float(ticker["last"])
                    total = krw + btc * price
                    initial = float(balance.initial_krw)
                    pnl = total - initial
                    pnl_pct = pnl / initial * 100

                    print(
                        f"  [{sid}] KRW={krw:>13,.0f} | BTC={btc:.8f} | "
                        f"Total={total:>13,.0f} | PnL={pnl:+,.0f} ({pnl_pct:+.2f}%)"
                    )
                except Exception:
                    print(f"  [{sid}] KRW={krw:>13,.0f} | BTC={btc:.8f}")

        # Trade history
        print()
        print("  Trade History")
        print("-" * 70)
        for sid in strategy_ids:
            orders = await store.get_orders(strategy_id=sid)
            if orders:
                for o in orders[-5:]:  # Last 5 orders
                    print(
                        f"  [{sid}] {o.side:>4} {float(o.amount):.8f} BTC "
                        f"@ {float(o.price):,.0f} | {o.status}"
                    )
            else:
                print(f"  [{sid}] No trades")

        print("=" * 70)

        # Engine stop notification
        await notifier._send(
            f"\U0001f6d1 <b>Engine Stopped</b>\n"
            f"Strategies: {', '.join(strategy_ids)}\n"
            f"Ticks completed: {tick_num}"
        )

        # Cleanup
        for loop in trading_loops.values():
            await loop.stop()
        await app.event_bus.stop()
        await notifier.stop()
        await exchange.disconnect()

    finally:
        await store.disconnect()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Paper Trading Runner")
    parser.add_argument("strategies", nargs="*", default=["STR-001"],
                        help="Strategy IDs to run (default: STR-001)")
    parser.add_argument("--ticks", type=int, default=0,
                        help="Number of ticks to run (default: 0 = continuous)")
    args = parser.parse_args()

    strategy_ids = args.strategies
    ticks = args.ticks

    # Validate strategy IDs
    from engine.strategy.presets import STRATEGY_PRESETS
    for sid in strategy_ids:
        if sid not in STRATEGY_PRESETS:
            print(f"[ERROR] Unknown strategy: {sid}")
            print(f"Available: {', '.join(STRATEGY_PRESETS.keys())}")
            sys.exit(1)

    print(f"Strategies: {strategy_ids}")
    asyncio.run(run_paper(strategy_ids, ticks=ticks))


if __name__ == "__main__":
    main()
