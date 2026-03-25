"""AI Regime-aware backtest over a specified historical period.

Detects market regime per week, auto-selects matching strategy preset,
runs backtest per segment, and compares with individual fixed strategies.

Usage:
    .venv/bin/python -m scripts.run_backtest_ai_period
    .venv/bin/python -m scripts.run_backtest_ai_period --start 2024-11-01 --end 2024-11-30
"""

from __future__ import annotations

import argparse
import asyncio
import time
from datetime import datetime, timedelta, timezone

import ccxt.async_support as ccxt
import pandas as pd

from engine.strategy.backtest.engine import BacktestConfig, BacktestEngine, BacktestTrade
from engine.strategy.backtest.metrics import compute_metrics
from engine.strategy.indicators import compute_indicators
from engine.strategy.presets import STRATEGY_PRESETS, StrategyPreset
from engine.strategy.regime import REGIME_PRESET_MAP, detect_regime
from engine.strategy.signal import SignalGenerator

SYMBOL = "BTC/KRW"
TIMEFRAMES = ["1h", "4h", "1d"]
INITIAL_BALANCE = 50_000_000
REGIME_EVAL_TF = "4h"
WEEK_DAYS = 7


async def fetch_ohlcv_paginated(
    exchange: ccxt.upbit, symbol: str, tf: str, since_ms: int, until_ms: int,
) -> list[list]:
    all_candles: list[list] = []
    cursor = since_ms
    while cursor < until_ms:
        try:
            candles = await exchange.fetch_ohlcv(symbol, tf, since=cursor, limit=200)
        except Exception as e:
            print(f"  [WARN] fetch error ({tf}): {e}")
            break
        if not candles:
            break
        all_candles.extend(candles)
        last_ts = candles[-1][0]
        if last_ts <= cursor:
            break
        cursor = last_ts + 1
        await asyncio.sleep(0.15)

    seen: set[int] = set()
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


def make_signal_generator(preset: StrategyPreset) -> SignalGenerator:
    return SignalGenerator(
        strategy_id=preset.strategy_id,
        scoring_mode=preset.scoring_mode,
        entry_mode=preset.entry_mode,
        score_weights=preset.score_weights,
        tf_weights=preset.tf_weights,
        buy_threshold=preset.buy_threshold,
        sell_threshold=preset.sell_threshold,
        majority_min=preset.majority_min,
        use_daily_gate=preset.use_daily_gate,
        macro_weight=preset.macro_weight,
    )


def determine_primary_tf(preset: StrategyPreset) -> str:
    for tf in ["1h", "4h", "1d"]:
        if tf in preset.tf_weights:
            return tf
    return "1h"


def detect_current_regime(ohlcv_4h: pd.DataFrame) -> tuple[str, str]:
    try:
        df_ind = compute_indicators(ohlcv_4h)
        result = detect_regime(df_ind)
        preset_id = REGIME_PRESET_MAP.get(result.regime, "STR-001")
        return result.regime.value, preset_id
    except Exception as e:
        print(f"  [WARN] regime detection failed: {e}")
        return "unknown", "STR-001"


def _fmt_pf(v: float) -> str:
    return "inf" if v == float("inf") else f"{v:.2f}"


