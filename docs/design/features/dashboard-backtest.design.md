# Dashboard Backtest Feature — 상세설계서

> 대시보드에서 과거 특정 기간의 백테스트를 실행하고 결과를 시각화하는 기능

## 1. 개요

### 1.1 목적
현재 백테스트는 CLI 스크립트(`scripts/run_backtest_*.py`)로만 실행 가능하다.
대시보드에서 직접 기간/전략을 선택하여 백테스트를 실행하고,
결과를 차트·테이블로 확인할 수 있는 UI를 제공한다.

### 1.2 핵심 요구사항
- 월 단위 또는 커스텀 기간 선택
- 전략 선택 (개별 프리셋, 전체 비교, AI Regime 모드)
- 비동기 실행 (백테스트는 5~30초 소요)
- 결과 저장 및 히스토리 조회
- 이퀴티 커브, 트레이드 목록, 메트릭스 시각화

---

## 2. 기간 선택 UX — 제안

### 2.1 방식 비교

| 방식 | 장점 | 단점 | 추천 |
|------|------|------|------|
| **A. 월 단위 드롭다운** | 직관적, 빠른 선택 | 유연성 낮음 | ✅ 기본 |
| **B. 캘린더 날짜 피커** | 완전 자유 기간 | 구현 복잡, 과도한 기간 선택 위험 | ✅ 고급 |
| **C. 슬라이더 (N일 전~오늘)** | 간편 | 과거 특정 구간 불가 | ❌ |

### 2.2 추천: 하이브리드 (A+B)

```
┌─────────────────────────────────────────────────┐
│  기간 선택                                       │
│                                                  │
│  [빠른 선택]                                      │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐   │
│  │ 1개월 │ │ 3개월 │ │ 6개월 │ │ 1년  │ │ 직접  │   │
│  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘   │
│                                                  │
│  ┌──────────────┐  ~  ┌──────────────┐          │
│  │ 2024-11-01   │     │ 2024-11-30   │          │
│  └──────────────┘     └──────────────┘          │
│                                                  │
│  ⓘ 최대 6개월, 최소 7일                           │
└─────────────────────────────────────────────────┘
```

**빠른 선택 버튼:**
- `1개월` → 직전 1개월 (예: 2월 1일~28일)
- `3개월` → 직전 3개월
- `6개월` → 직전 6개월
- `1년` → 직전 1년
- `직접` → 날짜 피커 활성화

**기간 제한:**
- 최소: 7일 (유의미한 트레이드 수 확보)
- 최대: 180일 (Upbit API 부하 + 실행 시간 제한)
- 기본값: 직전 1개월

---

## 3. 백테스트 모드

### 3.1 세 가지 모드

| 모드 | 설명 | 결과 |
|------|------|------|
| **단일 전략** | 선택한 1개 프리셋으로 전체 기간 실행 | 이퀴티 커브 + 메트릭스 |
| **전략 비교** | 8개 프리셋 전부 실행 후 비교 | 랭킹 테이블 + 오버레이 차트 |
| **AI Regime** | 주간 레짐 감지 → 자동 전략 선택 | 레짐 타임라인 + 전략별 구간 성과 |

### 3.2 UI 레이아웃

```
┌─────────────────────────────────────────────────┐
│  모드:  (●) 전략 비교  ( ) 단일 전략  ( ) AI Regime │
│                                                  │
│  [단일 전략 선택 시]                                │
│  전략: [▾ STR-002 Aggressive Trend (1h)     ]     │
│                                                  │
│  초기자금: [50,000,000] KRW                       │
│                                                  │
│  [  ▶ 백테스트 실행  ]                              │
└─────────────────────────────────────────────────┘
```

---

## 4. 비동기 실행 아키텍처

백테스트는 5~30초 소요되므로 HTTP 요청 내에서 완료할 수 없다.
**Job Queue 패턴**을 사용한다.

### 4.1 실행 흐름

```
Dashboard                    Next.js API             FastAPI Engine
   │                            │                        │
   │ POST /backtest/run         │                        │
   │ {mode, period, strategy}   │                        │
   │ ─────────────────────────> │ POST /backtest/run     │
   │                            │ ─────────────────────> │
   │                            │                        │ create job_id
   │                            │  { job_id, status }    │ start background task
   │  { job_id }                │ <───────────────────── │
   │ <───────────────────────── │                        │
   │                            │                        │
   │  [3초 폴링]                  │                        │
   │ GET /backtest/status/{id}  │                        │
   │ ─────────────────────────> │ GET /backtest/jobs/{id}│
   │                            │ ─────────────────────> │
   │                            │  { status, progress }  │
   │  { status: "running",      │ <───────────────────── │
   │    progress: "W2/5..." }   │                        │
   │ <───────────────────────── │                        │
   │                            │                        │
   │  [완료 시]                   │                        │
   │ GET /backtest/result/{id}  │                        │
   │ ─────────────────────────> │ GET /backtest/jobs/{id}│
   │                            │ ─────────────────────> │
   │                            │  { status: "done",     │
   │                            │    result: {...} }     │
   │ <───────────────────────── │ <───────────────────── │
```

### 4.2 Job 상태

```python
class BacktestJobStatus(StrEnum):
    PENDING   = "pending"    # 생성됨, 대기 중
    FETCHING  = "fetching"   # OHLCV 데이터 수집 중
    RUNNING   = "running"    # 백테스트 엔진 실행 중
    DONE      = "done"       # 완료
    FAILED    = "failed"     # 실패
```

### 4.3 동시 실행 제한
- 최대 1개 백테스트만 동시 실행 (단일 사용자 시스템)
- 이미 실행 중이면 409 Conflict 반환
- 완료된 Job은 메모리에 최대 20개 보관 (재시작 시 소멸)

---

## 5. API 설계

### 5.1 새 엔드포인트 (FastAPI)

**파일:** `api/routes/backtest.py`

