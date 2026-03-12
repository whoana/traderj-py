"""Grid search for optimal strategy parameters with Walk-Forward validation.

Fetches 90 days of BTC/KRW data, splits into 60-day train / 30-day test,
and evaluates parameter combinations across a grid.

Usage:
    python -m scripts.run_backtest_tuning
"""

from __future__ import annotations

import asyncio
import csv
import itertools
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Suppress noisy logs from engine internals during grid search
logging.basicConfig(level=logging.ERROR)

import ccxt.async_support as ccxt
import pandas as pd

from engine.strategy.backtest.engine import BacktestConfig, BacktestEngine
from engine.strategy.scoring import ScoreWeights, TREND_FOLLOW_WEIGHTS, HYBRID_WEIGHTS
from engine.strategy.signal import SignalGenerator
from shared.enums import EntryMode, ScoringMode

SYMBOL = "BTC/KRW"
TIMEFRAMES = ["1h", "4h", "1d"]
LOOKBACK_DAYS = 90
TRAIN_DAYS = 60
TEST_DAYS = 30
INITIAL_BALANCE = 10_000_000

# Grid parameters (reduced for speed — ~120 combos)
GRID = {
    "buy_threshold": [0.05, 0.08, 0.10, 0.12, 0.15],
    "scoring_mode": [ScoringMode.TREND_FOLLOW, ScoringMode.HYBRID],
    "tf_weights_set": [
        {"1h": 0.3, "4h": 0.5},
        {"1h": 0.5, "4h": 0.5},
        {"4h": 0.4, "1d": 0.6},
    ],
    "use_daily_gate": [False],
    "score_weights_set": [
        ScoreWeights(0.50, 0.30, 0.20),
        ScoreWeights(0.40, 0.35, 0.25),
    ],
    "macro_weight": [0.0, 0.10],
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


def split_train_test(
    ohlcv_data: dict[str, pd.DataFrame],
    train_end: datetime,
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """Split data into train (<= train_end) and test (> train_end)."""
    train = {}
    test = {}
    for tf, df in ohlcv_data.items():
        train[tf] = df[df.index <= train_end]
        test[tf] = df[df.index > train_end]
    return train, test


def determine_primary_tf(tf_weights: dict[str, float]) -> str:
    tf_order = ["15m", "1h", "4h", "1d"]
    for tf in tf_order:
        if tf in tf_weights:
            return tf
    return "1h"


def run_backtest_on_data(
    ohlcv: dict[str, pd.DataFrame],
    params: dict,
    max_days: int | None = None,
) -> dict | None:
    """Run a single backtest with given params. Returns metrics dict or None."""
    tf_weights = params["tf_weights"]
    primary_tf = determine_primary_tf(tf_weights)

    # Check data availability
    for tf in tf_weights:
        if tf not in ohlcv or ohlcv[tf].empty:
            return None

    # Build subset
    strategy_data = {}
    for tf in set(tf_weights.keys()) | ({"1d"} if params.get("use_daily_gate") else set()):
        if tf in ohlcv and not ohlcv[tf].empty:
            strategy_data[tf] = ohlcv[tf]
        else:
            return None

    scoring_mode = params["scoring_mode"]
    score_weights = params["score_weights"]
    # For HYBRID mode, use HYBRID_WEIGHTS if default TF weights provided
    if scoring_mode == ScoringMode.HYBRID:
        score_weights = HYBRID_WEIGHTS

    signal_gen = SignalGenerator(
        strategy_id="tuning",
        scoring_mode=scoring_mode,
        entry_mode=EntryMode.WEIGHTED,
        score_weights=score_weights,
        tf_weights=tf_weights,
        buy_threshold=params["buy_threshold"],
        sell_threshold=-params["buy_threshold"],
        majority_min=2,
        use_daily_gate=params.get("use_daily_gate", False),
        macro_weight=params["macro_weight"],
    )

    tf_bars_per_day = {"15m": 96, "1h": 24, "4h": 6, "1d": 1}
    max_bars = None
    if max_days:
        max_bars = tf_bars_per_day.get(primary_tf, 24) * max_days

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
    except Exception:
        return None


def compute_rank_score(metrics: dict) -> float:
    """Composite ranking: return(30%) + sharpe(25%) + PF(15%) - MDD(15%) + trade_freq(15%)."""
    ret = metrics.get("total_return_pct", 0)
    sharpe = metrics.get("sharpe_ratio", 0)
    pf = metrics.get("profit_factor", 0)
    if pf == float("inf"):
        pf = 5.0
    mdd = abs(metrics.get("max_drawdown_pct", 0))
    trades = metrics.get("total_trades", 0)

    # Normalize trade frequency: target 5-30 trades
    trade_score = min(trades / 10.0, 1.0) if trades > 0 else 0

    return ret * 0.30 + sharpe * 0.25 + min(pf, 5) * 0.15 - mdd * 0.15 + trade_score * 0.15


def generate_grid() -> list[dict]:
    """Generate all parameter combinations."""
    combos = []
    for bt, sm, tfw, dg, sw, mw in itertools.product(
        GRID["buy_threshold"],
        GRID["scoring_mode"],
        GRID["tf_weights_set"],
        GRID["use_daily_gate"],
        GRID["score_weights_set"],
        GRID["macro_weight"],
    ):
        combos.append({
            "buy_threshold": bt,
            "scoring_mode": sm,
            "tf_weights": tfw,
            "use_daily_gate": dg,
            "score_weights": sw,
            "macro_weight": mw,
        })
    return combos


async def main():
    print("=" * 80)
    print(f"  BTC/KRW Grid Search — {LOOKBACK_DAYS}일 (Train {TRAIN_DAYS}d / Test {TEST_DAYS}d)")
    print(f"  초기 자본: {INITIAL_BALANCE:,.0f} KRW")
    print("=" * 80)

    # Fetch data
    exchange = ccxt.upbit({"enableRateLimit": False})
    try:
        await exchange.load_markets()
    except Exception as e:
        print(f"[ERROR] Upbit 연결 실패: {e}")
        await exchange.close()
        return

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=LOOKBACK_DAYS + 60)  # extra for indicator warm-up
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

    # Split train/test
    train_end = now - timedelta(days=TEST_DAYS)
    train_data, test_data = split_train_test(ohlcv_data, train_end)

    print(f"\nTrain period: ~{TRAIN_DAYS}d (until {train_end.strftime('%Y-%m-%d')})")
    print(f"Test period: ~{TEST_DAYS}d (after {train_end.strftime('%Y-%m-%d')})")

    # Generate grid
    grid = generate_grid()
    total = len(grid)
    print(f"\n총 {total}개 파라미터 조합 테스트 시작...\n")

    results = []
    t0 = time.time()

    for i, params in enumerate(grid):
        if (i + 1) % 10 == 0 or i == 0:
            elapsed = time.time() - t0
            eta = (elapsed / (i + 1)) * (total - i - 1) if i > 0 else 0
            print(f"  [{i+1}/{total}] elapsed={elapsed:.0f}s ETA={eta:.0f}s")

        # Train
        train_metrics = run_backtest_on_data(train_data, params, max_days=TRAIN_DAYS)
        if not train_metrics or train_metrics.get("total_trades", 0) < 5:
            continue

        # Test (OOS)
        test_metrics = run_backtest_on_data(test_data, params, max_days=TEST_DAYS)
        if not test_metrics:
            continue

        train_ret = train_metrics.get("total_return_pct", 0)
        test_ret = test_metrics.get("total_return_pct", 0)
        divergence = abs(train_ret - test_ret)
        overfit_warn = "YES" if divergence > 3.0 else ""

        rank = compute_rank_score(test_metrics)

        results.append({
            "buy_threshold": params["buy_threshold"],
            "sell_threshold": -params["buy_threshold"],
            "scoring_mode": params["scoring_mode"].value,
            "tf_weights": str(params["tf_weights"]),
            "use_daily_gate": params["use_daily_gate"],
            "score_weights": f"({params['score_weights'].w1},{params['score_weights'].w2},{params['score_weights'].w3})",
            "macro_weight": params["macro_weight"],
            "train_return_pct": round(train_ret, 2),
            "train_trades": train_metrics.get("total_trades", 0),
            "train_sharpe": round(train_metrics.get("sharpe_ratio", 0), 2),
            "test_return_pct": round(test_ret, 2),
            "test_trades": test_metrics.get("total_trades", 0),
            "test_sharpe": round(test_metrics.get("sharpe_ratio", 0), 2),
            "test_pf": round(min(test_metrics.get("profit_factor", 0), 99), 2),
            "test_mdd_pct": round(test_metrics.get("max_drawdown_pct", 0), 2),
            "test_win_rate": round(test_metrics.get("win_rate_pct", 0), 1),
            "rank_score": round(rank, 4),
            "overfit_warn": overfit_warn,
        })

    elapsed_total = time.time() - t0
    print(f"\n완료: {len(results)}개 유효 결과 / {total}개 조합 ({elapsed_total:.0f}s)")

    if not results:
        print("유효한 결과가 없습니다.")
        return

    # Sort by rank
    results.sort(key=lambda r: r["rank_score"], reverse=True)

    # Save CSV
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = results_dir / f"tuning_grid_{timestamp}.csv"

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

    print(f"\n결과 저장: {csv_path}")

    # Print top 20
    print("\n" + "=" * 140)
    print(f"{'Rank':>4} | {'BuyTh':>5} | {'Mode':>12} | {'TF Weights':>30} | {'Gate':>4} | {'Macro':>5} | "
          f"{'TrainRet%':>8} | {'TestRet%':>8} | {'Sharpe':>6} | {'PF':>5} | {'MDD%':>5} | {'WR%':>4} | "
          f"{'Trades':>6} | {'Score':>6} | {'OFit':>4}")
    print("-" * 140)

    for i, r in enumerate(results[:20]):
        print(f"{i+1:>4} | {r['buy_threshold']:>5.2f} | {r['scoring_mode']:>12} | "
              f"{r['tf_weights']:>30} | {str(r['use_daily_gate'])[0]:>4} | {r['macro_weight']:>5.2f} | "
              f"{r['train_return_pct']:>+7.2f} | {r['test_return_pct']:>+7.2f} | "
              f"{r['test_sharpe']:>6.2f} | {r['test_pf']:>5.2f} | {r['test_mdd_pct']:>5.2f} | "
              f"{r['test_win_rate']:>4.0f} | {r['test_trades']:>6} | {r['rank_score']:>6.2f} | "
              f"{r['overfit_warn']:>4}")

    print("=" * 140)

    # Summary
    positive_oos = [r for r in results if r["test_return_pct"] > 0]
    print(f"\nOOS 양수 수익률 조합: {len(positive_oos)}/{len(results)}")
    if positive_oos:
        best = positive_oos[0]
        print(f"Best OOS: {best['test_return_pct']:+.2f}% (buy_th={best['buy_threshold']}, "
              f"mode={best['scoring_mode']}, macro={best['macro_weight']})")


if __name__ == "__main__":
    asyncio.run(main())
