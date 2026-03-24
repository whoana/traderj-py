# bit-trader 아키텍처 감사 보고서 (Round 1)

**작성일**: 2026-03-02
**대상**: bit-trader v0.1.0 — BTC/KRW 자동매매 봇 (Upbit)
**범위**: 전체 코드베이스 (`src/bit_trader/`, `migrations/`, `tests/`)

---

## 1. 전체 아키텍처 평가

### 1.1 구조 개요

```
src/bit_trader/
  app.py              ← DI 컨테이너 + 라이프사이클 오케스트레이터
  config/             ← 설정 (pydantic-settings) + 전략 프리셋 (frozen dataclass)
  exchange/           ← ccxt async Upbit 래퍼 + Rate Limiter + WebSocket
  data/               ← SQLite 저장소 + OHLCV 수집기 + 매크로 수집기
  strategy/           ← 지표 계산 + 필터 스코어링 + MTF 집계 + 시그널 생성
  execution/          ← 주문 관리 + 포지션 관리 + 리스크 엔진
  engine/             ← 메인 루프 + 스케줄러 + 상태 머신
  notify/             ← 텔레그램 알림
  utils/              ← 로깅 + 시간 유틸
```

- **언어/런타임**: Python 3.13, async/await 기반
- **패키지 관리**: Poetry 2.3.2
- **코드량**: 52개 파일, 59개 테스트

### 1.2 DI(의존성 주입) 패턴 분석

`app.py`의 `App.start()` 메서드가 모든 컴포넌트를 순차적으로 생성하고 연결하는 **수동 DI** 패턴을 사용한다.

**장점**:
- 명시적이고 추적 가능한 의존성 그래프
- 테스트에서 개별 컴포넌트 모킹 용이
- 별도 DI 프레임워크 없이 단순함 유지

**한계 (Medium)**:
- 모든 의존성이 `App.start()`에 하드코딩되어 있어 컴포넌트 추가/교체 시 반드시 이 메서드 수정 필요
- 인터페이스/프로토콜 정의 없음 — 구현 클래스에 직접 의존
- 멀티 봇 실행 시 동일 프로세스 내 격리 불가 (현재 별도 프로세스로 우회)

### 1.3 이벤트 흐름

현재 이벤트 흐름은 **스케줄러 기반 폴링** 방식이다:

```
[APScheduler Cron/Interval] → TradingLoop 메서드 호출
   → OHLCV 수집 / 시그널 생성 / 손절 체크 / 헬스 체크
   → StateMachine 전환
   → OrderManager / PositionManager 실행
   → Store (SQLite) 영속화
   → TelegramNotifier 알림
```

**한계 (High)**:
- **이벤트 버스 부재**: 컴포넌트 간 결합도가 높다. TradingLoop이 모든 컴포넌트를 직접 참조하고 호출한다 (13개 생성자 파라미터)
- **WebSocket 미활용**: `UpbitWebSocket`이 구현되어 있지만 실제 TradingLoop에 통합되지 않음. 실시간 데이터가 시그널 생성에 반영되지 않는다
- **비동기 체이닝 없음**: 스케줄러가 메서드를 직접 호출하므로 작업 간 순서 보장이 OHLCV 수집(minute=1) → 시그널 생성(minute=5) 같은 cron 시간 오프셋에 의존

---

## 2. 데이터 계층

### 2.1 SQLite + aiosqlite

**현재 구성**:
- `PRAGMA journal_mode=WAL` — 동시 읽기 허용
- `PRAGMA busy_timeout=30000` — 30초 잠금 대기
- `PRAGMA foreign_keys=ON`
- 마이그레이션: 파일 기반 순차 적용 (001_initial, 002_paper_balances, 003_multi_strategy)

**테이블 구조** (8개 테이블):
| 테이블 | 역할 | 인덱스 |
|--------|------|--------|
| candles | OHLCV 시계열 | symbol+timeframe+timestamp DESC |
| macro_snapshots | 매크로 지표 | timestamp DESC |
| signals | 생성된 시그널 | symbol+timestamp DESC |
| orders | 주문 이력 | status+created_at DESC |
| positions | 포지션 이력 | status+symbol |
| daily_pnl | 일일 손익 | date UNIQUE |
| bot_state | 봇 상태 | strategy_id UNIQUE |
| paper_balances | 페이퍼 잔고 | strategy_id UNIQUE |