```python
# 1. 백테스트 실행 요청
POST /api/v1/backtest/run
Body: {
    "mode": "compare" | "single" | "ai_regime",
    "start_date": "2024-11-01",
    "end_date": "2024-11-30",
    "strategy_id": "STR-002",       # mode=single 일 때만
    "initial_balance": 50000000,    # optional, default 50M
}
Response: { "job_id": "bt-20240301-abc123", "status": "pending" }

# 2. Job 상태 조회
GET /api/v1/backtest/jobs/{job_id}
Response: {
    "job_id": "bt-...",
    "status": "running",
    "progress": "전략 3/8 실행 중 (STR-003)",
    "started_at": "2024-03-01T10:00:00",
    "elapsed_sec": 12.5
}

# 3. 결과 조회 (완료 후)
GET /api/v1/backtest/jobs/{job_id}   # status=done 일 때 result 포함
Response: {
    "job_id": "bt-...",
    "status": "done",
    "result": {
        "mode": "compare",
        "period": { "start": "2024-11-01", "end": "2024-11-30" },
        "market": { "start_price": 98112000, "end_price": 133701000, "change_pct": 36.3 },
        "strategies": [
            {
                "strategy_id": "STR-002",
                "name": "Aggressive Trend (1h)",
                "metrics": { "total_return_pct", "total_trades", "win_rate_pct", "sharpe_ratio", "max_drawdown_pct", "profit_factor", ... },
                "equity_curve": [ { "time": "2024-11-01T00:00", "equity": 50000000 }, ... ],
                "trades": [ { "entry_time", "exit_time", "pnl_pct", "exit_reason", ... }, ... ]
            },
            ...
        ],
        "ai_regime": {   # mode=ai_regime 일 때만
            "weekly_decisions": [ { "week": 1, "start": "11/01", "end": "11/07", "regime": "bear_trend_high_vol", "strategy": "STR-007" }, ... ],
            "regime_distribution": { "bull_trend_high_vol": 3, ... },
            "aggregate_metrics": { ... }
        },
        "ranking": [ "STR-008", "STR-003", ... ]  # mode=compare 일 때
    }
}

# 4. Job 목록 (히스토리)
GET /api/v1/backtest/jobs?limit=10
Response: {
    "jobs": [
        { "job_id", "mode", "period", "status", "created_at", "summary": { "best_strategy", "best_return_pct" } },
        ...
    ]
}

# 5. Job 취소
DELETE /api/v1/backtest/jobs/{job_id}
Response: { "cancelled": true }
```

### 5.2 Dashboard API Proxy

**파일:** 기존 `dashboard/src/app/api/engine/[...path]/route.ts` 활용
- `/api/engine/backtest/*` → `/api/v1/backtest/*` 자동 프록시

---

## 6. 백엔드 구현

### 6.1 파일 구조

```
api/routes/backtest.py          # FastAPI 라우터 (5개 엔드포인트)
engine/backtest/                # (신규 패키지)
  __init__.py
  job_manager.py                # BacktestJobManager (in-memory job queue)
  runners.py                    # 3개 모드별 실행 함수
  schemas.py                    # Request/Response Pydantic 모델
```

### 6.2 BacktestJobManager

```python
@dataclass
class BacktestJob:
    job_id: str
    mode: str                    # "compare" | "single" | "ai_regime"
    config: dict                 # 실행 설정
    status: BacktestJobStatus
    progress: str                # 진행 상황 메시지
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    result: dict | None          # 완료 시 결과
    error: str | None            # 실패 시 에러 메시지
    task: asyncio.Task | None    # 실행 중인 태스크 참조

class BacktestJobManager:
    """In-memory job manager. 단일 사용자이므로 DB 불필요."""

    _jobs: dict[str, BacktestJob]   # job_id → Job
    _current: str | None            # 현재 실행 중 job_id
    MAX_HISTORY = 20

    async def submit(self, mode, config) -> BacktestJob:
        """새 백테스트 Job 생성 및 백그라운드 태스크 시작"""

    def get(self, job_id) -> BacktestJob | None:
        """Job 상태 조회"""

    def list_jobs(self, limit=10) -> list[BacktestJob]:
        """최근 Job 목록"""

    async def cancel(self, job_id) -> bool:
        """실행 중 Job 취소"""
```

### 6.3 Runner 함수 (재사용)

기존 `BacktestEngine`, `SignalGenerator`, `compute_metrics` 를 그대로 재사용.
OHLCV 수집은 `scripts/run_backtest_ai_period.py`의 Upbit 직접 호출 패턴 사용.

```python
# runners.py

async def run_single(job: BacktestJob, update_progress: Callable) -> dict:
    """단일 전략 백테스트"""
    # 1. OHLCV fetch (Upbit API via httpx)
    # 2. BacktestEngine(SignalGenerator(preset)).run(ohlcv_by_tf)
    # 3. compute_metrics() → return result dict

async def run_compare(job: BacktestJob, update_progress: Callable) -> dict:
    """전략 비교 (8개 프리셋 순차 실행)"""
    # for i, preset in enumerate(STRATEGY_PRESETS):
    #     update_progress(f"전략 {i+1}/8 실행 중 ({preset.name})")
    #     run BacktestEngine...
    # rank by total_return_pct → return comparison

async def run_ai_regime(job: BacktestJob, update_progress: Callable) -> dict:
    """AI Regime 모드 (주간 레짐 감지 → 전략 자동 선택)"""
    # 기존 run_backtest_ai_period.py 로직 재사용
    # + 8개 프리셋 비교도 포함
```

---

## 7. 대시보드 UI 설계

### 7.1 새 페이지: `/backtest`

기존 네비게이션에 "Backtest" 탭 추가 (Analytics 옆).

### 7.2 페이지 구조

```
┌──────────────────────────────────────────────────────────────┐
│  TopNav: [Dashboard] [Analytics] [Backtest] [AI Tuner] ...   │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─ 백테스트 설정 ─────────────────────────────────────────┐  │
│  │                                                        │  │
│  │  기간:  [1M] [3M] [6M] [1Y] [직접]                      │  │
│  │         2024-11-01 ~ 2024-11-30  (30일)                │  │
│  │                                                        │  │
│  │  모드:  (●) 전략 비교  ( ) 단일 전략  ( ) AI Regime      │  │
│  │                                                        │  │
│  │  초기자금: 50,000,000 KRW                               │  │
│  │                                                        │  │
│  │  [ ▶ 백테스트 실행 ]            [ ⟳ 히스토리 ]            │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌─ 실행 중 (표시: 실행 시에만) ─────────────────────────────┐  │
│  │  ████████████░░░░░░  전략 5/8 실행 중 (STR-005)  12.3s  │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌─ 결과 ─────────────────────────────────────────────────┐  │
│  │                                                        │  │
│  │  ┌─ 시장 요약 ──────────────────────────────────────┐  │  │
│  │  │  BTC/KRW  98,112,000 → 133,701,000  (+36.3%)   │  │  │
│  │  │  기간: 2024-11-01 ~ 2024-11-30 (30일)           │  │  │
│  │  └──────────────────────────────────────────────────┘  │  │
│  │                                                        │  │
│  │  ┌─ 이퀴티 커브 차트 ───────────────────────────────┐  │  │
│  │  │  (Lightweight Charts - Line Series)              │  │  │
│  │  │  8개 전략 오버레이 또는 단일 전략 + BTC 가격      │  │  │
│  │  │  ▪ 범례 클릭으로 전략별 토글                       │  │  │
│  │  └──────────────────────────────────────────────────┘  │  │
│  │                                                        │  │
│  │  ┌─ 전략 랭킹 테이블 ──────────────────────────────┐  │  │
│  │  │  #  전략           수익률  거래  승률  Sharpe  MDD │  │  │
│  │  │  1  STR-008 Bear   +0.12%   1  100%   ...   0.2%│  │  │
│  │  │  2  STR-003 Hybrid +0.01%   8   62%   ...   0.8%│  │  │
│  │  │  ...                                             │  │  │
│  │  └──────────────────────────────────────────────────┘  │  │
│  │                                                        │  │
│  │  [AI Regime 모드일 때 추가]                              │  │
│  │  ┌─ 레짐 타임라인 ─────────────────────────────────┐  │  │
│  │  │  W1 ■■■■  bear_trend    → STR-007              │  │  │
│  │  │  W2 ■■■■  bull_trend    → STR-002              │  │  │
│  │  │  W3 ■■■■  bull_trend    → STR-002              │  │  │
│  │  │  ...                                            │  │  │
│  │  └──────────────────────────────────────────────────┘  │  │
│  │                                                        │  │
│  │  ┌─ 트레이드 목록 (접이식) ─────────────────────────┐  │  │
│  │  │  ▾ 전체 18건 (9승 9패)                           │  │  │
│  │  │  #1  11/08 14:00  BUY → SELL  +0.12%  signal   │  │  │
│  │  │  #2  11/08 18:00  BUY → SELL  -0.23%  stop_loss│  │  │
│  │  │  ...                                            │  │  │
│  │  └──────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌─ 히스토리 (접이식) ─────────────────────────────────────┐  │
│  │  ▾ 최근 백테스트 5건                                    │  │
│  │  03/24 전략비교 11월 → Best: STR-008 +0.12%           │  │
│  │  03/23 AI Regime 10월 → AI: -0.5%, Best: STR-001 +2% │  │
│  │  ...                                                   │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 7.3 결과 카드 구성 (모드별)

| 구성 요소 | 단일 전략 | 전략 비교 | AI Regime |
|-----------|----------|----------|-----------|
| 시장 요약 | ✅ | ✅ | ✅ |
| 이퀴티 커브 | 1개 라인 + BTC 가격 | 8개 오버레이 | AI + Best Fixed + BTC |
| 메트릭스 테이블 | 1행 상세 | 8행 랭킹 | AI vs Best vs 전체 |
| 레짐 타임라인 | ❌ | ❌ | ✅ |
| 트레이드 목록 | ✅ (상세) | ❌ (너무 많음) | ✅ (AI 모드만) |

---

## 8. 컴포넌트 설계

### 8.1 신규 파일

```
dashboard/src/app/backtest/
  page.tsx                     # 메인 페이지
