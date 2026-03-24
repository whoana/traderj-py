# Round 2: 전략 엔진 요구사항서

> **작성자**: Quant Expert (Senior Quantitative Analyst)
> **작성일**: 2026-03-02
> **기반**: Round 1 전략 감사 보고서 (`round1-strategy-audit.md`)
> **참조**: Round 1 교차 발견사항 (팀 리더 종합)

---

## 목차

1. [비전 및 설계 원칙](#1-비전-및-설계-원칙)
2. [P0 요구사항 (Must Have)](#2-p0-요구사항-must-have)
3. [P1 요구사항 (Should Have)](#3-p1-요구사항-should-have)
4. [P2 요구사항 (Nice to Have)](#4-p2-요구사항-nice-to-have)
5. [교차 도메인 데이터 계약](#5-교차-도메인-데이터-계약)
6. [마일스톤 및 의존성 맵](#6-마일스톤-및-의존성-맵)

---

## 1. 비전 및 설계 원칙

### 비전

bit-trader의 전략 엔진을 **적응형 멀티 전략 플랫폼**으로 재설계한다. 현재 시스템은 MTF 백테스트에서 2년간 2회 거래(스코어 범위 이론 대비 10% 미만 활용)라는 구조적 병목을 보인다. 이를 해소하여 **통계적으로 검증 가능하고, 시장 레짐에 적응하며, 리스크를 동적으로 관리**하는 엔진으로 진화한다.

### 설계 원칙

| 원칙 | 설명 |
|------|------|
| **Normalized Scoring** | 모든 스코어링 함수는 [-1, +1] 범위를 Z-score 정규화로 보장. 임의 상수(×5, ×10, ×33) 제거 |
| **Weighted Composition** | 카테고리(trend/momentum/volume) 간 차등 가중치. 동일 평균 금지 |
| **Regime Awareness** | ATR/ADX 기반 4-레짐 분류. 레짐별 파라미터 오버라이드 |
| **Statistical Validation** | 모든 전략은 Walk-forward OOS 검증 + Monte Carlo 95% CI 통과 필수 |
| **Persistent Risk State** | 리스크 상태는 DB 영속화. 재시작 시 자동 복원. Fail-safe = 거래 중단 |
| **Plugin Architecture** | 새 지표/신호 소스를 `ScorePlugin` 인터페이스로 플러그인 |

---

## 2. P0 요구사항 (Must Have)

### P0-S1: 스코어링 아키텍처 재설계

**Round 1 근거**: 감사 보고서 §4 — combined 스코어 동일 가중 평균(1/3)이 신호 희석, 스코어 활용 범위 10% 미만

#### 기능 설명

1. **차등 가중치 도입**: `TimeframeScore.combined` 계산을 파라미터화
   - TREND_FOLLOW: `trend × w_t + momentum × w_m + volume × w_v` (기본: 0.50 / 0.30 / 0.20)
   - HYBRID: `reversal × w_r + quick_momentum × w_q + breakout × w_b` (기본: 0.40 / 0.40 / 0.20)
   - 가중치는 `StrategyParams.score_weights: tuple[float, float, float]`로 설정 가능

2. **임의 상수 제거 → Z-score 정규화**
   - MACD histogram: `macd_hist / close × 100 × 10` → `z_score(macd_hist, lookback=100)`
   - OBV 변화율: `obv_change × 5` → `z_score(obv_5bar_change, lookback=100)`
   - ROC: `roc × 33` → `z_score(roc_5bar, lookback=100)`
   - Z-score를 `tanh()` 또는 `clip(-1, 1)`으로 [-1, +1] 범위로 매핑

3. **BB %B 카테고리 재배치**: trend_score에서 제거, volume_score에 가격-변동성 확인용으로 이동 (또는 별도 volatility_score)

4. **AND 모드 → MAJORITY 모드 대체**
   - 새 `EntryMode.MAJORITY` 추가
   - 파라미터: `majority_min: int` (최소 통과 TF 수, 기본 2)
   - 로직: N개 TF 중 `majority_min`개 이상의 combined > threshold면 진입 허용
   - 기존 AND 모드는 deprecated 경고 후 유지 (하위 호환)

#### 인터페이스 / 데이터 계약

| 대상 | 계약 |
|------|------|
| **bot-developer** | `StrategyParams` 데이터 클래스에 `score_weights: tuple[float, float, float]`, `majority_min: int` 추가. 기존 필드 하위 호환 유지 |
| **bot-developer** | Z-score 계산을 위한 lookback 윈도우(100 bars)가 OHLCV 로드 최소 요구량에 반영되어야 함: 기존 250 → 350 bars |
| **dashboard-designer** | Signal.details JSON에 `score_weights`, `raw_scores`(정규화 전), `z_scores`(정규화 후) 추가. 스코어 분해 뷰에서 시각화 |

#### 성공 기준

- [ ] 스코어 활용 범위가 이론적 [-1, +1]의 **30% 이상** (현재 10% 미만)
- [ ] 기존 STR-005 백테스트에서 연간 거래 횟수 **>= 10회** (현재 ~1회)
- [ ] Z-score 정규화 결과가 가격 수준(3천만 원 vs 1억 원)에 **무관하게 일관된 스케일**
- [ ] 기존 59개 테스트 전부 통과 (또는 동등 대체)

#### 복잡도: **L**

---

### P0-S2: ATR 지표 추가 및 동적 리스크 통합

**Round 1 근거**: 감사 보고서 §3.2 — ATR 미사용이 치명적, §7.1/7.2 — 고정 20% 포지션 + 고정 3% 손절이 BTC 변동성에 부적합

#### 기능 설명

1. **ATR(14) 지표 계산**: `indicators.py`에 추가
   ```python
   df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=14)
   df["atr_pct"] = df["atr"] / df["close"]  # 가격 대비 비율 (%)
   ```

2. **동적 손절 (ATR-based Stop Loss)**
   - `stop_loss = entry_price - atr_stop_multiplier × ATR(14)` (기본 multiplier = 2.0)
   - `RiskParams`에 추가: `atr_stop_multiplier: float = 2.0`, `use_atr_stop: bool = True`
   - 고정 `stop_loss_pct`는 fallback으로 유지 (`use_atr_stop=False` 시)

3. **변동성 역비례 포지션 사이징**
   - `position_pct = target_risk_pct / atr_pct` (기본 target_risk = 2%)
   - 상한: `max_position_pct` (기존 20%), 하한: `min_position_pct` (새 파라미터, 기본 5%)
   - `RiskParams`에 추가: `target_risk_pct: float = 0.02`, `min_position_pct: float = 0.05`, `use_volatility_sizing: bool = True`

4. **변동성 캡 (Volatility Circuit Breaker)**
   - `atr_pct > volatility_cap` (기본 8%)이면 신규 진입 금지
   - `RiskParams`에 추가: `volatility_cap_pct: float = 0.08`

#### 인터페이스 / 데이터 계약

| 대상 | 계약 |
|------|------|
| **bot-developer** | `compute_indicators()` 반환 DataFrame에 `atr`, `atr_pct` 컬럼 추가 |
| **bot-developer** | `RiskManager.check_buy()`에 `current_atr: float` 파라미터 추가. 기존 호출에서 atr 전달 필요 |
| **bot-developer** | `RiskCheck` 반환에 `position_size_pct: float` (실제 적용된 비율) 추가 |
| **dashboard-designer** | 리스크 상태 패널에 "현재 ATR", "적용 포지션 비율", "변동성 상태(정상/경고/차단)" 표시 |

#### 성공 기준

- [ ] ATR(14) 값이 pandas-ta 공식 구현과 **0.01% 이내** 일치
- [ ] 백테스트에서 고정 3% 손절 대비 **max drawdown 20% 이상 감소**
- [ ] 고변동성 구간(ATR > 8%)에서 자동 진입 차단 동작 확인
- [ ] 저변동성 구간에서 포지션 크기 증가, 고변동성 구간에서 감소 확인
- [ ] 단위 테스트 **8개 이상** (ATR 계산, 동적 손절, 동적 사이징, 변동성 캡)

#### 복잡도: **M**

---

### P0-S3: MTF 집계 개선 및 1d TF 병목 해소

**Round 1 근거**: 감사 보고서 §5.1 — 1d 스코어 -0.112가 MTF를 병목, §5.2 — AND 모드의 p^N 문제

#### 기능 설명

1. **1d TF 처리 방식 변경**
   - 모든 프리셋에서 1d TF를 스코어링 가중치에서 **제거**
   - 대신 **이진 필터(Daily Trend Gate)** 도입:
     ```python
     # 1d EMA_short > EMA_medium이면 매수 허용, 아니면 매수 차단
     daily_trend_bullish: bool = ema_20d > ema_50d
     ```
   - `StrategyParams`에 `use_daily_gate: bool = False` 추가 (옵트인)
   - Gate가 차단해도 매도 신호는 항상 통과 (포지션 청산 보호)

2. **MAJORITY 엔트리 모드 구현**
   ```python
   class EntryMode(StrEnum):
       WEIGHTED = "weighted"
       AND = "and"          # deprecated
       MAJORITY = "majority" # 새로 추가
   ```
   - `majority_min: int = 2` — 최소 통과 TF 수
   - AND 모드 사용 시 deprecation warning 로그 출력

3. **전략 프리셋 정리** (P0-S4에서 상세화)

#### 인터페이스 / 데이터 계약

| 대상 | 계약 |
|------|------|
| **bot-developer** | `aggregate_mtf()` 함수에 `daily_gate: bool` 파라미터 추가. 1d OHLCV는 gate 판단용으로만 로드 |
| **bot-developer** | `EntryMode` enum에 `MAJORITY` 추가. `StrategyParams`에 `majority_min: int` 추가 |
| **dashboard-designer** | Signal.details에 `daily_gate_status: "pass" | "blocked"`, `majority_passed: int`, `majority_required: int` 추가 |

#### 성공 기준

- [ ] 1d TF 포함 프리셋(default, STR-001, STR-003)에서 **연간 거래 >= 10회** (현재 ~1회)
- [ ] Daily Gate 사용 시 장기 하락장에서 매수 진입 차단 확인
- [ ] MAJORITY 모드에서 2/3 TF 통과 시 정상 진입 확인
- [ ] AND 모드 사용 시 deprecation 로그 출력 확인

#### 복잡도: **M**

---

### P0-S4: 전략 프리셋 재구성

**Round 1 근거**: 감사 보고서 §2 — STR-001/002 교체, STR-003/006 개선 판정

#### 기능 설명

Round 1 감사 결과에 따라 프리셋을 재구성한다. 핵심 변경: 모든 1d TF 제거, AND 모드 폐지.

| 프리셋 | 현재 | 변경 후 | 변경 사유 |
|--------|------|---------|----------|
| **default** | WEIGHTED, 1h/4h/1d, th=0.20 | = STR-005 (가장 균형 잡힌 설정을 기본값으로) | 1d 병목 해소 |
| **STR-001** | AND, 1d/4h/1h | WEIGHTED, 4h(0.60)+1h(0.40), th=0.15, daily_gate=True | AND→WEIGHTED, 1d→gate |
| **STR-002** | AND, 4h/1h | MAJORITY(2), 4h(0.55)+1h(0.45), th=0.12 | AND→MAJORITY |
| **STR-003** | WEIGHTED, 1h/4h/1d, th=0.15 | WEIGHTED, 1h(0.35)+4h(0.65), th=0.12 | 1d 제거, threshold 하향 |
| **STR-004** | HYBRID, 1h, th=0.15 | 유지 (score_weights 조정: 0.40/0.40/0.20) | 서브스코어 가중치만 변경 |
| **STR-005** | WEIGHTED, 15m/1h/4h, th=0.20 | 유지 (threshold 0.15로 하향 탐색) | 가장 균형, threshold 미세 조정 |
| **STR-006** | HYBRID, 15m/1h, th=0.20 | HYBRID, 15m(0.25)+1h(0.45)+4h(0.30), th=0.15, trend_filter=True | 15m 가중치 축소, 4h 추가 |

#### 인터페이스 / 데이터 계약

| 대상 | 계약 |
|------|------|
| **bot-developer** | `params.py`의 `STRATEGY_PRESETS` dict 업데이트. `load_strategy()` 인터페이스 불변 |
| **bot-developer** | 기존 봇 DB의 strategy_id 참조 호환성: 구 프리셋 ID는 새 설정으로 매핑 |
| **dashboard-designer** | 전략 목록 UI에 scoring_mode, entry_mode, TF 구성, threshold 표시 |

#### 성공 기준

- [ ] AND 모드 사용 프리셋 **0개** (deprecated 경고만 남김)
- [ ] 1d TF가 스코어링 가중치에 사용되는 프리셋 **0개**
- [ ] 모든 프리셋의 MTF 백테스트에서 **연간 거래 >= 5회**
- [ ] 기존 페이퍼 봇(STR-003, STR-004, STR-005)과의 호환성 유지

#### 복잡도: **S**

---

### P0-S5: 리스크 상태 DB 영속화

**Round 1 근거**: 감사 보고서 §7.5 — 인메모리 상태가 재시작 시 소실. 교차 발견사항 #3 (Critical)

#### 기능 설명

1. **`risk_state` 테이블 생성**
   ```sql
   CREATE TABLE risk_state (
       strategy_id TEXT PRIMARY KEY,
       consecutive_losses INTEGER NOT NULL DEFAULT 0,
       daily_pnl REAL NOT NULL DEFAULT 0.0,
       daily_date TEXT NOT NULL DEFAULT '',
       cooldown_until TEXT,  -- ISO8601 timestamp or NULL
       total_trades INTEGER NOT NULL DEFAULT 0,
       total_wins INTEGER NOT NULL DEFAULT 0,
       last_updated TEXT NOT NULL DEFAULT (datetime('now'))
   );
   ```

2. **Write-through 패턴**: 상태 변경 시 즉시 DB 업데이트
   - `record_trade_result()` → DB UPDATE
   - `_ensure_daily_reset()` → DB UPDATE
   - 쿨다운 활성화 → DB UPDATE

3. **시작 시 복원**: `RiskManager.__init__()`에서 DB 로드
   - DB에 해당 strategy_id 레코드 없으면 INSERT DEFAULT
   - 쿨다운 시간이 과거면 자동 해제

4. **Fail-safe**: DB 쓰기 실패 시 인메모리 상태로 fallback + 경고 로그 + 텔레그램 알림

#### 인터페이스 / 데이터 계약

| 대상 | 계약 |
|------|------|
| **bot-developer** | `Store` 클래스에 `get_risk_state(strategy_id) -> RiskState`, `update_risk_state(state: RiskState) -> None` 추가 |
| **bot-developer** | 마이그레이션 SQL 파일 제공: `migrations/003_risk_state.sql` |
| **bot-developer** | `RiskManager.__init__(store: Store, strategy_id: str)` 시그니처 변경 — DI로 Store 주입 |
| **dashboard-designer** | 리스크 패널에 "연패 수", "일일 PnL", "쿨다운 잔여 시간", "총 거래/승리" 표시 |

#### 성공 기준

- [ ] 봇 재시작 후 연패 카운트 **100% 보존**
- [ ] 쿨다운 중 재시작 시 쿨다운 **유지됨** (남은 시간 정확)
- [ ] 일일 PnL 한도가 날짜 변경 시 **자동 리셋**
- [ ] DB 쓰기 실패 시 봇 **크래시하지 않음** (fallback 동작)
- [ ] 단위 테스트 **6개 이상**

#### 복잡도: **M**

---

## 3. P1 요구사항 (Should Have)

### P1-S1: 추가 기술 지표 (VWAP, CMF, Funding Rate)

**Round 1 근거**: 감사 보고서 §3.2 — 누락 지표 목록

#### 기능 설명

1. **VWAP (Volume-Weighted Average Price)**
   - 인트라데이 VWAP 계산 (세션 리셋 기준: UTC 00:00)
   - 사용: `price > vwap` → 매수 확인, `price < vwap` → 매도 확인
   - trend_score에 `vwap_signal` 서브팩터 추가 (가중치 0.15)

2. **CMF(20) (Chaikin Money Flow)**
   - OBV 보완/대체: 가격 위치 + 거래량 결합
   - volume_score에서 OBV 단독 사용 → CMF + OBV 앙상블로 변경

3. **Funding Rate (Binance)**
   - 매크로 스코어러에 새 컴포넌트 추가 (가중치 10%)
   - 극단적 양(> 0.05%) → 과매수 신호, 극단적 음(< -0.05%) → 과매도 신호
   - 선형 보간: `funding_score = -sigmoid(funding_rate / 0.03) × 10 + 5`

#### 인터페이스 / 데이터 계약

| 대상 | 계약 |
|------|------|
| **bot-developer** | Binance public API(`/fapi/v1/fundingRate`)에서 8시간마다 데이터 수집 스케줄러 추가 |
| **bot-developer** | `MacroSnapshot` 모델에 `funding_rate: float | None` 필드 추가 |
| **bot-developer** | `macro_snapshots` DB 테이블에 `funding_rate REAL` 컬럼 추가 |
| **dashboard-designer** | 매크로 패널에 Funding Rate 게이지 + 이력 차트 추가 |

#### 성공 기준

- [ ] VWAP 값이 TradingView 기준값과 **0.1% 이내** 일치
- [ ] CMF(20)와 OBV 앙상블이 단독 OBV 대비 volume_score **분별력 개선** (백테스트 Sharpe 향상)
- [ ] Funding Rate 수집 정상 동작 (8시간 주기, 무료 API)

#### 복잡도: **M**

---

### P1-S2: Walk-Forward 백테스트 프레임워크

**Round 1 근거**: 감사 보고서 §8.2 — 전체 in-sample 백테스트의 과적합 위험

#### 기능 설명

1. **리스크 조정 지표 추가**
   - Sharpe Ratio: `(annualized_return - Rf) / annualized_std` (Rf = 3.5% 연간)
   - Sortino Ratio: `(annualized_return - Rf) / annualized_downside_std`
   - Calmar Ratio: `annualized_return / max_drawdown`
   - Profit Factor: `gross_profit / gross_loss`
   - 연환산: `annual_factor = sqrt(periods_per_year)` (4h = sqrt(6×365))

2. **Equity Curve 기반 Max Drawdown**
   - 매 바(bar)에서 포지션의 unrealized PnL 포함한 equity 계산
   - 기존 trade-only 방식은 `realized_max_drawdown`으로 별도 유지

3. **Walk-Forward 최적화 프레임워크**
   - 구간 설정: `train_months=6, test_months=2`
   - 슬라이딩 윈도우: train → test → slide → 반복
   - 최적화 대상: `buy_threshold`, `sell_threshold`, `score_weights`
   - OOS(Out-of-Sample) 효율: `oos_return / is_return >= 0.5` → 통과

4. **트랜잭션 비용 모델링**
   - 수수료: 0.05% (기존)
   - 슬리피지 모델: `slippage = base_slippage + volume_impact`
     - `base_slippage`: 0.02% (Upbit BTC/KRW 평균 스프레드)
     - `volume_impact`: `order_size / avg_daily_volume × impact_factor`
   - 설정: `BacktestConfig.slippage_bps: float = 2.0` (basis points)

#### 인터페이스 / 데이터 계약

| 대상 | 계약 |
|------|------|
| **bot-developer** | `BacktestResult` 데이터 클래스 확장 (하단 스키마 참조) |
| **bot-developer** | `backtest_results` DB 테이블 생성 (strategy_id, params_hash, metrics JSON, equity_curve BLOB) |
| **bot-developer** | 대량 OHLCV 쿼리 최적화: 시계열 인덱스 + 날짜 범위 쿼리 |
| **dashboard-designer** | 백테스트 비교 테이블: Sharpe/Sortino/Calmar/Return/MDD/Trades/WinRate 컬럼 |
| **dashboard-designer** | Equity Curve 차트: 누적 수익 곡선 + drawdown 영역 표시 |
| **dashboard-designer** | Walk-Forward 시각화: IS 구간 vs OOS 구간 색상 구분 |

**BacktestResult JSON 스키마**:
```json
{
  "strategy_id": "STR-005",
  "params_hash": "a1b2c3d4",
  "config": {
    "train_months": 6,
    "test_months": 2,
    "slippage_bps": 2.0
  },
  "period": {"start": "2024-01-01", "end": "2025-12-31"},
  "metrics": {
    "total_return": 0.1281,
    "annualized_return": 0.064,
    "sharpe_ratio": 1.42,
    "sortino_ratio": 2.05,
    "calmar_ratio": 0.95,
    "profit_factor": 1.85,
    "max_drawdown": 0.135,
    "max_drawdown_unrealized": 0.182,
    "win_rate": 0.55,
    "total_trades": 24,
    "avg_win_pct": 0.058,
    "avg_loss_pct": -0.021,
    "avg_holding_bars": 18
  },
  "walk_forward": {
    "windows": [
      {"train": "2024-01~06", "test": "2024-07~08", "is_return": 0.08, "oos_return": 0.05, "oos_efficiency": 0.625},
      {"train": "2024-03~08", "test": "2024-09~10", "is_return": 0.06, "oos_return": 0.04, "oos_efficiency": 0.667}
    ],
    "avg_oos_efficiency": 0.646,
    "passed": true
  },
  "equity_curve": [
    {"timestamp": "2024-01-15T00:00:00Z", "equity": 10000000, "drawdown": 0.0},
    {"timestamp": "2024-01-15T04:00:00Z", "equity": 10050000, "drawdown": 0.0}
  ],
  "trades": [
    {"entry_time": "2024-02-01T08:00:00Z", "exit_time": "2024-02-03T12:00:00Z", "direction": "long", "entry_price": 65000000, "exit_price": 68000000, "pnl_pct": 0.046, "exit_reason": "signal"}
  ]
}
```

#### 성공 기준

- [ ] Sharpe/Sortino/Calmar가 전략 비교 출력에 **포함**
- [ ] Walk-forward OOS 효율이 **>= 0.5인 구간이 60% 이상**
- [ ] Equity curve MDD가 trade-only MDD보다 **항상 >= (더 보수적)**
- [ ] 슬리피지 2 bps 적용 시 수익률 변화율이 **합리적 범위** (1-5% 차이)

#### 복잡도: **XL**

---

### P1-S3: 매크로 스코어러 개선

**Round 1 근거**: 감사 보고서 §6 — 계단 함수 조잡, reserved 15% 중립 드래그, Fear&Greed 후행

#### 기능 설명

1. **계단 함수 → 연속 함수(시그모이드 보간)**
   - DXY: `score = 5.0 + 3.5 × tanh((102.5 - dxy) / 5.0)`
   - BTC Dominance: `score = 5.0 + 2.0 × tanh((dom - 50.0) / 10.0)`
   - Kimchi Premium: `score = 5.0 + 2.5 × tanh((-kp) / 3.0)` (역방향)
   - Fear & Greed: `score = fg / 10` (이미 연속이나, contrarian 옵션 추가)

2. **가중치 재배분** (reserved 15% 제거)
   - Fear & Greed: 30% → **35%**
   - BTC Dominance: 20% → **20%** (변화율 기반으로 변경)
   - DXY: 20% → **20%**
   - Kimchi Premium: 15% → **15%**
   - Funding Rate: 0% → **10%** (신규)
   - Reserved: 15% → **0%**

3. **BTC Dominance 변화율 기반**: 절대값 대신 7일 변화율 사용
   - `dom_change_7d > 3%` → 7.5 (BTC로 자금 이동 = bullish)
   - 선형 보간: `score = 5.0 + dom_change_7d × 0.8` (clip 2~8)

4. **Fear & Greed contrarian 옵션**
   - `StrategyParams.macro_contrarian: bool = False`
   - True 시: 극단적 공포(< 20) → 매수 강화(8.0+), 극단적 탐욕(> 80) → 매도 강화(2.0-)

#### 인터페이스 / 데이터 계약

| 대상 | 계약 |
|------|------|
| **bot-developer** | `MacroSnapshot`에 `funding_rate`, `btc_dom_7d_change` 필드 추가 |
| **bot-developer** | BTC Dominance 7일 변화율 계산은 데이터 수집 시점에 처리 (DB에 최근 7일분 보관) |
| **dashboard-designer** | 매크로 스코어러 분해 차트: 각 컴포넌트의 원시값 → 점수 변환 곡선(시그모이드) 시각화 |
| **dashboard-designer** | Funding Rate 게이지 (양/음 색상 구분) + 이력 차트 |

#### 성공 기준

- [ ] 동일 DXY 5포인트 범위 내에서 스코어 **변별력 존재** (DXY 101 ≠ DXY 104)
- [ ] Reserved 가중치 **0%** (전부 재배분 완료)
- [ ] Funding Rate 스코어링 정상 동작 (극단적 양/음에서 반전 신호)
- [ ] 매크로 스코어의 전체 범위 활용: 0-10 중 **2.0~8.0 범위 사용**

#### 복잡도: **M**

---

### P1-S4: 시장 레짐 분류기

**Round 1 근거**: 감사 보고서 §3.3 — 모든 지표 파라미터가 고정값, 시장 레짐 적응 부재

#### 기능 설명

1. **4-레짐 분류**

   | 레짐 | 조건 | 전략 적응 |
   |------|------|----------|
   | **Trending + High Vol** | ADX > 25 & ATR_pct > median_30d | 추세 추종 강화, 포지션 축소(target_risk 1.5%), 넓은 손절 |
   | **Trending + Low Vol** | ADX > 25 & ATR_pct <= median_30d | 추세 추종, 정상 포지션, 표준 손절 |
   | **Ranging + High Vol** | ADX <= 25 & ATR_pct > median_30d | 거래 자제(threshold 상향 0.25), 좁은 포지션 |
   | **Ranging + Low Vol** | ADX <= 25 & ATR_pct <= median_30d | BB 수축 대기, 브레이크아웃 가중치 강화, threshold 약간 하향 |

2. **`RegimeClassifier` 클래스**
   ```python
   class RegimeClassifier:
       def classify(self, df: pd.DataFrame) -> Regime
       def get_overrides(self, regime: Regime, base_params: StrategyParams) -> StrategyParams
   ```

3. **레짐별 파라미터 오버라이드 매핑**
   - threshold 조정, score_weights 조정, BB std_dev 조정, target_risk 조정
   - 오버라이드는 `StrategyParams`의 새 인스턴스 반환 (원본 불변)

4. **레짐 전환 히스테리시스**: 레짐 변경은 3 bars 연속 새 레짐 조건 충족 시만 전환 (잡음 방지)

#### 인터페이스 / 데이터 계약

| 대상 | 계약 |
|------|------|
| **bot-developer** | Signal 생성 파이프라인에서 `RegimeClassifier.classify()` → params override → `SignalGenerator.generate()` 호출 순서 |
| **bot-developer** | `Signal.details`에 `regime: str` 필드 추가 |
| **dashboard-designer** | 레짐 타임라인 차트: 시간축 위에 레짐별 색상 밴드 (4색). 현재 레짐 배지 표시 |
| **dashboard-designer** | 레짐별 성과 분해: 각 레짐에서의 거래 수, 승률, 평균 수익률 테이블 |

#### 성공 기준

- [ ] 최근 2년 BTC 데이터에서 **4개 레짐 모두 출현** 확인
- [ ] 레짐별 파라미터 적용 시 백테스트 **Sharpe Ratio >= 10% 개선**
- [ ] 히스테리시스 적용으로 잡음 전환 **80% 이상 감소** (3-bar 이하 레짐 체류 제거)
- [ ] 레짐 분류 지연 < 1ms (실시간 사용 가능)

#### 복잡도: **L**

---

### P1-S5: 트레일링 스탑

**Round 1 근거**: 감사 보고서 §7.6 — 트레일링 스탑 누락, 이익 보호 기능 없음

#### 기능 설명

1. **ATR 기반 트레일링 스탑**
   - 활성화: 미실현 이익 >= `trail_activation_pct` (기본 3%)
   - 추적: `trail_stop = highest_since_activation - trail_atr_multiplier × ATR(14)` (기본 multiplier 2.5)
   - `trail_stop`은 **단조 증가** (올라가기만 함, 내려가지 않음)

2. **대안: 고정 비율 트레일링**
   - `trail_stop = highest_since_activation × (1 - trail_pct)` (기본 2%)
   - ATR 트레일링과 양자택일 (설정으로 선택)

3. **파라미터**
   ```python
   # RiskParams 추가
   use_trailing_stop: bool = True
   trail_activation_pct: float = 0.03    # 활성화 조건: +3% 이익
   trail_atr_multiplier: float = 2.5     # ATR 기반 트레일
   trail_fixed_pct: float = 0.02         # 고정 비율 트레일
   trail_mode: str = "atr"               # "atr" or "fixed"
   ```

#### 인터페이스 / 데이터 계약

| 대상 | 계약 |
|------|------|
| **bot-developer** | **블로킹 의존성**: WebSocket 실시간 가격 피드 통합 필요. 30초 폴링으로는 트레일링 스탑이 효과적으로 작동하지 않음 |
| **bot-developer** | `order_manager.py`의 포지션 모니터링에 트레일링 스탑 로직 통합 |
| **bot-developer** | 포지션 DB에 `trail_stop_price`, `highest_price_since_entry` 필드 추가 |
| **dashboard-designer** | 포지션 카드에 "트레일링 스탑 상태" 표시: 활성화 여부, 현재 트레일 가격, 고점 대비 거리 |

#### 성공 기준

- [ ] 백테스트에서 평균 승리 거래 수익률 **20% 이상 향상**
- [ ] 실시간 봇에서 가격 업데이트 → 트레일 스탑 재계산 **1초 이내**
- [ ] 트레일 스탑 가격이 **단조 증가**하는지 단위 테스트로 검증

#### 복잡도: **M** (WebSocket 의존성 제외, 순수 로직만)

---

## 4. P2 요구사항 (Nice to Have)

### P2-S1: Monte Carlo 시뮬레이션

#### 기능 설명

- 트레이드 시퀀스 셔플링 (block bootstrap, block_size=5)
- 10,000회 시뮬레이션 → 수익률/MDD/Sharpe의 95% 신뢰구간
- 결과: `{mean, median, p5, p25, p75, p95}` for each metric
- **전략 유의성 판정**: 95% CI 하한이 0% 이상이면 "통계적으로 유의한 양의 알파"

#### 인터페이스 / 데이터 계약

| 대상 | 계약 |
|------|------|
| **bot-developer** | `MonteCarloResult` 데이터 클래스 제공. BacktestResult에 선택적 포함 |
| **dashboard-designer** | 수익률 분포 히스토그램 + 95% CI 밴드 차트 |

#### 성공 기준

- [ ] 10,000회 시뮬레이션이 **30초 이내** 완료
- [ ] Block bootstrap으로 시계열 자기상관 보존 확인

#### 복잡도: **M**

---

### P2-S2: ML 시그널 플러그인 아키텍처

#### 기능 설명

1. **`ScorePlugin` 프로토콜**
   ```python
   class ScorePlugin(Protocol):
       name: str
       def score(self, features: pd.DataFrame) -> float:
           """[-1, +1] 범위의 스코어 반환."""
           ...
       def required_features(self) -> list[str]:
           """필요한 feature 컬럼 목록."""
           ...
   ```

2. **초기 ML 모델**: LightGBM 분류기
   - Features: RSI, MACD_hist, ATR_pct, volume_ratio, bb_pct, adx, funding_rate (정규화)
   - Target: 다음 4h 가격 방향 (up/down/neutral)
   - Walk-forward 학습: 6개월 학습 → 2개월 예측

3. **플러그인 등록 및 가중치**
   ```python
   StrategyParams.plugins: list[tuple[ScorePlugin, float]]  # [(plugin, weight)]
   ```
   - 기존 technical_score와 plugin_score의 최종 합산

#### 인터페이스 / 데이터 계약

| 대상 | 계약 |
|------|------|
| **bot-developer** | Feature DataFrame 표준 스키마 정의 (모든 지표를 정규화된 값으로) |
| **bot-developer** | 모델 아티팩트 저장 경로: `data/models/{strategy_id}/{model_version}/` |
| **dashboard-designer** | ML 플러그인 점수를 Signal.details에 포함. 별도 ML 예측 패널 시각화 |

#### 성공 기준

- [ ] LightGBM OOS 정확도 **> 55%** (3-class)
- [ ] 추론 지연 **< 100ms**
- [ ] 플러그인 추가/제거가 기존 코드 변경 **없이** 가능

#### 복잡도: **XL**

---

### P2-S3: 포트폴리오 상관관계 분석

#### 기능 설명

- 다중 페어 확장 시(BTC, ETH, SOL 등) 페어 간 상관관계 분석
- 상관관계 기반 포지션 조정: `adjusted_size = base_size × (1 - avg_correlation)`
- 포트폴리오 레벨 VaR/CVaR 한도
- 섹터 노출 한도 (L1 합계, DeFi 합계 등)

| 대상 | 계약 |
|------|------|
| **bot-developer** | `PortfolioRiskManager` 클래스 → 기존 `RiskManager`의 상위 계층 |
| **dashboard-designer** | 상관관계 히트맵, 포트폴리오 구성 파이차트 |

#### 복잡도: **L**

---

### P2-S4: 동적 파라미터 적응 (고급 레짐 탐지)

#### 기능 설명

- P1-S4의 4-레짐을 확장: Hidden Markov Model(HMM) 기반 레짐 탐지
- 연속적 레짐 확률 (60% trending + 40% ranging 같은 혼합 상태)
- 파라미터 보간: `effective_param = trending_param × p_trend + ranging_param × p_range`

| 대상 | 계약 |
|------|------|
| **bot-developer** | HMM 모델 학습/추론 파이프라인 (hmmlearn 라이브러리) |

#### 복잡도: **XL**

---

## 5. 교차 도메인 데이터 계약

### 5.1 전략 → bot-developer (아키텍처 도메인)

#### 데이터 흐름

| 인터페이스 | 방향 | 데이터 | 빈도 | P-Level |
|-----------|------|--------|------|---------|
| OHLCV 조회 | 전략 ← DB | DataFrame(OHLCV) | 신호 생성 시 | P0 |
| 매크로 조회 | 전략 ← DB | MacroSnapshot | 신호 생성 시 | P0 |
| 리스크 상태 R/W | 전략 ↔ DB | RiskState | 상태 변경 시 | P0 |
| 실시간 가격 | 전략 ← WS | tick(price, vol) | 실시간 | P1 (트레일링) |
| Funding Rate | 전략 ← API | float | 8시간 | P1 |
| 백테스트 결과 저장 | 전략 → DB | BacktestResult JSON | 온디맨드 | P1 |
| 모델 아티팩트 저장 | 전략 → Storage | pickle/joblib | 학습 시 | P2 |

#### API 엔드포인트 요구사항

| 엔드포인트 | 메서드 | 설명 | P-Level |
|-----------|--------|------|---------|
| `GET /api/signals/latest` | REST | 최근 N개 신호 | P0 |
| `GET /api/strategies` | REST | 활성 전략 목록 + 현재 파라미터 | P0 |
| `GET /api/risk/{strategy_id}/state` | REST | 리스크 상태 | P0 |
| `PATCH /api/strategies/{id}/params` | REST | 런타임 파라미터 조정 | P1 |
| `POST /api/backtest/run` | REST | 백테스트 실행 (async) | P1 |
| `GET /api/backtest/results` | REST | 백테스트 결과 목록 | P1 |
| `WS /ws/signals` | WebSocket | 실시간 신호 스트림 | P1 |
| `WS /ws/prices` | WebSocket | 실시간 가격 (트레일링 스탑용) | P1 |

#### DB 스키마 요구사항 (전략 도메인 제공)

```sql
-- P0: 리스크 상태
CREATE TABLE risk_state (
    strategy_id TEXT PRIMARY KEY,
    consecutive_losses INTEGER NOT NULL DEFAULT 0,
    daily_pnl REAL NOT NULL DEFAULT 0.0,
    daily_date TEXT NOT NULL DEFAULT '',
    cooldown_until TEXT,
    total_trades INTEGER NOT NULL DEFAULT 0,
    total_wins INTEGER NOT NULL DEFAULT 0,
    last_updated TEXT NOT NULL DEFAULT (datetime('now'))
);

-- P1: 백테스트 결과
CREATE TABLE backtest_results (
    id TEXT PRIMARY KEY,            -- UUID
    strategy_id TEXT NOT NULL,
    params_hash TEXT NOT NULL,      -- 파라미터 해시 (중복 방지)
    config_json TEXT NOT NULL,      -- BacktestConfig JSON
    metrics_json TEXT NOT NULL,     -- 성과 지표 JSON
    equity_curve_json TEXT,         -- 누적 수익 곡선 JSON (nullable, 대형)
    trades_json TEXT,               -- 거래 내역 JSON (nullable, 대형)
    walk_forward_json TEXT,         -- Walk-forward 결과 (nullable)
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_bt_strategy ON backtest_results(strategy_id);
CREATE INDEX idx_bt_created ON backtest_results(created_at);

-- P1: 매크로 확장
ALTER TABLE macro_snapshots ADD COLUMN funding_rate REAL;
ALTER TABLE macro_snapshots ADD COLUMN btc_dom_7d_change REAL;
```

### 5.2 전략 → dashboard-designer (대시보드 도메인)

#### 필요한 데이터 뷰 (우선순위별)

| # | 뷰 | 데이터 소스 | P-Level |
|---|------|-----------|---------|
| 1 | **전략 현황 카드** | strategy_id, scoring_mode, entry_mode, 현재 레짐, 최근 신호 | P0 |
| 2 | **스코어 분해 바 차트** | Signal.details.tf_scores (각 TF × trend/momentum/volume) | P0 |
| 3 | **리스크 상태 패널** | 연패 수, 일일 PnL, 쿨다운, ATR, 적용 포지션 비율 | P0 |
| 4 | **신호 히스토리 차트** | timestamp vs score, 방향 마커, threshold 라인 | P1 |
| 5 | **백테스트 비교 테이블** | Sharpe/Sortino/Calmar/Return/MDD/Trades/WinRate | P1 |
| 6 | **Equity Curve 차트** | 누적 수익 곡선 + drawdown 영역 | P1 |
| 7 | **레짐 타임라인** | 시간별 레짐(4색) + 현재 레짐 배지 | P1 |
| 8 | **매크로 스코어 분해** | 각 컴포넌트 게이지 + 시그모이드 변환 곡선 | P1 |
| 9 | **Monte Carlo 분포** | 수익률 히스토그램 + 95% CI 밴드 | P2 |
| 10 | **ML 예측 패널** | 플러그인별 점수 + 피처 중요도 바 차트 | P2 |

#### Signal.details JSON 스키마 (확장)

```json
{
  "strategy_id": "STR-005",
  "scoring_mode": "trend_follow",
  "entry_mode": "weighted",
  "regime": "trending_low_vol",
  "technical": 0.185,
  "macro_raw": -0.084,
  "daily_gate_status": "pass",
  "score_weights": [0.50, 0.30, 0.20],
  "tf_scores": {
    "15m": {
      "trend": 0.35, "momentum": 0.22, "volume": 0.15,
      "combined": 0.275,
      "raw_scores": {"ema_align": 0.3, "adx_dir": 0.2, "rsi_norm": 0.18},
      "z_scores": {"macd_hist": 0.42, "obv_change": 0.11}
    },
    "1h": { "..." : "..." },
    "4h": { "..." : "..." }
  },
  "risk_state": {
    "position_pct_applied": 0.15,
    "stop_loss_atr": 62500000,
    "atr_pct": 0.048,
    "volatility_status": "normal"
  }
}
```

#### 실시간 업데이트 주기

| 데이터 | 주기 | 전달 방식 | P-Level |
|--------|------|----------|---------|
| 현재 가격 | 1초 | WebSocket | P1 |
| 신호 점수 | 전략별 (15m~1h) | WebSocket push | P0 |
| 리스크 상태 | 이벤트 기반 | WebSocket push | P0 |
| 포지션 상태 | 이벤트 기반 | WebSocket push | P0 |
| 레짐 변경 | 이벤트 기반 | WebSocket push | P1 |
| 백테스트 결과 | 온디맨드 | REST API | P1 |

---

## 6. 마일스톤 및 의존성 맵

### 6.1 타임라인

```
Week 1-2: P0
├── P0-S1: 스코어링 아키텍처 재설계 (L) ─── 독립
├── P0-S2: ATR + 동적 리스크 (M) ─── 독립
├── P0-S3: MTF 집계 개선 (M) ─── P0-S1에 의존 (score_weights)
├── P0-S4: 프리셋 재구성 (S) ─── P0-S1, P0-S3에 의존
└── P0-S5: 리스크 영속화 (M) ─── bot-developer DB 마이그레이션 블로킹

Week 3-4: P1 전반
├── P1-S1: 추가 지표 (M) ─── bot-developer Funding Rate 수집 블로킹
├── P1-S2: 백테스트 고도화 (XL) ─── 독립 (장기)
└── P1-S3: 매크로 개선 (M) ─── P1-S1에 의존 (funding_rate)

Week 5-6: P1 후반
├── P1-S4: 레짐 분류기 (L) ─── P0-S2에 의존 (ATR)
├── P1-S5: 트레일링 스탑 (M) ─── bot-developer WebSocket 통합 블로킹
└── 전체 전략 재검증 (P1-S2 백테스트 엔진 사용)

Week 7-12: P2
├── P2-S1: Monte Carlo (M)
├── P2-S2: ML 플러그인 (XL)
├── P2-S3: 포트폴리오 상관관계 (L)
└── P2-S4: HMM 레짐 (XL)
```

### 6.2 블로킹 의존성

| 전략 요구사항 | 블로킹 대상 | 필요 시점 | 해결 방법 |
|-------------|-----------|----------|----------|
| **P0-S5** 리스크 영속화 | bot-developer: DB 마이그레이션 | Week 1 | SQL 스키마 전략 도메인에서 제공, bot-developer가 적용 |
| **P1-S1** Funding Rate | bot-developer: Binance API 수집기 | Week 3 | Funding Rate 없이도 매크로 개선 가능 (비블로킹 fallback) |
| **P1-S5** 트레일링 스탑 | bot-developer: WebSocket 실시간 가격 | Week 5 | 백테스트에서만 먼저 구현, 실시간은 WS 준비 후 통합 |
| **P1-S2** 백테스트 결과 저장 | bot-developer: backtest_results 테이블 | Week 3 | 파일 저장(JSON)으로 우회 가능 |
| P0~P1 대시보드 뷰 | dashboard-designer: API 계층 | Week 3+ | REST API 없으면 직접 DB 조회로 우회 (기존 패턴) |

### 6.3 성공 지표 종합

| 지표 | 현재 (bit-trader) | P0 목표 | P1 목표 | P2 목표 |
|------|-------------------|---------|---------|---------|
| MTF 연간 거래 | ~1회 | >= 15회 | >= 30회 | >= 50회 |
| 스코어 활용 범위 | 10% | >= 30% | >= 50% | >= 60% |
| Sharpe Ratio | 미계산 | >= 0.8 | >= 1.2 | >= 1.5 |
| Max Drawdown | 미보고 | < 15% | < 10% | < 8% |
| 리스크 상태 영속 | 0% | 100% | 100% | 100% |
| Walk-forward OOS 통과 | 없음 | - | >= 60% 구간 | >= 70% 구간 |
| Monte Carlo 95% CI > 0 | 없음 | - | - | 통과 |
| ML OOS 정확도 | 없음 | - | - | > 55% |
