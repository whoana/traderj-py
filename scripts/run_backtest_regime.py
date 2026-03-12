"""Backtest with regime-based auto strategy switching.

Compares two modes on the same data:
  1. Fixed strategy (single preset, no switching)
  2. Regime-adaptive (auto-switches preset based on ADX + BB Width)

Usage:
    python -m scripts.run_backtest_regime
    python -m scripts.run_backtest_regime --days 60
    python -m scripts.run_backtest_regime --initial-preset STR-002
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from datetime import datetime, timedelta, timezone

import ccxt.async_support as ccxt
import pandas as pd

from engine.config.settings import AppSettings
from engine.data import create_data_store
from engine.strategy.backtest.engine import BacktestConfig, BacktestEngine
from engine.strategy.presets import STRATEGY_PRESETS
from engine.strategy.regime_switch import RegimeSwitchConfig, RegimeSwitchManager
from engine.strategy.signal import SignalGenerator
from shared.models import BacktestResult as BacktestResultModel

SYMBOL = "BTC/KRW"
TIMEFRAMES = ["15m", "1h", "4h", "1d"]
INITIAL_BALANCE = 10_000_000


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
            print(f"  [WARN] fetch_ohlcv error ({timeframe}): {e}")
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


def make_signal_generator(preset):
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


def determine_primary_tf(preset) -> str:
    tf_order = ["15m", "1h", "4h", "1d"]
    for tf in tf_order:
        if tf in preset.tf_weights:
            return tf
    return "1h"


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Regime-Adaptive Backtest")
    parser.add_argument("--days", type=int, default=30, help="Lookback days (default: 30)")
    parser.add_argument(
        "--initial-preset", type=str, default="STR-001",
        help="Initial preset for regime-adaptive mode (default: STR-001)",
    )
    args = parser.parse_args()

    lookback_days = args.days
    initial_preset_id = args.initial_preset

    if initial_preset_id not in STRATEGY_PRESETS:
        print(f"[ERROR] Unknown preset: {initial_preset_id}")
        print(f"Available: {', '.join(STRATEGY_PRESETS.keys())}")
        return

    print("=" * 80)
    print(f"  Regime-Adaptive Backtest — BTC/KRW {lookback_days}일")
    print(f"  초기 자본: {INITIAL_BALANCE:,.0f} KRW")
    print(f"  초기 프리셋: {initial_preset_id}")
    print("=" * 80)
    print()

    # ── 1. Fetch data ────────────────────────────────────────────

    exchange = ccxt.upbit({"enableRateLimit": False})
    try:
        await exchange.load_markets()
    except Exception as e:
        print(f"[ERROR] Upbit 연결 실패: {e}")
        await exchange.close()
        return

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=lookback_days + 60)
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

    initial_preset = STRATEGY_PRESETS[initial_preset_id]
    primary_tf = determine_primary_tf(initial_preset)
    tf_bars_per_day = {"15m": 96, "1h": 24, "4h": 6, "1d": 1}
    max_bars = tf_bars_per_day.get(primary_tf, 24) * lookback_days

    config = BacktestConfig(
        initial_balance_krw=INITIAL_BALANCE,
        fee_rate=0.0005,
        slippage_bps=5.0,
        max_bars=max_bars,
    )

    # ── 2. Fixed strategy backtest ───────────────────────────────

    print(f"[1/2] Fixed 전략 백테스트: {initial_preset_id} ({initial_preset.name})")
    sig_gen_fixed = make_signal_generator(initial_preset)
    engine_fixed = BacktestEngine(signal_generator=sig_gen_fixed, config=config)

    t0 = time.time()
    result_fixed = engine_fixed.run(ohlcv_data, primary_tf=primary_tf)
    elapsed_fixed = time.time() - t0
    print(f"  완료: {elapsed_fixed:.1f}s, {result_fixed.metrics['total_trades']} trades")

    # ── 3. Regime-adaptive backtest ──────────────────────────────

    print(f"\n[2/2] Regime-Adaptive 백테스트 (초기: {initial_preset_id})")
    sig_gen_regime = make_signal_generator(initial_preset)
    regime_mgr = RegimeSwitchManager(
        config=RegimeSwitchConfig(debounce_count=3, cooldown_minutes=60),
    )
    regime_mgr.set_initial_preset(initial_preset_id)

    engine_regime = BacktestEngine(
        signal_generator=sig_gen_regime,
        config=config,
        regime_switch_manager=regime_mgr,
    )

    t0 = time.time()
    result_regime = engine_regime.run(ohlcv_data, primary_tf=primary_tf)
    elapsed_regime = time.time() - t0
    switches = result_regime.config.get("regime_switches", 0)
    print(f"  완료: {elapsed_regime:.1f}s, {result_regime.metrics['total_trades']} trades, {switches} regime switches")

    # ── 4. Print regime switch history ───────────────────────────

    regime_history = result_regime.config.get("regime_history", [])
    if regime_history:
        print()
        print("레짐 전환 이력")
        print("-" * 80)
        for h in regime_history:
            old_r = h.get('old_regime') or '(none)'
            new_r = h.get('new_regime') or '(none)'
            old_p = h.get('old_preset') or '?'
            new_p = h.get('new_preset') or '?'
            conf = h.get('confidence', 0)
            print(f"  {old_r:>20} → {new_r:<20} | {old_p} → {new_p} | confidence={conf:.2f}")

    # ── 5. Comparison table ──────────────────────────────────────

    print()
    print("=" * 80)
    print("  비교 결과")
    print("=" * 80)

    mf = result_fixed.metrics
    mr = result_regime.metrics

    rows = [
        ("수익률 (%)", f"{mf.get('total_return_pct', 0):+.2f}", f"{mr.get('total_return_pct', 0):+.2f}"),
        ("최종 자산 (KRW)", f"{mf.get('final_equity', 0):>13,.0f}", f"{mr.get('final_equity', 0):>13,.0f}"),
        ("거래 수", f"{mf.get('total_trades', 0)}", f"{mr.get('total_trades', 0)}"),
        ("승률 (%)", f"{mf.get('win_rate_pct', 0):.1f}", f"{mr.get('win_rate_pct', 0):.1f}"),
        ("Profit Factor", _fmt_pf(mf.get('profit_factor', 0)), _fmt_pf(mr.get('profit_factor', 0))),
        ("Sharpe", f"{mf.get('sharpe_ratio', 0):.2f}", f"{mr.get('sharpe_ratio', 0):.2f}"),
        ("MDD (%)", f"{mf.get('max_drawdown_pct', 0):.2f}", f"{mr.get('max_drawdown_pct', 0):.2f}"),
        ("Calmar", f"{mf.get('calmar_ratio', 0):.2f}", f"{mr.get('calmar_ratio', 0):.2f}"),
        ("레짐 전환 횟수", "0", f"{switches}"),
    ]

    print(f"{'지표':<20} | {'Fixed':>15} | {'Regime-Adaptive':>15}")
    print("-" * 58)
    for label, v1, v2 in rows:
        print(f"{label:<20} | {v1:>15} | {v2:>15}")
    print("=" * 80)

    # ── 6. Save to DB ────────────────────────────────────────────

    settings = AppSettings()
    store = create_data_store(settings.db)
    await store.connect()

    for label, result in [("fixed", result_fixed), ("regime", result_regime)]:
        result_json = result.to_json()
        bt_model = BacktestResultModel(
            id=str(uuid.uuid4()),
            strategy_id=f"{initial_preset_id}-{label}",
            config_json=result_json.get("config", {}),
            metrics_json=result_json.get("metrics", {}),
            equity_curve_json=result_json.get("equity_curve", []),
            trades_json=result_json.get("trades", []),
            created_at=datetime.now(timezone.utc),
        )
        h = hashlib.sha256(f"{label}-{initial_preset_id}".encode()).hexdigest()[:16]
        await store.save_backtest_result(bt_model, params_hash=h)

    await store.disconnect()
    print(f"\n  결과가 DB에 저장되었습니다.")


def _fmt_pf(v):
    return "inf" if v == float("inf") else f"{v:.2f}"


if __name__ == "__main__":
    asyncio.run(main())