async def main() -> None:
    parser = argparse.ArgumentParser(description="AI Regime-Aware Period Backtest")
    parser.add_argument("--start", default="2024-11-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default="2024-11-30", help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    start_date = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_date = datetime.strptime(args.end, "%Y-%m-%d").replace(
        hour=23, minute=59, second=59, tzinfo=timezone.utc,
    )
    period_days = (end_date - start_date).days + 1

    print("=" * 100)
    print(f"  AI Regime-Aware Backtest: {args.start} ~ {args.end} ({period_days} days)")
    print(f"  Initial Balance: {INITIAL_BALANCE:,.0f} KRW")
    print("=" * 100)

    # ── 1. Fetch data (60 days extra for indicator warmup) ──

    exchange = ccxt.upbit({"enableRateLimit": False})
    try:
        await exchange.load_markets()
    except Exception as e:
        print(f"[ERROR] Upbit connection failed: {e}")
        await exchange.close()
        return

    warmup_start = start_date - timedelta(days=60)
    since_ms = int(warmup_start.timestamp() * 1000)
    until_ms = int(end_date.timestamp() * 1000)

    print("\nFetching candle data from Upbit...")
    ohlcv_all: dict[str, pd.DataFrame] = {}
    for tf in TIMEFRAMES:
        print(f"  {tf}...", end=" ", flush=True)
        raw = await fetch_ohlcv_paginated(exchange, SYMBOL, tf, since_ms, until_ms)
        df = candles_to_df(raw)
        ohlcv_all[tf] = df
        date_range = ""
        if len(df) > 0:
            date_range = f" ({df.index[0].strftime('%m/%d')} ~ {df.index[-1].strftime('%m/%d')})"
        print(f"{len(df)} candles{date_range}")

    await exchange.close()

    # BTC price info for the period
    df_1d = ohlcv_all.get("1d", pd.DataFrame())
    period_1d = df_1d[(df_1d.index >= start_date) & (df_1d.index <= end_date)]
    if len(period_1d) > 0:
        btc_start = float(period_1d.iloc[0]["open"])
        btc_end = float(period_1d.iloc[-1]["close"])
        btc_change = ((btc_end - btc_start) / btc_start) * 100
        print(f"\n  BTC/KRW: {btc_start:,.0f} -> {btc_end:,.0f} ({btc_change:+.1f}%)")

    # ── 2. Weekly regime detection + AI backtest ──

    weeks: list[tuple[datetime, datetime]] = []
    ws = start_date
    while ws < end_date:
        we = min(ws + timedelta(days=WEEK_DAYS) - timedelta(seconds=1), end_date)
        weeks.append((ws, we))
        ws = we + timedelta(seconds=1)

    print(f"\n  Period: {len(weeks)} weekly segments")
    print()
    print("-" * 100)
    print("  [AI Mode] Weekly regime detection -> strategy auto-select")
    print("-" * 100)

    ai_all_trades: list[BacktestTrade] = []
    ai_all_equity: list[dict] = []
    ai_balance = float(INITIAL_BALANCE)
    regime_log: list[dict] = []
    tf_bars_per_day = {"1h": 24, "4h": 6, "1d": 1}

    t0_ai = time.time()
    for i, (ws, we) in enumerate(weeks):
        # Regime from data up to start of week
        regime_data = ohlcv_all.get(REGIME_EVAL_TF, pd.DataFrame())
        regime_slice = regime_data[regime_data.index <= ws]
        if len(regime_slice) < 30:
            regime_slice = regime_data[regime_data.index <= we]

        regime_name, preset_id = detect_current_regime(regime_slice)
        preset = STRATEGY_PRESETS.get(preset_id, STRATEGY_PRESETS["STR-001"])

        week_days = (we - ws).days + 1

        regime_log.append({
            "week": i + 1,
            "start": ws.strftime("%m/%d"),
            "end": we.strftime("%m/%d"),
            "regime": regime_name,
            "preset": preset_id,
            "name": preset.name,
        })

        # Build data including warmup
        needed_tfs = set(preset.tf_weights.keys())
        if preset.use_daily_gate:
            needed_tfs.add("1d")
        strategy_data = {}
        for tf in needed_tfs:
            if tf in ohlcv_all:
                d = ohlcv_all[tf]
                strategy_data[tf] = d[d.index <= we].copy()

        if not strategy_data:
            print(f"  Week {i+1} ({ws.strftime('%m/%d')}~{we.strftime('%m/%d')}): [SKIP] no data")
            continue

        primary_tf = determine_primary_tf(preset)
        signal_gen = make_signal_generator(preset)
        max_bars = tf_bars_per_day.get(primary_tf, 24) * week_days

        config = BacktestConfig(
            initial_balance_krw=ai_balance,
            fee_rate=0.0005,
            slippage_bps=5.0,
            max_bars=max_bars,
        )
        engine = BacktestEngine(signal_generator=signal_gen, config=config)

        try:
            result = engine.run(strategy_data, primary_tf=primary_tf)
            ai_all_trades.extend(result.trades)
            ai_all_equity.extend(result.equity_curve)
            if result.equity_curve:
                ai_balance = result.equity_curve[-1]["equity"]
            w_ret = ((ai_balance - config.initial_balance_krw) / config.initial_balance_krw) * 100

            print(f"  W{i+1} {ws.strftime('%m/%d')}~{we.strftime('%m/%d')} "
                  f"| {regime_name:<24} | {preset_id} {preset.name:<26} "
                  f"| trades={len(result.trades):>2} ret={w_ret:>+6.2f}% bal={ai_balance:>13,.0f}")
        except Exception as e:
            print(f"  W{i+1} {ws.strftime('%m/%d')}~{we.strftime('%m/%d')} | [ERROR] {e}")

    elapsed_ai = time.time() - t0_ai

    # ── 3. All individual preset backtests ──

    print()
    print("-" * 100)
    print("  [Individual Strategies] Each preset over entire period")
    print("-" * 100)

    preset_results: list[tuple[str, str, dict]] = []

    for sid, p in STRATEGY_PRESETS.items():
        if sid == "default":
            continue
        ntfs = set(p.tf_weights.keys())
        if p.use_daily_gate:
            ntfs.add("1d")
        pdata = {tf: ohlcv_all[tf] for tf in ntfs if tf in ohlcv_all}
        if not pdata:
            continue

        ptf = determine_primary_tf(p)
        psig = make_signal_generator(p)
        pmb = tf_bars_per_day.get(ptf, 24) * period_days
        pcfg = BacktestConfig(initial_balance_krw=INITIAL_BALANCE, fee_rate=0.0005, slippage_bps=5.0, max_bars=pmb)
        peng = BacktestEngine(signal_generator=psig, config=pcfg)

        try:
            pr = peng.run(pdata, primary_tf=ptf)
            preset_results.append((sid, p.name, pr.metrics))
        except Exception as e:
            print(f"  {sid}: [ERROR] {e}")

    # Sort by return
    preset_results.sort(key=lambda x: x[2].get("total_return_pct", -999), reverse=True)

    print()
    print(f"  {'Strategy':>8} {'Name':<28} {'Return%':>8} {'Trades':>6} {'WR%':>6} "
          f"{'PF':>7} {'Sharpe':>7} {'MDD%':>7} {'Final':>14}")
    print(f"  {'-'*8} {'-'*28} {'-'*8} {'-'*6} {'-'*6} {'-'*7} {'-'*7} {'-'*7} {'-'*14}")

    for sid, name, m in preset_results:
        pf = _fmt_pf(m.get("profit_factor", 0))
        print(f"  {sid:>8} {name:<28} {m.get('total_return_pct', 0):>+7.2f}% "
              f"{m.get('total_trades', 0):>5} {m.get('win_rate_pct', 0):>5.1f}% "
              f"{pf:>7} {m.get('sharpe_ratio', 0):>7.2f} {m.get('max_drawdown_pct', 0):>6.2f}% "
              f"{m.get('final_equity', 0):>13,.0f}")

    # ── 4. Compute AI aggregate metrics ──

    ai_metrics = compute_metrics(
        trades=ai_all_trades,
        equity_curve=ai_all_equity,
        initial_balance=INITIAL_BALANCE,
    )

    # ── 5. Final Report ──

    print()
    print("=" * 100)
    print(f"  REPORT: AI Regime-Aware Backtest  |  {args.start} ~ {args.end}")
    print("=" * 100)

    # Regime log
    print()
    print("  [ Weekly Regime Decisions ]")
    print(f"  {'Week':>4} | {'Period':>11} | {'Regime':<24} | {'Selected Strategy':<36}")
    print(f"  {'-'*4}-+-{'-'*11}-+-{'-'*24}-+-{'-'*36}")
    for r in regime_log:
        print(f"  W{r['week']:>2}  | {r['start']}~{r['end']} | {r['regime']:<24} | {r['preset']} {r['name']}")

    # Regime distribution
    from collections import Counter
    regime_counts = Counter(r["regime"] for r in regime_log)
    print()
    print("  [ Regime Distribution ]")
    for rname, cnt in regime_counts.most_common():
        pct = cnt / len(regime_log) * 100
        bar = "#" * int(pct / 2)
        print(f"  {rname:<24} {cnt}x ({pct:.0f}%) {bar}")

    # Strategy usage
    strat_counts = Counter(r["preset"] for r in regime_log)
    print()
    print("  [ Strategy Usage ]")
    for sname, cnt in strat_counts.most_common():
        pct = cnt / len(regime_log) * 100
        info = STRATEGY_PRESETS.get(sname)
        label = f"{sname} {info.name}" if info else sname
        print(f"  {label:<36} {cnt}x ({pct:.0f}%)")

    # Performance comparison
    best_preset = preset_results[0] if preset_results else None

    print()
    print("  [ Performance Summary ]")
    print(f"  {'Metric':<22} | {'AI Regime':>14} | {'Best Fixed':>14} | {'STR-001':>14}")
    print(f"  {'-'*22}-+-{'-'*14}-+-{'-'*14}-+-{'-'*14}")

    bl_metrics = {}
    for sid, _, m in preset_results:
        if sid == "STR-001":
            bl_metrics = m
            break

    best_m = best_preset[2] if best_preset else {}

    metric_rows = [
        ("Total Return %", "total_return_pct", True),
        ("Final Equity", "final_equity", False),
        ("Total Trades", "total_trades", False),
        ("Win Rate %", "win_rate_pct", False),
        ("Profit Factor", "profit_factor", False),
        ("Sharpe Ratio", "sharpe_ratio", False),
        ("Sortino Ratio", "sortino_ratio", False),
        ("Max Drawdown %", "max_drawdown_pct", False),
        ("Calmar Ratio", "calmar_ratio", False),
        ("Avg Holding Hrs", "avg_holding_hours", False),
    ]

    for label, key, is_pct in metric_rows:
        ai_v = ai_metrics.get(key)
        bl_v = bl_metrics.get(key)
        best_v = best_m.get(key)

        def fmt(v):
            if v is None:
                return "--"
            if key == "final_equity":
                return f"{v:>12,.0f}"
            if key in ("total_trades",):
                return f"{int(v)}"
            if key == "profit_factor":
                return _fmt_pf(v)
            if is_pct:
                return f"{v:+.2f}%"
            return f"{v:.2f}"

        print(f"  {label:<22} | {fmt(ai_v):>14} | {fmt(best_v):>14} | {fmt(bl_v):>14}")

    if best_preset:
        print(f"\n  * Best Fixed = {best_preset[0]} ({best_preset[1]})")

    # Verdict
    ai_ret = ai_metrics.get("total_return_pct", 0) or 0
    bl_ret = bl_metrics.get("total_return_pct", 0) or 0
    best_ret = best_m.get("total_return_pct", 0) or 0

    print()
    print("  [ Verdict ]")
    if ai_ret > best_ret:
        print(f"  AI Regime mode WINS vs all fixed strategies by {ai_ret - best_ret:+.2f}%p")
    elif ai_ret > bl_ret:
        print(f"  AI Regime mode beats baseline (STR-001) by {ai_ret - bl_ret:+.2f}%p")
        print(f"  But underperforms best fixed ({best_preset[0]}) by {best_ret - ai_ret:.2f}%p")
    else:
        print(f"  Fixed strategies outperform AI Regime mode")
        print(f"  Best: {best_preset[0]} at {best_ret:+.2f}% vs AI {ai_ret:+.2f}%")

    print(f"\n  Elapsed: {elapsed_ai:.1f}s")
    print("=" * 100)


if __name__ == "__main__":
    asyncio.run(main())
