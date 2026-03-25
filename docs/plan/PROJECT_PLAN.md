# traderj 프로젝트 계획서

> **작성일**: 2026-03-03
> **작성자**: Team Leader (5-Round 에이전트 팀 종합)
> **참여자**: quant-expert, bot-developer, dashboard-designer
> **기반**: Round 1~5 산출물 16건 종합
> **상태**: Rev.1 — 최종 승인 대기

---

## 목차

1. [Executive Summary](#1-executive-summary)
2. [현황 분석](#2-현황-분석)
3. [기술 스택 결정](#3-기술-스택-결정)
4. [시스템 아키텍처](#4-시스템-아키텍처)
5. [전략 엔진 설계](#5-전략-엔진-설계)
6. [리스크 관리 프레임워크](#6-리스크-관리-프레임워크)
7. [대시보드 & UI 설계](#7-대시보드--ui-설계)
8. [구현 로드맵](#8-구현-로드맵)
9. [테스트 전략](#9-테스트-전략)
10. [배포 전략](#10-배포-전략)
11. [리스크 평가](#11-리스크-평가)

---

## 1. Executive Summary

### 1.1 프로젝트 목적

bit-trader(BTC/KRW 자동매매 봇)의 구조적 한계를 해소하고, 실전 수익성과 운영 안정성을 갖춘 **traderj**로 진화한다.

### 1.2 범위

| 영역 | bit-trader (현재) | traderj (목표) |
|------|-------------------|----------------|
| 전략 | 3단계 필터 동일 가중, MTF 2회 거래/2년 | 적응형 멀티 전략, 레짐 인식, Walk-forward 검증 |
| 아키텍처 | 스케줄러 직접 호출, SQLite, 인메모리 리스크 | 이벤트 기반, PostgreSQL+TimescaleDB, 영속적 리스크 |
| 대시보드 | Streamlit 읽기 전용, 수동 새로고침 | Next.js 실시간 대시보드, 봇 제어, 전략 비교 |
| 인프라 | Mac caffeinate, 프로세스 직접 관리 | Docker Compose, CI/CD, Prometheus+Grafana |

### 1.3 핵심 개선점

1. **스코어링 아키텍처 재설계**: 임의 상수(×5, ×10, ×33) → Z-score 정규화, 차등 가중치
2. **ATR 기반 동적 리스크**: 고정 3% 손절 → ATR 기반 동적 손절/포지션 사이징
3. **이벤트 주도 디커플링**: TradingLoop 13개 직접 의존 → EventBus pub/sub
4. **통계적 전략 검증**: 단순 백테스트 → Walk-forward OOS 검증, Monte Carlo 시뮬레이션
5. **실시간 대시보드**: Streamlit(UX 2/10) → Next.js+WebSocket(기관급 모니터링)

### 1.4 성공 지표

| 지표 | 목표 | 측정 시점 |
|------|------|----------|
| Walk-forward OOS Sharpe | > 0.8 | Phase 2 완료 |
| Maximum Drawdown | < 25% | 백테스트 검증 |
| 페이퍼 → 실전 졸업 | 6주 이내 | Phase 3 이후 |
| 대시보드 LCP | < 2초 | Sprint 4 |
| 시스템 가용성 | > 99.5% | 운영 1개월 후 |

---

## 2. 현황 분석

> 기반: Round 1 감사 보고서 3건

### 2.1 유지 항목

bit-trader에서 traderj로 **재사용**하는 검증된 요소:

| 항목 | 이유 |
|------|------|
| ccxt async Upbit 래퍼 | 안정적 거래소 연동, Rate Limiter 포함 |
| 전략 프리셋 구조 (STR-003~006) | 파라미터화된 전략 관리 패턴 |
| 6개 스코어링 함수 (trend/momentum/volume/reversal/breakout/quick_momentum) | 핵심 로직 재사용 (개선 적용) |
| 상태 머신 (9-state) | IDLE→SCANNING→EXECUTING 등 봇 라이프사이클 |
| APScheduler 기반 스케줄링 | OHLCV 수집, 매크로 수집, 헬스체크 |
| 텔레그램 알림 | 거래/손절/에러 알림 채널 |

### 2.2 교체 항목

| 항목 | 현재 | 교체 대상 | 이유 |
|------|------|----------|------|
| 데이터베이스 | SQLite (단일 writer) | PostgreSQL 16 + TimescaleDB | 멀티 봇 동시 쓰기, hypertable 파티셔닝, 연속 집계 |
| 대시보드 | Streamlit (UX 2/10) | Next.js 15 + Lightweight Charts | 실시간 WS, 캔들스틱, 봇 제어, 반응형 |
| 리스크 상태 | 인메모리 (재시작 시 소실) | DB 영속화 (write-through) | 재시작 후 리스크 상태 자동 복원 |
| 이벤트 흐름 | TradingLoop 직접 호출 | asyncio EventBus pub/sub | 컴포넌트 디커플링, 확장성 |
| 로깅 | loguru | structlog (JSON) | 컨텍스트 바인딩, Docker 로그 통합 |

### 2.3 개선 항목

| 항목 | 현재 문제 | 개선 방향 |
|------|----------|----------|
| 스코어링 | 동일 가중 평균, 임의 스케일링 상수 | 차등 가중치(0.50/0.30/0.20), Z-score 정규화 |
| MTF 집계 | 1d TF가 스코어 병목 (MTF 2회 거래/2년) | 1d를 Daily Gate로 분리, TF 가중치 재조정 |
| 리스크 관리 | 고정 3% 손절, 변동성 무시 | ATR 기반 동적 손절/포지션 사이징, 트레일링 스탑 |
| 백테스트 | IS-only, Sharpe/Sortino 미계산 | Walk-forward OOS, 리스크 조정 지표, Monte Carlo |
| 매크로 스코어러 | 계단 함수, 4개 지표 | 연속 함수, 6개 지표 (펀딩레이트, BTC Dom 7d 추가) |

---

## 3. 기술 스택 결정

> 기반: Round 3 TDR Rev.1 (13개 기술 결정 + 리스크 레지스터)

### 3.1 백엔드 (Python)

| 영역 | 기술 | 버전 | 결정 근거 |
|------|------|------|----------|
| 런타임 | Python | 3.13 | bit-trader 코드베이스 재사용 |
| 패키지 매니저 | Poetry | 2.x | 기존 호환 |
| 거래소 | ccxt (async) | ^4.4 | 멀티 거래소 지원 |
| DB (OLTP) | PostgreSQL + TimescaleDB | 16 + latest | TDR-001: hypertable, 연속 집계, 보존 정책 |
| DB (OLAP) | DuckDB | latest | TDR-001: 백테스트 대량 분석용 보조 DB |
| DB 드라이버 | asyncpg | latest | TDR-006: 네이티브 async, Prepared Statement |
| 마이그레이션 | Alembic | latest | TDR-006: Python 마이그레이션, 자동 감지 |
| API | FastAPI | latest | Pydantic v2 네이티브, OpenAPI 자동 생성, WS 내장 |
| 이벤트 버스 | asyncio 커스텀 | - | TDR-005: in-process Queue, DB 복원 |
| 로깅 | structlog (JSON) | latest | 컨텍스트 바인딩, Docker 통합 |
| 메트릭 | prometheus-client | latest | 13개 커스텀 메트릭 |
| 백테스트 | 커스텀 이벤트 기반 | - | TDR-002: 실전과 동일 경로 검증 |
| ML | scikit-learn + LightGBM + Optuna | latest | TDR-003: Walk-forward 학습 |
| 지표 계산 | pandas-ta + Z-score 래퍼 | latest | TDR-008: 커뮤니티 표준 |

### 3.2 프론트엔드 (TypeScript)

| 영역 | 기술 | 버전 | 결정 근거 |
|------|------|------|----------|
| 프레임워크 | Next.js (App Router) | 15 | SSR + API Routes + WS |
| 패키지 매니저 | pnpm | latest | 모노레포 호환 |
| 금융 차트 | Lightweight Charts | 4.x | TDR-004: TradingView OSS, Canvas 고성능 |
| 통계 차트 | Recharts | latest | TDR-004: PnL/통계 비금융 차트 |
| 상태 관리 | Zustand | latest | WS 스트림 최적 |
| 스타일링 | TailwindCSS + shadcn/ui | latest | 다크 테마 기본, 일관된 디자인 시스템 |
| 테이블 | TanStack Table | v8 | 가상 스크롤, 정렬/필터 내장 |
| 폼 | React Hook Form + Zod | latest | 전략 파라미터 유효성 검증 |
| API 타입 | openapi-typescript | latest | OpenAPI → TypeScript 자동 생성 |

### 3.3 인프라

| 영역 | 기술 | 결정 근거 |
|------|------|----------|
| 컨테이너 | Docker + docker-compose | 서비스 격리, 자동 재시작 |
| DB 이미지 | timescale/timescaledb:latest-pg16 | TDR-001 |
| 모니터링 | Prometheus + Grafana | 13개 커스텀 메트릭, 알림 규칙 |
| CI/CD | GitHub Actions | 서비스별 독립 워크플로우 |
| 레포 구조 | 모노레포 (도구 없음) | TDR-007: 서비스별 최상위 분리 |

---

## 4. 시스템 아키텍처

> 기반: Round 4 아키텍처 상세 설계서

### 4.1 아키텍처 스타일

**이벤트 주도 모놀리식** (Event-Driven Monolith) — 서비스별 Docker 컨테이너 분리

```
┌─────────────────────────────────────────────────────────────────┐
│                    docker-compose 네트워크                        │
│                                                                   │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────┐ │
│  │ engine   │   │ api      │   │ dashboard│   │ postgres     │ │
│  │ (Python) │──→│ (FastAPI)│──→│ (Next.js)│   │ (TimescaleDB)│ │
│  │ EventBus │   │ REST+WS  │   │ Zustand  │   │ hypertable   │ │
│  │ Strategy │   │ Bridge   │   │ LW Charts│   │ asyncpg      │ │
│  │ Execution│   │          │   │ shadcn   │   │              │ │
│  └────┬─────┘   └────┬─────┘   └──────────┘   └──────┬───────┘ │
│       └──────────────┴─────────────────────────────────┘         │
│                   shared PostgreSQL 접근                           │
│  ┌──────────┐   ┌──────────┐                                    │
│  │prometheus│   │ grafana  │                                    │
│  └──────────┘   └──────────┘                                    │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 모듈 구조

```
traderj/
├── shared/              # 공유 Python 패키지 (models, events, protocols, enums)
├── engine/              # 트레이딩 엔진
│   ├── config/          # 설정 + 전략 프리셋
│   ├── exchange/        # ccxt Upbit 래퍼 + WebSocket
│   ├── data/            # DataStore(PG/SQLite) + OHLCV/매크로 수집
│   ├── strategy/        # 지표, 스코어링, 시그널, 레짐, 리스크
│   │   └── backtest/    # Walk-forward, 메트릭, Monte Carlo
│   ├── execution/       # 주문/포지션/리스크/CircuitBreaker
│   ├── loop/            # EventBus, Scheduler, StateMachine, IPC
│   └── notify/          # 텔레그램
├── api/                 # FastAPI (REST 20개 + WS 6채널)
│   ├── routes/          # 엔드포인트
│   ├── ws/              # WebSocket 핸들러
│   ├── schemas/         # Pydantic 응답 모델
│   └── middleware/      # auth, cors, metrics
├── dashboard/           # Next.js 15 (App Router)
│   ├── src/app/         # 4개 페이지 (/, /analytics, /settings, /backtest)
│   ├── src/components/  # UI 컴포넌트
│   ├── src/stores/      # Zustand 스토어
│   └── src/lib/         # API/WS 클라이언트, 커스텀 훅
├── scripts/             # 마이그레이션, 타입 생성, Parquet 익스포트
├── migrations/          # Alembic
└── tests/               # 통합 테스트
```

### 4.3 서비스 간 통신

| 경로 | 프로토콜 | 용도 |
|------|---------|------|
| Engine ↔ API | Unix Domain Socket (JSON-lines) | 봇 제어(api→engine), 이벤트 push(engine→api) |
| API ↔ Dashboard | REST + WebSocket | 데이터 조회(REST), 실시간 스트림(WS 6채널) |
| Engine/API → PostgreSQL | asyncpg TCP | 데이터 읽기/쓰기 |
| Prometheus → Engine/API | HTTP scrape | 메트릭 수집 (`:8001/metrics`, `:8000/metrics`) |

### 4.4 DB 스키마 요약

| 테이블 | 유형 | 핵심 칼럼 | 비고 |
|--------|------|----------|------|
| candles | hypertable | time, symbol, timeframe, OHLCV | 2년 자동 보존, 1d 연속 집계 |
| signals | regular | strategy_id, direction, score, components(JSONB) | 전략별 시그널 이력 |
| orders | regular | strategy_id, side, amount, price, status, idempotency_key | 멱등성 보장 |
| positions | regular | strategy_id, entry_price, stop_loss, realized_pnl, status | 포지션 라이프사이클 |
| risk_state | regular | strategy_id, consecutive_losses, daily_pnl, cooldown_until | write-through 영속화 |
| bot_state | regular | strategy_id, state, trading_mode | 봇 상태 머신 |
| paper_balances | regular | strategy_id, krw, btc, initial_krw | 페이퍼 트레이딩 잔고 |
| daily_pnl | regular | date, strategy_id, realized, unrealized, trade_count | 일별 성과 |
| macro_snapshots | regular | timestamp, fear_greed, funding_rate, btc_dom_7d_change, market_score | 매크로 지표 |
| backtest_results | regular (P1) | strategy_id(TEXT), config_json(JSONB), metrics_json(JSONB), equity_curve_json(JSONB), trades_json(JSONB), walk_forward_json(JSONB) — UUID PK | 백테스트 결과 |

### 4.5 이벤트 버스

asyncio 기반 in-process 이벤트 버스로 13개 이벤트 타입 정의:

```
MarketTickEvent     → RiskManager, PositionManager, API WS Bridge
OHLCVUpdateEvent    → StrategyEngine
SignalEvent         → ExecutionEngine, API WS Bridge
OrderRequestEvent   → OrderManager
OrderFilledEvent    → PositionManager, RiskManager, Notifier, API WS Bridge
PositionOpenedEvent → RiskManager, API WS Bridge
PositionClosedEvent → RiskManager, API WS Bridge
StopLossTriggeredEvent → ExecutionEngine
RiskAlertEvent      → Notifier, API WS Bridge
BotStateChangeEvent → Logger, API WS Bridge
RegimeChangeEvent   → Logger, API WS Bridge
RiskStateEvent      → Dashboard WS, TelegramNotifier
MarketDataEvent     → StrategyEngine
```

---

## 5. 전략 엔진 설계

> 기반: Round 4 전략 엔진 상세 설계서 (72KB, 8개 섹션)

### 5.1 시그널 생성 파이프라인

```
OHLCV(DB) → compute_indicators() → normalize_scores(Z-score) → filter_scores()
                                                                      │
                                                              TimeframeScore
                                                                      │
RegimeClassifier → param_overrides → aggregate_mtf() → technical_score
                                                                      │
MacroScorer ──────────────────────────────────────→ macro_score ──────┤
ScorePlugins (P2) ────────────────────────────→ plugin_score ────────┤
                                                                      │
                                                                final_score
                                                                      │
                                                    RiskEngine.evaluate()
                                                    → direction, position_size,
                                                      stop_loss, trailing_params
                                                                      │
                                                            SignalEvent → EventBus
```

### 5.2 스코어링 개선

| 항목 | bit-trader | traderj |
|------|-----------|---------|
| 가중치 | 동일 (trend=momentum=volume=1/3) | 차등 (trend 0.50, momentum 0.30, volume 0.20) |
| 스케일링 | 임의 상수 (×5, ×10, ×33) | Z-score 정규화 → tanh 매핑 |
| ADX 판단 | 이진 (>25 = trending) | 연속: (DI+ - DI-) / (DI+ + DI-) × ADX강도 |
| MACD 크로스 | 즉시 소멸 (±0.5 → 0) | 3-bar 선형 감쇠 (0.5 → 0.33 → 0.17) |
| MTF 집계 | 1d(0.3) 병목 | 1d → Daily Gate 분리, 1h(0.3)+4h(0.5) 기본 |

### 5.3 시장 레짐 분류기 (RegimeClassifier)

4-state 레짐 분류 + 히스테리시스:

| 레짐 | 조건 | 파라미터 조정 |
|------|------|-------------|
| TRENDING_HIGH_VOL | ADX > 25 & ATR > median | threshold -0.05 (적극적), position ×1.0 |
| TRENDING_LOW_VOL | ADX > 25 & ATR ≤ median | threshold 0.0 (기본), position ×1.0 |
| RANGING_HIGH_VOL | ADX ≤ 25 & ATR > median | threshold +0.10 (보수적), position ×0.5 |
| RANGING_LOW_VOL | ADX ≤ 25 & ATR ≤ median | threshold +0.05, position ×0.7 |

- 히스테리시스: 3-bar 연속 확인 후 레짐 전환 (잦은 전환 방지)

### 5.4 백테스트 프레임워크

- **엔진**: 커스텀 이벤트 기반 (bit-trader SignalGenerator 직접 호출)
- **검증**: Walk-forward 5-fold OOS (IS 70%:OOS 30%)
- **지표**: Sharpe, Sortino, Calmar, Max DD, Win Rate, Profit Factor
- **ML**: LightGBM 플러그인 (ScorePlugin Protocol), Optuna 최적화
- **시뮬레이션**: Monte Carlo 1,000회 (95% CI에서 positive return 필수)

---

## 6. 리스크 관리 프레임워크

> 기반: Round 4 전략 엔진 설계서 §5 + Round 2 전략 요구사항서

### 6.1 ATR 기반 동적 리스크

| 요소 | 고정 (bit-trader) | 동적 (traderj) |
|------|-------------------|----------------|
| 손절 | -3% (고정) | entry - 2.0 × ATR(14) |
| 포지션 사이징 | 20% 고정 | target_risk(2%) / ATR_pct (변동성 역비례) |
| 트레일링 스탑 | 없음 | +3% 이익 후 활성화, 2.5 × ATR 트레일 |
| 변동성 캡 | 없음 | ATR > 8% → 진입 금지 |

### 6.2 CircuitBreaker

3-state 서킷 브레이커 (CLOSED → OPEN → HALF_OPEN):

| 상태 | 조건 | 동작 |
|------|------|------|
| CLOSED | 정상 | 모든 주문 허용 |
| OPEN | 연속 3회 실패 또는 일일 손실 >5% | 모든 주문 차단, 쿨다운 24시간 |
| HALF_OPEN | 쿨다운 종료 | 1건만 허용, 성공 시 CLOSED, 실패 시 OPEN |

### 6.3 일일/연속 제한

| 규칙 | 임계값 | 액션 |
|------|--------|------|
| 일일 최대 손실 | -5% | 해당 전략 24시간 중단 |
| 연속 손실 | 3회 | 24시간 쿨다운 |
| 최소 주문 금액 | ₩5,000 | 주문 거부 |
| 수수료 | 0.05% (Upbit) | 백테스트/실전 동일 적용 |
| 리스크 상태 영속화 | write-through | 재시작 시 자동 복원 |

### 6.4 페이퍼 → 실전 졸업 게이트

```
[백테스트 통과] → [Signal-Only 2주] → [Paper 4주] → [Pre-Live 2주] → [실전 10%]
                                                                        │
                                                              자본 점진 확대
                                                              10% → 20% → 40% → 80%
```

**필수 졸업 요건**: 페이퍼 6주 연속 운영, Sharpe ≥ 0.5, MDD ≤ 12%, 거래 ≥ 10회, 시그널-백테스트 일치 ≥ 85%, 리스크 이벤트 작동 확인

---

## 7. 대시보드 & UI 설계

> 기반: Round 4 대시보드 상세 설계서 (63KB, 8개 섹션 + 부록 3개)

### 7.1 페이지 구조

| 라우트 | 우선순위 | 핵심 기능 |
|--------|---------|----------|
| `/` (메인 대시보드) | P0 | KPI 헤더, 캔들스틱 차트, 봇 관리 패널, 주문/포지션 테이블 |
| `/analytics` | P1 | PnL 분석, Equity Curve, 전략 비교, 시그널 히트맵 |
| `/settings` | P2 | 전략 파라미터 설정, 알림 규칙 관리 |
| `/backtest` | P2 | 백테스트 결과 뷰어 |

### 7.2 핵심 컴포넌트

| 컴포넌트 | 설명 | 데이터 소스 |
|---------|------|-----------|
| KPIHeader | BTC 가격, 포트폴리오 가치, 총 PnL, 활성 봇 수 (sticky) | WS: ticker, bot_status |
| LWChartWrapper | Lightweight Charts 캔들스틱 + 볼륨 + 지표 오버레이 | REST: candles, WS: ticker |
| BotControlPanel | 봇 카드 (상태, PnL, 포지션), Start/Pause/Stop 버튼 | REST: bots, WS: bot_status |
| EmergencyStopButton | 전체 긴급 중지 (확인 다이얼로그 포함) | POST: emergency-stop |
| DataTabs | OpenPositions / OrderHistory / ClosedPositions 탭 | REST + WS |

### 7.3 실시간 데이터 흐름

```
Engine EventBus
    │
    ▼ (IPC: Unix Socket)
API Server
    │
    ▼ (WebSocket 6채널)
Dashboard Zustand Stores
    │
    ▼ (React re-render)
UI Components
```

**WebSocket 채널**: ticker (~1/sec), bot_status (on change), orders (on trade), positions (on change), signals (per eval), alerts (on alert)

**재연결**: 지수 백오프 (1s → 30s) + jitter, 최대 10회 재시도

### 7.4 디자인 시스템

- **토큰**: 36개 CSS Custom Properties (18 라이트 + 18 다크)
- **타이포그래피**: Inter (UI), JetBrains Mono (숫자/코드), tabular-nums
- **컴포넌트**: shadcn/ui 기반 + 8개 커스텀 (NumberDisplay, PnLText, DataTable 등)
- **접근성**: WCAG AA 준수, 키보드 네비게이션, 스크린 리더 대체 텍스트
- **성능 목표**: LCP < 2s, FID < 100ms, CLS < 0.1

---

## 8. 구현 로드맵

> 기반: Round 5 로드맵 3건 (전략/엔지니어링/대시보드) 통합

### 8.1 3개 도메인 통합 Phase 일정

```
         Week 1-2       Week 3-4       Week 5-6       Week 7-8       Week 9-10      Week 11-12     Week 13-14     Week 15-16
         ────────       ────────       ────────       ────────       ──────────      ──────────     ──────────     ──────────
엔지니어링 [Phase 0        ][Phase 1        ][Phase 2                  ][Phase 3                  ][Phase 4        ]
          기반 구축        코어 인프라       트레이딩 엔진               API + Docker               최적화/보안
          shared/          DataStore(PG)    StrategyEngine 통합         REST 20개                  성능 최적화
          DB 스키마        EventBus         OrderManager               WebSocket 6채널             보안 감사
          Docker 기본      ExchangeClient   RiskManager                IPC                        배포 자동화
                          Scheduler        StateMachine               Prometheus+Grafana

전략      [Phase S0        ][Phase S1                  ][Phase S2                                  ][Phase S3/S4              ]
          지표 파이프라인    스코어링 엔진                 백테스트 프레임워크                           레짐/ML/Monte Carlo
          Z-score 정규화   MTF 집계                     Walk-forward                               LightGBM 플러그인
          IndicatorConfig  SignalGenerator              OOS 검증                                   Optuna 최적화
                          RiskEngine(기본)              프리셋 검증                                 페이퍼 트레이딩

대시보드   [Sprint 1        ][Sprint 2        ][Sprint 3        ][Sprint 4        ]
          디자인 시스템      핵심 페이지 (P0)   고급 기능 (P1+P2)  최적화/폴리싱
          토큰/컴포넌트     캔들스틱+봇패널    Analytics          Lighthouse 최적화
          WS/API 클라이언트  데이터 테이블      설정/백테스트 뷰어  접근성 감사
          Mock 기반 개발     실시간 통합        매크로 바          PWA + 크로스브라우저
```

### 8.2 도메인 간 의존성 타임라인

| 시점 | 제공자 → 수신자 | 내용 |
|------|----------------|------|
| Week 1 | 엔지니어링 → 전략/대시보드 | shared/ 패키지 (models 10개+BacktestResult, events 13개, protocols 5개+ScorePlugin) |
| Week 1 | 엔지니어링 → 대시보드 | OpenAPI YAML 초안 (Mock 서버 기반 UI 선행 개발) |
| Week 3 | 엔지니어링 → 전략 | DataStore SQLite 구현체 (개발/테스트용) |
| Week 3 | 엔지니어링 → 전략 | EventBus 완성 |
| Week 5 | 전략 → 엔지니어링 | SignalResult/RiskConfig 스키마 확정 |
| Week 7 | 엔지니어링 → 대시보드 | REST API + WS 서버 완성 → Mock → 실제 API 전환 |
| Week 9 | 엔지니어링 → 전략 | PostgreSQL 2년 데이터 + DuckDB 파이프라인 |
| Week 9 | 전략 → 대시보드 | BacktestResult JSON 스키마 |

### 8.3 마일스톤 요약

| 마일스톤 | 시점 | 핵심 산출물 | 성공 지표 |
|---------|------|-----------|----------|
| **M1: 코어 완성** | Week 4 | EventBus + DataStore + ExchangeClient | 단위 테스트 100% 통과 |
| **M2: 엔진 동작** | Week 8 | 전체 거래 사이클 Paper 모드 | E2E 거래 사이클 통과 |
| **M3: API+대시보드** | Week 10 | REST+WS+대시보드 통합 | 대시보드에서 실시간 봇 모니터링 |
| **M4: 백테스트 검증** | Week 12 | Walk-forward OOS 결과 | Sharpe > 0.8, OOS 정확도 > 55% |
| **M5: ML+안정화** | Week 16 | LightGBM + Monte Carlo + 보안 | 전체 테스트 80%+ 커버리지 |
| **M6: 페이퍼 졸업** | Week 22 | 6주 페이퍼 운영 | MDD < 12%, 거래 ≥ 10회 |

---

## 9. 테스트 전략

> 기반: Round 5 엔지니어링 로드맵 §2

### 9.1 테스트 피라미드

```
                    ┌───────────────┐
                    │   E2E Tests   │  5% (~10개) — Docker Compose 전체 시스템
                    ├───────────────┤
                    │  Integration  │  20% (~50개) — DB, IPC, WebSocket
                    ├───────────────┤
                    │  Unit Tests   │  75% (~200개) — 순수 로직, 모델
                    └───────────────┘
```

### 9.2 커버리지 목표

| 패키지 | 목표 | 이유 |
|--------|------|------|
| shared/ | 95% | 전 서비스 기반 |
| engine/execution/ | 90% | 금융 로직 정확성 필수 |
| engine/strategy/ | 85% | 지표/스코어링/시그널 |
| api/routes/ | 85% | REST 엔드포인트 |
| dashboard/ 컴포넌트 | 70% | UI 시각적 검증은 E2E |
| **전체** | **80%+** | CI 게이트 기준 |

### 9.3 테스트 도구

| 도구 | 용도 |
|------|------|
| pytest + pytest-asyncio | Python 단위/통합 테스트 |
| pytest-cov | 커버리지 측정 |
| factory_boy | 테스트 데이터 팩토리 |
| pytest-docker | Docker 기반 통합 테스트 |
| httpx | FastAPI TestClient |
| vitest + React Testing Library | Next.js 컴포넌트 테스트 |
| Playwright | E2E 브라우저 테스트 |

### 9.4 백테스트 검증 기준

| 지표 | 목표 |
|------|------|
| Sharpe Ratio (OOS) | > 0.8 |
| Sortino Ratio | > 1.0 |
| Maximum Drawdown | < 25% |
| OOS 방향 정확도 | > 55% |
| 연간 거래 횟수 | 20-100회 |
| Profit Factor | > 1.3 |

### 9.5 과적합 방지 규칙

1. IS-OOS Sharpe 차이 < 0.5
2. 파라미터 ±20% 변동 시 Sharpe 변동 < 30%
3. OOS 구간 최소 10회 이상 거래
4. 다중 비교 시 Bonferroni 보정

---

## 10. 배포 전략

> 기반: Round 4 아키텍처 설계서 §10 + Round 5 엔지니어링 로드맵 §3-4

### 10.1 Docker Compose 구성

6개 서비스:

| 서비스 | 이미지 | 포트 | 의존성 |
|--------|--------|------|--------|
| postgres | timescale/timescaledb:latest-pg16 | 5432 | - |
| engine | engine:latest (Python 3.13) | - | postgres |
| api | api:latest (FastAPI/uvicorn) | 8000 | postgres, engine |
| dashboard | dashboard:latest (Next.js standalone) | 3000 | api |
| prometheus | prom/prometheus:latest | 9090 | engine, api |
| grafana | grafana/grafana:latest | 3001 | prometheus |

### 10.2 CI/CD 파이프라인

```
[Push/PR] → GitHub Actions
                │
    ┌───────────┼───────────┐
    ▼           ▼           ▼
 engine.yml   api.yml    dashboard.yml
    │           │           │
    ├ lint      ├ lint      ├ lint
    ├ test      ├ test      ├ test
    ├ coverage  ├ coverage  ├ build
    └ build     └ build     └ Lighthouse CI

[Tag push] → deploy.yml
                │
    ┌───────────┴──────────┐
    ▼                      ▼
 Docker Build           Deploy
 (multi-arch)           (수동 승인 게이트)
```

### 10.3 배포 런북 요약

| 단계 | 명령 | 검증 |
|------|------|------|
| 1. 이미지 빌드 | `docker compose build` | 빌드 성공 |
| 2. DB 마이그레이션 | `make migrate` | Alembic head 확인 |
| 3. 서비스 기동 | `docker compose up -d` | 6개 서비스 healthy |
| 4. 헬스체크 | `curl /api/v1/health` | `{status: "ok"}` |
| 5. 스모크 테스트 | 대시보드 접속 + WS 연결 확인 | 실시간 가격 표시 |

**롤백**: `docker compose down && git checkout <prev-tag> && docker compose up -d`

### 10.4 모니터링 알림 규칙

| 규칙 | 조건 | 채널 |
|------|------|------|
| 엔진 다운 | engine 헬스체크 2회 연속 실패 | Telegram + Grafana |
| API 응답 지연 | P95 > 2초 (5분간) | Grafana |
| DB 연결 실패 | asyncpg 연결 풀 고갈 | Telegram + Grafana |
| 에러율 급증 | 5xx 비율 > 5% (5분간) | Grafana |
| 디스크 사용량 | PostgreSQL 볼륨 > 80% | Grafana |

---

## 11. 리스크 평가

> 기반: Round 3 TDR 리스크 레지스터 + Round 5 도메인별 리스크

### 11.1 기술 리스크 (TDR 리스크 레지스터)

| ID | 리스크 | 영향도 | 확률 | 완화 전략 |
|----|--------|--------|------|----------|
| R1 | TimescaleDB 버전 호환성 | 중 | 낮 | Docker 이미지 버전 고정, 릴리스 노트 확인 |
| R2 | DuckDB-PostgreSQL 데이터 불일치 | 중 | 중 | 백테스트 직전 익스포트 강제, 타임스탬프 검증 |
| R3 | 커스텀 백테스트 엔진 개발 지연 | 높 | 중 | P1 후반 배치, P0 우선 완료 |
| R4 | ML 모델 과적합 | 중 | 중 | Walk-forward 필수, 자동 비활성화 스위치 |
| R5 | Optuna 하이퍼파라미터 오버피팅 | 중 | 중 | OOS 최종 검증, 파라미터 안정성 모니터링 |
| R6 | LW Charts 지표 오버레이 한계 | 낮 | 낮 | 핵심 5개만 수동 구현 |
| R7 | 이벤트 버스 프로세스 재시작 유실 | 중 | 낮 | DB가 truth, 재시작 시 DB에서 복원 |
| R8 | asyncpg SQL 인젝션 | 높 | 낮 | 파라미터화 쿼리 강제, 코드 리뷰 |
| R9 | shared 패키지 버전 동기화 | 중 | 중 | Poetry workspace + CI 통합 테스트 |
| R10 | pandas-ta 지표 버그 | 중 | 낮 | 주요 5개 지표 단위 테스트 + TA-Lib 교차 검증 |
| R11 | WebSocket 재연결 로직 | 낮 | 낮 | useWebSocket 훅 1회 구현 |

### 11.2 전략 리스크

| ID | 리스크 | 영향도 | 확률 | 완화 전략 |
|----|--------|--------|------|----------|
| S-R1 | Walk-forward Sharpe < 0.8 | 높 | 중 | 파라미터 그리드 확대, 레짐별 별도 최적화 |
| S-R2 | 레짐 분류 오류 | 중 | 낮 | 히스테리시스 3-bar, 수동 오버라이드 |
| S-R3 | 슬리피지 과소평가 | 높 | 중 | 백테스트에 0.1% 슬리피지 내장, 소액 실전 30일 |
| S-R4 | 매크로 데이터 소스 장애 | 낮 | 낮 | 24h 캐시, macro_weight=0 폴백 |

### 11.3 프로젝트 리스크

| ID | 리스크 | 영향도 | 확률 | 완화 전략 |
|----|--------|--------|------|----------|
| P-R1 | 도메인 간 일정 지연 (의존성 체인) | 높 | 중 | OpenAPI 선행 제공, Mock 서버 기반 병렬 개발 |
| P-R2 | 기존 bit-trader 로직 이식 오류 | 중 | 중 | 동일 입력 데이터로 bit-trader vs traderj 출력 비교 테스트 |
| P-R3 | 스코프 크립 (기능 확장 유혹) | 중 | 높 | P0/P1/P2 우선순위 엄격 적용, P2는 M4 이후만 |
| P-R4 | Upbit API 변경/장애 | 중 | 낮 | ExchangeClient Protocol 추상화, ccxt 업데이트 모니터링 |
| P-R5 | Docker 리소스 부족 (Mac 로컬) | 낮 | 중 | 개발용 docker-compose.dev.yml (SQLite, 서비스 최소화) |

### 11.4 리스크 대응 우선순위

**즉시 대응 필요 (높음 × 중간 이상)**:
1. **R3**: 백테스트 엔진 지연 → Phase S2를 Phase 1 인프라와 병렬 착수
2. **S-R1**: OOS Sharpe 미달 → 전략 프리셋 다양화, 레짐별 튜닝
3. **S-R3**: 슬리피지 → 백테스트 비용 모델에 반드시 포함
4. **P-R1**: 의존성 지연 → Mock 기반 병렬 개발 (OpenAPI YAML 선행)

---

## 부록: 산출물 목록

| # | 파일 | Round | 도메인 |
|---|------|-------|--------|
| 1 | round1-strategy-audit.md | R1 | 전략 |
| 2 | round1-architecture-audit.md | R1 | 아키텍처 |
| 3 | round1-ux-audit.md | R1 | 대시보드 |
| 4 | round2-strategy-vision.md | R2 | 전략 |
| 5 | round2-strategy-requirements.md | R2 | 전략 |
| 6 | round2-architecture-vision.md | R2 | 아키텍처 |
| 7 | round2-architecture-requirements.md | R2 | 아키텍처 |
| 8 | round2-dashboard-vision.md | R2 | 대시보드 |
| 9 | round2-dashboard-requirements.md | R2 | 대시보드 |
| 10 | round3-tech-decisions.md | R3 | 전체 |
| 11 | round4-strategy-design.md | R4 | 전략 |
| 12 | round4-architecture-design.md | R4 | 아키텍처 |
| 13 | round4-dashboard-design.md | R4 | 대시보드 |
| 14 | round5-strategy-roadmap.md | R5 | 전략 |
| 15 | round5-engineering-roadmap.md | R5 | 아키텍처 |
| 16 | round5-dashboard-roadmap.md | R5 | 대시보드 |

---

> **문서 상태**: Rev.1 — 최종 승인 대기
> **변경 이력**: Round 1-5 산출물 16건 종합