dashboard/src/components/backtest/
  BacktestForm.tsx             # 기간/모드/전략 선택 폼
  BacktestProgress.tsx         # 진행 상황 프로그레스 바
  BacktestResult.tsx           # 결과 컨테이너 (모드별 분기)
  EquityCurveChart.tsx         # 이퀴티 커브 (lightweight-charts)
  StrategyRankingTable.tsx     # 전략 비교 테이블
  RegimeTimeline.tsx           # AI Regime 주간 타임라인
  TradeList.tsx                # 트레이드 목록 (접이식)
  BacktestHistory.tsx          # 과거 백테스트 히스토리
```

### 8.2 상태 관리

```typescript
// page.tsx 내부 상태
interface BacktestState {
  // 설정
  mode: "compare" | "single" | "ai_regime";
  startDate: string;          // YYYY-MM-DD
  endDate: string;
  strategyId: string | null;  // mode=single 일 때
  initialBalance: number;

  // 실행
  jobId: string | null;
  status: "idle" | "pending" | "fetching" | "running" | "done" | "failed";
  progress: string;
  elapsedSec: number;

  // 결과
  result: BacktestResultData | null;

  // 히스토리
  history: BacktestJobSummary[];
}
```

### 8.3 폴링 로직

```typescript
// 3초 간격 폴링 (실행 중일 때만)
useEffect(() => {
  if (!jobId || status === "done" || status === "failed") return;

  const interval = setInterval(async () => {
    const res = await fetch(`/api/engine/backtest/jobs/${jobId}`);
    const data = await res.json();

    setStatus(data.status);
    setProgress(data.progress);

    if (data.status === "done") {
      setResult(data.result);
      clearInterval(interval);
    }
    if (data.status === "failed") {
      setError(data.error);
      clearInterval(interval);
    }
  }, 3000);

  return () => clearInterval(interval);
}, [jobId, status]);
```

---

## 9. 이퀴티 커브 차트 설계

### 9.1 라이브러리
기존 CandlestickChart에서 사용 중인 `lightweight-charts` 재사용.
LineSeries로 이퀴티 커브 표시.

### 9.2 전략 비교 모드 차트

```typescript
// 8개 전략을 각각 다른 색상의 LineSeries로 추가
const STRATEGY_COLORS = {
  "STR-001": "#6366f1",  // indigo
  "STR-002": "#f59e0b",  // amber
  "STR-003": "#10b981",  // emerald
  "STR-004": "#ef4444",  // red
  "STR-005": "#8b5cf6",  // violet
  "STR-006": "#06b6d4",  // cyan
  "STR-007": "#f97316",  // orange
  "STR-008": "#ec4899",  // pink
};

