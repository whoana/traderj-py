# Round 2: 전략 엔진 비전 및 요구사항 제안

> **작성자**: Quant Expert (Senior Quantitative Analyst)
> **작성일**: 2026-03-02
> **기반**: Round 1 전략 감사 보고서 + 팀 리더 교차 발견사항 종합

---

## 1. 전략 엔진 비전

### 1.1 현재 상태 요약

bit-trader의 전략 엔진은 **구조적으로 과도하게 보수적**이다. 3단계 필터의 동일 가중 평균, 1d TF 병목, AND 모드의 확률적 한계로 인해 2년간 MTF 백테스트에서 2회만 거래하는 결과를 낳았다. 인프라(ccxt 래퍼, 상태 머신, 스케줄러)는 견고하나, 전략 레이어가 실전 수익성을 제한한다.

### 1.2 목표 상태

**적응형 멀티 전략 엔진**으로 진화한다:

1. **시장 레짐 인식**: 변동성/추세 강도에 따라 전략 파라미터를 동적으로 조정
2. **통계적으로 검증된 전략**: Walk-forward 검증과 Monte Carlo 시뮬레이션으로 과적합 방지
3. **실시간 리스크 관리**: ATR 기반 동적 손절/포지션 사이징, 영속적 리스크 상태
4. **확장 가능한 신호 아키텍처**: 기술 지표, 매크로, 온체인, ML 신호를 플러그인 방식으로 추가

### 1.3 핵심 설계 원칙

| 원칙 | 설명 |
|------|------|
| **Signal-Agnostic Scoring** | 스코어링 함수가 지표 종류에 무관하게 동일한 [-1, +1] 인터페이스를 따름 |
| **Regime-Aware Parameters** | ATR/ADX 기반으로 변동성/추세 레짐을 분류하고, 레짐별로 파라미터 세트 적용 |
| **Statistically Validated** | 모든 전략 변경은 walk-forward 백테스트 + OOS(Out-of-Sample) 검증 필수 |
| **Fail-Safe Risk** | 리스크 상태는 DB 영속화, 재시작 시 자동 복원, 결함 시 안전 방향(거래 중단)으로 동작 |

---

## 2. 요구사항 (P0 / P1 / P2)

### P0: 핵심 (즉시 필요, 시스템 작동의 전제 조건)

#### P0-S1: ATR 지표 추가 및 동적 리스크 통합

**설명**: ATR(14)을 기술 지표에 추가하고, 손절/포지션 사이징에 사용한다.

**요구사항**:
- `indicators.py`에 ATR(14) 계산 추가
- 동적 손절: `stop_loss = entry_price - multiplier × ATR(14)` (기본 multiplier = 2.0)
- 변동성 역비례 포지션 사이징: `position_pct = target_risk / ATR_pct` (target_risk = 2%)
- ATR이 특정 임계값 초과 시 포지션 축소 (volatility cap)

**인터페이스 계약**:
- 입력: OHLCV DataFrame (기존 `compute_indicators` 동일)
- 출력: `df["atr"]` 컬럼 추가
- 리스크 엔진에 전달: `RiskCheck.stop_loss_price`가 ATR 기반으로 계산

**수용 기준**:
- ATR(14) 값이 pandas-ta 공식 구현과 0.01% 이내 일치
- 백테스트에서 고정 3% 손절 대비 max drawdown 감소 확인
- 단위 테스트 5개 이상

---

#### P0-S2: 리스크 상태 DB 영속화

**설명**: 인메모리 리스크 상태(연패 수, 일일 PnL, 쿨다운 시간)를 DB에 영속화한다.

**요구사항**:
- `risk_state` 테이블 생성 (strategy_id, consecutive_losses, daily_pnl, daily_date, cooldown_until)
- `RiskManager` 초기화 시 DB에서 상태 로드
- 상태 변경 시 즉시 DB 업데이트 (write-through)
- 봇 재시작 시 이전 리스크 상태 자동 복원

