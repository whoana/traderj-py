"""Market regime detection using ADX + BB Width.

Classifies the market into 4 regimes:
  - TRENDING_HIGH_VOL: Strong trend with high volatility (ADX > 25, BB Width > threshold)
  - TRENDING_LOW_VOL:  Strong trend with low volatility (ADX > 25, BB Width <= threshold)
  - RANGING_HIGH_VOL:  Sideways with high volatility (ADX <= 25, BB Width > threshold)
  - RANGING_LOW_VOL:   Sideways with low volatility (ADX <= 25, BB Width <= threshold)

Recommended strategy mapping:
  - TRENDING_*   → Trend Following (STR-001/002)
  - RANGING_*    → Grid Trading or Mean Reversion (STR-003)
  - *_HIGH_VOL   → Wider stops, smaller positions
  - *_LOW_VOL    → Tighter stops, larger positions
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from shared.enums import RegimeType

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegimeConfig:
    """Regime detection parameters."""

    adx_trend_threshold: float = 25.0
    bb_width_vol_threshold: float = 0.04
    smoothing_period: int = 3  # bars to confirm regime change
    min_bars: int = 30


@dataclass(frozen=True)
class RegimeResult:
    """Regime detection result."""

    regime: RegimeType
    adx: float
    bb_width: float
    trend_strength: float  # 0~1 normalized ADX
    volatility_level: float  # 0~1 normalized BB Width
    confidence: float  # how clearly the regime is identified


def detect_regime(
    df: pd.DataFrame,
    config: RegimeConfig | None = None,
) -> RegimeResult:
    """Detect current market regime from indicator DataFrame.

    Args:
        df: DataFrame with 'adx', 'bb_width' columns (from compute_indicators).
        config: Detection parameters.

    Returns:
        RegimeResult with classification and metrics.
    """
    cfg = config or RegimeConfig()

    if len(df) < cfg.min_bars:
        return RegimeResult(
            regime=RegimeType.RANGING_LOW_VOL,
            adx=0.0,
            bb_width=0.0,
            trend_strength=0.0,
            volatility_level=0.0,
            confidence=0.0,
        )

    # Use smoothed values over last N bars for stability
    tail = df.tail(cfg.smoothing_period)

    adx_vals = tail["adx"].dropna()
    bb_width_vals = tail["bb_width"].dropna()

    if adx_vals.empty or bb_width_vals.empty:
        return RegimeResult(
            regime=RegimeType.RANGING_LOW_VOL,
            adx=0.0,
            bb_width=0.0,
            trend_strength=0.0,
            volatility_level=0.0,
            confidence=0.0,
        )

    adx = float(adx_vals.mean())
    bb_width = float(bb_width_vals.mean())

    is_trending = adx > cfg.adx_trend_threshold
    is_high_vol = bb_width > cfg.bb_width_vol_threshold

    if is_trending and is_high_vol:
        regime = RegimeType.TRENDING_HIGH_VOL
    elif is_trending and not is_high_vol:
        regime = RegimeType.TRENDING_LOW_VOL
    elif not is_trending and is_high_vol:
        regime = RegimeType.RANGING_HIGH_VOL
    else:
        regime = RegimeType.RANGING_LOW_VOL

    # Normalized strength/level (0~1)
    trend_strength = min(adx / 50.0, 1.0)
    volatility_level = min(bb_width / 0.10, 1.0)

    # Confidence: how far from the threshold boundaries
    adx_distance = abs(adx - cfg.adx_trend_threshold) / cfg.adx_trend_threshold
    bb_distance = abs(bb_width - cfg.bb_width_vol_threshold) / cfg.bb_width_vol_threshold
    confidence = min(1.0, (adx_distance + bb_distance) / 2)

    return RegimeResult(
        regime=regime,
        adx=round(adx, 2),
        bb_width=round(bb_width, 4),
        trend_strength=round(trend_strength, 4),
        volatility_level=round(volatility_level, 4),
        confidence=round(confidence, 4),
    )


# Suggested preset mapping for auto-switch (P2)
REGIME_PRESET_MAP: dict[RegimeType, str] = {
    RegimeType.TRENDING_HIGH_VOL: "STR-002",   # Aggressive Trend
    RegimeType.TRENDING_LOW_VOL: "STR-001",    # Conservative Trend
    RegimeType.RANGING_HIGH_VOL: "STR-003",    # Hybrid Reversal
    RegimeType.RANGING_LOW_VOL: "STR-005",     # Low-Frequency Conservative
}
