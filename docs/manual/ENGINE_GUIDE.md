# TraderJ Engine - 자바 엔지니어를 위한 이해 가이드

> Java/Spring 개발자가 이해하기 쉽도록 Java 생태계에 비유하여 설명합니다.

---

## 목차

1. [전체 구조 한눈에 보기](#1-전체-구조-한눈에-보기)
2. [Java 비유로 이해하는 핵심 개념](#2-java-비유로-이해하는-핵심-개념)
3. [처리 플로우 (tick 한 사이클)](#3-처리-플로우-tick-한-사이클)
4. [시작점부터 마디별 소스 설명](#4-시작점부터-마디별-소스-설명)
5. [데이터 처리](#5-데이터-처리)
6. [백테스트 / 페이퍼 / 실제 환경 차이](#6-백테스트--페이퍼--실제-환경-차이)
7. [7개 전략 프리셋](#7-7개-전략-프리셋)
8. [주요 안전장치](#8-주요-안전장치)

---

## 1. 전체 구조 한눈에 보기

### 디렉토리 = Java 패키지 구조

```
engine/                          ← com.traderj.engine (메인 모듈)
├── config/settings.py           ← application.yml (환경설정)
├── app.py                       ← ApplicationContext (DI 컨테이너)
├── bootstrap.py                 ← @Configuration (빈 등록)
│
├── loop/                        ← com.traderj.core (코어 루프)
│   ├── trading_loop.py          ← @Scheduled 메인 스케줄러
│   ├── state.py                 ← StateMachine (9개 상태)
│   ├── event_bus.py             ← ApplicationEventPublisher
│   ├── scheduler.py             ← TaskScheduler (APScheduler)
│   └── ipc_server.py            ← CommandHandler (외부 명령)
│
├── strategy/                    ← com.traderj.strategy (전략 분석)
│   ├── signal.py                ← SignalService (8단계 파이프라인)
│   ├── indicators.py            ← 기술지표 계산 (20개+)
│   ├── scoring.py               ← 점수 산출 (추세/모멘텀/거래량)
│   ├── filters.py               ← 6개 스코어 함수
│   ├── mtf.py                   ← 멀티타임프레임 집계
│   ├── normalizer.py            ← Z-score 정규화
│   ├── risk.py                  ← ATR 기반 동적 위험관리
│   ├── presets.py               ← 7개 전략 프리셋 (enum-like)
│   └── backtest/engine.py       ← 백테스트 엔진
│
├── execution/                   ← com.traderj.execution (주문 실행)
│   ├── order_manager.py         ← OrderService (8단계 주문)
│   ├── position_manager.py      ← PositionService (포지션 관리)
│   ├── risk_manager.py          ← RiskService (리스크 검증)
│   └── circuit_breaker.py       ← CircuitBreaker (Resilience4j 같은)
│
├── exchange/                    ← com.traderj.infra.exchange
│   ├── upbit_client.py          ← ExchangeClient (REST API)
│   └── rate_limiter.py          ← RateLimiter (Bucket4j 같은)
│
├── data/                        ← com.traderj.infra.repository
│   ├── sqlite_store.py          ← H2Repository (개발/테스트)
│   └── postgres_store.py        ← JpaRepository (프로덕션)
│
└── notification/
    └── telegram.py              ← NotificationService
```

### 아키텍처 다이어그램

```
┌──────────────────────────────────────────────────────────────┐
│                    AppOrchestrator                            │
│               (= Spring ApplicationContext)                  │
│                                                              │
│  ┌─── 공유 컴포넌트 (싱글톤) ──────────────────────────┐    │
│  │  EventBus       = ApplicationEventPublisher          │    │
│  │  Scheduler      = TaskScheduler                      │    │
│  │  DataStore      = JpaRepository                      │    │
│  │  ExchangeClient = RestTemplate (Upbit API)           │    │
│  │  IPCServer      = CommandHandler                     │    │
│  └──────────────────────────────────────────────────────┘    │
│                         ↑ (주입)                              │
│  ┌─── 전략별 컴포넌트 (전략 수만큼 생성) ──────────────┐    │
│  │                                                      │    │
│  │  [STR-001]              [STR-002]         ...        │    │
│  │  ┌──────────────┐      ┌──────────────┐             │    │
│  │  │ TradingLoop  │      │ TradingLoop  │             │    │
│  │  │ SignalGen    │      │ SignalGen    │             │    │
│  │  │ OrderMgr     │      │ OrderMgr     │             │    │
│  │  │ PositionMgr  │      │ PositionMgr  │             │    │
│  │  │ RiskMgr      │      │ RiskMgr      │             │    │
│  │  │ StateMachine │      │ StateMachine │             │    │
│  │  │ CircuitBreaker│     │ CircuitBreaker│             │    │
│  │  └──────────────┘      └──────────────┘             │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

**핵심 포인트**: EventBus, DataStore, Exchange는 **싱글톤**(공유), 나머지는 **전략별 독립 인스턴스**.

---

## 2. Java 비유로 이해하는 핵심 개념

| Python (TraderJ) | Java 비유 | 역할 |
|---|---|---|
| `AppOrchestrator` | `ApplicationContext` | DI 컨테이너, 빈 라이프사이클 |
| `bootstrap()` | `@Configuration` 클래스 | 컴포넌트 생성 & 의존성 주입 |
| `EventBus` | `ApplicationEventPublisher` | 비동기 이벤트 발행/구독 |
| `TradingLoop.tick()` | `@Scheduled(fixedRate=60000)` | 60초마다 실행되는 메인 루프 |
| `StateMachine` | Spring State Machine | 9개 상태 전이 관리 |
| `CircuitBreaker` | Resilience4j CB | 연속 실패 시 요청 차단 |
| `DataStore` | `JpaRepository` | DB CRUD |
| `SlidingWindowRateLimiter` | Bucket4j | API 호출 속도 제한 |
| `StrategyPreset` | `@ConfigurationProperties` | 전략별 설정값 묶음 |
| `ccxt.upbit` | Feign Client (Upbit REST) | 거래소 API 호출 |
| `pandas DataFrame` | `List<Candle>` + Stream API | 시계열 데이터 처리 |

### async/await = CompletableFuture

```python
# Python (TraderJ)                      # Java 비유
async def tick():                       # CompletableFuture<Signal> tick()
    candles = await fetch_ohlcv()       #   .thenCompose(this::fetchOhlcv)
    signal = signal_gen.generate(data)  #   .thenApply(this::generateSignal)
    await order_mgr.execute(signal)     #   .thenCompose(this::executeOrder)
```

Python의 `async/await`는 Java의 `CompletableFuture`와 같은 비동기 처리.
`await`는 "이 작업이 끝날 때까지 기다린다"는 뜻 (블로킹 아님, 논블로킹 대기).

---

## 3. 처리 플로우 (tick 한 사이클)

### 전체 흐름도

```
[Scheduler: 60초마다]
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│                  TradingLoop.tick()                       │
│                 (한 사이클 = 약 0.3초)                    │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ① IPC 명령 확인                                        │
│     "pause/resume/stop 명령이 왔나?"                     │
│         │                                                │
│         ▼                                                │
│  ② 캔들 데이터 수집         ←── Upbit Public API        │
│     fetch_ohlcv(1h, 4h)         (인증 불필요)            │
│     200개 캔들 × 타임프레임 수                           │
│         │                                                │
│         ▼                                                │
│  ③ 현재가 조회 & 이벤트 발행                             │
│     fetch_ticker() → MarketTickEvent                     │
│         │                                                │
│         ▼                                                │
│  ④ 시그널 생성 (8단계 파이프라인)                        │
│     ┌─────────────────────────────────┐                 │
│     │ 지표 계산 (EMA, RSI, MACD...)  │                 │
│     │ Z-score 정규화                  │                 │
│     │ 스코어링 (추세/모멘텀/거래량)  │                 │
│     │ 멀티타임프레임 합산             │                 │
│     │ 매크로 지표 통합               │                 │
│     │ 방향 결정 (BUY/SELL/HOLD)      │                 │
│     └─────────────────────────────────┘                 │
│         │                                                │
│         ▼                                                │
│     ┌── score > +0.20 ──→ BUY ──┐                      │
│     │                            │                      │
│  ⑤ │── score < -0.15 ──→ SELL ──┤── 주문 실행          │
│     │                            │                      │
│     └── 그 외 ──────────→ HOLD ──┘── (아무것도 안 함)   │
│         │                                                │
│         ▼                                                │
│  ⑥ 주문 실행 (BUY 또는 SELL인 경우)                     │
│     ┌─────────────────────────────────┐                 │
│     │ 멱등성 확인 (중복 주문 방지)   │                 │
│     │ CircuitBreaker 확인             │                 │
│     │ 리스크 사전검증                 │                 │
│     │ Paper: 잔액 차감/증가           │                 │
│     │ Live:  Upbit API 주문 실행      │                 │
│     └─────────────────────────────────┘                 │
│         │                                                │
│         ▼                                                │
│  ⑦ 이벤트 발행 & DB 저장                                │
│     Signal → DB                                         │
│     Order → DB                                          │
│     Position 업데이트                                    │
│     EventBus에 이벤트 발행                               │
│         │                                                │
│         ▼                                                │
│  ⑧ 상태 전이                                            │
│     SCANNING → VALIDATING → EXECUTING → LOGGING         │
│                                    → MONITORING          │
│                                                          │
└─────────────────────────────────────────────────────────┘
        │
        ▼
   [60초 후 다시 ①부터 반복]
```

### 한 문장 요약

> **60초마다 시세를 가져오고 → 20개 지표를 계산하고 → 점수를 매기고 → 사고팔지 결정하고 → 주문을 넣는다.**

---

## 4. 시작점부터 마디별 소스 설명

### 4.0 시작점: 엔진 기동

```
engine/__main__.py (진입점)
    │
    ▼
bootstrap.py::bootstrap()          ← 컴포넌트 생성 & 조립
    │
    ├─ DataStore 생성 (PostgreSQL 또는 SQLite)
    ├─ ExchangeClient 생성 (Upbit ccxt 래퍼)
    ├─ EventBus 생성 (비동기 pub/sub)
    ├─ Scheduler 생성 (APScheduler)
    │
    └─ 전략별 반복:
       ├─ SignalGenerator 생성 (프리셋 설정 적용)
       ├─ CircuitBreaker 생성 (실패 3회 → 차단)
       ├─ OrderManager 생성 (주문 처리)
       ├─ PositionManager 생성 (포지션 추적)
       ├─ RiskManager 생성 (리스크 검증)
       ├─ StateMachine 생성 (상태 관리)
       └─ TradingLoop 생성 (위 컴포넌트 주입)
           │
           ▼
       Scheduler에 tick() 등록 (60초 간격)
```

**소스 위치**: `engine/bootstrap.py` (약 220줄)

---

### 4.1 캔들 데이터 수집

```
TradingLoop._fetch_ohlcv()
│
│  소스: engine/loop/trading_loop.py
│
│  하는 일:
│    전략에 설정된 타임프레임(예: 1h, 4h)별로
│    Upbit에서 최근 200개 캔들(봉) 조회
│
│  입력:  symbol="BTC/KRW", timeframe="1h"
│  출력:  {"1h": DataFrame(200행), "4h": DataFrame(200행)}
│
│  호출 체인:
│    exchange.fetch_ohlcv("BTC/KRW", "1h", limit=200)
│      → rate_limiter.acquire()     ← 500req/min 제한
│      → ccxt.upbit.fetch_ohlcv()   ← Upbit REST API 호출
│      → 응답: [[timestamp, open, high, low, close, volume], ...]
│      → Candle 모델로 변환
│      → DataFrame으로 변환
│
│  DataFrame 모양:
│    index(시간)  | open      | high      | low       | close     | volume
│    2024-01-01   | 90000000  | 90500000  | 89500000  | 90200000  | 15.3
│    2024-01-01   | 90200000  | 90800000  | 90100000  | 90600000  | 12.1
│    ...          | ...       | ...       | ...       | ...       | ...
│    (200행)
```

**소스 위치**: `engine/loop/trading_loop.py` → `_fetch_ohlcv()` 메서드

---

### 4.2 기술지표 계산

```
compute_indicators(df)
│
│  소스: engine/strategy/indicators.py
│
│  하는 일:
│    200개 캔들에서 20개 이상의 기술지표를 계산
│    (pandas-ta 라이브러리 사용)
│
│  입력:  DataFrame(200행, 5열: OHLCV)
│  출력:  DataFrame(200행, 25열+: OHLCV + 지표들)
│
│  추가되는 열(지표):
│
│  [추세 지표] — "지금 올라가는 중인가, 내려가는 중인가?"
│    ema_short  (20일 이동평균)    ← 단기 방향
│    ema_medium (50일 이동평균)    ← 중기 방향
│    ema_long   (200일 이동평균)   ← 장기 방향
│    adx        (추세 강도 0~100)  ← 추세가 얼마나 강한가
│
│  [모멘텀 지표] — "얼마나 빠르게 움직이는가?"
│    rsi        (상대강도지수 0~100) ← 70 이상: 과매수, 30 이하: 과매도
│    macd       (이동평균 수렴확산)  ← 양수: 상승세, 음수: 하락세
│    macd_hist  (MACD 히스토그램)    ← 모멘텀 가속/감속
│    stochrsi_k (스토캐스틱 RSI)     ← 80 이상: 과매수, 20 이하: 과매도
│
│  [변동성 지표] — "얼마나 출렁이는가?"
│    atr        (평균진폭)          ← 변동폭 (원 단위)
│    atr_pct    (평균진폭 %)        ← 변동폭 비율
│    bb_upper/lower (볼린저밴드)    ← 가격 밴드 상한/하한
│    bb_pct     (밴드 내 위치 0~1)  ← 1에 가까우면 상단, 0이면 하단
│
│  [거래량 지표] — "사람들이 많이 거래하는가?"
│    obv        (온밸런스 볼륨)     ← 매수세/매도세 축적량
│    volume_ma  (거래량 이동평균)   ← 평균 대비 현재 거래량
│    cmf        (자금흐름 -1~+1)   ← 양수: 매수 유입, 음수: 매도 유출
```

**소스 위치**: `engine/strategy/indicators.py`

---

### 4.3 Z-score 정규화

```
normalize_indicators(df)
│
│  소스: engine/strategy/normalizer.py
│
│  하는 일:
│    각 지표를 "평균 대비 몇 표준편차 떨어져 있는가"로 변환
│    → 서로 다른 단위의 지표들을 같은 척도로 비교 가능하게 함
│
│  비유:
│    키 180cm, 몸무게 80kg를 직접 비교할 수 없듯이
│    Z-score로 변환하면 "평균 대비 +1.5 표준편차" 식으로
│    같은 척도에서 비교 가능
│
│  입력:  macd_hist = 150000 (원 단위, 스케일 큼)
│  출력:  z_macd_hist = +1.2 (표준화, -3 ~ +3 범위)
│
│  정규화 대상:
│    z_macd_hist  ← MACD 히스토그램
│    z_obv_change ← OBV 5봉 변화율
│    z_roc_5      ← 5봉 수익률
│    z_macd_accel ← MACD 가속도
│    z_atr_pct    ← ATR 비율
```

**소스 위치**: `engine/strategy/normalizer.py`

---

### 4.4 스코어링 (점수 산출)

```
scoring.py (3가지 관점에서 점수 산출)
│
│  소스: engine/strategy/filters.py + engine/strategy/scoring.py
│
│  각 타임프레임(1h, 4h)별로 3가지 점수를 매긴다:
│
│  ┌──────────────────────────────────────────────────┐
│  │ [TREND_FOLLOW 모드] (기본)                       │
│  │                                                  │
│  │  s1: 추세 점수 (50%)                             │
│  │    "지금 상승 추세인가?"                         │
│  │    - EMA 정배열: 단기 > 중기 > 장기 → +1.0      │
│  │    - EMA 역배열: 단기 < 중기 < 장기 → -1.0      │
│  │    - 가격이 200일선 위? 아래?                    │
│  │    - ADX 방향: +DI > -DI → 양수                 │
│  │                                                  │
│  │  s2: 모멘텀 점수 (30%)                           │
│  │    "얼마나 힘차게 움직이는가?"                   │
│  │    - RSI 위치 (50 기준 양/음)                    │
│  │    - MACD 히스토그램 방향                         │
│  │    - MACD 골든크로스/데드크로스                   │
│  │    - StochRSI 위치                               │
│  │                                                  │
│  │  s3: 거래량 점수 (20%)                           │
│  │    "시장 참여자가 동의하는가?"                   │
│  │    - 거래량 > 평균? (거래 활발)                  │
│  │    - OBV 증가? (매수세 유입)                     │
│  │    - CMF 양수? (자금 유입)                       │
│  │    - 가격-거래량 일치? (신뢰도)                  │
│  │    - 볼린저 밴드 위치                            │
│  │                                                  │
│  │  타임프레임별 합산 점수:                          │
│  │    combined = s1×0.50 + s2×0.30 + s3×0.20        │
│  │    범위: [-1.0, +1.0]                            │
│  └──────────────────────────────────────────────────┘
│
│  예시:
│    1h: s1=+0.3, s2=+0.4, s3=+0.1
│         → combined = 0.3×0.5 + 0.4×0.3 + 0.1×0.2
│         → combined = 0.15 + 0.12 + 0.02 = +0.29
│
│    4h: s1=+0.1, s2=-0.2, s3=+0.3
│         → combined = 0.1×0.5 + (-0.2)×0.3 + 0.3×0.2
│         → combined = 0.05 - 0.06 + 0.06 = +0.05
```

**소스 위치**: `engine/strategy/filters.py` (6개 스코어 함수), `engine/strategy/scoring.py` (합산)

---

### 4.5 멀티타임프레임 합산 & 방향 결정

```
signal.py::generate() — 최종 결정
│
│  소스: engine/strategy/signal.py + engine/strategy/mtf.py
│
│  [가중합산 방식] (WEIGHTED, 기본)
│    technical = 1h점수 × 0.3 + 4h점수 × 0.7
│
│    예시: 1h=+0.29, 4h=+0.05, 가중치={1h: 0.3, 4h: 0.7}
│      → technical = 0.29×0.3 + 0.05×0.7
│      → technical = 0.087 + 0.035 = +0.122
│
│  [다수결 방식] (MAJORITY, STR-004)
│    "2개 이상 타임프레임이 같은 방향이면 진입"
│
│  [매크로 통합]
│    score = technical × 0.8 + macro × 0.2
│    (매크로 = 공포탐욕지수, 펀딩레이트 등 거시 지표)
│
│  [일일 게이트] (STR-001, STR-005만)
│    "일봉 EMA20 > EMA50이면 매수 허용, 아니면 매수 차단"
│    → 큰 추세가 하락이면 매수하지 않는 안전장치
│
│  [최종 방향 결정]
│  ┌─────────────────────────────────────────────┐
│  │                                             │
│  │   score > +buy_threshold  → BUY  (매수)    │
│  │   score < -sell_threshold → SELL (매도)     │
│  │   그 외                   → HOLD (관망)     │
│  │                                             │
│  │   예: STR-001 (보수적)                      │
│  │     buy_threshold  = 0.20  (확신 있어야 삼) │
│  │     sell_threshold = 0.15  (조금만 나빠도 팜)│
│  │                                             │
│  │   예: STR-002 (공격적)                      │
│  │     buy_threshold  = 0.12  (좀만 좋아도 삼) │
│  │     sell_threshold = 0.08                   │
│  │                                             │
│  │   score=+0.122 vs STR-001(th=0.20)         │
│  │     → 0.122 < 0.20 → HOLD (기준 미달)      │
│  │                                             │
│  │   score=+0.122 vs STR-002(th=0.12)         │
│  │     → 0.122 > 0.12 → BUY! (기준 충족)      │
│  │                                             │
│  └─────────────────────────────────────────────┘
│
│  반환:
│    SignalResult(
│      direction = BUY | SELL | HOLD
│      score     = +0.122
│      details   = {technical: 0.122, macro: 0.1, tf별 상세...}
│    )
```

**소스 위치**: `engine/strategy/signal.py` (generate 메서드)

---

### 4.6 주문 실행

```
OrderManager.handle_order_request()
│
│  소스: engine/execution/order_manager.py
│
│  8단계 주문 파이프라인:
│
│  ① 멱등성 확인
│     "이 주문을 이미 처리했나?" (같은 idempotency_key)
│     → Java의 @Idempotent 또는 Redis 중복방지와 동일
│     → 네트워크 재전송으로 인한 중복 주문 방지
│
│  ② CircuitBreaker 확인
│     "최근에 연속 실패했나?"
│     → 3회 연속 실패 → 5분간 주문 차단 (OPEN 상태)
│     → Java의 Resilience4j CircuitBreaker와 동일 패턴
│
│  ③ 리스크 사전검증
│     "이 주문이 안전한가?"
│     → 일일 손실한도 초과? → 거부
│     → 변동성 너무 높은가? → 거부
│     → 포지션 크기 적절한가? → 조정
│     → 쿨다운 중인가? (연패 후 24시간 휴식) → 거부
│
│  ④ 주문 실행
│     Paper 모드: 잔액에서 가감 (실제 API 호출 없음)
│     Live 모드:  Upbit API로 실제 주문 실행
│
│  ⑤ CircuitBreaker 결과 기록
│     성공 → CB 리셋
│     실패 → 실패 카운트 +1
│
│  ⑥ DB 저장 (orders 테이블)
│
│  ⑦ OrderFilledEvent 발행
│     → PositionManager가 구독하여 포지션 생성/종료
│     → RiskManager가 구독하여 연패 카운트 업데이트
│
│  ⑧ 결과 반환
```

**소스 위치**: `engine/execution/order_manager.py`

---

### 4.7 포지션 관리 & 손절

```
PositionManager
│
│  소스: engine/execution/position_manager.py
│
│  [포지션 생명주기]
│
│    주문체결(BUY)
│        │
│        ▼
│    ┌──────────────┐
│    │   OPEN       │ ← entry_price, amount, stop_loss 기록
│    │   (보유중)   │
│    └──────┬───────┘
│           │
│     ┌─────┴─────┐
│     │ 매 틱마다  │ ← MarketTickEvent 구독
│     │           │
│     │ 미실현PnL │ = (현재가 - 진입가) × 보유량
│     │ 업데이트   │
│     │           │
│     │ 손절 확인  │ → 현재가 <= stop_loss? → 강제 매도
│     └─────┬─────┘
│           │
│     매도 시그널 or 손절
│           │
│           ▼
│    ┌──────────────┐
│    │   CLOSED     │ ← realized_pnl 확정
│    │   (종료)     │
│    └──────────────┘
│
│  [손절가 계산] (RiskManager에서)
│    ATR 기반:  stop_loss = 진입가 - (ATR × 2.0)
│    고정 비율: stop_loss = 진입가 × 0.97 (3% 하락)
│
│    예시: 진입가 90,000,000원, ATR = 1,500,000원
│      → stop_loss = 90,000,000 - (1,500,000 × 2)
│      → stop_loss = 87,000,000원 (3.3% 하락 시 손절)
```

**소스 위치**: `engine/execution/position_manager.py`, `engine/execution/risk_manager.py`

---

## 5. 데이터 처리

### 5.1 데이터 흐름 전체 그림

```
[Upbit API]                    [Engine]                      [DB]
    │                              │                           │
    │  fetch_ohlcv(1h, 200개)     │                           │
    │ ◀────────────────────────── │                           │
    │  [[ts,o,h,l,c,v], ...]     │                           │
    │ ──────────────────────────▶ │                           │
    │                              │                           │
    │                    Candle 모델로 변환                    │
    │                    DataFrame으로 변환                    │
    │                              │                           │
    │                              │  upsert_candles()        │
    │                              │ ─────────────────────── ▶│
    │                              │                           │
    │                    compute_indicators()                  │
    │                    (5열 → 25열+)                         │
    │                              │                           │
    │                    normalize_indicators()                │
    │                    (Z-score 변환)                        │
    │                              │                           │
    │                    score 계산 → SignalResult             │
    │                              │                           │
    │                              │  save_signal()           │
    │                              │ ─────────────────────── ▶│
    │                              │                           │
    │                    [BUY/SELL 결정 시]                    │
    │                              │                           │
    │  fetch_ticker() (현재가)    │                           │
    │ ◀────────────────────────── │                           │
    │  {last: 90000000, ...}      │                           │
    │ ──────────────────────────▶ │                           │
    │                              │                           │
    │                    Paper: 잔액 가감                      │
    │                    Live:  create_order()                 │
    │                              │                           │
    │                              │  save_order()            │
    │                              │  save_position()         │
    │                              │  save_paper_balance()    │
    │                              │ ─────────────────────── ▶│
```

### 5.2 DB 테이블 구조 (핵심만)

```
┌─────────────────────────────────────────────────────────┐
│                     candles (캔들 데이터)                 │
├─────────────────────────────────────────────────────────┤
│  time       │ symbol   │ timeframe │ open ... close     │
│  2024-01-01 │ BTC/KRW  │ 1h        │ 90000000 ... 90.2M│
│  역할: 시계열 가격 데이터 저장 (지표 계산의 원본)        │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                     signals (시그널 기록)                 │
├─────────────────────────────────────────────────────────┤
│  id │ strategy_id │ direction │ score  │ details (JSON) │
│  역할: 매 tick마다 생성된 신호와 상세 근거 기록          │
│  → "왜 이 시점에 BUY/SELL/HOLD 했는지" 추적 가능       │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                     orders (주문 기록)                    │
├─────────────────────────────────────────────────────────┤
│  id │ strategy_id │ side │ amount │ price │ status      │
│  역할: 실행된 매수/매도 주문 기록                        │
│  idempotency_key로 중복 방지                             │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                   positions (포지션)                      │
├─────────────────────────────────────────────────────────┤
│  id │ strategy_id │ entry_price │ current_price │ status│
│  unrealized_pnl │ realized_pnl │ stop_loss             │
│  역할: 현재 보유 중인 자산 + 손익 추적                   │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│               paper_balances (모의투자 잔액)              │
├─────────────────────────────────────────────────────────┤
│  strategy_id │ krw (원화) │ btc (비트코인) │ initial_krw│
│  역할: Paper 모드 가상 잔액 (전략별 독립)                │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                 risk_state (리스크 상태)                  │
├─────────────────────────────────────────────────────────┤
│  strategy_id │ consecutive_losses │ daily_pnl │ cooldown│
│  역할: 연패 횟수, 일일 손실 누적, 쿨다운 시간 추적      │
└─────────────────────────────────────────────────────────┘
```

### 5.3 이벤트 흐름 (EventBus)

```
[이벤트 발행자]              [이벤트]              [구독자]

TradingLoop           MarketTickEvent         PositionManager
  (매 tick)         ──────────────────▶      (미실현PnL 업데이트)
                                              (손절 확인)

TradingLoop           SignalEvent             (로깅, 알림)
  (신호 생성)       ──────────────────▶

OrderManager          OrderFilledEvent        PositionManager
  (주문 체결)       ──────────────────▶      (포지션 생성/종료)
                                              RiskManager
                                              (연패 카운트)

StateMachine          BotStateChangeEvent     (로깅, Dashboard)
  (상태 변경)       ──────────────────▶

PositionManager       StopLossTriggeredEvent  TradingLoop
  (손절 발동)       ──────────────────▶      (강제 매도 실행)
```

Java 비유: `@EventListener` + `ApplicationEventPublisher`와 동일한 패턴.
차이점: asyncio Queue 기반이라 **비동기 비차단** 처리.

---

## 6. 백테스트 / 페이퍼 / 실제 환경 차이

### 한눈에 비교

```
                 ┌──────────────┬──────────────┬──────────────┐
                 │   백테스트    │   페이퍼      │   실전(Live) │
                 │  (Backtest)  │  (Paper)     │              │
┌────────────────┼──────────────┼──────────────┼──────────────┤
│ 데이터 소스    │ 과거 데이터   │ 실시간 시세   │ 실시간 시세  │
│                │ (미리 다운)   │ (Upbit API)  │ (Upbit API)  │
├────────────────┼──────────────┼──────────────┼──────────────┤
│ 주문 실행      │ 가상 체결     │ 가상 체결     │ 실제 주문    │
│                │ (close가로)   │ (현재가로)    │ (Upbit API)  │
├────────────────┼──────────────┼──────────────┼──────────────┤
│ 잔액           │ 시뮬레이션    │ paper_balance│ 실제 계좌    │
│                │ (메모리)      │ (DB 저장)    │ (Upbit 잔고) │
├────────────────┼──────────────┼──────────────┼──────────────┤
│ API 키 필요    │ 불필요        │ 불필요       │ 필수         │
│                │              │ (Public만)   │ (Private)    │
├────────────────┼──────────────┼──────────────┼──────────────┤
│ 실행 속도      │ 수초~수분     │ 실시간       │ 실시간       │
│                │ (30일=수초)   │ (60초/tick)  │ (60초/tick)  │
├────────────────┼──────────────┼──────────────┼──────────────┤
│ 수수료         │ 시뮬레이션    │ 미적용       │ 실제 차감    │
│                │ (0.05%)       │              │ (Upbit 수수) │
├────────────────┼──────────────┼──────────────┼──────────────┤
│ 슬리피지       │ 시뮬레이션    │ 없음         │ 실제 발생    │
│                │ (5bps)        │ (현재가체결)  │ (시장가주문) │
├────────────────┼──────────────┼──────────────┼──────────────┤
│ DB             │ 불필요        │ SQLite       │ PostgreSQL   │
│                │ (메모리)      │ (인메모리)   │ (Docker)     │
├────────────────┼──────────────┼──────────────┼──────────────┤
│ 용도           │ 전략 검증     │ 실전 전 테스트│ 실제 거래    │
│                │ 파라미터 최적화│ 리스크 없음  │              │
└────────────────┴──────────────┴──────────────┴──────────────┘
```

### 각 모드 상세

#### 백테스트 (Backtest)

```
┌────────────────────────────────────────────────────────┐
│  "과거 데이터로 전략이 돈을 벌었을지 시뮬레이션"       │
│                                                        │
│  실행: python -m scripts.run_backtest_all               │
│                                                        │
│  작동 방식:                                            │
│    1. Upbit에서 과거 90일 캔들 다운로드 (1회)          │
│    2. 시간순으로 한 봉씩 순차 처리                     │
│       (미래 데이터 참조 불가 = look-ahead bias 방지)   │
│    3. 각 봉에서 signal_gen.generate() 호출              │
│    4. BUY/SELL 시 가상 잔액 가감                       │
│    5. 수수료(0.05%) + 슬리피지(5bps) 반영              │
│    6. 결과 메트릭 계산:                                │
│       - 총 수익률, 승률, Sharpe Ratio                  │
│       - 최대 낙폭(MDD), Profit Factor                  │
│       - 연속 승/패 기록                                │
│                                                        │
│  특징:                                                 │
│    - 수초 만에 30일치 시뮬레이션 완료                  │
│    - API 키 불필요 (Public API로 데이터 다운)          │
│    - 7개 전략 일괄 비교 가능                           │
│    - 과거 성과 ≠ 미래 성과 (과적합 주의)               │
│                                                        │
│  소스: engine/strategy/backtest/engine.py               │
│  스크립트: scripts/run_backtest_all.py                  │
└────────────────────────────────────────────────────────┘
```

#### 페이퍼 트레이딩 (Paper)

```
┌────────────────────────────────────────────────────────┐
│  "실시간 시세로 거래하되, 진짜 돈은 안 쓴다"           │
│                                                        │
│  실행: python -m scripts.run_paper STR-005              │
│                                                        │
│  작동 방식:                                            │
│    1. 가상 잔액 1,000만원으로 시작                     │
│    2. 60초마다 Upbit에서 실시간 시세 조회              │
│    3. signal_gen.generate()로 신호 생성                │
│    4. BUY → paper_balance에서 KRW 차감, BTC 증가      │
│    5. SELL → BTC 차감, KRW 증가                       │
│    6. DB에 모든 거래/신호 기록                         │
│                                                        │
│  실전과의 차이:                                        │
│    - 주문이 항상 100% 체결됨 (실전은 부분체결 가능)    │
│    - 슬리피지 없음 (실전은 호가 차이로 손해)           │
│    - 수수료 미적용 (실전은 0.05% 차감)                │
│    - 시장 충격 없음 (큰 주문도 가격 영향 없음)        │
│                                                        │
│  소스: engine/execution/order_manager.py                │
│       (_execute_paper 메서드)                           │
│  스크립트: scripts/run_paper.py                        │
└────────────────────────────────────────────────────────┘
```

#### 실전 트레이딩 (Live)

```
┌────────────────────────────────────────────────────────┐
│  "진짜 돈으로 자동 매매"                               │
│                                                        │
│  실행: docker compose up (TRADING_MODE=live)            │
│                                                        │
│  작동 방식:                                            │
│    1. Upbit API 키로 인증                              │
│    2. 60초마다 시세 조회 + 신호 생성                   │
│    3. BUY → exchange.create_order() 실제 주문 실행     │
│    4. 주문 체결 확인 (3초 간격 × 3회 폴링)            │
│    5. 실제 체결 가격 기록 (슬리피지 포함)              │
│    6. 포지션 + 잔고 실시간 추적                        │
│                                                        │
│  추가 안전장치:                                        │
│    - CircuitBreaker: 3연속 실패 → 5분 차단             │
│    - RiskManager: 일일 손실 5% 초과 → 거래 중단        │
│    - 연속 3패 → 24시간 쿨다운                          │
│    - ATR 8% 초과 (고변동성) → 거래 차단                │
│    - Emergency Stop: 모든 포지션 즉시 청산              │
│                                                        │
│  소스: engine/execution/order_manager.py                │
│       (_execute_live 메서드)                            │
│  환경: Docker + PostgreSQL                              │
└────────────────────────────────────────────────────────┘
```

### 코드 레벨에서의 분기점

```python
# engine/execution/order_manager.py 에서

async def handle_order_request(event):
    # ... 공통 로직 (멱등성, CB, 리스크 검증) ...

    if self._trading_mode == TradingMode.PAPER:
        # Paper: DB의 가상 잔액만 조작
        result = await self._execute_paper(event)
        #   → store.get_paper_balance()
        #   → balance.krw -= cost
        #   → store.save_paper_balance()

    elif self._trading_mode == TradingMode.LIVE:
        # Live: 실제 Upbit API 호출
        result = await self._execute_live(event)
        #   → exchange.create_order()    ← 실제 주문!
        #   → exchange.fetch_order()     ← 체결 확인
        #   → 슬리피지 계산

    # ... 공통 로직 (DB 저장, 이벤트 발행) ...
```

---

## 7. 7개 전략 프리셋

```
┌──────────┬────────────────────┬──────────┬────────────┬──────────┐
│ 전략 ID  │ 이름               │ 매수기준 │ 주요TF     │ 특징     │
├──────────┼────────────────────┼──────────┼────────────┼──────────┤
│ default  │ 기본 추세추종      │ > +0.15  │ 1h, 4h     │ 기본값   │
│ STR-001  │ 보수적 추세        │ > +0.20  │ 4h (70%)   │ 일일게이트│
│ STR-002  │ 공격적 추세        │ > +0.12  │ 1h (50%)   │ 15m 포함 │
│ STR-003  │ 하이브리드 반전    │ > +0.15  │ 1h, 4h     │ 과매수반전│
│ STR-004  │ 다수결 투표        │ > +0.15  │ 1h, 4h     │ 2TF 합의 │
│ STR-005  │ 저빈도 보수적      │ > +0.25  │ 4h, 1d     │ 매우 신중│
│ STR-006  │ 스캘퍼             │ > +0.10  │ 15m, 1h    │ 빈번 매매│
└──────────┴────────────────────┴──────────┴────────────┴──────────┘

해석:
  - buy_threshold가 높을수록 → 확신이 있어야 매수 (보수적)
  - buy_threshold가 낮을수록 → 조금만 좋아도 매수 (공격적)
  - TF(타임프레임)가 클수록 → 장기 추세 중시 (느린 반응)
  - TF가 작을수록 → 단기 움직임 중시 (빠른 반응)
```

**소스 위치**: `engine/strategy/presets.py`

---

## 8. 주요 안전장치

### 계층별 안전장치

```
[Level 1: 신호 생성 단계]
  │
  ├─ 일일 게이트: 큰 추세가 하락이면 매수 차단
  ├─ 임계값: 점수가 충분히 높아야만 매수/매도
  └─ HOLD: 확신 없으면 아무것도 안 함
  │
[Level 2: 리스크 검증 단계]
  │
  ├─ 일일 손실 한도: 하루 5% 이상 잃으면 거래 중단
  ├─ 변동성 상한: ATR 8% 이상이면 거래 차단
  ├─ 포지션 크기: 변동성 높으면 적게, 낮으면 많이
  ├─ 연패 쿨다운: 3연패 → 24시간 거래 중단
  └─ 최소 주문금액: 5,000원 미만 주문 거부
  │
[Level 3: 주문 실행 단계]
  │
  ├─ 멱등성: 같은 주문 2번 실행 방지
  ├─ CircuitBreaker: 3연속 API 실패 → 5분 차단
  └─ 잔액 확인: 잔액 부족하면 주문 거부
  │
[Level 4: 포지션 관리 단계]
  │
  ├─ 손절(Stop-Loss): ATR×2 하락 시 자동 매도
  └─ Emergency Stop: 모든 포지션 즉시 청산 (수동)
```

### 상태머신 (9개 상태)

```
  IDLE (대기)
    │
    ▼
  STARTING (초기화)
    │
    ▼
  SCANNING (시장 감시) ◀──────────────────────────┐
    │                                              │
    ▼                                              │
  VALIDATING (신호 검증)                           │
    │                                              │
    ├── BUY/SELL → EXECUTING (주문 실행)           │
    │                  │                           │
    │                  ▼                           │
    │              LOGGING (결과 기록)              │
    │                  │                           │
    │                  ▼                           │
    │              MONITORING (모니터링) ──────────┘
    │                                     (60초 후)
    └── HOLD ──────────────────────────────────────┘

  PAUSED (일시중지) ←→ SCANNING (재개)

  SHUTTING_DOWN (종료중) → IDLE
```

Java 비유: Spring State Machine과 동일한 패턴.
각 상태 전이는 DB에 기록되어 엔진 재시작 시 복구 가능.

---

## 부록: 실행 명령어 모음

```bash
# 백테스트 (7개 전략 일괄)
python -m scripts.run_backtest_all

# 페이퍼 트레이딩 (연속 실행, Ctrl+C로 종료)
python -m scripts.run_paper STR-005

# 페이퍼 트레이딩 (10회만 실행)
python -m scripts.run_paper --ticks 10 STR-005

# 멀티 전략 동시 실행
python -m scripts.run_paper STR-001 STR-002

# 유닛 테스트
python -m pytest engine/tests/unit/ -v

# 통합 테스트
python -m pytest engine/tests/integration/ -v

# 전체 테스트
python -m pytest engine/tests/ -v
```