**인터페이스 계약 (→ 아키텍처 도메인)**:
- 데이터베이스 마이그레이션 스키마 제공 (SQL)
- Store 클래스에 `get_risk_state()`, `update_risk_state()` 메서드 추가 요청
- PostgreSQL/TimescaleDB 전환 시에도 동일 인터페이스 유지 필요

**수용 기준**:
- 봇 재시작 후 연패 카운트가 보존됨
- 쿨다운 중 재시작 시 쿨다운이 유지됨
- 일일 PnL 한도가 날짜 변경 시 자동 리셋됨

---

#### P0-S3: 스코어링 아키텍처 개선

**설명**: 3단계 필터의 동일 가중 평균을 차등 가중치로 변경하고, AND 모드를 개선한다.

**요구사항**:
- `TimeframeScore.combined` 계산을 차등 가중치로 변경:
  - TREND_FOLLOW 모드: trend(0.50) + momentum(0.30) + volume(0.20)
  - HYBRID 모드: reversal(0.40) + quick_momentum(0.40) + breakout(0.20)
- 가중치를 `StrategyParams`에 설정 가능하게 파라미터화
- AND 모드를 **majority voting**으로 대체: "N개 TF 중 M개 이상이 threshold 초과" (M/N 설정 가능)
- 스코어링 함수 내 임의적 상수(×5, ×10, ×33)를 Z-score 정규화로 교체

**인터페이스 계약**:
- `StrategyParams`에 `score_weights: tuple[float, float, float]` 추가
- `EntryMode`에 `MAJORITY` 옵션 추가 + `majority_count: int` 파라미터
- Signal 출력 형식은 기존과 동일 (하위 호환)

**수용 기준**:
- 기존 STR-005 백테스트에서 거래 횟수 증가 (>= 10회/연)
- 스코어 범위가 이론적 [-1, +1]의 30% 이상 활용 (현재 10% 미만)
- 기존 테스트 59개 전부 통과 (또는 동등 대체)

---

#### P0-S4: 전략 프리셋 정리

**설명**: Round 1 감사 결과에 따라 전략 프리셋을 교체/개선한다.

**요구사항**:
- STR-001 **교체**: AND 모드 → WEIGHTED, 1d 제거, 4h(0.6) + 1h(0.4), threshold 0.15
- STR-002 **교체**: AND 모드 → WEIGHTED, 4h(0.55) + 1h(0.45), threshold 0.12
- STR-003 **개선**: 1d 제거 → 1h(0.35) + 4h(0.65), threshold 0.12
- default: STR-005와 동일하게 변경 (가장 균형 잡힌 설정을 기본값으로)
- STR-004, STR-005: 유지
- STR-006 **개선**: 15m(0.25) + 1h(0.45) + 4h(0.30), threshold 0.15

**수용 기준**:
- 모든 프리셋이 단일 TF/MTF 백테스트에서 연간 5회 이상 거래
- AND 모드 사용 프리셋 제거됨

---

### P1: 중요 (1개월 내, 수익성에 직접 영향)

#### P1-S1: 트레일링 스탑 구현

**설명**: 이익 보호를 위한 트레일링 스탑 메커니즘을 추가한다.

**요구사항**:
- 활성화 조건: 미실현 이익이 entry + activation_pct(기본 5%) 초과 시 시작
- 추적 방식: 고점 대비 trail_pct(기본 2%) 하락 시 청산, 또는 고점 - trail_atr × ATR
- ATR 기반 트레일링: `trail_stop = highest_since_entry - trail_multiplier × ATR(14)`
- `RiskParams`에 `trailing_stop_activation_pct`, `trailing_stop_atr_multiplier` 추가

**인터페이스 계약 (→ 아키텍처 도메인)**:
- 실시간 가격 피드 필요 (WebSocket 통합)
- 30초 폴링이 아닌 **tick-level 또는 1초 이내** 가격 업데이트 필수
- `order_manager.py`의 포지션 모니터링 루프에 통합

