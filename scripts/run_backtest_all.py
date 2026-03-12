"""Run backtest for all 7 strategy presets on 1-month BTC/KRW data.

Fetches real historical data from Upbit Public API (no API key needed),
runs BacktestEngine for each strategy, and prints comparison table.

Usage:
    python -m scripts.run_backtest_all
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import ccxt.async_support as ccxt
import pandas as pd

from engine.config.settings import AppSettings
from engine.data import create_data_store
from engine.strategy.backtest.engine import BacktestConfig, BacktestEngine
from engine.strategy.presets import STRATEGY_PRESETS, StrategyPreset
from engine.strategy.signal import SignalGenerator
from shared.models import BacktestResult as BacktestResultModel


SYMBOL = "BTC/KRW"
TIMEFRAMES = ["15m", "1h", "4h", "1d"]
LOOKBACK_DAYS = 90
INITIAL_BALANCE = 10_000_000  # 1000만원


async def fetch_ohlcv_paginated(
    exchange: ccxt.upbit,
    symbol: str,
    timeframe: str,
    since_ms: int,
    until_ms: int,
    limit_per_req: int = 200,
) -> list[list]:
    """Fetch OHLCV with pagination to get > 200 candles."""
    all_candles: list[list] = []
    cursor = since_ms

    while cursor < until_ms:
        try:
            candles = await exchange.fetch_ohlcv(
                symbol, timeframe, since=cursor, limit=limit_per_req
            )
        except Exception as e:
            print(f"  [WARN] fetch_ohlcv error ({timeframe}): {e}")
            break

        if not candles:
            break

        all_candles.extend(candles)
        last_ts = candles[-1][0]
        if last_ts <= cursor:
            break
        cursor = last_ts + 1

        # Rate limit: small delay between requests
        await asyncio.sleep(0.15)

    # Deduplicate by timestamp
    seen = set()
    unique = []
    for c in all_candles:
        if c[0] not in seen and c[0] <= until_ms:
            seen.add(c[0])
            unique.append(c)

    unique.sort(key=lambda c: c[0])
    return unique


def candles_to_df(raw: list[list]) -> pd.DataFrame:
    """Convert ccxt OHLCV list to DataFrame."""
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
    """Pick the smallest (most granular) timeframe as primary."""
    tf_order = ["15m", "1h", "4h", "1d"]
    for tf in tf_order:
        if tf in preset.tf_weights:
            return tf
    return "1h"


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


def compute_params_hash(preset: StrategyPreset, config: BacktestConfig) -> str:
    """Create a deterministic hash from strategy params + backtest config."""
    data = {
        "strategy_id": preset.strategy_id,
        "scoring_mode": preset.scoring_mode,
        "entry_mode": preset.entry_mode,
        "score_weights": preset.score_weights,
        "tf_weights": preset.tf_weights,
        "buy_threshold": preset.buy_threshold,
        "sell_threshold": preset.sell_threshold,
        "majority_min": preset.majority_min,
        "use_daily_gate": preset.use_daily_gate,
        "macro_weight": preset.macro_weight,
        "initial_balance_krw": config.initial_balance_krw,
        "fee_rate": config.fee_rate,
        "slippage_bps": config.slippage_bps,
        "max_bars": config.max_bars,
    }
    raw = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


async def main():
    print("=" * 80)
    print(f"  BTC/KRW 전략별 백테스트 — 최근 {LOOKBACK_DAYS}일")
    print(f"  초기 자본: {INITIAL_BALANCE:,.0f} KRW")
    print("=" * 80)
    print()

    # ── 0. Connect to DataStore ─────────────────────────────────

    settings = AppSettings()
    store = create_data_store(settings.db)
    await store.connect()

    # ── 1. Fetch data from Upbit ────────────────────────────────

    exchange = ccxt.upbit({"enableRateLimit": False})

    try:
        await exchange.load_markets()
    except Exception as e:
        print(f"[ERROR] Upbit 연결 실패: {e}")
        await exchange.close()
        return

    now = datetime.now(timezone.utc)
    # Need extra lookback for indicator warm-up (EMA 200 on 4h = 200*4h = ~33 days)
    # Fetch 60 extra days to ensure sufficient warm-up for all timeframes
    since = now - timedelta(days=LOOKBACK_DAYS + 60)
    since_ms = int(since.timestamp() * 1000)
    until_ms = int(now.timestamp() * 1000)

    print("Upbit에서 캔들 데이터 조회 중...")
    ohlcv_data: dict[str, pd.DataFrame] = {}

    for tf in TIMEFRAMES:
        print(f"  {tf}...", end=" ", flush=True)
        raw = await fetch_ohlcv_paginated(exchange, SYMBOL, tf, since_ms, until_ms)
        df = candles_to_df(raw)
        ohlcv_data[tf] = df
        print(f"{len(df)} candles")

    await exchange.close()

    print()

    # Verify we have enough data
    for tf, df in ohlcv_data.items():
        if len(df) < 60:
            print(f"[WARN] {tf} 데이터 부족: {len(df)} candles (최소 60 필요)")

    # ── 2. Run backtests ────────────────────────────────────────

    results = []

    for strategy_id, preset in STRATEGY_PRESETS.items():
        # Build per-strategy OHLCV subset
        needed_tfs = set(preset.tf_weights.keys())
        if preset.use_daily_gate and "1d" not in needed_tfs:
            needed_tfs.add("1d")

        strategy_data: dict[str, pd.DataFrame] = {}
        skip = False
        for tf in needed_tfs:
            if tf in ohlcv_data and not ohlcv_data[tf].empty:
                strategy_data[tf] = ohlcv_data[tf]
            else:
                print(f"[SKIP] {strategy_id}: {tf} 데이터 없음")
                skip = True
                break

        if skip:
            continue

        primary_tf = determine_primary_tf(preset)
        signal_gen = make_signal_generator(preset)

        # Limit bars to ~30 days worth of primary TF
        tf_bars_per_day = {"15m": 96, "1h": 24, "4h": 6, "1d": 1}
        max_bars = tf_bars_per_day.get(primary_tf, 24) * LOOKBACK_DAYS

        config = BacktestConfig(
            initial_balance_krw=INITIAL_BALANCE,
            fee_rate=0.0005,
            slippage_bps=5.0,
            max_bars=max_bars,
        )
        engine = BacktestEngine(
            signal_generator=signal_gen,
            config=config,
        )

        try:
            t0 = time.time()
            result = engine.run(strategy_data, primary_tf=primary_tf)
            elapsed = time.time() - t0
            results.append((preset, result, elapsed, config))
            print(f"  {strategy_id} ({preset.name}) — {elapsed:.1f}s, {result.metrics['total_trades']} trades")

            # Save to PostgreSQL
            params_hash = compute_params_hash(preset, config)
            result_json = result.to_json()
            bt_model = BacktestResultModel(
                id=str(uuid.uuid4()),
                strategy_id=strategy_id,
                config_json=result_json.get("config", {}),
                metrics_json=result_json.get("metrics", {}),
                equity_curve_json=result_json.get("equity_curve", []),
                trades_json=result_json.get("trades", []),
                created_at=datetime.now(timezone.utc),
            )
            await store.save_backtest_result(bt_model, params_hash)
            print(f"    → DB 저장 완료 (hash={params_hash})")

        except Exception as e:
            print(f"  [ERROR] {strategy_id}: {e}")

    print()

    # ── 3. Print comparison table ───────────────────────────────

    if not results:
        print("백테스트 결과가 없습니다.")
        return

    # Sort by total return descending
    results.sort(key=lambda r: r[1].metrics.get("total_return_pct", 0), reverse=True)  # noqa: E501

    # Header
    print("=" * 120)
    print(f"{'전략':>10} | {'이름':<24} | {'수익률%':>8} | {'최종자산':>14} | "
          f"{'거래수':>5} | {'승률%':>6} | {'PF':>6} | {'Sharpe':>7} | "
          f"{'MDD%':>7} | {'연승':>3} | {'연패':>3}")
    print("-" * 120)

    for preset, result, elapsed, _cfg in results:
        m = result.metrics
        sid = preset.strategy_id
        name = preset.name[:22]
        ret = m.get("total_return_pct", 0)
        final = m.get("final_equity", INITIAL_BALANCE)
        trades = m.get("total_trades", 0)
        wr = m.get("win_rate_pct", 0)
        pf = m.get("profit_factor", 0)
        sharpe = m.get("sharpe_ratio", 0)
        mdd = m.get("max_drawdown_pct", 0)
        cw = m.get("max_consecutive_wins", 0)
        cl = m.get("max_consecutive_losses", 0)

        # Format profit factor
        pf_str = "∞" if pf == float("inf") else f"{pf:.2f}"

        # Color indicator
        ret_sign = "+" if ret > 0 else ""

        print(f"{sid:>10} | {name:<24} | {ret_sign}{ret:>7.2f} | {final:>13,.0f} | "
              f"{trades:>5} | {wr:>5.1f} | {pf_str:>6} | {sharpe:>7.2f} | "
              f"{mdd:>6.2f} | {cw:>3} | {cl:>3}")

    print("=" * 120)

    # ── 4. Detailed per-strategy summary ─────────────────────────

    print()
    print("상세 지표")
    print("-" * 80)

    for preset, result, elapsed, _cfg in results:
        m = result.metrics
        print(f"\n[{preset.strategy_id}] {preset.name}")
        print(f"  Primary TF: {determine_primary_tf(preset)}")
        print(f"  TF Weights: {preset.tf_weights}")
        print(f"  Buy/Sell Threshold: {preset.buy_threshold} / {preset.sell_threshold}")
        print(f"  수익률: {m.get('total_return_pct', 0):+.2f}%")
        print(f"  최종 자산: {m.get('final_equity', 0):,.0f} KRW")
        print(f"  거래 수: {m.get('total_trades', 0)}")
        if m.get("total_trades", 0) > 0:
            print(f"  승/패: {m.get('winning_trades', 0)}/{m.get('losing_trades', 0)} "
                  f"(승률 {m.get('win_rate_pct', 0):.1f}%)")
            print(f"  평균 수익: {m.get('avg_win_krw', 0):,.0f} KRW | "
                  f"평균 손실: {m.get('avg_loss_krw', 0):,.0f} KRW")
            pf = m.get('profit_factor', 0)
            pf_str = "∞" if pf == float("inf") else f"{pf:.2f}"
            print(f"  Profit Factor: {pf_str}")
            print(f"  최대 수익 거래: {m.get('best_trade_krw', 0):+,.0f} KRW")
            print(f"  최대 손실 거래: {m.get('worst_trade_krw', 0):+,.0f} KRW")
            print(f"  평균 보유 시간: {m.get('avg_holding_hours', 0):.1f}h")
        print(f"  Sharpe: {m.get('sharpe_ratio', 0):.2f} | "
              f"Sortino: {m.get('sortino_ratio', 0):.2f}")
        print(f"  MDD: {m.get('max_drawdown_pct', 0):.2f}% "
              f"({m.get('max_drawdown_duration_bars', 0)} bars)")
        print(f"  Calmar: {m.get('calmar_ratio', 0):.2f}")
        print(f"  처리된 바: {result.config.get('bars_processed', 0)} | 소요: {elapsed:.1f}s")

    # ── 5. Cleanup ──────────────────────────────────────────────

    await store.disconnect()
    print(f"\n  총 {len(results)}개 전략 결과가 DB에 저장되었습니다.")


if __name__ == "__main__":
    asyncio.run(main())
