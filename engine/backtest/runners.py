"""Backtest runner functions for 3 modes: single, compare, ai_regime.

Reuses existing BacktestEngine + SignalGenerator from engine.strategy.
Fetches candles via CandleCache (DB-cached, fills gaps from Upbit).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import aiosqlite
import pandas as pd

from engine.backtest.candle_cache import CandleCache
from engine.backtest.job_manager import BacktestJob
from engine.backtest.schemas import BacktestJobStatus, BacktestMode
from engine.strategy.backtest.engine import BacktestConfig, BacktestEngine, BacktestTrade
from engine.strategy.backtest.metrics import compute_metrics
from engine.strategy.indicators import compute_indicators
from engine.strategy.presets import STRATEGY_PRESETS, StrategyPreset
from engine.strategy.regime import REGIME_PRESET_MAP, detect_regime
from engine.strategy.signal import SignalGenerator

logger = logging.getLogger(__name__)

SYMBOL = "BTC/KRW"
TIMEFRAMES = ["1h", "4h", "1d"]
WARMUP_DAYS = 60
WEEK_DAYS = 7
_TF_BARS_PER_DAY = {"1h": 24, "4h": 6, "1d": 1}


def _make_signal_generator(preset: StrategyPreset) -> SignalGenerator:
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


def _primary_tf(preset: StrategyPreset) -> str:
    for tf in ["1h", "4h", "1d"]:
        if tf in preset.tf_weights:
            return tf
    return "1h"


def _market_info(ohlcv_1d: pd.DataFrame, start: datetime, end: datetime) -> dict[str, Any]:
    period = ohlcv_1d[(ohlcv_1d.index >= start) & (ohlcv_1d.index <= end)]
    if period.empty:
        return {}
    sp = float(period.iloc[0]["open"])
    ep = float(period.iloc[-1]["close"])
    return {"start_price": sp, "end_price": ep, "change_pct": round(((ep - sp) / sp) * 100, 2)}


def _metrics_to_dict(m: dict) -> dict[str, Any]:
    """Ensure all metrics values are JSON-serializable."""
    out = {}
    for k, v in m.items():
        if v == float("inf"):
            out[k] = None
        elif v == float("-inf"):
            out[k] = None
        elif isinstance(v, float) and v != v:  # NaN
            out[k] = None
        else:
            out[k] = v
    return out


def _trades_to_list(trades: list[BacktestTrade]) -> list[dict[str, Any]]:
    return [
        {
            "entry_time": t.entry_time.isoformat(),
            "exit_time": t.exit_time.isoformat(),
            "side": t.side,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "amount_btc": t.amount_btc,
            "pnl_krw": round(t.pnl_krw, 0),
            "pnl_pct": round(t.pnl_pct, 4),
            "exit_reason": t.exit_reason,
        }
        for t in trades
    ]


def _equity_summary(curve: list[dict], max_points: int = 500) -> list[dict[str, Any]]:
    """Downsample equity curve for JSON response."""
    if len(curve) <= max_points:
        return [{"time": e["time"].isoformat() if hasattr(e["time"], "isoformat") else str(e["time"]),
                 "equity": round(e["equity"], 0)} for e in curve]
    step = max(1, len(curve) // max_points)
    return [{"time": e["time"].isoformat() if hasattr(e["time"], "isoformat") else str(e["time"]),
             "equity": round(e["equity"], 0)} for e in curve[::step]]


# ── Upbit fetcher (used by CandleCache for gap-filling) ──────


async def _create_upbit_fetcher():
    """Create a fetcher function that uses ccxt Upbit API."""
    import ccxt.async_support as ccxt_async

    exchange = ccxt_async.upbit({"enableRateLimit": False})
    await exchange.load_markets()

    async def fetcher(symbol: str, tf: str, since_ms: int, until_ms: int) -> list[list]:
        all_candles: list[list] = []
        cursor = since_ms
        while cursor < until_ms:
            try:
                candles = await exchange.fetch_ohlcv(symbol, tf, since=cursor, limit=200)
            except Exception as e:
                logger.warning("Upbit fetch error (%s): %s", tf, e)
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

    return exchange, fetcher


async def _fetch_all_candles(
    cache: CandleCache,
    start: datetime,
    end: datetime,
    update: Callable[[str], None],
) -> tuple[dict[str, pd.DataFrame], Any]:
    """Fetch candles for all timeframes via cache (with Upbit gap-fill)."""
    warmup_start = start - timedelta(days=WARMUP_DAYS)
    since_ms = int(warmup_start.timestamp() * 1000)
    until_ms = int(end.timestamp() * 1000)

    exchange, fetcher = await _create_upbit_fetcher()
    ohlcv: dict[str, pd.DataFrame] = {}

    try:
        for tf in TIMEFRAMES:
            update(f"캔들 수집 중: {tf}")
            df = await cache.get_candles(SYMBOL, tf, since_ms, until_ms, fetcher=fetcher)
            ohlcv[tf] = df
            logger.info("Loaded %s: %d candles", tf, len(df))
    finally:
        await exchange.close()

    return ohlcv, exchange


def _run_single_preset(
    preset: StrategyPreset,
    ohlcv: dict[str, pd.DataFrame],
    initial_balance: float,
    period_days: int,
    max_bars_override: int | None = None,
) -> dict[str, Any]:
    """Run backtest for a single preset. Returns strategy result dict."""
    needed_tfs = set(preset.tf_weights.keys())
    if preset.use_daily_gate:
        needed_tfs.add("1d")
    data = {tf: ohlcv[tf] for tf in needed_tfs if tf in ohlcv}
    if not data:
        return {"strategy_id": preset.strategy_id, "name": preset.name, "error": "no data"}

    ptf = _primary_tf(preset)
    max_bars = max_bars_override or _TF_BARS_PER_DAY.get(ptf, 24) * period_days
    config = BacktestConfig(initial_balance_krw=initial_balance, fee_rate=0.0005, slippage_bps=5.0, max_bars=max_bars)
    sig = _make_signal_generator(preset)
    eng = BacktestEngine(signal_generator=sig, config=config)
    result = eng.run(data, primary_tf=ptf)

    return {
        "strategy_id": preset.strategy_id,
        "name": preset.name,
        "metrics": _metrics_to_dict(result.metrics),
        "equity_curve": _equity_summary(result.equity_curve),
        "trades": _trades_to_list(result.trades),
    }


# ── Runner: single ───────────────────────────────────────────


async def run_single(
    job: BacktestJob,
    update: Callable[[str], None],
    db: aiosqlite.Connection,
) -> dict[str, Any]:
    strategy_id = job.config["strategy_id"]
    preset = STRATEGY_PRESETS.get(strategy_id)
    if preset is None:
        raise ValueError(f"Unknown strategy: {strategy_id}")

    start = datetime.strptime(job.config["start_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = datetime.strptime(job.config["end_date"], "%Y-%m-%d").replace(
        hour=23, minute=59, second=59, tzinfo=timezone.utc
    )
    period_days = (end - start).days + 1
    initial = job.config.get("initial_balance", 50_000_000)

    cache = CandleCache(db)
    await cache.init_table()

    job.status = BacktestJobStatus.FETCHING
    ohlcv, _ = await _fetch_all_candles(cache, start, end, update)

    job.status = BacktestJobStatus.RUNNING
    update(f"백테스트 실행 중: {preset.name}")
    strat_result = _run_single_preset(preset, ohlcv, initial, period_days)

    market = _market_info(ohlcv.get("1d", pd.DataFrame()), start, end)

    return {
        "mode": "single",
        "period": {"start": job.config["start_date"], "end": job.config["end_date"], "days": period_days},
        "market": market,
        "strategies": [strat_result],
        "ranking": [strategy_id],
    }


# ── Runner: compare ──────────────────────────────────────────


async def run_compare(
    job: BacktestJob,
    update: Callable[[str], None],
    db: aiosqlite.Connection,
) -> dict[str, Any]:
    start = datetime.strptime(job.config["start_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = datetime.strptime(job.config["end_date"], "%Y-%m-%d").replace(
        hour=23, minute=59, second=59, tzinfo=timezone.utc
    )
    period_days = (end - start).days + 1
    initial = job.config.get("initial_balance", 50_000_000)

    cache = CandleCache(db)
    await cache.init_table()

    job.status = BacktestJobStatus.FETCHING
    ohlcv, _ = await _fetch_all_candles(cache, start, end, update)

    job.status = BacktestJobStatus.RUNNING
    presets = [(sid, p) for sid, p in STRATEGY_PRESETS.items() if sid != "default"]
    results: list[dict[str, Any]] = []

    for i, (sid, preset) in enumerate(presets):
        update(f"전략 {i + 1}/{len(presets)} 실행 중 ({preset.name})")
        try:
            r = _run_single_preset(preset, ohlcv, initial, period_days)
            results.append(r)
        except Exception as e:
            logger.warning("Backtest failed for %s: %s", sid, e)
            results.append({"strategy_id": sid, "name": preset.name, "error": str(e)})

    # Sort by return
    results.sort(
        key=lambda x: x.get("metrics", {}).get("total_return_pct", -999),
        reverse=True,
    )
    ranking = [r["strategy_id"] for r in results if "metrics" in r]
    market = _market_info(ohlcv.get("1d", pd.DataFrame()), start, end)

    return {
        "mode": "compare",
        "period": {"start": job.config["start_date"], "end": job.config["end_date"], "days": period_days},
        "market": market,
        "strategies": results,
        "ranking": ranking,
    }


# ── Runner: ai_regime ────────────────────────────────────────


async def run_ai_regime(
    job: BacktestJob,
    update: Callable[[str], None],
    db: aiosqlite.Connection,
) -> dict[str, Any]:
    start = datetime.strptime(job.config["start_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = datetime.strptime(job.config["end_date"], "%Y-%m-%d").replace(
        hour=23, minute=59, second=59, tzinfo=timezone.utc
    )
    period_days = (end - start).days + 1
    initial = job.config.get("initial_balance", 50_000_000)

    cache = CandleCache(db)
    await cache.init_table()

    job.status = BacktestJobStatus.FETCHING
    ohlcv, _ = await _fetch_all_candles(cache, start, end, update)

    job.status = BacktestJobStatus.RUNNING

    # ── Weekly regime detection + AI backtest ──
    weeks: list[tuple[datetime, datetime]] = []
    ws = start
    while ws < end:
        we = min(ws + timedelta(days=WEEK_DAYS) - timedelta(seconds=1), end)
        weeks.append((ws, we))
        ws = we + timedelta(seconds=1)

    ai_all_trades: list[BacktestTrade] = []
    ai_all_equity: list[dict] = []
    ai_balance = float(initial)
    regime_log: list[dict] = []

    for i, (ws, we) in enumerate(weeks):
        update(f"AI 레짐 분석 중: W{i + 1}/{len(weeks)}")

        # Detect regime
        regime_data = ohlcv.get("4h", pd.DataFrame())
        regime_slice = regime_data[regime_data.index <= ws]
        if len(regime_slice) < 30:
            regime_slice = regime_data[regime_data.index <= we]

        try:
            df_ind = compute_indicators(regime_slice)
            regime_result = detect_regime(df_ind)
            regime_name = regime_result.regime.value
            preset_id = REGIME_PRESET_MAP.get(regime_result.regime, "STR-001")
        except Exception:
            regime_name = "unknown"
            preset_id = "STR-001"

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

        # Run backtest for this week
        needed_tfs = set(preset.tf_weights.keys())
        if preset.use_daily_gate:
            needed_tfs.add("1d")
        week_data = {tf: ohlcv[tf][ohlcv[tf].index <= we].copy() for tf in needed_tfs if tf in ohlcv}

        if not week_data:
            continue

        ptf = _primary_tf(preset)
        max_bars = _TF_BARS_PER_DAY.get(ptf, 24) * week_days
        config = BacktestConfig(initial_balance_krw=ai_balance, fee_rate=0.0005, slippage_bps=5.0, max_bars=max_bars)
        sig = _make_signal_generator(preset)
        eng = BacktestEngine(signal_generator=sig, config=config)

        try:
            result = eng.run(week_data, primary_tf=ptf)
            ai_all_trades.extend(result.trades)
            ai_all_equity.extend(result.equity_curve)
            if result.equity_curve:
                ai_balance = result.equity_curve[-1]["equity"]
        except Exception as e:
            logger.warning("AI regime backtest W%d failed: %s", i + 1, e)

        w_ret = ((ai_balance - config.initial_balance_krw) / config.initial_balance_krw) * 100
        regime_log[-1]["return_pct"] = round(w_ret, 2)
        regime_log[-1]["trades"] = len(result.trades) if result else 0

    # AI aggregate metrics
    ai_metrics = compute_metrics(trades=ai_all_trades, equity_curve=ai_all_equity, initial_balance=initial)

    # ── Also run all individual presets for comparison ──
    update("개별 전략 비교 실행 중...")
    presets = [(sid, p) for sid, p in STRATEGY_PRESETS.items() if sid != "default"]
    compare_results: list[dict[str, Any]] = []

    for j, (sid, preset) in enumerate(presets):
        update(f"비교 전략 {j + 1}/{len(presets)} ({preset.name})")
        try:
            r = _run_single_preset(preset, ohlcv, initial, period_days)
            compare_results.append(r)
        except Exception as e:
            logger.warning("Compare backtest failed for %s: %s", sid, e)

    compare_results.sort(
        key=lambda x: x.get("metrics", {}).get("total_return_pct", -999),
        reverse=True,
    )
    ranking = [r["strategy_id"] for r in compare_results if "metrics" in r]

    # Regime distribution
    regime_counts = Counter(r["regime"] for r in regime_log)
    strat_counts = Counter(r["preset"] for r in regime_log)

    market = _market_info(ohlcv.get("1d", pd.DataFrame()), start, end)

    return {
        "mode": "ai_regime",
        "period": {"start": job.config["start_date"], "end": job.config["end_date"], "days": period_days},
        "market": market,
        "strategies": compare_results,
        "ranking": ranking,
        "ai_regime": {
            "weekly_decisions": regime_log,
            "regime_distribution": dict(regime_counts.most_common()),
            "strategy_usage": dict(strat_counts.most_common()),
            "aggregate_metrics": _metrics_to_dict(ai_metrics),
            "equity_curve": _equity_summary(ai_all_equity),
            "trades": _trades_to_list(ai_all_trades),
        },
    }
