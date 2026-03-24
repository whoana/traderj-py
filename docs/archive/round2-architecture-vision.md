# traderj 아키텍처 비전 및 요구사항 (Round 2)

**작성일**: 2026-03-02
**작성자**: bot-developer (아키텍처 도메인)
**기반**: Round 1 아키텍처 감사 + 교차 발견사항 종합

---

## 1. 아키텍처 비전

### 1.1 핵심 목표

bit-trader의 비즈니스 로직(전략 스코어링, 리스크 규칙)을 **재사용**하면서, 다음 3가지 구조적 한계를 해소하는 새로운 아키텍처를 구축한다:

1. **이벤트 기반 디커플링**: 스케줄러 직접 호출 → 이벤트 버스 기반 느슨한 결합
2. **실시간 데이터 파이프라인**: 폴링 → WebSocket 스트림 통합
3. **프로덕션 운영 준비**: Mac 로컬 → Docker + 모니터링 + CI/CD

### 1.2 아키텍처 원칙

| 원칙 | 설명 |
|------|------|
| **Event-Driven** | 모든 컴포넌트가 이벤트를 발행/구독하며 직접 참조하지 않음 |
| **Protocol-First** | Python Protocol로 인터페이스 정의 → 구현 교체 용이 |
| **Persistence-First Risk** | 리스크 상태를 반드시 DB에 영속화, 재시작 시 완전 복원 |
| **Observable** | 모든 핵심 경로에 메트릭 + 구조화된 로깅 내장 |
| **Fail-Safe** | 장애 시 포지션 보호 우선, 거래 중단보다 안전 |

