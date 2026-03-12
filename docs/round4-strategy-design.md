# Round 4: 전략 엔진 상세 설계서

> **작성자**: Quant Expert (Senior Quantitative Analyst)
> **작성일**: 2026-03-02
> **기반**: Round 2 요구사항서 + Round 3 TDR 합의
> **기술 스택**: Python 3.13, PostgreSQL 16 + TimescaleDB, pandas-ta, asyncio, FastAPI, LightGBM (P2)

---

## 목차

1. [설계 개요](#1-설계-개요)
2. [지표 파이프라인 설계](#2-지표-파이프라인-설계)
3. [스코어링 엔진 설계](#3-스코어링-엔진-설계)
4. [시그널 생성 파이프라인](#4-시그널-생성-파이프라인)
5. [리스크 엔진 설계](#5-리스크-엔진-설계)
6. [백테스트 하네스 설계](#6-백테스트-하네스-설계)
7. [ML 시그널 플러그인 인터페이스](#7-ml-시그널-플러그인-인터페이스)
8. [교차 도메인 계약](#8-교차-도메인-계약)

---

## 1. 설계 개요

### 1.1 모듈 구조

```
src/traderj/strategy/
├── __init__.py
├── indicators.py        # 지표 계산 파이프라인
├── normalizer.py        # Z-score 정규화 엔진
├── filters.py           # 스코어링 함수 (trend/momentum/volume/reversal/breakout/quick_momentum)
├── scoring.py           # TimeframeScore + combined 계산 (차등 가중치)
├── mtf.py               # MTF 집계 (WEIGHTED/MAJORITY/Daily Gate)
├── regime.py            # 시장 레짐 분류기
├── signal.py            # SignalGenerator (파이프라인 오케스트레이터)
├── macro.py             # 매크로 스코어러 (연속 함수)
├── risk.py              # 리스크 엔진 (ATR 기반 동적 관리)
├── plugins.py           # ScorePlugin Protocol + 레지스트리
└── backtest/
    ├── __init__.py
    ├── engine.py         # 이벤트 기반 백테스트 엔진
    ├── walkforward.py    # Walk-forward 최적화
    ├── metrics.py        # Sharpe/Sortino/Calmar/MDD 계산
    └── montecarlo.py     # Monte Carlo 시뮬레이션 (P2)
```

### 1.2 데이터 흐름 개요

```
OHLCV(DB) ──→ compute_indicators() ──→ normalize_scores() ──→ filter_scores()
                                                                    │
                                                            ┌───────┴───────┐
                                                            │ TimeframeScore │
                                                            └───────┬───────┘
                                                                    │
RegimeClassifier ──→ param_overrides ──→ aggregate_mtf() ──→ technical_score
                                                                    │
MacroScorer ────────────────────────────────────────→ macro_score ──┤
ScorePlugins (P2) ──────────────────────────────→ plugin_score ────┤
                                                                    │
                                                              final_score
                                                                    │
                                                    ┌───────────────┴───────────────┐
                                                    │ RiskEngine.evaluate()          │
                                                    │ → direction, position_size,    │
                                                    │   stop_loss, trailing_params   │
                                                    └───────────────┬───────────────┘
                                                                    │
                                                          SignalEvent → EventBus
```

---

## 2. 지표 파이프라인 설계

### 2.1 compute_indicators 함수

기존 bit-trader의 `compute_indicators(df, params)`를 확장한다. ATR, VWAP, CMF를 추가하고 Z-score 정규화 전처리 컬럼을 생성한다.

```python
# src/traderj/strategy/indicators.py

from dataclasses import dataclass
import pandas as pd
import pandas_ta as ta

@dataclass(frozen=True)
class IndicatorConfig:
    """지표 파라미터 — StrategyParams에서 추출."""
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
    atr_period: int = 14         # 신규 P0
    vwap_anchor: str = "D"       # 신규 P1 (일별 리셋)
    cmf_period: int = 20         # 신규 P1
    volume_ma_period: int = 20

def compute_indicators(
    df: pd.DataFrame,
    config: IndicatorConfig | None = None,
) -> pd.DataFrame:
    """OHLCV DataFrame에 기술 지표 컬럼을 추가한다.

    Args:
        df: columns=['open','high','low','close','volume','timestamp']
        config: 지표 파라미터

    Returns:
        df with added indicator columns. 원본 수정하지 않음 (copy).

    Required minimum rows: max(ema_long, 100) + atr_period = 214+ bars
    """
    cfg = config or IndicatorConfig()
    out = df.copy()

    # --- Trend ---
    out["ema_short"] = ta.ema(out["close"], length=cfg.ema_short)
    out["ema_medium"] = ta.ema(out["close"], length=cfg.ema_medium)
    out["ema_long"] = ta.ema(out["close"], length=cfg.ema_long)
    out["adx"] = ta.adx(out["high"], out["low"], out["close"], length=cfg.adx_period)["ADX_14"]
    out["dmp"] = ta.adx(out["high"], out["low"], out["close"], length=cfg.adx_period)["DMP_14"]
    out["dmn"] = ta.adx(out["high"], out["low"], out["close"], length=cfg.adx_period)["DMN_14"]

    # --- Volatility (P0 신규) ---
    out["atr"] = ta.atr(out["high"], out["low"], out["close"], length=cfg.atr_period)
    out["atr_pct"] = out["atr"] / out["close"]

    # --- Bollinger Bands ---
    bbands = ta.bbands(out["close"], length=cfg.bb_period, std=cfg.bb_std)
    out["bb_upper"] = bbands[f"BBU_{cfg.bb_period}_{cfg.bb_std}"]
    out["bb_lower"] = bbands[f"BBL_{cfg.bb_period}_{cfg.bb_std}"]
    out["bb_mid"] = bbands[f"BBM_{cfg.bb_period}_{cfg.bb_std}"]
    bb_range = out["bb_upper"] - out["bb_lower"]
    out["bb_pct"] = (out["close"] - out["bb_lower"]) / bb_range.replace(0, float("nan"))
    out["bb_width"] = bb_range / out["bb_mid"]

    # --- Momentum ---
    out["rsi"] = ta.rsi(out["close"], length=cfg.rsi_period)
    macd_result = ta.macd(out["close"], fast=cfg.macd_fast, slow=cfg.macd_slow, signal=cfg.macd_signal)
    out["macd"] = macd_result[f"MACD_{cfg.macd_fast}_{cfg.macd_slow}_{cfg.macd_signal}"]
    out["macd_signal"] = macd_result[f"MACDs_{cfg.macd_fast}_{cfg.macd_slow}_{cfg.macd_signal}"]
    out["macd_hist"] = macd_result[f"MACDh_{cfg.macd_fast}_{cfg.macd_slow}_{cfg.macd_signal}"]
    stoch = ta.stochrsi(out["close"], length=cfg.stoch_rsi_period, rsi_length=cfg.stoch_rsi_period,
                        k=cfg.stoch_smooth_k, d=cfg.stoch_smooth_d)
    out["stochrsi_k"] = stoch[f"STOCHRSIk_{cfg.stoch_rsi_period}_{cfg.stoch_rsi_period}_{cfg.stoch_smooth_k}_{cfg.stoch_smooth_d}"]
    out["stochrsi_d"] = stoch[f"STOCHRSId_{cfg.stoch_rsi_period}_{cfg.stoch_rsi_period}_{cfg.stoch_smooth_k}_{cfg.stoch_smooth_d}"]

    # --- Volume ---
    out["obv"] = ta.obv(out["close"], out["volume"])
    out["volume_ma"] = ta.sma(out["volume"], length=cfg.volume_ma_period)

    # --- P1 추가 지표 ---
    # CMF (Chaikin Money Flow)
    out["cmf"] = ta.cmf(out["high"], out["low"], out["close"], out["volume"], length=cfg.cmf_period)

    # VWAP (intraday, daily reset 기준)
    # 주의: VWAP은 intraday TF(15m, 1h)에서만 유의미. 4h/1d에서는 skip.
    # 호출 측에서 timeframe 확인 후 선택적으로 사용.

    # --- Z-score 전처리 컬럼 (normalizer.py에서 사용) ---
    # 원시값을 그대로 둠. normalizer가 lookback window 기반으로 z-score 계산.

    return out
```

### 2.2 Z-score 정규화 엔진

기존 bit-trader의 임의 스케일링 상수(×5, ×10, ×33)를 제거하고, 통계적으로 일관된 정규화를 적용한다.

```python
# src/traderj/strategy/normalizer.py

import numpy as np
import pandas as pd

DEFAULT_LOOKBACK = 100  # Z-score 계산용 롤링 윈도우

def z_score(
    series: pd.Series,
    lookback: int = DEFAULT_LOOKBACK,
) -> pd.Series:
    """롤링 Z-score를 계산한다.

    z = (x - mean_N) / std_N

    Args:
        series: 원시 값 시리즈
        lookback: 롤링 윈도우 크기 (bars)

    Returns:
        Z-score 시리즈. std=0인 경우 0.0 반환.
    """
    rolling_mean = series.rolling(window=lookback, min_periods=max(lookback // 2, 10)).mean()
    rolling_std = series.rolling(window=lookback, min_periods=max(lookback // 2, 10)).std()
    # std가 0이면 (변동 없음) z-score = 0
    return ((series - rolling_mean) / rolling_std.replace(0, float("nan"))).fillna(0.0)

def z_to_score(z: float | pd.Series, method: str = "tanh") -> float | pd.Series:
    """Z-score를 [-1, +1] 범위로 매핑한다.

    Args:
        z: Z-score 값 (또는 시리즈)
        method: "tanh" (부드러운 곡선) 또는 "clip" (선형 클리핑)

    Returns:
        [-1, +1] 범위의 정규화된 스코어
    """
    if method == "tanh":
        return np.tanh(z)  # z=1 → 0.76, z=2 → 0.96, z=3 → 1.00
    elif method == "clip":
        if isinstance(z, pd.Series):
            return z.clip(-3, 3) / 3.0
        return max(-1.0, min(1.0, z / 3.0))
    else:
        raise ValueError(f"Unknown method: {method}")

def normalize_indicators(df: pd.DataFrame, lookback: int = DEFAULT_LOOKBACK) -> pd.DataFrame:
    """지표 DataFrame에 Z-score 정규화 컬럼을 추가한다.

    기존 임의 상수를 대체하는 정규화 대상:
    - macd_hist  : 기존 (hist/close × 100 × 10) → z_score(macd_hist)
    - obv 변화율 : 기존 (obv_change × 5)         → z_score(obv_5bar_change)
    - roc 5-bar  : 기존 (roc × 33)              → z_score(roc_5bar)

    Returns:
        df with added z_* columns
    """
    out = df.copy()

    # MACD histogram Z-score
    if "macd_hist" in out.columns:
        out["z_macd_hist"] = z_to_score(z_score(out["macd_hist"], lookback))

    # OBV 5-bar 변화율 Z-score
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

    # ATR percentile (변동성 수준 정규화)
    if "atr_pct" in out.columns:
        out["z_atr_pct"] = z_to_score(z_score(out["atr_pct"], lookback))

    return out
```

### 2.3 지표 파이프라인 전체 흐름

```
OHLCV DataFrame (350+ bars)
    │
    ▼
compute_indicators(df, config)
    │ → ema_short/medium/long, adx, dmp, dmn
    │ → atr, atr_pct (P0 신규)
    │ → bb_upper/lower/mid/pct/width
    │ → rsi, macd/signal/hist, stochrsi_k/d
    │ → obv, volume_ma, cmf (P1)
    │
    ▼
normalize_indicators(df, lookback=100)
    │ → z_macd_hist, z_obv_change, z_roc_5
    │ → z_macd_accel, z_cmf, z_atr_pct
    │
    ▼
Ready for scoring functions
```

**최소 데이터 요구량**: 350 bars (= EMA 200 + Z-score lookback 100 + 50 버퍼)
- 기존 bit-trader: 250 bars
- 변경 사유: Z-score 정규화에 100-bar 롤링 윈도우 추가

---

## 3. 스코어링 엔진 설계

### 3.1 차등 가중치 스코어 결합

기존 bit-trader의 `TimeframeScore.combined = (trend + momentum + volume) / 3` 을 차등 가중치로 개선한다.

```python
# src/traderj/strategy/scoring.py

from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum

class ScoringMode(StrEnum):
    TREND_FOLLOW = "trend_follow"
    HYBRID = "hybrid"

@dataclass(frozen=True)
class ScoreWeights:
    """서브스코어 가중치. 합계 = 1.0 검증."""
    w1: float  # TREND_FOLLOW: trend,   HYBRID: reversal
    w2: float  # TREND_FOLLOW: momentum, HYBRID: quick_momentum
    w3: float  # TREND_FOLLOW: volume,   HYBRID: breakout

    def __post_init__(self):
        total = self.w1 + self.w2 + self.w3
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Score weights must sum to 1.0, got {total}")

# 기본값
TREND_FOLLOW_WEIGHTS = ScoreWeights(0.50, 0.30, 0.20)  # trend, momentum, volume
HYBRID_WEIGHTS = ScoreWeights(0.40, 0.40, 0.20)         # reversal, quick_mom, breakout

@dataclass
class TimeframeScore:
    """단일 타임프레임의 3개 서브스코어."""
    timeframe: str
    s1: float  # trend 또는 reversal
    s2: float  # momentum 또는 quick_momentum
    s3: float  # volume 또는 breakout

    def combined(self, weights: ScoreWeights) -> float:
        """차등 가중 합산. [-1, +1] 범위."""
        raw = self.s1 * weights.w1 + self.s2 * weights.w2 + self.s3 * weights.w3
        return max(-1.0, min(1.0, raw))

    def as_dict(self, weights: ScoreWeights) -> dict:
        """Signal.details용 직렬화."""
        return {
            "s1": round(self.s1, 4),
            "s2": round(self.s2, 4),
            "s3": round(self.s3, 4),
            "combined": round(self.combined(weights), 4),
            "weights": [weights.w1, weights.w2, weights.w3],
        }
```

### 3.2 개선된 스코어링 함수

기존 `filters.py`의 6개 함수를 Z-score 정규화 기반으로 개선한다. 핵심 변경사항만 기술한다.

#### trend_score 변경점

```python
def trend_score(df: pd.DataFrame) -> float:
    """추세 강도 스코어. [-1, +1]

    변경사항 (vs bit-trader):
    - BB %B 제거 (→ volume_score로 이동)
    - ADX 이진 판단 → 연속 스케일: adx_direction = (dmp - dmn) / (dmp + dmn) × adx_strength
    - 가중치: EMA alignment(0.40), Price vs EMA200(0.25), ADX direction(0.35)
    """
    last = df.iloc[-1]
    components = []

    # 1. EMA alignment (0.40)
    ema_s, ema_m, ema_l = last.get("ema_short"), last.get("ema_medium"), last.get("ema_long")
    if all(pd.notna(v) for v in (ema_s, ema_m, ema_l)):
        if ema_s > ema_m > ema_l:
            components.append(("ema_align", 1.0, 0.40))
        elif ema_s < ema_m < ema_l:
            components.append(("ema_align", -1.0, 0.40))
        elif ema_s > ema_m:
            components.append(("ema_align", 0.4, 0.40))
        elif ema_s < ema_m:
            components.append(("ema_align", -0.4, 0.40))
        else:
            components.append(("ema_align", 0.0, 0.40))

    # 2. Price vs EMA long (0.25) — 연속 스케일로 변경
    close, ema_long = last.get("close"), last.get("ema_long")
    if pd.notna(close) and pd.notna(ema_long) and ema_long > 0:
        distance = (close - ema_long) / ema_long  # 가격 대비 비율
        # tanh로 매핑: 2% 이상이면 ±0.76, 5% 이상이면 ±0.96
        price_score = float(np.tanh(distance / 0.03))
        components.append(("price_vs_ema200", price_score, 0.25))

    # 3. ADX direction (0.35) — 연속 스케일
    adx, dmp, dmn = last.get("adx"), last.get("dmp"), last.get("dmn")
    if all(pd.notna(v) for v in (adx, dmp, dmn)) and (dmp + dmn) > 0:
        di_ratio = (dmp - dmn) / (dmp + dmn)  # [-1, +1] 방향
        adx_strength = min(adx / 50.0, 1.0)   # 0~1 강도 (50 이상이면 1.0)
        adx_score = di_ratio * adx_strength
        components.append(("adx_direction", adx_score, 0.35))

    if not components:
        return 0.0

    total_weight = sum(w for _, _, w in components)
    weighted_sum = sum(v * w for _, v, w in components)
    return max(-1.0, min(1.0, weighted_sum / total_weight))
```

#### momentum_score 변경점

```python
def momentum_score(df: pd.DataFrame) -> float:
    """모멘텀 스코어. [-1, +1]

    변경사항 (vs bit-trader):
    - MACD hist: (hist/close×100×10) → z_macd_hist (Z-score 정규화)
    - MACD crossover: 이산 ±0.5 → 크로스 후 3-bar 감쇠
    - 가중치: RSI(0.30), MACD_z(0.30), MACD_cross(0.15), StochRSI(0.25)
    """
    last = df.iloc[-1]
    components = []

    # 1. RSI 정규화 (0.30) — 기존과 동일
    rsi = last.get("rsi")
    if pd.notna(rsi):
        components.append(("rsi", (rsi - 50) / 50 * 0.8, 0.30))

    # 2. MACD histogram Z-score (0.30) — 임의 상수 제거
    z_macd = last.get("z_macd_hist")
    if pd.notna(z_macd):
        components.append(("macd_z", float(z_macd), 0.30))

    # 3. MACD crossover with 3-bar decay (0.15)
    if len(df) >= 4:
        cross_signal = _detect_macd_cross_decay(df, decay_bars=3)
        components.append(("macd_cross", cross_signal, 0.15))

    # 4. StochRSI (0.25) — 기존과 동일
    stoch_k = last.get("stochrsi_k")
    stoch_d = last.get("stochrsi_d")
    if pd.notna(stoch_k) and pd.notna(stoch_d):
        stoch_avg = (stoch_k + stoch_d) / 2
        components.append(("stochrsi", (stoch_avg - 50) / 50 * 0.6, 0.25))

    if not components:
        return 0.0
    total_weight = sum(w for _, _, w in components)
    weighted_sum = sum(v * w for _, v, w in components)
    return max(-1.0, min(1.0, weighted_sum / total_weight))

def _detect_macd_cross_decay(df: pd.DataFrame, decay_bars: int = 3) -> float:
    """MACD 크로스오버를 감지하고 3-bar 감쇠를 적용한다.

    기존 bit-trader: 크로스 직후 1 bar에서만 ±0.5 → 다음 바에서 즉시 소멸
    개선: 크로스 후 3 bars에 걸쳐 선형 감쇠 (0.5 → 0.33 → 0.17 → 0)
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
            return 0.5 * decay_factor   # 골든 크로스
        elif prev_macd >= prev_sig and curr_macd < curr_sig:
            return -0.5 * decay_factor  # 데드 크로스
    return 0.0
```

#### volume_score 변경점

```python
def volume_score(df: pd.DataFrame) -> float:
    """거래량 확인 스코어. [-1, +1]

    변경사항 (vs bit-trader):
    - OBV: (obv_change × 5) → z_obv_change (Z-score 정규화)
    - BB %B 추가: trend_score에서 이동 (가격-변동성 확인용)
    - CMF 추가 (P1): OBV 보완
    - 가중치: Volume/MA(0.25), OBV_z(0.20), CMF(0.20), Price-Vol align(0.20), BB%B(0.15)
    """
    last = df.iloc[-1]
    components = []

    # 1. Volume/MA ratio (0.25) — 연속 스케일로 변경
    vol = last.get("volume")
    vol_ma = last.get("volume_ma")
    if pd.notna(vol) and pd.notna(vol_ma) and vol_ma > 0:
        ratio = vol / vol_ma
        # 연속 매핑: ratio 1.0 → 0.0, ratio 2.0 → +0.8, ratio 0.5 → -0.5
        vol_score = float(np.tanh((ratio - 1.0) * 1.5))
        components.append(("vol_ratio", vol_score, 0.25))

    # 2. OBV Z-score (0.20)
    z_obv = last.get("z_obv_change")
    if pd.notna(z_obv):
        components.append(("obv_z", float(z_obv), 0.20))

    # 3. CMF (0.20) — P1, 없으면 skip
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

    # 5. BB %B (0.15) — trend_score에서 이동
    bb_pct = last.get("bb_pct")
    if pd.notna(bb_pct):
        components.append(("bb_pct", (bb_pct - 0.5) * 0.6, 0.15))

    if not components:
        return 0.0
    total_weight = sum(w for _, _, w in components)
    weighted_sum = sum(v * w for _, v, w in components)
    return max(-1.0, min(1.0, weighted_sum / total_weight))
```

### 3.3 MTF 집계: MAJORITY 모드 + Daily Gate

```python
# src/traderj/strategy/mtf.py

from __future__ import annotations
from enum import StrEnum
from dataclasses import dataclass
import warnings

from traderj.strategy.scoring import TimeframeScore, ScoreWeights

class EntryMode(StrEnum):
    WEIGHTED = "weighted"
    MAJORITY = "majority"
    AND = "and"  # deprecated

@dataclass(frozen=True)
class DailyGateResult:
    """Daily Gate 판정 결과."""
    passed: bool
    ema_short: float  # 1d EMA20
    ema_medium: float  # 1d EMA50
    reason: str

def check_daily_gate(daily_df: dict | None) -> DailyGateResult:
    """1d EMA alignment으로 매수 허용 여부를 판정한다.

    규칙:
    - EMA20(1d) > EMA50(1d) → 매수 허용 (passed=True)
    - EMA20(1d) <= EMA50(1d) → 매수 차단 (passed=False)
    - 매도 신호는 항상 통과 (포지션 청산 보호)
    - daily_df가 None이면 gate 비활성 (passed=True)
    """
    if daily_df is None:
        return DailyGateResult(passed=True, ema_short=0, ema_medium=0, reason="gate_disabled")

    last = daily_df.iloc[-1]
    ema_s = last.get("ema_short", 0)
    ema_m = last.get("ema_medium", 0)

    if ema_s > ema_m:
        return DailyGateResult(passed=True, ema_short=ema_s, ema_medium=ema_m, reason="bullish_alignment")
    else:
        return DailyGateResult(passed=False, ema_short=ema_s, ema_medium=ema_m, reason="bearish_alignment")

def aggregate_mtf(
    scores: dict[str, TimeframeScore],
    weights: ScoreWeights,
    tf_weights: dict[str, float],  # {"15m": 0.2, "1h": 0.3, "4h": 0.5}
    entry_mode: EntryMode = EntryMode.WEIGHTED,
    buy_threshold: float = 0.15,
    majority_min: int = 2,
) -> float:
    """멀티 타임프레임 스코어를 단일 값으로 집계한다.

    Args:
        scores: TF별 TimeframeScore
        weights: 서브스코어 가중치 (ScoreWeights)
        tf_weights: TF별 가중치 (합계 = 1.0)
        entry_mode: WEIGHTED | MAJORITY | AND(deprecated)
        buy_threshold: MAJORITY 모드에서 TF 통과 기준
        majority_min: MAJORITY 모드에서 최소 통과 TF 수

    Returns:
        집계된 스코어 [-1, +1]
    """
    if entry_mode == EntryMode.AND:
        warnings.warn(
            "EntryMode.AND is deprecated. Use MAJORITY or WEIGHTED.",
            DeprecationWarning, stacklevel=2,
        )
        # AND 모드: 모든 TF가 threshold 통과해야 함
        for tf, tf_w in tf_weights.items():
            ts = scores.get(tf)
            if ts is None or ts.combined(weights) < buy_threshold:
                return 0.0

    if entry_mode == EntryMode.MAJORITY:
        # MAJORITY: majority_min개 이상의 TF가 threshold 통과
        passed_count = 0
        for tf in tf_weights:
            ts = scores.get(tf)
            if ts is not None and ts.combined(weights) >= buy_threshold:
                passed_count += 1
        if passed_count < majority_min:
            return 0.0
        # 통과한 경우 가중 평균으로 최종 스코어 계산

    # WEIGHTED 또는 MAJORITY 통과 후 → 가중 평균
    total_score = 0.0
    total_weight = 0.0
    for tf, tf_w in tf_weights.items():
        ts = scores.get(tf)
        if ts is None:
            continue
        total_score += ts.combined(weights) * tf_w
        total_weight += tf_w

    if total_weight == 0:
        return 0.0

    return max(-1.0, min(1.0, total_score / total_weight))
```

### 3.4 시장 레짐 분류기

```python
# src/traderj/strategy/regime.py

from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
import pandas as pd

class Regime(StrEnum):
    TRENDING_HIGH_VOL = "trending_high_vol"
    TRENDING_LOW_VOL = "trending_low_vol"
    RANGING_HIGH_VOL = "ranging_high_vol"
    RANGING_LOW_VOL = "ranging_low_vol"

@dataclass
class RegimeOverrides:
    """레짐별 파라미터 오버라이드."""
    buy_threshold_adj: float = 0.0    # threshold에 더하는 값
    sell_threshold_adj: float = 0.0
    target_risk_pct: float = 0.02     # ATR 기반 포지션 사이징의 target
    bb_std_override: float | None = None

# 레짐별 기본 오버라이드
REGIME_OVERRIDES: dict[Regime, RegimeOverrides] = {
    Regime.TRENDING_HIGH_VOL: RegimeOverrides(
        buy_threshold_adj=-0.03,   # threshold 낮춤 (추세 타기 쉽게)
        sell_threshold_adj=0.03,
        target_risk_pct=0.015,     # 포지션 축소
        bb_std_override=2.5,
    ),
    Regime.TRENDING_LOW_VOL: RegimeOverrides(
        buy_threshold_adj=-0.02,
        sell_threshold_adj=0.02,
        target_risk_pct=0.02,      # 정상
    ),
    Regime.RANGING_HIGH_VOL: RegimeOverrides(
        buy_threshold_adj=0.05,    # threshold 높임 (거래 자제)
        sell_threshold_adj=-0.05,
        target_risk_pct=0.01,      # 크게 축소
    ),
    Regime.RANGING_LOW_VOL: RegimeOverrides(
        buy_threshold_adj=-0.01,   # 약간 낮춤 (브레이크아웃 포착)
        sell_threshold_adj=0.01,
        target_risk_pct=0.025,     # 약간 확대
        bb_std_override=1.5,
    ),
}

@dataclass
class RegimeClassifier:
    """ATR + ADX 기반 4-레짐 분류기.

    히스테리시스: 레짐 변경은 3 bars 연속 새 레짐 조건 충족 시만 전환.
    """
    adx_threshold: float = 25.0    # trending vs ranging 경계
    vol_lookback: int = 30         # ATR 중앙값 계산 윈도우
    hysteresis_bars: int = 3       # 레짐 전환 확인 bars

    _current_regime: Regime = Regime.TRENDING_LOW_VOL  # 초기값
    _candidate_regime: Regime | None = None
    _candidate_count: int = 0

    def classify(self, df: pd.DataFrame) -> Regime:
        """현재 시장 레짐을 분류한다.

        Args:
            df: 지표가 계산된 DataFrame (adx, atr_pct 필수)

        Returns:
            현재 레짐 (히스테리시스 적용)
        """
        if df.empty or len(df) < self.vol_lookback:
            return self._current_regime

        last = df.iloc[-1]
        adx = last.get("adx", 0)
        atr_pct = last.get("atr_pct", 0)
        atr_median = df["atr_pct"].rolling(self.vol_lookback).median().iloc[-1]

        is_trending = adx > self.adx_threshold
        is_high_vol = atr_pct > atr_median

        if is_trending and is_high_vol:
            raw = Regime.TRENDING_HIGH_VOL
        elif is_trending:
            raw = Regime.TRENDING_LOW_VOL
        elif is_high_vol:
            raw = Regime.RANGING_HIGH_VOL
        else:
            raw = Regime.RANGING_LOW_VOL

        # 히스테리시스 적용
        if raw == self._current_regime:
            self._candidate_regime = None
            self._candidate_count = 0
        elif raw == self._candidate_regime:
            self._candidate_count += 1
            if self._candidate_count >= self.hysteresis_bars:
                self._current_regime = raw
                self._candidate_regime = None
                self._candidate_count = 0
        else:
            self._candidate_regime = raw
            self._candidate_count = 1

        return self._current_regime

    def get_overrides(self) -> RegimeOverrides:
        """현재 레짐의 파라미터 오버라이드를 반환한다."""
        return REGIME_OVERRIDES[self._current_regime]
```

---

## 4. 시그널 생성 파이프라인

### 4.1 SignalGenerator 설계

```python
# src/traderj/strategy/signal.py

from __future__ import annotations
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from structlog import get_logger

from traderj.strategy.indicators import compute_indicators, IndicatorConfig
from traderj.strategy.normalizer import normalize_indicators
from traderj.strategy.filters import trend_score, momentum_score, volume_score
from traderj.strategy.filters import reversal_score, breakout_score, quick_momentum_score
from traderj.strategy.scoring import (
    TimeframeScore, ScoreWeights, ScoringMode,
    TREND_FOLLOW_WEIGHTS, HYBRID_WEIGHTS,
)
from traderj.strategy.mtf import aggregate_mtf, check_daily_gate, EntryMode, DailyGateResult
from traderj.strategy.regime import RegimeClassifier, Regime, RegimeOverrides
from traderj.strategy.macro import compute_macro_score
from traderj.strategy.plugins import ScorePlugin

logger = get_logger()

class SignalDirection:
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"

@dataclass
class SignalResult:
    """신호 생성 결과."""
    timestamp: datetime
    symbol: str
    direction: str  # "buy" | "sell" | "hold"
    score: float
    details: dict[str, Any]

class SignalGenerator:
    """전략 신호 생성 파이프라인 오케스트레이터.

    파이프라인:
    1. 각 TF별 지표 계산 + Z-score 정규화
    2. 스코어링 함수 실행 → TimeframeScore
    3. 레짐 분류 → 파라미터 오버라이드
    4. Daily Gate 체크 (옵션)
    5. MTF 집계 → technical_score
    6. 매크로 스코어 통합
    7. 플러그인 스코어 통합 (P2)
    8. 최종 방향 결정
    """

    def __init__(
        self,
        strategy_id: str,
        scoring_mode: ScoringMode,
        entry_mode: EntryMode,
        score_weights: ScoreWeights | None = None,
        tf_weights: dict[str, float] | None = None,
        buy_threshold: float = 0.15,
        sell_threshold: float = -0.15,
        majority_min: int = 2,
        use_daily_gate: bool = False,
        macro_weight: float = 0.2,
        indicator_config: IndicatorConfig | None = None,
        regime_classifier: RegimeClassifier | None = None,
        plugins: list[tuple[ScorePlugin, float]] | None = None,
    ):
        self.strategy_id = strategy_id
        self.scoring_mode = scoring_mode
        self.entry_mode = entry_mode
        self.score_weights = score_weights or (
            TREND_FOLLOW_WEIGHTS if scoring_mode == ScoringMode.TREND_FOLLOW else HYBRID_WEIGHTS
        )
        self.tf_weights = tf_weights or {"1h": 0.3, "4h": 0.5}
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.majority_min = majority_min
        self.use_daily_gate = use_daily_gate
        self.macro_weight = macro_weight
        self.indicator_config = indicator_config or IndicatorConfig()
        self.regime_classifier = regime_classifier
        self.plugins = plugins or []

    def generate(
        self,
        ohlcv_by_tf: dict[str, pd.DataFrame],
        macro_snapshot: dict | None = None,
        symbol: str = "BTC/KRW",
    ) -> SignalResult:
        """신호를 생성한다.

        Args:
            ohlcv_by_tf: {"15m": df, "1h": df, "4h": df, "1d": df(gate용)}
            macro_snapshot: 매크로 데이터 (fear_greed, btc_dom 등)
            symbol: 거래쌍

        Returns:
            SignalResult
        """
        now = datetime.now(UTC)

        # Step 1-2: 각 TF별 지표 계산 + 스코어링
        tf_scores: dict[str, TimeframeScore] = {}
        tf_details: dict[str, dict] = {}

        for tf, df in ohlcv_by_tf.items():
            if tf == "1d" and self.use_daily_gate:
                continue  # 1d는 gate 전용
            if df.empty or tf not in self.tf_weights:
                continue

            df_ind = compute_indicators(df, self.indicator_config)
            df_norm = normalize_indicators(df_ind)

            if self.scoring_mode == ScoringMode.HYBRID:
                s1 = reversal_score(df_norm)
                s2 = quick_momentum_score(df_norm)
                s3 = breakout_score(df_norm)
            else:
                s1 = trend_score(df_norm)
                s2 = momentum_score(df_norm)
                s3 = volume_score(df_norm)

            ts = TimeframeScore(timeframe=tf, s1=s1, s2=s2, s3=s3)
            tf_scores[tf] = ts
            tf_details[tf] = ts.as_dict(self.score_weights)

        # Step 3: 레짐 분류
        regime: Regime | None = None
        regime_overrides: RegimeOverrides | None = None
        effective_buy_th = self.buy_threshold
        effective_sell_th = self.sell_threshold

        if self.regime_classifier and tf_scores:
            # 가장 긴 TF의 DataFrame에서 레짐 분류
            primary_tf = max(self.tf_weights.keys(), key=lambda t: _tf_to_minutes(t))
            if primary_tf in ohlcv_by_tf:
                df_primary = compute_indicators(ohlcv_by_tf[primary_tf], self.indicator_config)
                regime = self.regime_classifier.classify(df_primary)
                regime_overrides = self.regime_classifier.get_overrides()
                effective_buy_th += regime_overrides.buy_threshold_adj
                effective_sell_th += regime_overrides.sell_threshold_adj

        # Step 4: Daily Gate
        daily_gate: DailyGateResult | None = None
        if self.use_daily_gate and "1d" in ohlcv_by_tf:
            df_1d = compute_indicators(ohlcv_by_tf["1d"], self.indicator_config)
            daily_gate = check_daily_gate(df_1d)

        # Step 5: MTF 집계
        technical_score = aggregate_mtf(
            scores=tf_scores,
            weights=self.score_weights,
            tf_weights=self.tf_weights,
            entry_mode=self.entry_mode,
            buy_threshold=effective_buy_th,
            majority_min=self.majority_min,
        )

        # Step 6: 매크로 스코어
        macro_score = 0.0
        if macro_snapshot:
            macro_score = compute_macro_score(macro_snapshot)

        combined = technical_score * (1 - self.macro_weight) + macro_score * self.macro_weight

        # Step 7: 플러그인 (P2)
        plugin_scores: dict[str, float] = {}
        plugin_total_weight = sum(w for _, w in self.plugins)
        if self.plugins and plugin_total_weight > 0:
            base_weight = 1.0 - plugin_total_weight
            plugin_combined = 0.0
            for plugin, weight in self.plugins:
                # 가장 세밀한 TF의 DataFrame 사용
                finest_tf = min(self.tf_weights.keys(), key=lambda t: _tf_to_minutes(t))
                if finest_tf in ohlcv_by_tf:
                    df_feat = normalize_indicators(compute_indicators(ohlcv_by_tf[finest_tf]))
                    ps = plugin.score(df_feat)
                    plugin_scores[plugin.name] = ps
                    plugin_combined += ps * weight
            combined = combined * base_weight + plugin_combined

        # Step 8: 방향 결정
        if daily_gate and not daily_gate.passed and combined >= effective_buy_th:
            direction = SignalDirection.HOLD  # Gate가 매수 차단
        elif combined >= effective_buy_th:
            direction = SignalDirection.BUY
        elif combined <= effective_sell_th:
            direction = SignalDirection.SELL
        else:
            direction = SignalDirection.HOLD

        # Signal.details 구성
        details = {
            "strategy_id": self.strategy_id,
            "scoring_mode": self.scoring_mode.value,
            "entry_mode": self.entry_mode.value,
            "regime": regime.value if regime else None,
            "technical": round(technical_score, 4),
            "macro_raw": round(macro_score, 4),
            "score_weights": [self.score_weights.w1, self.score_weights.w2, self.score_weights.w3],
            "effective_thresholds": {
                "buy": round(effective_buy_th, 4),
                "sell": round(effective_sell_th, 4),
            },
            "daily_gate_status": daily_gate.reason if daily_gate else "disabled",
            "tf_scores": tf_details,
            "plugin_scores": plugin_scores if plugin_scores else None,
        }

        logger.info(
            "signal_generated",
            strategy_id=self.strategy_id,
            direction=direction,
            score=round(combined, 4),
            technical=round(technical_score, 4),
            macro=round(macro_score, 4),
            regime=regime.value if regime else None,
        )

        return SignalResult(
            timestamp=now,
            symbol=symbol,
            direction=direction,
            score=round(combined, 6),
            details=details,
        )

def _tf_to_minutes(tf: str) -> int:
    """타임프레임 문자열을 분 단위로 변환."""
    mapping = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
    return mapping.get(tf, 60)
```

### 4.2 이벤트 버스 연동

SignalGenerator가 생성한 결과를 EventBus에 발행하여 bot-developer 도메인(주문 실행, 로깅)과 dashboard-designer 도메인(실시간 UI)에 전달한다.

```python
# 이벤트 타입 정의 (아키텍처 설계서 §5.1 정본 — frozen dataclass, 대문자 enum)
# event_type 필드 불필요: 이벤트 클래스 자체가 타입 역할

@dataclass(frozen=True)
class SignalEvent:
    """전략 엔진 → EventBus로 발행하는 신호 이벤트."""
    timestamp: datetime
    strategy_id: str
    symbol: str
    direction: str        # BUY | SELL | HOLD (대문자 enum)
    score: float
    timeframe: str        # 기준 타임프레임
    components: dict      # {trend, momentum, volume, macro}
    details: dict = field(default_factory=dict)

@dataclass(frozen=True)
class RegimeChangeEvent:
    """레짐 전환 시 발행."""
    timestamp: datetime
    strategy_id: str
    old_regime: str
    new_regime: str
    overrides: dict = field(default_factory=dict)  # RegimeOverrides 직렬화

@dataclass(frozen=True)
class RiskStateEvent:
    """리스크 상태 변경 시 발행."""
    timestamp: datetime
    strategy_id: str
    consecutive_losses: int
    daily_pnl: float
    cooldown_until: str | None = None
    position_pct: float = 0.0
    atr_pct: float = 0.0
    volatility_status: str = "normal"  # "normal" | "warning" | "blocked"
```

---

## 5. 리스크 엔진 설계

### 5.1 ATR 기반 동적 리스크 관리

```python
# src/traderj/strategy/risk.py

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

from structlog import get_logger

logger = get_logger()

@dataclass(frozen=True)
class RiskConfig:
    """리스크 파라미터."""
    # 포지션 사이징
    max_position_pct: float = 0.20
    min_position_pct: float = 0.05
    target_risk_pct: float = 0.02      # 변동성 역비례 사이징 목표
    use_volatility_sizing: bool = True

    # 손절
    stop_loss_pct: float = 0.03        # 고정 손절 (fallback)
    atr_stop_multiplier: float = 2.0   # ATR 기반 손절 배수
    use_atr_stop: bool = True

    # 트레일링 스탑 (P1)
    use_trailing_stop: bool = True
    trail_activation_pct: float = 0.03  # 활성화 조건: +3% 이익
    trail_atr_multiplier: float = 2.5   # ATR 기반 트레일
    trail_mode: str = "atr"             # "atr" | "fixed"
    trail_fixed_pct: float = 0.02       # 고정 비율 트레일

    # 변동성 캡
    volatility_cap_pct: float = 0.08    # ATR > 8%면 진입 금지

    # 일일/연속 제한
    daily_max_loss_pct: float = 0.05
    max_consecutive_losses: int = 3
    cooldown_hours: int = 24
    min_order_krw: float = 5_000.0
    fee_rate: float = 0.0005

@dataclass
class RiskState:
    """DB에 영속화되는 리스크 상태."""
    strategy_id: str
    consecutive_losses: int = 0
    daily_pnl: float = 0.0
    daily_date: str = ""
    cooldown_until: str | None = None  # ISO8601
    total_trades: int = 0
    total_wins: int = 0
    last_updated: str = ""

class RiskStore(Protocol):
    """리스크 상태 영속화 인터페이스. bot-developer가 구현."""
    async def get_risk_state(self, strategy_id: str) -> RiskState | None: ...
    async def save_risk_state(self, state: RiskState) -> None: ...

@dataclass
class RiskDecision:
    """리스크 평가 결과."""
    allowed: bool
    reason: str
    position_size_krw: float = 0.0
    position_pct: float = 0.0
    stop_loss_price: float = 0.0
    atr_pct: float = 0.0
    volatility_status: str = "normal"  # "normal" | "warning" | "blocked"

class RiskEngine:
    """ATR 기반 동적 리스크 관리 엔진.

    기존 bit-trader RiskManager 대비 변경:
    1. ATR 기반 동적 손절 (고정 3% → entry - 2.0×ATR)
    2. 변동성 역비례 포지션 사이징 (고정 20% → target_risk / ATR_pct)
    3. 변동성 캡 (ATR > 8% → 진입 차단)
    4. DB 영속화 (인메모리 → write-through)
    5. 트레일링 스탑 (P1)
    """

    def __init__(self, config: RiskConfig, store: RiskStore, strategy_id: str):
        self.config = config
        self.store = store
        self.strategy_id = strategy_id
        self._state: RiskState | None = None  # 초기화 시 DB 로드

    async def initialize(self) -> None:
        """DB에서 리스크 상태를 로드한다. 없으면 기본값 생성."""
        self._state = await self.store.get_risk_state(self.strategy_id)
        if self._state is None:
            self._state = RiskState(strategy_id=self.strategy_id)
            await self._persist()
        # 만료된 쿨다운 해제
        if self._state.cooldown_until:
            cooldown_dt = datetime.fromisoformat(self._state.cooldown_until)
            if datetime.now(UTC) >= cooldown_dt:
                self._state.cooldown_until = None
                await self._persist()
        logger.info("risk_engine_initialized", strategy_id=self.strategy_id,
                     consecutive_losses=self._state.consecutive_losses)

    async def evaluate_buy(
        self,
        total_balance_krw: float,
        current_price: float,
        current_atr: float,
        existing_position_krw: float = 0.0,
    ) -> RiskDecision:
        """매수 허용 여부를 평가하고 포지션 크기/손절가를 계산한다."""
        assert self._state is not None, "RiskEngine not initialized"
        self._ensure_daily_reset()

        # 1. 쿨다운 체크
        if self._state.cooldown_until:
            cooldown_dt = datetime.fromisoformat(self._state.cooldown_until)
            if datetime.now(UTC) < cooldown_dt:
                remaining = (cooldown_dt - datetime.now(UTC)).total_seconds() / 3600
                return RiskDecision(allowed=False, reason=f"cooldown_active_{remaining:.1f}h")

        # 2. 일일 손실 한도 체크
        if total_balance_krw > 0:
            daily_loss_pct = abs(min(0, self._state.daily_pnl)) / total_balance_krw
            if daily_loss_pct >= self.config.daily_max_loss_pct:
                return RiskDecision(allowed=False, reason=f"daily_loss_limit_{daily_loss_pct:.1%}")

        # 3. 변동성 캡 체크
        atr_pct = current_atr / current_price if current_price > 0 else 0
        vol_status = "normal"
        if atr_pct > self.config.volatility_cap_pct:
            return RiskDecision(
                allowed=False,
                reason=f"volatility_cap_exceeded_{atr_pct:.1%}",
                atr_pct=atr_pct,
                volatility_status="blocked",
            )
        elif atr_pct > self.config.volatility_cap_pct * 0.75:
            vol_status = "warning"

        # 4. 포지션 사이징
        if self.config.use_volatility_sizing and atr_pct > 0:
            position_pct = self.config.target_risk_pct / atr_pct
            position_pct = max(self.config.min_position_pct,
                               min(self.config.max_position_pct, position_pct))
        else:
            position_pct = self.config.max_position_pct

        max_position_krw = total_balance_krw * position_pct
        available = max_position_krw - existing_position_krw
        if available <= self.config.min_order_krw:
            return RiskDecision(allowed=False, reason="max_position_reached")

        position_size = min(available, max_position_krw)
        position_size = max(position_size, self.config.min_order_krw)

        # 5. 손절가 계산
        if self.config.use_atr_stop:
            stop_loss = current_price - self.config.atr_stop_multiplier * current_atr
        else:
            stop_loss = current_price * (1 - self.config.stop_loss_pct)

        return RiskDecision(
            allowed=True,
            reason="ok",
            position_size_krw=position_size,
            position_pct=position_pct,
            stop_loss_price=stop_loss,
            atr_pct=atr_pct,
            volatility_status=vol_status,
        )

    async def record_trade_result(self, pnl: float) -> None:
        """거래 결과를 기록한다. Write-through로 DB 영속화."""
        assert self._state is not None
        self._ensure_daily_reset()
        self._state.daily_pnl += pnl
        self._state.total_trades += 1

        if pnl < 0:
            self._state.consecutive_losses += 1
            if self._state.consecutive_losses >= self.config.max_consecutive_losses:
                cooldown = datetime.now(UTC) + timedelta(hours=self.config.cooldown_hours)
                self._state.cooldown_until = cooldown.isoformat()
                logger.warning("cooldown_activated",
                               consecutive_losses=self._state.consecutive_losses)
        else:
            self._state.consecutive_losses = 0
            self._state.total_wins += 1

        await self._persist()

    def calculate_trailing_stop(
        self,
        entry_price: float,
        highest_since_entry: float,
        current_atr: float,
    ) -> float | None:
        """트레일링 스탑 가격을 계산한다.

        Returns:
            트레일 스탑 가격. 미활성화면 None.
        """
        if not self.config.use_trailing_stop:
            return None

        unrealized_pct = (highest_since_entry - entry_price) / entry_price
        if unrealized_pct < self.config.trail_activation_pct:
            return None  # 아직 활성화 조건 미달

        if self.config.trail_mode == "atr":
            trail_stop = highest_since_entry - self.config.trail_atr_multiplier * current_atr
        else:  # fixed
            trail_stop = highest_since_entry * (1 - self.config.trail_fixed_pct)

        return trail_stop

    def _ensure_daily_reset(self) -> None:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        if self._state and self._state.daily_date != today:
            self._state.daily_pnl = 0.0
            self._state.daily_date = today

    async def _persist(self) -> None:
        """상태를 DB에 영속화한다. 실패 시 fallback."""
        if self._state is None:
            return
        self._state.last_updated = datetime.now(UTC).isoformat()
        try:
            await self.store.save_risk_state(self._state)
        except Exception:
            logger.error("risk_state_persist_failed", strategy_id=self.strategy_id, exc_info=True)
            # fallback: 인메모리 상태 유지, 텔레그램 알림 트리거
```

### 5.2 risk_state DB 스키마 (PostgreSQL + TimescaleDB)

```sql
-- migrations/003_risk_state.sql

CREATE TABLE IF NOT EXISTS risk_state (
    strategy_id TEXT PRIMARY KEY,
    consecutive_losses INTEGER NOT NULL DEFAULT 0,
    daily_pnl DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    daily_date TEXT NOT NULL DEFAULT '',
    cooldown_until TIMESTAMPTZ,
    total_trades INTEGER NOT NULL DEFAULT 0,
    total_wins INTEGER NOT NULL DEFAULT 0,
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 인덱스: strategy_id는 PK이므로 자동
CREATE INDEX IF NOT EXISTS idx_risk_state_updated ON risk_state(last_updated);
```

---

## 6. 백테스트 하네스 설계

### 6.1 이벤트 기반 백테스트 엔진

```python
# src/traderj/strategy/backtest/engine.py

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from traderj.strategy.signal import SignalGenerator, SignalResult
from traderj.strategy.risk import RiskConfig, RiskDecision
from traderj.strategy.backtest.metrics import compute_metrics, BacktestMetrics

@dataclass
class BacktestConfig:
    """백테스트 설정."""
    initial_balance: float = 10_000_000  # KRW
    fee_rate: float = 0.0005
    slippage_bps: float = 2.0   # basis points (0.02%)
    position_pct: float = 0.20  # fallback (ATR 사이징 비활성화 시)
    use_atr_sizing: bool = True
    risk_config: RiskConfig = field(default_factory=RiskConfig)

@dataclass
class Trade:
    """단일 거래 기록."""
    entry_time: datetime
    exit_time: datetime | None = None
    direction: str = "long"
    entry_price: float = 0.0
    exit_price: float = 0.0
    position_size_krw: float = 0.0
    pnl_krw: float = 0.0
    pnl_pct: float = 0.0
    exit_reason: str = ""  # "signal" | "stop_loss" | "trailing_stop" | "eod"
    fees: float = 0.0

@dataclass
class EquityPoint:
    """Equity curve 데이터 포인트."""
    timestamp: datetime
    equity: float
    drawdown: float
    position_value: float  # 미실현 포지션 가치

@dataclass
class BacktestResult:
    """백테스트 전체 결과."""
    strategy_id: str
    config: BacktestConfig
    period_start: datetime
    period_end: datetime
    metrics: BacktestMetrics
    trades: list[Trade]
    equity_curve: list[EquityPoint]
    signals_generated: int
    params_hash: str = ""

class BacktestEngine:
    """이벤트 기반 bar-by-bar 백테스트 엔진.

    기존 bit-trader의 run_backtest()를 재설계:
    - Equity curve 기반 MDD (매 bar에서 unrealized PnL 포함)
    - ATR 기반 동적 손절/포지션 사이징
    - 트레일링 스탑
    - 슬리피지 모델링
    - 트랜잭션 비용
    """

    def __init__(self, signal_gen: SignalGenerator, config: BacktestConfig):
        self.signal_gen = signal_gen
        self.config = config

    def run(
        self,
        ohlcv_by_tf: dict[str, pd.DataFrame],
        macro_snapshots: list[dict] | None = None,
    ) -> BacktestResult:
        """백테스트를 실행한다.

        bar-by-bar 시뮬레이션:
        1. 현재 bar의 OHLCV 윈도우 추출
        2. 신호 생성
        3. 기존 포지션 체크 (손절, 트레일링 스탑)
        4. 신호에 따라 진입/청산
        5. Equity 업데이트

        Args:
            ohlcv_by_tf: 전체 기간 OHLCV (TF별)
            macro_snapshots: 시간순 매크로 데이터 (선택)

        Returns:
            BacktestResult
        """
        # 가장 세밀한 TF를 기준 시간축으로 사용
        primary_tf = min(self.signal_gen.tf_weights.keys(), key=_tf_to_minutes)
        primary_df = ohlcv_by_tf[primary_tf]
        window_size = 350  # 최소 데이터 요구량

        balance = self.config.initial_balance
        trades: list[Trade] = []
        equity_curve: list[EquityPoint] = []
        signals_count = 0
        current_trade: Trade | None = None
        highest_since_entry = 0.0
        peak_equity = balance

        for i in range(window_size, len(primary_df)):
            bar = primary_df.iloc[i]
            bar_time = bar["timestamp"] if "timestamp" in bar.index else bar.name
            current_price = bar["close"]

            # 현재까지의 윈도우로 각 TF OHLCV 추출
            windows = self._extract_windows(ohlcv_by_tf, bar_time, window_size)

            # 신호 생성
            macro = self._get_macro_at(macro_snapshots, bar_time)
            signal = self.signal_gen.generate(windows, macro)
            signals_count += 1

            # ATR 추출
            current_atr = self._get_current_atr(windows, primary_tf)

            # 기존 포지션 체크
            if current_trade is not None:
                highest_since_entry = max(highest_since_entry, bar["high"])

                # 손절 체크
                if current_price <= current_trade.stop_loss_price:
                    self._close_trade(current_trade, current_price, bar_time, "stop_loss")
                    balance += current_trade.pnl_krw - current_trade.fees
                    trades.append(current_trade)
                    current_trade = None

                # 트레일링 스탑 체크
                elif self.config.risk_config.use_trailing_stop:
                    trail = self._calculate_trail(
                        current_trade.entry_price, highest_since_entry, current_atr)
                    if trail and current_price <= trail:
                        self._close_trade(current_trade, current_price, bar_time, "trailing_stop")
                        balance += current_trade.pnl_krw - current_trade.fees
                        trades.append(current_trade)
                        current_trade = None

                # 매도 신호 체크
                elif signal.direction == "sell":
                    self._close_trade(current_trade, current_price, bar_time, "signal")
                    balance += current_trade.pnl_krw - current_trade.fees
                    trades.append(current_trade)
                    current_trade = None

            # 매수 신호 처리
            if current_trade is None and signal.direction == "buy":
                position_size = self._calculate_position(balance, current_price, current_atr)
                if position_size >= self.config.risk_config.min_order_krw:
                    entry_price = current_price * (1 + self.config.slippage_bps / 10000)
                    stop_loss = self._calculate_stop_loss(entry_price, current_atr)
                    current_trade = Trade(
                        entry_time=bar_time,
                        entry_price=entry_price,
                        position_size_krw=position_size,
                    )
                    current_trade.stop_loss_price = stop_loss
                    balance -= position_size
                    highest_since_entry = entry_price

            # Equity 업데이트
            unrealized = 0.0
            if current_trade is not None:
                unrealized = current_trade.position_size_krw * (
                    current_price / current_trade.entry_price - 1)
            total_equity = balance + (current_trade.position_size_krw + unrealized if current_trade else 0)
            peak_equity = max(peak_equity, total_equity)
            drawdown = (peak_equity - total_equity) / peak_equity if peak_equity > 0 else 0

            equity_curve.append(EquityPoint(
                timestamp=bar_time,
                equity=total_equity,
                drawdown=drawdown,
                position_value=unrealized,
            ))

        # 미청산 포지션 강제 청산
        if current_trade is not None:
            final_price = primary_df.iloc[-1]["close"]
            self._close_trade(current_trade, final_price, primary_df.iloc[-1].name, "end_of_data")
            balance += current_trade.pnl_krw - current_trade.fees
            trades.append(current_trade)

        metrics = compute_metrics(
            trades=trades,
            equity_curve=equity_curve,
            initial_balance=self.config.initial_balance,
        )

        return BacktestResult(
            strategy_id=self.signal_gen.strategy_id,
            config=self.config,
            period_start=primary_df.iloc[window_size]["timestamp"],
            period_end=primary_df.iloc[-1]["timestamp"],
            metrics=metrics,
            trades=trades,
            equity_curve=equity_curve,
            signals_generated=signals_count,
        )

    # --- 내부 헬퍼 (시그니처만 정의) ---

    def _extract_windows(self, ohlcv_by_tf, bar_time, window_size) -> dict[str, pd.DataFrame]:
        """bar_time 기준 각 TF의 윈도우를 추출한다."""
        ...

    def _get_macro_at(self, snapshots, bar_time) -> dict | None:
        """bar_time에 해당하는 매크로 데이터를 찾는다."""
        ...

    def _get_current_atr(self, windows, tf) -> float:
        """현재 ATR 값을 추출한다."""
        ...

    def _calculate_position(self, balance, price, atr) -> float:
        """ATR 기반 포지션 크기를 계산한다."""
        ...

    def _calculate_stop_loss(self, entry_price, atr) -> float:
        """ATR 기반 손절가를 계산한다."""
        ...

    def _calculate_trail(self, entry_price, highest, atr) -> float | None:
        """트레일링 스탑 가격을 계산한다."""
        ...

    def _close_trade(self, trade, exit_price, exit_time, reason) -> None:
        """포지션을 청산하고 PnL을 계산한다."""
        exit_price_adj = exit_price * (1 - self.config.slippage_bps / 10000)
        trade.exit_time = exit_time
        trade.exit_price = exit_price_adj
        trade.exit_reason = reason
        trade.pnl_pct = (exit_price_adj / trade.entry_price) - 1
        trade.pnl_krw = trade.position_size_krw * trade.pnl_pct
        trade.fees = (trade.position_size_krw + trade.position_size_krw + trade.pnl_krw) * self.config.fee_rate
```

### 6.2 성과 지표 계산

```python
# src/traderj/strategy/backtest/metrics.py

from __future__ import annotations
from dataclasses import dataclass
import math

@dataclass
class BacktestMetrics:
    """백테스트 성과 지표."""
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    profit_factor: float
    max_drawdown: float          # equity curve 기반 (unrealized 포함)
    max_drawdown_realized: float  # trade-only
    win_rate: float
    total_trades: int
    avg_win_pct: float
    avg_loss_pct: float
    avg_holding_bars: int
    expectancy: float            # 평균 거래당 기대 수익률

def compute_metrics(
    trades: list,
    equity_curve: list,
    initial_balance: float,
    risk_free_rate: float = 0.035,  # 연 3.5%
    periods_per_year: float = 365 * 6,  # 4h 기준
) -> BacktestMetrics:
    """거래 내역과 equity curve에서 성과 지표를 계산한다.

    Sharpe = (R_ann - Rf) / σ_ann
    Sortino = (R_ann - Rf) / σ_downside_ann
    Calmar = R_ann / MaxDD
    Profit Factor = Σ(wins) / Σ(losses)
    Expectancy = win_rate × avg_win - (1 - win_rate) × avg_loss
    """
    if not trades:
        return BacktestMetrics(
            total_return=0, annualized_return=0, sharpe_ratio=0,
            sortino_ratio=0, calmar_ratio=0, profit_factor=0,
            max_drawdown=0, max_drawdown_realized=0, win_rate=0,
            total_trades=0, avg_win_pct=0, avg_loss_pct=0,
            avg_holding_bars=0, expectancy=0,
        )

    # 기본 지표
    final_equity = equity_curve[-1].equity if equity_curve else initial_balance
    total_return = (final_equity - initial_balance) / initial_balance

    # 연환산
    n_bars = len(equity_curve)
    years = n_bars / periods_per_year
    annualized_return = (1 + total_return) ** (1 / max(years, 0.01)) - 1 if years > 0 else 0

    # 수익률 시리즈 (bar-by-bar)
    returns = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1].equity
        curr = equity_curve[i].equity
        returns.append((curr - prev) / prev if prev > 0 else 0)

    # Sharpe
    if returns:
        mean_r = sum(returns) / len(returns)
        std_r = (sum((r - mean_r) ** 2 for r in returns) / len(returns)) ** 0.5
        ann_factor = math.sqrt(periods_per_year)
        sharpe = ((mean_r * periods_per_year - risk_free_rate) /
                  (std_r * ann_factor)) if std_r > 0 else 0
    else:
        sharpe = 0

    # Sortino
    downside = [r for r in returns if r < 0]
    if downside:
        downside_std = (sum(r ** 2 for r in downside) / len(returns)) ** 0.5
        ann_downside = downside_std * math.sqrt(periods_per_year)
        sortino = (annualized_return - risk_free_rate) / ann_downside if ann_downside > 0 else 0
    else:
        sortino = float("inf") if annualized_return > risk_free_rate else 0

    # Max Drawdown (equity curve)
    max_dd = max(p.drawdown for p in equity_curve) if equity_curve else 0

    # Calmar
    calmar = annualized_return / max_dd if max_dd > 0 else 0

    # Trade 기반 지표
    wins = [t for t in trades if t.pnl_pct > 0]
    losses = [t for t in trades if t.pnl_pct <= 0]
    win_rate = len(wins) / len(trades) if trades else 0
    avg_win = sum(t.pnl_pct for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t.pnl_pct for t in losses) / len(losses) if losses else 0
    gross_profit = sum(t.pnl_krw for t in wins)
    gross_loss = abs(sum(t.pnl_krw for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    expectancy = win_rate * avg_win - (1 - win_rate) * abs(avg_loss)

    return BacktestMetrics(
        total_return=total_return,
        annualized_return=annualized_return,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        calmar_ratio=calmar,
        profit_factor=profit_factor,
        max_drawdown=max_dd,
        max_drawdown_realized=_trade_only_mdd(trades, initial_balance),
        win_rate=win_rate,
        total_trades=len(trades),
        avg_win_pct=avg_win,
        avg_loss_pct=avg_loss,
        avg_holding_bars=0,  # 구현 시 bar 간격으로 계산
        expectancy=expectancy,
    )

def _trade_only_mdd(trades, initial_balance) -> float:
    """거래 시점만의 realized MDD."""
    equity = initial_balance
    peak = equity
    max_dd = 0.0
    for t in trades:
        equity += t.pnl_krw
        peak = max(peak, equity)
        dd = (peak - equity) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)
    return max_dd
```

### 6.3 Walk-Forward 최적화

```python
# src/traderj/strategy/backtest/walkforward.py

from __future__ import annotations
from dataclasses import dataclass

@dataclass
class WalkForwardWindow:
    """단일 walk-forward 윈도우 결과."""
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    is_return: float      # In-Sample 수익률
    oos_return: float     # Out-of-Sample 수익률
    oos_sharpe: float
    oos_efficiency: float  # oos_return / is_return
    best_params: dict     # 최적 파라미터

@dataclass
class WalkForwardResult:
    """Walk-forward 전체 결과."""
    windows: list[WalkForwardWindow]
    avg_oos_efficiency: float
    avg_oos_sharpe: float
    passed: bool  # avg_oos_efficiency >= 0.5

class WalkForwardOptimizer:
    """Walk-forward 최적화 프레임워크.

    슬라이딩 윈도우:
    - train_months=6, test_months=2
    - 2년 데이터 → 약 9개 윈도우
    - 각 윈도우에서 threshold, score_weights 최적화
    - OOS 효율: oos_return / is_return >= 0.5 → 통과

    최적화 대상 파라미터:
    - buy_threshold: [0.05, 0.10, 0.15, 0.20, 0.25]
    - sell_threshold: [-0.05, -0.10, -0.15, -0.20, -0.25]
    - score_weights.w1: [0.35, 0.40, 0.45, 0.50, 0.55]
    """

    def __init__(
        self,
        train_months: int = 6,
        test_months: int = 2,
        slide_months: int = 2,  # 슬라이드 간격
    ):
        self.train_months = train_months
        self.test_months = test_months
        self.slide_months = slide_months

    def run(self, ohlcv_by_tf: dict, macro: list | None = None) -> WalkForwardResult:
        """Walk-forward 최적화를 실행한다.

        1. 전체 기간을 train+test 윈도우로 분할
        2. 각 train 구간에서 그리드 서치로 최적 파라미터 탐색
        3. 해당 파라미터로 test 구간 성과 측정
        4. OOS 효율 계산
        """
        # 구현 시 BacktestEngine 인스턴스를 파라미터별로 재사용
        ...
```

---

## 7. ML 시그널 플러그인 인터페이스

### 7.1 ScorePlugin Protocol (P2)

```python
# src/traderj/strategy/plugins.py

from __future__ import annotations
from typing import Protocol, runtime_checkable
import pandas as pd

@runtime_checkable
class ScorePlugin(Protocol):
    """ML/외부 신호 플러그인 인터페이스.

    구현 요구사항:
    - score() 반환값은 반드시 [-1, +1] 범위
    - required_features()의 컬럼이 입력 DataFrame에 존재해야 함
    - 추론 지연 < 100ms
    """

    @property
    def name(self) -> str:
        """플러그인 고유 이름."""
        ...

    def score(self, features: pd.DataFrame) -> float:
        """정규화된 DataFrame에서 스코어를 계산한다.

        Args:
            features: normalize_indicators() 출력 DataFrame

        Returns:
            [-1, +1] 범위의 스코어
        """
        ...

    def required_features(self) -> list[str]:
        """필요한 feature 컬럼 목록."""
        ...

class PluginRegistry:
    """플러그인 관리 레지스트리."""

    def __init__(self):
        self._plugins: dict[str, tuple[ScorePlugin, float]] = {}

    def register(self, plugin: ScorePlugin, weight: float) -> None:
        """플러그인을 등록한다. weight는 최종 스코어에서의 가중치."""
        if not 0 < weight < 1:
            raise ValueError(f"Plugin weight must be (0, 1), got {weight}")
        self._plugins[plugin.name] = (plugin, weight)

    def get_all(self) -> list[tuple[ScorePlugin, float]]:
        return list(self._plugins.values())

    def total_weight(self) -> float:
        return sum(w for _, w in self._plugins.values())
```

### 7.2 LightGBM 플러그인 예시 (P2 구현 시)

```python
# 참조용 설계. P2 단계에서 구현.

class LightGBMPlugin:
    """LightGBM 기반 방향 예측 플러그인.

    Features: rsi, z_macd_hist, atr_pct, volume_ratio, bb_pct, adx, cmf
    Target: 다음 4h 가격 방향 (up=1, down=-1, neutral=0)
    학습: Walk-forward 6개월 학습 → 2개월 예측
    """
    name: str = "lgbm_direction"
    model_path: str = "data/models/{strategy_id}/lgbm_latest.pkl"

    def score(self, features: pd.DataFrame) -> float:
        """LightGBM 예측 확률을 [-1, +1] 스코어로 변환."""
        # proba[up] - proba[down] → [-1, +1]
        ...

    def required_features(self) -> list[str]:
        return ["rsi", "z_macd_hist", "atr_pct", "bb_pct", "adx", "z_cmf"]
```

---

## 8. 교차 도메인 계약

### 8.1 전략 → bot-developer (아키텍처 도메인)

#### EventBus 이벤트 타입 (전략 도메인 발행/소비 — 전체 13개 중)

> 전체 이벤트 목록은 아키텍처 설계서 §5.1 참조 (13개 이벤트)

| 이벤트 | 발행자 | 소비자 | 페이로드 | 빈도 |
|--------|--------|--------|----------|------|
| `SignalEvent` | SignalGenerator | ExecutionEngine, Dashboard WS | direction, score, timeframe, components, details | 전략별 15m~1h |
| `RegimeChangeEvent` | RegimeClassifier | Logger, Dashboard WS | old/new regime, overrides | 이벤트 기반 |
| `RiskStateEvent` | RiskEngine | Dashboard WS, TelegramNotifier | state snapshot | 상태 변경 시 |
| `MarketDataEvent` | DataCollector | SignalGenerator | symbol, ohlcv_by_tf dict | 수집 완료 시 |
| `OHLCVUpdateEvent` | Scheduler | StrategyEngine | symbol, timeframe, candles[] | 스케줄 기반 |
| `MarketTickEvent` | ExchangeWS | RiskManager, PositionManager | price, bid, ask, volume_24h | 실시간 |

#### DataStore Protocol

```python
class StrategyDataStore(Protocol):
    """전략 엔진이 요구하는 데이터 접근 인터페이스.
    아키텍처 DataStore Protocol (§6.1)과 리턴 타입 통일.
    """

    async def get_candles(
        self, symbol: str, timeframe: str, limit: int = 350,
    ) -> list["Candle"]:
        """최근 N개 캔들을 조회한다.
        전략 엔진 내부에서 pd.DataFrame(candles) 변환하여 사용.
        """
        ...

    async def get_macro_snapshot(self) -> dict | None:
        """최신 매크로 데이터를 조회한다."""
        ...

    async def save_signal(self, signal: SignalResult) -> None:
        """신호를 저장한다."""
        ...

    async def get_risk_state(self, strategy_id: str) -> RiskState | None: ...
    async def save_risk_state(self, state: RiskState) -> None: ...

    async def save_backtest_result(self, result: BacktestResult) -> None:
        """백테스트 결과를 저장한다 (P1)."""
        ...
```

#### DB 스키마 요구사항

```sql
-- 전략 도메인이 정의, bot-developer가 마이그레이션 적용

-- P0: risk_state (§5.2 참조)
-- P1: backtest_results
CREATE TABLE IF NOT EXISTS backtest_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id TEXT NOT NULL,
    params_hash TEXT NOT NULL,
    config_json JSONB NOT NULL,
    metrics_json JSONB NOT NULL,
    equity_curve_json JSONB,
    trades_json JSONB,
    walk_forward_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_bt_strategy ON backtest_results(strategy_id);
CREATE INDEX idx_bt_created ON backtest_results(created_at DESC);

-- P1: macro 확장
ALTER TABLE macro_snapshots ADD COLUMN IF NOT EXISTS funding_rate DOUBLE PRECISION;
ALTER TABLE macro_snapshots ADD COLUMN IF NOT EXISTS btc_dom_7d_change DOUBLE PRECISION;
```

### 8.2 전략 → dashboard-designer (대시보드 도메인)

#### Signal.details JSON 스키마 (최종)

```json
{
  "strategy_id": "STR-005",
  "scoring_mode": "trend_follow",
  "entry_mode": "weighted",
  "regime": "trending_low_vol",
  "technical": 0.185,
  "macro_raw": -0.084,
  "score_weights": [0.50, 0.30, 0.20],
  "effective_thresholds": {
    "buy": 0.13,
    "sell": -0.17
  },
  "daily_gate_status": "pass",
  "tf_scores": {
    "15m": {
      "s1": 0.35, "s2": 0.22, "s3": 0.15,
      "combined": 0.275,
      "weights": [0.50, 0.30, 0.20]
    },
    "1h": { "s1": 0.28, "s2": 0.31, "s3": 0.08, "combined": 0.249, "weights": [0.50, 0.30, 0.20] },
    "4h": { "s1": 0.42, "s2": 0.18, "s3": 0.22, "combined": 0.308, "weights": [0.50, 0.30, 0.20] }
  },
  "risk_state": {
    "position_pct": 0.15,
    "stop_loss_price": 62500000,
    "atr_pct": 0.048,
    "volatility_status": "normal"
  },
  "plugin_scores": null
}
```

#### 대시보드 데이터 뷰 요구사항

| # | 뷰 | 데이터 필드 | P-Level |
|---|------|-----------|---------|
| 1 | 전략 현황 카드 | strategy_id, scoring_mode, entry_mode, regime, 최근 score | P0 |
| 2 | 스코어 분해 바 차트 | tf_scores (TF별 s1/s2/s3 스택 바) | P0 |
| 3 | 리스크 상태 패널 | consecutive_losses, daily_pnl, cooldown, atr_pct, position_pct | P0 |
| 4 | 레짐 타임라인 | 시간×레짐(4색 밴드) + 현재 배지 | P1 |
| 5 | 백테스트 비교 테이블 | Sharpe/Sortino/Calmar/Return/MDD/Trades/WinRate | P1 |
| 6 | Equity Curve 차트 | 누적 수익 곡선 + drawdown 영역 | P1 |
| 7 | 매크로 분해 | 컴포넌트별 게이지 + 시그모이드 곡선 | P1 |

#### 실시간 업데이트 주기

| 데이터 | 주기 | 전달 방식 |
|--------|------|----------|
| 신호 점수 | 전략별 (15m~1h) | WebSocket `/ws/signals` |
| 리스크 상태 | 이벤트 기반 | WebSocket `/ws/risk` |
| 레짐 변경 | 이벤트 기반 | WebSocket `/ws/regime` |
| 현재 가격 | 1초 | WebSocket `/ws/prices` |

---

## 부록: 전략 프리셋 재구성표

TDR 확정 후 최종 프리셋 정의:

| 프리셋 | 모드 | 엔트리 | TF 가중치 | BuyTh | SellTh | DailyGate | 비고 |
|--------|------|--------|----------|-------|--------|-----------|------|
| **default** | TREND_FOLLOW | WEIGHTED | 15m(0.2)+1h(0.3)+4h(0.5) | 0.15 | -0.15 | No | = STR-005 기반 |
| **STR-001** | TREND_FOLLOW | WEIGHTED | 4h(0.60)+1h(0.40) | 0.15 | -0.15 | Yes | 1d→gate, AND→WEIGHTED |
| **STR-002** | TREND_FOLLOW | MAJORITY(2) | 4h(0.55)+1h(0.45) | 0.12 | -0.12 | No | AND→MAJORITY |
| **STR-003** | TREND_FOLLOW | WEIGHTED | 1h(0.35)+4h(0.65) | 0.12 | -0.12 | No | 1d 제거, th 하향 |
| **STR-004** | HYBRID | WEIGHTED | 1h(1.0) | 0.15 | -0.15 | No | score_weights 0.40/0.40/0.20 |
| **STR-005** | TREND_FOLLOW | WEIGHTED | 15m(0.2)+1h(0.3)+4h(0.5) | 0.15 | -0.15 | No | threshold 0.20→0.15 |
| **STR-006** | HYBRID | WEIGHTED | 15m(0.25)+1h(0.45)+4h(0.30) | 0.15 | -0.15 | Yes | 15m↓, 4h 추가, trend_filter |

score_weights 기본값:
- TREND_FOLLOW: `ScoreWeights(0.50, 0.30, 0.20)` — trend, momentum, volume
- HYBRID: `ScoreWeights(0.40, 0.40, 0.20)` — reversal, quick_momentum, breakout
