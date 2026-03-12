"""Before/After comparison: current presets vs tuned presets.

Runs 7 strategies x 2 (before/after) = 14 backtests on 90-day data
and prints a side-by-side comparison.

Usage:
    python -m scripts.run_backtest_compare
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone

import ccxt.async_support as ccxt
import pandas as pd

from engine.strategy.backtest.engine import BacktestConfig, BacktestEngine
from engine.strategy.presets import STRATEGY_PRESETS, StrategyPreset
from engine.strategy.signal import SignalGenerator
from shared.enums import EntryMode, ScoringMode
from engine.strategy.scoring import ScoreWeights

SYMBOL = "BTC/KRW"
TIMEFRAMES = ["15m", "1h", "4h", "1d"]
LOOKBACK_DAYS = 90
INITIAL_BALANCE = 10_000_000


# "Before" presets: original values hardcoded for stable comparison
BEFORE_OVERRIDES: dict[str, dict] = {
    "default":  {"buy_threshold": 0.15, "sell_threshold": -0.15, "macro_weight": 0.2},
    "STR-001":  {"buy_threshold": 0.20, "sell_threshold": -0.20, "macro_weight": 0.25},
    "STR-002":  {"buy_threshold": 0.12, "sell_threshold": -0.12, "macro_weight": 0.15},
    "STR-003":  {"buy_threshold": 0.18, "sell_threshold": -0.18, "macro_weight": 0.2},
    "STR-004":  {"buy_threshold": 0.15, "sell_threshold": -0.15, "macro_weight": 0.2},
    "STR-005":  {"buy_threshold": 0.25, "sell_threshold": -0.25, "macro_weight": 0.30},
    "STR-006":  {"buy_threshold": 0.10, "sell_threshold": -0.10, "macro_weight": 0.10},
}


async def fetch_ohlcv_paginated(
    exchange: ccxt.upbit,
    symbol: str,
    timeframe: str,
    since_ms: int,
    until_ms: int,
    limit_per_req: int = 200,
) -> list[list]:
    all_candles: list[list] = []
    cursor = since_ms
    while cursor < until_ms:
        try:
            candles = await exchange.fetch_ohlcv(
                symbol, timeframe, since=cursor, limit=limit_per_req
            )
        except Exception as e:
            print(f"  [WARN] fetch error ({timeframe}): {e}")
            break
        if not candles:
            break
        all_candles.extend(candles)
        last_ts = candles[-1][0]
        if last_ts <= cursor:
            break
        cursor = last_ts + 1
        await asyncio.sleep(0.15)

    seen = set()
    unique = []
    for c in all_candles:
        if c[0] not in seen and c[0] <= until_ms:
            seen.add(c[0])
            unique.append(c)
    unique.sort(key=lambda c: c[0])
    return unique


def candles_to_df(raw: list[list]) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame()
    data = {
        "open": [c[1] for c in raw],
        "high": [c[2] for c in raw],
        "low": [c[3] for c in raw],
        "close": [c[4] for c in raw],
        "volume": [c[5] for c in raw],
    }
    index = pd.DatetimeIndex(
        [datetime.fromtimestamp(c[0] / 1000, tz=timezone.utc) for c in raw]
    )
    return pd.DataFrame(data, index=index)


def determine_primary_tf(preset: StrategyPreset) -> str:
    tf_order = ["15m", "1h", "4h", "1d"]
    for tf in tf_order:
        if tf in preset.tf_weights:
            return tf
    return "1h"


def make_signal_generator(preset: StrategyPreset, overrides: dict | None = None) -> SignalGenerator:
    buy_th = preset.buy_threshold
    sell_th = preset.sell_threshold
    macro_w = preset.macro_weight

    if overrides:
        buy_th = overrides.get("buy_threshold", buy_th)
        sell_th = overrides.get("sell_threshold", sell_th)
        macro_w = overrides.get("macro_weight", macro_w)

    return SignalGenerator(
        strategy_id=preset.strategy_id,
        scoring_mode=preset.scoring_mode,
        entry_mode=preset.entry_mode,
        score_weights=preset.score_weights,
        tf_weights=preset.tf_weights,
        buy_threshold=buy_th,
        sell_threshold=sell_th,
        majority_min=preset.majority_min,
        use_daily_gate=preset.use_daily_gate,
        macro_weight=macro_w,
    )


def run_single(
    preset: StrategyPreset,
    ohlcv_data: dict[str, pd.DataFrame],
    overrides: dict | None = None,
) -> dict | None:
    needed_tfs = set(preset.tf_weights.keys())
    if preset.use_daily_gate:
        needed_tfs.add("1d")

    strategy_data = {}
    for tf in needed_tfs:
        if tf in ohlcv_data and not ohlcv_data[tf].empty:
            strategy_data[tf] = ohlcv_data[tf]
        else:
            return None

    primary_tf = determine_primary_tf(preset)
    signal_gen = make_signal_generator(preset, overrides)

    tf_bars_per_day = {"15m": 96, "1h": 24, "4h": 6, "1d": 1}
    max_bars = tf_bars_per_day.get(primary_tf, 24) * LOOKBACK_DAYS

    config = BacktestConfig(
        initial_balance_krw=INITIAL_BALANCE,
        fee_rate=0.0005,
        slippage_bps=5.0,
        max_bars=max_bars,
    )
    engine = BacktestEngine(signal_generator=signal_gen, config=config)

    try:
        result = engine.run(strategy_data, primary_tf=primary_tf)
        return result.metrics
    except Exception as e:
        print(f"  [ERROR] {preset.strategy_id}: {e}")
        return None


async def main():
    print("=" * 100)
    print(f"  BTC/KRW Before/After 비교 — {LOOKBACK_DAYS}일")
    print(f"  초기 자본: {INITIAL_BALANCE:,.0f} KRW")
    print("=" * 100)

    # Fetch data
    exchange = ccxt.upbit({"enableRateLimit": False})
    try:
        await exchange.load_markets()
    except Exception as e:
        print(f"[ERROR] Upbit 연결 실패: {e}")
        await exchange.close()
        return

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=LOOKBACK_DAYS + 60)
    since_ms = int(since.timestamp() * 1000)
    until_ms = int(now.timestamp() * 1000)

    print("\nUpbit에서 캔들 데이터 조회 중...")
    ohlcv_data: dict[str, pd.DataFrame] = {}
    for tf in TIMEFRAMES:
        print(f"  {tf}...", end=" ", flush=True)
        raw = await fetch_ohlcv_paginated(exchange, SYMBOL, tf, since_ms, until_ms)
        df = candles_to_df(raw)
        ohlcv_data[tf] = df
        print(f"{len(df)} candles")

    await exchange.close()
    print()

    # Run Before/After
    comparisons = []

    for strategy_id, preset in STRATEGY_PRESETS.items():
        before_overrides = BEFORE_OVERRIDES.get(strategy_id)

        # Before: original params
        t0 = time.time()
        before_metrics = run_single(preset, ohlcv_data, overrides=before_overrides)
        before_time = time.time() - t0

        # After: current preset params (tuned)
        t0 = time.time()
        after_metrics = run_single(preset, ohlcv_data)
        after_time = time.time() - t0

        comparisons.append({
            "strategy_id": strategy_id,
            "name": preset.name,
            "before": before_metrics,
            "after": after_metrics,
            "before_time": before_time,
            "after_time": after_time,
        })

        b_ret = before_metrics.get("total_return_pct", 0) if before_metrics else 0
        a_ret = after_metrics.get("total_return_pct", 0) if after_metrics else 0
        print(f"  {strategy_id}: Before={b_ret:+.2f}% After={a_ret:+.2f}% "
              f"(delta={a_ret - b_ret:+.2f}%)")

    # Print comparison table
    print("\n" + "=" * 130)
    print(f"{'전략':>10} | {'Before':>50} | {'After':>50} | {'Delta':>8}")
    print(f"{'':>10} | {'Ret%':>7} {'Trades':>6} {'WR%':>5} {'Sharpe':>7} {'MDD%':>6} {'PF':>6} | "
          f"{'Ret%':>7} {'Trades':>6} {'WR%':>5} {'Sharpe':>7} {'MDD%':>6} {'PF':>6} | {'Ret%':>8}")
    print("-" * 130)

    for c in comparisons:
        sid = c["strategy_id"]
        b = c["before"] or {}
        a = c["after"] or {}

        b_ret = b.get("total_return_pct", 0)
        a_ret = a.get("total_return_pct", 0)
        delta = a_ret - b_ret

        def fmt_pf(v):
            return "inf" if v == float("inf") else f"{v:.2f}"

        print(f"{sid:>10} | "
              f"{b_ret:>+6.2f} {b.get('total_trades', 0):>6} "
              f"{b.get('win_rate_pct', 0):>5.1f} {b.get('sharpe_ratio', 0):>7.2f} "
              f"{b.get('max_drawdown_pct', 0):>6.2f} {fmt_pf(b.get('profit_factor', 0)):>6} | "
              f"{a_ret:>+6.2f} {a.get('total_trades', 0):>6} "
              f"{a.get('win_rate_pct', 0):>5.1f} {a.get('sharpe_ratio', 0):>7.2f} "
              f"{a.get('max_drawdown_pct', 0):>6.2f} {fmt_pf(a.get('profit_factor', 0)):>6} | "
              f"{delta:>+7.2f}")

    print("=" * 130)

    # Summary
    improved = sum(
        1 for c in comparisons
        if c["before"] and c["after"]
        and c["after"].get("total_return_pct", 0) > c["before"].get("total_return_pct", 0)
    )
    total = len(comparisons)
    print(f"\n개선된 전략: {improved}/{total}")


if __name__ == "__main__":
    asyncio.run(main())
