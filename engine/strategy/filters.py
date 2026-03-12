"""Scoring functions for technical analysis.

Six scoring functions, each returning a value in [-1, +1]:
  - trend_score: EMA alignment, price vs EMA200, ADX direction
  - momentum_score: RSI, MACD Z-score, MACD crossover, StochRSI
  - volume_score: Volume/MA, OBV Z-score, CMF, Price-vol alignment, BB%B
  - reversal_score: Overextension reversal signals
  - breakout_score: BB breakout + volume confirmation
  - quick_momentum_score: Fast momentum (ROC + MACD accel)
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def trend_score(df: pd.DataFrame) -> float:
    """Trend strength score. [-1, +1]

    Components:
      - EMA alignment (weight 0.40)
      - Price vs EMA200 (weight 0.25)
      - ADX direction (weight 0.35)
    """
    last = df.iloc[-1]
    components: list[tuple[str, float, float]] = []

    # 1. EMA alignment (0.40)
    ema_s = last.get("ema_short")
    ema_m = last.get("ema_medium")
    ema_l = last.get("ema_long")
    if all(pd.notna(v) for v in (ema_s, ema_m, ema_l)):
        if ema_s > ema_m > ema_l:
            components.append(("ema_align", 1.0, 0.40))
        elif ema_s < ema_m < ema_l:
            components.append(("ema_align", -1.0, 0.40))
        elif ema_s > ema_m:
            # Partial bullish: continuous scale 0.4~0.7 based on ema_m distance from ema_l
            if ema_l > 0:
                dist_ratio = min((ema_m - ema_l) / ema_l / 0.03, 1.0) if ema_m > ema_l else 0.0
                partial = 0.4 + 0.3 * dist_ratio
            else:
                partial = 0.4
            components.append(("ema_align", partial, 0.40))
        elif ema_s < ema_m:
            # Partial bearish: continuous scale -0.4~-0.7
            if ema_l > 0:
                dist_ratio = min((ema_l - ema_m) / ema_l / 0.03, 1.0) if ema_m < ema_l else 0.0
                partial = -(0.4 + 0.3 * dist_ratio)
            else:
                partial = -0.4
            components.append(("ema_align", partial, 0.40))
        else:
            components.append(("ema_align", 0.0, 0.40))

    # 2. Price vs EMA long (0.25) — continuous scale
    close = last.get("close")
    ema_long = last.get("ema_long")
    if pd.notna(close) and pd.notna(ema_long) and ema_long > 0:
        distance = (close - ema_long) / ema_long
        price_score = float(np.tanh(distance / 0.03))
        components.append(("price_vs_ema200", price_score, 0.25))

    # 3. ADX direction (0.35) — continuous scale
    adx = last.get("adx")
    dmp = last.get("dmp")
    dmn = last.get("dmn")
    if all(pd.notna(v) for v in (adx, dmp, dmn)) and (dmp + dmn) > 0:
        di_ratio = (dmp - dmn) / (dmp + dmn)
        adx_strength = min(adx / 50.0, 1.0)
        adx_score = di_ratio * adx_strength
        components.append(("adx_direction", adx_score, 0.35))

    return _weighted_combine(components)


def momentum_score(df: pd.DataFrame) -> float:
    """Momentum score. [-1, +1]

    Components:
      - RSI (weight 0.30)
      - MACD histogram Z-score (weight 0.30)
      - MACD crossover with 3-bar decay (weight 0.15)
      - StochRSI (weight 0.25)
    """
    last = df.iloc[-1]
    components: list[tuple[str, float, float]] = []

    # 1. RSI normalized (0.30)
    rsi = last.get("rsi")
    if pd.notna(rsi):
        components.append(("rsi", (rsi - 50) / 50 * 0.8, 0.30))

    # 2. MACD histogram Z-score (0.30)
    z_macd = last.get("z_macd_hist")
    if pd.notna(z_macd):
        components.append(("macd_z", float(z_macd), 0.30))

    # 3. MACD crossover with 3-bar decay (0.15)
    if len(df) >= 4:
        cross_signal = _detect_macd_cross_decay(df, decay_bars=3)
        components.append(("macd_cross", cross_signal, 0.15))

    # 4. StochRSI (0.25)
    stoch_k = last.get("stochrsi_k")
    stoch_d = last.get("stochrsi_d")
    if pd.notna(stoch_k) and pd.notna(stoch_d):
        stoch_avg = (stoch_k + stoch_d) / 2
        components.append(("stochrsi", (stoch_avg - 50) / 50 * 0.6, 0.25))

    return _weighted_combine(components)


def volume_score(df: pd.DataFrame) -> float:
    """Volume confirmation score. [-1, +1]

    Components:
      - Volume/MA ratio (weight 0.25)
      - OBV Z-score (weight 0.20)
      - CMF Z-score (weight 0.20)
      - Price-volume alignment (weight 0.20)
      - BB %B (weight 0.15)
    """
    last = df.iloc[-1]
    components: list[tuple[str, float, float]] = []

    # 1. Volume/MA ratio (0.25)
    vol = last.get("volume")
    vol_ma = last.get("volume_ma")
    if pd.notna(vol) and pd.notna(vol_ma) and vol_ma > 0:
        ratio = vol / vol_ma
        vol_s = float(np.tanh((ratio - 1.0) * 1.5))
        components.append(("vol_ratio", vol_s, 0.25))

    # 2. OBV Z-score (0.20)
    z_obv = last.get("z_obv_change")
    if pd.notna(z_obv):
        components.append(("obv_z", float(z_obv), 0.20))

    # 3. CMF Z-score (0.20)
    z_cmf = last.get("z_cmf")
    if pd.notna(z_cmf):
        components.append(("cmf_z", float(z_cmf), 0.20))

    # 4. Price-volume alignment (0.20)
    if len(df) >= 2:
        close_now = last.get("close")
        close_prev = df.iloc[-2].get("close")
        if pd.notna(close_now) and pd.notna(close_prev) and pd.notna(vol) and pd.notna(vol_ma):
            price_up = close_now > close_prev
            high_vol = vol > vol_ma
            if price_up and high_vol:
                components.append(("price_vol_align", 0.6, 0.20))
            elif not price_up and high_vol:
                components.append(("price_vol_align", -0.6, 0.20))
            else:
                components.append(("price_vol_align", 0.0, 0.20))

    # 5. BB %B (0.15)
    bb_pct = last.get("bb_pct")
    if pd.notna(bb_pct):
        components.append(("bb_pct", (bb_pct - 0.5) * 0.6, 0.15))

    return _weighted_combine(components)


def reversal_score(df: pd.DataFrame) -> float:
    """Overextension reversal score. [-1, +1]

    Detects overbought/oversold conditions using RSI extremes,
    BB %B extremes, and StochRSI crossovers.
    """
    last = df.iloc[-1]
    components: list[tuple[str, float, float]] = []

    # 1. RSI extremes (0.35)
    rsi = last.get("rsi")
    if pd.notna(rsi):
        if rsi > 70:
            components.append(("rsi_extreme", -(rsi - 70) / 30, 0.35))
        elif rsi < 30:
            components.append(("rsi_extreme", (30 - rsi) / 30, 0.35))
        else:
            components.append(("rsi_extreme", 0.0, 0.35))

    # 2. BB %B extremes (0.30)
    bb_pct = last.get("bb_pct")
    if pd.notna(bb_pct):
        if bb_pct > 1.0:
            components.append(("bb_extreme", -(bb_pct - 1.0) * 0.5, 0.30))
        elif bb_pct < 0.0:
            components.append(("bb_extreme", -bb_pct * 0.5, 0.30))
        else:
            components.append(("bb_extreme", 0.0, 0.30))

    # 3. StochRSI crossover (0.35)
    stoch_k = last.get("stochrsi_k")
    stoch_d = last.get("stochrsi_d")
    if pd.notna(stoch_k) and pd.notna(stoch_d):
        if stoch_k < 20 and stoch_k > stoch_d:
            components.append(("stoch_reversal", 0.6, 0.35))
        elif stoch_k > 80 and stoch_k < stoch_d:
            components.append(("stoch_reversal", -0.6, 0.35))
        else:
            components.append(("stoch_reversal", 0.0, 0.35))

    return _weighted_combine(components)


def breakout_score(df: pd.DataFrame) -> float:
    """BB breakout + volume confirmation score. [-1, +1]

    Detects breakouts from Bollinger Bands confirmed by volume.
    """
    last = df.iloc[-1]
    components: list[tuple[str, float, float]] = []

    close = last.get("close")
    bb_upper = last.get("bb_upper")
    bb_lower = last.get("bb_lower")
    bb_width = last.get("bb_width")
    vol = last.get("volume")
    vol_ma = last.get("volume_ma")

    # 1. BB breakout direction (0.45)
    if pd.notna(close) and pd.notna(bb_upper) and pd.notna(bb_lower):
        if close > bb_upper:
            components.append(("bb_breakout", 0.8, 0.45))
        elif close < bb_lower:
            components.append(("bb_breakout", -0.8, 0.45))
        else:
            components.append(("bb_breakout", 0.0, 0.45))

    # 2. Volume confirmation (0.30)
    if pd.notna(vol) and pd.notna(vol_ma) and vol_ma > 0:
        vol_ratio = vol / vol_ma
        if vol_ratio > 1.5:
            components.append(("vol_confirm", 0.6, 0.30))
        elif vol_ratio > 1.0:
            components.append(("vol_confirm", 0.2, 0.30))
        else:
            components.append(("vol_confirm", -0.2, 0.30))

    # 3. BB width (squeeze detection) (0.25)
    if pd.notna(bb_width):
        if bb_width < 0.03:
            components.append(("bb_squeeze", 0.5, 0.25))
        elif bb_width > 0.10:
            components.append(("bb_squeeze", -0.3, 0.25))
        else:
            components.append(("bb_squeeze", 0.0, 0.25))

    return _weighted_combine(components)


def quick_momentum_score(df: pd.DataFrame) -> float:
    """Fast momentum score using ROC and MACD acceleration. [-1, +1]

    Components:
      - ROC 5-bar Z-score (weight 0.40)
      - MACD acceleration Z-score (weight 0.35)
      - Price action (weight 0.25)
    """
    last = df.iloc[-1]
    components: list[tuple[str, float, float]] = []

    # 1. ROC 5-bar Z-score (0.40)
    z_roc = last.get("z_roc_5")
    if pd.notna(z_roc):
        components.append(("roc_z", float(z_roc), 0.40))

    # 2. MACD acceleration Z-score (0.35)
    z_macd_accel = last.get("z_macd_accel")
    if pd.notna(z_macd_accel):
        components.append(("macd_accel_z", float(z_macd_accel), 0.35))

    # 3. Price action — consecutive candles (0.25)
    if len(df) >= 3:
        closes = df["close"].iloc[-3:].tolist()
        if all(pd.notna(c) for c in closes):
            if closes[2] > closes[1] > closes[0]:
                components.append(("price_action", 0.5, 0.25))
            elif closes[2] < closes[1] < closes[0]:
                components.append(("price_action", -0.5, 0.25))
            else:
                components.append(("price_action", 0.0, 0.25))

    return _weighted_combine(components)


# --- Internal helpers ---


def _weighted_combine(components: list[tuple[str, float, float]]) -> float:
    """Combine weighted components into a single score in [-1, +1]."""
    if not components:
        return 0.0
    total_weight = sum(w for _, _, w in components)
    weighted_sum = sum(v * w for _, v, w in components)
    return max(-1.0, min(1.0, weighted_sum / total_weight))


def _detect_macd_cross_decay(df: pd.DataFrame, decay_bars: int = 3) -> float:
    """Detect MACD crossover with linear decay over N bars.

    Golden cross: +0.5 decaying to 0 over decay_bars.
    Death cross: -0.5 decaying to 0 over decay_bars.
    """
    for lookback in range(decay_bars):
        idx = -(lookback + 1)
        prev_idx = idx - 1
        if abs(prev_idx) > len(df):
            break
        curr_macd = df.iloc[idx].get("macd")
        curr_sig = df.iloc[idx].get("macd_signal")
        prev_macd = df.iloc[prev_idx].get("macd")
        prev_sig = df.iloc[prev_idx].get("macd_signal")
        if not all(pd.notna(v) for v in (curr_macd, curr_sig, prev_macd, prev_sig)):
            continue
        decay_factor = 1.0 - (lookback / decay_bars)
        if prev_macd <= prev_sig and curr_macd > curr_sig:
            return 0.5 * decay_factor
        elif prev_macd >= prev_sig and curr_macd < curr_sig:
            return -0.5 * decay_factor
    return 0.0