// BTC 가격은 우측 Y축에 별도 스케일로 표시 (회색 점선)
// 범례 클릭으로 개별 전략 토글 가능
```

### 9.3 AI Regime 모드 차트
- AI 이퀴티 (파란 실선, 굵게)
- Best Fixed 이퀴티 (녹색 점선)
- BTC 가격 (회색, 우측 Y축)
- 레짐 구간을 배경색으로 표시 (bull=연초록, bear=연빨강, ranging=연회색)

---

## 10. 네비게이션 변경

### 10.1 TopNav / BottomNav 탭 추가

현재 순서: Dashboard → Analytics → AI Tuner → Control → Settings
변경 순서: Dashboard → Analytics → **Backtest** → AI Tuner → Control → Settings

```typescript
// TopNav, BottomNav에 추가
{
  href: "/backtest",
  label: "Backtest",
  icon: "M3 3v18h18M9 17V9m4 8V5m4 8v-4"  // 바 차트 아이콘
}
```

---

## 11. 데이터 제한 및 안전장치

| 제한 항목 | 값 | 이유 |
|-----------|-----|------|
| 최대 기간 | 180일 | Upbit API 요청량 + 실행 시간 |
| 최소 기간 | 7일 | 유의미한 트레이드 수 |
| 동시 실행 | 1개 | 단일 사용자 + CPU 부하 |
| Job 히스토리 | 20개 | 메모리 절약 |
| 실행 타임아웃 | 120초 | 무한 대기 방지 |
| Upbit API 호출 간격 | 0.15초 | Rate limit 준수 |
| 워밍업 기간 | 60일 | EMA 등 지표 안정화 |

---

## 12. 에러 처리

| 상황 | 처리 |
|------|------|
| Upbit API 실패 | 3회 재시도 → 실패 시 Job 에러 |
| 기간 내 캔들 부족 | "데이터 부족" 에러 메시지 |
| 이미 실행 중 | 409 Conflict + "진행 중인 백테스트가 있습니다" |
| 타임아웃 (120초) | Job 자동 취소 + "시간 초과" 에러 |
| 전략 ID 잘못됨 | 400 Bad Request + 유효 전략 목록 |

---

## 13. 구현 순서

### Phase 1: 백엔드 API (3개 파일)
1. `engine/backtest/schemas.py` — Request/Response 모델
2. `engine/backtest/job_manager.py` — Job 관리자
3. `engine/backtest/runners.py` — 3개 모드 실행 함수
4. `api/routes/backtest.py` — 5개 엔드포인트
5. `api/main.py` — 라우터 등록

### Phase 2: 대시보드 기본 UI (4개 파일)
1. `dashboard/src/app/backtest/page.tsx` — 메인 페이지
2. `dashboard/src/components/backtest/BacktestForm.tsx` — 설정 폼
3. `dashboard/src/components/backtest/BacktestProgress.tsx` — 프로그레스
4. 네비게이션 탭 추가 (TopNav, BottomNav)

### Phase 3: 결과 시각화 (4개 파일)
1. `StrategyRankingTable.tsx` — 전략 비교 테이블
2. `EquityCurveChart.tsx` — 이퀴티 커브 차트
3. `TradeList.tsx` — 트레이드 목록
4. `RegimeTimeline.tsx` — AI Regime 타임라인

### Phase 4: 히스토리 + 마무리
1. `BacktestHistory.tsx` — 히스토리 UI
2. 모바일 반응형 최적화
3. 테스트 및 배포

---

## 14. 예상 소요 및 리스크

### 공수
- Phase 1 (백엔드): 파일 4개 + 라우터 등록
- Phase 2 (기본 UI): 파일 4개
- Phase 3 (시각화): 파일 4개
- Phase 4 (마무리): 파일 1개 + 반응형

### 리스크
| 리스크 | 대응 |
|--------|------|
| Upbit API rate limit | 기존 0.15초 간격 유지, 최대 180일 제한 |
| 장기 백테스트 메모리 | 이퀴티 커브 데이터포인트 다운샘플링 (1일 1점으로) |
| Fly.io CPU 제한 | 타임아웃 120초, 동시 1개 제한 |
| 차트 렌더링 성능 | 8개 전략 × 180일 = ~1,440 포인트 (lightweight-charts 처리 가능) |

---

## 15. 도움말 연동

기존 helpData.ts에 백테스트 관련 항목 추가:

| ID | Term | TermKo | Category |
|----|------|--------|----------|
| backtest | Backtest | 백테스트 | concept |
| backtest-compare | Strategy Compare | 전략 비교 | process |
| backtest-ai-regime | AI Regime Backtest | AI 레짐 백테스트 | process |
| equity-curve | Equity Curve | 자산 곡선 | metric |
| backtest-period | Backtest Period | 백테스트 기간 | concept |

---

## 16. 결과 영구 저장 및 캔들 캐시

### 16.1 캔들 데이터 캐시

백테스트 시 수집한 OHLCV 캔들을 DB에 캐시하여 같은 기간 재실행 시 Upbit API 호출을 생략한다.

**DB 스키마:**

```sql
CREATE TABLE IF NOT EXISTS backtest_candle_cache (
    symbol      TEXT NOT NULL,          -- "BTC/KRW"
    timeframe   TEXT NOT NULL,          -- "1h", "4h", "1d"
    timestamp   INTEGER NOT NULL,       -- Unix ms
    open        REAL NOT NULL,
    high        REAL NOT NULL,
    low         REAL NOT NULL,
    close       REAL NOT NULL,
    volume      REAL NOT NULL,
    PRIMARY KEY (symbol, timeframe, timestamp)
);
CREATE INDEX IF NOT EXISTS idx_bcc_range
    ON backtest_candle_cache(symbol, timeframe, timestamp);
```

**캐시 로직:**

```python
class CandleCache:
    """OHLCV 캔들 캐시. 없는 구간만 Upbit에서 보충."""

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        start_ms: int,
        end_ms: int,
    ) -> pd.DataFrame:
        # 1. DB에서 [start_ms, end_ms] 구간 캔들 조회
        cached = await self._load_from_db(symbol, timeframe, start_ms, end_ms)

        # 2. 누락 구간 계산
        gaps = self._find_gaps(cached, start_ms, end_ms, timeframe)

        # 3. 누락 구간만 Upbit API에서 fetch
        for gap_start, gap_end in gaps:
            fresh = await fetch_ohlcv_paginated(exchange, symbol, timeframe, gap_start, gap_end)
            await self._save_to_db(symbol, timeframe, fresh)
            cached = pd.concat([cached, fresh])

        # 4. 정렬 후 반환
        return cached.sort_values("timestamp").drop_duplicates("timestamp")
```

**효과:**
- 첫 실행: Upbit에서 전체 fetch (5~10초) → DB에 저장
- 재실행: DB에서 즉시 로드 (< 0.5초)
- 부분 겹침: 없는 구간만 보충 fetch

### 16.2 백테스트 결과 영구 저장

기존 `backtest_results` 테이블을 활용하되, 대시보드 백테스트 전용 메타데이터를 추가한다.

**확장 스키마:**

```sql
-- 기존 backtest_results 테이블에 컬럼 추가
ALTER TABLE backtest_results ADD COLUMN source TEXT DEFAULT 'script';
    -- 'script': CLI 스크립트 실행
    -- 'dashboard': 대시보드에서 실행
    -- 'tuner': 튜너 최적화 과정에서 실행

ALTER TABLE backtest_results ADD COLUMN mode TEXT;
    -- 'single', 'compare', 'ai_regime'

ALTER TABLE backtest_results ADD COLUMN period_start TEXT;
    -- '2024-11-01'

ALTER TABLE backtest_results ADD COLUMN period_end TEXT;
    -- '2024-11-30'

ALTER TABLE backtest_results ADD COLUMN job_id TEXT;
    -- 대시보드 Job ID 참조

ALTER TABLE backtest_results ADD COLUMN market_json TEXT;
    -- {"start_price": 98112000, "end_price": 133701000, "change_pct": 36.3}
