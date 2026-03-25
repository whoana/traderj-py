# Signal Pipeline 용어 설명서

TraderJ 엔진의 시그널 생성 파이프라인에서 사용되는 주요 용어와 값의 의미를 설명합니다.

---

## 로그 출력 예시

```
signal_generated: strategy=STR-005 direction=hold score=-0.1391 tech=-0.1987
```

| 필드 | 의미 | 범위 |
|------|------|------|
| `strategy` | 실행 중인 전략 프리셋 ID | STR-001 ~ STR-006 |
| `direction` | 최종 매매 판단 결과 | buy / sell / hold |
| `score` | 최종 종합 점수 (기술 + 매크로) | -1.0 ~ +1.0 |
| `tech` | 순수 기술적 지표 점수 | -1.0 ~ +1.0 |

---

## 8단계 시그널 파이프라인

```
OHLCV 데이터 (타임프레임별)
  │
  ▼
[Step 1] 기술적 지표 계산 (compute_indicators)
  │       EMA, RSI, MACD, Bollinger Band, OBV, ADX, StochRSI, CMF, ATR 등
  ▼
[Step 2] Z-Score 정규화 (normalize_indicators)
  │       MACD Histogram, OBV 변화율, ROC, CMF 등을 z-score → tanh 변환
  ▼
[Step 3] 서브 스코어 산출 (scoring functions)
  │       3개의 서브 스코어(s1, s2, s3) 생성 → 가중 합산 → TimeframeScore
  ▼
[Step 4] 데일리 게이트 (Daily Gate, 선택)
  │       1일봉 EMA 정렬로 매수 허용 여부 판단
  ▼
[Step 5] MTF 집계 (aggregate_mtf)
  │       타임프레임별 가중치로 합산 → technical_score (= "tech")
  ▼
[Step 6-7] 매크로 점수 통합
  │       score = tech × (1 - macro_weight) + macro × macro_weight (= "score")
  ▼
[Step 8] 방향 결정 (Direction)
          score ≥ buy_threshold  → BUY
          score ≤ sell_threshold → SELL
          그 사이               → HOLD
```

---

## 핵심 용어 상세

### tech (Technical Score)

**정의:** 여러 타임프레임의 기술적 지표를 종합한 순수 기술 점수.

**산출 과정:**

1. 각 타임프레임(예: 1h, 4h)에서 3개의 서브 스코어 산출
2. 서브 스코어를 `score_weights`로 가중 합산하여 타임프레임별 combined score 산출
3. 타임프레임별 combined score를 `tf_weights`로 가중 합산

**공식:**

```
tf_combined = s1 × w1 + s2 × w2 + s3 × w3
tech = Σ(tf_combined × tf_weight) / Σ(tf_weight)
```

**예시 (STR-005):**

```
tf_weights: {"4h": 0.4, "1d": 0.6}
score_weights: trend=0.45, momentum=0.35, volume=0.20

4h_combined = trend_4h × 0.45 + momentum_4h × 0.35 + volume_4h × 0.20
1d_combined = trend_1d × 0.45 + momentum_1d × 0.35 + volume_1d × 0.20

tech = (4h_combined × 0.4 + 1d_combined × 0.6) / (0.4 + 0.6)
```

### score (Combined Score)

**정의:** `tech`에 매크로(거시경제) 점수를 혼합한 최종 종합 점수. 매매 판단의 기준값.

**공식:**

```
score = tech × (1 - macro_weight) + macro_score × macro_weight
```

**예시 (STR-005, macro_weight=0.30):**

```
tech = -0.1987
macro_score = 0.0 (미입력 시 기본값)

score = -0.1987 × 0.70 + 0.0 × 0.30 = -0.1391
```

> `score`와 `tech`의 차이가 매크로 보정의 효과를 나타냅니다.
> 위 예시에서 -0.1987 → -0.1391로 약세가 완화된 것은 매크로 중립(0.0)이 기술적 약세를 희석한 결과입니다.

---

## 서브 스코어 (s1, s2, s3)

Scoring Mode에 따라 서브 스코어의 의미가 달라집니다.

### TREND_FOLLOW 모드

