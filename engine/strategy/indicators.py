"""Technical indicator computation pipeline.

Computes 20+ indicator columns from OHLCV data using pandas-ta.
All parameters are configurable via IndicatorConfig.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pandas_ta as ta


@dataclass(frozen=True)
class IndicatorConfig:
    """Indicator parameters — extractable from StrategyParams."""

    ema_short: int = 20
    ema_medium: int = 50
    ema_long: int = 200
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    stoch_rsi_period: int = 14
    stoch_smooth_k: int = 3
    stoch_smooth_d: int = 3
    bb_period: int = 20
    bb_std: float = 2.0
    adx_period: int = 14
    atr_period: int = 14
    vwap_anchor: str = "D"
    cmf_period: int = 20
    volume_ma_period: int = 20


def compute_indicators(
    df: pd.DataFrame,
    config: IndicatorConfig | None = None,
) -> pd.DataFrame:
    """Add technical indicator columns to OHLCV DataFrame.

    Args:
        df: DataFrame with columns ['open', 'high', 'low', 'close', 'volume'].
        config: Indicator parameters. Uses defaults if None.

    Returns:
        New DataFrame with added indicator columns. Original is not modified.

    Required minimum rows: max(ema_long, 100) + atr_period = 214+ bars
    """
    cfg = config or IndicatorConfig()
    out = df.copy()

    n = len(out)
    nan_series = pd.Series(float("nan"), index=out.index)

    # --- Trend ---
    out["ema_short"] = ta.ema(out["close"], length=cfg.ema_short) if n > cfg.ema_short else nan_series
    out["ema_medium"] = ta.ema(out["close"], length=cfg.ema_medium) if n > cfg.ema_medium else nan_series
    out["ema_long"] = ta.ema(out["close"], length=cfg.ema_long) if n > cfg.ema_long else nan_series

    adx_result = ta.adx(out["high"], out["low"], out["close"], length=cfg.adx_period) if n > cfg.adx_period * 2 else None
    if adx_result is not None:
        out["adx"] = adx_result[f"ADX_{cfg.adx_period}"]
        out["dmp"] = adx_result[f"DMP_{cfg.adx_period}"]
        out["dmn"] = adx_result[f"DMN_{cfg.adx_period}"]
    else:
        out["adx"] = nan_series
        out["dmp"] = nan_series
        out["dmn"] = nan_series

    # --- Volatility ---
    out["atr"] = ta.atr(out["high"], out["low"], out["close"], length=cfg.atr_period) if n > cfg.atr_period else nan_series
    out["atr_pct"] = out["atr"] / out["close"]

    # --- Bollinger Bands ---
    bbands = ta.bbands(out["close"], length=cfg.bb_period, std=cfg.bb_std) if n > cfg.bb_period else None
    bb_suffix = f"{cfg.bb_period}_{cfg.bb_std}_{cfg.bb_std}"
    if bbands is not None:
        out["bb_upper"] = bbands[f"BBU_{bb_suffix}"]
        out["bb_lower"] = bbands[f"BBL_{bb_suffix}"]
        out["bb_mid"] = bbands[f"BBM_{bb_suffix}"]
    else:
        out["bb_upper"] = nan_series
        out["bb_lower"] = nan_series
        out["bb_mid"] = nan_series
    bb_range = out["bb_upper"] - out["bb_lower"]
    out["bb_pct"] = (out["close"] - out["bb_lower"]) / bb_range.replace(0, float("nan"))
    out["bb_width"] = bb_range / out["bb_mid"]

    # --- Momentum ---
    out["rsi"] = ta.rsi(out["close"], length=cfg.rsi_period) if n > cfg.rsi_period else nan_series

    macd_min = cfg.macd_slow + cfg.macd_signal
    macd_result = ta.macd(
        out["close"], fast=cfg.macd_fast, slow=cfg.macd_slow, signal=cfg.macd_signal
    ) if n > macd_min else None
    if macd_result is not None:
        out["macd"] = macd_result[f"MACD_{cfg.macd_fast}_{cfg.macd_slow}_{cfg.macd_signal}"]
        out["macd_signal"] = macd_result[
            f"MACDs_{cfg.macd_fast}_{cfg.macd_slow}_{cfg.macd_signal}"
        ]
        out["macd_hist"] = macd_result[
            f"MACDh_{cfg.macd_fast}_{cfg.macd_slow}_{cfg.macd_signal}"
        ]
    else:
        out["macd"] = nan_series
        out["macd_signal"] = nan_series
        out["macd_hist"] = nan_series

    stoch_min = cfg.stoch_rsi_period * 2 + cfg.stoch_smooth_k
    stoch = ta.stochrsi(
        out["close"],
        length=cfg.stoch_rsi_period,
        rsi_length=cfg.stoch_rsi_period,
        k=cfg.stoch_smooth_k,
        d=cfg.stoch_smooth_d,
    ) if n > stoch_min else None
    stoch_prefix = (
        f"STOCHRSIk_{cfg.stoch_rsi_period}_{cfg.stoch_rsi_period}"
        f"_{cfg.stoch_smooth_k}_{cfg.stoch_smooth_d}"
    )
    stoch_d_prefix = (
        f"STOCHRSId_{cfg.stoch_rsi_period}_{cfg.stoch_rsi_period}"
        f"_{cfg.stoch_smooth_k}_{cfg.stoch_smooth_d}"
    )
    if stoch is not None:
        out["stochrsi_k"] = stoch[stoch_prefix]
        out["stochrsi_d"] = stoch[stoch_d_prefix]
    else:
        out["stochrsi_k"] = nan_series
        out["stochrsi_d"] = nan_series

    # --- Volume ---
    out["obv"] = ta.obv(out["close"], out["volume"]) if n > 1 else nan_series
    out["volume_ma"] = ta.sma(out["volume"], length=cfg.volume_ma_period) if n > cfg.volume_ma_period else nan_series

    # --- CMF (Chaikin Money Flow) ---
    out["cmf"] = ta.cmf(
        out["high"], out["low"], out["close"], out["volume"], length=cfg.cmf_period
    ) if n > cfg.cmf_period else nan_series

    return out