**수용 기준**:
- 백테스트에서 트레일링 스탑 적용 시 평균 승리 거래 수익률 20% 이상 향상
- 실시간 봇에서 1초 이내 가격 반영

---

#### P1-S2: 백테스트 엔진 고도화

**설명**: 통계적으로 유의미한 전략 검증이 가능한 백테스트 엔진을 구축한다.

**요구사항**:
- **리스크 조정 지표 추가**:
  - Sharpe Ratio: (annualized return - Rf) / annualized σ
  - Sortino Ratio: (annualized return - Rf) / annualized downside σ
  - Calmar Ratio: annualized return / max drawdown
  - Profit Factor: gross profit / gross loss
- **Walk-forward 최적화**:
  - 학습 구간 6개월, 검증 구간 2개월, 슬라이딩 윈도우
  - OOS(Out-of-Sample) 성과가 IS(In-Sample)의 50% 이상이면 통과
- **Equity curve 기반 Max Drawdown**: 매 바(bar)에서 unrealized PnL 포함
- **트랜잭션 비용 모델링**: 수수료 + 슬리피지(0.01~0.1%) + 스프레드(0.02%)

**인터페이스 계약 (→ 아키텍처 도메인)**:
- 과거 데이터 API: `get_candles(symbol, timeframe, start, end)` → 대량 데이터 쿼리 최적화 필요
- 백테스트 결과 저장: `backtest_results` 테이블 (strategy_id, params_hash, metrics JSON)
- 대시보드에 백테스트 비교 뷰 제공 요청

**인터페이스 계약 (→ 대시보드 도메인)**:
- 백테스트 결과 JSON 스키마:
```json
{
  "strategy_id": "STR-005",
  "period": {"start": "2024-01-01", "end": "2025-12-31"},
  "metrics": {
    "total_return": 0.1281,
    "sharpe_ratio": 1.42,
    "sortino_ratio": 2.05,
    "calmar_ratio": 0.95,
    "max_drawdown": 0.135,
    "win_rate": 0.55,
    "profit_factor": 1.85,
    "total_trades": 24
  },
  "equity_curve": [{"timestamp": "...", "equity": 10000000}, ...],
  "trades": [{"entry_time": "...", "exit_time": "...", "pnl_pct": 0.05}, ...]
}
```

**수용 기준**:
- Sharpe/Sortino/Calmar가 전략 비교 테이블에 표시
- Walk-forward OOS 결과가 별도 구간으로 출력
- 기존 백테스트 대비 성과 지표가 5개 이상 추가

---

#### P1-S3: 매크로 스코어러 개선

**설명**: 계단 함수를 연속 함수로 변환하고, 새 데이터 소스를 추가한다.

**요구사항**:
- 모든 계단 함수를 **선형 보간 또는 시그모이드 함수**로 변환
  - 예: DXY → `dxy_score = 5.0 + 3.5 × sigmoid((102.5 - dxy) / 5.0)`
- Reserved 15% 가중치를 기존 컴포넌트에 재배분: FG 35%, Dom 25%, DXY 25%, KP 15%
- **Funding Rate** 추가 (Binance API): 극단적 롱/숏 편향 → 반전 신호
  - 가중치 10% (기존 컴포넌트에서 균등 차감)
- BTC Dominance: 절대값 → **7일 변화율** 기반으로 변경

**인터페이스 계약 (→ 아키텍처 도메인)**:
- Binance Funding Rate API 수집기 추가 필요
- `MacroSnapshot` 모델에 `funding_rate: float | None` 필드 추가
- 데이터 수집 스케줄: 8시간마다 (funding rate 정산 주기에 맞춤)