```

**저장 시점:**
- Job 완료 시 `runners.py`에서 자동 저장
- 전략 비교 모드: 8개 결과 + 1개 요약 = 9건 저장
- AI Regime 모드: AI 종합 결과 + 8개 비교 = 9건 저장
- 단일 전략: 1건 저장

**API 확장:**

```python
# 저장된 백테스트 결과 조회
GET /api/v1/backtest/results
Params: {
    "source": "dashboard",          # optional: script|dashboard|tuner
    "mode": "compare",              # optional
    "strategy_id": "STR-002",       # optional
    "period_start": "2024-11-01",   # optional
    "period_end": "2024-11-30",     # optional
    "limit": 20
}
Response: {
    "results": [
        {
            "id": "bt-result-xxx",
            "strategy_id": "STR-002",
            "mode": "compare",
            "period": { "start": "2024-11-01", "end": "2024-11-30" },
            "market": { "start_price": 98112000, ... },
            "metrics": { "total_return_pct": -0.36, ... },
            "created_at": "2026-03-24T20:00:00"
        },
        ...
    ]
}
```

---

## 17. AI Tuner 연동 — 백테스트 결과 → 파라미터 최적화

### 17.1 개념

```
┌──────────────────┐        ┌────────────────────┐        ┌──────────────────┐
│  Dashboard        │        │  Analysis &         │        │  AI Tuner         │
│  Backtest         │───────>│  Recommendation     │───────>│  Pipeline         │
│                   │ 결과   │                     │ 제안   │                   │
│  - 기간별 성과     │ 저장   │  - 최적 전략 식별    │        │  - Optuna 최적화   │
│  - 레짐별 성과     │        │  - 약점 진단        │        │  - 파라미터 적용    │
│  - 전략 비교      │        │  - 파라미터 제안     │        │  - 안전 검증       │
└──────────────────┘        └────────────────────┘        └──────────────────┘
```

### 17.2 세 가지 최적화 액션

백테스트 결과에서 도출할 수 있는 3가지 액션:

#### Action A: 전략 프리셋 전환 (즉시 적용)

```
백테스트 결과 → "STR-003이 현재 시장에서 가장 좋은 성과"
→ [전략 전환] 버튼 클릭
→ POST /api/v1/strategy/switch {strategy_id: "STR-003"}
→ 라이브 엔진에 즉시 적용
```

| 항목 | 내용 |
|------|------|
| 대상 | 단일 전략 또는 전략 비교 결과 |
| 난이도 | 낮음 (기존 API 재사용) |
| 위험도 | 낮음 (프리셋 전환은 이미 구현됨) |
| UI | 랭킹 테이블에서 "이 전략으로 전환" 버튼 |

#### Action B: 레짐-전략 매핑 업데이트 (Tier 3, 승인 필요)

```
AI Regime 백테스트 결과 분석:
  bear_trend_high_vol → STR-007 (현재 매핑) → -0.5%
  bear_trend_high_vol → STR-008 (백테스트 최고) → +0.3%

→ "레짐 매핑 최적화" 버튼 클릭
→ POST /api/v1/tuning/optimize-regime-map
→ 분석 결과 표시 + 승인 요청
→ 사용자 승인 후 REGIME_PRESET_MAP 업데이트
```

| 항목 | 내용 |
|------|------|
| 대상 | AI Regime 백테스트 결과 |
| 난이도 | 중간 |
| 위험도 | 중간 (Tier 3 → 수동 승인 필수) |
| 분석 | 레짐별 실제 매핑 vs 최적 매핑 비교 테이블 |

**분석 로직:**

```python
def analyze_regime_mapping(ai_result: dict, compare_result: dict) -> list[RegimeMapSuggestion]:
    """
    AI Regime 백테스트 + 전체 전략 비교 결과를 교차 분석하여
    레짐-전략 매핑 개선안을 도출한다.
    """
    suggestions = []
    for week in ai_result["weekly_decisions"]:
        regime = week["regime"]
        current_strategy = REGIME_PRESET_MAP[regime]
        # 해당 주간의 각 전략 성과를 비교
        best_strategy = find_best_for_period(compare_result, week["start"], week["end"])

        if best_strategy != current_strategy:
            suggestions.append(RegimeMapSuggestion(
                regime=regime,
                current=current_strategy,
                suggested=best_strategy,
                current_return=week["return_pct"],
                suggested_return=best_return_pct,
                confidence=calculate_confidence(sample_count, return_diff),
            ))
    return suggestions
```

**UI (결과 화면에 표시):**

```
┌─ 레짐 매핑 최적화 제안 ─────────────────────────────────────┐
│                                                              │
│  레짐                 현재 매핑        제안 매핑      개선폭   │
│  ──────────────────── ─────────────── ────────────── ──────  │
│  bear_trend_high_vol  STR-007 (-0.5%) STR-008 (+0.3%) +0.8% │
│  ranging_high_vol     STR-003 (+0.01%) STR-005 (+0.1%) +0.09%│
│                                                              │
│  ⚠ Tier 3 변경: 승인이 필요합니다                              │
│                                                              │
│  [ 매핑 업데이트 요청 ]          [ 무시 ]                      │
└──────────────────────────────────────────────────────────────┘
```

#### Action C: 파라미터 튜닝 트리거 (Tuner Pipeline 활용)

```
백테스트 결과 → "STR-002가 bull 구간에서 수익률 부진"
→ [파라미터 최적화] 버튼 클릭
→ POST /api/v1/tuning/optimize-from-backtest
  {
    strategy_id: "STR-002",
    backtest_result_id: "bt-result-xxx",
    period_start: "2024-11-01",
    period_end: "2024-11-30",
    tier: "tier_1"
  }
→ 해당 기간의 캔들 데이터 + 백테스트 결과를 Tuner Pipeline에 전달
→ Optuna가 해당 기간에 최적화된 파라미터를 탐색
→ 결과를 대시보드에 표시 + 적용 여부 선택
```

| 항목 | 내용 |
|------|------|
| 대상 | 특정 전략의 특정 기간 성과 |
| 난이도 | 높음 (Tuner Pipeline 확장) |
| 위험도 | 낮음 (Walk-Forward 검증 + Guardrails) |
| 소요 시간 | 30~120초 (Optuna 50 trials) |

**흐름:**

```
Dashboard                          Tuner Pipeline
   │                                    │
   │ POST /tuning/optimize-from-backtest│
   │ ──────────────────────────────────>│
   │                                    │
   │                                    │ 1. 캔들 캐시에서 기간 데이터 로드
   │                                    │ 2. 백테스트 결과에서 현재 메트릭스 확인
   │                                    │ 3. HybridOptimizer.optimize()
   │                                    │    - Optuna 50 trials
   │                                    │    - 각 trial → BacktestEngine 실행
   │                                    │    - Walk-Forward 검증
   │                                    │ 4. Guardrails 검증
   │                                    │ 5. LLM 진단 + 승인 (optional)
   │                                    │
   │  { optimization_result }           │
   │ <──────────────────────────────────│
   │                                    │
   │  사용자가 "적용" 클릭               │
   │ POST /tuning/apply                 │
   │ ──────────────────────────────────>│
   │                                    │ 6. ParameterApplier 실행
   │                                    │ 7. RollbackMonitor 시작 (48h)
   │  { applied, monitoring }           │
   │ <──────────────────────────────────│
```

**결과 UI:**

```
┌─ 파라미터 최적화 결과 ─────────────────────────────────────┐
│                                                            │
│  대상: STR-002 Aggressive Trend (1h)                       │
│  기간: 2024-11-01 ~ 2024-11-30                             │
│  Optuna: 50 trials 완료                                    │
│                                                            │
│  파라미터          현재값    최적값    변경폭               │
│  ──────────────── ──────── ──────── ────────              │
│  buy_threshold    0.050    0.072    +44%                   │
│  sell_threshold   -0.050   -0.038   +24%                   │
│  tf_weight_1h     0.500    0.350    -30%                   │
│  tf_weight_4h     0.500    0.650    +30%                   │
│                                                            │
│  검증 결과 (Walk-Forward)                                   │
│  현재 파라미터: -0.36% (14 trades, WR 50%)                 │
│  최적 파라미터: +0.18% (11 trades, WR 64%)                 │
│  개선: +0.54%p                                             │
│                                                            │
│  ⚠ Guardrails: buy_threshold 변경폭 44% > 20% 제한        │
│    → 클램핑 적용: 0.050 → 0.060 (최대 20% 변경)            │
│                                                            │
│  [ 라이브에 적용 ]    [ 다른 기간으로 재검증 ]   [ 무시 ]     │
└────────────────────────────────────────────────────────────┘
```

### 17.3 Tuner 연동 API

```python
# 새 엔드포인트