### 2.2 문제점 및 기술 부채

**[Critical] 동시성 한계**:
- SQLite는 단일 writer 잠금 모델이다. 현재 멀티 봇(STR-003, STR-004, STR-005)이 **별도 프로세스 + 별도 DB 파일**로 실행되지만, 같은 DB를 공유하면 쓰기 충돌 발생
- `Store` 클래스의 `transaction()` 메서드가 `BEGIN IMMEDIATE`를 사용하지만, 실제 코드에서 `transaction()` 컨텍스트 매니저를 사용하는 곳이 없다. 대부분의 쓰기 작업이 개별 `execute` + `commit`으로 이루어져 있어 원자성이 보장되지 않는 시나리오 존재
- 예: `_paper_order()`에서 잔고 부족 시 retry 로직이 `atomic_buy_balance` → `get_paper_balance` → `atomic_buy_balance` 순서로 경합 조건 가능

**[High] 스키마 설계 한계**:
- `candles` 테이블에 시간 기반 파티셔닝 없음 — 데이터가 누적될수록 쿼리 성능 저하
- `timestamp`를 TEXT(ISO 8601)로 저장 — 범위 쿼리 시 문자열 비교, REAL(Unix timestamp) 대비 비효율적
- `signals` 테이블에 `strategy_id` 칼럼 없음 — 멀티 전략 환경에서 어떤 전략이 생성한 시그널인지 DB 레벨에서 구분 불가 (details JSON 내부에만 존재)
- `daily_pnl` 테이블에 `strategy_id` 칼럼 없음 — 전략별 일일 손익 분리 불가

**[Medium] 데이터 수명 관리 미비**:
- 캔들 데이터 자동 정리 정책 없음 (TTL/파티션 등)
- 시그널 테이블이 무한히 증가 (HOLD 포함 매 시간 기록)
- 마이그레이션에서 `executescript()`가 트랜잭션 외부에서 실행됨 — 마이그레이션 실패 시 불완전한 상태 가능

**[Low] ORM 미사용**:
- 수동 SQL + Row→dataclass 변환 코드가 반복적으로 존재 (boilerplate)
- 쿼리 빌더 없이 문자열 SQL 직접 작성 — SQL 인젝션 위험은 파라미터 바인딩으로 방지하지만 유지보수 비용

---

## 3. 거래소 통합

### 3.1 ccxt 래퍼 (`UpbitClient`)

**장점**:
- ccxt의 `async_support` 활용으로 비동기 API 호출
- 내부 rate limiter 직접 구현하여 ccxt의 기본 rate limit 비활성화 (`enableRateLimit: False`)
- 깔끔한 도메인 모델 변환 (raw dict → `Ticker`, `Order`, `Balance`)

**[High] 에러 처리 미흡**:
- `create_order()`에서 ccxt 예외(NetworkError, ExchangeError, InsufficientFunds 등)에 대한 구체적 처리 없음 — 모든 예외가 caller에게 전파
- 주문 생성 후 상태 확인 로직 없음 — 네트워크 오류 시 주문이 거래소에서 체결되었는지 알 수 없는 **유령 주문(ghost order)** 위험
- `fetch_open_orders()`와 `fetch_order()`의 반환 타입이 `dict[str, object]`로 타입 안전성 부족

**[Medium] 단일 거래소 종속**:
- `UpbitClient`가 Upbit 특화 구현으로, 다른 거래소 추가 시 전면 리팩토링 필요
- 거래소 추상 인터페이스(Protocol) 미정의

### 3.2 Rate Limiter

```python
TokenBucket(rate=10.0, capacity=10.0)  # market: 10 req/sec
TokenBucket(rate=8.0, capacity=8.0)    # order: 8 req/sec
TokenBucket(rate=30.0, capacity=30.0)  # exchange: 30 req/sec
```