**수용 기준**:
- 매크로 스코어의 분해능 향상: 동일 DXY 5포인트 범위 내에서 점수 변별력 확인
- Funding Rate 데이터 수집 및 스코어링 정상 동작

---

#### P1-S4: 시장 레짐 분류기

**설명**: ATR과 ADX를 기반으로 현재 시장 레짐을 분류하고, 레짐별 전략 파라미터를 적용한다.

**요구사항**:
- 4가지 레짐 정의:
  - **Trending + High Vol**: ADX > 25 & ATR > median → 추세 추종 강화, 포지션 축소
  - **Trending + Low Vol**: ADX > 25 & ATR <= median → 추세 추종, 정상 포지션
  - **Ranging + High Vol**: ADX <= 25 & ATR > median → 거래 자제 또는 평균 회귀
  - **Ranging + Low Vol**: ADX <= 25 & ATR <= median → BB 수축 브레이크아웃 대기
- 각 레짐별 파라미터 오버라이드:
  - threshold 조정 (ranging 시 높임, trending 시 낮춤)
  - BB std_dev 조정 (high vol 시 2.5, low vol 시 1.5)
  - score_weights 조정 (trending 시 trend 가중치 증가)
- `RegimeClassifier` 클래스로 구현

**인터페이스 계약**:
- 입력: 최근 N일 OHLCV (ATR/ADX 계산용)
- 출력: `Regime` enum + 해당 레짐의 `StrategyParams` 오버라이드
- Signal 생성 파이프라인에서 `RegimeClassifier.current_regime()` → params 적용 → signal 생성

**수용 기준**:
- 레짐 전환이 올바르게 감지됨 (최근 2년 BTC 데이터에서 4개 레짐 모두 출현 확인)
- 레짐별 파라미터 적용 시 백테스트 Sharpe Ratio 개선

---

### P2: 향후 (2-3개월, 경쟁력 확보)

#### P2-S1: Monte Carlo 시뮬레이션

**설명**: 백테스트 결과의 통계적 유의성을 검증한다.

**요구사항**:
- 트레이드 시퀀스 셔플링: 10,000회 시뮬레이션
- 95% 신뢰구간으로 수익률/MDD/Sharpe 범위 산출
- Bootstrap 방식과 Block bootstrap 방식 모두 지원
- 결과 시각화: 수익률 분포 히스토그램, 신뢰구간 밴드

**수용 기준**:
- STR-005의 95% CI가 0% 이상이면 통계적으로 유의한 전략으로 판정

---

#### P2-S2: ML 신호 플러그인 아키텍처

**설명**: 머신러닝 기반 신호를 기존 스코어링 파이프라인에 플러그인할 수 있는 아키텍처를 설계한다.

**요구사항**:
- `SignalPlugin` 인터페이스 정의:
  ```python
  class SignalPlugin(Protocol):
      def score(self, features: pd.DataFrame) -> float:
          """Return score in [-1, +1] range."""
          ...
  ```
- 플러그인 등록 및 가중치 설정 메커니즘
- 초기 ML 모델 후보:
  - LightGBM 분류기 (feature: RSI/MACD/ATR/volume/macro → target: 다음 4h 방향)
  - LSTM 시계열 예측 (24h 가격 방향)
- Walk-forward 학습 파이프라인: 6개월 학습 → 2개월 예측 → 슬라이딩

**인터페이스 계약**:
- Feature DataFrame 스키마 표준화 (모든 지표를 정규화된 [-1, +1] 범위로 변환)
- 모델 아티팩트 저장소 (S3 또는 로컬)
- 추론 지연시간 < 100ms

---

#### P2-S3: 다중 페어 확장

**설명**: BTC/KRW 단일 페어에서 ETH/KRW, SOL/KRW 등으로 확장한다.

**요구사항**:
- 페어별 독립 전략 파라미터 (상관관계가 다르므로)
- 포트폴리오 레벨 리스크 관리:
  - 전체 포트폴리오 VaR/CVaR 한도
  - 페어 간 상관관계 기반 분산 투자 (correlation-adjusted position sizing)
  - 섹터 노출 한도 (예: L1 토큰 합계 < 60%)
