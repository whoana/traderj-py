# traderj 구현 팀 구성안

## Context

5라운드 설계 완료 + 교차 검증 수정 완료 후, 구현 착수를 위한 Agent Teams 구성안이다.
프로젝트는 3개 도메인(Engine+API / Strategy / Dashboard)으로 나뉘며, 총 214개 작업(100+31+83)을 Phase/Sprint 단위로 병렬 진행해야 한다.

---

## 추천안: 동적 4인 팀 (옵션 B+)

### 팀 구성

| 이름 | 에이전트 타입 | 담당 도메인 | 작업 수 |
|------|-------------|-----------|--------|
| **team-lead** | `general-purpose` | 조정 + shared/ 구현 + 코드 리뷰 | — |
| **engine** | `bot-developer` | Engine + API (Python) | 100개 |
| **strategist** | `quant-expert` | 전략 엔진 + 백테스트 (Python) | 31개 |
| **frontend** | `dashboard-designer` | 대시보드 (TypeScript) | 83개 |

### 왜 4인인가

| 비교 | 3인 (최소) | **4인 (추천)** | 5~6인 (확장) |
|------|-----------|--------------|-------------|
| 조정 오버헤드 | 낮음 | **적정** | 높음 |
| 병렬성 | 리더 병목 | **3 도메인 병렬** | Phase 0-1 유휴 발생 |
| 코드 리뷰 | 불가 (자기 리뷰) | **리더가 전담** | 별도 리뷰어 효용 낮음 |
| 리소스 비용 | 최소 | **균형** | API 비용 급증 |

핵심: **team-lead가 구현에서 분리되어 조정/리뷰에 집중**하면서, Phase 0에서는 shared/ 패키지를 직접 구현하여 유휴 시간 제거

---

## Phase별 팀 운영

### Phase 0 (Week 1-2): 기반 구축

```
team-lead --- shared/ 패키지 설계 확정, 인터페이스 계약, OpenAPI 리뷰
engine    --- 모노레포 구조, DB 스키마+마이그레이션, Docker, CI, shared/ 구현
strategist    [대기] -> shared/ 완성 후 S0 착수 (지표 파이프라인, Z-score)
frontend      [대기] -> OpenAPI 초안 후 Sprint 1 착수 (디자인 시스템, MSW Mock)
```

**언블록 시점**:
- engine이 `shared/` 커밋 -> strategist S0 착수
- engine이 OpenAPI 초안 커밋 -> frontend Sprint 1 착수

### Phase 1 (Week 3-4): 코어 인프라

```
team-lead --- engine 코드 리뷰 (DataStore, EventBus), 이벤트 인터페이스 조율
engine    --- DataStore(PG+SQLite), EventBus, ExchangeClient, Scheduler, AppOrchestrator
strategist -- S0 완료 -> S1 착수 (스코어링 6종, MTF 집계, SignalGenerator, RiskEngine)
frontend  --- Sprint 1 완료 -> Sprint 2 착수 (캔들스틱, 봇 패널 -- Mock 기반)
```

**언블록**: engine SQLiteDataStore + EventBus -> strategist 통합 테스트 가능

### Phase 2 (Week 5-6): 트레이딩 엔진

```
team-lead --- 금융 로직 코드 리뷰 (OrderManager, RiskManager -- 최고 우선순위)
engine    --- OrderManager+CB, PositionManager, RiskManager 영속화, StateMachine, Telegram
strategist -- S1 완료 -> S2 착수 (백테스트 엔진, Walk-forward, 프리셋 검증)
frontend  --- Sprint 2 진행 (데이터 테이블, 주문 이력 -- Mock)
```

**코드 리뷰 집중**: `execution/order_manager.py`, `execution/risk.py` -- 금전 영향 코드

### Phase 3 (Week 7-8): API + 통합 <- 가장 바쁜 Phase

```
team-lead --- OpenAPI 최종 diff 검증, Mock->실제 전환 조율, WS 프로토콜 검증
engine    --- FastAPI REST 20개, WS 6채널, IPC, OpenAPI 타입 생성, Docker 전체 빌드
strategist -- S2 완료 -> S3 착수 (레짐 분류기, 트레일링 스탑, 매크로 확장, 페이퍼 시작)
frontend  --- Sprint 3: Mock -> 실제 API 전환, WS 실시간 통합, Analytics 완성
```

**핵심 이벤트**: engine REST+WS 완성 -> team-lead가 타입 생성 -> frontend Mock 교체

### Phase 4 (Week 9-10): 최적화 + 안정화

```
team-lead --- 보안 감사, E2E 시나리오 실행, 배포 런북 검증
engine    --- 성능 최적화, 보안 강화, E2E 테스트, 배포 자동화
strategist -- S3 완료 -> S4 (LightGBM, Monte Carlo -- 선택적)
frontend  --- Sprint 4 (Lighthouse 최적화, 접근성 감사, E2E Playwright)
```

