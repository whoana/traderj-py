# Round 3: 기술 결정 기록 (TDR)

**작성일**: 2026-03-02
**주도**: bot-developer (아키텍처 도메인)
**참여**: quant-expert (전략 도메인), dashboard-designer (대시보드 도메인)
**기반**: Round 2 요구사항서 3건 (architecture, strategy, dashboard)

---

## 목차

1. [합의된 사항 (Round 2에서 확정)](#1-합의된-사항)
2. [TDR-001: 데이터베이스](#tdr-001-데이터베이스)
3. [TDR-002: 백테스트 프레임워크](#tdr-002-백테스트-프레임워크)
4. [TDR-003: ML/AI 파이프라인](#tdr-003-mlai-파이프라인)
5. [TDR-004: 차트 라이브러리](#tdr-004-차트-라이브러리)
6. [TDR-005: 이벤트 버스](#tdr-005-이벤트-버스)
7. [TDR-006: DB 드라이버 / ORM](#tdr-006-db-드라이버--orm)
8. [TDR-007: 모노레포 구조](#tdr-007-모노레포-구조)
9. [TDR-008: 지표 계산 라이브러리](#tdr-008-지표-계산-라이브러리)
10. [TDR-009: 실시간 통신 (WebSocket)](#tdr-009-실시간-통신-websocket)
11. [추가 결정: 로깅 프레임워크](#추가-결정-로깅-프레임워크)
12. [기술 스택 종합 요약](#기술-스택-종합-요약)
13. [리스크 레지스터](#리스크-레지스터)

---

## 1. 합의된 사항

Round 2 요구사항서에서 3개 도메인이 이미 합의한 기술:

| 항목 | 선택 | 합의 근거 |
|------|------|----------|
| **백엔드 언어** | Python 3.13 (async/await) | bit-trader 코드베이스 재사용, 전략 엔진 Python 종속 (pandas, pandas-ta, ccxt) |
| **대시보드 프레임워크** | Next.js 15 (App Router) | UX 감사 결론: Streamlit 한계 → SSR + 실시간 WS 필요 |
| **API 레이어** | FastAPI | ADR-003: Pydantic v2 네이티브, OpenAPI 자동 생성, WebSocket 내장 |
| **배포** | Docker + docker-compose | ADR: Mac caffeinate 탈피, 서비스 격리, 자동 재시작 |
| **상태 관리 (FE)** | Zustand | 대시보드 요구사항서: WS 스트림 상태에 최적, 보일러플레이트 최소 |
| **스타일링 (FE)** | TailwindCSS + shadcn/ui | 대시보드 요구사항서: 다크 테마 기본, 래피드 프로토타이핑 |
| **테이블 (FE)** | TanStack Table v8 | 대시보드 요구사항서: 가상 스크롤, 정렬/필터 내장 |
| **폼 (FE)** | React Hook Form + Zod | 대시보드 요구사항서: 전략 파라미터 유효성 검증 |
| **거래소 라이브러리** | ccxt (async) | bit-trader 기존 사용, 멀티 거래소 지원 내장 |
| **메트릭** | Prometheus + Grafana | 아키텍처 요구사항서 P1-A10: 13개 커스텀 메트릭 정의 완료 |

**추가 확인**: 이상의 10개 기술은 **토론 불필요**. 3개 도메인 모두 동의.

---

## TDR-001: 데이터베이스

### 배경

Round 1 Critical C2: SQLite 단일 writer 잠금 → 멀티 봇 동시 쓰기 불가.
교차 발견사항 #1: 데이터 계층이 전 도메인의 병목.

### 도메인별 의견

| 도메인 | 의견 |
|--------|------|
| **bot-developer** | PostgreSQL 16 + TimescaleDB 확장. hypertable로 candles 자동 파티셔닝, 연속 집계, 자동 보존 정책(2년). asyncpg 드라이버. (ADR-001) |
| **quant-expert** | TimescaleDB의 시간 범위 쿼리가 walk-forward 백테스트 데이터 분할에 필수. `get_candles_range(start, end)` 성능이 핵심. DuckDB를 분석 전용 보조 DB로 검토 요청. |
| **dashboard-designer** | DB 직접 접근 안 함 (API 서버 경유). 연속 집계(`candles_1d_summary`)가 대시보드 차트 초기 로딩 성능에 직접 영향. |

### 비교 분석

| 기준 | PostgreSQL + TimescaleDB | PostgreSQL only | DuckDB (보조) |
|------|-------------------------|-----------------|---------------|
| candles 쿼리 성능 | hypertable 자동 청크 → 시간 범위 쿼리 최적 | B-tree 인덱스 → 대량 데이터 시 성능 저하 | 컬럼 스토어 → 분석 쿼리 최적 |
| 연속 집계 | `CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous)` 자동 | 수동 materialized view + cron 리프레시 | N/A (별도 프로세스) |
| 보존 정책 | `add_retention_policy('candles', INTERVAL '2 years')` 자동 | 수동 DELETE cron | N/A |
| 멀티 writer | MVCC 완전 지원 | MVCC 완전 지원 | 단일 writer (SQLite 동일) |
| 배포 복잡도 | `timescale/timescaledb:latest-pg16` Docker 이미지 1개 | 기본 postgres 이미지 | 임베디드 (별도 서버 불요) |
| 추가 운영 비용 | TimescaleDB 익스텐션 설치만 추가 | 없음 | 별도 데이터 파이프라인 필요 |
| Walk-forward 지원 | 시간 범위 인덱스 최적 | 가능하나 수동 튜닝 필요 | 시간 범위 쿼리 매우 빠름 |

### 결정

**PostgreSQL 16 + TimescaleDB (OLTP) + DuckDB (OLAP 보조)** — 듀얼 DB 아키텍처

**메인 DB**: PostgreSQL 16 + TimescaleDB
- 실시간 트레이딩 데이터: candles, orders, positions, risk_state
- hypertable 자동 파티셔닝, 연속 집계, 보존 정책

**보조 분석 DB**: DuckDB (P1 백테스트 단계에서 도입)
- 백테스트 대량 분석: walk-forward 윈도우 스캔, 파라미터 최적화 그리드
- PostgreSQL → Parquet 익스포트 → DuckDB 로드 파이프라인
- 임베디드 모드 (별도 서버 불요), 컬럼 스토어로 분석 쿼리 10-100x 빠름

근거 (quant-expert 듀얼 DB 제안 수용):
1. **OLTP/OLAP 분리**: 실시간 트레이딩과 대량 분석이 서로 간섭하지 않음
2. **Parquet 중간 형식**: PostgreSQL → Parquet 익스포트가 데이터 아카이브 역할 겸임
3. **DuckDB의 파이프라인 부담이 제한적**: Parquet 파일 기반이므로 실시간 동기화 불필요. 백테스트 실행 전 1회 익스포트
4. **P1 백테스트와 동시 도입**: 백테스트 엔진 개발과 맞물려 자연스럽게 통합
5. DuckDB는 임베디드이므로 Docker 구성에 추가 서비스 없음

**데이터 흐름**:
```
[실시간] Exchange → Engine → PostgreSQL/TimescaleDB (OLTP)
[분석시] PostgreSQL → COPY TO Parquet → DuckDB (OLAP) → BacktestResult
```

### 리스크

| 리스크 | 영향 | 완화 |
|--------|------|------|
| TimescaleDB 버전 호환성 | 업그레이드 시 hypertable 마이그레이션 필요 | Docker 이미지 버전 고정, 릴리스 노트 확인 |
| 리소스 사용량 | PostgreSQL은 SQLite 대비 메모리 사용 증가 | `shared_buffers` 튜닝 (512MB 권장) |
| DuckDB-PostgreSQL 데이터 불일치 | Parquet 익스포트 시점과 실시간 데이터 차이 | 백테스트 실행 직전 익스포트 강제, 타임스탬프 검증 |
| Parquet 파일 관리 | 디스크 공간 증가 | 보존 정책 (최근 N개 익스포트만 유지) |

### 마이그레이션 경로

SQLite → PostgreSQL 일괄 마이그레이션 스크립트 (`scripts/migrate_to_pg.py`) 제공.
개발 환경에서는 `DataStore Protocol` 추상화로 SQLite 유지 가능.
DuckDB는 P1 백테스트 단계에서 `AnalyticsStore Protocol`로 추상화하여 도입.

---

## TDR-002: 백테스트 프레임워크

### 배경

Round 1 전략 감사 §8: bit-trader의 스크립트 기반 백테스트는 전체 in-sample 테스트만 가능.
전략 도메인 P1-S2: Walk-forward OOS 검증 + 리스크 조정 지표(Sharpe/Sortino/Calmar) 필수.

### 도메인별 의견

| 도메인 | 의견 |
|--------|------|
| **quant-expert** | Walk-forward 필수. vectorbt 벤치마크 참조하되 커스텀 엔진 선호. 슬리피지 모델링, equity curve 기반 MDD 계산 필요. 복잡도 **XL**. |
| **bot-developer** | 커스텀 엔진이 이벤트 버스/DataStore Protocol과 통합에 유리. 기존 bit-trader 로직 재사용 가능. `BacktestDataProvider` Protocol 제공. |
| **dashboard-designer** | 백테스트 결과 JSON 스키마 필요 (equity curve, trades, walk-forward windows). BacktestResult 뷰어 P2. |

### 비교 분석

| 기준 | 커스텀 이벤트 기반 | vectorbt | backtrader |
|------|-------------------|----------|------------|
| Walk-forward | 직접 구현 (전략팀 완전 제어) | `vbt.Portfolio.from_signals()` + 슬라이딩 윈도우 | `bt.Strategy` + 수동 슬라이딩 |
| 기존 로직 재사용 | bit-trader SignalGenerator 직접 호출 | pandas 벡터화 필요 (로직 변환) | cerebro 프레임워크 적응 필요 |
| 이벤트 버스 통합 | EventBus 그대로 사용 | 별도 벡터화 경로 | 별도 cerebro 경로 |
| 성능 (2년 4h) | 중간 (이벤트 루프) | 빠름 (벡터화) | 느림 (이벤트 루프 + Python 순수) |
| 슬리피지/비용 모델 | 직접 구현 (완전 제어) | 내장 (fee_pct + slippage) | 내장 (CommissionInfo) |
| 학습 곡선 | 낮음 (자체 코드) | 중간 (vectorbt API) | 높음 (backtrader 패턴) |

### 결정

**커스텀 이벤트 기반 백테스트 엔진**

근거:
1. bit-trader의 SignalGenerator/RiskManager 로직을 직접 호출하여 **실전과 동일한 경로** 검증
2. EventBus/DataStore Protocol과 자연스럽게 통합 (BacktestDataProvider로 데이터 소스만 교체)
3. Walk-forward 윈도우 로직은 전략 도메인이 **완전 제어**
4. vectorbt의 벡터화 성능이 매력적이나, 로직 변환 비용이 높고 유지보수 이중화 위험

**성능 보완**: 순수 Python 이벤트 루프의 성능 한계는 다음으로 완화:
- pandas 벡터 연산으로 지표 계산 (기존 방식 유지)
- 이벤트 루프는 시그널 판단 + 주문 시뮬레이션만 담당
- 2년 4h 데이터 ≈ 4,380 bars → 단일 전략 백테스트 **5초 이내** 목표

### 리스크

| 리스크 | 영향 | 완화 |
|--------|------|------|
| 개발 비용 XL | 전략 팀 4+ 주 소요 | P1 후반에 배치, P0 우선 완료 |
| look-ahead bias | 미래 데이터 참조 위험 | `BacktestDataProvider`가 시간 범위 엄격 제한 |
| 실전-백테스트 괴리 | 슬리피지/지연 시뮬레이션 부정확 | 페이퍼 트레이딩 결과와 백테스트 비교 검증 루틴 |

---

## TDR-003: ML/AI 파이프라인

### 배경

전략 도메인 P2-S2: ML 시그널 플러그인 아키텍처.
초기 모델: 다음 4h 가격 방향 분류 (up/down/neutral).

### 도메인별 의견

| 도메인 | 의견 |
|--------|------|
| **quant-expert** | LightGBM 초기 선택. ScorePlugin 프로토콜로 플러그인 아키텍처. Walk-forward 학습(6개월 학습 → 2개월 예측). OOS 정확도 > 55% 목표. |
| **bot-developer** | 모델 아티팩트 저장 경로 `data/models/{strategy_id}/{model_version}/`. Feature DataFrame 표준 스키마 필요. |
| **dashboard-designer** | ML 예측 패널: 플러그인별 점수 + 피처 중요도 바 차트 (P2). |

### 비교 분석

| 기준 | LightGBM | scikit-learn (RandomForest) | PyTorch (LSTM) |
|------|----------|-----------------------------|----------------|
| 학습 속도 | 매우 빠름 (GPU 불요) | 빠름 | 느림 (GPU 권장) |
| 추론 속도 | < 1ms | < 5ms | 10-50ms |
| 표 형태 데이터 | 최적 | 좋음 | 부적합 (시계열 특화) |
| 해석 가능성 | feature_importance 내장 | feature_importance 내장 | 블랙박스 (SHAP 필요) |
| 의존성 크기 | `lightgbm` (경량) | `scikit-learn` (표준) | `torch` (2GB+) |
| 과적합 제어 | early_stopping + L1/L2 | max_depth + n_estimators | dropout + weight_decay |

### 결정

**scikit-learn + LightGBM + optuna** (ML 파이프라인 3종 세트)

구성:
- **scikit-learn**: 전처리(StandardScaler, Pipeline), 평가(cross_val_score, classification_report), 베이스라인 모델(RandomForest)
- **LightGBM**: 메인 분류 모델 (3-class: up/down/neutral). tabular 데이터에 최적
- **optuna**: Bayesian 하이퍼파라미터 최적화. `n_trials=100`, TPE sampler, pruning 지원

근거:
1. 금융 시계열의 tabular feature에 가장 적합 (LightGBM)
2. 추론 < 1ms로 실시간 시그널 생성에 지장 없음
3. feature_importance 내장 → 대시보드 시각화 용이
4. Docker 이미지 크기 영향 최소 (PyTorch 대비 ~100x 경량)
5. Walk-forward 학습에서 빠른 재학습 주기 가능
6. **optuna**: GridSearch/RandomSearch 대비 효율적 탐색. Walk-forward 각 윈도우에서 최적 파라미터 자동 탐색 (quant-expert 제안)
7. **scikit-learn Pipeline**: feature 전처리 → 모델 학습 → 평가를 단일 파이프라인으로 캡슐화

**향후 확장**: P2 이후 시계열 패턴 인식이 필요하면 PyTorch 추가 검토.
ScorePlugin 프로토콜로 프레임워크 교체 가능.

### 리스크

| 리스크 | 영향 | 완화 |
|--------|------|------|
| 과적합 | OOS 성능 저하 | Walk-forward 검증 필수, 최소 5개 OOS 윈도우 통과 |
| Feature 엔지니어링 부담 | 수동 feature 설계 필요 | pandas-ta 지표를 표준 feature set으로 자동화 |
| 55% 정확도 미달 | ML 플러그인 무가치 | 가중치 0으로 비활성화 가능 (기존 기술적 분석만 사용) |
| optuna 과최적화 | 하이퍼파라미터 오버피팅 | Walk-forward OOS에서 최종 검증, 파라미터 안정성 모니터링 |

---

## TDR-004: 차트 라이브러리

### 배경

UX 감사: Streamlit 차트 한계. 금융 차트(캔들스틱) + 통계 차트(PnL/비교) 두 가지 요구.

### 도메인별 의견

| 도메인 | 의견 |
|--------|------|
| **dashboard-designer** | Lightweight Charts 4.x (금융 차트) + Recharts (통계/분석 차트). D3.js는 불필요. |
| **quant-expert** | 기술 지표 오버레이(EMA/BB/RSI/MACD) 필요. Walk-forward IS vs OOS 구간 색상 구분. Monte Carlo 히스토그램. Equity Curve + Drawdown 영역. |
| **bot-developer** | API 서버에서 OHLCV + 지표 데이터를 JSON으로 제공. 차트 라이브러리 선택은 대시보드 도메인 결정 존중. |

### 비교 분석

| 기준 | Lightweight Charts + Recharts | TradingView (상용) | D3.js |
|------|------------------------------|---------------------|-------|
| 금융 차트 | Lightweight Charts: 캔들+볼륨+마커, TradingView OSS | 완전한 차팅 플랫폼 | 직접 구현 (수백 시간) |
| 통계 차트 | Recharts: 라인/바/에어리어/레이더 | 제한적 | 모든 시각화 가능 |
| React 통합 | 두 라이브러리 모두 React 래퍼 존재 | iframe 임베드 | 직접 통합 필요 |
| 실시간 업데이트 | LW Charts: `update()` API | 내장 | 직접 구현 |
| 번들 크기 | LW ~50KB + Recharts ~70KB | 위젯 ~500KB | 트리 셰이킹 가능 |
| 비용 | 무료 (Apache 2.0) | 무료 티어 제한, 상용 유료 | 무료 (BSD) |
| 지표 오버레이 | LW Charts: `addLineSeries()` 수동 추가 | 100+ 내장 지표 | 직접 구현 |

### 결정

**Lightweight Charts 4.x (금융) + Recharts (통계)**

근거:
1. Lightweight Charts는 TradingView의 OSS 버전으로 금융 차트에 최적화
2. 캔들스틱 + 볼륨 + 거래 마커 + 실시간 업데이트 기본 지원
3. 기술 지표 오버레이는 `addLineSeries()`로 EMA/BB 라인 추가 가능 (P2)
4. RSI/MACD는 별도 패널로 분리 (LW Charts의 `createPriceLine()` + 별도 차트 인스턴스)
5. Recharts는 PnL 분석, 전략 비교, 매크로 게이지, 레이더 차트에 적합
6. D3.js의 표현력은 뛰어나지만 개발 비용 대비 우리 요구사항은 LW+Recharts로 충분

**D3.js 불필요 확인**: 히트맵(시그널 분석)은 Recharts의 커스텀 셀 렌더링 또는 CSS Grid로 구현 가능. 별도 D3.js 의존성 추가 불필요.

### 리스크

| 리스크 | 영향 | 완화 |
|--------|------|------|
| LW Charts 지표 오버레이 한계 | TradingView 상용 대비 지표 수 제한 | 핵심 5개(EMA, BB, RSI, MACD, Volume) 수동 구현. P2 범위 |
| LW Charts 커스텀 필요 | 특수 시각화(Walk-forward 구간 등) 추가 작업 | `addRectangle()` 플러그인 활용 |

---

## TDR-005: 이벤트 버스

### 배경

Round 1 H1: TradingLoop 13개 직접 의존성. 컴포넌트 디커플링 필수.
아키텍처 요구사항서 P0-A1: asyncio 기반 in-process 이벤트 버스 설계 완료.

### 도메인별 의견

| 도메인 | 의견 |
|--------|------|
| **bot-developer** | asyncio Queue 기반 in-process EventBus. 10개 이벤트 타입 정의 완료 (ADR-004). Redis는 P2 분산 확장 시 검토. |
| **quant-expert** | `SignalEvent` 발행으로 전략 엔진과 실행 엔진 분리. `MarketTickEvent` 수신으로 ATR 기반 실시간 손절 가능. 동의. |
| **dashboard-designer** | `API(WS)` 구독자가 EventBus 이벤트를 WebSocket 클라이언트에 push. 실시간 UX의 핵심 경로. 동의. |

### 비교 분석

| 기준 | asyncio EventBus | Redis Pub/Sub | Redis Streams | Kafka |
|------|-----------------|---------------|---------------|-------|
| 지연 | ~μs (in-process) | ~1ms (네트워크) | ~1ms | ~5ms |
| 내구성 | 없음 (프로세스 종료 시 유실) | 없음 (fire-and-forget) | 있음 (consumer group) | 있음 |
| 운영 복잡도 | 없음 | Redis 서버 1대 | Redis 서버 1대 | 클러스터 3+ 노드 |
| Docker 구성 | 추가 없음 | redis 컨테이너 추가 | redis 컨테이너 추가 | kafka+zookeeper 추가 |
| 적합 규모 | 단일 프로세스 (우리 현재) | 멀티 프로세스 | 멀티 프로세스 + 재생 | 마이크로서비스 |
| 에러 격리 | `try/except` per handler | 프로세스 격리 | 프로세스 격리 | 토픽별 격리 |

### 결정

**asyncio 기반 in-process EventBus**

근거:
1. traderj는 **단일 프로세스** 내 멀티 전략 (asyncio 태스크)로 운영
2. 이벤트 영속성이 필요한 것은 DB에 기록 (주문, 포지션, 리스크 상태)
3. 이벤트 자체의 내구성은 불필요 — 재시작 시 DB에서 상태 복원
4. 외부 MQ 추가 시 Docker 구성 복잡화 + 네트워크 지연 추가
5. μs 단위 지연으로 실시간 손절 (100ms 이내 반응) 보장

**확장 전략**: P2 멀티 프로세스 분산이 필요해지면:
- EventBus 인터페이스는 동일 유지
- 구현체만 `RedisEventBus`로 교체 (Protocol-First 설계의 이점)

### 리스크

| 리스크 | 영향 | 완화 |
|--------|------|------|
| 프로세스 재시작 시 이벤트 유실 | 진행 중 이벤트 소실 가능 | 주문/포지션은 DB 기록이 truth. 재시작 시 DB에서 복원 |
| 단일 프로세스 병목 | CPU-bound 작업이 이벤트 루프 차단 | 지표 계산은 ThreadPoolExecutor로 오프로드 |

---

## TDR-006: DB 드라이버 / ORM

### 배경

PostgreSQL 드라이버 선택: 직접 SQL vs ORM.
아키텍처 요구사항서 ADR-002에서 초안 결정.

### 도메인별 의견

| 도메인 | 의견 |
|--------|------|
| **bot-developer** | asyncpg 직접 사용 + Alembic 마이그레이션. bit-trader의 직접 SQL 패턴 유지. DataStore Protocol로 추상화. (ADR-002) |
| **quant-expert** | 백테스트 대량 쿼리(수만 rows) 성능 중요. ORM 오버헤드 회피 동의. 직접 SQL이 쿼리 최적화에도 유리. |
| **dashboard-designer** | API 서버의 Pydantic 모델이 DB 결과를 직접 매핑. ORM 유무와 무관 — API 응답 스키마만 명확하면 됨. |

### 비교 분석

| 기준 | asyncpg (직접 SQL) | SQLAlchemy 2.0 async | Tortoise ORM |
|------|-------------------|---------------------|--------------|
| 성능 | **3x faster** (벤치마크) | ORM 오버헤드 (쿼리 빌드 + 결과 매핑) | ORM 오버헤드 |
| SQL 제어 | 완전 — 쿼리 튜닝 직접 가능 | Core 표현식 또는 raw SQL 가능 | 제한적 |
| 타입 매핑 | 수동 (`Record → dataclass`) | 자동 (`Model` 인스턴스) | 자동 |
| 마이그레이션 | Alembic 별도 사용 | Alembic 통합 | Aerich |
| bit-trader 호환 | 패턴 동일 (기존 `store.py` 직접 SQL) | 패턴 변경 필요 | 패턴 변경 필요 |
| TimescaleDB 지원 | 완전 (raw SQL) | `create_hypertable()` 수동 호출 필요 | 미지원 |
| 학습 곡선 | 낮음 (SQL 숙련자) | 중간 (SQLAlchemy 2.0 패턴) | 낮음 (Django-like) |

### 결정

**asyncpg + Alembic (마이그레이션)**

> **팀 리더 권장**: SQLAlchemy 2.0 async + Alembic을 표준으로 고려.
> **결정**: asyncpg 직접 SQL 유지. 아래 근거로 팀 리더 권장안을 수용하지 않음.

근거:
1. **성능**: asyncpg는 SQLAlchemy async 대비 3x 빠름. 대량 candle 쿼리(수만 rows)에서 결정적 차이. DuckDB 듀얼 DB 도입으로 OLAP 부하는 분리되나, OLTP에서도 asyncpg의 낮은 오버헤드가 유리
2. **일관성**: bit-trader `store.py`의 직접 SQL 패턴 유지 → 마이그레이션 비용 최소
3. **투명성**: 금융 시스템에서 ORM이 생성하는 SQL보다 직접 SQL이 감사/디버깅에 유리
4. **TimescaleDB**: hypertable, 연속 집계, 보존 정책 등은 raw SQL로만 완전 제어 가능. SQLAlchemy에서는 `create_hypertable()` 등을 수동 raw SQL 호출해야 하므로 ORM의 이점이 반감
5. **DataStore Protocol**: 인터페이스 추상화로 구현체 교체 가능. 테스트에서 SQLite 유지
6. **보완**: SQL 인젝션 리스크는 asyncpg의 `$1, $2` 파라미터 바인딩 강제 + 코드 리뷰 규칙으로 완화. 타입 매핑 보일러플레이트는 `row_to_model()` 제네릭 헬퍼 1회 구현으로 해결

**Alembic 사용 방식**:
- 마이그레이션 파일만 Alembic으로 관리 (스키마 버전 관리)
- 런타임 쿼리는 asyncpg 직접 사용
- `env.py`에서 asyncpg 연결로 마이그레이션 실행

### 리스크

| 리스크 | 영향 | 완화 |
|--------|------|------|
| SQL 인젝션 위험 | 직접 SQL 작성 시 파라미터 바인딩 누락 가능 | asyncpg의 `$1, $2` 파라미터화 쿼리 강제. 문자열 포맷 금지 코드 리뷰 규칙 |
| 타입 매핑 보일러플레이트 | `Record → dataclass` 변환 코드 반복 | 헬퍼 함수 `row_to_dataclass()` 1회 구현 |
| 스키마 변경 추적 | Alembic 없이는 수동 관리 | Alembic autogenerate 비활성 (수동 마이그레이션만 사용) |

---

## TDR-007: 모노레포 구조

### 배경

traderj는 Python 백엔드 + Next.js 프론트엔드의 풀스택 프로젝트.
저장소 구조 결정 필요.

### 도메인별 의견

| 도메인 | 의견 |
|--------|------|
| **bot-developer** | 모노레포 선호. 공유 타입(API 스키마), docker-compose, CI/CD를 단일 레포에서 관리. Poetry (Python) + pnpm (Node.js) 병존. |
| **quant-expert** | 전략 코드가 백엔드와 밀접 결합 (같은 Python 패키지). 모노레포 동의. |
| **dashboard-designer** | OpenAPI 자동 생성 타입을 모노레포 내에서 공유하면 타입 동기화 비용 제거. 모노레포 동의. |

### 비교 분석

| 기준 | 모노레포 (단일) | 분리 레포 (2개) | Turborepo/Nx |
|------|----------------|----------------|-------------|
| 타입 공유 | 직접 import / OpenAPI codegen | Git submodule 또는 npm 패키지 배포 | 직접 import |
| CI/CD | 단일 workflow (변경 감지로 선택 빌드) | 각 레포별 독립 workflow | 빌드 캐시 + 변경 감지 |
| docker-compose | 루트에 1개 | 별도 infra 레포 또는 중복 | 루트에 1개 |
| 코드 리뷰 | 풀스택 변경을 단일 PR에서 검토 | 연관 변경이 2개 PR로 분산 | 단일 PR |
| 패키지 매니저 충돌 | Poetry + pnpm 공존 (각 디렉터리 독립) | 없음 (각 레포 독립) | 통합 관리 |
| 셋업 복잡도 | 낮음 | 중간 (동기화 필요) | 높음 (학습 곡선) |
| 확장성 | 팀 3명에 적합 | 팀 10명+ 시 유리 | 팀 5명+ 시 유리 |

### 결정

**모노레포 (단일 레포, 도구 없음)**

Turborepo/Nx는 도입하지 않는다. 근거:
1. 팀 규모 3명 — 빌드 캐시/변경 감지 자동화의 이점이 도구 학습 비용보다 작음
2. Python(Poetry) + Node.js(pnpm)는 디렉터리 분리만으로 충돌 없이 공존
3. CI/CD에서 `paths` 필터로 변경 감지 가능 (GitHub Actions 네이티브)

**프로젝트 구조** (dashboard-designer 제안 반영: 서비스별 최상위 분리):

```
traderj/
├── docker-compose.yml          # 전체 시스템 오케스트레이션
├── .github/workflows/          # CI/CD
│   ├── engine.yml              # Python lint+test+build (engine/ 변경 시)
│   ├── api.yml                 # Python lint+test+build (api/ 변경 시)
│   └── dashboard.yml           # Next.js lint+test+build (dashboard/ 변경 시)
│
├── shared/                     # 공유 코드 (Python 패키지)
│   ├── pyproject.toml          # 공유 패키지 (models, events, protocols)
│   ├── shared/
│   │   ├── models.py           # Candle, Order, Position, Signal, ...
│   │   ├── events.py           # MarketTickEvent, SignalEvent, ...
│   │   └── protocols.py        # DataStore, ExchangeClient, WebSocketStream
│   └── py.typed
│
├── engine/                     # 트레이딩 엔진 (Python)
│   ├── pyproject.toml          # Poetry (shared 패키지 의존)
│   ├── Dockerfile
│   ├── engine/
│   │   ├── config/             # 설정
│   │   ├── exchange/           # ccxt 래퍼, rate limiter, WebSocket
│   │   ├── data/               # PostgreSQL store, OHLCV collector
│   │   ├── strategy/           # 시그널 생성, 지표, MTF, 매크로
│   │   ├── execution/          # 주문 관리, 포지션 관리, 리스크
│   │   ├── loop/               # 이벤트 버스, 스케줄러, 상태 머신
│   │   └── notify/             # Telegram
│   └── tests/
│       ├── unit/
│       └── integration/
│
├── api/                        # FastAPI API 서버 (Python)
│   ├── pyproject.toml          # Poetry (shared 패키지 의존)
│   ├── Dockerfile
│   ├── api/
│   │   ├── routes/             # REST 엔드포인트
│   │   ├── ws/                 # WebSocket 핸들러
│   │   └── deps.py             # 의존성 주입
│   └── tests/
│
├── dashboard/                  # Next.js 프론트엔드
│   ├── package.json            # pnpm
│   ├── Dockerfile
│   ├── next.config.ts
│   ├── src/
│   │   ├── app/                # App Router 페이지
│   │   ├── components/         # UI 컴포넌트
│   │   ├── stores/             # Zustand 스토어
│   │   ├── lib/                # API 클라이언트, 유틸리티
│   │   └── types/              # 자동 생성 API 타입 (OpenAPI codegen)
│   └── tailwind.config.ts
│
├── scripts/                    # 유틸리티 스크립트
│   ├── migrate_to_pg.py        # SQLite → PostgreSQL 마이그레이션
│   └── generate_api_types.sh   # OpenAPI → TypeScript 타입 생성
│
├── migrations/                 # Alembic 마이그레이션
├── docs/                       # 기획/설계 문서
│
├── Makefile                    # 통합 명령어 래핑
└── .env.example                # 환경 변수 템플릿
```

**구조 변경 근거** (기존 `src/traderj/` 단일 Python 패키지 → 서비스별 분리):
1. **Docker 빌드 최적화**: 각 서비스가 자체 Dockerfile을 가져 독립 빌드 가능
2. **관심사 분리**: API 서버(요청/응답)와 엔진(트레이딩 루프)이 명확히 분리
3. **shared 패키지**: `models.py`, `events.py`, `protocols.py`를 별도 패키지로 추출. engine과 api가 각각 `dependency`로 참조
4. **CI/CD 독립성**: 3개 서비스 각각 독립적으로 테스트/빌드/배포 가능
5. **향후 분산 배포**: engine과 api를 별도 컨테이너로 스케일링 가능

**타입 동기화 방식**:
1. FastAPI가 OpenAPI 3.1 스키마 자동 생성 (`/openapi.json`)
2. `scripts/generate_api_types.sh`가 `openapi-typescript` CLI로 TypeScript 타입 생성
3. 생성된 타입이 `dashboard/src/types/api.ts`에 저장
4. CI에서 스키마 변경 시 자동 재생성 + 타입 불일치 감지

### 리스크

| 리스크 | 영향 | 완화 |
|--------|------|------|
| 레포 크기 증가 | clone/CI 시간 증가 | shallow clone + sparse checkout 옵션 |
| 패키지 매니저 혼동 | 루트에서 잘못된 매니저 실행 | `Makefile` 또는 `justfile`로 명령어 래핑 |

---

## TDR-008: 지표 계산 라이브러리

### 배경

bit-trader는 pandas-ta로 기술 지표(EMA, BB, RSI, MACD, ATR)를 계산 중.
전략 도메인 P0-S3: 멀티 타임프레임 지표 통합, P1-S1: 추가 지표(Stochastic, ADX, OBV, CMF).
Round 1 전략 감사: 0-100 임의 스케일링 상수 → Z-score 정규화 필요.

### 도메인별 의견

| 도메인 | 의견 |
|--------|------|
| **quant-expert** | pandas-ta 유지. TA-Lib 대비 C 컴파일 불요(Docker 호환), pandas 네이티브 체이닝. 단, 임의 스케일링 상수 제거 → 전 지표 Z-score 정규화 래퍼 필요. |
| **bot-developer** | `Indicator Protocol`로 지표 계산 추상화. pandas-ta 의존을 Protocol 뒤에 감춤. |
| **dashboard-designer** | 지표 값은 API JSON으로 수신. 오버레이 렌더링만 담당. |

### 비교 분석

| 기준 | pandas-ta | TA-Lib | 직접 구현 (numpy) |
|------|-----------|--------|-------------------|
| 지표 수 | 130+ | 150+ | 필요한 것만 |
| 설치 | `pip install pandas-ta` | C 라이브러리 + Python 래퍼 (Docker 빌드 복잡) | 의존성 없음 |
| pandas 통합 | 네이티브 (`df.ta.ema()`) | `talib.EMA(close)` (ndarray) | 직접 변환 |
| 성능 | 순수 Python (중간) | C 확장 (빠름) | numpy (빠름) |
| 유지보수 | 활발한 커뮤니티 | 업데이트 느림 | 직접 관리 |
| Docker 호환 | 문제 없음 | `ta-lib` C 빌드 필요 (Alpine 이슈 빈번) | 문제 없음 |

### 결정

**pandas-ta + 커스텀 Z-score 정규화 래퍼**

근거:
1. **bit-trader 호환**: 기존 pandas-ta 사용 패턴 유지 → 마이그레이션 비용 제로
2. **Docker 친화적**: TA-Lib의 C 빌드 이슈 회피 (Alpine/slim 이미지 호환)
3. **pandas 체이닝**: `df.ta.ema(length=20)` → DataFrame에 직접 컬럼 추가
4. **Z-score 래퍼**: 모든 지표를 `(value - rolling_mean) / rolling_std`로 정규화. bit-trader의 0-100 임의 스케일링 상수 완전 제거
5. **Indicator Protocol**: 향후 TA-Lib이나 직접 구현으로 교체 가능한 추상화 제공

**Z-score 정규화 규칙**:
- `lookback_window`: 지표별 기본값 제공 (RSI: 252, ATR: 126 등)
- 정규화 결과는 표준편차 단위 → ±2σ 이상이면 극단치 시그널
- ML feature로 직접 사용 가능 (스케일 통일)

### 리스크

| 리스크 | 영향 | 완화 |
|--------|------|------|
| pandas-ta 특정 지표 버그 | 잘못된 시그널 | 주요 5개 지표(EMA, BB, RSI, MACD, ATR)는 단위 테스트 + TA-Lib 결과와 교차 검증 |
| Z-score lookback 민감도 | lookback이 짧으면 과민, 길면 둔감 | 프리셋별 lookback 설정 + Walk-forward OOS에서 검증 |

---

## TDR-009: 실시간 통신 (WebSocket)

### 배경

대시보드 요구사항서: 21개 REST + 6개 WebSocket 채널 (ticker, bot_status, orders, positions, signals, alerts).
아키텍처 요구사항서 P0-A4: FastAPI WebSocket + 인증/재연결/하트비트.

### 도메인별 의견

| 도메인 | 의견 |
|--------|------|
| **bot-developer** | FastAPI 내장 WebSocket 사용. Socket.IO 불필요 (1:1 연결, 방 개념 불필요). 이벤트 버스 → WebSocket 브릿지로 실시간 push. |
| **dashboard-designer** | Native WebSocket 선호. Socket.IO는 번들 크기(~50KB) + 프로토콜 오버헤드. 지수 백오프 + jitter 재연결 전략 필요. 채널 구독/해지 프로토콜 제안. |
| **quant-expert** | 직접 관련 없음. 다만 MarketTickEvent가 WebSocket으로 대시보드에 실시간 전달되면 스트래티지 모니터링 UX 개선에 동의. |

### 비교 분석

| 기준 | Native WebSocket | Socket.IO | SSE (Server-Sent Events) |
|------|-----------------|-----------|--------------------------|
| 양방향 통신 | 완전 | 완전 | 서버→클라이언트만 |
| 자동 재연결 | 직접 구현 | 내장 | EventSource 내장 (제한적) |
| 프로토콜 오버헤드 | 없음 (raw WS) | Engine.IO 핸드셰이크 + 패킷 헤더 | HTTP 헤더 반복 |
| 번들 크기 (클라이언트) | 0KB (브라우저 내장) | ~50KB | 0KB (브라우저 내장) |
| 방(Room) 기능 | 직접 구현 (채널 패턴) | 내장 | N/A |
| FastAPI 통합 | 네이티브 (`@app.websocket()`) | python-socketio 추가 | StreamingResponse |
| 바이너리 전송 | 지원 | 지원 | 텍스트만 |

### 결정

**Native WebSocket (FastAPI 내장)**

근거:
1. **1:1 연결**: 단일 사용자 대시보드 → Socket.IO의 방/네임스페이스 기능 불필요
2. **번들 크기 제로**: 브라우저 내장 WebSocket API 사용, 추가 라이브러리 없음
3. **FastAPI 네이티브**: `@app.websocket("/ws")` 데코레이터로 즉시 사용
4. **이벤트 버스 브릿지**: EventBus 구독자가 WS 클라이언트에 직접 push
5. **SSE 제외**: 양방향 필요 (클라이언트 → 서버: 봇 제어, 구독 변경)

**재연결 전략** (dashboard-designer 제안 수용):
```
reconnectConfig = {
  maxRetries: 10,
  baseDelay: 1000,      // 1초
  maxDelay: 30000,      // 30초
  jitter: true,         // 무작위 지터
  backoffMultiplier: 2  // 지수 백오프
}
```

**메시지 프로토콜**:
```json
// 클라이언트 → 서버 (구독)
{ "type": "subscribe", "channels": ["ticker", "bot_status", "orders"] }

// 클라이언트 → 서버 (해지)
{ "type": "unsubscribe", "channels": ["orders"] }

// 서버 → 클라이언트 (데이터)
{ "type": "data", "channel": "ticker", "payload": { ... }, "ts": 1709337600000 }

// 양방향 (하트비트)
{ "type": "ping" } / { "type": "pong" }
```

**하트비트**: 30초 간격 ping/pong. 60초 무응답 시 연결 끊김 판정.

### 리스크

| 리스크 | 영향 | 완화 |
|--------|------|------|
| 재연결 로직 직접 구현 부담 | Socket.IO 대비 코드 추가 | 재연결 훅(`useWebSocket`) 1회 구현, 팀 공유 |
| 메시지 직렬화 수동 관리 | 프로토콜 불일치 가능 | Zod 스키마로 메시지 유효성 검증 (클라이언트), Pydantic 모델 (서버) |
| 프록시/방화벽 WS 차단 | 연결 불가 | HTTP 폴백은 구현하지 않음 (로컬 네트워크 전제). 포트 설정 가이드 제공 |

---

## 추가 결정: 로깅 프레임워크

### 배경

아키텍처 요구사항서 ADR-005: structlog vs loguru.
bit-trader는 현재 loguru 사용 중.

### 결정

**structlog** (JSON 렌더러)

근거 (ADR-005 그대로 확정):
1. **컨텍스트 바인딩**: `bind(strategy_id=X)` → 모든 하위 로그에 자동 포함. 멀티 전략 로깅의 핵심
2. **asyncio 호환**: loguru의 `contextualize()`는 thread-local → asyncio 태스크 간 격리 문제 가능
3. **마이그레이션 비용**: `logger.info("msg", key=val)` → `log.info("msg", key=val)` 수준으로 낮음
4. **Docker 로그 통합**: JSON stdout → Docker 로그 드라이버 → Grafana Loki (향후)

---

## 기술 스택 종합 요약

### 백엔드 (Python)

| 영역 | 기술 | 버전 | 결정 근거 |
|------|------|------|----------|
| 런타임 | Python | 3.13 | 합의 (bit-trader 호환) |
| 패키지 매니저 | Poetry | 2.x | bit-trader 호환 |
| 거래소 | ccxt | ^4.4 | 합의 (멀티 거래소 지원) |
| DB (OLTP) | PostgreSQL + TimescaleDB | 16 + latest | TDR-001 |
| DB (OLAP) | DuckDB | latest | TDR-001 (보조 분석) |
| DB 드라이버 | asyncpg | latest | TDR-006 |
| 마이그레이션 | Alembic | latest | TDR-006 |
| API 프레임워크 | FastAPI | latest | 합의 (ADR-003) |
| WebSocket | Native (FastAPI 내장) | - | TDR-009 |
| 이벤트 버스 | asyncio 커스텀 | - | TDR-005 |
| 로깅 | structlog | latest | 추가 결정 |
| 메트릭 | prometheus-client | latest | 합의 |
| 백테스트 | 커스텀 이벤트 기반 | - | TDR-002 |
| ML | scikit-learn + LightGBM + optuna | latest | TDR-003 |
| 지표 계산 | pandas-ta + Z-score 래퍼 | latest | TDR-008 |
| 알림 | python-telegram-bot | ^20 | bit-trader 호환 |

### 프론트엔드 (TypeScript)

| 영역 | 기술 | 버전 | 결정 근거 |
|------|------|------|----------|
| 프레임워크 | Next.js (App Router) | 15 | 합의 |
| 패키지 매니저 | pnpm | latest | 모노레포 호환 |
| 금융 차트 | Lightweight Charts | 4.x | TDR-004 |
| 통계 차트 | Recharts | latest | TDR-004 |
| 상태 관리 | Zustand | latest | 합의 |
| 스타일링 | TailwindCSS + shadcn/ui | latest | 합의 |
| 테이블 | TanStack Table | v8 | 합의 |
| 폼 | React Hook Form + Zod | latest | 합의 |
| API 타입 | openapi-typescript | latest | TDR-007 |

### 인프라

| 영역 | 기술 | 결정 근거 |
|------|------|----------|
| 컨테이너 | Docker + docker-compose | 합의 |
| DB 이미지 | timescale/timescaledb:latest-pg16 | TDR-001 |
| 모니터링 | Prometheus + Grafana | 합의 |
| CI/CD | GitHub Actions | 합의 |
| 레포 구조 | 모노레포 (도구 없음) | TDR-007 |

---

## 리스크 레지스터

전체 기술 결정에 대한 통합 리스크 요약:

| ID | 리스크 | 영향도 | 발생 확률 | TDR | 완화 전략 |
|----|--------|--------|----------|-----|----------|
| R1 | TimescaleDB 버전 호환성 | 중 | 낮 | 001 | Docker 이미지 버전 고정 |
| R2 | DuckDB-PostgreSQL 데이터 불일치 | 중 | 중 | 001 | 백테스트 실행 직전 익스포트 강제 |
| R3 | 커스텀 백테스트 개발 지연 | 높 | 중 | 002 | P1 후반 배치, P0 우선 |
| R4 | ML 모델 과적합 | 중 | 중 | 003 | Walk-forward 필수, 비활성화 가능 |
| R5 | optuna 하이퍼파라미터 오버피팅 | 중 | 중 | 003 | OOS 최종 검증, 파라미터 안정성 모니터링 |
| R6 | LW Charts 지표 오버레이 한계 | 낮 | 낮 | 004 | 핵심 5개만 수동 구현 |
| R7 | 이벤트 버스 프로세스 재시작 유실 | 중 | 낮 | 005 | DB가 truth, 재시작 시 복원 |
| R8 | asyncpg SQL 인젝션 | 높 | 낮 | 006 | 파라미터화 쿼리 강제, 코드 리뷰 |
| R9 | shared 패키지 버전 동기화 | 중 | 중 | 007 | Poetry workspace 의존성 + CI 통합 테스트 |
| R10 | pandas-ta 지표 버그 | 중 | 낮 | 008 | 주요 5개 지표 단위 테스트 + TA-Lib 교차 검증 |
| R11 | WebSocket 재연결 로직 구현 부담 | 낮 | 낮 | 009 | useWebSocket 훅 1회 구현 |

---

> **문서 상태**: Rev.1 — 팀 전원 의견 반영 완료. 팀 리더 최종 검토 대기
> **변경 이력**: Rev.0 초안 작성 → Rev.1: quant-expert(DuckDB, optuna, pandas-ta), dashboard-designer(WebSocket, 모노레포 구조), team-lead(SQLAlchemy 권장 대응) 반영
> **다음 단계**: 팀 리더 승인 후 Round 4에서 구체적 구현 계획(모듈별 작업 분할) 수립