- `PortfolioRiskManager` 클래스

---

#### P2-S4: 주문 실행 최적화

**설명**: 현재 시장가 단일 주문을 TWAP/VWAP 분할 주문으로 개선한다.

**요구사항**:
- TWAP(Time-Weighted Average Price): N분에 걸쳐 균등 분할 주문
- 호가창 분석: 주문 크기 대비 유동성 확인 후 슬리피지 예측
- 조건부 주문: 지정가 주문 + timeout 후 시장가 전환

---

## 3. 교차 도메인 인터페이스 계약

### 3.1 전략 엔진 → 데이터 파이프라인 (아키텍처 도메인)

| 인터페이스 | 방향 | 데이터 | 빈도 | 비고 |
|-----------|------|--------|------|------|
| OHLCV 조회 | 전략 ← DB | DataFrame(OHLCV+timestamp) | 매 신호 생성 시 | 최소 250 bars, TF별 |
| 매크로 조회 | 전략 ← DB | MacroSnapshot | 매 신호 생성 시 | 24h 이내 데이터 |
| 리스크 상태 | 전략 ↔ DB | RiskState | 상태 변경 시 | write-through |
| 백테스트 결과 | 전략 → DB | BacktestResult JSON | 백테스트 실행 후 | bulk insert |
| 실시간 가격 | 전략 ← WebSocket | tick(price, volume, timestamp) | 실시간 | 트레일링 스탑용 |

#### OHLCV 쿼리 요구사항
```sql
-- 백테스트 시 대량 쿼리 최적화 필요
-- 현재 SQLite: get_candles(symbol, timeframe, limit=100000) → 인덱스 + 페이지네이션 필요
-- PostgreSQL 전환 시: 시계열 인덱스 (TimescaleDB hypertable)
SELECT * FROM candles
WHERE symbol = $1 AND timeframe = $2
  AND timestamp BETWEEN $3 AND $4
ORDER BY timestamp ASC;
```

#### RiskState 테이블 스키마 제안
```sql
CREATE TABLE risk_state (
    strategy_id TEXT PRIMARY KEY,
    consecutive_losses INTEGER NOT NULL DEFAULT 0,
    daily_pnl REAL NOT NULL DEFAULT 0.0,
    daily_date TEXT NOT NULL DEFAULT '',
    cooldown_until TIMESTAMPTZ,
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 3.2 전략 엔진 → API 서버 (아키텍처 도메인)

| 엔드포인트 | 메서드 | 데이터 | 용도 |
|-----------|--------|--------|------|
| `/api/signals/latest` | GET | Signal[] | 최근 신호 조회 |
| `/api/signals/history` | GET | Signal[] (paginated) | 신호 이력 |
| `/api/strategies` | GET | StrategyParams[] | 활성 전략 목록 |
| `/api/strategies/{id}/params` | PATCH | StrategyParams (partial) | 런타임 파라미터 조정 |
| `/api/risk/state` | GET | RiskState | 리스크 상태 조회 |
| `/api/backtest/run` | POST | BacktestConfig → BacktestResult | 백테스트 실행 |
| `/api/backtest/results` | GET | BacktestResult[] | 백테스트 이력 |
| `/ws/signals` | WebSocket | Signal (실시간 스트림) | 대시보드 실시간 피드 |
| `/ws/prices` | WebSocket | tick(price, volume) | 실시간 가격 |

### 3.3 전략 엔진 → 대시보드 (대시보드 도메인)

#### 대시보드에서 필요한 데이터 뷰

1. **전략 현황 카드**: strategy_id, scoring_mode, entry_mode, 현재 레짐, 최근 신호 방향/점수
2. **신호 히스토리 차트**: timestamp vs score, buy/sell/hold 마커, threshold 라인
3. **스코어 분해 뷰**: 각 TF별 trend/momentum/volume 스코어 바 차트
4. **리스크 상태 패널**: 연패 수, 일일 PnL, 쿨다운 카운트다운, 포지션 크기
5. **백테스트 비교 테이블**: 전략별 Sharpe/Sortino/Calmar/Return/MDD 비교
6. **Equity Curve 차트**: 백테스트 결과의 누적 수익 곡선
7. **레짐 타임라인**: 시간별 시장 레짐(trending/ranging × high/low vol) 색상 코딩

#### 실시간 업데이트 주기

| 데이터 | 업데이트 주기 | 전달 방식 |
|--------|-------------|----------|
| 현재 가격 | 1초 | WebSocket |
| 신호 점수 | 전략별 (15m~1h) | WebSocket push |
| 리스크 상태 | 이벤트 기반 | WebSocket push |
| 포지션 상태 | 이벤트 기반 | WebSocket push |
| 백테스트 결과 | 온디맨드 | REST API |

---

## 4. 마일스톤 로드맵

```
Week 1-2 (P0)
├── P0-S1: ATR 지표 추가 + 동적 리스크
├── P0-S2: 리스크 상태 DB 영속화
├── P0-S3: 스코어링 아키텍처 개선 (가중치 차등화, AND→MAJORITY)
└── P0-S4: 전략 프리셋 정리 (STR-001/002/003 교체/개선)