**장점**:
- Token Bucket 알고리즘의 정확한 구현
- 그룹별 분리된 버킷 (market/order/exchange)
- async Lock으로 동시 호출 안전

**[Low] 개선 가능 사항**:
- 버킷 소진 시 busy-wait 루프(`while True`) — `asyncio.Event` 기반 대기가 더 효율적
- 멀티 프로세스 환경에서는 프로세스 간 rate limit 공유 불가

### 3.3 WebSocket (`UpbitWebSocket`)

**장점**:
- 콜백 기반 구독 패턴 (`on_ticker`, `on_trade`, `on_orderbook`)
- 자동 재연결 (5초 딜레이)
- 깔끔한 생명주기 관리 (`start`/`stop`)

**[High] 미활용 — Dead Code**:
- WebSocket이 구현되어 있으나 `app.py`에서 초기화되지 않고, `TradingLoop`에서 사용되지 않음
- 실시간 가격 데이터 대신 30초 간격 `fetch_ticker()` 폴링으로 손절 체크 — 급등락 시 30초 지연
- WebSocket 통합 시 손절 반응 시간을 밀리초 단위로 줄일 수 있음

---

## 4. 실행 엔진

### 4.1 주문 관리 (`OrderManager`)

**Paper Trading 구현 (양호)**:
- `atomic_buy_balance()` / `atomic_sell_balance()`으로 SQLite 레벨 원자적 잔고 업데이트
- 잔고 부족 시 가용 잔고 전량 사용하는 fallback 로직

**[High] Live Trading 취약점**:
- **시장가 주문만 지원**: `OrderType.MARKET` 하드코딩 — 지정가, TWAP, VWAP 등 고급 주문 유형 미지원
- **슬리피지 미고려**: `current_price`를 기준으로 주문하지만 실제 체결가는 다를 수 있음. 체결가와 예상가의 차이를 기록하지 않음
- **주문 실패 복구 없음**: 주문 API 호출 실패 시 단순 예외 전파. 재시도나 알림 없음
- **주문 금액 계산**: `amount_btc = amount_krw / current_price`에서 Upbit의 최소 주문 단위(sat 단위) 미고려

**[Medium] 주문 조정(Reconciliation)**:
- 5분 간격으로 미체결 주문 상태 확인 — 양호
- 그러나 reconcile 중 `ccxt.ExchangeError` 등 예외가 발생하면 해당 주문을 건너뛰고 로그만 기록

### 4.2 포지션 관리 (`PositionManager`)

**[High] 단일 포지션 제한**:
- `get_open_position()`이 `LIMIT 1`로 심볼당 하나의 포지션만 반환
- 분할 매수(DCA), 피라미딩 등 고급 포지션 전략 불가

**[Medium] PnL 계산 정확도**:
- `realized_pnl = (exit_price - entry_price) * amount - fee`에서 진입 시 수수료가 반영되지 않음
- `update_current_price()`가 미실현 PnL을 계산하지만 DB에 저장하지 않음 (반환만 함)

### 4.3 리스크 엔진 (`RiskManager`)

**장점**:
- 4중 리스크 체크: 쿨다운 → 일일 손실 한도 → 최대 포지션 비율 → 손절
- 3연속 손실 시 24시간 쿨다운 메커니즘

**[Critical] 메모리 전용 상태**:
- `_consecutive_losses`, `_daily_pnl`, `_cooldown_until`이 **인스턴스 변수**로만 관리됨
- 봇 재시작 시 모든 리스크 상태가 초기화됨 — 재시작 직후 쿨다운이 무효화되어 연속 손실 상태에서도 거래 가능
- 일일 손실 리셋이 날짜 문자열 비교로만 이루어져 시간대(UTC vs KST) 불일치 가능성

**[Medium] 리스크 파라미터 불변성**:
- `RiskParams`가 `frozen=True` dataclass이므로 런타임 조정 불가
- 시장 변동성에 따른 동적 포지션 사이징 미지원

---

## 5. 스케줄러

### 5.1 APScheduler 구성

현재 등록 작업 (8~9개):

