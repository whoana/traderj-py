# Round 4: 시스템 아키텍처 상세 설계서

**작성일**: 2026-03-02
**작성자**: bot-developer (아키텍처 도메인)
**기반**: Round 3 TDR (Rev.1) + Round 2 요구사항서 3건
**상태**: Draft — 팀 리더 검토 대기

---

## 목차

1. [시스템 개요](#1-시스템-개요)
2. [모듈 다이어그램](#2-모듈-다이어그램)
3. [프로젝트 구조](#3-프로젝트-구조)
4. [DB 스키마 설계](#4-db-스키마-설계)
5. [이벤트 버스 설계](#5-이벤트-버스-설계)
6. [거래소 추상화 레이어](#6-거래소-추상화-레이어)
7. [주문 관리 흐름](#7-주문-관리-흐름)
8. [API 서버 설계](#8-api-서버-설계)
9. [WebSocket 설계](#9-websocket-설계)
10. [배포 아키텍처](#10-배포-아키텍처)
11. [교차 도메인 계약 요약](#11-교차-도메인-계약-요약)
12. [구현 순서 및 마일스톤](#12-구현-순서-및-마일스톤)

---

## 1. 시스템 개요

### 1.1 아키텍처 스타일

**이벤트 주도 모놀리식** (Event-Driven Monolith) — 서비스별 Docker 컨테이너 분리

```
┌─────────────────────────────────────────────────────────────────┐
│                    docker-compose 네트워크                        │
│                                                                   │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────┐ │
│  │ engine   │   │ api      │   │ dashboard│   │ postgres     │ │
│  │ (Python) │──→│ (FastAPI)│──→│ (Next.js)│   │ (TimescaleDB)│ │
│  │          │   │          │   │          │   │              │ │
│  │ EventBus │   │ REST+WS  │   │ Zustand  │   │ hypertable   │ │
│  │ Strategy │   │ Bridge   │   │ LW Charts│   │ asyncpg      │ │
│  │ Execution│   │          │   │ shadcn   │   │              │ │
│  └────┬─────┘   └────┬─────┘   └──────────┘   └──────┬───────┘ │
│       │              │                                 │         │
│       └──────────────┴─────────────────────────────────┘         │
│                   shared PostgreSQL 접근                           │
│                                                                   │
│  ┌──────────┐   ┌──────────┐                                    │
│  │prometheus│   │ grafana  │                                    │
│  └──────────┘   └──────────┘                                    │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 설계 원칙 (Round 2 확정)

| 원칙 | 적용 방법 |
|------|----------|
| Event-Driven | EventBus 발행/구독. 컴포넌트 직접 참조 금지 |
| Protocol-First | Python `Protocol`로 모든 외부 의존성 추상화 |
| Persistence-First Risk | 리스크 상태 DB 즉시 영속화 (write-through) |
| Observable | structlog JSON + Prometheus 13개 커스텀 메트릭 |
| Fail-Safe | 장애 시 포지션 보호 우선 (거래 중단 > 잘못된 거래) |
| Decimal Precision | 금융 데이터에 `Decimal` 사용, API 전달 시 `string` |

---

## 2. 모듈 다이어그램

### 2.1 Engine 서비스 내부

```
engine/
┌────────────────────────────────────────────────────────────────┐
│                         AppOrchestrator                         │
│  (DI 컨테이너, 수명주기 관리, 시그널 핸들러)                        │
├────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────────┐  │
│  │ Exchange │    │  EventBus    │    │    Scheduler         │  │
│  │ Adapter  │    │ (asyncio)    │    │  (APScheduler)       │  │
│  │          │    │              │    │                      │  │
│  │ ┌──────┐ │    │  publish()   │    │  OHLCV collect       │  │
│  │ │Upbit │ │    │  subscribe() │    │  MacroSnapshot       │  │
│  │ │Client│ │    │  unsubscribe│    │  DailyPnL calc       │  │
│  │ └──────┘ │    └───────┬──────┘    │  HealthCheck         │  │
│  │ ┌──────┐ │            │           └──────────────────────┘  │
│  │ │Upbit │ │            │                                      │
│  │ │WS    │ │    ┌───────▼──────────────────────────┐          │
│  │ └──────┘ │    │          Event Flow               │          │
│  └──────────┘    │                                    │          │
│                  │  MarketTick ──→ RiskManager         │          │
│  ┌──────────┐    │  OHLCVUpdate ──→ StrategyEngine    │          │
│  │DataStore │    │  Signal ──→ ExecutionEngine         │          │
│  │(asyncpg) │    │  OrderRequest ──→ OrderManager      │          │
│  │          │    │  OrderFilled ──→ PositionManager    │          │
│  │ candles  │    │  Position ──→ RiskManager           │          │
│  │ orders   │    │  StopLoss ──→ ExecutionEngine       │          │
│  │ positions│    │  RiskAlert ──→ Notifier             │          │
│  │ risk     │    │  StateChange ──→ Logger             │          │
│  └──────────┘    └──────────────────────────────────┘          │
│                                                                  │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │Strategy  │    │ Execution    │    │ Notify       │          │
│  │Engine    │    │ Engine       │    │ (Telegram)   │          │
│  │          │    │              │    │              │          │
│  │ Signal   │    │ OrderManager │    │ trade alert  │          │
│  │ Generator│    │ PositionMgr  │    │ stop-loss    │          │
│  │ Indicator│    │ RiskManager  │    │ daily summary│          │
│  │ MTF      │    │ StateMachine │    │ error alert  │          │
│  │ MacroScr │    │ CircuitBreak│    │              │          │
│  └──────────┘    └──────────────┘    └──────────────┘          │
└────────────────────────────────────────────────────────────────┘
```

### 2.2 API 서비스 내부

```
api/
┌────────────────────────────────────────────────────────┐
│                   FastAPI Application                    │
├────────────────────────────────────────────────────────┤
│                                                          │
│  ┌───────────────────────────────────────────────────┐  │
│  │  REST Routes                                       │  │
│  │  /api/v1/bots       → BotController               │  │
│  │  /api/v1/positions  → PositionController           │  │
│  │  /api/v1/orders     → OrderController              │  │
│  │  /api/v1/candles    → CandleController             │  │
│  │  /api/v1/signals    → SignalController              │  │
│  │  /api/v1/pnl        → PnLController                │  │
│  │  /api/v1/risk       → RiskController               │  │
│  │  /api/v1/macro      → MacroController              │  │
│  │  /api/v1/analytics  → AnalyticsController          │  │
│  │  /api/v1/health     → HealthController             │  │
│  └───────────────────────────────────────────────────┘  │
│                                                          │
│  ┌───────────────────────────────────────────────────┐  │
│  │  WebSocket Handler                                 │  │
│  │  /ws/v1/stream   → WSConnectionManager            │  │
│  │                   → ChannelSubscriber              │  │
│  │                   → HeartbeatManager               │  │
│  └───────────────────────────────────────────────────┘  │
│                                                          │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ DataStore   │  │ EngineClient │  │ Middleware    │  │
│  │ (read-only) │  │ (IPC/HTTP)   │  │ - auth       │  │
│  │             │  │              │  │ - cors       │  │
│  │ candles     │  │ bot control  │  │ - metrics    │  │
│  │ orders      │  │ emergency    │  │ - error      │  │
│  │ positions   │  │ state query  │  │              │  │
│  └─────────────┘  └──────────────┘  └──────────────┘  │
└────────────────────────────────────────────────────────┘
```

### 2.3 서비스 간 통신

```
┌────────────┐     IPC (Unix Socket)      ┌───────────┐
│   engine   │ ←─────────────────────────→ │    api    │
│            │                              │           │
│ EventBus   │  1. bot control (api→engine)│ REST      │
│ DB write   │  2. state query (api→engine)│ WebSocket │
│ Exchange   │  3. event push (engine→api) │ DB read   │
└────────────┘                              └───────────┘
       │                                         │
       │         ┌────────────────┐              │
       └─────────│   PostgreSQL   │──────────────┘
                 │  (TimescaleDB) │
                 └────────────────┘
```

**Engine ↔ API IPC 프로토콜**: Unix Domain Socket (`/tmp/traderj.sock`)
- **api → engine**: 봇 제어 명령 (start/stop/pause/resume/emergency-exit)
- **engine → api**: 이벤트 스트림 push (ticker, signal, order, position, state change)
- 프로토콜: JSON-lines over UDS (각 메시지는 `\n`으로 구분된 JSON)
- Fallback: 같은 PostgreSQL에 `bot_commands` 테이블로 큐잉 (UDS 장애 시)

---

## 3. 프로젝트 구조

> TDR-007 Rev.1 확정 구조 (서비스별 최상위 분리)

```
traderj/
├── docker-compose.yml
├── docker-compose.dev.yml          # 개발용 오버라이드 (SQLite, 볼륨 마운트)
├── .github/workflows/
│   ├── engine.yml
│   ├── api.yml
│   └── dashboard.yml
├── .env.example
├── Makefile                        # make engine-test, make api-test, make up 등
│
├── shared/                         # 공유 Python 패키지
│   ├── pyproject.toml              # name = "traderj-shared"
│   └── shared/
│       ├── __init__.py
│       ├── models.py               # Candle, Order, Position, Signal, RiskState, ...
│       ├── events.py               # MarketTickEvent, SignalEvent, OrderFilledEvent, ...
│       ├── protocols.py            # DataStore, ExchangeClient, WebSocketStream, ...
│       ├── enums.py                # OrderSide, OrderType, OrderStatus, ...
│       └── py.typed
│
├── engine/                         # 트레이딩 엔진
│   ├── pyproject.toml              # dependencies: traderj-shared (path), asyncpg, ccxt, ...
│   ├── Dockerfile
│   └── engine/
│       ├── __init__.py
│       ├── app.py                  # AppOrchestrator (DI, lifecycle)
│       ├── config/
│       │   ├── settings.py         # pydantic-settings (env-based)
│       │   └── params.py           # STRATEGY_PRESETS dict
│       ├── exchange/
│       │   ├── client.py           # UpbitExchangeClient (ExchangeClient Protocol 구현)
│       │   ├── websocket.py        # UpbitWebSocketStream (WebSocketStream Protocol 구현)
│       │   ├── rate_limiter.py     # SlidingWindowRateLimiter
│       │   └── models.py           # 거래소 특화 변환 로직
│       ├── data/
│       │   ├── pg_store.py         # PostgresDataStore (DataStore Protocol 구현)
│       │   ├── sqlite_store.py     # SQLiteDataStore (dev/test용)
│       │   ├── analytics_store.py  # DuckDBAnalyticsStore (AnalyticsStore Protocol 구현)
│       │   ├── ohlcv.py            # OHLCVCollector (스케줄러 잡)
│       │   └── macro.py            # MacroCollector (Fear&Greed, DXY, Funding Rate)
│       ├── strategy/
│       │   ├── signal.py           # SignalGenerator
│       │   ├── indicators.py       # pandas-ta 래퍼 + Z-score 정규화
│       │   ├── mtf.py              # MultiTimeframeAggregator
│       │   ├── macro_scorer.py     # MacroScoreCalculator
│       │   ├── filters.py          # DailyGate, VolatilityCap, TrendFilter
│       │   └── plugins/            # ScorePlugin 구현체 디렉터리
│       │       └── lgbm_plugin.py  # LightGBM ML 플러그인 (P2)
│       ├── execution/
│       │   ├── order_manager.py    # OrderManager (멱등성, 확인 루프, 슬리피지)
│       │   ├── position_manager.py # PositionManager (open/close, PnL 계산)
│       │   ├── risk.py             # RiskManager (영속화, 쿨다운, circuit breaker)
│       │   └── circuit_breaker.py  # CircuitBreaker (CLOSED/OPEN/HALF_OPEN)
│       ├── loop/
│       │   ├── event_bus.py        # AsyncioEventBus
│       │   ├── scheduler.py        # APScheduler 래퍼
│       │   ├── state.py            # StateMachine (9 states, DB 영속화)
│       │   └── ipc_server.py       # Unix Domain Socket 서버 (API 서비스 ↔ Engine)
│       └── notify/
│           └── telegram.py         # TelegramNotifier
│
├── api/                            # FastAPI API 서버
│   ├── pyproject.toml              # dependencies: traderj-shared (path), fastapi, asyncpg, ...
│   ├── Dockerfile
│   └── api/
│       ├── __init__.py
│       ├── main.py                 # FastAPI app factory
│       ├── deps.py                 # 의존성 주입 (DataStore, EngineClient)
│       ├── routes/
│       │   ├── bots.py             # /api/v1/bots
│       │   ├── positions.py        # /api/v1/positions
│       │   ├── orders.py           # /api/v1/orders
│       │   ├── candles.py          # /api/v1/candles
│       │   ├── signals.py          # /api/v1/signals
│       │   ├── pnl.py              # /api/v1/pnl
│       │   ├── risk.py             # /api/v1/risk
│       │   ├── macro.py            # /api/v1/macro
│       │   ├── analytics.py        # /api/v1/analytics
│       │   └── health.py           # /api/v1/health
│       ├── ws/
│       │   ├── handler.py          # WebSocket 연결 관리, 채널 구독/해지
│       │   ├── channels.py         # 채널별 브로드캐스터 (ticker, bot_status, ...)
│       │   └── heartbeat.py        # ping/pong 하트비트 관리
│       ├── schemas/
│       │   ├── bot.py              # BotResponse, BotControlResponse
│       │   ├── position.py         # PositionResponse
│       │   ├── order.py            # OrderResponse
│       │   ├── signal.py           # SignalResponse
│       │   ├── pnl.py              # DailyPnLResponse, PnLAnalytics
│       │   ├── risk.py             # RiskStateResponse
│       │   └── common.py           # PaginatedResponse[T]
│       ├── middleware/
│       │   ├── auth.py             # X-API-Key 인증
│       │   ├── cors.py             # CORS 설정
│       │   └── metrics.py          # Prometheus 미들웨어
│       └── ipc_client.py           # Unix Domain Socket 클라이언트 (→ Engine)
│
├── dashboard/                      # Next.js 프론트엔드
│   ├── package.json
│   ├── Dockerfile
│   ├── next.config.ts
│   ├── src/
│   │   ├── app/                    # App Router
│   │   ├── components/             # UI 컴포넌트
│   │   ├── stores/                 # Zustand 스토어
│   │   ├── lib/                    # API 클라이언트, WebSocket 훅
│   │   └── types/                  # OpenAPI 자동 생성 타입
│   └── tailwind.config.ts
│
├── scripts/
│   ├── migrate_to_pg.py            # SQLite → PostgreSQL 마이그레이션
│   ├── generate_api_types.sh       # openapi-typescript 실행
│   └── export_parquet.py           # PostgreSQL → Parquet 익스포트 (DuckDB용)
│
├── migrations/                     # Alembic
│   ├── alembic.ini
│   ├── env.py
│   └── versions/
│       ├── 001_initial_schema.py
│       └── 002_timescaledb_setup.py
│
├── tests/                          # 통합 테스트 (서비스 횡단)
│   └── integration/
│       ├── test_engine_api_ipc.py
│       └── test_full_trade_cycle.py
│
└── docs/
```

---

## 4. DB 스키마 설계

### 4.1 PostgreSQL + TimescaleDB (OLTP)

#### candles (hypertable)

```sql
CREATE TABLE candles (
    time        TIMESTAMPTZ     NOT NULL,
    symbol      TEXT            NOT NULL,
    timeframe   TEXT            NOT NULL,
    open        NUMERIC(18,8)   NOT NULL,
    high        NUMERIC(18,8)   NOT NULL,
    low         NUMERIC(18,8)   NOT NULL,
    close       NUMERIC(18,8)   NOT NULL,
    volume      NUMERIC(24,8)   NOT NULL,
    UNIQUE(symbol, timeframe, time)
);

SELECT create_hypertable('candles', by_range('time'));

-- 자동 보존 정책 (2년)
SELECT add_retention_policy('candles', INTERVAL '2 years');

-- 연속 집계 (대시보드 일별 요약)
CREATE MATERIALIZED VIEW candles_1d_summary
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 day', time) AS bucket,
       symbol,
       first(open, time) AS open,
       max(high) AS high,
       min(low) AS low,
       last(close, time) AS close,
       sum(volume) AS volume
FROM candles
WHERE timeframe = '1h'
GROUP BY bucket, symbol;

SELECT add_continuous_aggregate_policy('candles_1d_summary',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');
```

#### signals

```sql
CREATE TABLE signals (
    id              SERIAL          PRIMARY KEY,
    timestamp       TIMESTAMPTZ     NOT NULL,
    symbol          TEXT            NOT NULL,
    strategy_id     TEXT            NOT NULL,
    direction       TEXT            NOT NULL,  -- BUY | SELL | HOLD
    score           REAL            NOT NULL,
    timeframe       TEXT            NOT NULL,
    components      JSONB           NOT NULL,  -- {trend, momentum, volume, macro, tf_scores}
    details         JSONB           DEFAULT '{}',
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_signals_strategy_ts ON signals(strategy_id, timestamp DESC);
CREATE INDEX idx_signals_symbol_ts ON signals(symbol, timestamp DESC);
```

#### orders

```sql
CREATE TABLE orders (
    id              SERIAL          PRIMARY KEY,
    exchange_id     TEXT,
    symbol          TEXT            NOT NULL,
    side            TEXT            NOT NULL,  -- buy | sell
    order_type      TEXT            NOT NULL,  -- market | limit
    amount          NUMERIC(18,8)   NOT NULL,
    price           NUMERIC(18,8),
    cost            NUMERIC(18,8),
    fee             NUMERIC(18,8)   NOT NULL DEFAULT 0,
    status          TEXT            NOT NULL DEFAULT 'pending',
    is_paper        BOOLEAN         NOT NULL DEFAULT TRUE,
    signal_id       INTEGER         REFERENCES signals(id),
    strategy_id     TEXT            NOT NULL,
    idempotency_key TEXT            NOT NULL UNIQUE,
    expected_price  NUMERIC(18,8),
    actual_price    NUMERIC(18,8),
    slippage_pct    REAL,
    retry_count     INTEGER         NOT NULL DEFAULT 0,
    error_message   TEXT,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    filled_at       TIMESTAMPTZ
);

CREATE INDEX idx_orders_strategy_ts ON orders(strategy_id, created_at DESC);
CREATE INDEX idx_orders_status ON orders(status) WHERE status = 'pending';
CREATE INDEX idx_orders_idempotency ON orders(idempotency_key);
```

#### positions

```sql
CREATE TABLE positions (
    id              SERIAL          PRIMARY KEY,
    symbol          TEXT            NOT NULL,
    side            TEXT            NOT NULL DEFAULT 'long',
    entry_price     NUMERIC(18,8)   NOT NULL,
    amount          NUMERIC(18,8)   NOT NULL,
    current_price   NUMERIC(18,8)   NOT NULL DEFAULT 0,
    stop_loss       NUMERIC(18,8)   NOT NULL DEFAULT 0,
    unrealized_pnl  NUMERIC(18,2)   NOT NULL DEFAULT 0,
    realized_pnl    NUMERIC(18,2)   NOT NULL DEFAULT 0,
    status          TEXT            NOT NULL DEFAULT 'open',
    entry_order_id  INTEGER         REFERENCES orders(id),
    exit_order_id   INTEGER         REFERENCES orders(id),
    strategy_id     TEXT            NOT NULL,
    opened_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    closed_at       TIMESTAMPTZ
);

CREATE INDEX idx_positions_open ON positions(strategy_id, status) WHERE status = 'open';
CREATE INDEX idx_positions_strategy_ts ON positions(strategy_id, opened_at DESC);
```

#### risk_state

```sql
CREATE TABLE risk_state (
    strategy_id         TEXT            PRIMARY KEY,
    consecutive_losses  INTEGER         NOT NULL DEFAULT 0,
    daily_pnl           NUMERIC(18,2)   NOT NULL DEFAULT 0,
    daily_date          DATE            NOT NULL DEFAULT CURRENT_DATE,
    cooldown_until      TIMESTAMPTZ,
    total_trades        INTEGER         NOT NULL DEFAULT 0,
    total_wins          INTEGER         NOT NULL DEFAULT 0,
    last_atr            REAL,           -- P0-S2: 최근 ATR 값 캐시
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);
```

#### bot_state

```sql
CREATE TABLE bot_state (
    strategy_id     TEXT            PRIMARY KEY,
    state           TEXT            NOT NULL DEFAULT 'IDLE',
    trading_mode    TEXT            NOT NULL DEFAULT 'paper',
    started_at      TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);
```

#### paper_balances

```sql
CREATE TABLE paper_balances (
    strategy_id     TEXT            PRIMARY KEY,
    krw             NUMERIC(18,2)   NOT NULL DEFAULT 10000000,
    btc             NUMERIC(18,8)   NOT NULL DEFAULT 0,
    initial_krw     NUMERIC(18,2)   NOT NULL DEFAULT 10000000,
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);
```

#### daily_pnl

```sql
CREATE TABLE daily_pnl (
    id              SERIAL          PRIMARY KEY,
    date            DATE            NOT NULL,
    strategy_id     TEXT            NOT NULL,
    realized        NUMERIC(18,2)   NOT NULL DEFAULT 0,
    unrealized      NUMERIC(18,2)   NOT NULL DEFAULT 0,
    total_value     NUMERIC(18,2)   NOT NULL DEFAULT 0,
    trade_count     INTEGER         NOT NULL DEFAULT 0,
    win_count       INTEGER         NOT NULL DEFAULT 0,
    loss_count      INTEGER         NOT NULL DEFAULT 0,
    UNIQUE(date, strategy_id)
);
```

#### macro_snapshots

```sql
CREATE TABLE macro_snapshots (
    id              SERIAL          PRIMARY KEY,
    timestamp       TIMESTAMPTZ     NOT NULL,
    fear_greed      REAL,
    btc_dominance   REAL,
    dxy             REAL,
    nasdaq          REAL,
    kimchi_premium  REAL,
    funding_rate    REAL,           -- P1-S1: Binance funding rate
    btc_dom_7d_change REAL,        -- P1-S1: BTC 도미넌스 7일 변화율
    market_score    REAL,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_macro_ts ON macro_snapshots(timestamp DESC);
```

#### backtest_results (P1)

```sql
-- UUID PK + JSONB 기반 (전략 설계서 §8.1 정본)
-- 백테스트 메트릭은 유동적이며 JSONB가 확장성에 유리
CREATE TABLE backtest_results (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id     TEXT            NOT NULL,
    params_hash     TEXT            NOT NULL,
    config_json     JSONB           NOT NULL,     -- 전략 설정 (프리셋, 파라미터)
    metrics_json    JSONB           NOT NULL,     -- {sharpe, sortino, calmar, mdd, win_rate, ...}
    equity_curve_json JSONB,                      -- [{timestamp, equity, drawdown}]
    trades_json     JSONB,                        -- [{entry_time, exit_time, pnl_pct, ...}]
    walk_forward_json JSONB,                      -- Walk-forward fold별 결과
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_bt_strategy ON backtest_results(strategy_id);
CREATE INDEX idx_bt_created ON backtest_results(created_at DESC);
```

#### bot_commands (IPC fallback 큐)

```sql
CREATE TABLE bot_commands (
    id              SERIAL          PRIMARY KEY,
    strategy_id     TEXT            NOT NULL,
    command         TEXT            NOT NULL,  -- start | stop | pause | resume | emergency_exit
    payload         JSONB           DEFAULT '{}',
    status          TEXT            NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    processed_at    TIMESTAMPTZ
);

CREATE INDEX idx_bot_commands_pending ON bot_commands(status, created_at)
    WHERE status = 'pending';
```

### 4.2 DuckDB (OLAP 보조 — P1)

> DuckDB는 파일 기반 임베디드 DB. `data/analytics.duckdb`에 저장.
> PostgreSQL → Parquet → DuckDB 파이프라인으로 데이터 로드.

```sql
-- DuckDB 스키마 (자동 생성)
CREATE TABLE candles AS
    SELECT * FROM read_parquet('data/exports/candles_*.parquet');

CREATE TABLE signals AS
    SELECT * FROM read_parquet('data/exports/signals_*.parquet');

CREATE TABLE orders AS
    SELECT * FROM read_parquet('data/exports/orders_*.parquet');
```

**익스포트 파이프라인** (`scripts/export_parquet.py`):
1. `COPY (SELECT * FROM candles WHERE time >= $1) TO STDOUT WITH (FORMAT PARQUET)`
2. Parquet 파일을 `data/exports/` 에 저장
3. 백테스트 실행 전 1회 호출

---

## 5. 이벤트 버스 설계

### 5.1 핵심 이벤트 타입

```python
# shared/events.py

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

@dataclass(frozen=True)
class MarketTickEvent:
    timestamp: datetime
    symbol: str
    price: Decimal
    bid: Decimal
    ask: Decimal
    volume_24h: Decimal
    source: str  # "websocket" | "rest_poll"

@dataclass(frozen=True)
class OHLCVUpdateEvent:
    timestamp: datetime
    symbol: str
    timeframe: str
    candles: list  # list[Candle]

@dataclass(frozen=True)
class SignalEvent:
    timestamp: datetime
    strategy_id: str
    symbol: str
    direction: str  # BUY | SELL | HOLD
    score: float
    timeframe: str
    components: dict  # {trend, momentum, volume, macro}
    details: dict = field(default_factory=dict)

@dataclass(frozen=True)
class OrderRequestEvent:
    timestamp: datetime
    strategy_id: str
    symbol: str
    side: str  # buy | sell
    amount: Decimal
    order_type: str  # market | limit
    price: Decimal | None = None
    idempotency_key: str = ""

@dataclass(frozen=True)
class OrderFilledEvent:
    timestamp: datetime
    order_id: int
    exchange_id: str
    strategy_id: str
    symbol: str
    side: str
    amount: Decimal
    actual_price: Decimal
    cost: Decimal
    fee: Decimal
    slippage_pct: float

@dataclass(frozen=True)
class PositionOpenedEvent:
    timestamp: datetime
    position_id: int
    strategy_id: str
    symbol: str
    entry_price: Decimal
    amount: Decimal
    stop_loss: Decimal

@dataclass(frozen=True)
class PositionClosedEvent:
    timestamp: datetime
    position_id: int
    strategy_id: str
    symbol: str
    realized_pnl: Decimal
    exit_reason: str  # signal | stop_loss | emergency | manual

@dataclass(frozen=True)
class StopLossTriggeredEvent:
    timestamp: datetime
    position_id: int
    strategy_id: str
    trigger_price: Decimal
    stop_loss_price: Decimal

@dataclass(frozen=True)
class RiskAlertEvent:
    timestamp: datetime
    strategy_id: str
    alert_type: str  # circuit_breaker | daily_limit | cooldown | volatility_cap
    message: str
    severity: str  # warning | critical

@dataclass(frozen=True)
class BotStateChangeEvent:
    timestamp: datetime
    strategy_id: str
    old_state: str
    new_state: str
    reason: str = ""

@dataclass(frozen=True)
class RegimeChangeEvent:
    timestamp: datetime
    strategy_id: str
    old_regime: str
    new_regime: str
    overrides: dict = field(default_factory=dict)  # RegimeOverrides 직렬화

@dataclass(frozen=True)
class RiskStateEvent:
    timestamp: datetime
    strategy_id: str
    consecutive_losses: int
    daily_pnl: float
    cooldown_until: str | None = None
    position_pct: float = 0.0
    atr_pct: float = 0.0
    volatility_status: str = "normal"  # "normal" | "warning" | "blocked"

@dataclass(frozen=True)
class MarketDataEvent:
    timestamp: datetime
    symbol: str
    ohlcv_by_tf: dict  # {timeframe: list[Candle]}
```

### 5.2 EventBus 구현

```python
# engine/loop/event_bus.py

import asyncio
import structlog
from collections import defaultdict
from typing import TypeVar, Callable, Coroutine, Any
from prometheus_client import Counter, Histogram

T = TypeVar("T")
log = structlog.get_logger()

event_published = Counter(
    "traderj_event_bus_published_total", "Events published", ["event_type"]
)
handler_latency = Histogram(
    "traderj_event_bus_handler_latency_seconds", "Handler processing time",
    ["event_type", "handler"]
)

class AsyncioEventBus:
    """asyncio 기반 in-process 이벤트 버스. Protocol-First 설계."""

    def __init__(self) -> None:
        self._handlers: dict[type, list[Callable]] = defaultdict(list)

    def subscribe(
        self,
        event_type: type[T],
        handler: Callable[[T], Coroutine[Any, Any, None]],
    ) -> None:
        self._handlers[event_type].append(handler)
        log.debug("event_bus.subscribe", event_type=event_type.__name__,
                  handler=handler.__qualname__)

    def unsubscribe(self, event_type: type[T], handler: Callable) -> None:
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    async def publish(self, event: T) -> None:
        event_type = type(event)
        event_name = event_type.__name__
        handlers = self._handlers.get(event_type, [])

        event_published.labels(event_type=event_name).inc()

        for handler in handlers:
            try:
                with handler_latency.labels(
                    event_type=event_name,
                    handler=handler.__qualname__
                ).time():
                    await handler(event)
            except Exception:
                log.exception(
                    "event_bus.handler_error",
                    event_type=event_name,
                    handler=handler.__qualname__,
                )
                # 에러 격리: 한 핸들러 실패가 다른 핸들러에 영향 없음
```

### 5.3 이벤트 흐름도

```
[Upbit WebSocket]
    │
    ▼
MarketTickEvent ──→ RiskManager.on_tick()         → 실시간 손절 체크
                ──→ PositionManager.on_tick()     → unrealized_pnl 갱신
                ──→ API WS Bridge                 → dashboard push

[OHLCV Scheduler]
    │
    ▼
OHLCVUpdateEvent ──→ StrategyEngine.on_ohlcv()   → 시그널 생성
    │
    ▼
SignalEvent ──→ ExecutionEngine.on_signal()        → 매매 결정
           ──→ API WS Bridge                      → dashboard push
    │
    ▼
OrderRequestEvent ──→ OrderManager.on_order_request()
    │
    ▼
OrderFilledEvent ──→ PositionManager.on_order_filled()
                ──→ RiskManager.on_order_filled()
                ──→ Notifier.on_order_filled()
                ──→ API WS Bridge
    │
    ▼
PositionOpenedEvent / PositionClosedEvent
                ──→ RiskManager.on_position_change()
                ──→ API WS Bridge

[RegimeClassifier]
    │
    ▼
RegimeChangeEvent ──→ Logger                          → 레짐 전환 기록
                  ──→ API WS Bridge                   → dashboard push

[RiskEngine]
    │
    ▼
RiskStateEvent ──→ API WS Bridge                      → dashboard push
               ──→ TelegramNotifier                   → 리스크 상태 알림

[DataCollector]
    │
    ▼
MarketDataEvent ──→ StrategyEngine.on_market_data()   → 시그널 생성 트리거
```

---

## 6. 거래소 추상화 레이어

### 6.1 Protocol 정의

```python
# shared/protocols.py

from typing import Protocol
from decimal import Decimal
from datetime import datetime

class ExchangeClient(Protocol):
    """거래소 API 추상 인터페이스."""

    async def close(self) -> None: ...

    # Market Data
    async def fetch_ohlcv(
        self, symbol: str, timeframe: str = "1h",
        since: int | None = None, limit: int = 200
    ) -> list[list[float]]: ...

    async def fetch_ticker(self, symbol: str) -> "Ticker": ...

    # Account
    async def fetch_balance(self) -> list["Balance"]: ...
    async def fetch_krw_balance(self) -> Decimal: ...

    # Orders
    async def create_order(
        self, symbol: str, side: "OrderSide", order_type: "OrderType",
        amount: Decimal, price: Decimal | None = None
    ) -> "Order": ...

    async def cancel_order(self, order_id: str, symbol: str) -> None: ...
    async def fetch_order(self, order_id: str, symbol: str) -> "Order": ...
    async def fetch_open_orders(self, symbol: str) -> list["Order"]: ...

    # Market Info
    async def fetch_min_order_amount(self, symbol: str) -> Decimal: ...
    async def fetch_trading_fee(self, symbol: str) -> Decimal: ...


class WebSocketStream(Protocol):
    """거래소 WebSocket 추상 인터페이스."""

    async def start(self, symbols: list[str]) -> None: ...
    async def stop(self) -> None: ...
    def on_ticker(self, callback: "TickerCallback") -> None: ...
    def on_trade(self, callback: "TradeCallback") -> None: ...
    def on_orderbook(self, callback: "OrderBookCallback") -> None: ...


class DataStore(Protocol):
    """데이터 접근 추상 인터페이스. SQLite(dev) / PostgreSQL(prod) 교체 가능."""

    async def connect(self) -> None: ...
    async def close(self) -> None: ...

    # Candles
    async def upsert_candles(self, candles: list["Candle"]) -> int: ...
    async def get_candles(
        self, symbol: str, tf: str, limit: int,
        before: datetime | None = None
    ) -> list["Candle"]: ...

    # Signals
    async def insert_signal(self, signal: "Signal") -> int: ...
    async def get_signals(
        self, symbol: str, strategy_id: str, limit: int = 50
    ) -> list["Signal"]: ...

    # Orders
    async def insert_order(self, order: "Order") -> int: ...
    async def update_order_status(
        self, order_id: int, status: str,
        actual_price: Decimal | None = None
    ) -> None: ...
    async def get_open_orders(self, symbol: str, strategy_id: str) -> list["Order"]: ...
    async def get_orders(
        self, symbol: str, strategy_id: str, limit: int = 50
    ) -> list["Order"]: ...

    # Positions
    async def insert_position(self, pos: "Position") -> int: ...
    async def close_position(
        self, position_id: int, realized_pnl: Decimal, exit_order_id: int
    ) -> None: ...
    async def get_open_position(
        self, symbol: str, strategy_id: str
    ) -> "Position | None": ...
    async def get_positions(
        self, symbol: str, strategy_id: str,
        status: str | None = None, limit: int = 50
    ) -> list["Position"]: ...

    # Risk State
    async def get_risk_state(self, strategy_id: str) -> "RiskState": ...
    async def update_risk_state(self, state: "RiskState") -> None: ...

    # Bot State
    async def get_bot_state(self, strategy_id: str) -> str: ...
    async def set_bot_state(self, strategy_id: str, state: str) -> None: ...

    # Paper Balances
    async def get_paper_balance(self, strategy_id: str) -> "PaperBalance": ...
    async def atomic_buy_balance(
        self, strategy_id: str, cost: Decimal, fee: Decimal, btc_amount: Decimal
    ) -> bool: ...
    async def atomic_sell_balance(
        self, strategy_id: str, btc_amount: Decimal, proceeds: Decimal, fee: Decimal
    ) -> bool: ...

    # Daily PnL
    async def upsert_daily_pnl(self, pnl: "DailyPnL") -> None: ...
    async def get_daily_pnl(
        self, strategy_id: str, days: int = 30
    ) -> list["DailyPnL"]: ...

    # Macro
    async def insert_macro(self, snap: "MacroSnapshot") -> int: ...
    async def get_latest_macro(self) -> "MacroSnapshot | None": ...


class AnalyticsStore(Protocol):
    """분석 전용 데이터 스토어. DuckDB 구현."""

    async def load_parquet(self, table: str, path: str) -> int: ...
    async def get_candles_range(
        self, symbol: str, tf: str, start: datetime, end: datetime
    ) -> list["Candle"]: ...
    async def get_signals_range(
        self, strategy_id: str, start: datetime, end: datetime
    ) -> list["Signal"]: ...
```

### 6.2 Rate Limiter

```python
# engine/exchange/rate_limiter.py

class SlidingWindowRateLimiter:
    """ccxt Upbit rate limit 준수 (bit-trader 검증 완료 설정)"""

    LIMITS = {
        "market": (10, 1.0),    # 10 req/sec (fetch_ohlcv, fetch_ticker)
        "order": (8, 1.0),      # 8 req/sec (create/cancel/fetch order)
        "exchange": (30, 1.0),  # 30 req/sec (global)
    }
```

---

## 7. 주문 관리 흐름

### 7.1 주문 실행 파이프라인

```
OrderRequestEvent 수신
    │
    ▼
[1] Idempotency 체크 ──→ 동일 key 존재? ──→ SKIP (로그 경고)
    │
    ▼
[2] 리스크 사전 검증
    ├── CircuitBreaker 상태 체크 (OPEN → REJECT)
    ├── RiskManager.check_buy/sell()
    │   ├── daily_pnl_limit 초과? → REJECT
    │   ├── cooldown_until > now()? → REJECT
    │   ├── volatility_cap 초과? → REJECT (P0-S2)
    │   └── 통과 → position_size_pct 산출
    │
    ▼
[3] 주문 발행
    ├── Paper Mode → PaperOrderExecutor (내부 잔고 차감)
    └── Live Mode → ExchangeClient.create_order()
    │
    ▼
[4] DB 기록: DataStore.insert_order(status=pending)
    │
    ▼
[5] 확인 루프 (Live 전용)
    ├── 3초 대기 → ExchangeClient.fetch_order()
    ├── filled → update_order_status(filled) → [6]
    ├── pending → 재확인 (최대 3회, 총 9초)
    └── failed/cancelled → update_order_status(failed) → RiskAlertEvent
    │
    ▼
[6] 슬리피지 기록
    │ slippage_pct = |actual_price - expected_price| / expected_price × 100
    │ 메트릭: traderj_order_slippage_pct
    │
    ▼
[7] OrderFilledEvent 발행
    │
    ▼
[8] Circuit Breaker 업데이트
    ├── 성공 → reset (HALF_OPEN → CLOSED)
    └── 실패 → increment (3연속 → OPEN, 5분 후 HALF_OPEN)
```

### 7.2 Circuit Breaker 상태 머신

```
    ┌────────┐  연속 3회 실패   ┌────────┐
    │ CLOSED │ ──────────────→ │  OPEN  │
    │ (정상)  │ ←────────────── │ (차단)  │
    └────────┘  성공 (HALF_OPEN)└───┬────┘
                                    │ 5분 경과
                                    ▼
                              ┌──────────┐
                              │HALF_OPEN │
                              │ (시험)    │
                              └──────────┘
                              1건 허용:
                              성공 → CLOSED
                              실패 → OPEN (5분 재시작)
```

---

## 8. API 서버 설계

### 8.1 REST API 엔드포인트

| Method | Path | 설명 | 응답 | 인증 |
|--------|------|------|------|------|
| GET | `/api/v1/health` | 시스템 헬스체크 | `{status, uptime, db, ws, engine}` | 없음 |
| GET | `/api/v1/bots` | 전체 봇 상태 | `BotResponse[]` | API Key |
| GET | `/api/v1/bots/{strategy_id}` | 봇 상세 | `BotResponse` | API Key |
| POST | `/api/v1/bots/{strategy_id}/start` | 봇 시작 | `BotControlResponse` | API Key |
| POST | `/api/v1/bots/{strategy_id}/stop` | 봇 중지 | `BotControlResponse` | API Key |
| POST | `/api/v1/bots/{strategy_id}/pause` | 봇 일시정지 | `BotControlResponse` | API Key |
| POST | `/api/v1/bots/{strategy_id}/resume` | 봇 재개 | `BotControlResponse` | API Key |
| POST | `/api/v1/bots/{strategy_id}/emergency-exit` | 긴급 청산 | `{order_id}` | API Key |
| POST | `/api/v1/bots/emergency-stop` | 전체 긴급 중지 | `BotControlResponse` | API Key |
| GET | `/api/v1/positions` | 포지션 목록 | `PaginatedResponse<PositionResponse>` | API Key |
| GET | `/api/v1/orders` | 주문 이력 | `PaginatedResponse<OrderResponse>` | API Key |
| GET | `/api/v1/candles/{symbol}/{tf}` | OHLCV | `CandleResponse[]` | API Key |
| GET | `/api/v1/signals` | 시그널 이력 | `PaginatedResponse<SignalResponse>` | API Key |
| GET | `/api/v1/pnl/daily` | 일일 PnL | `DailyPnLResponse[]` | API Key |
| GET | `/api/v1/pnl/summary` | 전략별 성과 요약 | `StrategySummary[]` | API Key |
| GET | `/api/v1/risk/{strategy_id}` | 리스크 상태 | `RiskStateResponse` | API Key |
| GET | `/api/v1/macro/latest` | 최신 매크로 | `MacroSnapshotResponse` | API Key |
| GET | `/api/v1/analytics/pnl` | PnL 분석 | `PnLAnalytics` | API Key |
| GET | `/api/v1/analytics/compare` | 전략 비교 | `StrategyComparison` | API Key |
| POST | `/api/v1/positions/close-all` | 전 포지션 청산 | `CloseAllResponse` | API Key |

> **L1 참고**: `GET /bots/{strategy_id}`는 개별 봇 상세 조회 (대시보드 BotCard 상세 뷰 진입 시 사용 예정). `POST /bots/{id}/emergency-exit`는 개별 봇 긴급 청산 (EmergencyStop 컴포넌트에서 호출).

**P2 예정 엔드포인트** (대시보드 로드맵 참조):

| Method | Path | 설명 | 응답 | 인증 |
|--------|------|------|------|------|
| GET | `/api/v1/bots/{strategy_id}/config` | 봇 설정 조회 | `BotConfigResponse` | API Key |
| PUT | `/api/v1/bots/{strategy_id}/config` | 봇 설정 변경 | `BotConfigResponse` | API Key |
| GET | `/api/v1/alerts/rules` | 알림 규칙 목록 | `AlertRule[]` | API Key |
| GET | `/api/v1/backtest/results` | 백테스트 결과 목록 | `PaginatedResponse<BacktestResultResponse>` | API Key |

**Query Parameters 규칙**:
- 필터: `?strategy_id=STR-005&status=open`
- 페이지네이션: `?page=1&size=20` (기본 size=20, 최대 100)
- 기간: `?days=30` 또는 `?period=30d`
- 정렬: `?sort=created_at&order=desc`

**응답 형식 (Pagination)**:
```json
{
    "items": [...],
    "total": 150,
    "page": 1,
    "size": 20,
    "pages": 8
}
```

### 8.2 Pydantic 응답 스키마

> OpenAPI → TypeScript 자동 생성의 소스. FastAPI `response_model`에 사용.

```python
# api/schemas/responses.py

from pydantic import BaseModel, ConfigDict
from datetime import datetime
from decimal import Decimal

class BotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    strategy_id: str
    state: str                  # IDLE | STARTING | SCANNING | ...
    trading_mode: str           # paper | live
    started_at: datetime | None
    updated_at: datetime

class PositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    symbol: str
    side: str
    entry_price: str            # Decimal → string (정밀도 보존)
    amount: str
    current_price: str
    stop_loss: str
    unrealized_pnl: str
    realized_pnl: str
    status: str
    strategy_id: str
    opened_at: datetime
    closed_at: datetime | None

class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    exchange_id: str | None
    symbol: str
    side: str
    order_type: str
    amount: str
    price: str | None
    cost: str | None
    fee: str
    status: str
    is_paper: bool
    strategy_id: str
    slippage_pct: float | None
    created_at: datetime
    filled_at: datetime | None

class CandleData(BaseModel):
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

class SignalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    timestamp: datetime
    symbol: str
    strategy_id: str
    direction: str              # BUY | SELL | HOLD
    score: float
    timeframe: str
    components: dict
    details: dict
    created_at: datetime

class DailyPnLResponse(BaseModel):
    date: str
    strategy_id: str
    realized: str
    unrealized: str
    total_value: str
    trade_count: int
    win_count: int
    loss_count: int

class RiskStateResponse(BaseModel):
    strategy_id: str
    consecutive_losses: int
    daily_pnl: str
    cooldown_until: datetime | None
    total_trades: int
    total_wins: int
    last_atr: float | None
    updated_at: datetime

class MacroSnapshotResponse(BaseModel):
    timestamp: datetime
    fear_greed: float | None
    btc_dominance: float | None
    dxy: float | None
    nasdaq: float | None
    kimchi_premium: float | None
    funding_rate: float | None
    btc_dom_7d_change: float | None
    market_score: float | None

class BacktestResultResponse(BaseModel):
    id: str                     # UUID
    strategy_id: str
    params_hash: str
    config_json: dict
    metrics_json: dict
    equity_curve_json: dict | None
    trades_json: dict | None
    walk_forward_json: dict | None
    created_at: datetime

class BotControlResponse(BaseModel):
    strategy_id: str
    command: str
    accepted: bool
    message: str = ""

class BotConfigResponse(BaseModel):
    strategy_id: str
    config: dict
    updated_at: datetime

class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    size: int
    pages: int
```

### 8.3 인증 (구 §8.2)

**초기 구현**: `X-API-Key` 헤더 기반 (로컬/Docker 내부 통신)

```python
# api/middleware/auth.py

async def api_key_auth(request: Request) -> None:
    api_key = request.headers.get("X-API-Key")
    if api_key != settings.API_KEY:
        raise HTTPException(401, "Invalid API key")
```

- API Key는 `.env`의 `TRADERJ_API_KEY` 환경변수
- WebSocket 연결 시 query param으로 전달: `/ws/v1/stream?api_key=...`
- `/api/v1/health`는 인증 제외 (헬스체크용)
- JWT 전환은 P2

### 8.4 CORS 설정

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # dashboard dev
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 9. WebSocket 설계

> TDR-009 확정: Native WebSocket (FastAPI 내장)

### 9.1 연결 흐름

```
Client                              API Server
  │                                     │
  │ ──── WS connect /ws/v1/stream ────→ │
  │ ←── connection accepted ─────────── │
  │                                     │
  │ ──── {type: "subscribe",           │
  │       channels: ["ticker",         │
  │                  "bot_status",     │
  │                  "orders"]}  ─────→ │
  │ ←── {type: "subscribed",          │
  │       channels: [...]} ──────────── │
  │                                     │
  │ ←── {type: "data",                │
  │       channel: "ticker",           │
  │       payload: {...},              │
  │       ts: 1709337600000} ────────── │  (engine → api → client)
  │                                     │
  │ ──── {type: "ping"} ──────────────→ │
  │ ←── {type: "pong"} ──────────────── │
  │                                     │
  │ ──── {type: "unsubscribe",         │
  │       channels: ["orders"]} ──────→ │
  │                                     │
```

### 9.2 채널 목록

| 채널 | 데이터 소스 | 업데이트 빈도 | 페이로드 |
|------|-----------|-------------|---------|
| `ticker` | MarketTickEvent | ~1/sec | `{symbol, price, bid, ask, volume_24h, change_pct_24h}` |
| `bot_status` | BotStateChangeEvent | on change | `{strategy_id, state, trading_mode, pnl_pct, open_position}` |
| `orders` | OrderFilledEvent | on trade | `{order_id, strategy_id, side, amount, price, status}` |
| `positions` | PositionOpenedEvent / ClosedEvent | on change | `{position_id, strategy_id, status, unrealized_pnl}` |
| `signals` | SignalEvent | per eval cycle | `{strategy_id, direction, score, components}` |
| `alerts` | RiskAlertEvent | on alert | `{strategy_id, alert_type, message, severity}` |

### 9.3 메시지 프로토콜

```typescript
// 클라이언트 → 서버
type ClientMessage =
  | { type: "subscribe"; channels: string[] }
  | { type: "unsubscribe"; channels: string[] }
  | { type: "ping" }

// 서버 → 클라이언트
type ServerMessage =
  | { type: "subscribed"; channels: string[] }
  | { type: "unsubscribed"; channels: string[] }
  | { type: "data"; channel: string; payload: unknown; ts: number }
  | { type: "pong" }
  | { type: "error"; code: string; message: string }
```

### 9.4 재연결 전략 (클라이언트)

```typescript
// dashboard/src/lib/useWebSocket.ts

const RECONNECT_CONFIG = {
    maxRetries: 10,
    baseDelay: 1000,
    maxDelay: 30000,
    jitter: true,
    backoffMultiplier: 2,
};

// delay = min(baseDelay * 2^attempt + jitter, maxDelay)
```

### 9.5 하트비트

- 서버: 30초 간격 ping 전송
- 클라이언트: pong 응답
- 서버: 60초 무응답 시 연결 끊김 판정 → 리소스 정리

---

## 10. 배포 아키텍처

### 10.1 docker-compose.yml

```yaml
version: "3.9"

services:
  postgres:
    image: timescale/timescaledb:latest-pg16
    environment:
      POSTGRES_DB: traderj
      POSTGRES_USER: traderj
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U traderj"]
      interval: 5s
      timeout: 3s
      retries: 5
    restart: unless-stopped

  engine:
    build:
      context: .
      dockerfile: engine/Dockerfile
    depends_on:
      postgres:
        condition: service_healthy
    env_file: .env
    volumes:
      - ipc_socket:/tmp/traderj
      - engine_data:/app/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import asyncio; asyncio.run(__import__('engine.health').health.check())"]
      interval: 30s
      timeout: 10s

  api:
    build:
      context: .
      dockerfile: api/Dockerfile
    depends_on:
      postgres:
        condition: service_healthy
      engine:
        condition: service_healthy
    ports:
      - "8000:8000"
    env_file: .env
    volumes:
      - ipc_socket:/tmp/traderj
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
      interval: 10s

  dashboard:
    build:
      context: .
      dockerfile: dashboard/Dockerfile
    depends_on:
      - api
    ports:
      - "3000:3000"
    environment:
      NEXT_PUBLIC_API_URL: http://api:8000
      NEXT_PUBLIC_WS_URL: ws://api:8000
    restart: unless-stopped

  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    depends_on:
      - prometheus
    ports:
      - "3001:3000"
    volumes:
      - grafana_data:/var/lib/grafana
    restart: unless-stopped

volumes:
  pgdata:
  ipc_socket:
  engine_data:
  prometheus_data:
  grafana_data:
```

### 10.2 Dockerfile 예시

**engine/Dockerfile**:
```dockerfile
FROM python:3.13-slim AS base

WORKDIR /app

# shared 패키지 복사 + 설치
COPY shared/ /app/shared/
RUN pip install /app/shared/

# engine 패키지 복사 + 설치
COPY engine/pyproject.toml engine/poetry.lock* /app/engine/
WORKDIR /app/engine
RUN pip install poetry && poetry install --no-dev --no-interaction

COPY engine/ /app/engine/

CMD ["poetry", "run", "python", "-m", "engine.app"]
```

**api/Dockerfile**:
```dockerfile
FROM python:3.13-slim AS base

WORKDIR /app

COPY shared/ /app/shared/
RUN pip install /app/shared/

COPY api/pyproject.toml api/poetry.lock* /app/api/
WORKDIR /app/api
RUN pip install poetry && poetry install --no-dev --no-interaction

COPY api/ /app/api/

EXPOSE 8000
CMD ["poetry", "run", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**dashboard/Dockerfile**:
```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY dashboard/package.json dashboard/pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY dashboard/ .
RUN pnpm build

FROM node:20-alpine AS runner
WORKDIR /app
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]
```

### 10.3 환경변수 (.env.example)

```bash
# Database
DB_HOST=postgres
DB_PORT=5432
DB_NAME=traderj
DB_USER=traderj
DB_PASSWORD=changeme

# Exchange
UPBIT_ACCESS_KEY=
UPBIT_SECRET_KEY=

# API
TRADERJ_API_KEY=dev-api-key-changeme

# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Trading
TRADING_MODE=paper  # paper | live
DEFAULT_SYMBOL=BTC/KRW
```

---

## 11. 교차 도메인 계약 요약

### 11.1 아키텍처 → 전략 (bot-developer → quant-expert)

| 인터페이스 | 형태 | 설명 |
|-----------|------|------|
| `DataStore Protocol` | Python Protocol | OHLCV, 시그널, 매크로 CRUD |
| `EventBus` | Python 클래스 | 이벤트 발행/구독 |
| `MarketTickEvent` | dataclass | 실시간 가격 (ATR 손절용) |
| `BacktestDataProvider` (= AnalyticsStore) | Protocol | 히스토리컬 데이터 (walk-forward) |
| `StrategyParams` | frozen dataclass | 전략 파라미터 (기존 bit-trader 호환) |
| Indicator Protocol | Protocol | pandas-ta 래퍼 추상화 |

### 11.2 아키텍처 → 대시보드 (bot-developer → dashboard-designer)

| 인터페이스 | 형태 | 설명 |
|-----------|------|------|
| REST API 20개 | HTTP JSON | 읽기 16 + 제어 4 |
| WebSocket 6채널 | WS JSON | ticker, bot_status, orders, positions, signals, alerts |
| OpenAPI Spec | auto-generated | TypeScript 타입 자동 생성 기반 |
| Pydantic 응답 스키마 | Python BaseModel | API 응답 형식 정의 |

### 11.3 응답 시간 목표 (UX 시나리오 매핑)

| 시나리오 | 사용 API | 목표 |
|---------|---------|------|
| 아침 점검 (30초) | `GET /bots` + `GET /pnl/summary` | < 200ms |
| 긴급 상황 (10초) | WS events + `POST /emergency-exit` | < 500ms |
| 성과 분석 (30초) | `GET /analytics/pnl` + `GET /signals` | < 300ms |
| 캔들 차트 로딩 | `GET /candles/{symbol}/{tf}?limit=500` | < 1000ms |

---

## 12. 구현 순서 및 마일스톤

### 12.1 의존성 그래프

```
Phase 0 (기반)
  shared/ 패키지 ──┐
  PostgreSQL 스키마 ─┤
                     ├──→ Phase 1 (핵심)
                     │      DataStore(PG) 구현
                     │      EventBus 구현
                     │      ExchangeClient 구현
                     │
                     └──→ Phase 2 (엔진)
                            RiskManager (영속화)
                            OrderManager (멱등성, CB)
                            PositionManager
                            StateMachine
                            StrategyEngine 통합
                            │
                            ├──→ Phase 3 (API)
                            │      FastAPI REST 전체
                            │      WebSocket 핸들러
                            │      IPC 클라이언트/서버
                            │      → 대시보드 팀 언블록
                            │
                            └──→ Phase 4 (인프라)
                                   Docker 전체
                                   CI/CD
                                   로깅 + 메트릭
                                   테스트 80%
```

### 12.2 대시보드 팀 선행 개발 지원

API 서버 완성 전 대시보드 팀이 선행 개발할 수 있도록:

1. **Phase 0에서 OpenAPI YAML 먼저 작성** → 대시보드 팀에 전달
2. 대시보드 팀은 mock 서버(`msw` 또는 `json-server`)로 UI 개발 착수
3. Phase 3 완료 시 mock → 실제 API로 전환

### 12.3 전략 팀 협업 포인트

| 시점 | 전략 팀 필요 사항 | 아키텍처 팀 제공 |
|------|------------------|----------------|
| Phase 0 | shared 모델 검토/승인 | `shared/models.py`, `shared/events.py` |
| Phase 1 | DataStore 메서드 테스트 | SQLite 구현체 (dev용) |
| Phase 2 | EventBus 이벤트 타입 확정 | EventBus + 전체 이벤트 목록 |
| Phase 3 | 백테스트용 데이터 API | AnalyticsStore + Parquet 파이프라인 |

---

> **문서 상태**: Draft — 팀 리더 검토 대기
> **다음 단계**: 팀 리더 승인 + quant-expert/dashboard-designer 교차 검토 후 구현 착수
