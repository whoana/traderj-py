"""Market regime detection using ADX + BB Width + DI direction.

Classifies the market into 6 regimes:
  - BULL_TREND_HIGH_VOL: Bullish trend + high volatility (ADX > 25, DI+ > DI-, BB Width > threshold)
  - BULL_TREND_LOW_VOL:  Bullish trend + low volatility
  - BEAR_TREND_HIGH_VOL: Bearish trend + high volatility (ADX > 25, DI- > DI+)
  - BEAR_TREND_LOW_VOL:  Bearish trend + low volatility
  - RANGING_HIGH_VOL:    Sideways with high volatility (ADX <= 25)
  - RANGING_LOW_VOL:     Sideways with low volatility

Direction detection uses DMP/DMN (DI+/DI-) already computed by indicators.py.

Recommended strategy mapping:
  - BULL_TREND_* → Trend Following (STR-001/002)
  - BEAR_TREND_* → Bear Defensive / Cautious Reversal (STR-007/008)
  - RANGING_*    → Grid Trading or Mean Reversion (STR-003/005)
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
    dmp: float  # DI+ (positive directional indicator)
    dmn: float  # DI- (negative directional indicator)
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

    _default = RegimeResult(
        regime=RegimeType.RANGING_LOW_VOL,
        adx=0.0, bb_width=0.0, dmp=0.0, dmn=0.0,
        trend_strength=0.0, volatility_level=0.0, confidence=0.0,
    )

    if len(df) < cfg.min_bars:
        return _default

    # Use smoothed values over last N bars for stability
    tail = df.tail(cfg.smoothing_period)

    adx_vals = tail["adx"].dropna()
    bb_width_vals = tail["bb_width"].dropna()
    dmp_vals = tail["dmp"].dropna() if "dmp" in tail.columns else pd.Series(dtype=float)
    dmn_vals = tail["dmn"].dropna() if "dmn" in tail.columns else pd.Series(dtype=float)

    if adx_vals.empty or bb_width_vals.empty:
        return _default

    adx = float(adx_vals.mean())
    bb_width = float(bb_width_vals.mean())
    dmp = float(dmp_vals.mean()) if not dmp_vals.empty else 0.0
    dmn = float(dmn_vals.mean()) if not dmn_vals.empty else 0.0

    is_trending = adx > cfg.adx_trend_threshold
    is_high_vol = bb_width > cfg.bb_width_vol_threshold
    is_bullish = dmp >= dmn  # DI+ >= DI- means bullish direction

    if is_trending:
        if is_bullish:
            regime = RegimeType.BULL_TREND_HIGH_VOL if is_high_vol else RegimeType.BULL_TREND_LOW_VOL
        else:
            regime = RegimeType.BEAR_TREND_HIGH_VOL if is_high_vol else RegimeType.BEAR_TREND_LOW_VOL
    elif is_high_vol:
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
        dmp=round(dmp, 2),
        dmn=round(dmn, 2),
        trend_strength=round(trend_strength, 4),
        volatility_level=round(volatility_level, 4),
        confidence=round(confidence, 4),
    )


# Suggested preset mapping for auto-switch (P2)
REGIME_PRESET_MAP: dict[RegimeType, str] = {
    RegimeType.BULL_TREND_HIGH_VOL: "STR-002",   # Aggressive Trend
    RegimeType.BULL_TREND_LOW_VOL: "STR-001",    # Conservative Trend
    RegimeType.BEAR_TREND_HIGH_VOL: "STR-007",   # Bear Defensive
    RegimeType.BEAR_TREND_LOW_VOL: "STR-008",    # Bear Cautious Reversal
    RegimeType.RANGING_HIGH_VOL: "STR-003",      # Hybrid Reversal
    RegimeType.RANGING_LOW_VOL: "STR-005",       # Low-Frequency Conservative
}