| 작업 | 트리거 | 주기 |
|------|--------|------|
| ohlcv_15m | Cron minute=1,16,31,46 | 15분 (선택적) |
| ohlcv_1h | Cron minute=1 | 1시간 |
| ohlcv_4h | Cron hour=0,4,8..20, minute=2 | 4시간 |
| ohlcv_1d | Cron hour=0, minute=3 | 1일 |
| signal | Cron minute=5 또는 5,20,35,50 | 1시간 또는 15분 |
| macro | Interval 6h | 6시간 |
| stop_loss | Interval 30s | 30초 |
| reconcile | Interval 5m | 5분 |
| health | Interval 1m | 1분 |

**장점**:
- OHLCV 수집과 시그널 생성 간 시간 오프셋(4분)으로 데이터 준비 후 분석 실행
- 15분 전략 여부에 따른 조건부 등록

**[High] 작업 실패 처리**:
- APScheduler의 기본 설정 사용 — 작업 실패 시 재시도 없음, misfire 정책 미설정
- `misfire_grace_time` 미설정 — Mac 잠자기 등으로 인한 놓친 작업 처리 불명확
- `coalesce` 미설정 — 스케줄러 재시작 시 밀린 작업들이 한꺼번에 실행될 수 있음

**[Medium] 작업 의존성 미관리**:
- OHLCV 수집 실패 시에도 시그널 생성이 실행됨 (오래된 데이터로 시그널 생성)
- 작업 간 데이터 의존성을 시간 오프셋에만 의존 — OHLCV 수집이 4분 이상 걸리면 불완전한 데이터로 시그널 생성

**[Low] 단일 스케줄러 인스턴스**:
- 다운 시 모든 작업 중단, 분산 스케줄링 미지원

---

## 6. 상태 머신

### 6.1 9개 상태 + 전환 규칙

```
STARTING → IDLE ↔ SCANNING → VALIDATING → EXECUTING → LOGGING → IDLE
                              ↓                         ↓
                         MONITORING → LOGGING       PAUSED
                                                      ↓
ALL STATES → SHUTTING_DOWN (terminal)               IDLE
```

**장점**:
- 명시적 전환 규칙 (`_TRANSITIONS` dict)으로 잘못된 상태 전환 방지
- `force_state()` 복구 메커니즘으로 비정상 종료 후 안전한 재시작
- 영속화 최적화 — `IDLE`, `PAUSED`, `SHUTTING_DOWN`만 DB에 저장 (불필요한 I/O 감소)

**[Medium] 분산 환경 부적합**:
- 인메모리 상태 + SQLite 영속화 — 단일 프로세스 전용
- 상태 전환 이력(audit trail) 미기록 — 디버깅 시 상태 흐름 추적 불가
- `MONITORING` 상태가 정의되어 있지만 실제 코드에서 전환되지 않음 (dead state)

**[Low] 전환 로직**:
- `transition()`이 `async` 함수지만 DB 쓰기가 필요 없는 전환에도 await 호출

---

## 7. 테스트 및 CI

### 7.1 테스트 현황

| 카테고리 | 파일 | 테스트 수 (추정) |
|----------|------|------------------|
| Unit — indicators | test_indicators.py | ~15 |
| Unit — filters | test_filters.py | ~8 |
| Unit — risk | test_risk.py | ~8 |
| Unit — rate_limiter | test_rate_limiter.py | ~5 |
| Unit — signal | test_signal.py | ~5 |
| Unit — concurrency | test_concurrency.py | ~3 |
| Integration — exchange | test_exchange_client.py | ~5 |
| Integration — order_flow | test_order_flow.py | ~5 |
| Integration — paper_balance | test_paper_balance.py | ~6 |
| Integration — data_pipeline | test_data_pipeline.py | ~3 |
| **합계** | **10 파일** | **~59개** |

**[High] 테스트 커버리지 부족**:
- `TradingLoop` (핵심 비즈니스 로직) — 테스트 없음
- `StateMachine` — 전환 규칙 테스트 없음
- `TradingScheduler` — 스케줄 등록/실행 테스트 없음
- `App` — 통합 기동/종료 테스트 없음
- `TelegramNotifier` — 테스트 없음
- `OHLCVCollector.backfill()` — retry 로직 테스트 없음
- E2E(end-to-end) 테스트 없음 — 시그널 생성부터 주문 실행까지의 전체 흐름 미검증