| 서브 스코어 | 기본 가중치 | 구성 요소 |
|-------------|-------------|-----------|
| **s1 (trend)** | 0.50 | EMA 정렬(40%), 가격 vs EMA200(25%), ADX 방향(35%) |
| **s2 (momentum)** | 0.30 | RSI(30%), MACD Z-score(30%), MACD 크로스(15%), StochRSI(25%) |
| **s3 (volume)** | 0.20 | 거래량/MA(25%), OBV Z(20%), CMF Z(20%), 가격-거래량 정렬(20%), BB%B(15%) |

### HYBRID 모드

| 서브 스코어 | 기본 가중치 | 구성 요소 |
|-------------|-------------|-----------|
| **s1 (reversal)** | 0.40 | RSI 극단(35%), BB%B 극단(30%), StochRSI 크로스(35%) |
| **s2 (quick_momentum)** | 0.40 | ROC 5봉 Z(40%), MACD 가속 Z(35%), 연속 캔들(25%) |
| **s3 (breakout)** | 0.20 | BB 돌파(45%), 거래량 확인(30%), BB 스퀴즈(25%) |

---

## 타임프레임 가중치 (tf_weights)

전략별로 어떤 타임프레임에 더 비중을 두는지 결정합니다.

| 전략 | tf_weights | 특성 |
|------|------------|------|
| STR-001 | 1h:0.2, 4h:0.5, 1d:0.3 | 보수적, 장기 위주 |
| STR-002 | 15m:0.2, 1h:0.5, 4h:0.3 | 공격적, 단기 위주 |
| STR-003 | 1h:0.4, 4h:0.6 | 하이브리드 반전 |
| STR-004 | 15m:0.2, 1h:0.3, 4h:0.5 | 다수결 투표 |
| STR-005 | 4h:0.4, 1d:0.6 | 저빈도, 장기 보수적 |
| STR-006 | 15m:0.5, 1h:0.5 | 스캘핑, 초단기 |

---

## Z-Score 정규화

원시 지표값을 통계적으로 일관된 범위로 변환합니다.

**과정:**

```
1. 롤링 Z-Score:  z = (현재값 - 100봉 평균) / 100봉 표준편차
2. tanh 변환:     score = tanh(z)  →  -1.0 ~ +1.0 범위로 매핑
```

**정규화 대상:**

| 원시 지표 | 정규화 컬럼 | 용도 |
|-----------|-------------|------|
| MACD Histogram | `z_macd_hist` | momentum 스코어링 |
| OBV 5봉 변화율 | `z_obv_change` | volume 스코어링 |
| 가격 ROC 5봉 | `z_roc_5` | quick_momentum 스코어링 |
| MACD 가속도(3봉 diff) | `z_macd_accel` | quick_momentum 스코어링 |
| CMF | `z_cmf` | volume 스코어링 |

---

## 매매 임계값 (Thresholds)

최종 `score`를 기준으로 방향을 결정합니다.

| 전략 | buy_threshold | sell_threshold | 특성 |
|------|---------------|----------------|------|
| STR-001 | +0.20 | -0.20 | 보수적 — 확실한 시그널만 |
| STR-002 | +0.12 | -0.12 | 공격적 — 약한 시그널도 진입 |
| STR-003 | +0.18 | -0.18 | 중간 |
| STR-004 | +0.15 | -0.15 | 기본 |
| STR-005 | +0.25 | -0.25 | 매우 보수적 — 강한 확신 필요 |
| STR-006 | +0.10 | -0.10 | 적극적 — 빈번한 진입 |

> 임계값이 높을수록 거래 빈도가 낮아지고, 낮을수록 빈번해집니다.

---

## Daily Gate (일봉 게이트)

1일봉 EMA 정렬을 확인하여 매수 시그널을 필터링합니다.

- **EMA20(1d) > EMA50(1d)**: 상승 추세 → 매수 허용
- **EMA20(1d) <= EMA50(1d)**: 하락 추세 → 매수 차단 (hold로 강제)
- 매도 시그널에는 영향 없음 (포지션 보호)

**적용 전략:** STR-001, STR-005, STR-006 (`use_daily_gate: true`)

---

## Macro Weight (매크로 가중치)

기술적 점수와 거시경제 점수의 혼합 비율입니다.