---

## 의존성 관리 프로토콜

team-lead가 관리하는 6개 체크포인트:

| 시점 | 제공 -> 수신 | 전달 항목 | team-lead 액션 |
|------|------------|----------|---------------|
| Week 1 중반 | engine -> strategist | shared/ (models, events, protocols) | TaskUpdate 언블록 + SendMessage |
| Week 1 후반 | engine -> frontend | OpenAPI YAML 초안 | frontend Sprint 1 착수 메시지 |
| Week 3 | engine -> strategist | SQLiteDataStore + EventBus | 통합 테스트 환경 안내 |
| Week 5 | strategist -> engine | SignalResult/RiskConfig 확정 | engine에 스키마 반영 요청 |
| Week 7 | engine -> frontend | REST API + WS 완성 + 타입 생성 | Mock->실제 전환 안내 |
| Week 9 | strategist -> frontend | BacktestResult JSON 스키마 | 백테스트 뷰어 데이터 구조 |

---

## 코드 리뷰 전략

| 리뷰 대상 | 리뷰어 | 중점 | Phase |
|-----------|--------|------|-------|
| `shared/` 패키지 | team-lead | 인터페이스 일관성, 순환 의존 방지 | 0 |
| `engine/execution/` (금융 로직) | team-lead | 멱등성, Decimal 정밀도, SQL injection | 2 |
| `engine/data/` (DB 접근) | team-lead | asyncpg 파라미터 바인딩, 트랜잭션 | 1 |
| `strategy/backtest/` | team-lead | Look-ahead bias, Walk-forward 경계 | S2 |
| `api/routes/` | team-lead | 인증, 페이지네이션, 에러 일관성 | 3 |
| `dashboard/` 핵심 컴포넌트 | team-lead | TS 타입 안전, 접근성, 성능 | Sprint 2-4 |

---

## Task 크기 가이드라인

| 단위 | 규모 | 예시 |
|------|------|------|
| 파일 1개 | 100-300줄 | `event_bus.py`, `ws-client.ts` |
| 모듈 1개 (2-3 파일) | 300-600줄 | DataStore (Protocol + PG + SQLite) |
| 기능 단위 (3-5 파일 + 테스트) | 500-1000줄 | OrderManager + CircuitBreaker + 테스트 |

**TaskCreate 단위**: Phase 하위 그룹 (P0-E1, P0-E2 등) = 1 Task

---

## Phase 0 초기 Task 목록

TeamCreate 직후 team-lead가 생성할 Task:

```
Task 1: "P0-E1: 모노레포 구조 + shared/ 패키지"
  owner: engine
  description: 디렉터리 구조, shared/(models 11개, events 13개, protocols 6개, enums)
               engine/api/dashboard 패키지 초기화, Makefile, .env.example
  blocks: [Task 4, Task 5]

Task 2: "P0-E2: DB 스키마 + Alembic 마이그레이션"
  owner: engine
  blockedBy: [Task 1]
  description: Alembic 초기화, 001_initial(10테이블), 002_timescaledb, 003_backtest

Task 3: "P0-E3: Docker + CI + OpenAPI 초안"
  owner: engine
  blockedBy: [Task 1]
  description: docker-compose(6서비스), Dockerfiles 3개, GH Actions 3개, OpenAPI YAML
  blocks: [Task 5]

Task 4: "S0: 지표 파이프라인 + Z-score 정규화"
  owner: strategist
  blockedBy: [Task 1]  (shared/models.py 필요)
  description: IndicatorConfig, compute_indicators, normalizer, 단위 테스트

Task 5: "Sprint 1: 디자인 시스템 기반"
  owner: frontend
  blockedBy: [Task 1, Task 3]  (OpenAPI 초안 필요)
  description: Next.js 초기화, 디자인 토큰, UI 6종, WS/API 클라이언트, Zustand 4개
```

---

## 실행 방법

```
1. TeamCreate  -> team_name: "traderj"
2. Agent(bot-developer, name: "engine")        -> Task 1 즉시 착수
3. [Task 1 완료 후] Agent(quant-expert, name: "strategist")   -> Task 4 착수
4. [Task 3 완료 후] Agent(dashboard-designer, name: "frontend") -> Task 5 착수
5. team-lead: Phase 진행에 따라 Task 추가 생성, 리뷰, 언블록 관리
```

---

## 참조 파일

| 에이전트 | 주 참조 문서 |
|---------|------------|
| team-lead | `docs/PROJECT_PLAN.md`, 모든 Round 4-5 설계서 |
| engine | `docs/round5-engineering-roadmap.md`, `docs/round4-architecture-design.md` |
| strategist | `docs/round5-strategy-roadmap.md`, `docs/round4-strategy-design.md` |
| frontend | `docs/round5-dashboard-roadmap.md`, `docs/round4-dashboard-design.md` |
