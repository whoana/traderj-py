# Round 5: 전략 구현 로드맵

**작성일**: 2026-03-03
**작성자**: quant-expert (Senior Quantitative Analyst)
**기반**: Round 3 TDR Rev.1, Round 4 상세 설계서 3건 (전략/아키텍처/대시보드)
**목적**: 전략 엔진의 단계적 구현 순서, 검증 기준, 졸업 조건, 교차 의존성 정의

---

## 목차

1. [Phase별 전략 구현 순서](#1-phase별-전략-구현-순서)
2. [백테스트 검증 기준](#2-백테스트-검증-기준)
3. [페이퍼 트레이딩 → 실전 졸업 기준](#3-페이퍼-트레이딩--실전-졸업-기준)
4. [마일스톤별 성공 지표](#4-마일스톤별-성공-지표)
5. [교차 의존성](#5-교차-의존성)
6. [리스크 & 완화 전략](#6-리스크--완화-전략)

---

## 1. Phase별 전략 구현 순서

### 1.1 전체 로드맵 개요

```
Phase S0 (기초)       Phase S1 (핵심)        Phase S2 (검증)        Phase S3 (고급)        Phase S4 (ML)
━━━━━━━━━━━━━━━━━━   ━━━━━━━━━━━━━━━━━━━   ━━━━━━━━━━━━━━━━━━━   ━━━━━━━━━━━━━━━━━━━   ━━━━━━━━━━━━━━━━━━━
지표 파이프라인       스코어링 엔진         백테스트 엔진          트레일링 스탑          LightGBM 플러그인
Z-score 정규화       MTF 집계             Walk-forward          레짐 분류기            Feature 엔지니어링
IndicatorConfig      SignalGenerator      성과 지표 계산        매크로 확장            Walk-forward 학습
                     리스크 엔진(기본)     IS/OOS 검증           DailyGate              Optuna 최적화
                     이벤트 발행           프리셋 검증            변동성 캡              Monte Carlo (P2)
                                          페이퍼 트레이딩
```

### 1.2 Phase S0: 기초 지표 인프라

**목표**: 모든 전략의 기반이 되는 지표 계산 및 정규화 파이프라인 완성

| # | 작업 | 파일 | 세부 내용 | 의존성 |
|---|------|------|----------|--------|
| S0-1 | `IndicatorConfig` dataclass | `strategy/indicators.py` | 17개 파라미터 정의 (EMA 3종, RSI, MACD, StochRSI, BB, ADX, ATR, VWAP, CMF, Volume MA) | 없음 |
| S0-2 | `compute_indicators()` 함수 | `strategy/indicators.py` | pandas-ta 기반 20+ 컬럼 생성. ATR/ATR_pct 신규 추가 | S0-1 |
| S0-3 | Z-score 정규화 엔진 | `strategy/normalizer.py` | `z_score()`, `z_to_score()`, `normalize_indicators()` 구현. 기존 임의 상수(×5, ×10, ×33) 완전 제거 | S0-2 |
| S0-4 | 단위 테스트 | `tests/unit/test_indicators.py` | 5개 핵심 지표(EMA, BB, RSI, MACD, ATR) 정확도 검증. TA-Lib 결과와 교차 검증 (오차 < 0.01%) | S0-2, S0-3 |

**S0 완료 기준**: `compute_indicators()` + `normalize_indicators()` 체이닝이 350 bars OHLCV에서 에러 없이 동작하고, 5개 핵심 지표 단위 테스트 통과

### 1.3 Phase S1: 핵심 전략 엔진

**목표**: 단일 전략의 시그널 생성 → 리스크 평가 → 이벤트 발행 전체 경로 완성

| # | 작업 | 파일 | 세부 내용 | 의존성 |
|---|------|------|----------|--------|
| S1-1 | 스코어링 함수 6종 | `strategy/filters.py` | `trend_score`, `momentum_score`, `volume_score`, `reversal_score`, `breakout_score`, `quick_momentum_score`. 차등 가중치 기반, 모두 [-1, +1] 반환 | S0-3 |
| S1-2 | `TimeframeScore` + `ScoreWeights` | `strategy/scoring.py` | TREND_FOLLOW(0.50/0.30/0.20), HYBRID(0.40/0.40/0.20) 모드. `combined()` 차등 가중 합산 | S1-1 |
| S1-3 | MTF 집계 (`aggregate_mtf`) | `strategy/mtf.py` | WEIGHTED, MAJORITY(min=2), AND(deprecated) 모드. TF별 가중치 적용 | S1-2 |
| S1-4 | `SignalGenerator` 클래스 | `strategy/signal.py` | 8단계 파이프라인 오케스트레이터. `generate()` 메서드로 `SignalResult` 반환 | S1-1~S1-3 |
| S1-5 | 리스크 엔진 (기본) | `strategy/risk.py` | `RiskEngine.evaluate_buy()` — ATR 기반 포지션 사이징, ATR 기반 동적 손절, 쿨다운/일일 한도. `RiskState` DB 영속화 (write-through) | S0-2 (ATR) |
| S1-6 | 이벤트 타입 정의 | `shared/events.py` | `SignalEvent`, `RegimeChangeEvent`, `RiskStateEvent` dataclass. EventBus 발행 연동 | S1-4, S1-5 |
| S1-7 | 전략 프리셋 7종 정의 | `strategy/presets.py` | default, STR-001~006. 각 프리셋의 ScoringMode, EntryMode, TF 가중치, threshold 설정 | S1-4 |
| S1-8 | 통합 테스트 | `tests/integration/test_signal_pipeline.py` | 전체 파이프라인(지표→정규화→스코어→MTF→시그널) end-to-end. 과거 BTC/KRW 데이터로 시그널 방향 검증 | S1-4~S1-7 |

**S1 완료 기준**: 7개 프리셋 모두에서 `SignalGenerator.generate()`가 에러 없이 BUY/SELL/HOLD 시그널 생성. RiskEngine이 포지션 사이징/손절가를 정상 계산.

### 1.4 Phase S2: 백테스트 & 검증

**목표**: 전략의 과거 성과를 정량적으로 검증하고, 페이퍼 트레이딩으로 실시간 검증 시작

| # | 작업 | 파일 | 세부 내용 | 의존성 |
|---|------|------|----------|--------|
| S2-1 | 백테스트 엔진 | `strategy/backtest/engine.py` | Bar-by-bar 이벤트 시뮬레이션. 슬리피지(2bps), 수수료(0.05%), ATR 동적 손절 포함 | S1-4, S1-5 |
| S2-2 | 성과 지표 계산 | `strategy/backtest/metrics.py` | Sharpe, Sortino, Calmar, Profit Factor, Max DD(equity curve 기반), Win Rate, Expectancy. 14개 지표 | S2-1 |
| S2-3 | Walk-forward 옵티마이저 | `strategy/backtest/walkforward.py` | 6개월 학습 + 2개월 검증, 2개월 슬라이드. 2년 데이터 → ~9개 윈도우. 최적화 대상: threshold, score_weights | S2-1, S2-2 |
| S2-4 | DuckDB 데이터 파이프라인 | (아키텍처 팀 제공) | PostgreSQL → Parquet 익스포트 → DuckDB 로드. 백테스트 대량 데이터 조회 최적화 | 아키텍처 Phase 1 |
| S2-5 | 프리셋 백테스트 실행 | - | 7개 프리셋 × 2년 BTC/KRW 4h 데이터. 검증 기준(§2) 통과 여부 판정 | S2-1~S2-3 |
| S2-6 | 페이퍼 트레이딩 시작 | - | 검증 통과 프리셋만 페이퍼 모드로 실전 투입. 실시간 시그널 ↔ 백테스트 비교 | S2-5, 아키텍처 Phase 2 |

**S2 완료 기준**: 최소 2개 이상의 프리셋이 백테스트 검증 기준(§2) 통과. Walk-forward OOS 효율 ≥ 0.5. 페이퍼 트레이딩 시작.

### 1.5 Phase S3: 고급 전략 기능

**목표**: 리스크 관리 고도화, 시장 적응형 파라미터 조정

| # | 작업 | 파일 | 세부 내용 | 의존성 |
|---|------|------|----------|--------|
| S3-1 | 레짐 분류기 | `strategy/regime.py` | ATR + ADX 기반 4-레짐 분류. 히스테리시스(3 bars 연속). 레짐별 threshold/position 오버라이드 | S2-5 (검증 데이터 참조) |
| S3-2 | Daily Gate | `strategy/mtf.py` | 1d EMA20 > EMA50 → 매수 허용, 아닐 경우 매수 차단(매도는 항상 통과). STR-001/STR-006에 적용 | S1-3 |
| S3-3 | 트레일링 스탑 | `strategy/risk.py` | ATR 기반 트레일(2.5×ATR) + 고정 비율(2%) 선택. 활성화 조건: +3% 이익. `RiskEngine.calculate_trailing_stop()` | S1-5 |
| S3-4 | 변동성 캡 | `strategy/risk.py` | ATR > 8% → 진입 차단. 75% 수준(6%)에서 경고(warning). 실전 보호 최후 방어선 | S1-5 |
| S3-5 | 매크로 스코어 확장 | `strategy/macro.py` | 기존 4지표(Fear&Greed, BTC Dom, DXY, Kimchi) + 펀딩 레이트(P1) + BTC Dom 7일 변화(P1). 시그모이드 정규화 | S1-4 |
| S3-6 | 레짐 적응 백테스트 | - | 레짐 분류기 적용 전/후 성과 비교. 레짐 오버라이드 효과 정량 측정 | S3-1, S2-1 |

**S3 완료 기준**: 레짐 분류기 적용 시 Sharpe Ratio 5% 이상 개선 또는 Max DD 10% 이상 감소 확인. 트레일링 스탑 적용 시 avg_win_pct 개선.

### 1.6 Phase S4: ML 시그널 통합

**목표**: LightGBM 기반 방향 예측 플러그인 추가, 기술적 분석과 앙상블

| # | 작업 | 파일 | 세부 내용 | 의존성 |
|---|------|------|----------|--------|
| S4-1 | `ScorePlugin` Protocol | `strategy/plugins.py` | 플러그인 인터페이스 + `PluginRegistry`. 가중치 기반 통합. 추론 < 100ms 제약 | S1-4 |
| S4-2 | Feature 엔지니어링 | `strategy/ml/features.py` | 표준 feature set 정의. Z-score 정규화 지표 + 파생 feature (lag, rolling stats). scikit-learn Pipeline으로 캡슐화 | S0-3 |
| S4-3 | LightGBM 학습 파이프라인 | `strategy/ml/lgbm_trainer.py` | Walk-forward 학습 (6개월→2개월). 3-class 분류 (up/down/neutral). Target: 다음 4h 방향 | S4-2, S2-3 |
| S4-4 | Optuna 하이퍼파라미터 최적화 | `strategy/ml/optimizer.py` | TPE sampler, n_trials=100, pruning. Walk-forward 각 윈도우에서 최적 파라미터 자동 탐색 | S4-3 |
| S4-5 | LightGBM 플러그인 | `strategy/ml/lgbm_plugin.py` | `ScorePlugin` 구현. `proba[up] - proba[down]` → [-1, +1]. 모델 아티팩트 `data/models/{strategy_id}/` | S4-1, S4-3 |
| S4-6 | 앙상블 검증 | - | 기술적 분석 only vs TA + ML(weight=0.2) 비교. OOS에서 ML 추가 시 Sharpe 개선 확인 | S4-5, S2-3 |
| S4-7 | Monte Carlo 시뮬레이션 (P2) | `strategy/backtest/montecarlo.py` | 거래 순서 셔플 1,000회. 5th percentile MDD < 15% 확인. 전략 강건성 검증 | S2-2 |

**S4 완료 기준**: ML 플러그인 OOS 정확도 > 55%. TA + ML 앙상블이 TA only 대비 Sharpe 개선 또는 동등. OOS에서 과적합 징후 없음.

### 1.7 Phase 간 의존성 그래프

```
Phase S0 (기초)
  indicators.py ──────────┐
  normalizer.py ──────────┤
                          │
                          ▼
Phase S1 (핵심) ←── 아키텍처 Phase 0 (shared/ 모델, EventBus 인터페이스)
  filters.py ────────────┐
  scoring.py ────────────┤
  mtf.py ────────────────┤
  signal.py ─────────────┤
  risk.py ───────────────┤
                         │
                         ▼
Phase S2 (검증) ←── 아키텍처 Phase 1 (DataStore PG, DuckDB 파이프라인)
  backtest/engine.py ────┤        ←── 아키텍처 Phase 2 (ExchangeClient, Scheduler)
  backtest/metrics.py ───┤
  backtest/walkforward.py┤
  페이퍼 트레이딩 ─────────┤
                         │
                         ├─────────────────────┐
                         ▼                     ▼
Phase S3 (고급)                        Phase S4 (ML)
  regime.py ──────────┐                  plugins.py ─────────┐
  DailyGate ──────────┤                  ml/features.py ─────┤
  trailing stop ──────┤                  ml/lgbm_trainer.py ─┤
  volatility cap ─────┤                  ml/optimizer.py ────┤
  macro 확장 ──────────┤                  ml/lgbm_plugin.py ──┤
                                         montecarlo.py ──────┤
```

> **S3과 S4는 병렬 진행 가능** — S3은 전통적 기술적 분석 고도화, S4는 ML 파이프라인으로 독립적 개발 가능. 단, 앙상블(S4-6)은 S3 완료 후 실행.

---

## 2. 백테스트 검증 기준

### 2.1 필수 통과 기준 (Gate Criteria)

모든 전략은 아래 기준을 **동시에** 만족해야 "검증 통과"로 판정한다.

| # | 지표 | 기준 | 근거 |
|---|------|------|------|
| G1 | **Sharpe Ratio** | ≥ 0.8 (연환산) | 리스크 조정 수익 최소선. S&P 500 장기 Sharpe ~0.4 기준 2배 |
| G2 | **Sortino Ratio** | ≥ 1.0 (연환산) | 하방 변동성 기준. 상방 변동은 허용 |
| G3 | **Max Drawdown** (equity curve) | ≤ 15% | 미실현 포함 최대 고점 대비 하락. 초보 투자자 심리적 한계선 |
| G4 | **Calmar Ratio** | ≥ 0.5 | 연환산 수익률 / MaxDD. 수익 대비 리스크 효율 |
| G5 | **Profit Factor** | ≥ 1.3 | 총이익 / 총손실. 1.3 미만은 수수료/슬리피지에 취약 |
| G6 | **Win Rate** | ≥ 35% | 최소 승률. 낮은 승률은 avg_win/avg_loss 비율로 보완 가능 |
| G7 | **총 거래 수** | ≥ 30 (2년 기준) | 통계적 유의성 최소 표본. 30건 미만은 과적합 위험 |
| G8 | **OOS 효율** (Walk-forward) | ≥ 0.50 | OOS_return / IS_return. 0.5 미만은 과적합 의심 |
| G9 | **OOS 평균 Sharpe** | ≥ 0.5 | Walk-forward OOS 윈도우들의 평균 Sharpe |
| G10 | **Expectancy** | > 0 | win_rate × avg_win - (1 - win_rate) × avg_loss > 0 |

### 2.2 Walk-Forward 검증 규칙

```
데이터 기간: 최소 2년 (BTC/KRW 4h ≈ 4,380 bars)
학습 윈도우: 6개월 (in-sample)
검증 윈도우: 2개월 (out-of-sample)
슬라이드: 2개월
결과: ~9개 OOS 윈도우

통과 조건:
  1. 최소 7/9 윈도우에서 OOS Return > 0
  2. 평균 OOS 효율(oos_ret / is_ret) ≥ 0.50
  3. 어떤 단일 OOS 윈도우에서도 MDD > 20% 없음
  4. IS → OOS 전환 시 Sharpe 하락폭 < 50%
```

### 2.3 검증 등급

| 등급 | Sharpe | OOS 효율 | Max DD | 판정 |
|------|--------|---------|--------|------|
| **A** (우수) | ≥ 1.5 | ≥ 0.70 | ≤ 10% | 즉시 페이퍼 → 실전 후보 |
| **B** (양호) | ≥ 0.8 | ≥ 0.50 | ≤ 15% | 페이퍼 2주 이상 검증 후 실전 |
| **C** (조건부) | ≥ 0.5 | ≥ 0.40 | ≤ 20% | 파라미터 조정 후 재검증 필요 |
| **D** (미달) | < 0.5 | < 0.40 | > 20% | 전략 폐기 또는 근본 재설계 |

### 2.4 과적합 탐지 체크리스트

- [ ] IS Sharpe > 3.0이면서 OOS Sharpe < 0.5 → **과적합 의심**
- [ ] 최적화 파라미터가 윈도우마다 극단적으로 변동 → **파라미터 불안정**
- [ ] 거래 수가 IS에서 50+ → OOS에서 5 미만 → **필터 과적합**
- [ ] 단일 대형 거래가 전체 수익의 50% 이상 → **운에 의존**
- [ ] train/test 분할 시점 변경에 따라 결과가 크게 변동 → **시간 종속성**

---

## 3. 페이퍼 트레이딩 → 실전 졸업 기준

### 3.1 페이퍼 트레이딩 단계

```
Stage 1: 시그널 전용 (Signal-Only)
  기간: 최소 2주
  내용: 시그널 생성만 기록, 주문 미발행
  목적: 시그널 빈도/방향 실시간 확인, 백테스트와 차이 분석

Stage 2: 소규모 페이퍼 (Paper Trading)
  기간: 최소 4주
  내용: 가상 잔고(1,000만 원)로 완전 자동 거래 시뮬레이션
  목적: 리스크 엔진(손절/트레일링/쿨다운) 실전 작동 검증

Stage 3: 실전 준비 (Pre-Live)
  기간: 최소 2주
  내용: 실전과 동일한 거래소 API 호출(주문은 미발송), 레이턴시 측정
  목적: 슬리피지 실측, API 에러 핸들링, 재연결 복구 검증
```

### 3.2 졸업 기준 (Paper → Live Gate)

**필수 조건 (ALL 충족)**:

| # | 기준 | 측정 방법 | 근거 |
|---|------|----------|------|
| L1 | 페이퍼 기간 ≥ 6주 | Stage 1(2주) + Stage 2(4주) 합산 | 최소 1.5 시장 사이클 관찰 |
| L2 | 페이퍼 Sharpe ≥ 0.5 | Stage 2 전체 기간 실시간 계산 | 백테스트 대비 보수적 기준 (0.8→0.5) |
| L3 | 페이퍼 Max DD ≤ 12% | Stage 2 equity curve 기준 | 실전에서는 슬리피지 추가 → 여유분 확보 |
| L4 | 페이퍼-백테스트 일치도 | 동일 기간 백테스트 대비 시그널 방향 일치율 ≥ 85% | 실전-백테스트 괴리 한계선 |
| L5 | 리스크 이벤트 정상 작동 | 손절/쿨다운/일일 한도 최소 각 1회 발동 확인 | 안전장치 작동 검증 |
| L6 | 시스템 안정성 | 6주간 무중단 운영 (재시작 시 상태 자동 복원) | Docker 자동 재시작 + DB 복원 |
| L7 | 거래 수 ≥ 10 | Stage 2 기간 중 거래 기록 | 통계적 최소 표본 |

**선택 조건 (2/3 이상 충족)**:

| # | 기준 | 설명 |
|---|------|------|
| O1 | Win Rate ≥ 40% | 백테스트 기준(35%)보다 보수적 |
| O2 | Profit Factor ≥ 1.2 | 백테스트 기준(1.3)보다 보수적 (슬리피지 반영) |
| O3 | 최대 연속 손실 < 5회 | 쿨다운(3회) 이후 추가 2회 허용 |

### 3.3 실전 투입 규칙

```
실전 시작 프로토콜:
1. 졸업 기준 충족 → 팀 리더 승인 요청
2. 초기 실전 자본: 전체 트레이딩 자금의 10%
3. 2주간 모니터링 (일일 PnL 보고, 주간 성과 리뷰)
4. 2주 성과가 페이퍼 대비 -20% 이상 괴리 시 → 즉시 페이퍼 복귀
5. 양호한 경우: 4주마다 자본 2배 증가 (10% → 20% → 40% → 최대 80%)

긴급 중단 조건 (자동):
- 일일 손실 > -5% → 해당 전략 24시간 중단
- 연속 3회 손실 → 24시간 쿨다운
- 단일 거래 손실 > -3% → 이후 포지션 크기 50% 축소 (1일간)
- 시스템 에러 3회 연속 → 전체 봇 일시 정지 + 텔레그램 알림
```

### 3.4 전체 진행 타임라인

```
[백테스트 검증] ──→ [Signal-Only 2주] ──→ [Paper 4주] ──→ [Pre-Live 2주] ──→ [실전 10%]
    Phase S2           Phase S2/S3           Phase S2/S3      Phase S2/S3       졸업 후
                                                                                 │
                                              동시 진행: Phase S3/S4              │
                                              (레짐, ML 추가 검증)                 │
                                                                                 ▼
                                                                          [자본 점진적 확대]
                                                                          10% → 20% → 40%
```

---

## 4. 마일스톤별 성공 지표

### 4.1 Phase S0 완료 KPI

| KPI | 목표값 | 측정 방법 |
|-----|--------|----------|
| 지표 계산 정확도 | 오차 < 0.01% (TA-Lib 대비) | 5개 핵심 지표 교차 검증 테스트 |
| 처리 속도 | 350 bars × 20+ 지표 < 200ms | `time.perf_counter()` 벤치마크 |
| Z-score 분포 검증 | 평균 ≈ 0, σ ≈ 1 (lookback 100) | 1년 BTC/KRW 4h 데이터로 통계 검증 |
| 테스트 커버리지 | indicators.py + normalizer.py ≥ 90% | pytest-cov |
| 임의 상수 제거 | 0건 | 코드 내 매직 넘버 검색 (×5, ×10, ×33) |

### 4.2 Phase S1 완료 KPI

| KPI | 목표값 | 측정 방법 |
|-----|--------|----------|
| 시그널 생성 성공률 | 7/7 프리셋 에러 없음 | 7개 프리셋 × 100 bars 시뮬레이션 |
| 시그널 생성 레이턴시 | < 500ms (전체 파이프라인) | 15m+1h+4h 3-TF 동시 처리 기준 |
| 스코어 범위 | 100% [-1, +1] 범위 내 | 10,000 bars 실행 후 범위 검증 |
| 리스크 계산 정확도 | ATR 손절가가 entry - 2.0×ATR ± 0.01% | 단위 테스트 |
| 이벤트 발행 확인 | SignalEvent/RiskStateEvent EventBus 수신 | 통합 테스트 |
| 테스트 커버리지 | strategy/ 전체 ≥ 80% | pytest-cov |

### 4.3 Phase S2 완료 KPI

| KPI | 목표값 | 측정 방법 |
|-----|--------|----------|
| 백테스트 엔진 정확도 | 수수료/슬리피지 반영 오차 < 0.1% | 수동 계산 대조 |
| 백테스트 속도 | 2년 4h 단일 전략 < 5초 | `time.perf_counter()` |
| Walk-forward 윈도우 | ≥ 9개 (2년 데이터) | 자동 검증 |
| 검증 통과 프리셋 | ≥ 2/7 (등급 B 이상) | §2.1 Gate Criteria |
| 페이퍼 트레이딩 시작 | 최소 1개 전략 Paper 모드 | 시스템 로그 확인 |
| BacktestResult JSON | 대시보드 팀이 파싱 가능 | JSON 스키마 검증 |

### 4.4 Phase S3 완료 KPI

| KPI | 목표값 | 측정 방법 |
|-----|--------|----------|
| 레짐 분류 정확도 | 시각적 검증 + 4-레짐 분포 25±10% 범위 | 2년 데이터 레짐 분포 히스토그램 |
| 레짐 적응 효과 | Sharpe +5% 또는 MaxDD -10% 개선 | 적용 전/후 백테스트 비교 |
| 트레일링 스탑 효과 | avg_win_pct 개선 | 적용 전/후 비교 |
| 변동성 캡 작동 | ATR > 8% 시 0건 진입 | 백테스트 + 페이퍼 로그 |
| 매크로 지표 추가 | 펀딩레이트 + BTC Dom 7d 변화 정상 수집 | API 호출 성공률 > 99% |

### 4.5 Phase S4 완료 KPI

| KPI | 목표값 | 측정 방법 |
|-----|--------|----------|
| OOS 분류 정확도 | > 55% (3-class) | Walk-forward OOS 평균 |
| 추론 레이턴시 | < 100ms | `time.perf_counter()` |
| 앙상블 효과 | TA+ML Sharpe ≥ TA-only Sharpe | 동일 OOS 기간 비교 |
| Feature 중요도 | 상위 5 feature 안정성 (윈도우 간 중복 ≥ 60%) | Walk-forward feature_importance 비교 |
| Optuna 최적화 | 시행당 < 30분 (100 trials) | 실행 시간 측정 |
| 모델 아티팩트 관리 | 자동 버전 관리 (data/models/) | 파일 시스템 검증 |
| Monte Carlo 95% MDD | < 15% | 1,000회 시뮬레이션 5th percentile |

---

## 5. 교차 의존성

### 5.1 전략 팀이 필요로 하는 것 (의존성)

#### 엔지니어링 팀 (bot-developer) 제공 필요

| Phase | 필요 항목 | 세부 설명 | 차단 수준 |
|-------|----------|----------|----------|
| S0 | `shared/models.py` | Candle, Signal, RiskState 등 공유 dataclass | **블로킹** — S0 시작 불가 |
| S0 | `shared/events.py` 인터페이스 | EventBus 이벤트 타입 스텁 | **블로킹** |
| S1 | `DataStore Protocol` 구현 (SQLite dev용) | `get_candles()`, `save_signal()`, `get/save_risk_state()` | **블로킹** — S1 리스크 엔진 테스트 불가 |
| S1 | `EventBus` 구현 | asyncio Queue 기반 pub/sub | **블로킹** — 이벤트 발행 테스트 불가 |
| S2 | `DataStore` PostgreSQL 구현 | 실제 DB에서 2년 히스토리컬 데이터 조회 | **블로킹** — 백테스트 실행 불가 |
| S2 | DuckDB 파이프라인 | PG → Parquet → DuckDB. `AnalyticsStore` Protocol | 소프트 — 초기 백테스트는 pandas 메모리로 대체 가능 |
| S2 | ExchangeClient + Scheduler | OHLCV 자동 수집, 페이퍼 트레이딩 루프 | **블로킹** — 페이퍼 시작 불가 |
| S3 | 매크로 수집 스케줄러 | Fear&Greed, BTC Dom, DXY, Kimchi Premium API 호출 | 소프트 — 매크로 비활성화로 우회 가능 |
| S4 | 모델 아티팩트 저장 경로 | `data/models/{strategy_id}/{model_version}/` 디렉터리 관리 | 소프트 — 로컬 파일로 대체 가능 |

#### 대시보드 팀 (dashboard-designer) 제공 필요

| Phase | 필요 항목 | 세부 설명 | 차단 수준 |
|-------|----------|----------|----------|
| S2 | 백테스트 결과 뷰어 (P2) | BacktestResult JSON → 차트/테이블 렌더링 | 소프트 — CLI 출력으로 대체 가능 |
| S3 | 레짐 타임라인 차트 (P1) | 시간×레짐(4색 밴드) 시각화 | 소프트 |

### 5.2 전략 팀이 제공하는 것

#### → 엔지니어링 팀에게

| Phase | 제공 항목 | 세부 설명 |
|-------|----------|----------|
| S0 | `IndicatorConfig` dataclass | 17개 지표 파라미터 정의 |
| S1 | `SignalEvent`, `RegimeChangeEvent`, `RiskStateEvent` | 이벤트 페이로드 스키마 |
| S1 | `RiskConfig` + `RiskState` | 리스크 파라미터 + 영속화 구조 |
| S1 | `StrategyDataStore Protocol` | 전략이 요구하는 데이터 접근 인터페이스 |
| S2 | `BacktestResult` JSON 스키마 | 백테스트 결과 저장/조회 구조 |
| S2 | DB 마이그레이션 SQL | `risk_state`, `backtest_results` 테이블 DDL |

#### → 대시보드 팀에게

| Phase | 제공 항목 | 세부 설명 |
|-------|----------|----------|
| S1 | `Signal.details` JSON 스키마 | 스코어 분해, 레짐, 리스크 상태 포함 (§4.2 참조) |
| S1 | 7개 프리셋 정의서 | 모드, 가중치, threshold 등 대시보드 표시용 |
| S2 | `BacktestMetrics` 14개 지표 정의 | Sharpe, Sortino, Calmar 등 정의 + 계산식 |
| S3 | 레짐 4종 정의 + 색상 매핑 | TRENDING_HIGH_VOL(빨강), TRENDING_LOW_VOL(초록), RANGING_HIGH_VOL(주황), RANGING_LOW_VOL(파랑) |

### 5.3 API 엔드포인트 의존성

전략 엔진의 정상 작동을 위해 아키텍처 팀이 구현해야 하는 핵심 API:

| 엔드포인트 | 메서드 | 전략 사용 목적 | 필요 Phase |
|-----------|--------|--------------|-----------|
| `/api/v1/candles/{symbol}/{tf}` | GET | 지표 계산용 OHLCV 조회 | S1 |
| `/api/v1/signals` | POST | 시그널 저장 | S1 |
| `/api/v1/risk/{strategy_id}` | GET/PUT | 리스크 상태 조회/저장 | S1 |
| `/api/v1/bots/{id}/config` | GET | 전략 파라미터 로드 | S1 |
| `/api/v1/macro/latest` | GET | 매크로 스코어 데이터 | S3 |
| `/api/v1/backtest/run` | POST | 백테스트 실행 트리거 | S2 |
| `/api/v1/backtest/results` | GET | 결과 조회 (대시보드용) | S2 |

### 5.4 DB 테이블 의존성

| 테이블 | 정의 주체 | 구현 주체 | 필요 Phase |
|--------|----------|----------|-----------|
| `candles` (hypertable) | 아키텍처 | 아키텍처 | S0 (데이터 수집) |
| `signals` | 공동 (스키마: 전략) | 아키텍처 | S1 |
| `risk_state` | 전략 (§5.2 SQL) | 아키텍처 (마이그레이션) | S1 |
| `backtest_results` | 전략 (§8 SQL) | 아키텍처 (마이그레이션) | S2 |
| `macro_snapshots` | 공동 | 아키텍처 | S3 |

### 5.5 대시보드 UI 컴포넌트 의존성

대시보드 팀이 전략 데이터를 표시하기 위해 필요한 컴포넌트:

| 컴포넌트 | 데이터 소스 | P-Level | 전략 Phase |
|---------|-----------|---------|-----------|
| 스코어 분해 바 차트 | `Signal.details.tf_scores` | P0 | S1 이후 |
| 리스크 상태 패널 | `RiskStateEvent` (WS) | P0 | S1 이후 |
| 전략 현황 카드 | `Signal.details` 요약 | P0 | S1 이후 |
| 레짐 타임라인 | `RegimeChangeEvent` 이력 | P1 | S3 이후 |
| 백테스트 비교 테이블 | `BacktestResult.metrics` | P1 | S2 이후 |
| Equity Curve 차트 | `BacktestResult.equity_curve` | P1 | S2 이후 |
| ML 예측 패널 | `plugin_scores` | P2 | S4 이후 |

---

## 6. 리스크 & 완화 전략

### 6.1 기술적 리스크

| ID | 리스크 | 영향도 | 발생확률 | 해당 Phase | 완화 전략 |
|----|--------|--------|---------|-----------|----------|
| SR-01 | **커스텀 백테스트 엔진 개발 지연** | 높음 | 중간 | S2 | S0/S1을 우선 완료하여 S2 시작 시점 최대한 앞당김. 초기 백테스트는 pandas 메모리 기반으로 DuckDB 의존성 제거 |
| SR-02 | **Look-ahead bias** (미래 데이터 참조) | 높음 | 중간 | S2 | `BacktestDataProvider`가 현재 bar 이후 데이터 접근 차단. `_extract_windows()` 에서 `bar_time` 기준 엄격 필터링. 코드 리뷰 필수 |
| SR-03 | **Z-score lookback 민감도** | 중간 | 중간 | S0 | 기본값 100 설정 + Walk-forward에서 50/100/200 비교. 프리셋별 lookback 커스터마이즈 허용 |
| SR-04 | **MTF 과보수적 필터링** | 중간 | 높음 | S1 | bit-trader의 AND 모드 문제(2년 2거래) 교훈. WEIGHTED를 기본으로, MAJORITY는 min=2로 완화. AND 모드 deprecated |
| SR-05 | **pandas-ta 지표 버그** | 중간 | 낮음 | S0 | 핵심 5개 지표(EMA, BB, RSI, MACD, ATR) TA-Lib 결과와 교차 검증 단위 테스트 |
| SR-06 | **이벤트 버스 프로세스 재시작 시 상태 유실** | 중간 | 낮음 | S1 | RiskState DB write-through. 재시작 시 `RiskEngine.initialize()` 에서 DB 로드 |

### 6.2 전략적 리스크

| ID | 리스크 | 영향도 | 발생확률 | 해당 Phase | 완화 전략 |
|----|--------|--------|---------|-----------|----------|
| SR-07 | **과적합 (Overfitting)** | 높음 | 높음 | S2, S4 | Walk-forward OOS 검증 필수. IS/OOS 효율 < 0.5 → 실격. 최적화 파라미터 수 최소화 (threshold + w1만). Monte Carlo(S4-7)로 강건성 검증 |
| SR-08 | **실전-백테스트 괴리** | 높음 | 중간 | S2→실전 | 페이퍼 트레이딩 6주 필수. 슬리피지 2bps + 수수료 0.05% 보수적 모델링. 페이퍼-백테스트 시그널 일치율 85% 기준 |
| SR-09 | **ML 모델 과적합** (P2) | 중간 | 중간 | S4 | Walk-forward 학습. OOS 정확도 55% 미달 시 가중치 0으로 비활성화 (기존 TA만 사용). Optuna pruning으로 과최적화 방지 |
| SR-10 | **단일 자산 집중 리스크** | 중간 | 낮음 | 전체 | 현재 BTC/KRW 단일 페어. 향후 ETH/KRW 추가 시 상관관계 분석 후 결정. 포트폴리오 수준 리스크 관리는 Phase 이후 |
| SR-11 | **변동성 급등 시 대응** | 높음 | 중간 | S3 | 변동성 캡(ATR > 8%) 자동 차단. 레짐 분류기의 RANGING_HIGH_VOL → 포지션 크기 50% 축소. 긴급 전체 중지 버튼 |

### 6.3 운영 리스크

| ID | 리스크 | 영향도 | 발생확률 | 해당 Phase | 완화 전략 |
|----|--------|--------|---------|-----------|----------|
| SR-12 | **거래소 API 장애** | 높음 | 중간 | S2→실전 | ccxt 재시도 로직 (3회, 지수 백오프). 연결 실패 시 자동 pause. 텔레그램 즉시 알림 |
| SR-13 | **DB 영속화 실패** | 높음 | 낮음 | S1 | RiskEngine._persist() 실패 시 인메모리 상태 유지 + 텔레그램 알림. 다음 성공적 persist 시 최신 상태 반영 |
| SR-14 | **연속 손실 심리적 영향** | 중간 | 중간 | 실전 | 자동 쿨다운 (3연속 → 24h). 일일 손실 한도 5%. 자본 점진적 확대(10% 시작)로 초기 리스크 최소화 |
| SR-15 | **모델 Drift** (ML) | 중간 | 중간 | S4 | Walk-forward 자동 재학습 주기(2개월). Feature importance 모니터링. 정확도 50% 미만 시 자동 비활성화 |

### 6.4 리스크 대응 우선순위 매트릭스

```
영향도 ↑
높     │ SR-12  SR-11 │ SR-01  SR-02  SR-07  SR-08
       │              │
중     │ SR-05  SR-06 │ SR-03  SR-04  SR-09  SR-14  SR-15
       │  SR-13       │  SR-10
       │              │
낮     │              │
       └──────────────┴───────────────────────
               낮              중/높          → 발생확률

[빨강 영역] 높음×중/높: SR-01, SR-02, SR-07, SR-08, SR-11, SR-12
  → 즉시 대응 계획 수립. 매 Phase 완료 시 검증.

[노랑 영역] 중간×중: SR-03, SR-04, SR-09, SR-14, SR-15
  → 완화 전략 적용 후 모니터링.

[초록 영역] 낮음 영향 또는 낮은 확률: SR-05, SR-06, SR-10, SR-13
  → 기본 대응 계획 유지.
```

---

## 부록: 전략 프리셋 구현 우선순위

Phase S1에서 7개 프리셋을 동시 정의하되, 백테스트 검증(S2)은 아래 우선순위로 진행:

| 순위 | 프리셋 | 근거 |
|------|--------|------|
| 1 | **default** (= STR-005 기반) | TREND_FOLLOW + WEIGHTED + 3-TF. 가장 범용적 |
| 2 | **STR-003** | TREND_FOLLOW + WEIGHTED + 2-TF(1h+4h). 1d 제거로 거래 빈도 개선 |
| 3 | **STR-002** | TREND_FOLLOW + MAJORITY(2) + 2-TF. MAJORITY 모드 검증 |
| 4 | **STR-004** | HYBRID + 단일 TF(1h). 역추세 전략 검증 |
| 5 | **STR-001** | TREND_FOLLOW + WEIGHTED + DailyGate. Gate 효과 검증 |
| 6 | **STR-006** | HYBRID + 3-TF + DailyGate. 복합 조건 검증 |
| 7 | **STR-005** | 원본 bit-trader 설정 매핑. 레거시 비교용 |

> 순위 1~3은 S2에서 반드시 검증. 순위 4~7은 1~3 결과 확인 후 우선순위 조정 가능.

---

> **문서 상태**: Draft — 팀 리더 검토 대기
> **다음 단계**: 엔지니어링/대시보드 로드맵과 교차 검증 후 PROJECT_PLAN.md 통합