**[High] CI/CD 파이프라인 없음**:
- GitHub Actions, GitLab CI 등 자동화된 테스트/린트 파이프라인 미구성
- 수동으로 `poetry run pytest` + `poetry run ruff check` 실행
- 코드 커버리지 측정 미설정 (`pytest-cov` 미사용)
- pre-commit 훅 미설정

### 7.2 린트 및 타입 검사

- **Ruff**: `["E", "F", "W", "I", "N", "UP", "B", "A", "SIM"]` 규칙 활성화, 현재 clean
- **Mypy**: `strict = true` — 양호한 설정이나 ccxt, pandas_ta 등 주요 라이브러리의 타입 검사를 `ignore_missing_imports`로 우회

---

## 8. 운영

### 8.1 로깅

- **Loguru** 사용 — 구조화된 로깅, 파일 로테이션 지원
- 로그 레벨 `.env`로 설정 가능

**[Medium] 구조화된 로깅 미비**:
- 텍스트 기반 로그 포맷 — JSON 구조화 로깅 미사용
- 중앙 집중 로그 수집 없음 (ELK, Grafana Loki 등)
- `strategy_id`가 로그 컨텍스트에 바인딩되지 않음 — 멀티 봇 로그에서 전략별 필터링 어려움

### 8.2 모니터링

**[High] 메트릭 수집 없음**:
- Prometheus, StatsD 등 메트릭 수집 미구성
- 주문 체결 시간, API 응답 시간, 시그널 생성 지연 등 핵심 운영 지표 미추적
- 알림이 Telegram에만 의존 — 봇 자체가 다운되면 알림도 중단
- 외부 헬스 체크(watchdog) 없음

### 8.3 배포

**[High] 컨테이너화 미구성**:
- Dockerfile 없음
- `caffeinate -i` 의존 — Mac 로컬 실행 전용
- 프로세스 관리가 PID 파일 기반의 수동 방식 (`/tmp/bit_trader_pids_*.pid`)
- systemd, supervisord 등 프로세스 매니저 미사용
- 환경별 설정 분리 없음 (dev/staging/prod)

**[Medium] 비밀 관리**:
- `.env` 파일에 API 키 직접 저장 — 시크릿 매니저(Vault, AWS Secrets Manager) 미사용
- `SecretStr` 사용으로 로그 노출은 방지하나, 파일 시스템 접근 시 평문 노출

---

## 9. 종합 기술 부채 목록

### Critical (즉시 해결 필요)

| # | 항목 | 설명 | 영향 |
|---|------|------|------|
| C1 | 리스크 상태 메모리 전용 | 연속 손실/쿨다운/일일 PnL이 재시작 시 초기화 | 재시작 후 쿨다운 무효화로 연속 손실 확대 가능 |
| C2 | SQLite 동시 쓰기 한계 | 멀티 봇이 같은 DB 공유 불가 | 멀티 전략 확장의 근본적 제약 |

### High (조기 해결 권장)

| # | 항목 | 설명 | 영향 |
|---|------|------|------|
| H1 | 이벤트 버스 부재 | TradingLoop이 모든 컴포넌트에 직접 의존 | 확장 시 결합도 급증, 테스트 곤란 |
| H2 | WebSocket 미통합 | 실시간 데이터 미활용, 30초 폴링 손절 | 급등락 시 손절 지연 최대 30초 |
| H3 | Live 주문 에러 처리 미흡 | 유령 주문 위험, 슬리피지 미고려 | 실거래 시 자금 손실 위험 |
| H4 | 핵심 로직 테스트 부재 | TradingLoop, StateMachine, Scheduler 미테스트 | 리팩토링 안전망 없음 |
| H5 | CI/CD 없음 | 수동 테스트/린트 실행 | 회귀 버그 조기 발견 불가 |
| H6 | 메트릭/모니터링 없음 | 운영 지표 미추적 | 장애 인지 지연 |
| H7 | 컨테이너화 없음 | Mac 로컬 전용, PID 파일 기반 | 서버 배포 불가 |
| H8 | APScheduler misfire 미설정 | 놓친 작업 처리 불명확 | 데이터 누락 가능 |
| H9 | 시장가 주문만 지원 | 지정가/TWAP/VWAP 미지원 | 슬리피지 최소화 불가 |

