# traderj 아키텍처 요구사항서 (Round 2)

**작성일**: 2026-03-02
**작성자**: bot-developer (아키텍처 도메인)
**기반 문서**: Round 1 아키텍처/전략/UX 감사 보고서 + Round 2 교차 발견사항 종합
**상태**: Draft — 팀 리더 승인 대기

---

## 목차

1. [설계 원칙](#1-설계-원칙)
2. [P0 — 필수 요구사항](#2-p0--필수-요구사항)
3. [P1 — 중요 요구사항](#3-p1--중요-요구사항)
4. [P2 — 개선 요구사항](#4-p2--개선-요구사항)
5. [교차 도메인 인터페이스 계약](#5-교차-도메인-인터페이스-계약)
6. [기술 선택 의사결정 기록 (ADR)](#6-기술-선택-의사결정-기록-adr)
7. [구현 의존성 그래프 및 순서](#7-구현-의존성-그래프-및-순서)
8. [공유 데이터 모델](#8-공유-데이터-모델)

---

## 1. 설계 원칙

| 원칙 | 설명 | 근거 (Round 1 발견사항) |
|------|------|------------------------|
| **Event-Driven** | 컴포넌트 간 이벤트 발행/구독, 직접 참조 금지 | H1: TradingLoop 13개 직접 의존성 |
| **Protocol-First** | Python `Protocol`로 모든 외부 의존성 인터페이스 정의 | M5: 인터페이스 미정의, 구현 교체 불가 |
| **Persistence-First Risk** | 리스크 상태는 반드시 DB에 영속화 | C1: 메모리 전용 리스크 → 재시작 시 쿨다운 소실 |
| **Observable** | 모든 핵심 경로에 메트릭 + 구조화된 로깅 | H6: 메트릭 없음, 장애 인지 지연 |
| **Fail-Safe** | 장애 시 포지션 보호 우선 (거래 중단 > 잘못된 거래) | H3: 유령 주문, 주문 실패 복구 없음 |
| **Decimal Precision** | 금융 데이터에 `Decimal` 사용 | M7: float PnL 계산 오차 |

---

## 2. P0 — 필수 요구사항

> 실거래 전환 및 안전 운영의 절대 전제조건. 이 항목 없이는 페이퍼→라이브 전환 불가.

---

### P0-A1: 이벤트 버스

| 항목 | 내용 |
|------|------|
| **문제** | Round 1 H1: TradingLoop이 13개 컴포넌트에 직접 의존. 컴포넌트 추가/교체 시 TradingLoop 수정 불가피 |
| **해결** | asyncio 기반 in-process 이벤트 버스 구현 |
| **복잡도** | **M** (Medium) |

**기능 요구사항**:

1. **발행/구독**: 이벤트 타입별 다중 구독자 등록, 발행 시 모든 구독자에게 비동기 전달
2. **에러 격리**: 구독자 A에서 예외 발생해도 구독자 B는 정상 수신
3. **순서 보장**: 동일 이벤트 타입에 대해 구독 등록 순서대로 전달
4. **타입 안전성**: 제네릭 타입으로 이벤트 타입별 구독자 시그니처 검증
5. **메트릭 통합**: 이벤트 발행 수, 처리 지연, 에러 수 자동 카운트

**핵심 이벤트 목록**:

| 이벤트 | 발행자 | 구독자 | 페이로드 |
|--------|--------|--------|----------|
| `MarketTickEvent` | WebSocketStream | RiskManager, PositionManager, API(WS) | symbol, price, bid, ask, volume, timestamp |
| `OHLCVUpdateEvent` | OHLCVCollector | StrategyEngine | symbol, timeframe, candles[] |
| `SignalEvent` | StrategyEngine | ExecutionEngine, API(WS), Logger | strategy_id, symbol, direction, score, components |
| `OrderRequestEvent` | ExecutionEngine | OrderManager | strategy_id, symbol, side, amount, order_type |
| `OrderFilledEvent` | OrderManager | PositionManager, RiskManager, Notifier, API(WS) | order 전체 |
| `PositionOpenedEvent` | PositionManager | RiskManager, API(WS) | position 전체 |
| `PositionClosedEvent` | PositionManager | RiskManager, Notifier, API(WS) | position, realized_pnl |
| `StopLossTriggeredEvent` | RiskManager | ExecutionEngine, Notifier | position_id, trigger_price |
| `RiskAlertEvent` | RiskManager | ExecutionEngine(halt), Notifier | alert_type, message, strategy_id |
| `BotStateChangeEvent` | StateMachine | API(WS), Logger | strategy_id, old_state, new_state |

**인터페이스**:
```python
from typing import TypeVar, Generic, Callable, Coroutine, Any

T = TypeVar("T")

class EventBus:
    async def publish(self, event: T) -> None: ...
    def subscribe(self, event_type: type[T], handler: Callable[[T], Coroutine[Any, Any, None]]) -> None: ...
    def unsubscribe(self, event_type: type[T], handler: Callable) -> None: ...
```

**대시보드 도메인 연관**: `API(WS)` 구독자가 이벤트를 WebSocket 클라이언트에게 실시간 push → UX 감사 3.1절 "실시간성 Critical" 해결

**전략 도메인 연관**: `SignalEvent`가 전략 엔진의 출력 계약. 전략 감사 4.3절의 "combined 스코어 차등 가중치"가 반영된 결과가 `components` 필드에 포함

---

### P0-A2: 리스크 상태 영속화

| 항목 | 내용 |
|------|------|
| **문제** | Round 1 C1: `_consecutive_losses`, `_daily_pnl`, `_cooldown_until`이 인스턴스 변수. 재시작 시 전부 초기화 |
| **해결** | 모든 거래 결과 반영 시 DB 동기 업데이트, 기동 시 자동 복원 |
| **복잡도** | **S** (Small) |

**데이터 계약** — `risk_state` 테이블:
```sql
CREATE TABLE risk_state (
    strategy_id         TEXT        PRIMARY KEY,
    consecutive_losses  INTEGER     NOT NULL DEFAULT 0,
    daily_pnl           NUMERIC(18,2) NOT NULL DEFAULT 0,
    daily_date          DATE        NOT NULL DEFAULT CURRENT_DATE,
    cooldown_until      TIMESTAMPTZ,
    total_trades        INTEGER     NOT NULL DEFAULT 0,
    total_wins          INTEGER     NOT NULL DEFAULT 0,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**동작 규칙**:
1. `RiskManager.record_trade_result(pnl)` 호출 시 즉시 `risk_state` UPDATE
2. 봇 시작 시 `RiskManager.__init__`에서 `risk_state` SELECT → 상태 복원
3. 일일 리셋: `daily_date != today`면 `daily_pnl=0` 후 UPDATE
4. 쿨다운 체크: `cooldown_until > now()`면 거래 차단 (재시작 후에도 유지)

**전략 도메인 연관**: 전략 감사 7.5절 "리스크 상태 영속성" 긴급 개선 사항과 직접 대응. 전략 감사 7.4절의 "변동성 조건 추가" 권고를 위해 `last_atr` 칼럼 예약

---

### P0-A3: 데이터베이스 전환 (SQLite → PostgreSQL + TimescaleDB)

| 항목 | 내용 |
|------|------|
| **문제** | Round 1 C2: SQLite 단일 writer 잠금 → 멀티 봇 동시 쓰기 불가. 교차 발견사항 #1: 데이터 계층이 모든 도메인의 병목 |
| **해결** | PostgreSQL 16 + TimescaleDB 확장 + asyncpg 드라이버 |
| **복잡도** | **L** (Large) |

**스키마 설계 원칙**:
1. 모든 테이블에 `strategy_id` 칼럼 포함 (Round 1 M1, M2 해결)
2. `timestamp` → `TIMESTAMPTZ` 타입 통일 (Round 1 M3 해결)
3. `candles` 테이블: TimescaleDB hypertable로 변환 (자동 시간 기반 파티셔닝)
4. 금액 관련 칼럼: `NUMERIC(18,8)` (BTC 8자리 소수점 + KRW 정수부)
5. `signals` 테이블에 `strategy_id` 칼럼 추가 (Round 1 M1)
6. `daily_pnl` 테이블에 `strategy_id` 칼럼 추가 (Round 1 M2)

**candles hypertable**:
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

SELECT create_hypertable('candles', 'time');

-- 자동 데이터 보존 정책 (Round 1 M4 해결)
SELECT add_retention_policy('candles', INTERVAL '2 years');

-- 연속 집계 (대시보드 성능 최적화)
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
```

**마이그레이션 전략**:
- Alembic 기반 버전 관리 (기존 파일 기반 마이그레이션 교체)
- SQLite → PostgreSQL 일괄 마이그레이션 스크립트 (`scripts/migrate_to_pg.py`)
- 개발 환경에서 SQLite 유지 옵션 (DataStore Protocol로 추상화)

**DataStore Protocol** (전체 도메인 공유):
```python
class DataStore(Protocol):
    # Connection lifecycle
    async def connect(self) -> None: ...
    async def close(self) -> None: ...

    # Candles (전략 도메인 소비)
    async def upsert_candles(self, candles: list[Candle]) -> int: ...
    async def get_candles(self, symbol: str, tf: str, limit: int,
                          before: datetime | None = None) -> list[Candle]: ...

    # Signals
    async def insert_signal(self, signal: Signal) -> int: ...
    async def get_signals(self, symbol: str, strategy_id: str,
                          limit: int = 50) -> list[Signal]: ...

    # Orders
    async def insert_order(self, order: Order) -> int: ...
    async def update_order_status(self, order_id: int, status: str,
                                  actual_price: float | None = None) -> None: ...
    async def get_open_orders(self, symbol: str, strategy_id: str) -> list[Order]: ...
    async def get_orders(self, symbol: str, strategy_id: str,
                         limit: int = 50) -> list[Order]: ...

    # Positions
    async def insert_position(self, pos: Position) -> int: ...
    async def close_position(self, position_id: int, realized_pnl: Decimal,
                             exit_order_id: int) -> None: ...
    async def get_open_position(self, symbol: str, strategy_id: str) -> Position | None: ...
    async def get_positions(self, symbol: str, strategy_id: str,
                            status: str | None = None, limit: int = 50) -> list[Position]: ...

    # Risk State (P0-A2)
    async def get_risk_state(self, strategy_id: str) -> RiskState: ...
    async def update_risk_state(self, state: RiskState) -> None: ...

    # Bot State
    async def get_bot_state(self, strategy_id: str) -> str: ...
    async def set_bot_state(self, strategy_id: str, state: str) -> None: ...

    # Paper Balances
    async def get_paper_balance(self, strategy_id: str) -> PaperBalance: ...
    async def atomic_buy_balance(self, strategy_id: str, cost: Decimal,
                                 fee: Decimal, btc_amount: Decimal) -> bool: ...
    async def atomic_sell_balance(self, strategy_id: str, btc_amount: Decimal,
                                  proceeds: Decimal, fee: Decimal) -> bool: ...

    # Daily PnL
    async def upsert_daily_pnl(self, pnl: DailyPnL) -> None: ...
    async def get_daily_pnl(self, strategy_id: str, days: int = 30) -> list[DailyPnL]: ...

    # Macro
    async def insert_macro(self, snap: MacroSnapshot) -> int: ...
    async def get_latest_macro(self) -> MacroSnapshot | None: ...
```

**전략 도메인 연관**: 전략 감사 8.3절 "데이터 제약" — TimescaleDB의 연속 집계로 백테스트 데이터 조회 성능 개선. `get_candles()`에 `before` 파라미터로 walk-forward 데이터 분할 지원

**대시보드 도메인 연관**: UX 감사 3.8절 "데이터 모델 활용도" — 대시보드가 DB 직접 접근 대신 API 서버를 통해 DataStore 간접 사용. API 서버가 DataStore Protocol의 소비자

---

### P0-A4: WebSocket 실시간 데이터 통합

| 항목 | 내용 |
|------|------|
| **문제** | Round 1 H2: WebSocket 구현 완료(dead code), 30초 폴링 손절. 교차 발견사항 #2: 실시간성 부재가 전 영역에 영향 |
| **해결** | 기존 UpbitWebSocket을 이벤트 버스에 통합, 실시간 가격 기반 손절 체크 |
| **복잡도** | **M** (Medium) |

**동작 흐름**:
```
UpbitWebSocket.on_ticker()
  → EventBus.publish(MarketTickEvent)
    → RiskManager: 실시간 손절 체크 (ms 단위, 기존 30초 → ~100ms)
    → PositionManager: unrealized_pnl 실시간 갱신
    → API WebSocket: 대시보드 클라이언트에 push

UpbitWebSocket.on_orderbook()
  → EventBus.publish(OrderBookEvent)
    → API WebSocket: 대시보드 depth chart용 push (P2)
```

**Fallback 전략**:
| 상태 | 동작 |
|------|------|
| WebSocket 정상 | `MarketTickEvent.source = "websocket"`, 실시간 처리 |
| WebSocket 끊김 | 자동 재연결 시도 (exponential backoff: 1s, 2s, 4s, 8s, max 30s) |
| 재연결 3회 실패 | `source = "rest_poll"`로 전환, 10초 간격 `fetch_ticker()` 폴링 |
| 재연결 성공 | 자동으로 WebSocket 모드 복귀, 메트릭에 전환 이벤트 기록 |

**인터페이스 계약** (대시보드 도메인):
```python
@dataclass(frozen=True)
class MarketTickEvent:
    timestamp: datetime      # UTC
    symbol: str              # "BTC/KRW"
    price: Decimal
    bid: Decimal
    ask: Decimal
    volume_24h: Decimal
    source: str              # "websocket" | "rest_poll"
```

**전략 도메인 연관**: 전략 감사 7.2절 "고정 3% 손절 → ATR 기반 동적 손절" — 실시간 가격이 있어야 ATR 기반 동적 손절을 밀리초 단위로 실행 가능

---

### P0-A5: 주문 실행 안전성 강화

| 항목 | 내용 |
|------|------|
| **문제** | Round 1 H3: 유령 주문 위험, 슬리피지 미고려, 실패 재시도 없음, 시장가만 지원(H9) |
| **해결** | 주문 실행 파이프라인에 멱등성, 확인 루프, 슬리피지 기록, circuit breaker 추가 |
| **복잡도** | **L** (Large) |

**주문 실행 파이프라인**:
```
OrderRequestEvent 수신
  → [1] Idempotency 체크: 동일 key 주문 존재 시 skip
  → [2] 리스크 사전 검증: RiskManager.check_buy/sell()
  → [3] 주문 발행: ExchangeClient.create_order()
  → [4] DB 기록: DataStore.insert_order(status=pending)
  → [5] 확인 루프: 3초 대기 → fetch_order() → 상태 확인
       ├─ filled → update_order_status(filled, actual_price) → OrderFilledEvent 발행
       ├─ pending → 재확인 (최대 3회, 총 9초)
       └─ failed/cancelled → update_order_status(failed) → RiskAlertEvent 발행
  → [6] 슬리피지 기록: |actual_price - expected_price| / expected_price
  → [7] Circuit Breaker: 연속 3회 실패 시 해당 전략 거래 중단 + RiskAlertEvent
```

**확장된 Order 모델**:
```python
@dataclass
class Order:
    # 기존 필드 (bit-trader 호환)
    id: int | None = None
    exchange_id: str | None = None
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    order_type: OrderType = OrderType.MARKET
    amount: Decimal = Decimal(0)
    price: Decimal | None = None
    cost: Decimal | None = None
    fee: Decimal = Decimal(0)
    status: OrderStatus = OrderStatus.PENDING
    is_paper: bool = True
    signal_id: int | None = None
    strategy_id: str = "default"
    created_at: datetime | None = None
    filled_at: datetime | None = None

    # 신규 필드 (P0-A5)
    idempotency_key: str = ""           # UUID, 중복 주문 방지
    expected_price: Decimal | None = None  # 주문 시점 시장가
    actual_price: Decimal | None = None    # 실제 체결가
    slippage_pct: float | None = None      # (actual - expected) / expected × 100
    retry_count: int = 0                   # 확인 루프 재시도 횟수
    error_message: str | None = None       # 실패 시 사유
```

**Circuit Breaker 규칙**:
| 상태 | 조건 | 동작 |
|------|------|------|
| CLOSED (정상) | - | 주문 정상 처리 |
| OPEN (차단) | 연속 3회 주문 실패 | 해당 strategy의 모든 주문 차단 + RiskAlertEvent |
| HALF_OPEN | OPEN 후 5분 경과 | 다음 1건만 허용, 성공 시 CLOSED 복귀 |

**전략 도메인 연관**: 전략 감사 7.1절 "변동성 역비례 포지션 사이징" — `RiskCheck.position_size_krw`가 ATR 기반으로 산출된 값을 OrderRequestEvent에 전달

**대시보드 도메인 연관**: UX 감사 3.2절 "긴급 청산 기능" — API 서버의 `POST /api/v1/bots/{id}/emergency-exit` 엔드포인트가 `OrderRequestEvent(side=SELL, amount=ALL)` 발행

---

### P0-A6: 거래소 추상화 레이어

| 항목 | 내용 |
|------|------|
| **문제** | Round 1 L4: 거래소 추상 인터페이스 없음 → 멀티 거래소 확장 비용 |
| **해결** | Python Protocol로 거래소 인터페이스 정의, UpbitClient를 첫 번째 구현체로 |
| **복잡도** | **M** (Medium) |

**ExchangeClient Protocol**:
```python
class ExchangeClient(Protocol):
    """거래소 API 추상 인터페이스. 모든 거래소 구현체가 이 Protocol을 따름."""

    async def close(self) -> None: ...

    # Market Data
    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1h",
                          since: int | None = None, limit: int = 200) -> list[list[float]]: ...
    async def fetch_ticker(self, symbol: str) -> Ticker: ...

    # Account
    async def fetch_balance(self) -> list[Balance]: ...
    async def fetch_krw_balance(self) -> Decimal: ...

    # Orders
    async def create_order(self, symbol: str, side: OrderSide,
                          order_type: OrderType, amount: Decimal,
                          price: Decimal | None = None) -> Order: ...
    async def cancel_order(self, order_id: str, symbol: str) -> None: ...
    async def fetch_order(self, order_id: str, symbol: str) -> Order: ...
    async def fetch_open_orders(self, symbol: str) -> list[Order]: ...

    # Market Info
    async def fetch_min_order_amount(self, symbol: str) -> Decimal: ...
    async def fetch_trading_fee(self, symbol: str) -> Decimal: ...
```

**WebSocketStream Protocol**:
```python
class WebSocketStream(Protocol):
    """거래소 WebSocket 추상 인터페이스."""

    async def start(self, symbols: list[str]) -> None: ...
    async def stop(self) -> None: ...
    def on_ticker(self, callback: TickerCallback) -> None: ...
    def on_trade(self, callback: TradeCallback) -> None: ...
    def on_orderbook(self, callback: OrderBookCallback) -> None: ...
```

---

## 3. P1 — 중요 요구사항

> 운영 안정성 확보 및 대시보드/전략 도메인 언블록.

---

### P1-A7: API 서버 (FastAPI)

| 항목 | 내용 |
|------|------|
| **문제** | UX 감사 4.2절: 대시보드가 SQLite 직접 연결, 프레임워크 전환 시 API 필요. 교차 발견사항 #5: API 계층 신규 필요 |
| **해결** | FastAPI 기반 REST + WebSocket API 서버 |
| **복잡도** | **L** (Large) |

**REST API 엔드포인트**:

| Method | Path | 설명 | 응답 | 대시보드 사용처 |
|--------|------|------|------|----------------|
| GET | `/api/v1/health` | 시스템 헬스 | `{status, uptime, db, ws}` | 상태바 |
| GET | `/api/v1/bots` | 봇 목록 + 상태 | `Bot[]` | 멀티봇 개요 (UX 3.2) |
| GET | `/api/v1/bots/{strategy_id}` | 봇 상세 | `BotDetail` | 봇 상세 뷰 |
| POST | `/api/v1/bots/{strategy_id}/pause` | 일시정지 | `{ok}` | 봇 제어 패널 (UX 3.2) |
| POST | `/api/v1/bots/{strategy_id}/resume` | 재개 | `{ok}` | 봇 제어 패널 |
| POST | `/api/v1/bots/{strategy_id}/emergency-exit` | 긴급 청산 | `{order_id}` | 긴급 버튼 (UX 시나리오2) |
| GET | `/api/v1/positions?strategy_id=X` | 포지션 목록 | `Position[]` | 포지션 뷰 |
| GET | `/api/v1/orders?strategy_id=X&page=1&size=20` | 주문 이력 | `PaginatedResponse<Order>` | 주문 이력 테이블 |
| GET | `/api/v1/signals?strategy_id=X&page=1&size=20` | 시그널 이력 | `PaginatedResponse<Signal>` | 시그널 테이블 |
| GET | `/api/v1/candles/{symbol}/{tf}?limit=200` | OHLCV | `Candle[]` | 캔들스틱 차트 (UX 3.4) |
| GET | `/api/v1/pnl/daily?strategy_id=X&days=30` | 일일 손익 | `DailyPnL[]` | PnL 차트 |
| GET | `/api/v1/pnl/summary` | 전략별 성과 요약 | `StrategySummary[]` | 전략 비교 뷰 (UX 3.3) |
| GET | `/api/v1/risk/{strategy_id}` | 리스크 상태 | `RiskState` | 리스크 메트릭 (UX 3.3) |
| GET | `/api/v1/macro/latest` | 최신 매크로 | `MacroSnapshot` | 매크로 패널 |

**WebSocket API 엔드포인트**:

| Path | 설명 | 메시지 형식 | 대시보드 사용처 |
|------|------|------------|----------------|
| `/ws/v1/ticker/{symbol}` | 실시간 가격 | `MarketTickEvent JSON` | 실시간 가격 표시, 차트 업데이트 |
| `/ws/v1/events?strategy_id=X` | 봇 이벤트 스트림 | `BotEvent JSON` | 시그널/주문/상태 실시간 알림 |

**WebSocket 메시지 형식**:
```json
{
    "type": "ticker",
    "timestamp": "2026-03-02T09:30:00Z",
    "data": {
        "symbol": "BTC/KRW",
        "price": "125000000",
        "bid": "124990000",
        "ask": "125010000",
        "volume_24h": "1234.56"
    }
}
```

```json
{
    "type": "signal",
    "timestamp": "2026-03-02T09:30:05Z",
    "data": {
        "strategy_id": "STR-005",
        "symbol": "BTC/KRW",
        "direction": "BUY",
        "score": 0.25,
        "components": {"trend": 0.3, "momentum": 0.2, "volume": 0.15, "macro": -0.08}
    }
}
```

**Pagination 응답 형식**:
```json
{
    "items": [...],
    "total": 150,
    "page": 1,
    "size": 20,
    "pages": 8
}
```

**인증**: 초기 구현은 `X-API-Key` 헤더 기반. 로컬/Docker 내부 통신이므로 단순 키로 충분. JWT 전환은 P2.

---

### P1-A8: Docker 컨테이너화

| 항목 | 내용 |
|------|------|
| **문제** | Round 1 H7: Dockerfile 없음, Mac caffeinate 의존, PID 파일 기반 프로세스 관리 |
| **해결** | Docker + docker-compose로 전체 시스템 컨테이너화 |
| **복잡도** | **M** (Medium) |

**docker-compose 구성**:
```yaml
services:
  postgres:
    image: timescale/timescaledb:latest-pg16
    volumes: [pgdata:/var/lib/postgresql/data]
    ports: ["5432:5432"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U traderj"]
      interval: 5s

  traderj-engine:
    build: {context: ., dockerfile: Dockerfile.engine}
    depends_on:
      postgres: {condition: service_healthy}
    restart: unless-stopped
    env_file: .env
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/api/v1/health')"]

  traderj-api:
    build: {context: ., dockerfile: Dockerfile.api}
    depends_on:
      postgres: {condition: service_healthy}
    ports: ["8000:8000"]
    restart: unless-stopped
    env_file: .env

  prometheus:
    image: prom/prometheus:latest
    volumes: [./prometheus.yml:/etc/prometheus/prometheus.yml]
    ports: ["9090:9090"]

  grafana:
    image: grafana/grafana:latest
    depends_on: [prometheus]
    ports: ["3001:3000"]
    volumes: [grafana-data:/var/lib/grafana]
```

**원칙**:
- `traderj-engine`: 멀티 전략을 asyncio 태스크로 동시 실행 (프로세스 분리 불필요 — PostgreSQL이 동시성 해결)
- `traderj-api`: 별도 컨테이너 (엔진 장애 시에도 마지막 상태 조회 가능)
- `restart: unless-stopped`: 장애 시 자동 재시작 (Mac caffeinate 대체)
- 환경변수 `.env`로 시크릿 관리 (Round 1 M10 일부 해결)

---

### P1-A9: CI/CD 파이프라인

| 항목 | 내용 |
|------|------|
| **문제** | Round 1 H5: 수동 테스트/린트, 자동화 부재 |
| **해결** | GitHub Actions 기반 자동화 파이프라인 |
| **복잡도** | **S** (Small) |

**PR 생성 시**:
```
→ ruff check + ruff format --check
→ mypy --strict
→ pytest --cov=traderj --cov-fail-under=80
→ Docker 빌드 테스트 (docker build --target test)
```

**main 병합 시**:
```
→ 위 전부 + Docker 이미지 빌드
→ ghcr.io 레지스트리 푸시
→ (옵션) docker-compose pull + restart
```

---

### P1-A10: 구조화된 로깅 + Prometheus 메트릭

| 항목 | 내용 |
|------|------|
| **문제** | Round 1 H6: 메트릭 없음, M6: 텍스트 로깅 |
| **해결** | structlog JSON 로깅 + prometheus-client 메트릭 |
| **복잡도** | **M** (Medium) |

**로깅**:
- `structlog` + JSON 렌더러
- 필수 바인딩 컨텍스트: `strategy_id`, `symbol`, `correlation_id`(이벤트 체인 추적)
- 로그 레벨 ERROR → Telegram 알림 자동 트리거 (기존 `notify_error()` 연계)
- 개발 환경: 컬러 콘솔 출력 / 프로덕션: JSON stdout → Docker 로그 수집

**Prometheus 메트릭**:

| 메트릭 이름 | 타입 | 레이블 | 용도 |
|------------|------|--------|------|
| `traderj_signal_total` | Counter | strategy_id, direction | 전략별 시그널 빈도 |
| `traderj_order_total` | Counter | strategy_id, side, status | 주문 성공/실패율 |
| `traderj_order_latency_seconds` | Histogram | strategy_id | 주문→체결 지연 |
| `traderj_order_slippage_pct` | Histogram | strategy_id, side | 슬리피지 분포 |
| `traderj_position_unrealized_pnl_krw` | Gauge | strategy_id | 미실현 PnL |
| `traderj_risk_consecutive_losses` | Gauge | strategy_id | 연속 손실 |
| `traderj_risk_daily_pnl_krw` | Gauge | strategy_id | 일일 PnL |
| `traderj_ws_connected` | Gauge | exchange | WebSocket 상태 |
| `traderj_ws_reconnect_total` | Counter | exchange | 재연결 횟수 |
| `traderj_exchange_rate_limit_remaining` | Gauge | group | Rate limit 잔여 |
| `traderj_event_bus_published_total` | Counter | event_type | 이벤트 발행 수 |
| `traderj_event_bus_handler_latency_seconds` | Histogram | event_type, handler | 핸들러 처리 시간 |
| `traderj_api_request_duration_seconds` | Histogram | method, path, status | API 응답 시간 |

**Grafana 대시보드**: 기본 제공 JSON 프로비저닝 (시스템 개요, 전략별 성과, 주문 실행 성능)

---

### P1-A11: 핵심 로직 테스트

| 항목 | 내용 |
|------|------|
| **문제** | Round 1 H4: TradingLoop, StateMachine, Scheduler 테스트 없음 |
| **해결** | 커버리지 80% 목표, 핵심 경로 100% |
| **복잡도** | **L** (Large) |

**테스트 매트릭스**:

| 모듈 | 테스트 유형 | 범위 | 의존성 |
|------|------------|------|--------|
| EventBus | Unit | 발행/구독, 에러 격리, 순서 보장, 타입 검증 | 없음 |
| StateMachine | Unit | 모든 전환, 잘못된 전환 거부, force_state, 영속화 | Mock DataStore |
| RiskManager | Unit | 영속화/복원, 쿨다운 경계값, 일일 리셋, circuit breaker | Mock DataStore |
| OrderManager | Unit | 멱등성, 재시도, 슬리피지, paper/live 분기 | Mock Exchange, Mock DataStore |
| PositionManager | Unit | open/close, PnL 계산 (Decimal 정확도) | Mock DataStore |
| TradingLoop (E2E) | Integration | 시그널→주문→포지션 전체 사이클 | Mock Exchange, Real DataStore(SQLite) |
| API Endpoints | Integration | 모든 REST 엔드포인트 응답 검증, 에러 처리 | httpx TestClient, Mock DataStore |
| DataStore(PG) | Integration | CRUD, 트랜잭션, hypertable 쿼리 | testcontainers-python (PostgreSQL) |

---

## 4. P2 — 개선 요구사항

> 고급 기능, 장기 확장성. P0/P1 완료 후 착수.

---

### P2-A12: 고급 주문 유형

| 항목 | 내용 | 복잡도 |
|------|------|--------|
| 지정가 주문 (Limit) | `OrderType.LIMIT` 지원, 미체결 타임아웃 관리 | **S** |
| TWAP | 대량 주문을 N분할, 일정 간격 실행 | **M** |
| 트레일링 스탑 | 고점 대비 N% 하락 시 자동 청산 (전략 감사 7.6절) | **M** |
| OCO | 이익 실현 + 손절 동시 설정 | **M** |

**전략 도메인 연관**: 전략 감사 7.6절 "트레일링 스탑: 높음 우선순위" — 실시간 WebSocket(P0-A4) + 이벤트 버스(P0-A1)가 전제

---

### P2-A13: 멀티 포지션 지원

| 항목 | 내용 | 복잡도 |
|------|------|--------|
| 심볼당 다수 포지션 | `LIMIT 1` 제거, 포지션 그룹 관리 | **M** |
| 부분 청산 | 포지션의 일부만 매도 | **S** |
| DCA (Dollar Cost Averaging) | 가격 하락 시 추가 매수 | **M** |

**전략 도메인 연관**: 전략 감사 7.1절 "변동성 역비례 포지션 사이징" — ATR 기반으로 매 분할 매수량 산출

---

### P2-A14: 이벤트 소싱 + 감사 로그

| 항목 | 내용 | 복잡도 |
|------|------|--------|
| 이벤트 저장소 | 모든 이벤트를 불변 테이블에 기록 | **L** |
| 상태 재구성 | 이벤트 리플레이로 특정 시점 상태 재현 | **XL** |
| 감사 추적 | 주문/포지션/리스크 상태 변경 이력 완전 보존 | **M** |

---

### P2-A15: 멀티 심볼 지원

| 항목 | 내용 | 복잡도 |
|------|------|--------|
| 심볼 설정 | `Settings.symbol` → `Settings.symbols: list[str]` | **S** |
| 심볼별 전략 매핑 | `strategy_id + symbol` 복합 키 | **M** |
| 포트폴리오 리스크 | 전체 노출도 관리, VaR 계산 | **L** |

---

### P2-A16: 시크릿 매니저 통합

| 항목 | 내용 | 복잡도 |
|------|------|--------|
| Docker Secrets | docker-compose secrets 기반 | **S** |
| HashiCorp Vault | API 키 중앙 관리 | **M** |

---

## 5. 교차 도메인 인터페이스 계약

### 5.1 아키텍처 → 전략 도메인

| 인터페이스 | 방향 | 형태 | 설명 |
|-----------|------|------|------|
| `DataStore Protocol` | 아키텍처 제공 | Python Protocol | OHLCV/시그널/매크로 CRUD. 전략 엔진이 `get_candles()` 소비 |
| `EventBus` | 아키텍처 제공 | Python 클래스 | 전략 엔진이 `OHLCVUpdateEvent` 구독, `SignalEvent` 발행 |
| `MarketTickEvent` | 아키텍처 발행 | Event dataclass | 전략 엔진이 실시간 가격 참조 (ATR 기반 손절 등) |
| `StrategyParams` | 전략 정의 | frozen dataclass | 아키텍처가 전략 파라미터를 그대로 수용 (기존 bit-trader 호환) |
| `BacktestDataProvider` | 아키텍처 제공 | Protocol | 백테스트 엔진이 히스토리컬 데이터 조회 (walk-forward 지원) |

```python
class BacktestDataProvider(Protocol):
    """백테스트 전용 데이터 인터페이스. 실시간 DataStore와 분리."""
    async def get_candles_range(self, symbol: str, tf: str,
                                 start: datetime, end: datetime) -> list[Candle]: ...
    async def get_macro_range(self, start: datetime, end: datetime) -> list[MacroSnapshot]: ...
```

### 5.2 아키텍처 → 대시보드 도메인

| 인터페이스 | 방향 | 형태 | 설명 |
|-----------|------|------|------|
| REST API `/api/v1/*` | 아키텍처 → 대시보드 | HTTP JSON | 13개 읽기 + 3개 제어 엔드포인트 (P1-A7 상세 참조) |
| WS API `/ws/v1/*` | 아키텍처 → 대시보드 | WebSocket JSON | 실시간 ticker + 봇 이벤트 스트림 |
| OpenAPI Spec | 아키텍처 → 대시보드 | auto-generated | FastAPI 자동 생성, 대시보드 타입 생성 기반 |

**대시보드 UX 시나리오 매핑**:

| UX 시나리오 (UX 감사 3.7절) | 필요 API | 목표 응답 시간 |
|----------------------------|----------|--------------|
| 아침 점검 (30초 목표) | `GET /bots` + `GET /pnl/summary` | <200ms |
| 긴급 상황 (10초 목표) | `WS events` + `POST /emergency-exit` | <500ms |
| 성과 분석 (30초 목표) | `GET /pnl/daily` + `GET /signals` + `GET /positions` | <300ms |

### 5.3 공유 데이터 계약 — 응답 스키마

```python
# API 응답에 사용되는 Pydantic 모델 (대시보드가 이 스키마를 기준으로 타입 생성)

class BotResponse(BaseModel):
    strategy_id: str
    state: str              # IDLE | SCANNING | EXECUTING | PAUSED | ...
    trading_mode: str       # paper | live
    symbol: str
    is_connected: bool      # WebSocket 연결 상태
    last_signal: SignalResponse | None
    open_position: PositionResponse | None
    risk: RiskStateResponse

class PositionResponse(BaseModel):
    id: int
    symbol: str
    side: str
    entry_price: str        # Decimal → string (정밀도 유지)
    amount: str
    current_price: str
    stop_loss: str
    unrealized_pnl: str
    unrealized_pnl_pct: float
    opened_at: datetime

class SignalResponse(BaseModel):
    id: int
    timestamp: datetime
    strategy_id: str
    symbol: str
    direction: str          # BUY | SELL | HOLD
    score: float
    components: dict[str, float]  # trend, momentum, volume, macro

class RiskStateResponse(BaseModel):
    consecutive_losses: int
    daily_pnl: str
    cooldown_until: datetime | None
    cooldown_active: bool
    daily_loss_pct: float
```

---

## 6. 기술 선택 의사결정 기록 (ADR)

### ADR-001: PostgreSQL + TimescaleDB vs 대안

| 기준 | PostgreSQL + TimescaleDB | DuckDB | ClickHouse |
|------|-------------------------|--------|------------|
| 동시 쓰기 | MVCC, 멀티 writer | 단일 writer (SQLite와 동일) | 뛰어남 |
| 시계열 최적화 | hypertable, 연속 집계, 자동 보존 정책 | 분석용 컬럼 스토어 | 뛰어나지만 운영 복잡 |
| asyncio 드라이버 | asyncpg (성숙, 고성능) | 없음 (sync만) | asynch 있으나 미성숙 |
| Docker 배포 | 공식 이미지, 1명령 실행 | 임베디드 전용 | 별도 서버, 운영 부담 |
| ORM/마이그레이션 | Alembic, SQLAlchemy 완전 지원 | 제한적 | 제한적 |
| 커뮤니티/문서 | 최대급 | 성장 중 | 성장 중 |
| 운영 성숙도 | 30년+ | 3년 | 10년 (분석 전용) |

**결정**: PostgreSQL + TimescaleDB
**근거**: 동시 쓰기 해결(C2), 시계열 최적화, asyncpg 성능(10-20x vs SQLAlchemy async), Docker 1-click 배포, 가장 넓은 에코시스템

---

### ADR-002: asyncpg vs SQLAlchemy async

| 기준 | asyncpg | SQLAlchemy async |
|------|---------|------------------|
| 성능 | 3x faster (벤치마크 기준) | ORM 오버헤드 |
| SQL 제어 | 직접 SQL (bit-trader 스타일 유지) | ORM 또는 Core 표현식 |
| 마이그레이션 | Alembic 별도 사용 | 통합 |
| 타입 매핑 | 수동 (but 명확) | 자동 |
| 학습 곡선 | 낮음 (raw SQL) | 중간 (ORM 패턴) |

**결정**: asyncpg + Alembic (마이그레이션만)
**근거**: bit-trader의 기존 패턴(직접 SQL)과 일관성 유지, ORM 불필요한 오버헤드 회피, 금융 시스템에서의 SQL 제어 투명성

---

### ADR-003: FastAPI vs 대안

| 기준 | FastAPI | Litestar | aiohttp |
|------|---------|----------|---------|
| async 네이티브 | O | O | O |
| OpenAPI 자동 생성 | O (대시보드 타입 생성 기반) | O | X |
| WebSocket 지원 | 내장 | 내장 | 내장 |
| Pydantic 통합 | 네이티브 (v2) | 네이티브 | 수동 |
| 에코시스템/문서 | 최대급 | 성장 중 | 성숙 |
| 성능 | 우수 (Uvicorn/Starlette) | 우수 | 우수 |

**결정**: FastAPI
**근거**: Pydantic v2 네이티브 통합(기존 Settings 호환), OpenAPI 자동 생성(대시보드 팀이 타입 생성 가능), 가장 넓은 커뮤니티

---

### ADR-004: in-process EventBus vs 외부 MQ

| 기준 | asyncio EventBus | Redis Streams | Kafka |
|------|-----------------|---------------|-------|
| 지연 | ~μs (in-process) | ~ms (네트워크) | ~ms |
| 운영 복잡도 | 없음 | Redis 서버 필요 | Kafka 클러스터 필요 |
| 내구성 | 없음 (프로세스 재시작 시 유실) | 내구적 | 내구적 |
| 적합 규모 | 단일 프로세스 | 멀티 프로세스 | 마이크로서비스 |

**결정**: asyncio 기반 in-process EventBus
**근거**: traderj는 단일 프로세스(멀티 전략 asyncio 태스크)로 운영. 이벤트 영속성은 DB에서 보장(주문/포지션 기록). 외부 MQ는 P2 분산 확장 시 검토

---

### ADR-005: structlog vs loguru (JSON mode)

| 기준 | structlog | loguru (JSON sink) |
|------|-----------|-------------------|
| 구조화 로깅 | 네이티브 설계 | 플러그인 방식 |
| 컨텍스트 바인딩 | `bind(strategy_id=X)` → 모든 하위 로그에 자동 포함 | `contextualize()` (thread-local) |
| asyncio 호환 | 완전 | 완전 |
| 성능 | 빠름 (pre-processing 파이프라인) | 빠름 |
| 기존 호환 | bit-trader loguru → 마이그레이션 필요 | bit-trader loguru → 최소 변경 |

**결정**: structlog
**근거**: 컨텍스트 바인딩이 멀티 전략 로깅에 핵심 (`strategy_id`가 모든 로그에 자동 포함). loguru의 `contextualize()`는 thread-local이라 asyncio 태스크 간 격리 문제. 마이그레이션 비용은 `logger.info("msg", key=val)` → `log.info("msg", key=val)` 수준으로 낮음

---

## 7. 구현 의존성 그래프 및 순서

```
P0-A3 (PostgreSQL) ──┐
                     ├──→ P0-A2 (Risk 영속화) ──→ P0-A5 (주문 안전성)
P0-A6 (거래소 추상화)─┤                                    │
                     ├──→ P0-A1 (이벤트 버스) ──→ P0-A4 (WebSocket 통합)
                     │                                     │
                     │                    ┌────────────────┘
                     │                    ▼
                     └──→ P1-A7 (API 서버) ──→ [대시보드 팀 언블록]
                              │
                     ┌────────┤
                     ▼        ▼
              P1-A8 (Docker)  P1-A10 (로깅+메트릭)
                     │
                     ▼
              P1-A9 (CI/CD)
                     │
                     ▼
              P1-A11 (테스트)
                     │
                     ▼
              P2-A12~A16 (확장 기능)
```

**추천 구현 순서**:

| 단계 | 항목 | 병렬 가능 | 언블록 대상 |
|------|------|----------|------------|
| 1 | P0-A3 (PostgreSQL) + P0-A6 (거래소 추상화) | 서로 병렬 | 전체 |
| 2 | P0-A2 (Risk 영속화) + P0-A1 (이벤트 버스) | 서로 병렬 | 실행 엔진, WebSocket |
| 3 | P0-A4 (WebSocket) + P0-A5 (주문 안전성) | 서로 병렬 | 실시간 기능 |
| 4 | P1-A7 (API 서버) | - | **대시보드 팀** |
| 5 | P1-A8 (Docker) + P1-A10 (로깅+메트릭) | 서로 병렬 | 운영 |
| 6 | P1-A9 (CI/CD) + P1-A11 (테스트) | 서로 병렬 | 품질 보증 |

**대시보드 팀 최초 연동 가능 시점**: 단계 4 완료 후 (API 서버 가용). REST API 스펙은 단계 1에서 OpenAPI YAML로 먼저 공유 가능 → 대시보드 팀이 mock 서버로 선행 개발

---

## 8. 공유 데이터 모델

> 모든 도메인이 참조하는 핵심 데이터 모델. `traderj/shared/models.py`에 정의.

```python
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


# ── Enums ──

class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"

class OrderType(StrEnum):
    LIMIT = "limit"
    MARKET = "market"

class OrderStatus(StrEnum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"

class SignalDirection(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

class PositionSide(StrEnum):
    LONG = "long"
    SHORT = "short"

class PositionStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


# ── Value Objects ──

@dataclass(frozen=True)
class Candle:
    symbol: str
    timeframe: str
    timestamp: datetime          # UTC TIMESTAMPTZ
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    id: int | None = None

@dataclass(frozen=True)
class Ticker:
    symbol: str
    last: Decimal
    bid: Decimal
    ask: Decimal
    high: Decimal
    low: Decimal
    volume: Decimal
    timestamp: datetime

@dataclass(frozen=True)
class Balance:
    currency: str
    total: Decimal
    free: Decimal
    used: Decimal

@dataclass(frozen=True)
class SignalComponents:
    trend: float
    momentum: float
    volume: float
    macro: float
    tf_scores: dict[str, dict[str, float]] = field(default_factory=dict)


# ── Entities ──

@dataclass
class Signal:
    timestamp: datetime
    symbol: str
    strategy_id: str
    direction: SignalDirection
    score: float
    timeframe: str
    components: SignalComponents
    details: dict[str, object] = field(default_factory=dict)
    id: int | None = None

@dataclass
class Order:
    symbol: str
    side: OrderSide
    order_type: OrderType
    amount: Decimal
    price: Decimal | None = None
    cost: Decimal | None = None
    fee: Decimal = Decimal(0)
    status: OrderStatus = OrderStatus.PENDING
    exchange_id: str | None = None
    is_paper: bool = True
    signal_id: int | None = None
    strategy_id: str = "default"
    idempotency_key: str = ""
    expected_price: Decimal | None = None
    actual_price: Decimal | None = None
    slippage_pct: float | None = None
    retry_count: int = 0
    error_message: str | None = None
    id: int | None = None
    created_at: datetime | None = None
    filled_at: datetime | None = None

@dataclass
class Position:
    symbol: str
    side: PositionSide = PositionSide.LONG
    entry_price: Decimal = Decimal(0)
    amount: Decimal = Decimal(0)
    current_price: Decimal = Decimal(0)
    stop_loss: Decimal = Decimal(0)
    unrealized_pnl: Decimal = Decimal(0)
    realized_pnl: Decimal = Decimal(0)
    status: PositionStatus = PositionStatus.OPEN
    entry_order_id: int | None = None
    exit_order_id: int | None = None
    strategy_id: str = "default"
    id: int | None = None
    opened_at: datetime | None = None
    closed_at: datetime | None = None

@dataclass
class RiskState:
    strategy_id: str
    consecutive_losses: int = 0
    daily_pnl: Decimal = Decimal(0)
    daily_date: str = ""
    cooldown_until: datetime | None = None
    total_trades: int = 0
    total_wins: int = 0
    updated_at: datetime | None = None

@dataclass(frozen=True)
class MacroSnapshot:
    timestamp: datetime
    fear_greed: float | None = None
    btc_dominance: float | None = None
    dxy: float | None = None
    nasdaq: float | None = None
    kimchi_premium: float | None = None
    market_score: float | None = None
    id: int | None = None

@dataclass
class DailyPnL:
    date: str                    # YYYY-MM-DD
    strategy_id: str
    realized: Decimal = Decimal(0)
    unrealized: Decimal = Decimal(0)
    total_value: Decimal = Decimal(0)
    trade_count: int = 0
    win_count: int = 0
    loss_count: int = 0

@dataclass
class PaperBalance:
    strategy_id: str
    krw: Decimal = Decimal("10000000")
    btc: Decimal = Decimal(0)
    initial_krw: Decimal = Decimal("10000000")
    updated_at: datetime | None = None
```

> **참고**: `float` → `Decimal` 전환은 bit-trader의 `float` 기반 모델과의 호환성 브레이킹 변경. 마이그레이션 시 전략 엔진 내부에서는 계산 성능을 위해 `float` 유지 가능하되, 저장/전달 시점에서 `Decimal` 변환. 이 결정은 전략 도메인과 합의 필요.