Week 3-4 (P1 전반)
├── P1-S1: 트레일링 스탑 (WebSocket 통합 의존)
├── P1-S2: 백테스트 고도화 (Sharpe/Sortino/Walk-forward)
└── P1-S3: 매크로 스코어러 개선

Week 5-6 (P1 후반)
├── P1-S4: 시장 레짐 분류기
└── 전체 전략 재검증 (새 백테스트 엔진으로)

Week 7-12 (P2)
├── P2-S1: Monte Carlo 시뮬레이션
├── P2-S2: ML 신호 플러그인 아키텍처
├── P2-S3: 다중 페어 확장
└── P2-S4: 주문 실행 최적화
```

---

## 5. 의존성 및 블로커

| 전략 요구사항 | 의존 도메인 | 필요 시점 | 블로킹 여부 |
|-------------|-----------|----------|-----------|
| 리스크 상태 DB 영속화 | 아키텍처 (DB 스키마) | P0 Week 1 | **블로킹** — DB 마이그레이션 필요 |
| 실시간 가격 피드 | 아키텍처 (WebSocket 통합) | P1 Week 3 | **블로킹** — 트레일링 스탑의 전제 |
| 백테스트 결과 저장 | 아키텍처 (DB 테이블) | P1 Week 3 | 비블로킹 — 파일 저장으로 우회 가능 |
| Funding Rate 수집 | 아키텍처 (Binance API) | P1 Week 4 | 비블로킹 — 매크로 스코어러의 선택적 기능 |
| 백테스트 비교 뷰 | 대시보드 (UI) | P1 Week 4 | 비블로킹 — CLI 출력으로 우회 가능 |
| API 서버 | 아키텍처 (REST + WS) | P1-P2 | **블로킹** — 대시보드 연동의 전제 |

---

## 6. 성공 기준

| 지표 | 현재 | 목표 (P0 완료 후) | 목표 (P1 완료 후) |
|------|------|-------------------|-------------------|
| MTF 연간 거래 횟수 | ~1회 | >= 15회 | >= 30회 |
| 백테스트 Sharpe Ratio | 미계산 | >= 0.8 | >= 1.2 |
| Max Drawdown | 미보고 | < 15% | < 10% |
| 스코어 활용 범위 | 10% | >= 30% | >= 50% |
| 리스크 상태 영속화 | 없음 | 100% | 100% |
| Walk-forward OOS 통과 | 없음 | - | >= 60% 구간 |