| 전략 | macro_weight | 의미 |
|------|-------------|------|
| STR-006 | 0.10 | 기술 90%, 매크로 10% — 거의 기술 의존 |
| STR-002 | 0.15 | 기술 85%, 매크로 15% |
| STR-003, STR-004 | 0.20 | 기술 80%, 매크로 20% — 기본 |
| STR-001 | 0.25 | 기술 75%, 매크로 25% |
| STR-005 | 0.30 | 기술 70%, 매크로 30% — 거시경제 영향 큼 |

---

## Entry Mode (진입 모드)

MTF 집계 방식을 결정합니다.

### WEIGHTED (가중 합산)

각 타임프레임의 combined score를 tf_weights로 가중 평균합니다. 대부분의 전략이 사용합니다.

### MAJORITY (다수결)

각 타임프레임에서 독립적으로 매수/매도 판단 후, `majority_min`개 이상의 타임프레임이 동의해야 시그널 발생합니다. STR-004만 사용합니다.

---

## 전략 프리셋 요약

| ID | 이름 | 모드 | 진입 | TF 중심 | 임계값 | 매크로 | 게이트 |
|----|------|------|------|---------|--------|--------|--------|
| STR-001 | Conservative Trend | TREND_FOLLOW | WEIGHTED | 4h | ±0.20 | 25% | O |
| STR-002 | Aggressive Trend | TREND_FOLLOW | WEIGHTED | 1h | ±0.12 | 15% | X |
| STR-003 | Hybrid Reversal | HYBRID | WEIGHTED | 4h | ±0.18 | 20% | X |
| STR-004 | Majority Vote | TREND_FOLLOW | MAJORITY | 4h | ±0.15 | 20% | X |
| STR-005 | Low-Freq Conservative | TREND_FOLLOW | WEIGHTED | 1d | ±0.25 | 30% | O |
| STR-006 | Scalper | TREND_FOLLOW | WEIGHTED | 15m/1h | ±0.10 | 10% | O |

---

## 값 해석 가이드

### score / tech 값의 의미

| 범위 | 해석 |
|------|------|
| +0.50 ~ +1.00 | 강한 매수 시그널 |
| +0.15 ~ +0.50 | 약~중간 매수 시그널 |
| -0.15 ~ +0.15 | 중립 (hold) |
| -0.50 ~ -0.15 | 약~중간 매도 시그널 |
| -1.00 ~ -0.50 | 강한 매도 시그널 |

> 실제 매매 발생 여부는 전략별 `buy_threshold` / `sell_threshold`에 따라 달라집니다.

### score vs tech 차이 해석

| 상황 | 의미 |
|------|------|
| score > tech | 매크로가 기술 대비 긍정적 → 약세 완화 또는 강세 강화 |
| score < tech | 매크로가 기술 대비 부정적 → 강세 완화 또는 약세 강화 |
| score ≈ tech | 매크로 영향 미미 (macro_weight 낮거나 macro_score ≈ 0) |

### 예시: STR-005 로그 해석

```
score=-0.1391  tech=-0.1987  direction=hold
```

1. `tech=-0.1987`: 기술적으로 약세 방향이지만 강하지 않음
2. `score=-0.1391`: 매크로(0.0) 보정으로 약세가 -0.1987 → -0.1391로 완화
3. STR-005의 `sell_threshold=-0.25`이므로 -0.1391은 매도 기준 미달
4. `buy_threshold=+0.25`에도 미달 → **hold** (대기)

---

## 관련 소스 파일

| 파일 | 역할 |
|------|------|
| `engine/strategy/signal.py` | 파이프라인 오케스트레이터 (SignalGenerator) |
| `engine/strategy/indicators.py` | 기술적 지표 계산 (compute_indicators) |
| `engine/strategy/normalizer.py` | Z-Score 정규화 (normalize_indicators) |
| `engine/strategy/filters.py` | 서브 스코어 산출 함수 6종 |
| `engine/strategy/scoring.py` | TimeframeScore, ScoreWeights 데이터 구조 |
| `engine/strategy/mtf.py` | MTF 집계 + Daily Gate |
| `engine/strategy/presets.py` | 전략 프리셋 정의 (STR-001 ~ STR-006) |