### Medium (개선 권장)

| # | 항목 | 설명 |
|---|------|------|
| M1 | signals 테이블에 strategy_id 없음 | 멀티 전략 시그널 구분 불가 |
| M2 | daily_pnl에 strategy_id 없음 | 전략별 일일 손익 분리 불가 |
| M3 | timestamp TEXT 저장 | 범위 쿼리 비효율 |
| M4 | 데이터 수명 관리 없음 | 무한 데이터 증가 |
| M5 | 수동 DI + 인터페이스 미정의 | 컴포넌트 교체 비용 |
| M6 | 구조화된 로깅 미비 | 로그 분석 어려움 |
| M7 | PnL 계산에 진입 수수료 미반영 | 수익 과대 계측 |
| M8 | 단일 포지션 제한 | DCA/피라미딩 불가 |
| M9 | MONITORING 상태 미사용 | Dead state |
| M10 | 비밀 관리 .env 의존 | 시크릿 매니저 미사용 |

### Low (장기 개선)

| # | 항목 | 설명 |
|---|------|------|
| L1 | ORM 미사용 | 반복적 SQL→dataclass 변환 |
| L2 | Rate Limiter busy-wait | Event 기반 대기로 개선 가능 |
| L3 | 상태 전환 이력 미기록 | 디버깅 시 상태 흐름 추적 불가 |
| L4 | 거래소 추상 인터페이스 없음 | 멀티 거래소 확장 비용 |

---

## 10. traderj 마이그레이션 시 핵심 권장사항

### 10.1 즉시 적용 (Phase 1)

1. **RiskManager 상태 영속화**: 연속 손실, 쿨다운, 일일 PnL을 DB에 저장하고 재시작 시 복원
2. **핵심 로직 테스트 작성**: TradingLoop, StateMachine에 대한 유닛 테스트 우선 작성
3. **CI 파이프라인 구축**: GitHub Actions에 pytest + ruff + mypy 자동 실행

### 10.2 아키텍처 개선 (Phase 2)

4. **이벤트 기반 아키텍처**: asyncio Queue 또는 경량 이벤트 버스 도입으로 컴포넌트 디커플링
5. **WebSocket 통합**: 실시간 가격 데이터를 손절 체크 및 시그널 트리거에 활용
6. **데이터베이스 마이그레이션**: SQLite → PostgreSQL (TimescaleDB) 또는 DuckDB 전환 검토

### 10.3 운영 강화 (Phase 3)

7. **Docker 컨테이너화**: Dockerfile + docker-compose 작성
8. **메트릭 수집**: Prometheus 메트릭 엔드포인트 추가
9. **구조화된 로깅**: JSON 로그 + 중앙 수집
10. **주문 실행 개선**: 지정가 주문 지원, 슬리피지 기록, 주문 실패 재시도

---

## 11. 총평

bit-trader는 **연구개발 단계의 단일 자산 자동매매 봇**으로서 핵심 기능이 잘 구현되어 있다. async Python 기반의 모듈 구조, 명시적 상태 머신, 그룹별 rate limiter, 원자적 페이퍼 잔고 관리 등은 좋은 설계 판단이다.

그러나 **실거래 전환** 및 **멀티 전략/멀티 거래소 확장**에는 구조적 한계가 명확하다. 특히 리스크 상태의 메모리 전용 관리(C1)는 실거래 환경에서 즉각적인 위험 요소이며, 이벤트 버스 부재(H1)와 WebSocket 미통합(H2)은 시스템 복잡도 증가 시 유지보수 비용을 크게 높일 것이다.

traderj 프로젝트에서는 bit-trader의 비즈니스 로직(전략 스코어링, 리스크 규칙)을 **재사용**하되, 아키텍처 계층(데이터 저장소, 이벤트 흐름, 배포 인프라)을 **처음부터 재설계**하는 것을 권장한다.