# 1. 백테스트 기반 파라미터 최적화 (Action C)
POST /api/v1/tuning/optimize-from-backtest
Body: {
    "strategy_id": "STR-002",
    "backtest_result_id": "bt-result-xxx",   # 참조할 백테스트 결과
    "tier": "tier_1",                        # 최적화 대상 티어
    "n_trials": 50                           # Optuna 시행 횟수 (optional)
}
Response: {
    "job_id": "tune-xxx",
    "status": "pending"
}
# → 기존 backtest job polling 패턴으로 진행 상황 조회

# 2. 레짐 매핑 분석 (Action B)
POST /api/v1/tuning/analyze-regime-map
Body: {
    "backtest_job_id": "bt-xxx"              # AI Regime 백테스트 job
}
Response: {
    "suggestions": [
        {
            "regime": "bear_trend_high_vol",
            "current_strategy": "STR-007",
            "suggested_strategy": "STR-008",
            "current_return_pct": -0.5,
            "suggested_return_pct": 0.3,
            "improvement_pct": 0.8,
            "confidence": "medium",
            "sample_weeks": 3
        }
    ]
}

# 3. 레짐 매핑 업데이트 적용 (승인 후)
POST /api/v1/tuning/apply-regime-map
Body: {
    "changes": [
        { "regime": "bear_trend_high_vol", "new_strategy": "STR-008" }
    ]
}
Response: {
    "tuning_id": "tune-xxx",
    "status": "applied",
    "tier": "tier_3",
    "requires_approval": true
}

# 4. 최적화 결과 라이브 적용
POST /api/v1/tuning/apply-optimization
Body: {
    "optimization_job_id": "tune-xxx",
    "strategy_id": "STR-002"
}
Response: {
    "tuning_id": "tune-xxx",
    "status": "applied",
    "monitoring_until": "2026-03-26T20:00:00"
}
```

### 17.4 전체 사용자 플로우

```
                              Dashboard Backtest Page
                                      │
                    ┌─────────────────┼──────────────────┐
                    │                 │                   │
              [전략 비교 실행]    [단일 전략 실행]     [AI Regime 실행]
                    │                 │                   │
                    ▼                 ▼                   ▼
              랭킹 테이블         메트릭스 상세        레짐 타임라인
              이퀴티 커브         트레이드 목록        전략별 구간 성과
                    │                 │                   │
         ┌─────────┤          ┌──────┤            ┌──────┤
         │         │          │      │            │      │
    [전략 전환]  [무시]   [파라미터   [무시]   [레짐 매핑  [파라미터
     Action A]           최적화]              최적화]     최적화]
         │              Action C]            Action B]   Action C]
         │                │                    │          │
         ▼                ▼                    ▼          ▼
    즉시 적용        Optuna 최적화 →     분석 테이블 →  Optuna 최적화
    (기존 API)       Walk-Forward       승인 요청      (동일)
                     검증 → 적용        (Tier 3)
                     (48h 모니터링)      → 적용
```

### 17.5 UI 통합 — 결과 화면 하단 액션 영역

```
┌─ 결과 기반 액션 ──────────────────────────────────────────────┐
│                                                               │
│  📊 분석 요약                                                  │
│  • 최고 성과: STR-008 (+0.12%) — 현재 활성 전략과 다름         │
│  • bull_trend 구간에서 STR-002 부진 (-0.61%/주)                │
│  • 레짐 매핑 개선 여지: bear_trend → STR-008 전환 시 +0.8%p    │
│                                                               │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ │
│  │  ▶ 전략 전환     │ │  ⚡ 파라미터      │ │  🔄 레짐 매핑    │ │
│  │  STR-008로 전환  │ │  최적화 실행      │ │  최적화 분석      │ │
│  │  (즉시 적용)     │ │  (Optuna 50회)   │ │  (AI Regime만)   │ │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘ │
│                                                               │
│  ⓘ 파라미터 최적화는 해당 기간 데이터로 Optuna를 실행합니다.    │
│    Walk-Forward 검증 + Guardrails 안전 검증 포함.              │
└───────────────────────────────────────────────────────────────┘
```

---

## 18. 다단계 롤백 시스템

### 18.1 현재 롤백 (단일 단계)

기존 구현: 직전 튜닝 1건만 롤백 가능 (`POST /tuning/rollback/{tuning_id}`)

### 18.2 다단계 롤백 설계

파라미터 변경 이력을 스냅샷 체인으로 관리하여, 임의 시점으로 복원할 수 있도록 한다.

**스냅샷 테이블:**

```sql
CREATE TABLE IF NOT EXISTS param_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id     TEXT NOT NULL UNIQUE,        -- "snap-20260324-001"
    strategy_id     TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    source          TEXT NOT NULL,               -- "tuning" | "backtest" | "manual" | "rollback"
    source_id       TEXT,                        -- tuning_id 또는 backtest_result_id
    description     TEXT,                        -- "Optuna 최적화 from 11월 백테스트"
    params_json     TEXT NOT NULL,               -- 전체 파라미터 스냅샷 (완전한 상태)
    regime_map_json TEXT,                        -- REGIME_PRESET_MAP 스냅샷 (Tier 3)
    is_active       INTEGER DEFAULT 0           -- 현재 활성 스냅샷
);
CREATE INDEX IF NOT EXISTS idx_ps_strategy
    ON param_snapshots(strategy_id, created_at DESC);
```

**핵심 설계: 전체 스냅샷 저장**

diff(변경분)가 아닌 **전체 파라미터 상태**를 매번 저장한다.

```python
@dataclass(frozen=True)
class ParamSnapshot:
    snapshot_id: str
    strategy_id: str
    created_at: datetime
    source: str                     # "tuning" | "backtest" | "manual" | "rollback"
    source_id: str | None           # 원본 참조 ID
    description: str
    params: dict[str, float]        # 전체 파라미터 값
    regime_map: dict[str, str] | None  # 전체 레짐 매핑

# 스냅샷 생성 시점:
# - 튜너 파라미터 적용 시
# - 백테스트 기반 최적화 적용 시
# - 전략 전환 시
# - 레짐 매핑 변경 시
# - 롤백 실행 시 (롤백 자체도 새 스냅샷)
```

**다단계 롤백 흐름:**

```
현재 상태: snap-005 (active)

스냅샷 체인:
  snap-001  03/20 초기값 (기본 프리셋)
  snap-002  03/21 Optuna 최적화 (buy_threshold 조정)
  snap-003  03/22 레짐 매핑 변경 (bear→STR-008)
  snap-004  03/23 Optuna 최적화 (tf_weight 조정)
  snap-005  03/24 백테스트 기반 최적화 ← 현재

사용자: "snap-002 시점으로 돌아가고 싶다"
→ POST /api/v1/tuning/rollback-to-snapshot
  { snapshot_id: "snap-002" }
