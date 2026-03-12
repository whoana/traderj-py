"""Robustness validation: 180-day backtest + parameter sensitivity analysis.

Tests:
  1. 180-day backtest for all 7 strategies (longer-term validation)
  2. Parameter sensitivity: vary buy_threshold +-10%, +-20% and check stability

Usage:
    PYTHONUNBUFFERED=1 python -m scripts.run_backtest_robustness
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

import ccxt.async_support as ccxt
import pandas as pd

from engine.strategy.backtest.engine import BacktestConfig, BacktestEngine
from engine.strategy.presets import STRATEGY_PRESETS, StrategyPreset
from engine.strategy.signal import SignalGenerator

logging.basicConfig(level=logging.ERROR)

SYMBOL = "BTC/KRW"
TIMEFRAMES = ["1h", "4h", "1d"]
LOOKBACK_DAYS = 180
INITIAL_BALANCE = 10_000_000
SENSITIVITY_DELTAS = [-0.20, -0.10, 0.0, +0.10, +0.20]


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
    tf_order = ["1h", "4h", "1d"]
    for tf in tf_order:
        if tf in preset.tf_weights:
            return tf
    return "1h"


def run_backtest(
    preset: StrategyPreset,
    ohlcv_data: dict[str, pd.DataFrame],
    buy_threshold: float | None = None,
    sell_threshold: float | None = None,
    lookback_days: int = LOOKBACK_DAYS,
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

    buy_th = buy_threshold if buy_threshold is not None else preset.buy_threshold
    sell_th = sell_threshold if sell_threshold is not None else preset.sell_threshold

    signal_gen = SignalGenerator(
        strategy_id=preset.strategy_id,
        scoring_mode=preset.scoring_mode,
        entry_mode=preset.entry_mode,
        score_weights=preset.score_weights,
        tf_weights=preset.tf_weights,
        buy_threshold=buy_th,
        sell_threshold=sell_th,
        majority_min=preset.majority_min,
        use_daily_gate=preset.use_daily_gate,
        macro_weight=preset.macro_weight,
    )

    primary_tf = determine_primary_tf(preset)
    tf_bars_per_day = {"15m": 96, "1h": 24, "4h": 6, "1d": 1}
    max_bars = tf_bars_per_day.get(primary_tf, 24) * lookback_days

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
    print(f"  BTC/KRW Robustness 검증 — {LOOKBACK_DAYS}일")
    print(f"  초기 자본: {INITIAL_BALANCE:,.0f} KRW")
    print(f"  파라미터 변동: {SENSITIVITY_DELTAS}")
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

    # ── Part 1: 180-day baseline backtest ──────────────────────

    print(f"\n{'='*100}")
    print(f"  Part 1: {LOOKBACK_DAYS}일 기본 백테스트")
    print(f"{'='*100}\n")

    baseline_results: dict[str, dict] = {}

    for strategy_id, preset in STRATEGY_PRESETS.items():
        t0 = time.time()
        metrics = run_backtest(preset, ohlcv_data)
        elapsed = time.time() - t0

        if metrics:
            baseline_results[strategy_id] = metrics
            ret = metrics.get("total_return_pct", 0)
            trades = metrics.get("total_trades", 0)
            wr = metrics.get("win_rate_pct", 0)
            mdd = metrics.get("max_drawdown_pct", 0)
            pf = metrics.get("profit_factor", 0)
            pf_str = "inf" if pf == float("inf") else f"{pf:.2f}"
            print(f"  {strategy_id:>10}: Ret={ret:+6.2f}%  Trades={trades:>3}  "
                  f"WR={wr:>5.1f}%  MDD={mdd:>5.2f}%  PF={pf_str:>6}  ({elapsed:.1f}s)")
        else:
            print(f"  {strategy_id:>10}: [SKIP]")

    # ── Part 2: Parameter sensitivity ─────────────────────────

    print(f"\n{'='*100}")
    print("  Part 2: 파라미터 민감도 분석 (buy_threshold +-10%, +-20%)")
    print(f"{'='*100}\n")

    # Header
    delta_labels = [f"{d:+.0%}" for d in SENSITIVITY_DELTAS]
    header = f"{'전략':>10} | " + " | ".join(f"{dl:>10}" for dl in delta_labels) + " | Stable?"
    print(header)
    print("-" * len(header))

    sensitivity_summary: dict[str, dict] = {}

    for strategy_id, preset in STRATEGY_PRESETS.items():
        returns: list[float | None] = []

        for delta in SENSITIVITY_DELTAS:
            varied_buy = round(preset.buy_threshold * (1 + delta), 4)
            varied_sell = round(preset.sell_threshold * (1 + delta), 4)

            metrics = run_backtest(
                preset, ohlcv_data,
                buy_threshold=varied_buy,
                sell_threshold=varied_sell,
            )

            if metrics:
                ret = metrics.get("total_return_pct", 0)
                returns.append(ret)
            else:
                returns.append(None)

        # Format output
        cells = []
        for r in returns:
            if r is None:
                cells.append(f"{'N/A':>10}")
            else:
                cells.append(f"{r:>+9.2f}%")

        # Stability check: all returns within +-1% of baseline
        valid_returns = [r for r in returns if r is not None]
        baseline_ret = returns[2] if returns[2] is not None else 0
        stable = all(
            abs(r - baseline_ret) < 1.0
            for r in valid_returns
        ) if len(valid_returns) == len(SENSITIVITY_DELTAS) else False

        stability_str = "YES" if stable else "NO"
        sensitivity_summary[strategy_id] = {
            "returns": returns,
            "stable": stable,
            "baseline_ret": baseline_ret,
            "range": max(valid_returns) - min(valid_returns) if valid_returns else 0,
        }

        print(f"{strategy_id:>10} | " + " | ".join(cells) + f" | {stability_str:>6}")

    # ── Summary ──────────────────────────────────────────────

    print(f"\n{'='*100}")
    print("  종합 요약")
    print(f"{'='*100}\n")

    positive_180d = sum(
        1 for m in baseline_results.values()
        if m.get("total_return_pct", 0) > 0
    )
    stable_count = sum(1 for s in sensitivity_summary.values() if s["stable"])

    print(f"  {LOOKBACK_DAYS}일 양수 수익률: {positive_180d}/{len(baseline_results)} 전략")
    print(f"  파라미터 안정성: {stable_count}/{len(sensitivity_summary)} 전략")
    print()

    for sid, summary in sensitivity_summary.items():
        baseline = baseline_results.get(sid, {})
        ret = baseline.get("total_return_pct", 0)
        rng = summary["range"]
        stable = "Stable" if summary["stable"] else "Unstable"
        print(f"  {sid:>10}: {LOOKBACK_DAYS}d Ret={ret:+6.2f}%  "
              f"Sensitivity Range={rng:.2f}pp  ({stable})")


if __name__ == "__main__":
    asyncio.run(main())
