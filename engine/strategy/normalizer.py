"""Z-score normalization engine.

Replaces arbitrary scaling constants (x5, x10, x33) from legacy code
with statistically consistent rolling Z-score normalization.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_LOOKBACK = 100


def z_score(
    series: pd.Series,
    lookback: int = DEFAULT_LOOKBACK,
) -> pd.Series:
    """Compute rolling Z-score.

    z = (x - mean_N) / std_N

    Args:
        series: Raw value series.
        lookback: Rolling window size in bars.

    Returns:
        Z-score series. Returns 0.0 where std=0 (no variation).
    """
    min_periods = max(lookback // 2, 10)
    rolling_mean = series.rolling(window=lookback, min_periods=min_periods).mean()
    rolling_std = series.rolling(window=lookback, min_periods=min_periods).std()
    return ((series - rolling_mean) / rolling_std.replace(0, float("nan"))).fillna(0.0)


def z_to_score(
    z: float | pd.Series,
    method: str = "tanh",
) -> float | pd.Series:
    """Map Z-score to [-1, +1] range.

    Args:
        z: Z-score value or series.
        method: "tanh" (smooth curve) or "clip" (linear clipping at +/-3).

    Returns:
        Normalized score in [-1, +1] range.
    """
    if method == "tanh":
        return np.tanh(z)
    elif method == "clip":
        if isinstance(z, pd.Series):
            return z.clip(-3, 3) / 3.0
        return max(-1.0, min(1.0, z / 3.0))
    else:
        raise ValueError(f"Unknown method: {method}")


def normalize_indicators(
    df: pd.DataFrame,
    lookback: int = DEFAULT_LOOKBACK,
) -> pd.DataFrame:
    """Add Z-score normalized columns to indicator DataFrame.

    Normalization targets (replaces legacy arbitrary constants):
    - macd_hist  : legacy (hist/close * 100 * 10)  -> z_score(macd_hist)
    - obv change : legacy (obv_change * 5)          -> z_score(obv_5bar_change)
    - roc 5-bar  : legacy (roc * 33)                -> z_score(roc_5bar)

    Returns:
        New DataFrame with added z_* columns. Original is not modified.
    """
    out = df.copy()

    # MACD histogram Z-score
    if "macd_hist" in out.columns:
        out["z_macd_hist"] = z_to_score(z_score(out["macd_hist"], lookback))

    # OBV 5-bar change rate Z-score
    if "obv" in out.columns:
        obv_change = out["obv"].pct_change(periods=5)
        out["z_obv_change"] = z_to_score(z_score(obv_change, lookback))

    # Price ROC 5-bar Z-score
    if "close" in out.columns:
        roc_5 = out["close"].pct_change(periods=5)
        out["z_roc_5"] = z_to_score(z_score(roc_5, lookback))

    # MACD acceleration Z-score (3-bar change)
    if "macd_hist" in out.columns:
        macd_accel = out["macd_hist"].diff(periods=3)
        out["z_macd_accel"] = z_to_score(z_score(macd_accel, lookback))

    # CMF Z-score
    if "cmf" in out.columns:
        out["z_cmf"] = z_to_score(z_score(out["cmf"], lookback))

    # ATR percentile (volatility level normalization)
    if "atr_pct" in out.columns:
        out["z_atr_pct"] = z_to_score(z_score(out["atr_pct"], lookback))

    return out