→ snap-002의 params를 라이브 엔진에 적용
→ snap-006 생성 (source="rollback", source_id="snap-002")
→ 모니터링 시작 (48h)

결과:
  snap-006  03/24 롤백 → snap-002 시점 ← 현재 (active)
```

### 18.3 롤백 API

```python
# 1. 스냅샷 목록 조회
GET /api/v1/tuning/snapshots
Params: { "strategy_id": "STR-002", "limit": 20 }
Response: {
    "snapshots": [
        {
            "snapshot_id": "snap-005",
            "strategy_id": "STR-002",
            "created_at": "2026-03-24T20:00:00",
            "source": "backtest",
            "description": "11월 백테스트 기반 Optuna 최적화",
            "is_active": true,
            "params": { "buy_threshold": 0.06, ... }
        },
        ...
    ]
}

# 2. 특정 스냅샷으로 롤백
POST /api/v1/tuning/rollback-to-snapshot
Body: {
    "snapshot_id": "snap-002",
    "strategy_id": "STR-002"
}
Response: {
    "new_snapshot_id": "snap-006",
    "rolled_back_to": "snap-002",
    "status": "applied",
    "monitoring_until": "2026-03-26T20:00:00"
}

# 3. 두 스냅샷 비교 (diff)
GET /api/v1/tuning/snapshots/diff
Params: { "from": "snap-002", "to": "snap-005" }
Response: {
    "changes": [
        { "param": "buy_threshold", "from": 0.05, "to": 0.06, "change_pct": 20.0 },
        { "param": "tf_weight_1h", "from": 0.50, "to": 0.35, "change_pct": -30.0 },
        ...
    ],
    "regime_map_changes": [
        { "regime": "bear_trend_high_vol", "from": "STR-007", "to": "STR-008" }
    ]
}
```

### 18.4 롤백 UI

```
┌─ 파라미터 히스토리 (타임라인) ──────────────────────────────┐
│                                                              │
│  ● snap-005  03/24 20:00  백테스트 기반 최적화  ← 현재       │
│  │  buy_threshold 0.05→0.06, tf_weight_1h 0.50→0.35         │
│  │  [ 비교 ] [ 이 시점으로 롤백 ]                             │
│  │                                                           │
│  ○ snap-004  03/23 15:00  Optuna 정기 최적화                 │
│  │  sell_threshold -0.05→-0.04                               │
│  │  [ 비교 ] [ 이 시점으로 롤백 ]                             │
│  │                                                           │
│  ○ snap-003  03/22 10:00  레짐 매핑 변경                     │
│  │  bear_trend: STR-007→STR-008                              │
│  │  [ 비교 ] [ 이 시점으로 롤백 ]                             │
│  │                                                           │
│  ○ snap-002  03/21 09:00  Optuna 최적화                      │
│  │  buy_threshold 0.08→0.05                                  │
│  │  [ 비교 ] [ 이 시점으로 롤백 ]                             │
│  │                                                           │
│  ○ snap-001  03/20 00:00  초기값 (STR-002 기본)              │
│     [ 비교 ] [ 초기값으로 리셋 ]                              │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 19. 튜닝 적용 히스토리 (Backtest → Tuning 연결)

### 19.1 목적

"어떤 백테스트 결과를 보고 어떤 변경을 했는지" 추적.
성과 악화 시 원인 역추적 + 롤백 판단 근거 제공.

### 19.2 DB 스키마 확장

```sql
-- 기존 tuning_history 테이블에 컬럼 추가
ALTER TABLE tuning_history ADD COLUMN backtest_result_id TEXT;
    -- 이 튜닝을 촉발한 백테스트 결과 ID

ALTER TABLE tuning_history ADD COLUMN action_type TEXT;
    -- 'preset_switch': Action A (전략 전환)
    -- 'regime_map':    Action B (레짐 매핑 변경)
    -- 'param_optimize': Action C (파라미터 최적화)
    -- 'scheduled':     정기 스케줄 튜닝
    -- 'manual':        수동 트리거
    -- 'rollback':      롤백

ALTER TABLE tuning_history ADD COLUMN snapshot_id TEXT;
    -- 이 튜닝으로 생성된 param_snapshot ID
```

### 19.3 연결 구조

```
backtest_results                tuning_history              param_snapshots
┌──────────────┐    촉발     ┌──────────────────┐  생성   ┌────────────────┐
│ bt-result-001│───────────>│ tuning-001        │──────>│ snap-003       │
│ 11월 전략비교 │            │ action: regime_map│       │ 레짐매핑 변경   │
│ Best: STR-008│            │ bt_id: bt-001     │       │ bear→STR-008   │
└──────────────┘            │ snap_id: snap-003 │       └────────────────┘
                            └──────────────────┘
                                    │
                                    │ 48h 후 성과 악화
                                    ▼
                            ┌──────────────────┐  생성   ┌────────────────┐
                            │ tuning-002        │──────>│ snap-004       │
                            │ action: rollback  │       │ snap-002로 복원 │
                            │ snap_id: snap-004 │       └────────────────┘
                            └──────────────────┘
```

### 19.4 조회 API

```python
# 1. 특정 백테스트에서 파생된 튜닝 목록
GET /api/v1/tuning/history?backtest_result_id=bt-result-001
Response: {
    "records": [
        {
            "tuning_id": "tuning-001",
            "action_type": "regime_map",
            "backtest_result_id": "bt-result-001",
            "snapshot_id": "snap-003",
            "created_at": "2026-03-22T10:00:00",
            "status": "rolled_back",
            "changes": [...]
        }
    ]
}

# 2. 전체 튜닝 히스토리 (출처 포함)
GET /api/v1/tuning/history?limit=20
Response: {
    "records": [
        {
            "tuning_id": "tuning-002",
            "action_type": "rollback",
            "source": "backtest",          # 백테스트 기반
            "backtest_result_id": "bt-result-001",
            ...
        },
        {
            "tuning_id": "tuning-003",
            "action_type": "param_optimize",
            "source": "scheduled",         # 정기 스케줄
            "backtest_result_id": null,
            ...
        }
    ]
}
```

### 19.5 대시보드 조회 — 양쪽 페이지

**Tuner 페이지 (기존 확장):**
- 전체 튜닝 히스토리에 `출처` 컬럼 추가 (스케줄/백테스트/수동)
- 백테스트 출처인 경우 → 원본 백테스트 결과 링크
- 스냅샷 타임라인 탭 추가

**Backtest 페이지 (결과 하단):**
- "적용 히스토리" 섹션: 이 백테스트에서 파생된 튜닝만 표시
- 각 적용의 현재 상태 (적용중/모니터링/확정/롤백됨)