### 1.3 대상 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────┐
│                     traderj 시스템                           │
│                                                             │
│  ┌──────────┐   ┌──────────────┐   ┌───────────────────┐   │
│  │ WebSocket│──▶│  Event Bus   │──▶│  Strategy Engine  │   │
│  │ Streams  │   │  (asyncio)   │   │  (Signal Gen)     │   │
│  └──────────┘   └──────┬───────┘   └────────┬──────────┘   │
│                        │                     │              │
│  ┌──────────┐   ┌──────▼───────┐   ┌────────▼──────────┐   │
│  │ Scheduler│──▶│  Data Store  │◀──│  Execution Engine  │   │
│  │ (OHLCV)  │   │ (PostgreSQL) │   │  (Order + Risk)    │   │
│  └──────────┘   └──────┬───────┘   └───────────────────┘   │
│                        │                                    │
│  ┌──────────┐   ┌──────▼───────┐   ┌───────────────────┐   │
│  │ REST API │◀──│  State Mgr   │──▶│  Notification Svc  │   │
│  │ (FastAPI)│   │  (StateMachine│   │  (Telegram+Slack) │   │
│  └────┬─────┘   └──────────────┘   └───────────────────┘   │
│       │                                                     │
│  ┌────▼─────┐   ┌──────────────┐                           │
│  │ WS API   │──▶│  Metrics     │                           │
│  │ (실시간) │   │ (Prometheus) │                           │
│  └──────────┘   └──────────────┘                           │
└─────────────────────────────────────────────────────────────┘
         │              │
    ┌────▼────┐   ┌─────▼─────┐
    │Dashboard│   │ Grafana   │
    │(Next.js)│   │(모니터링) │
    └─────────┘   └───────────┘
```

---

## 2. 요구사항 (P0 / P1 / P2)

---

### P0: 필수 — 실거래 전환 및 안전 운영의 전제조건

#### P0-A1: 이벤트 버스 도입

**문제**: TradingLoop이 13개 의존성에 직접 결합, 컴포넌트 추가/교체 시 수정 비용 급증
**해결**: asyncio 기반 경량 이벤트 버스 구현

```
이벤트 흐름 예시:
  WebSocket tick → MarketDataEvent 발행
    → StrategyEngine 구독 → SignalEvent 발행
      → ExecutionEngine 구독 → OrderEvent 발행
        → RiskManager 구독 → RiskStateEvent 발행
        → NotificationService 구독
        → DashboardWSAPI 구독
```

**핵심 이벤트 정의**:
| 이벤트 | 발행자 | 구독자 |
|--------|--------|--------|
| `MarketDataEvent` | WebSocket/OHLCV Collector | Strategy Engine, Dashboard |
| `SignalEvent` | Strategy Engine | Execution Engine, Dashboard, Logger |
| `OrderRequestEvent` | Execution Engine | Order Manager |
| `OrderFilledEvent` | Order Manager | Position Manager, Risk Manager, Notifier |
| `PositionUpdateEvent` | Position Manager | Risk Manager, Dashboard |
| `RiskAlertEvent` | Risk Manager | Execution Engine (halt), Notifier |
| `StopLossTriggeredEvent` | Risk Manager | Execution Engine, Notifier |
| `BotStateChangeEvent` | State Machine | Dashboard, Logger |

**인터페이스 계약** (전략 도메인):
```python
@dataclass(frozen=True)
class SignalEvent:
    timestamp: datetime
    symbol: str
    strategy_id: str
    direction: SignalDirection  # BUY | SELL | HOLD
    score: float
    components: dict[str, float]  # trend, momentum, volume, macro
    metadata: dict[str, Any]
```

**인터페이스 계약** (대시보드 도메인):
```python
@dataclass(frozen=True)
class MarketDataEvent:
    timestamp: datetime
    symbol: str
    price: float
    bid: float
    ask: float
    volume_24h: float
    source: str  # "websocket" | "rest_poll"
```

---

#### P0-A2: 리스크 상태 영속화

**문제**: [Critical C1] 연속 손실/쿨다운/일일 PnL이 메모리 전용, 재시작 시 초기화
**해결**: 리스크 상태를 DB에 영속화, 봇 기동 시 자동 복원

**데이터 계약** — `risk_state` 테이블:
```sql
CREATE TABLE risk_state (
    strategy_id     TEXT PRIMARY KEY,
    consecutive_losses INTEGER NOT NULL DEFAULT 0,
    daily_pnl       DECIMAL(18,2) NOT NULL DEFAULT 0,
    daily_date      DATE NOT NULL,
    cooldown_until  TIMESTAMPTZ,
    total_trades    INTEGER NOT NULL DEFAULT 0,
    total_wins      INTEGER NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**동작 규칙**:
- 모든 거래 결과 기록 시 `risk_state` 동기 업데이트
- 봇 시작 시 `risk_state` 로드 → `RiskManager` 상태 복원
- 쿨다운이 활성화된 상태에서 재시작해도 쿨다운 유지

---

#### P0-A3: 데이터베이스 전환 (SQLite → PostgreSQL)

**문제**: [Critical C2] 단일 writer 잠금, 멀티봇 동시 쓰기 불가
**해결**: PostgreSQL + asyncpg (또는 TimescaleDB for 시계열)

**스키마 설계 원칙**:
- 모든 테이블에 `strategy_id` 칼럼 포함 (signals, daily_pnl 포함)
- `timestamp` 타입을 `TIMESTAMPTZ`(UTC)로 통일
- candles 테이블: TimescaleDB hypertable 또는 월별 파티셔닝
- 인덱스: `(symbol, timeframe, timestamp DESC)` composite index

**마이그레이션 전략**:
- SQLAlchemy Core 또는 asyncpg 직접 사용 (ORM 오버헤드 최소화)
- Alembic 기반 마이그레이션 관리
- 기존 SQLite 데이터 → PostgreSQL 일괄 마이그레이션 스크립트 제공

**인터페이스 계약** (전체 도메인 공유):
```python
class DataStore(Protocol):
    async def upsert_candles(self, candles: list[Candle]) -> int: ...
    async def get_candles(self, symbol: str, tf: str, limit: int) -> list[Candle]: ...
    async def insert_signal(self, signal: Signal) -> int: ...
    async def insert_order(self, order: Order) -> int: ...
    async def get_open_position(self, symbol: str, strategy_id: str) -> Position | None: ...
    async def get_risk_state(self, strategy_id: str) -> RiskState: ...
    async def update_risk_state(self, state: RiskState) -> None: ...
```

---

#### P0-A4: WebSocket 실시간 데이터 통합

**문제**: [High H2] WebSocket 구현되어 있으나 미활용, 30초 폴링 손절
**해결**: WebSocket 스트림을 이벤트 버스에 통합

**동작 흐름**:
```
UpbitWebSocket
  → on_ticker() → EventBus.publish(MarketDataEvent)
    → RiskManager: 실시간 손절 체크 (밀리초 단위)
    → PositionManager: 미실현 PnL 실시간 갱신
    → DashboardWSAPI: 클라이언트에 실시간 가격 push
```

**Fallback 전략**:
- WebSocket 연결 실패 시 자동으로 30초 폴링으로 전환
- 재연결 성공 시 WebSocket 모드로 자동 복귀
- 모드 전환 시 `MarketDataEvent.source` 필드로 구분

**인터페이스 계약** (대시보드 도메인):
```python
# WebSocket API → Dashboard 실시간 push
class WSMessage:
    type: str           # "ticker" | "signal" | "order" | "position" | "bot_state"
    timestamp: datetime
    data: dict[str, Any]
```

---

#### P0-A5: 주문 실행 안전성 강화

**문제**: [High H3] 유령 주문 위험, 슬리피지 미고려, 실패 재시도 없음
**해결**: 주문 실행 파이프라인 재설계

**핵심 규칙**:
1. **Idempotency Key**: 모든 주문에 UUID 기반 멱등성 키 부여, 네트워크 재시도 시 중복 주문 방지
2. **주문 확인 루프**: `create_order()` → 3초 후 `fetch_order()` → 상태 확인, 최대 3회 재시도
3. **슬리피지 기록**: `expected_price`, `actual_price`, `slippage_pct` 필드 추가
4. **최소 주문 단위**: Upbit의 `market.limits`에서 최소 수량 자동 조회/적용
5. **Circuit Breaker**: 연속 주문 실패 N회 시 자동 거래 중단 + 알림

**데이터 계약** — 확장된 Order:
```python
@dataclass
class Order:
    # 기존 필드 유지 +
    idempotency_key: str         # UUID
    expected_price: float | None  # 주문 시점 가격
    actual_price: float | None    # 체결 가격
    slippage_pct: float | None    # (actual - expected) / expected
    retry_count: int = 0
    error_message: str | None = None
```

---

### P1: 중요 — 운영 안정성 및 확장 기반

#### P1-A6: API 서버 (FastAPI)

**목적**: 대시보드와 봇 엔진 사이의 API 계층 (대시보드가 DB 직접 접근하지 않음)

**REST API 엔드포인트**:
| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/v1/bots` | 실행 중인 봇 목록 + 상태 |
| POST | `/api/v1/bots/{id}/pause` | 봇 일시정지 |
| POST | `/api/v1/bots/{id}/resume` | 봇 재개 |
| GET | `/api/v1/positions` | 현재 포지션 목록 |
| GET | `/api/v1/orders` | 주문 이력 (pagination) |
| GET | `/api/v1/signals` | 시그널 이력 (pagination) |
| GET | `/api/v1/candles/{symbol}/{tf}` | OHLCV 데이터 |
| GET | `/api/v1/pnl/daily` | 일일 손익 |
| GET | `/api/v1/pnl/summary` | 전략별 성과 요약 |
| GET | `/api/v1/risk/{strategy_id}` | 리스크 상태 |
| GET | `/api/v1/health` | 시스템 헬스 체크 |

**WebSocket API 엔드포인트**:
| Path | 설명 |
|------|------|
| `/ws/v1/ticker/{symbol}` | 실시간 가격 스트림 |
| `/ws/v1/events` | 봇 이벤트 스트림 (시그널, 주문, 상태 변경) |

**인터페이스 계약** (대시보드 도메인):
- REST: JSON 응답, 표준 pagination (`?page=1&size=20`)
- WebSocket: JSON 메시지, `type` 필드로 이벤트 구분
- 인증: 초기엔 API Key 헤더, 추후 JWT 전환 가능

---

#### P1-A7: Docker 컨테이너화

**구성**:
```yaml
# docker-compose.yml
services:
  postgres:        # PostgreSQL + TimescaleDB
  traderj-engine:  # 트레이딩 엔진 (멀티 전략)
  traderj-api:     # FastAPI 서버
  prometheus:      # 메트릭 수집
  grafana:         # 모니터링 대시보드
```

**원칙**:
- 단일 `traderj-engine` 컨테이너 내에서 멀티 전략 asyncio 태스크로 실행
- `traderj-api`는 별도 컨테이너 (엔진 장애 시에도 API 가용)
- 환경변수 기반 설정 (`docker-compose.yml` + `.env`)
- 헬스 체크 엔드포인트로 Docker 자동 재시작

---

#### P1-A8: CI/CD 파이프라인

**GitHub Actions 워크플로우**:
```
PR 생성 시:
  → ruff check + ruff format --check
  → mypy --strict
  → pytest --cov=traderj (커버리지 80% 임계값)
  → Docker 빌드 테스트

main 병합 시:
  → Docker 이미지 빌드 + 레지스트리 푸시
  → (선택) 스테이징 자동 배포
```

---

#### P1-A9: 구조화된 로깅 + 메트릭

**로깅**:
- JSON 구조화 로깅 (structlog 또는 loguru JSON sink)
- 필수 컨텍스트: `strategy_id`, `symbol`, `correlation_id`
- 로그 레벨: ERROR → Telegram 알림 자동 트리거

**메트릭** (Prometheus):
| 메트릭 | 타입 | 설명 |
|--------|------|------|
| `traderj_signal_total` | Counter | 전략별 시그널 생성 수 (direction 레이블) |
| `traderj_order_total` | Counter | 주문 실행 수 (side, status 레이블) |
| `traderj_order_latency_seconds` | Histogram | 주문 체결 지연 |
| `traderj_position_pnl_krw` | Gauge | 현재 미실현 PnL |
| `traderj_risk_consecutive_losses` | Gauge | 연속 손실 횟수 |
| `traderj_ws_connected` | Gauge | WebSocket 연결 상태 |
| `traderj_api_request_duration` | Histogram | API 응답 시간 |
| `traderj_exchange_rate_limit_remaining` | Gauge | Rate limit 잔여량 |

---

#### P1-A10: 핵심 로직 테스트 작성

**목표 커버리지**: 80% (핵심 경로 100%)

**필수 테스트**:
| 모듈 | 테스트 범위 |
|------|------------|
| EventBus | 발행/구독, 에러 격리, 순서 보장 |
| StateMachine | 모든 전환 규칙, 잘못된 전환 거부, force_state |
| RiskManager | 영속화/복원, 쿨다운 경계값, 일일 리셋 |
| OrderManager | 멱등성, 재시도, 슬리피지 기록, circuit breaker |
| TradingLoop | 전체 시그널→실행 사이클 (mocked 의존성) |
| API | 엔드포인트별 응답 검증, 에러 처리 |

---

### P2: 개선 — 고급 기능 및 확장성

#### P2-A11: 멀티 거래소 추상화

```python
class ExchangeClient(Protocol):
    async def fetch_ohlcv(self, symbol: str, tf: str, limit: int) -> list[Candle]: ...
    async def fetch_ticker(self, symbol: str) -> Ticker: ...
    async def create_order(self, req: OrderRequest) -> Order: ...
    async def cancel_order(self, order_id: str, symbol: str) -> None: ...
    async def fetch_balance(self) -> list[Balance]: ...
```

- `UpbitClient`, `BinanceClient` 등이 동일 Protocol 구현
- 거래소 선택을 설정으로 관리

#### P2-A12: 고급 주문 유형

- 지정가 주문 (Limit Order)
- TWAP (Time-Weighted Average Price): 대량 주문 분할 실행
- 아이스버그 주문: 전체 수량의 일부만 노출
- OCO (One-Cancels-the-Other): 이익 실현 + 손절을 동시 설정

#### P2-A13: 멀티 포지션 지원

- 심볼당 다수 포지션 허용 (DCA, 피라미딩)
- 포지션 그룹 관리 (전략별 독립 포지션 풀)
- 부분 청산 지원

#### P2-A14: 이벤트 소싱 + 감사 로그

- 모든 상태 변경을 불변 이벤트로 기록
- 특정 시점 상태 재구성 가능
- 거래 감사 추적(audit trail) 완전 지원

---

## 3. 교차 도메인 인터페이스 요약

### 3.1 아키텍처 → 전략 도메인

| 인터페이스 | 방향 | 설명 |
|-----------|------|------|
| `DataStore.get_candles()` | 아키텍처 → 전략 | OHLCV 데이터 조회 Protocol |
| `SignalEvent` | 전략 → 아키텍처 | 시그널 생성 결과를 이벤트로 발행 |
| `StrategyConfig` | 전략 → 아키텍처 | 전략 파라미터 정의 (frozen dataclass 유지) |
| `BacktestDataProvider` | 아키텍처 → 전략 | 백테스트용 히스토리컬 데이터 인터페이스 |

### 3.2 아키텍처 → 대시보드 도메인

| 인터페이스 | 방향 | 설명 |
|-----------|------|------|
| REST API `/api/v1/*` | 아키텍처 → 대시보드 | 모든 읽기 데이터 |
| WebSocket `/ws/v1/*` | 아키텍처 → 대시보드 | 실시간 가격 + 이벤트 스트림 |
| `BotControlAPI` | 대시보드 → 아키텍처 | pause/resume/stop 제어 |

### 3.3 공유 데이터 모델

```python
# 모든 도메인이 공유하는 핵심 모델 (shared/models.py)
@dataclass(frozen=True)
class Candle:
    symbol: str
    timeframe: str
    timestamp: datetime  # UTC
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

@dataclass(frozen=True)
class Signal:
    id: int
    timestamp: datetime
    symbol: str
    strategy_id: str
    direction: SignalDirection
    score: float
    components: SignalComponents

@dataclass
class Position:
    id: int
    symbol: str
    strategy_id: str
    side: PositionSide
    entry_price: Decimal
    amount: Decimal
    stop_loss: Decimal
    status: PositionStatus
    unrealized_pnl: Decimal
    realized_pnl: Decimal
```

> **참고**: 금융 데이터에 `float` 대신 `Decimal` 사용 권장 — 부동소수점 오차로 인한 PnL 계산 오류 방지

---

## 4. 구현 순서 제안

```
Phase 1 (P0): 핵심 안전 인프라
  ├─ P0-A3: PostgreSQL 전환 + 스키마 설계
  ├─ P0-A2: 리스크 상태 영속화
  ├─ P0-A1: 이벤트 버스 구현
  ├─ P0-A4: WebSocket 통합
  └─ P0-A5: 주문 실행 안전성

Phase 2 (P1): 운영 인프라
  ├─ P1-A6: FastAPI 서버
  ├─ P1-A7: Docker 컨테이너화
  ├─ P1-A8: CI/CD
  ├─ P1-A9: 로깅 + 메트릭
  └─ P1-A10: 테스트

Phase 3 (P2): 확장 기능
  ├─ P2-A11: 멀티 거래소
  ├─ P2-A12: 고급 주문
  ├─ P2-A13: 멀티 포지션
  └─ P2-A14: 이벤트 소싱
```

**교차 의존성 고려**:
- P0-A3(DB 전환)이 모든 것의 기반 → 최우선 착수
- P0-A1(이벤트 버스)이 P0-A4(WebSocket), P1-A6(API)의 전제
- P1-A6(API)이 대시보드 도메인의 전제 → 대시보드 팀과 병렬 작업 가능 시점 결정

---

## 5. 기술 스택 제안

| 구분 | 선택 | 대안 | 선택 이유 |
|------|------|------|----------|
| 언어 | Python 3.13 async | - | bit-trader 자산 재사용, ccxt 호환 |
| DB | PostgreSQL 16 + TimescaleDB | DuckDB | 동시 쓰기, 시계열 최적화, 운영 성숙도 |
| DB 드라이버 | asyncpg | SQLAlchemy async | 성능 (10-20x faster), 직접 SQL 제어 |
| API | FastAPI | - | async 네이티브, 자동 OpenAPI 문서 |
| 이벤트 버스 | asyncio Queue + 커스텀 | aiokafka | 단일 프로세스이므로 외부 MQ 불필요 |
| 메트릭 | prometheus-client | - | 업계 표준, Grafana 통합 |
| 로깅 | structlog (JSON) | loguru JSON sink | 구조화 + 성능 |
| 테스트 | pytest + pytest-asyncio + pytest-cov | - | 기존 호환 |
| CI | GitHub Actions | - | 표준 |
| 컨테이너 | Docker + docker-compose | - | 표준 |
