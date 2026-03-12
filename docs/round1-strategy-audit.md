# Round 1: 전략 감사 보고서

> **작성자**: Quant Expert (Senior Quantitative Analyst)
> **작성일**: 2026-03-02
> **대상 코드베이스**: bit-trader (BTC/KRW Auto-Trading Bot)
> **분석 범위**: 전략 프리셋(STR-001~006), 기술 지표, 스코어링 로직, MTF 집계, 매크로 스코어러, 리스크 관리, 백테스트 프레임워크

---

## 목차

1. [종합 요약](#1-종합-요약)
2. [전략 프리셋 평가 (STR-001~006)](#2-전략-프리셋-평가)
3. [기술 지표 효과성 평가](#3-기술-지표-효과성-평가)
4. [3단계 필터 스코어링 로직 분석](#4-3단계-필터-스코어링-로직-분석)
5. [멀티 타임프레임 집계 문제점](#5-멀티-타임프레임-집계-문제점)
6. [매크로 스코어러 유효성 검증](#6-매크로-스코어러-유효성-검증)
7. [리스크 규칙 적절성 평가](#7-리스크-규칙-적절성-평가)
8. [백테스트 프레임워크 한계 분석](#8-백테스트-프레임워크-한계-분석)
9. [종합 판정 매트릭스](#9-종합-판정-매트릭스)
10. [우선순위 권고사항](#10-우선순위-권고사항)

---

## 1. 종합 요약

bit-trader는 구조적으로 잘 설계된 BTC/KRW 자동매매 봇이다. 52개 파일, 59개 테스트, 깔끔한 모듈 분리를 갖추고 있다. 그러나 **전략 레이어에 구조적 병목**이 존재하며, 백테스트 결과가 이를 명확히 입증한다:

- **단일 TF 백테스트**: +12.81% 수익, 15회 거래 (합리적)
- **MTF 백테스트**: +0.15% 수익, **2회 거래** (과도하게 보수적)

이 격차는 단순한 파라미터 튜닝 문제가 아니라, **스코어링 아키텍처 자체의 구조적 결함**에서 비롯된다.

### 핵심 발견사항

| # | 발견사항 | 심각도 | 판정 |
|---|---------|--------|------|
| 1 | 1d TF가 MTF 스코어를 지속적으로 끌어내림 (-0.112) | **치명적** | 개선 |
| 2 | trend/momentum/volume 동일 가중 평균이 신호 희석 | 높음 | 개선 |
| 3 | 스코어링 함수 내 임의적 스케일링 상수 (×5, ×10, ×33) | 높음 | 개선 |
| 4 | ATR 미사용으로 변동성 기반 적응 부재 | 높음 | 개선 |
| 5 | 리스크 상태 인메모리 저장 (재시작 시 소실) | 높음 | 개선 |
| 6 | 백테스트에 Sharpe/Sortino/Calmar 미계산 | 중간 | 개선 |
| 7 | 매크로 스코어러 계단 함수의 granularity 부족 | 중간 | 개선 |
| 8 | Walk-forward 검증, Monte Carlo 시뮬레이션 미구현 | 중간 | 개선 |

---

## 2. 전략 프리셋 평가

### 2.1 default (= STR-003과 유사한 설정)

```python
scoring_mode: TREND_FOLLOW
entry_mode: WEIGHTED
tf_entries: 1h(0.3) + 4h(0.4) + 1d(0.3)
threshold: 0.20 / -0.20
```

**강점**:
- 가장 기본적인 트렌드 추종 구조
- 4h에 가장 높은 가중치(0.4)를 부여하여 적절한 시간 균형

**약점**:
- 1d(0.3) 가중치가 너무 높아 스코어 병목 유발 (HANDOFF.md 확인: 1d 스코어가 지속적으로 -0.112)
- MTF 백테스트에서 2년간 **2회만 거래**

**판정**: `개선` — 1d 가중치를 0.1 이하로 낮추거나 제거 필요

---

### 2.2 STR-001

```python
scoring_mode: TREND_FOLLOW
entry_mode: AND
tf_entries: 1d(0.3, th=0.0) + 4h(0.4, th=0.1) + 1h(0.3, th=0.2)
```

**강점**:
- AND 모드로 모든 TF가 합의해야 진입 → 높은 확신 거래
- 1d threshold=0.0으로 약간의 유연성 확보

**약점**:
- AND 모드의 근본적 문제: **하나의 TF라도 중립이면 거래 불가**
- 1d TF가 장기적으로 중립/약세면 사실상 진입 불가능
- 실제 시장에서 3개 TF가 동시 합의하는 경우는 매우 드묾 (연간 2-5회 수준)
- 1h threshold=0.2는 단독으로도 달성이 어려운 수준

**판정**: `교체` — AND 모드는 BTC 같은 고변동성 자산에 부적합. 가중 평균 방식으로 전환 권고

---

### 2.3 STR-002

```python
scoring_mode: TREND_FOLLOW
entry_mode: AND
tf_entries: 4h(0.5, th=0.2) + 1h(0.5, th=0.2)
```

**강점**:
- 1d TF를 제외하여 병목 회피
- 2개 TF만 사용하므로 AND 모드의 부담 감소

**약점**:
- AND 모드 + threshold 0.2의 이중 필터는 여전히 보수적
- 양 TF 모두 combined > 0.2를 요구 → (trend+momentum+volume)/3 > 0.2는 3개 중 최소 2개가 명확히 양수여야 달성
- 4h와 1h에 동일 가중치(0.5) → 실질적으로 AND 모드에서 가중치는 의미 없음 (둘 다 통과해야 하므로)

**판정**: `교체` — STR-002의 AND 로직은 STR-005의 WEIGHTED 방식으로 대체 가능하며, 더 나은 결과를 기대할 수 있음

---

### 2.4 STR-003

```python
scoring_mode: TREND_FOLLOW
entry_mode: WEIGHTED
tf_entries: 1h(0.3) + 4h(0.5) + 1d(0.2)
threshold: 0.15 / -0.15
```

**강점**:
- WEIGHTED 모드로 유연한 신호 생성
- 낮은 threshold(0.15)로 적절한 거래 빈도 확보 가능
- 1d 가중치를 0.2로 낮춤 (default의 0.3 대비 개선)

**약점**:
- 1d(0.2)가 여전히 존재 → 약세 시 스코어 드래그 잔존
- threshold 0.15에서도 1d 영향으로 실제 진입 빈도 제한적일 수 있음
- 현재 페이퍼 트레이딩에서 10건 시그널 모두 HOLD (score -0.03 ~ +0.10)

**판정**: `개선` — 1d 제거하고 1h(0.35) + 4h(0.65)로 단순화 권고. threshold 0.10~0.15 구간 탐색 필요

---

### 2.5 STR-004

```python
scoring_mode: HYBRID
entry_mode: WEIGHTED
tf_entries: 1h(1.0)
threshold: 0.15 / -0.15
trend_filter: True
```

**강점**:
- 단일 TF로 MTF 병목 완전 회피
- HYBRID 모드(reversal + breakout + quick_momentum)는 다양한 시장 상태 대응
- trend_filter가 역추세 신호 억제 → 리스크 감소

**약점**:
- 단일 1h TF만 사용 → 노이즈에 취약
- HYBRID의 3개 서브스코어(reversal, breakout, quick_momentum)가 서로 상충 가능:
  - reversal_score는 과매도에서 매수 (역추세)
  - breakout_score는 BB 돌파 시 순추세
  - 동시에 과매도 + BB 하단 이탈이면 상충하는 신호 발생
- reversal_score의 RSI 존 40/60이 너무 넓어 잡음 신호 과다

**판정**: `유지 (조건부)` — 단일 TF 전략으로서 가치 있으나, HYBRID 서브스코어 간 가중치 조정 필요. 4h를 보조 확인으로 추가 권고

---

### 2.6 STR-005

```python
scoring_mode: TREND_FOLLOW
entry_mode: WEIGHTED
tf_entries: 15m(0.2) + 1h(0.3) + 4h(0.5)
threshold: 0.20 / -0.20
```

**강점**:
- **1d TF 제외** → 핵심 병목 해소
- 15m으로 빠른 반응성 확보
- 4h에 가장 높은 가중치(0.5) → 노이즈 필터링 효과
- 계층적 가중치 구조(0.2 → 0.3 → 0.5)가 논리적으로 타당

**약점**:
- 15m 캔들의 노이즈 → 과잉매매 리스크 (모니터링 중)
- threshold 0.20은 15m 없는 STR-003(0.15) 대비 높음 → 상쇄 효과로 실질 거래 빈도 불확실
- 15m 과거 데이터가 Upbit API 제한으로 33일분만 가용 → 백테스트 불가

**판정**: `유지` — 가장 균형 잡힌 설정. 15m 데이터 축적 후 백테스트 검증 필요. threshold 0.15로 낮춰 테스트 권고

---

### 2.7 STR-006

```python
scoring_mode: HYBRID
entry_mode: WEIGHTED
tf_entries: 15m(0.4) + 1h(0.6)
threshold: 0.20 / -0.20
trend_filter: True
```

**강점**:
- 단기 TF 조합(15m + 1h)으로 빠른 진입/청산
- HYBRID + trend_filter 조합으로 역추세 잡음 제거
- 스캘핑~스윙 중간 포지션의 전략적 틈새

**약점**:
- 15m(0.4)의 높은 가중치 → 노이즈 민감도 상당
- 4h 이상의 큰 그림 없이 단기 신호에 의존
- HYBRID 서브스코어 상충 문제 (STR-004와 동일)
- reversal_score + trend_filter 조합에서 신호가 과도하게 필터링될 가능성

**판정**: `개선` — 15m 가중치를 0.25로 낮추고, 4h(0.25) 추가로 큰 그림 참조 필요

---

## 3. 기술 지표 효과성 평가

### 3.1 현재 사용 지표

| 카테고리 | 지표 | 파라미터 | 판정 | 비고 |
|---------|------|---------|------|------|
| **Trend** | EMA(20/50/200) | 표준 | `유지` | 업계 표준, 잘 작동 |
| **Trend** | ADX(14) | strong_trend=25 | `유지` | 추세 강도 판별에 유효 |
| **Trend** | Bollinger(20, 2.0) | 표준 | `유지` | 변동성 + 평균 회귀 겸용 |
| **Momentum** | RSI(14) | OB=70, OS=30 | `유지` | 기본 오실레이터, 필수 |
| **Momentum** | MACD(12/26/9) | 표준 | `유지` | 추세 모멘텀 확인에 유효 |
| **Momentum** | StochRSI(14/14/3/3) | 표준 | `유지` | RSI 보완용으로 적절 |
| **Volume** | OBV | - | `개선` | 단독으로는 노이즈 많음, 트렌드 확인용으로만 사용 권고 |
| **Volume** | Volume MA(20) | - | `유지` | 기본적이지만 효과적 |

### 3.2 누락된 핵심 지표

| 지표 | 용도 | 추가 우선순위 | 근거 |
|------|------|-------------|------|
| **ATR(14)** | 변동성 기반 손절/포지션 사이징 | **최우선** | 고정 3% 손절을 ATR 기반 동적 손절로 대체 가능. BTC의 일일 변동성이 2~8%로 크게 변하므로 ATR 미사용은 치명적 |
| **VWAP** | 체결가 대비 공정가치 판단 | 높음 | 크립토 시장 참여자 대부분이 VWAP 참조, 진입 타이밍 최적화에 유용 |
| **CMF(20)** | 자금 흐름 방향 | 중간 | OBV 보완/대체 가능. 가격 위치와 거래량을 결합하여 더 정확한 매집/분산 신호 |
| **Funding Rate** | 시장 레버리지 편향 | 중간 | 극단적 롱/숏 편향 시 반전 신호. Binance 등에서 무료 API 제공 |
| **Open Interest** | 포지션 집중도 | 중간 | 가격 상승 + OI 증가 = 진짜 추세, 가격 상승 + OI 감소 = 숏 청산 랠리 |

### 3.3 지표 파라미터 적응성 문제

현재 모든 지표 파라미터가 **고정값**이다. BTC 시장은 고변동성 구간(2021 Q4)과 저변동성 구간(2023 Q3)이 극단적으로 다르므로, 최소한 ATR 기반의 동적 파라미터 조정이 필요하다:

- **BB std_dev**: 고변동성 시 2.5, 저변동성 시 1.5 (현재 고정 2.0)
- **RSI period**: 변동성 높을 때 21, 낮을 때 10 (현재 고정 14)
- **EMA periods**: 레짐에 따른 적응형 EMA 또는 KAMA(Kaufman Adaptive MA) 고려

---

## 4. 3단계 필터 스코어링 로직 분석

### 4.1 TREND_FOLLOW 모드 (trend_score + momentum_score + volume_score)

#### trend_score (`filters.py:8-62`)

| 컴포넌트 | 가중치 | 범위 | 분석 |
|---------|--------|------|------|
| EMA alignment | 1/factors | ±1.0 / ±0.3 | 이산적 판단 (완전정렬 vs 부분정렬), 중간값 없음 |
| Price vs EMA200 | 1/factors | ±0.5 | 이진 판단, 경계 근처에서 불안정 |
| ADX + DI | 1/factors | ±0.8 / ±0.2 | ADX 25 기준 이진 분류, 연속 스케일 아님 |
| BB %B | 1/factors | (bb_pct-0.5)×0.6 | 유일한 연속값, 범위 ≈ ±0.3 |

**문제점**:
1. **동일 가중 평균**: 4개 팩터가 동일 가중치(`score / factors`)로 평균되지만, EMA alignment(±1.0)와 BB %B(≈±0.3)의 스케일이 다름 → EMA alignment이 과도하게 지배적
2. **BB %B의 카테고리 오배치**: BB %B는 평균 회귀 지표인데 trend_score에 배치됨. HYBRID 모드의 reversal_score에는 올바르게 배치

#### momentum_score (`filters.py:65-114`)

| 컴포넌트 | 가중치 | 범위 | 분석 |
|---------|--------|------|------|
| RSI | 1/factors | (rsi-50)/50 × 0.8 | ≈ ±0.8, 적절 |
| MACD hist | 1/factors | (hist/price×100) × 10 | 임의 스케일링 ×10, 가격 수준에 따라 민감도 변동 |
| MACD crossover | 1/factors | ±0.5 | 이산값, 크로스 직후에만 활성 |
| StochRSI avg | 1/factors | (avg-50)/50 × 0.6 | ≈ ±0.6, 적절 |

**문제점**:
1. **MACD hist 정규화**: `macd_hist / close * 100 * 10`의 스케일링 상수 10은 **경험적 근거 없는 임의값**. BTC 가격이 1억 원일 때와 3천만 원일 때 민감도가 크게 다름
2. **MACD crossover의 단발성**: 크로스 발생 직후 1 bar에서만 ±0.5 기여 → 다음 바에서 즉시 소멸하여 신호 일관성 저하

#### volume_score (`filters.py:117-161`)

| 컴포넌트 | 가중치 | 범위 | 분석 |
|---------|--------|------|------|
| Volume/MA ratio | 1/factors | +0.8 / +0.3 / -0.3 | 3단계 이산, 세밀도 부족 |
| OBV trend | 1/factors | obv_change × 5 | 5-bar 변화율 × 5, 임의 스케일링 |
| Price-volume alignment | 1/factors | ±0.5 | 방향 확인용, 적절 |

**문제점**:
1. **OBV 스케일링 상수 5**: 경험적 근거 없음. OBV 자체가 누적값이므로 변화율의 의미가 시간대별로 다름
2. **거래량 데이터 신뢰성**: 크립토 시장의 wash trading 문제로 volume 기반 점수의 신뢰도 자체가 의문

### 4.2 HYBRID 모드 (reversal_score + breakout_score + quick_momentum_score)

#### reversal_score (`filters.py:164-215`)

가중 합산 방식(RSI 0.40 + BB%B 0.35 + StochRSI 0.25)으로 설계되어 TREND_FOLLOW 모드보다 체계적이나:

- **RSI 존 40/60**: 표준 30/70 대비 넓어 잡음 신호 과다. 특히 횡보장에서 RSI 40~60 내 변동이 빈번
- **trend_filter와의 상호작용**: `price < ema_long and score > 0` → 매수 신호 제거. 하락 추세에서 과매도 반전 기회를 완전 차단하는 것이 의도된 동작인지 재검토 필요

#### breakout_score (`filters.py:218-259`)

BB 돌파 시에만 활성화(밴드 내부 = 0.0)되어 reversal_score와 충돌을 잘 방지하나:

- **BB 바깥에서만 활성화** → 전체 시간의 ~5% 미만에서만 비영점 → TimeframeScore.combined에 기여도 극히 낮음
- `intensity × (0.5 + vol_mult × 0.3 + width_mult × 0.2)`에서 기본 0.5 + 최대 0.5 → 실질 기여 범위가 좁음

#### quick_momentum_score (`filters.py:262-308`)

- MACD hist(0.30) + MACD accel(0.25) + ROC 5-bar(0.25) + RSI(0.20)
- `ROC × 33`: **스케일링 상수 33이 임의적**. 5-bar ROC가 3%면 score ≈ 0.25 × 1.0 = 0.25가 되도록 설계한 것으로 추정되나, 명시적 근거 없음

### 4.3 combined 스코어 계산

```python
# mtf.py:16-17
@property
def combined(self) -> float:
    return (self.trend + self.momentum + self.volume) / 3
```

**핵심 문제**: trend, momentum, volume을 **동일 가중치(1/3)로 평균**한다.

- 추세 추종 전략에서는 trend_score가 가장 중요해야 하며, volume은 확인용이므로 가중치가 낮아야 한다
- 제안: trend(0.5) + momentum(0.3) + volume(0.2) 또는 시장 레짐별 동적 가중치
- HYBRID 모드에서는 reversal(0.4) + quick_momentum(0.4) + breakout(0.2) 정도가 적절 (breakout은 대부분 0이므로)

---

## 5. 멀티 타임프레임 집계 문제점

### 5.1 1d 타임프레임 병목 (치명적)

**증거**: MTF 백테스트에서 1d 스코어가 지속적으로 -0.112 수준 → 가중 합산 시 전체 스코어를 threshold 이하로 끌어내림

**원인 분석**:
- 1d 캔들의 지표 계산은 200-bar EMA에 200일(≈9개월)치 데이터 필요
- 1d trend_score에서 EMA alignment가 지배적 → BTC가 중기 횡보하면 EMA가 수렴하여 약한 음수 유지
- 1d momentum_score의 RSI가 40~60 범위 내에서 약한 음수/양수 오가며 노이즈 생성
- **결론**: 1d TF는 "장기 추세 확인" 의도였으나, 실제로는 **노이즈 생성기**로 작동

**해결 방안** (우선순위순):
1. 1d TF 제거 (STR-005 방식) — 즉시 적용 가능
2. 1d를 scoring 대신 **이진 필터**로 사용: "1d EMA20 > EMA50이면 매수 허용" 식의 on/off 조건
3. 1d 가중치를 0.05 이하로 낮춤 (사실상 무시 수준)

### 5.2 AND 모드의 구조적 한계

```python
# mtf.py:33-37
if p.entry_mode == EntryMode.AND:
    for tf, entry in entries.items():
        tf_score = scores.get(tf)
        if tf_score is None or tf_score.combined < entry.threshold:
            return 0.0  # ← 하나라도 실패하면 즉시 0.0
```

**문제점**:
- 확률적 관점: N개 TF가 독립이라면, 각 TF 통과 확률 p일 때 전체 통과 확률 = p^N
- p=0.3(합리적 추정)이고 N=3이면 → 0.3^3 = 2.7% → **거래 기회가 극단적으로 희소**
- 실제 TF 간에는 상관관계가 있어 약간 나아지지만, AND 모드는 본질적으로 **과잉 필터링** 유발

**해결 방안**: AND 모드를 **minimum threshold** 방식으로 변경
- 예: "최소 2개 TF가 threshold를 넘어야 진입" (majority voting)

### 5.3 WEIGHTED 모드의 정규화 문제

```python
# mtf.py:39-51
total_score += tf_score.combined * entry.weight
total_weight += entry.weight
return max(-1.0, min(1.0, total_score / total_weight))
```

- `total_score / total_weight`는 가중 평균이므로 이론적으로 [-1, 1] 범위
- 그러나 combined 자체가 (trend + momentum + volume) / 3이므로, 개별 score가 모두 +1.0이어도 combined = 1.0 → 가중 평균도 최대 1.0
- **실제 관측값**: 페이퍼 트레이딩에서 score 범위가 -0.03 ~ +0.10 → **이론적 범위의 10% 미만만 활용**
- 이는 필터 스코어들의 상쇄 효과가 심하다는 증거

---

## 6. 매크로 스코어러 유효성 검증

### 6.1 컴포넌트 분석

#### Fear & Greed Index (30%)

```python
fg_score = snap.fear_greed / 10  # 0-100 → 0-10
```

- **유효성**: 중간. Fear & Greed는 소매 투자자 심리를 반영하나, 가격에 후행하는 경향
- **데이터 소스 리스크**: alternative.me API의 안정성과 정확성 의문 (무료 서비스)
- **개선**: 역방향 사용 고려 — 극단적 공포(< 20)에서 매수, 극단적 탐욕(> 80)에서 매도 (contrarian)

#### BTC Dominance (20%)

```python
# 계단 함수: 60%→7.0, 50%→6.0, 40%→5.0, <40%→3.5
```

- **문제점**:
  - 4단계 계단 함수는 너무 조잡 (10% 폭의 구간 내에서 동일 점수)
  - "BTC Dominance 높음 = BTC에 bullish"라는 가정은 항상 성립하지 않음
  - Dominance 상승이 알트코인 폭락에 의한 것이면 전체 시장 약세 신호
- **개선**: Dominance의 **변화율(7일/30일 변화)** 을 사용하고, 연속 함수로 변환

#### DXY (20%)

```python
# 계단 함수: >110→2.0, >105→3.5, >100→5.0, >95→7.0, ≤95→8.5
```

- **문제점**:
  - 5포인트 간격의 계단 함수 → DXY 103과 100.1이 동일 점수
  - DXY ↔ BTC 상관관계는 시기별로 변동 (2022: 강한 역상관, 2024: 약한 역상관)
- **개선**: 선형 보간 또는 Z-score 정규화 (과거 N일 대비 현재 위치)

#### Kimchi Premium (15%)

```python
# 계단 함수: >10%→3.0, >5%→4.0, >0→6.0, >-3%→7.0, ≤-3%→8.0
```

- **유효성**: 높음 (한국 시장 특화). 프리미엄 역방향 사용은 contrarian 전략으로 유효
- **문제점**: 계단 함수의 조잡함 (위와 동일)

#### Reserved (15%)

- 나머지 15%가 neutral(5.0)로 고정 → 전체 점수를 중립으로 끌어당기는 효과
- **즉시 개선**: 15% 여분을 기존 컴포넌트에 재배분

### 6.2 매크로-기술 통합 방식

```python
# signal.py:56-59
final_score = technical * (1 - macro_weight) + m_score * macro_weight
# = technical * 0.8 + m_score * 0.2
```

- **macro_weight = 0.2**: 적절한 수준. 매크로는 보조 필터 역할
- **m_score 범위**: (market_score - 5.0) / 5.0 → [-1, +1]
- **문제**: 현재 market_score가 4.58일 때 m_score = -0.084 → 기술 점수를 -0.017만큼 끌어내림 → 영향이 미미
- 매크로가 실질적 영향을 미치려면 market_score가 2.0 이하(m_score = -0.6) 또는 8.0 이상(m_score = +0.6)이어야 하는데, 이는 극단적 시장 상황에서만 발생

### 6.3 누락된 매크로 데이터

| 데이터 | 중요도 | 소스 | 비고 |
|--------|--------|------|------|
| **Funding Rate** | 높음 | Binance API (무료) | 레버리지 편향 → 반전 신호 |
| **Open Interest** | 높음 | CoinGlass/Binance | 포지션 집중 → 청산 리스크 |
| **Exchange Inflow/Outflow** | 중간 | CryptoQuant (유료) | 매도 압력 예측 |
| **M2 Money Supply** | 낮음 | FRED API (무료) | 장기 유동성 지표 |
| **연준 금리** | 낮음 | FRED API (무료) | 거시경제 방향성 |

---

## 7. 리스크 규칙 적절성 평가

### 7.1 포지션 사이징

```python
max_position_pct: float = 0.20  # 포트폴리오의 20%
```

- **판정**: `개선` — 고정 20%는 BTC 변동성을 무시
- **문제**: BTC ATR(14d)이 3%일 때와 8%일 때 동일 20% 투입은 리스크 불균등
- **권고**:
  - **변동성 역비례 사이징**: position_size = target_risk / ATR
  - 예: target_risk = 2%, ATR = 5% → position = 40%, ATR = 10% → position = 20%
  - Kelly Criterion: f* = (p × b - q) / b 적용 (백테스트 win_rate와 avg_win/avg_loss 기반)

### 7.2 손절

```python
stop_loss_pct: float = 0.03  # -3%
```

- **판정**: `개선` — 고정 3%는 BTC 시장에 부적합
- **문제**:
  - BTC 일일 변동성이 3~5%인 날이 빈번 → 정상 변동에서 불필요한 손절 발생
  - 반대로 저변동성 기간에는 3%가 너무 느슨
- **권고**: ATR 기반 동적 손절
  - stop_loss = entry_price - (2.0 × ATR_14)
  - 또는 Chandelier Exit: highest_high_22 - 3 × ATR_22

### 7.3 일일 최대 손실

```python
daily_max_loss_pct: float = 0.05  # -5%
```

- **판정**: `유지` — 합리적 한도. 포트폴리오 보호에 효과적

### 7.4 연속 손실 쿨다운

```python
max_consecutive_losses: int = 3
cooldown_hours: int = 24
```

- **판정**: `개선`
- **문제**: 24시간 쿨다운은 시간 기반이며 시장 상태를 무시
  - 3연패 후 24시간 뒤 시장이 여전히 불리하면 즉시 4연패 가능
  - 반대로, 3연패 후 1시간 만에 시장이 급반전해도 23시간을 더 기다려야 함
- **권고**:
  - 시간 기반 쿨다운에 **변동성 조건** 추가: ATR이 일정 수준 이하로 안정된 경우에만 재진입
  - 쿨다운 후 **반포지션(10%)** 으로 복귀하여 점진적 리스크 확대

### 7.5 리스크 상태 영속성

```python
# risk.py 전체가 인메모리 상태
self._consecutive_losses: int = 0
self._daily_pnl: float = 0.0
self._cooldown_until: datetime | None = None
```

- **판정**: `개선` (긴급)
- **문제**: 봇 재시작 시 모든 리스크 상태가 초기화됨
  - 2연패 상태에서 봇 재시작 → 연패 카운트 0으로 리셋 → 쿨다운 회피 가능
  - 일일 손실 5% 근접 상태에서 재시작 → 한도 리셋
- **권고**: SQLite에 risk_state 테이블 추가하여 영속화 (bot_state 테이블과 유사 패턴)

### 7.6 누락된 리스크 기능

| 기능 | 중요도 | 비고 |
|------|--------|------|
| **트레일링 스탑** | 높음 | 이익 실현 보호. entry+5% 이후 고점 대비 2% 하락 시 청산 |
| **이익 실현 목표** | 중간 | 고정 TP 또는 R:R 비율 기반 (예: 2:1) |
| **포트폴리오 VaR** | 낮음 | 단일 페어이므로 우선순위 낮으나, 다중 페어 확장 시 필수 |
| **최대 보유 기간** | 중간 | 포지션이 N일(예: 7일) 이상 횡보하면 청산 → 기회비용 관리 |

---

## 8. 백테스트 프레임워크 한계 분석

### 8.1 현재 구현 범위

`run_backtest.py` (440줄)가 제공하는 기능:
- 단일 TF 백테스트 + threshold sweep
- MTF 백테스트 (SignalGenerator 연동)
- 전략 간 비교 (`--compare`)
- 기본 성과 지표: 수익률, B&H, Alpha, Win Rate, Max Drawdown

### 8.2 누락된 핵심 기능

#### 8.2.1 리스크 조정 성과 지표

현재 **Sharpe Ratio, Sortino Ratio, Calmar Ratio가 모두 미계산**. 이는 전략 비교에 치명적.

- **Sharpe Ratio** = (Return - Rf) / σ: 전략의 위험 대비 수익. 1.0 이상이면 양호
- **Sortino Ratio** = (Return - Rf) / σ_downside: 하방 변동성만 패널티. 트레이딩에 더 적합
- **Calmar Ratio** = Annual Return / Max Drawdown: 드로다운 대비 수익

**현재 백테스트 결과만으로는 STR-003과 STR-005 중 어느 것이 "더 나은" 전략인지 판단 불가**.

#### 8.2.2 Walk-Forward 최적화

현재 백테스트는 **in-sample 전체 구간**에서 성과를 측정한다. 이는 과적합(overfitting) 위험이 극도로 높다.

- **필요**: Train(70%) / Validation(15%) / Test(15%) 분할
- Walk-forward: 6개월 학습 → 2개월 검증을 슬라이딩 윈도우로 반복
- Anchored walk-forward: 학습 구간 시작점 고정, 종료점만 확장

#### 8.2.3 Monte Carlo 시뮬레이션

- 트레이드 순서를 무작위로 재배치하여 운(luck) vs 실력(skill) 구분
- 1,000~10,000회 시뮬레이션으로 수익률 신뢰구간 산출
- 예: "95% 확률로 수익률이 -5% ~ +25% 범위"

#### 8.2.4 트랜잭션 비용 민감도 분석

현재 수수료 0.05%만 반영하나, 실제 비용은:
- **슬리피지**: 주문 크기 대비 호가창 깊이에 따라 0.01~0.5%
- **시장 충격**: 대량 주문 시 가격 이동
- **스프레드**: Upbit BTC/KRW bid-ask spread (평균 ~0.02%)

#### 8.2.5 Max Drawdown 계산 한계

```python
def _max_drawdown(trades, initial_balance, position_pct, fee_rate):
    # 트레이드 시점에서만 equity 업데이트
    # 중간의 unrealized PnL을 무시
```

- **문제**: 포지션 보유 중 가격이 크게 떨어졌다가 회복한 경우, 실제 max drawdown은 더 클 수 있으나 현재 코드는 이를 감지하지 못함
- **개선**: 모든 바(bar)에서 equity를 계산하는 equity curve 기반 max drawdown

### 8.3 데이터 제약

- **1h 데이터**: Upbit API가 33일분만 제공 → 1h 기반 전략의 장기 백테스트 불가
- **15m 데이터**: 아직 수집되지 않음 → STR-005/006 백테스트 불가
- **대안**: Binance BTC/USDT 데이터를 프록시로 사용 (환율 조정), Kaiko/CryptoCompare 등 유료 데이터 소스 고려

---

## 9. 종합 판정 매트릭스

| 항목 | 현재 상태 | 판정 | 긴급도 | 상세 |
|------|----------|------|--------|------|
| **STR-001** | AND + 3TF(1d 포함) | `교체` | 높음 | AND 모드를 WEIGHTED로 전환 |
| **STR-002** | AND + 2TF | `교체` | 높음 | STR-005 방식으로 대체 |
| **STR-003** | WEIGHTED + 3TF(1d 포함) | `개선` | 높음 | 1d 제거, threshold 조정 |
| **STR-004** | HYBRID + 1h 단일 | `유지` | 낮음 | 서브스코어 가중치 미세 조정 |
| **STR-005** | WEIGHTED + 15m/1h/4h | `유지` | - | 가장 균형 잡힌 설정 |
| **STR-006** | HYBRID + 15m/1h | `개선` | 중간 | 15m 가중치 축소, 4h 추가 고려 |
| **기술 지표** | 7개 표준 지표 | `개선` | 높음 | ATR 최우선 추가 |
| **3단계 필터** | 동일 가중 평균 | `개선` | 높음 | 카테고리별 차등 가중치 |
| **MTF 집계** | AND + WEIGHTED 2모드 | `개선` | 높음 | AND 폐지, majority voting 도입 |
| **매크로 스코어러** | 계단 함수, 4컴포넌트 | `개선` | 중간 | 연속 함수화, funding rate 추가 |
| **리스크 관리** | 고정값 기반 | `개선` | 높음 | ATR 기반 동적화, 상태 영속화 |
| **백테스트** | 기본 지표만 | `개선` | 중간 | Sharpe/Sortino 추가, walk-forward |

---

## 10. 우선순위 권고사항

### Phase 1: 즉시 개선 (1-2주)

1. **ATR 지표 추가** → 동적 손절, 포지션 사이징의 기반
2. **1d TF 제거** (STR-001/003/default에서) → MTF 병목 해소
3. **AND 모드 폐지** → WEIGHTED 또는 majority voting으로 대체
4. **combined 스코어 차등 가중치**: trend(0.5) + momentum(0.3) + volume(0.2)
5. **리스크 상태 SQLite 영속화**

### Phase 2: 핵심 개선 (2-4주)

6. **ATR 기반 동적 손절**: entry - 2×ATR(14)
7. **변동성 역비례 포지션 사이징**: target_risk / ATR
8. **트레일링 스탑** 구현
9. **백테스트 Sharpe/Sortino/Calmar** 추가
10. **매크로 스코어러 연속 함수화** + reserved 15% 재배분

### Phase 3: 고도화 (4-8주)

11. **Walk-forward 백테스트 프레임워크**
12. **Funding Rate + Open Interest** 매크로 데이터 추가
13. **HYBRID 서브스코어 가중치 최적화**
14. **Monte Carlo 시뮬레이션**
15. **다중 페어 확장 아키텍처** 설계

---

> **결론**: bit-trader의 인프라(봇 엔진, 데이터 파이프라인, 모니터링)는 견고하나, **전략 레이어의 스코어링 아키텍처가 구조적으로 보수적이어서 실전 수익성이 제한된다.** 1d TF 제거, ATR 기반 동적화, 필터 가중치 차등화를 통해 즉시 개선 가능하며, 백테스트 고도화를 통해 전략의 통계적 유의성을 검증해야 한다.