```
┌─ 이 백테스트에서 적용한 변경 ────────────────────────────────┐
│                                                              │
│  #1  03/22 10:00  레짐 매핑 변경                             │
│      bear_trend: STR-007 → STR-008                          │
│      상태: 롤백됨 (03/24, MDD 초과)                          │
│                                                              │
│  #2  03/22 11:00  파라미터 최적화 (STR-002, Tier 1)          │
│      buy_threshold: 0.05 → 0.06                             │
│      상태: 확정됨 (48h 모니터링 통과)                         │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 20. 백테스트 히스토리 조회 강화

### 20.1 히스토리 목록

```
┌─ 백테스트 히스토리 ──────────────────────────────────────────┐
│                                                              │
│  필터: [전체▾] [전략비교▾] [기간▾]        🔍 검색             │
│                                                              │
│  03/24 20:00  전략 비교  11월 (30일)                         │
│    Best: STR-008 +0.12%  |  Worst: STR-001 -0.74%          │
│    적용: 레짐 매핑 1건, 파라미터 최적화 1건                   │
│    [ 결과 보기 ]  [ 삭제 ]                                    │
│                                                              │
│  03/23 15:00  AI Regime  10월 (31일)                         │
│    AI: -0.50%  |  Best Fixed: STR-001 +2.1%                 │
│    적용: 없음                                                │
│    [ 결과 보기 ]  [ 삭제 ]                                    │
│                                                              │
│  03/22 09:00  단일 전략  STR-002  9~11월 (90일)              │
│    수익률: +1.2%  |  Sharpe: 0.85  |  MDD: 3.2%             │
│    적용: 파라미터 최적화 1건 (확정됨)                         │
│    [ 결과 보기 ]  [ 삭제 ]                                    │
│                                                              │
│  ───────── 더 보기 (12건 남음) ─────────                      │
└──────────────────────────────────────────────────────────────┘
```

### 20.2 결과 복원 보기

히스토리에서 "결과 보기" 클릭 시:
- DB에 저장된 전체 결과 (metrics, equity_curve, trades) 로드
- 동일한 결과 UI (차트 + 테이블 + 트레이드) 렌더링
- 재실행 불필요 (저장된 데이터로 즉시 표시)

### 20.3 결과 비교 (v2 후보)

두 백테스트 결과를 나란히 비교:
- 같은 전략, 다른 기간 (시장 환경 변화 분석)
- 같은 기간, 다른 전략 (전략 선택 근거)
- 최적화 전/후 비교 (파라미터 변경 효과)

→ Phase 5 이후 v2에서 구현 검토

---

## 21. 구현 순서 (최종)

### Phase 1: 백엔드 기반
| # | 파일 | 내용 |
|---|------|------|
| 1 | `engine/backtest/schemas.py` | Pydantic 모델 (Request/Response, Job, Snapshot) |
| 2 | `engine/backtest/candle_cache.py` | 캔들 데이터 DB 캐시 |
| 3 | `engine/backtest/job_manager.py` | 비동기 Job 관리 (생성/폴링/취소) |
| 4 | `engine/backtest/runners.py` | 3개 모드 실행 함수 + 결과 DB 저장 |
| 5 | `api/routes/backtest.py` | 백테스트 API 엔드포인트 |
| 6 | `api/main.py` | 라우터 등록 |
| 7 | DB 마이그레이션 | backtest_candle_cache, backtest_results 확장, param_snapshots 테이블 |

### Phase 2: 대시보드 기본 UI
| # | 파일 | 내용 |
|---|------|------|
| 1 | `dashboard/src/app/backtest/page.tsx` | 메인 페이지 (폼 + 프로그레스 + 결과) |
| 2 | `dashboard/src/components/backtest/BacktestForm.tsx` | 기간/모드/전략 선택 폼 |
| 3 | `dashboard/src/components/backtest/BacktestProgress.tsx` | 실행 프로그레스 바 |
| 4 | TopNav.tsx, BottomNav.tsx | Backtest 네비게이션 탭 추가 |

### Phase 3: 결과 시각화
| # | 파일 | 내용 |
|---|------|------|
| 1 | `StrategyRankingTable.tsx` | 전략 비교 랭킹 테이블 |
| 2 | `EquityCurveChart.tsx` | 이퀴티 커브 (lightweight-charts) |
| 3 | `TradeList.tsx` | 트레이드 목록 (접이식) |
| 4 | `RegimeTimeline.tsx` | AI Regime 주간 타임라인 |

### Phase 4: Tuner 연동 + 액션
| # | 파일 | 내용 |
|---|------|------|
| 1 | `engine/backtest/analyzer.py` | 결과 분석 + 레짐 매핑 제안 로직 |
| 2 | `api/routes/backtest.py` 확장 | Tuner 연동 엔드포인트 (optimize, regime-map, apply) |
| 3 | `ActionPanel.tsx` | 3가지 액션 UI (전략전환/매핑변경/파라미터최적화) |
| 4 | `OptimizationResult.tsx` | Optuna 최적화 결과 표시 |

### Phase 5: 히스토리 + 롤백
| # | 파일 | 내용 |
|---|------|------|
| 1 | `BacktestHistory.tsx` | 백테스트 히스토리 목록 + 결과 복원 |
| 2 | `SnapshotTimeline.tsx` | 파라미터 스냅샷 타임라인 (다단계 롤백 UI) |
| 3 | `TuningApplyHistory.tsx` | 백테스트→튜닝 적용 히스토리 |
| 4 | Tuner 페이지 확장 | 출처 필터 + 스냅샷 탭 추가 |

### Phase 6: 마무리
| # | 작업 | 내용 |
|---|------|------|
| 1 | 모바일 반응형 | 전체 UI 모바일 최적화 |
| 2 | 도움말 연동 | helpData.ts에 백테스트 항목 추가 |
| 3 | 테스트 | 백엔드 단위 테스트 + UI 통합 테스트 |
| 4 | 배포 | Fly.io (엔진) + Vercel (대시보드) |

### Phase 1: 백엔드 기반 (5개 파일)
1. `engine/backtest/schemas.py` — Request/Response 모델
2. `engine/backtest/candle_cache.py` — 캔들 데이터 캐시
3. `engine/backtest/job_manager.py` — Job 관리자
4. `engine/backtest/runners.py` — 3개 모드 실행 함수 (캐시 활용)
5. `api/routes/backtest.py` — 기본 5개 엔드포인트 + 결과 조회

### Phase 2: 대시보드 기본 UI (4개 파일)
1. `dashboard/src/app/backtest/page.tsx` — 메인 페이지
2. `dashboard/src/components/backtest/BacktestForm.tsx` — 설정 폼
3. `dashboard/src/components/backtest/BacktestProgress.tsx` — 프로그레스
4. 네비게이션 탭 추가

### Phase 3: 결과 시각화 (4개 파일)
1. `StrategyRankingTable.tsx`
2. `EquityCurveChart.tsx`
3. `TradeList.tsx`
4. `RegimeTimeline.tsx`

### Phase 4: Tuner 연동 (3개 파일)
1. `engine/backtest/analyzer.py` — 결과 분석 + 레짐 매핑 제안
2. `api/routes/backtest.py` 확장 — Tuner 연동 엔드포인트 3개
3. `dashboard/src/components/backtest/ActionPanel.tsx` — 액션 UI

### Phase 5: 히스토리 + 마무리
1. `BacktestHistory.tsx` — 히스토리 UI (DB 저장 결과 조회)
2. 모바일 반응형 최적화
3. 테스트 및 배포
