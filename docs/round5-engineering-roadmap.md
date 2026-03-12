# Round 5: 엔지니어링 로드맵

**작성일**: 2026-03-03
**작성자**: bot-developer (Engineering Architect)
**기반**: Round 3 TDR (Rev.1) + Round 4 상세 설계서 3건 (아키텍처/전략/대시보드)
**상태**: Draft — 팀 리더 검토 대기

---

## 목차

1. [Phase별 엔지니어링 작업 순서](#1-phase별-엔지니어링-작업-순서)
2. [테스트 전략](#2-테스트-전략)
3. [CI/CD 파이프라인](#3-cicd-파이프라인)
4. [배포 런북](#4-배포-런북)
5. [인프라 마일스톤](#5-인프라-마일스톤)
6. [교차 의존성](#6-교차-의존성)
7. [리스크 & 완화 전략](#7-리스크--완화-전략)

---

## 1. Phase별 엔지니어링 작업 순서

### 1.0 의존성 그래프 요약

```
Phase 0 (기반)                Phase 1 (코어)               Phase 2 (엔진)               Phase 3 (API+통합)           Phase 4 (최적화+안정화)
─────────────────            ─────────────────            ─────────────────            ─────────────────            ─────────────────
shared/ 패키지        ──→    DataStore(PG) 구현    ──→    StrategyEngine 통합   ──→    REST API 전체 구현    ──→    성능 최적화
PostgreSQL 스키마     ──→    EventBus 구현         ──→    OrderManager(멱등+CB) ──→    WebSocket 핸들러      ──→    E2E 테스트
Docker 기반 구성      ──→    ExchangeClient 구현   ──→    PositionManager       ──→    IPC 클라이언트/서버   ──→    모니터링 대시보드
Alembic 마이그레이션  ──→    RateLimiter 구현      ──→    RiskManager(영속화)   ──→    OpenAPI 타입 생성     ──→    보안 감사
CI 기본 설정          ──→    WebSocket Stream      ──→    StateMachine          ──→    Docker 전체 빌드      ──→    배포 자동화
OpenAPI YAML 초안              Scheduler(APScheduler)     CircuitBreaker               Prometheus+Grafana           문서화
                               structlog 설정              OHLCV Collector              Telegram 알림
                                                           MacroCollector
```

---

### Phase 0: 프로젝트 기반 구축

**목표**: 모노레포 골격, 공유 패키지, DB 스키마, Docker 기본 구성, CI 파이프라인 초기화
**선행 조건**: 없음 (최초 작업)
**예상 산출물**: 빌드 가능한 모노레포 + DB 스키마 마이그레이션 + CI green

#### P0-E1: 모노레포 구조 생성

| 작업 | 상세 | 산출물 |
|------|------|--------|
| 디렉터리 구조 생성 | TDR-007 확정 구조 (`shared/`, `engine/`, `api/`, `dashboard/`, `scripts/`, `migrations/`) | 전체 디렉터리 트리 |
| shared 패키지 초기화 | `pyproject.toml` (name=traderj-shared), `py.typed` | `shared/pyproject.toml` |
| shared/models.py | Candle, Order, Position, Signal, RiskState, PaperBalance, DailyPnL, MacroSnapshot, BotState, **BacktestResult** 데이터클래스 | Round 4 §4 스키마 기반 (BacktestResult P1 예비 정의 선행) |
| shared/events.py | 13개 이벤트 타입: MarketTickEvent, OHLCVUpdateEvent, SignalEvent, OrderRequestEvent, OrderFilledEvent, PositionOpenedEvent, PositionClosedEvent, StopLossTriggeredEvent, RiskAlertEvent, BotStateChangeEvent, **RegimeChangeEvent**, **RiskStateEvent**, **MarketDataEvent** | Round 4 §5.1 (교차 검증 후 3개 추가) |
| shared/protocols.py | ExchangeClient, WebSocketStream, DataStore, AnalyticsStore, **ScorePlugin** Protocol 정의 | Round 4 §6.1 + 전략 §7.1 ScorePlugin (P2 ML 플러그인 인터페이스 선행 등록) |
| shared/enums.py | OrderSide, OrderType, OrderStatus, BotState, TradingMode 등 | Round 4 스키마 기반 |
| engine 패키지 초기화 | `pyproject.toml` (shared 의존), Dockerfile, `__init__.py` | engine 빌드 가능 |
| api 패키지 초기화 | `pyproject.toml` (shared + FastAPI 의존), Dockerfile | api 빌드 가능 |
| dashboard 초기화 | `pnpm create next-app@15`, Dockerfile, TailwindCSS + shadcn/ui 설정 | dashboard 빌드 가능 |
| Makefile 작성 | `make engine-test`, `make api-test`, `make dashboard-test`, `make up`, `make down` | 루트 Makefile |
| .env.example | DB, Exchange, API, Telegram, Trading 설정 템플릿 | Round 4 §10.3 |

#### P0-E2: 데이터베이스 스키마 + 마이그레이션

| 작업 | 상세 | 산출물 |
|------|------|--------|
| Alembic 초기화 | `alembic.ini`, `env.py` (asyncpg 연결 설정) | `migrations/` |
| 001_initial_schema | candles(hypertable), signals, orders, positions, risk_state, bot_state, paper_balances, daily_pnl, macro_snapshots, bot_commands | Round 4 §4.1 SQL 그대로 |
| 002_timescaledb_setup | `create_hypertable('candles', ...)`, 연속 집계 `candles_1d_summary`, 보존 정책 2년, 인덱스 | Round 4 §4.1 |
| 003_backtest_results | backtest_results 테이블 (P1 예비, 스키마만 생성) | Round 4 §4.1 |
| 마이그레이션 검증 스크립트 | `scripts/validate_schema.py` — 마이그레이션 후 테이블/인덱스 존재 확인 | 자동화 검증 |

#### P0-E3: Docker 기본 구성

| 작업 | 상세 | 산출물 |
|------|------|--------|
| docker-compose.yml | postgres(TimescaleDB), engine, api, dashboard, prometheus, grafana — Round 4 §10.1 구조 | 루트 docker-compose.yml |
| docker-compose.dev.yml | 개발용 오버라이드: 볼륨 마운트, hot-reload, SQLite 옵션 | 개발 환경 |
| engine/Dockerfile | Python 3.13-slim, shared 설치, Poetry install | Round 4 §10.2 |
| api/Dockerfile | Python 3.13-slim, shared 설치, uvicorn | Round 4 §10.2 |
| dashboard/Dockerfile | Node 20-alpine, pnpm, multi-stage build | Round 4 §10.2 |
| prometheus.yml | engine:8001/metrics, api:8000/metrics 스크래핑 설정 | 메트릭 수집 |
| 헬스체크 구성 | postgres: `pg_isready`, engine: Python health module, api: `/api/v1/health` curl | docker-compose 내장 |

#### P0-E4: CI 기본 설정 + OpenAPI 초안

| 작업 | 상세 | 산출물 |
|------|------|--------|
| .github/workflows/engine.yml | Python lint(ruff) + type-check(mypy) + unit test(pytest) | engine/ 변경 시 트리거 |
| .github/workflows/api.yml | Python lint + type-check + unit test | api/ 변경 시 트리거 |
| .github/workflows/dashboard.yml | ESLint + TypeScript check + unit test(vitest) | dashboard/ 변경 시 트리거 |
| ruff.toml | Python 린트 규칙 (line-length=120, select=["E","W","F","I","UP"]) | 루트 설정 |
| mypy.ini | strict mode, asyncpg stubs | 루트 설정 |
| OpenAPI YAML 초안 | REST API 20개 엔드포인트 스키마 — Round 4 §8.1 기반 | `api/openapi-draft.yaml` |
| generate_api_types.sh | `openapi-typescript` CLI로 TypeScript 타입 자동 생성 | `scripts/generate_api_types.sh` |

> **대시보드 팀 언블록**: P0-E4의 OpenAPI 초안을 대시보드 팀에 전달. `msw`(Mock Service Worker) 또는 `json-server`로 mock API 기반 UI 개발 착수 가능.

---

### Phase 1: 코어 인프라 구현

**목표**: DB 접근 레이어, 이벤트 버스, 거래소 클라이언트 — 엔진의 기반 모듈 완성
**선행 조건**: Phase 0 완료 (shared 패키지, DB 스키마, Docker 기본)
**예상 산출물**: engine 단독 실행 가능 (DB 연결 + 이벤트 발행/구독 + 거래소 API 호출)

#### P1-E1: DataStore 구현 (PostgreSQL + SQLite)

| 작업 | 상세 | 산출물 |
|------|------|--------|
| PostgresDataStore | DataStore Protocol 구현. asyncpg 직접 SQL, 파라미터 바인딩($1, $2), `row_to_model()` 제네릭 헬퍼 | `engine/data/pg_store.py` |
| SQLiteDataStore | dev/test용 DataStore 구현. aiosqlite 기반, 동일 인터페이스 | `engine/data/sqlite_store.py` |
| 연결 풀 관리 | asyncpg `create_pool(min_size=2, max_size=10)`, graceful shutdown | pg_store.py 내장 |
| candles upsert 최적화 | `INSERT ... ON CONFLICT DO UPDATE`, 배치 upsert (executemany) | 성능 테스트 포함 |
| DataStore 단위 테스트 | SQLite 구현체 기반 CRUD 테스트 전 메서드 (30+ 테스트 케이스) | `engine/tests/unit/test_data_store.py` |
| DataStore 통합 테스트 | PostgreSQL 실제 연결 테스트 (Docker Compose 기반) | `tests/integration/test_pg_store.py` |

#### P1-E2: EventBus 구현

| 작업 | 상세 | 산출물 |
|------|------|--------|
| AsyncioEventBus | Round 4 §5.2 구현 그대로. subscribe/unsubscribe/publish, 에러 격리, Prometheus 메트릭 | `engine/loop/event_bus.py` |
| 이벤트 타입 검증 | frozen dataclass 직렬화/역직렬화 테스트, JSON 변환 유틸 | `shared/events.py` + 테스트 |
| 메트릭 계측 | `traderj_event_bus_published_total`, `traderj_event_bus_handler_latency_seconds` | prometheus_client 연동 |
| EventBus 단위 테스트 | 이벤트 발행/구독, 에러 격리, 언서브스크라이브 | `engine/tests/unit/test_event_bus.py` |

#### P1-E3: 거래소 클라이언트 구현

| 작업 | 상세 | 산출물 |
|------|------|--------|
| UpbitExchangeClient | ExchangeClient Protocol 구현. ccxt async 래핑 | `engine/exchange/client.py` |
| SlidingWindowRateLimiter | market(10/s), order(8/s), exchange(30/s) — bit-trader 검증 설정 | `engine/exchange/rate_limiter.py` |
| UpbitWebSocketStream | WebSocketStream Protocol 구현. Upbit WS ticker 구독, 자동 재연결 | `engine/exchange/websocket.py` |
| 거래소 모델 변환 | ccxt 응답 → shared 모델 변환 로직 | `engine/exchange/models.py` |
| Mock ExchangeClient | 테스트용 가짜 거래소 (고정 가격/잔고 반환) | `engine/tests/fixtures/mock_exchange.py` |
| Rate Limiter 테스트 | 윈도우 내 요청 제한 검증, 윈도우 슬라이딩 검증 | `engine/tests/unit/test_rate_limiter.py` |

#### P1-E4: 보조 인프라

| 작업 | 상세 | 산출물 |
|------|------|--------|
| structlog 설정 | JSON 렌더러, 컨텍스트 바인딩 (`strategy_id`), asyncio 호환 | `engine/config/logging.py` |
| Scheduler 래퍼 | APScheduler AsyncIOScheduler 래핑, cron job 등록 인터페이스 | `engine/loop/scheduler.py` |
| pydantic-settings 설정 | `.env` 기반 설정 로드, DB/Exchange/API/Trading 구분 | `engine/config/settings.py` |
| AppOrchestrator 골격 | DI 컨테이너, 수명주기 관리 (startup/shutdown), 시그널 핸들러(SIGTERM) | `engine/app.py` |

> **전략 팀 언블록**: P1-E1 SQLiteDataStore + P1-E2 EventBus 완료 시 전략 팀이 SignalGenerator 통합 테스트 착수 가능.

---

### Phase 2: 트레이딩 엔진 핵심 로직

**목표**: 시그널 → 주문 → 포지션 → 리스크 전체 파이프라인 구축
**선행 조건**: Phase 1 완료 (DataStore, EventBus, ExchangeClient)
**예상 산출물**: Paper trading 모드로 전체 거래 사이클 실행 가능

#### P2-E1: 주문 관리

| 작업 | 상세 | 산출물 |
|------|------|--------|
| OrderManager | Round 4 §7.1 주문 실행 파이프라인 구현. 멱등성(idempotency_key), 확인 루프(3회×3초), 슬리피지 기록 | `engine/execution/order_manager.py` |
| PaperOrderExecutor | Paper 모드 내부 주문 실행. 잔고 차감, 즉시 체결 시뮬레이션 | OrderManager 내장 |
| CircuitBreaker | Round 4 §7.2 상태 머신 (CLOSED/OPEN/HALF_OPEN). 3연속 실패→OPEN, 5분 후→HALF_OPEN | `engine/execution/circuit_breaker.py` |
| OrderManager 테스트 | 멱등성 검증, CB 상태 전이, 슬리피지 계산, 재시도 로직 | 단위 테스트 20+ |

#### P2-E2: 포지션 관리

| 작업 | 상세 | 산출물 |
|------|------|--------|
| PositionManager | 포지션 open/close, unrealized PnL 갱신 (MarketTickEvent 구독), 포지션 DB 영속화 | `engine/execution/position_manager.py` |
| Paper 잔고 관리 | `atomic_buy_balance`, `atomic_sell_balance` — 원자적 잔고 변경 | DataStore 메서드 |
| PositionManager 테스트 | 포지션 오픈/클로즈, PnL 정확성, 잔고 일관성 | 단위 테스트 15+ |

#### P2-E3: 리스크 매니저 (영속화)

| 작업 | 상세 | 산출물 |
|------|------|--------|
| RiskManager | Round 4 §5: ATR 기반 동적 손절, 변동성 역비례 포지션 사이징, 변동성 캡, 일일 손실 한도, 연속 손실 쿨다운 | `engine/execution/risk.py` |
| Write-Through 영속화 | risk_state 테이블에 매 변경마다 즉시 기록. DB 실패 시 인메모리 유지 + 텔레그램 알림 | 영속화 레이어 |
| 실시간 손절 체크 | MarketTickEvent → RiskManager.on_tick() → StopLossTriggeredEvent 발행 (100ms 이내) | EventBus 연동 |
| RiskManager 테스트 | ATR 손절 계산, 포지션 사이징 범위, 쿨다운 활성/해제, 변동성 캡 차단, daily reset | 단위 테스트 25+ |

#### P2-E4: 상태 머신 + 스케줄러 통합

| 작업 | 상세 | 산출물 |
|------|------|--------|
| StateMachine | 9개 상태 (IDLE→STARTING→SCANNING→VALIDATING→EXECUTING→LOGGING→MONITORING→PAUSED→SHUTTING_DOWN), DB 영속화, force_state 복구 | `engine/loop/state.py` |
| Scheduler 잡 등록 | OHLCV 수집 (15m/1h/4h/1d), 매크로 스냅샷 (6h), 일일 PnL (00:00 UTC), 헬스체크 (1m) | `engine/loop/scheduler.py` |
| OHLCV Collector | ccxt fetch_ohlcv → DataStore.upsert_candles, OHLCVUpdateEvent 발행 | `engine/data/ohlcv.py` |
| MacroCollector | Fear&Greed, BTC Dominance, DXY, Funding Rate 수집 | `engine/data/macro.py` |
| 전략 엔진 통합 | OHLCVUpdateEvent → StrategyEngine.on_ohlcv() → SignalEvent 발행. quant-expert SignalGenerator 호출 | `engine/strategy/` 통합 |

#### P2-E5: Telegram 알림

| 작업 | 상세 | 산출물 |
|------|------|--------|
| TelegramNotifier | 거래 알림, 손절 알림, 일일 요약, 에러 알림. EventBus 구독 | `engine/notify/telegram.py` |
| 메시지 포맷 | 마크다운 포맷, KRW/BTC 단위 변환, 이모지 상태 표시 | 메시지 템플릿 |

---

### Phase 3: API 서버 + 서비스 통합

**목표**: FastAPI REST+WebSocket 서버, Engine↔API IPC, Docker 전체 빌드
**선행 조건**: Phase 2 완료 (엔진 전체 동작)
**예상 산출물**: docker-compose up으로 전체 시스템 기동. 대시보드 실제 API 연동 가능

#### P3-E1: FastAPI REST API

| 작업 | 상세 | 산출물 |
|------|------|--------|
| App Factory | FastAPI 앱 생성, 미들웨어 등록, 라우터 마운트 | `api/main.py` |
| 인증 미들웨어 | X-API-Key 헤더 검증, `/health` 제외 | `api/middleware/auth.py` |
| CORS 미들웨어 | `localhost:3000` 허용, 프로덕션 설정 분리 | `api/middleware/cors.py` |
| Prometheus 미들웨어 | 요청 수, 응답 시간 히스토그램, 에러율 | `api/middleware/metrics.py` |
| 의존성 주입 | DataStore(read-only), EngineClient(IPC) 주입 | `api/deps.py` |
| REST 라우트 20개 | Round 4 §8.1 전체 구현. Pydantic v2 응답 스키마, 페이지네이션, 필터 | `api/routes/*.py` |
| 응답 스키마 | BotResponse, PositionResponse, OrderResponse, SignalResponse, PnLAnalytics 등 | `api/schemas/*.py` |
| REST API 테스트 | 각 엔드포인트 정상/에러 응답, 인증, 페이지네이션 | 단위/통합 테스트 40+ |

#### P3-E2: WebSocket 핸들러

| 작업 | 상세 | 산출물 |
|------|------|--------|
| WSConnectionManager | WebSocket 연결 수락, 채널 구독/해지 관리 | `api/ws/handler.py` |
| 채널 브로드캐스터 | ticker, bot_status, orders, positions, signals, alerts — 6개 채널 | `api/ws/channels.py` |
| HeartbeatManager | 30초 ping, 60초 무응답 시 연결 끊김 판정, 리소스 정리 | `api/ws/heartbeat.py` |
| 메시지 프로토콜 구현 | Round 4 §9.3: subscribe/unsubscribe/data/pong/error | Pydantic 모델 |
| WebSocket 테스트 | 연결/구독/데이터 수신/해지/재연결 시나리오 | 통합 테스트 10+ |

#### P3-E3: IPC (Engine ↔ API)

| 작업 | 상세 | 산출물 |
|------|------|--------|
| IPC 서버 (Engine) | Unix Domain Socket `/tmp/traderj.sock`, JSON-lines 프로토콜 | `engine/loop/ipc_server.py` |
| IPC 클라이언트 (API) | UDS 연결, 봇 제어 명령 전송, 이벤트 스트림 수신 | `api/ipc_client.py` |
| Fallback 큐 | UDS 장애 시 `bot_commands` 테이블 큐잉, Engine에서 폴링 | DB 기반 fallback |
| EventBus → WS Bridge | Engine EventBus 이벤트를 IPC 경유 API WS 채널로 중계 | 브릿지 로직 |

#### P3-E4: OpenAPI 타입 생성 + 대시보드 연동

| 작업 | 상세 | 산출물 |
|------|------|--------|
| OpenAPI 자동 생성 | FastAPI `/openapi.json` 스키마 확정 | 자동 생성 |
| TypeScript 타입 생성 | `openapi-typescript` CLI → `dashboard/src/types/api.ts` | 자동화 스크립트 |
| API 클라이언트 | fetch 래퍼 (baseURL, API-Key, 에러 핸들링) | `dashboard/src/lib/api-client.ts` |
| Mock → 실제 API 전환 | 대시보드의 msw mock을 실제 FastAPI 엔드포인트로 교체 | 대시보드 팀 협업 |

#### P3-E5: Docker 전체 빌드 + 메트릭

| 작업 | 상세 | 산출물 |
|------|------|--------|
| 전체 docker-compose up 검증 | 6개 서비스 동시 기동, 헬스체크 통과, 네트워크 연결 | 통합 검증 |
| Prometheus 설정 | 엔진 + API 메트릭 스크래핑, 커스텀 메트릭 13개 등록 | `prometheus.yml` |
| Grafana 대시보드 | 트레이딩 메트릭 대시보드 (PnL, 주문 수, 지연, 에러율, DB 연결) | JSON 프로비저닝 |
| 로그 집약 | structlog JSON → Docker 로그 드라이버 → 기본 stdout 수집 | 로그 설정 |

---

### Phase 4: 최적화 + 안정화

**목표**: 성능 최적화, 보안 강화, E2E 테스트, 배포 자동화, 문서화
**선행 조건**: Phase 3 완료 (전체 시스템 동작)
**예상 산출물**: 프로덕션 준비 완료

#### P4-E1: 성능 최적화

| 작업 | 상세 | 산출물 |
|------|------|--------|
| DB 쿼리 최적화 | EXPLAIN ANALYZE로 슬로우 쿼리 식별, 인덱스 추가, 쿼리 리팩터링 | 성능 벤치마크 |
| asyncpg 커넥션 풀 튜닝 | `shared_buffers`, `work_mem`, 풀 사이즈 최적화 | PostgreSQL 설정 |
| EventBus 처리량 테스트 | 1000 events/sec 부하 테스트, 핸들러 병목 식별 | 부하 테스트 스크립트 |
| WebSocket 동시 연결 | 5+ 동시 구독 클라이언트, 메시지 지연 측정 | 성능 테스트 |
| API 응답 시간 목표 검증 | Round 4 §11.3: 봇 상태 <200ms, 긴급 제어 <500ms, 캔들 <1000ms | 벤치마크 결과 |

#### P4-E2: 보안 강화

| 작업 | 상세 | 산출물 |
|------|------|--------|
| SQL 인젝션 감사 | asyncpg 파라미터 바인딩 전수 검사, 문자열 포맷 쿼리 금지 확인 | 코드 리뷰 체크리스트 |
| API Key 관리 | `.env`에서만 관리, 로그 출력 마스킹, 환경별 분리 | 보안 정책 |
| CORS 정책 강화 | 프로덕션에서는 특정 origin만 허용 | 환경별 설정 |
| 의존성 보안 스캔 | `pip-audit`, `pnpm audit` CI 통합 | GitHub Actions |
| Docker 보안 | non-root 사용자, read-only 파일시스템, 최소 이미지(slim/alpine) | Dockerfile 강화 |

#### P4-E3: E2E 테스트

| 작업 | 상세 | 산출물 |
|------|------|--------|
| Engine-API IPC 테스트 | 봇 제어 명령 → Engine 상태 변경 → WS 이벤트 확인 | `tests/integration/test_engine_api_ipc.py` |
| Full Trade Cycle 테스트 | Paper 모드: OHLCV 수집 → 시그널 생성 → 주문 → 포지션 → PnL | `tests/integration/test_full_trade_cycle.py` |
| Docker Compose 통합 테스트 | docker-compose up → 헬스체크 → API 호출 → docker-compose down | CI 통합 테스트 |
| 장애 시나리오 테스트 | DB 다운, Exchange 타임아웃, IPC 장애 → 복구 확인 | 카오스 테스트 |

#### P4-E4: 배포 자동화 + 문서화

| 작업 | 상세 | 산출물 |
|------|------|--------|
| 배포 자동화 | GitHub Actions deploy workflow (§3 CI/CD 참조) | `.github/workflows/deploy.yml` |
| 배포 런북 작성 | §4 배포 런북 완성 | 운영 문서 |
| 모니터링 알림 규칙 | Grafana Alert: 에러율 >5%, 응답 지연 >2s, DB 연결 실패, 엔진 헬스체크 실패 | Grafana Alert 설정 |
| 개발자 가이드 | 로컬 개발 환경 설정, 테스트 실행, 기여 가이드 | `docs/dev-guide.md` |

---

## 2. 테스트 전략

### 2.1 테스트 피라미드

```
                    ┌───────────────┐
                    │   E2E Tests   │  5% — Docker Compose 기반 전체 시스템
                    │   (~10개)     │  장애 시나리오, 전체 거래 사이클
                    ├───────────────┤
                    │  Integration  │  20% — DB 연결, IPC, WebSocket
                    │   (~50개)     │  서비스 간 통신 검증
                    ├───────────────┤
                    │  Unit Tests   │  75% — 순수 로직, 모델, 유틸
                    │   (~200개)    │  빠른 피드백, 높은 커버리지
                    └───────────────┘
```

### 2.2 커버리지 목표

| 패키지 | 커버리지 목표 | 이유 |
|--------|-------------|------|
| `shared/` | **95%** | 공유 모델/이벤트/프로토콜 — 전 서비스 기반 |
| `engine/execution/` | **90%** | 주문/포지션/리스크 — 금융 로직 정확성 필수 |
| `engine/exchange/` | **80%** | ccxt 래퍼 — 외부 API 모킹 한계 |
| `engine/data/` | **85%** | DataStore — CRUD 전 메서드 |
| `engine/loop/` | **80%** | EventBus, StateMachine — 상태 전이 검증 |
| `engine/strategy/` | **85%** | 지표/스코어링/시그널 — quant-expert 도메인 |
| `api/routes/` | **85%** | REST 엔드포인트 — 정상/에러 응답 |
| `api/ws/` | **75%** | WebSocket — 비동기 통신 테스트 복잡 |
| `dashboard/` (컴포넌트) | **70%** | UI 컴포넌트 — 시각적 검증은 E2E에서 |
| **전체 프로젝트** | **80%+** | CI 게이트 기준 |

### 2.3 테스트 도구

| 도구 | 용도 | 적용 범위 |
|------|------|----------|
| **pytest** | Python 단위/통합 테스트 프레임워크 | engine/, api/ |
| **pytest-asyncio** | async/await 테스트 지원 | asyncpg, EventBus, ccxt |
| **pytest-cov** | 커버리지 측정 | 전체 Python |
| **factory_boy** | 테스트 데이터 팩토리 (Candle, Order, Position 등) | 모델 생성 |
| **pytest-docker** | Docker Compose 기반 통합 테스트 | PostgreSQL 실제 연결 |
| **httpx** | FastAPI TestClient (async) | api/routes/ |
| **vitest** | Next.js 단위 테스트 | dashboard/ |
| **React Testing Library** | 컴포넌트 렌더링 테스트 | dashboard/components/ |
| **Playwright** | E2E 브라우저 테스트 (P4) | 전체 시스템 |

### 2.4 테스트 유형별 상세

#### 단위 테스트 (Unit)

```
engine/tests/unit/
├── test_data_store.py          # DataStore CRUD (SQLite 기반)
├── test_event_bus.py           # 이벤트 발행/구독/에러 격리
├── test_rate_limiter.py        # 요청 제한, 윈도우 슬라이딩
├── test_order_manager.py       # 멱등성, CB 상태 전이, 슬리피지
├── test_position_manager.py    # 포지션 open/close, PnL 계산
├── test_risk_manager.py        # ATR 손절, 포지션 사이징, 쿨다운
├── test_circuit_breaker.py     # CLOSED→OPEN→HALF_OPEN 전이
├── test_state_machine.py       # 9개 상태 전이 매트릭스
├── test_indicators.py          # 지표 계산 정확성 (교차 검증)
├── test_normalizer.py          # Z-score 계산, tanh 매핑
├── test_scoring.py             # TimeframeScore, 가중 합산
├── test_signal_generator.py    # 시그널 생성 파이프라인
├── test_regime_classifier.py   # 4-레짐 분류, 히스테리시스
└── test_backtest_metrics.py    # Sharpe/Sortino/Calmar 계산

api/tests/unit/
├── test_routes_bots.py         # 봇 상태/제어 API
├── test_routes_positions.py    # 포지션 API
├── test_routes_orders.py       # 주문 API
├── test_routes_candles.py      # OHLCV API
├── test_routes_pnl.py          # PnL API
├── test_routes_health.py       # 헬스체크
├── test_auth_middleware.py      # API Key 인증
└── test_ws_handler.py          # WebSocket 메시지 처리
```

#### 통합 테스트 (Integration)

```
tests/integration/
├── test_pg_store.py            # PostgreSQL 실제 CRUD
├── test_timescaledb.py         # hypertable, 연속 집계 검증
├── test_engine_api_ipc.py      # UDS IPC 양방향 통신
├── test_ws_channels.py         # WebSocket 채널 구독/데이터 수신
├── test_exchange_mock.py       # ccxt 모킹 + 전체 주문 흐름
├── test_full_trade_cycle.py    # Paper 모드 전체 사이클
└── conftest.py                 # Docker PostgreSQL fixture
```

### 2.5 주요 테스트 규칙

1. **금융 계산 정밀도**: Decimal 비교 시 `assert abs(actual - expected) < Decimal("0.00000001")`
2. **비동기 테스트**: 모든 async 테스트는 `@pytest.mark.asyncio` 데코레이터
3. **외부 의존성 모킹**: ccxt, Telegram, 외부 API는 항상 mock. 실제 호출 금지
4. **시간 제어**: datetime.now() 대신 주입 가능한 `clock` 사용 (백테스트/쿨다운 테스트)
5. **테스트 격리**: 각 테스트는 독립적. DB 상태 공유 금지 (트랜잭션 롤백 또는 개별 스키마)

---

## 3. CI/CD 파이프라인

### 3.1 전체 흐름도

```
                Push / PR
                    │
                    ▼
        ┌───────────────────────┐
        │   변경 감지 (paths)     │
        │   engine/ api/ dashboard/│
        └───────────┬───────────┘
                    │
        ┌───────────┼───────────┐
        │           │           │
        ▼           ▼           ▼
   ┌─────────┐ ┌─────────┐ ┌──────────┐
   │ engine  │ │  api    │ │dashboard │
   │ CI      │ │  CI     │ │  CI      │
   │         │ │         │ │          │
   │ ruff    │ │ ruff    │ │ ESLint   │
   │ mypy    │ │ mypy    │ │ tsc      │
   │ pytest  │ │ pytest  │ │ vitest   │
   │ coverage│ │ coverage│ │ coverage │
   └────┬────┘ └────┬────┘ └────┬─────┘
        │           │           │
        └───────────┼───────────┘
                    │
                    ▼ (main 브랜치만)
        ┌───────────────────────┐
        │  통합 테스트 (Integration)│
        │  Docker Compose 기동     │
        │  PostgreSQL + Engine + API│
        │  pytest tests/integration/│
        └───────────┬───────────┘
                    │
                    ▼ (tag 시)
        ┌───────────────────────┐
        │  Docker 이미지 빌드      │
        │  engine:tag, api:tag   │
        │  dashboard:tag         │
        └───────────┬───────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │  배포 (수동 승인)        │
        │  docker-compose pull    │
        │  docker-compose up -d   │
        └───────────────────────┘
```

### 3.2 GitHub Actions Workflow 상세

#### engine.yml

```yaml
name: Engine CI

on:
  push:
    paths: ['engine/**', 'shared/**', 'migrations/**']
  pull_request:
    paths: ['engine/**', 'shared/**', 'migrations/**']

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.13'

      - name: Install dependencies
        run: |
          pip install poetry
          cd shared && pip install -e .
          cd ../engine && poetry install

      - name: Lint (ruff)
        run: cd engine && ruff check .

      - name: Type check (mypy)
        run: cd engine && mypy engine/ --strict

      - name: Unit tests
        run: cd engine && pytest tests/unit/ -v --cov=engine --cov-report=xml

      - name: Coverage gate (80%+)
        run: cd engine && coverage report --fail-under=80

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: engine/coverage.xml
          flags: engine
```

#### api.yml

```yaml
name: API CI

on:
  push:
    paths: ['api/**', 'shared/**']
  pull_request:
    paths: ['api/**', 'shared/**']

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.13'

      - name: Install dependencies
        run: |
          pip install poetry
          cd shared && pip install -e .
          cd ../api && poetry install

      - name: Lint (ruff)
        run: cd api && ruff check .

      - name: Type check (mypy)
        run: cd api && mypy api/ --strict

      - name: Unit tests
        run: cd api && pytest tests/ -v --cov=api --cov-report=xml

      - name: Coverage gate (80%+)
        run: cd api && coverage report --fail-under=80

      - name: OpenAPI schema diff
        run: |
          cd api && python -c "from api.main import app; import json; print(json.dumps(app.openapi()))" > /tmp/openapi.json
          diff api/openapi-draft.yaml /tmp/openapi.json || echo "::warning::OpenAPI schema changed"
```

#### dashboard.yml

```yaml
name: Dashboard CI

on:
  push:
    paths: ['dashboard/**']
  pull_request:
    paths: ['dashboard/**']

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'pnpm'
          cache-dependency-path: 'dashboard/pnpm-lock.yaml'

      - name: Install dependencies
        run: cd dashboard && pnpm install --frozen-lockfile

      - name: Lint (ESLint)
        run: cd dashboard && pnpm lint

      - name: Type check (tsc)
        run: cd dashboard && pnpm tsc --noEmit

      - name: Unit tests (vitest)
        run: cd dashboard && pnpm test --coverage

      - name: Build check
        run: cd dashboard && pnpm build
```

#### integration.yml

```yaml
name: Integration Tests

on:
  push:
    branches: [main]

jobs:
  integration:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: timescale/timescaledb:latest-pg16
        env:
          POSTGRES_DB: traderj_test
          POSTGRES_USER: traderj
          POSTGRES_PASSWORD: test
        ports: ['5432:5432']
        options: >-
          --health-cmd="pg_isready -U traderj"
          --health-interval=5s
          --health-timeout=3s
          --health-retries=10

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.13'

      - name: Install all packages
        run: |
          pip install poetry
          cd shared && pip install -e .
          cd ../engine && poetry install
          cd ../api && poetry install

      - name: Run migrations
        env:
          DB_HOST: localhost
          DB_PORT: 5432
          DB_NAME: traderj_test
          DB_USER: traderj
          DB_PASSWORD: test
        run: cd migrations && alembic upgrade head

      - name: Integration tests
        env:
          DB_HOST: localhost
          DB_PORT: 5432
          DB_NAME: traderj_test
          DB_USER: traderj
          DB_PASSWORD: test
        run: pytest tests/integration/ -v --timeout=60
```

### 3.3 Docker 이미지 빌드 + 레지스트리

| 항목 | 설정 |
|------|------|
| 레지스트리 | GitHub Container Registry (ghcr.io) |
| 태깅 | `ghcr.io/whoana/traderj-engine:v0.1.0`, `ghcr.io/whoana/traderj-api:v0.1.0` |
| 빌드 트리거 | Git tag (`v*`) 푸시 시 |
| 멀티 스테이지 | builder → runtime (slim/alpine) |
| 캐시 | GitHub Actions cache (BuildKit layer cache) |

### 3.4 스테이징 / 프로덕션 분리

| 환경 | 구성 | 배포 방식 |
|------|------|----------|
| **로컬 개발** | docker-compose.dev.yml (SQLite 옵션, hot-reload, 볼륨 마운트) | `make dev` |
| **CI 테스트** | GitHub Actions services (PostgreSQL), 임시 환경 | 자동 |
| **스테이징** | docker-compose.yml + `.env.staging` (Paper 모드 강제) | 수동 배포 (tag 기반) |
| **프로덕션** | docker-compose.yml + `.env.production` (Live 모드 가능) | 수동 배포 + 승인 |

---

## 4. 배포 런북

### 4.1 최초 배포 절차

```bash
# 1. 서버 준비 (Docker, docker-compose 설치 확인)
docker --version        # 24.0+
docker compose version  # 2.20+

# 2. 레포지토리 클론
git clone https://github.com/whoana/traderj.git
cd traderj

# 3. 환경변수 설정
cp .env.example .env
# .env 편집: DB_PASSWORD, UPBIT_ACCESS_KEY, UPBIT_SECRET_KEY, TRADERJ_API_KEY, TELEGRAM_*

# 4. Docker 이미지 빌드
docker compose build

# 5. DB 마이그레이션
docker compose up -d postgres
docker compose run --rm engine alembic upgrade head

# 6. 전체 서비스 기동
docker compose up -d

# 7. 헬스체크 확인
curl http://localhost:8000/api/v1/health
# {"status": "ok", "uptime": ..., "db": "connected", "engine": "running"}

# 8. 대시보드 접속
open http://localhost:3000
```

### 4.2 업데이트 배포 절차

```bash
# 1. 변경 사항 확인
git pull origin main
git log --oneline -5

# 2. DB 마이그레이션 (있는 경우)
docker compose run --rm engine alembic upgrade head

# 3. 이미지 재빌드
docker compose build engine api dashboard

# 4. 롤링 재시작 (순서 중요)
#    a) Engine은 포지션 보호 후 재시작
docker compose stop engine
# 포지션이 열려있으면 먼저 안전하게 정리
docker compose up -d engine
docker compose exec engine python -c "import asyncio; asyncio.run(__import__('engine.health').health.check())"

#    b) API 재시작
docker compose stop api
docker compose up -d api
curl http://localhost:8000/api/v1/health

#    c) Dashboard 재시작
docker compose stop dashboard
docker compose up -d dashboard

# 5. 로그 확인
docker compose logs --tail=50 engine
docker compose logs --tail=50 api
```

### 4.3 롤백 전략

```bash
# 1. 문제 발견 시 즉시 Engine 중지 (포지션 보호 우선)
docker compose stop engine

# 2. 이전 이미지로 롤백
git checkout <previous-tag>
docker compose build engine api dashboard
docker compose up -d

# 3. DB 마이그레이션 롤백 (필요 시)
docker compose run --rm engine alembic downgrade -1

# 4. 헬스체크 확인
curl http://localhost:8000/api/v1/health

# 5. Telegram 알림으로 팀에 롤백 사실 통보
```

### 4.4 헬스체크 체크리스트

| 서비스 | 체크 방법 | 정상 응답 | 장애 대응 |
|--------|----------|----------|----------|
| PostgreSQL | `pg_isready -U traderj` | exit 0 | docker compose restart postgres |
| Engine | Python health module (30초 간격) | DB 연결 + EventBus 활성 | docker compose restart engine |
| API | `GET /api/v1/health` (10초 간격) | `{"status":"ok"}` | docker compose restart api |
| Dashboard | HTTP 200 on `localhost:3000` | 페이지 로드 | docker compose restart dashboard |
| Prometheus | `GET localhost:9090/-/healthy` | 200 OK | docker compose restart prometheus |
| Grafana | `GET localhost:3001/api/health` | 200 OK | docker compose restart grafana |

### 4.5 긴급 대응 매뉴얼

| 상황 | 즉시 조치 | 후속 조치 |
|------|----------|----------|
| **Engine 무응답** | `docker compose restart engine` | 로그 분석, 포지션 상태 DB 확인 |
| **DB 연결 실패** | `docker compose restart postgres` | 커넥션 풀 상태 확인, `shared_buffers` 조정 |
| **미체결 주문 잔존** | `POST /api/v1/bots/emergency-stop` | 거래소에서 직접 미체결 주문 취소 확인 |
| **열린 포지션 + Engine 장애** | `POST /api/v1/positions/close-all` 또는 거래소 직접 청산 | DB 포지션 상태 동기화 |
| **디스크 부족** | `docker system prune -f` | candles 보존 정책 확인, Parquet 파일 정리 |
| **OOM (메모리 부족)** | 서비스별 `mem_limit` 설정 확인, 불필요 서비스 중지 | `shared_buffers`, 커넥션 풀 축소 |

---

## 5. 인프라 마일스톤

### Phase별 인프라 준비 사항

| Phase | 인프라 항목 | 상세 | 완료 기준 |
|-------|-----------|------|----------|
| **Phase 0** | 모노레포 구조 | TDR-007 디렉터리 생성, pyproject.toml×3, package.json×1 | `make install` 성공 |
| | PostgreSQL + TimescaleDB | Docker 이미지 (`timescale/timescaledb:latest-pg16`), 볼륨 마운트 | `docker compose up postgres` + `pg_isready` |
| | Alembic 마이그레이션 | 초기 스키마 3개 마이그레이션 파일, `alembic upgrade head` | 10개 테이블 + 인덱스 생성 확인 |
| | CI 기본 | GitHub Actions 3개 workflow (engine/api/dashboard), ruff + mypy + pytest/vitest | PR 시 CI green |
| | OpenAPI YAML 초안 | REST API 20개 엔드포인트 스키마 | 대시보드 팀 mock API 구축 가능 |
| **Phase 1** | asyncpg 연결 풀 | `create_pool(min=2, max=10)`, graceful shutdown | DataStore 단위 테스트 통과 |
| | EventBus + Prometheus | asyncio EventBus, 이벤트 메트릭 카운터/히스토그램 | EventBus 단위 테스트 통과 |
| | ccxt Upbit 연결 | Rate Limiter, WebSocket Stream | Mock 기반 테스트 통과 |
| | structlog JSON 로깅 | 컨텍스트 바인딩, JSON stdout, Docker 호환 | 로그 포맷 검증 |
| | APScheduler | cron job 등록/해제 인터페이스 | 스케줄러 작동 확인 |
| **Phase 2** | Paper Trading 잔고 | paper_balances 테이블, 원자적 잔고 변경 | Paper 주문 실행 성공 |
| | risk_state 영속화 | Write-through, daily reset, 쿨다운 | RiskManager 테스트 통과 |
| | StateMachine DB 영속화 | bot_state 테이블, 재시작 시 복원 | 상태 전이 테스트 통과 |
| | Telegram Bot | python-telegram-bot, 알림 전송 | 테스트 메시지 발송 확인 |
| **Phase 3** | FastAPI 서버 | REST 20개 + WS 1개 엔드포인트, 미들웨어(auth/cors/metrics) | API 통합 테스트 통과 |
| | Unix Domain Socket IPC | Engine ↔ API 양방향 통신, Fallback 큐 | IPC 통합 테스트 통과 |
| | Docker 전체 빌드 | 6개 서비스 docker-compose up, 헬스체크 통과 | 전체 시스템 기동 |
| | Prometheus + Grafana | 스크래핑 설정, 커스텀 메트릭 13개, 기본 대시보드 | 메트릭 그래프 확인 |
| | OpenAPI → TypeScript 타입 | openapi-typescript 자동 생성, CI 불일치 감지 | 타입 동기화 확인 |
| **Phase 4** | DB 쿼리 최적화 | EXPLAIN ANALYZE, 인덱스 추가 | 응답 시간 목표 달성 |
| | 보안 스캔 | pip-audit, pnpm audit, SQL 인젝션 감사 | 취약점 0건 |
| | Grafana 알림 | 에러율, 응답 지연, DB, 엔진 헬스 알림 규칙 4개 | 알림 발송 확인 |
| | 배포 자동화 | deploy workflow, 수동 승인 게이트 | 태그 배포 성공 |

### DuckDB 도입 (P1-백테스트 연계)

| 작업 | 상세 | 시점 |
|------|------|------|
| DuckDBAnalyticsStore 구현 | AnalyticsStore Protocol 구현, Parquet 로드 | P1 백테스트 착수 시 |
| export_parquet.py | PostgreSQL `COPY TO` → Parquet 파일 생성 | 백테스트 파이프라인 |
| Parquet 보존 정책 | 최근 5개 익스포트만 유지, 오래된 파일 자동 삭제 | 디스크 관리 |

---

## 6. 교차 의존성

### 6.1 API 계약 (bot-developer ↔ dashboard-designer)

#### REST API 계약

| 계약 항목 | 내용 | 합의 상태 |
|-----------|------|----------|
| 엔드포인트 | Round 4 §8.1: P0/P1 20개 REST (읽기 16 + 제어 4) + P2 4개 예정 (총 24개) | 확정 |
| 인증 | X-API-Key 헤더, `/health` 제외 | 확정 |
| 응답 형식 | `PaginatedResponse<T>` — `{items, total, page, size, pages}` | 확정 |
| 에러 형식 | `{detail: string, status_code: int}` | 확정 |
| Query Params | `?strategy_id=&status=&page=&size=&days=&sort=&order=` | 확정 |
| 응답 시간 SLA | 봇 상태 <200ms, 긴급 제어 <500ms, 캔들 차트 <1000ms | 확정 (Round 4 §11.3) |

#### WebSocket 계약

| 계약 항목 | 내용 | 합의 상태 |
|-----------|------|----------|
| 엔드포인트 | `/ws/v1/stream?api_key=...` | 확정 |
| 채널 | ticker, bot_status, orders, positions, signals, alerts — 6개 | 확정 |
| 메시지 프로토콜 | Round 4 §9.3: subscribe/unsubscribe/data/pong/error | 확정 |
| 하트비트 | 30초 ping/pong, 60초 무응답 시 끊김 | 확정 |
| 재연결 | 지수 백오프(1s~30s) + jitter, 무한 재시도 | 확정 |

#### OpenAPI 타입 동기화 흐름

```
FastAPI (api/main.py)
    │
    ▼ /openapi.json 자동 생성
    │
scripts/generate_api_types.sh
    │ openapi-typescript CLI
    ▼
dashboard/src/types/api.ts (자동 생성)
    │
    ▼ CI에서 스키마 변경 감지
    │ → PR 코멘트로 불일치 알림
```

### 6.2 이벤트 타입 계약 (bot-developer ↔ quant-expert)

| 이벤트 | 발행자 | 소비자 | 데이터 형식 | 합의 상태 |
|--------|--------|--------|------------|----------|
| MarketTickEvent | engine(exchange) | RiskManager, PositionManager, API WS Bridge | price, bid, ask, volume_24h | 확정 |
| OHLCVUpdateEvent | engine(scheduler) | StrategyEngine(quant) | symbol, timeframe, candles[] | 확정 |
| SignalEvent | StrategyEngine(quant) | ExecutionEngine, API WS Bridge | direction, score, components, details | 확정 |
| OrderRequestEvent | ExecutionEngine | OrderManager | side, amount, order_type, idempotency_key | 확정 |
| OrderFilledEvent | OrderManager | PositionManager, RiskManager, Notifier, API WS Bridge | actual_price, slippage_pct | 확정 |
| PositionOpenedEvent | PositionManager | RiskManager, API WS Bridge | entry_price, amount, stop_loss | 확정 |
| PositionClosedEvent | PositionManager | RiskManager, API WS Bridge | realized_pnl, exit_reason | 확정 |
| StopLossTriggeredEvent | RiskManager | ExecutionEngine | trigger_price, stop_loss_price | 확정 |
| RiskAlertEvent | RiskManager | Notifier, API WS Bridge | alert_type, message, severity | 확정 |
| BotStateChangeEvent | StateMachine | Logger, API WS Bridge | old_state, new_state, reason | 확정 |
| RegimeChangeEvent | RegimeClassifier(quant) | Logger, API WS Bridge | old/new regime, overrides | 확정 |
| RiskStateEvent | RiskEngine(quant) | Dashboard WS, TelegramNotifier | consecutive_losses, daily_pnl, cooldown, position_pct, atr_pct, volatility_status | 확정 |
| MarketDataEvent | DataCollector(engine) | StrategyEngine(quant) | symbol, ohlcv_by_tf dict | 확정 |

### 6.3 DB 스키마 계약

| 테이블 | 정의 도메인 | 읽기 도메인 | 쓰기 도메인 | 마이그레이션 담당 |
|--------|-----------|-----------|-----------|---------------|
| candles | bot-developer | quant, dashboard(API 경유) | engine(collector) | bot-developer |
| signals | quant-expert | dashboard(API 경유) | engine(strategy) | bot-developer |
| orders | bot-developer | dashboard(API 경유) | engine(execution) | bot-developer |
| positions | bot-developer | dashboard(API 경유) | engine(execution) | bot-developer |
| risk_state | quant-expert | dashboard(API 경유) | engine(risk) | bot-developer |
| bot_state | bot-developer | dashboard(API 경유) | engine(state machine) | bot-developer |
| paper_balances | bot-developer | dashboard(API 경유) | engine(execution) | bot-developer |
| daily_pnl | bot-developer | dashboard(API 경유) | engine(scheduler) | bot-developer |
| macro_snapshots | bot-developer | quant(strategy) | engine(macro collector) | bot-developer |
| backtest_results | quant-expert | dashboard(API 경유) | engine(backtest) | bot-developer |
| bot_commands | bot-developer | engine(poller) | api(IPC fallback) | bot-developer |

### 6.4 Signal.details JSON 스키마 (전략 ↔ 대시보드)

Round 4 전략 설계서 §8.2에서 확정된 JSON 구조:

```json
{
  "strategy_id": "STR-005",
  "scoring_mode": "trend_follow | hybrid",
  "entry_mode": "weighted | majority",
  "regime": "trending_high_vol | trending_low_vol | ranging_high_vol | ranging_low_vol | null",
  "technical": 0.185,
  "macro_raw": -0.084,
  "score_weights": [0.50, 0.30, 0.20],
  "effective_thresholds": { "buy": 0.13, "sell": -0.17 },
  "daily_gate_status": "pass | fail | disabled",
  "tf_scores": {
    "<tf>": { "s1": 0.35, "s2": 0.22, "s3": 0.15, "combined": 0.275, "weights": [0.50, 0.30, 0.20] }
  },
  "risk_state": {
    "position_pct": 0.15, "stop_loss_price": 62500000,
    "atr_pct": 0.048, "volatility_status": "normal | warning | blocked"
  },
  "plugin_scores": null
}
```

> 대시보드는 이 JSON 구조를 기반으로 스코어 분해 바 차트, 리스크 상태 패널, 레짐 타임라인을 렌더링한다.

### 6.5 팀 협업 타임라인

```
Phase 0                Phase 1                Phase 2                Phase 3                Phase 4
──────                 ──────                 ──────                 ──────                 ──────
bot-dev:               bot-dev:               bot-dev:               bot-dev:               bot-dev:
  모노레포 구조           DataStore(PG)          OrderManager           REST API 20개          성능 최적화
  DB 스키마               EventBus               PositionManager        WebSocket              E2E 테스트
  Docker 기본             ExchangeClient         RiskManager            IPC 서버/클라이언트     배포 자동화
  OpenAPI 초안 ──────→   Rate Limiter           StateMachine           Docker 전체
                                                                       Prometheus/Grafana

quant:                 quant:                 quant:                 quant:                 quant:
  shared/models 검토     SignalGenerator ←──── 전략 엔진 통합          백테스트 결과 API       Walk-forward
  shared/events 검토     (독립 개발 착수)       EventBus 연동           (API 경유 조회)        ML 플러그인(P2)
                         Z-score 정규화                                AnalyticsStore
                         Regime Classifier

dashboard:             dashboard:             dashboard:             dashboard:             dashboard:
  Next.js 초기화          mock API 기반 ←────── BotCard, KPIHeader     mock→실제 API 전환     E2E 테스트
  TailwindCSS 설정       UI 개발 착수            DataTabs               WebSocket 연동         성능 최적화
  shadcn/ui 설정         (msw mock)             LWChartWrapper         Zustand 스토어 연동    반응형 검증
                                                                       Analytics 페이지
```

---

## 7. 리스크 & 완화 전략

### 7.1 기술 부채 리스크

| ID | 리스크 | 영향도 | 발생 확률 | 완화 전략 |
|----|--------|--------|----------|----------|
| T1 | asyncpg 직접 SQL → 타입 매핑 보일러플레이트 | 중 | 높 | `row_to_model()` 제네릭 헬퍼 1회 구현. 코드 리뷰에서 반복 패턴 감지 |
| T2 | shared 패키지 순환 의존 | 높 | 중 | models/events/protocols만 포함, 로직 코드 금지. CI에서 import 순환 탐지 |
| T3 | IPC JSON-lines 프로토콜 한계 | 중 | 낮 | 메시지 크기 모니터링, 향후 gRPC 전환 경로 확보 |
| T4 | Alembic autogenerate 비활성 | 낮 | 중 | 수동 마이그레이션 규칙 문서화, PR 리뷰 시 스키마 변경 체크 |
| T5 | Python 3.13 + asyncio 태스크 관리 복잡도 | 중 | 중 | TaskGroup 패턴 표준화, 미완료 태스크 리크 감시 메트릭 |

### 7.2 성능 병목 리스크

| ID | 리스크 | 영향도 | 발생 확률 | 완화 전략 |
|----|--------|--------|----------|----------|
| P1 | candles 대량 쿼리(수만 rows) 지연 | 중 | 중 | TimescaleDB hypertable 청크 최적화, `LIMIT` 강제, 연속 집계 활용 |
| P2 | EventBus 핸들러 블로킹 | 높 | 낮 | CPU-bound 작업은 `ThreadPoolExecutor` 오프로드. 핸들러 지연 히스토그램 모니터링 |
| P3 | 지표 계산(pandas-ta) 지연 | 중 | 중 | 350 bars 제한, 결과 캐싱 (동일 TF+시간 재계산 방지) |
| P4 | WebSocket 메시지 백프레셔 | 중 | 낮 | 메시지 큐 크기 제한(1000), overflow 시 최신만 유지 |
| P5 | Docker 이미지 빌드 시간 | 낮 | 중 | 멀티 스테이지 빌드, Poetry lock 레이어 캐시, BuildKit 활성화 |

### 7.3 보안 리스크

| ID | 리스크 | 영향도 | 발생 확률 | 완화 전략 |
|----|--------|--------|----------|----------|
| S1 | SQL 인젝션 (asyncpg 직접 SQL) | **치명** | 낮 | asyncpg `$1,$2` 파라미터 바인딩 필수. 문자열 포맷 금지 코드 리뷰 규칙. CI grep 검사 |
| S2 | API Key 노출 | 높 | 낮 | `.env` 전용, 로그 마스킹, Git에 `.env` 포함 금지 (.gitignore) |
| S3 | 거래소 API 키 유출 | **치명** | 낮 | 환경변수 전용, Docker Secret 또는 볼륨 마운트, 로그에서 마스킹 |
| S4 | CORS 과도한 허용 | 중 | 중 | 프로덕션에서 `allow_origins`를 실제 대시보드 도메인만으로 제한 |
| S5 | 의존성 취약점 | 중 | 중 | `pip-audit` + `pnpm audit` CI 통합. Dependabot 활성화 |

### 7.4 운영 리스크

| ID | 리스크 | 영향도 | 발생 확률 | 완화 전략 |
|----|--------|--------|----------|----------|
| O1 | Engine 재시작 시 포지션 불일치 | 높 | 중 | Persistence-First: risk_state, position, bot_state DB 영속화. 재시작 시 DB에서 복원 |
| O2 | 거래소 API 다운타임 | 높 | 중 | CircuitBreaker(3연속 실패→차단), 지수 백오프 재시도, Telegram 알림 |
| O3 | TimescaleDB 업그레이드 호환성 | 중 | 낮 | Docker 이미지 버전 고정(`timescale/timescaledb:2.x.x-pg16`), 릴리스 노트 확인 후 업그레이드 |
| O4 | DuckDB-PostgreSQL 데이터 불일치 | 중 | 중 | 백테스트 실행 직전 Parquet 익스포트 강제, 타임스탬프 검증 |
| O5 | 디스크 용량 부족 | 중 | 중 | candles 보존 정책 2년 자동, Parquet 최근 5개만 유지, Docker prune cron |
| O6 | 단일 장애점 (Single Point of Failure) | 높 | 중 | `restart: unless-stopped` 전 서비스, 헬스체크 자동 재시작, Telegram 즉시 알림 |

### 7.5 리스크 모니터링 매트릭스

```
Prometheus Alert Rules:

# 엔진 헬스
- alert: EngineDown
  expr: up{job="engine"} == 0
  for: 1m
  severity: critical

# API 응답 지연
- alert: APIHighLatency
  expr: histogram_quantile(0.95, traderj_http_request_duration_seconds_bucket) > 2
  for: 5m
  severity: warning

# DB 연결 실패
- alert: DBConnectionFailed
  expr: traderj_db_pool_available == 0
  for: 30s
  severity: critical

# 이벤트 버스 핸들러 에러
- alert: EventBusHandlerErrors
  expr: rate(traderj_event_bus_handler_errors_total[5m]) > 0.1
  for: 5m
  severity: warning

# 주문 실패율
- alert: OrderFailureRate
  expr: rate(traderj_order_failures_total[1h]) / rate(traderj_order_total[1h]) > 0.2
  for: 10m
  severity: critical

# CircuitBreaker OPEN
- alert: CircuitBreakerOpen
  expr: traderj_circuit_breaker_state == 2
  for: 1m
  severity: critical
```

---

> **문서 상태**: Draft — 팀 리더 검토 대기
> **기반 문서**: Round 3 TDR (Rev.1), Round 4 아키텍처/전략/대시보드 설계서
> **다음 단계**: 팀 리더 승인 후 Phase 0 작업 착수
