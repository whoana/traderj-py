# 수익률 개선 프로세스 — 최종 설계서

> **상태:** 확정
> **작성일:** 2026-03-25
> **근거 문서:**
> - `docs/plan/profit-improvement-process.md` — 프로세스 초안
> - `docs/plan/profit-improvement-meeting_20260325.md` — Q1~Q6 회의 결론
> - `docs/design/wizard-ui-design.md` — 위자드 UI 설계

---

## 1. 목표

백테스트 결과를 기반으로 레짐/전략/파라미터를 **체계적으로 개선**하는 반복 사이클을 구축한다.

```
현재: 백테스트 → 결과 확인 → (끊김) → 수동 코드 수정 → 재배포
목표: 백테스트 → 분석 → 최적화 → 적용 → 검증 → 완료 (위자드 UI로 자동화)
```

### 핵심 원칙

1. **engine/tuner/ 활용** — 15개 모듈이 이미 구현됨. 신규 개발 아닌 **배선(wiring)** 중심
2. **검증이 수익의 열쇠** — 과적합 방지를 위한 Walk-forward + 3-Gate 검증 필수
3. **JSON 오버라이드** — 재시작해도 튜닝이 유지되는 영속 메커니즘
4. **단계적 자동화** — Tier 1 완전자동 → Tier 2 반자동 → Tier 3 수동승인

---

## 2. 현재 상태 분석

### 2.1 이미 구현된 것

| 영역 | 모듈 | 상태 |
|------|------|------|
| 백테스트 실행 | `engine/backtest/runners.py` | 4모드 완료 (single/compare/ai_regime/optimize) |
| 캔들 캐시 | `engine/backtest/candle_cache.py` | SQLite 캐시 + Upbit gap-fill |
| 분석/인사이트 | `engine/backtest/analyzer.py` | analyze_results + regime_mapping |
| Optuna 최적화 | `engine/backtest/runners.py` (optimize) | Tier 1, ±30%, 30 trials |
| API (백테스트) | `api/routes/backtest.py` | 6개 엔드포인트 |
| 대시보드 액션 | `ActionPanel.tsx` | 전략전환/레짐매핑/파라미터최적화 |
| AI Tuner 평가 | `engine/tuner/evaluator.py` | 성과 메트릭 + LLM 진단 |
| AI Tuner 최적화 | `engine/tuner/optimizer.py` | Optuna + Walk-forward + LLM 후보선택 |
| AI Tuner 적용 | `engine/tuner/applier.py` | Hot-reload + Guardrails + 이력 저장 |
| AI Tuner 모니터링 | `engine/tuner/rollback.py` | 48h 모니터링 + 자동 롤백 |
| AI Tuner 파이프라인 | `engine/tuner/pipeline.py` | 전체 오케스트레이션 |
| AI Tuner DB | `engine/tuner/store.py` | tuning_history + tuning_report |
| AI Tuner 안전장치 | `engine/tuner/guardrails.py` | 파라미터 클램핑 + 가중치 정규화 |
| LLM 클라이언트 | `engine/tuner/llm_client.py` | Claude + OpenAI (httpx) |
| LLM 라우터 | `engine/tuner/provider_router.py` | 서킷브레이커 + 비용 추적 |
| 11개 전략 프리셋 | `engine/strategy/presets.py` | STR-001~010 + default |

### 2.2 미구현 (이 설계서의 범위)

| 영역 | 설명 | 우선순위 |
|------|------|----------|
| JSON 프리셋 오버라이드 | 최적화 결과 영속화 | P0 |
| Gate 1 백테스트 검증 | 적용 전 OOS 검증 | P0 |
| Optuna objective 개선 | 리스크 조정 복합 지표 | P1 |
| 위자드 UI | 6단계 풀스크린 오버레이 | P1 |
| 위자드 API | 위자드 전용 엔드포인트 | P1 |
| TunerPipeline 배선 | bootstrap.py 연결 | P2 |
| Telegram 알림 연동 | 튜닝 결과 알림 | P2 |

---

## 3. 프로세스 흐름 (6단계)

```
┌────────────────────────────────────────────────────────────┐
│                수익률 개선 사이클 (PDCA)                      │
│                                                            │
│  ① 백테스트 선택  →  ② 분석  →  ③ 최적화  →  ④ 적용 리뷰   │
│        ↑                                      │            │
│        └──────────── ⑤ 검증 ←────────────────┘            │
│                        │                                   │
│                   통과 시 ↓                                 │
│                   ⑥ 완료                                    │
└────────────────────────────────────────────────────────────┘
```

### Step 1: 백테스트 선택

| 항목 | 내용 |
|------|------|
| 입력 | 기존 백테스트 결과 or 새 백테스트 실행 |
| 데이터 | `GET /backtest/jobs` → 히스토리 목록 |
| 진행 조건 | 유효한 결과 1개 선택됨 |
| 기존 구현 | `BacktestJobManager.list_jobs()` |

### Step 2: 분석

| 항목 | 내용 |
|------|------|
| 입력 | 선택된 백테스트 결과 |
| 데이터 | `GET /backtest/analyze/{job_id}` |
| 표시 | 핵심 지표 4카드, Equity Curve, AI 인사이트 |
| 사용자 선택 | 개선 영역 체크 (전략전환 / 레짐매핑 / 파라미터튜닝) |
| 진행 조건 | 분석 로딩 완료 |
| 기존 구현 | `analyzer.py` — analyze_results + analyze_regime_mapping |

### Step 3: 최적화

선택된 항목별 실행 (최대 3가지 동시):

**A. 전략 전환**
- 분석에서 추천된 Best 전략으로 전환
- 즉시 완료 (최적화 불필요)

**B. 레짐 매핑 변경**
- 레짐별 최적 전략 재배치 (같은 카테고리 내만 허용)
- STR-009/010 후보 포함
- `RegimeSwitchManager.preset_map` 주입

**C. 파라미터 최적화**
- Optuna TPE sampler, Tier 1 파라미터 (9개)
- **개선된 Objective**: `sharpe * 0.4 + return_pct * 0.3 + PF * 0.2 + (1/MDD) * 0.1`
- Walk-forward 3-window 검증 의무화
- Top 3 후보 도출

| 항목 | 내용 |
|------|------|
| 표시 | 프로그레스 바, Baseline vs Optimized 비교, Top 3 테이블 |
| 진행 조건 | 선택된 모든 작업 완료 |
| 기존 구현 | `runners.run_optimize()`, `HybridOptimizer` |

### Step 4: 적용 리뷰

| 항목 | 내용 |
|------|------|
| 표시 | Before/After 비교, 변경사항 체크리스트 (토글) |
| 사용자 선택 | 적용할 항목 토글 on/off |
| 경고 | 라이브 엔진 즉시 반영 안내 |
| 옵션 | "검증 없이 바로 적용" (경고 포함) |
| 진행 조건 | 1개 이상 항목 선택 |
| **신규 구현** | 적용 API, JSON 오버라이드 저장 |

### Step 5: 검증 (Gate 1)

3-Gate 중 Gate 1 (백테스트 검증)을 위자드 내에서 실행:

| 기준 | 임계값 |
|------|--------|
| OOS 수익률 | > baseline + 2% |
| Profit Factor | > 1.2 |
| MDD | < baseline × 1.3 |
| 거래 수 | ≥ 10건 |

Walk-forward 구조:
```
Window 1: [Train: D-240~D-150] → [Test: D-150~D-120]
Window 2: [Train: D-180~D-90]  → [Test: D-90~D-60]
Window 3: [Train: D-120~D-30]  → [Test: D-30~D-0]
→ OOS 전체 평균이 기준 충족해야 통과
```

| 판정 | 조건 |
|------|------|
| Pass (초록) | 모든 기준 충족 |
| Warn (노랑) | 1~2개 미달 |
| Fail (빨강) | 3개 이상 미달 |

| 항목 | 내용 |
|------|------|
| 건너뛰기 | 가능 (경고 문구 포함) |
| 미통과 시 | Step 3으로 돌아가 재최적화 권고 |
| **신규 구현** | 검증 백테스트 API, Walk-forward 엔진 |

### Step 6: 완료

| 항목 | 내용 |
|------|------|
| 표시 | 축하 메시지, 적용 요약, 예상 개선폭 |
| 액션 | "대시보드로 돌아가기" / "새 백테스트 시작" |
| 후속 | Gate 2 (48~72h 라이브 모니터링) 자동 시작 |

---

## 4. 엔진 구현 상세

### 4.1 JSON 프리셋 오버라이드 (P0)

**파일:** `/data/preset_overrides.json` (Fly.io 볼륨)

```json
{
  "version": 1,
  "updated_at": "2026-03-25T10:00:00Z",
  "presets": {
    "STR-003": {
      "buy_threshold": 0.48,
      "sell_threshold": -0.12,
      "macro_weight": 0.35
    }
  },
  "regime_map": {
    "TRENDING": "STR-009",
    "MEAN_REVERTING": "STR-003",
    "HIGH_VOL": "STR-007"
  }
}
```

**동작 규칙:**
1. 엔진 부팅: `presets.py` 로드 → JSON 오버라이드 적용
2. 변경된 파라미터만 저장 (sparse override)
3. JSON 손상/누락 시 `presets.py`로 자동 폴백
4. 변경 이력은 `tuning_history` DB 테이블에 기록

**구현 위치:**
- `engine/strategy/presets.py` — `load_preset(strategy_id)` 함수 추가
- `engine/tuner/applier.py` — JSON write 로직 추가

### 4.2 Optuna Objective 개선 (P1)

**현재:** `return_pct + profit_factor * 0.1` (수익률 편향)

**변경:**
```python
def objective(trial):
    # ... backtest execution ...
    sharpe = calculate_sharpe(equity_curve)
    score = (
        sharpe * 0.4
        + return_pct * 0.3
        + profit_factor * 0.2
        + (1.0 / max(abs(mdd), 0.01)) * 0.1
    )
    return score
```

**구현 위치:** `engine/backtest/runners.py` — `_run_optuna_optimize()`

### 4.3 Gate 1 검증 백테스트 (P0)

최적화에 사용되지 않은 기간(OOS)으로 백테스트를 재실행하여 과적합을 검증.

**구현 위치:**
- `engine/backtest/validators.py` — `run_gate1_validation()` 함수 (별도 모듈로 분리)
- Walk-forward 동적 윈도우 (WalkForwardEngine 활용, 데이터 길이에 적응)
- 기준 판정: critical(return, MDD) 실패 시 fail, 비critical만 실패 시 warn

### 4.4 레짐 전환 포지션 처리 세분화 (P1)

**레짐 전환 시 (RegimeSwitchManager):**

| 조건 | 처리 |
|------|------|
| 미실현 이익 (PnL > 0) | SL을 손익분기점으로 올림 + 새 전략 TP 적용 |
| 소규모 손실 (0 > PnL > -1.5%) | SL 타이트닝 (현재 로직) |
| 큰 손실 (PnL < -1.5%) | 즉시 청산 |
| BEAR 레짐 전환 | **무조건 즉시 청산** |

**AI Tuner 파라미터 변경 시:**
- Tier 1(시그널): 기존 포지션 영향 없음
- Tier 2(리스크): 열린 포지션 있으면 다음 포지션부터 적용

---

## 5. API 구현 상세

### 5.1 신규 엔드포인트

```
POST /backtest/wizard/optimize     최적화 실행 (개선된 objective)
POST /backtest/wizard/validate     검증 백테스트 실행 (Walk-forward)
POST /backtest/wizard/apply        변경사항 적용 (JSON 오버라이드 저장)
GET  /backtest/wizard/apply-preview 적용 전 Before/After 미리보기
```

### 5.2 `/wizard/optimize` 요청/응답

```python
# Request
{
  "job_id": "bt-20260325-...",
  "strategy_id": "STR-003",
  "areas": ["strategy_switch", "regime_map", "param_optimize"],
  "n_trials": 30
}

# Response
{
  "job_id": "wiz-opt-...",
  "status": "running",
  "progress": 0
}
```

### 5.3 `/wizard/validate` 요청/응답

```python
# Request
{
  "strategy_id": "STR-003",
  "params": { "buy_threshold": 0.48, ... },
  "regime_map": { "TRENDING": "STR-009", ... },
  "baseline_job_id": "bt-20260325-..."
}

# Response
{
  "job_id": "wiz-val-...",
  "status": "done",
  "result": {
    "windows": [
      { "train": "D-240~D-150", "test": "D-150~D-120", "return_pct": 3.2, "pf": 1.4, "mdd": -4.1 },
      { "train": "D-180~D-90", "test": "D-90~D-60", "return_pct": 2.8, "pf": 1.3, "mdd": -3.8 },
      { "train": "D-120~D-30", "test": "D-30~D-0", "return_pct": 4.1, "pf": 1.6, "mdd": -3.2 }
    ],
    "avg_return_pct": 3.37,
    "avg_pf": 1.43,
    "avg_mdd": -3.7,
    "gates": {
      "oos_return": { "value": 3.37, "threshold": 2.0, "pass": true },
      "profit_factor": { "value": 1.43, "threshold": 1.2, "pass": true },
      "mdd": { "value": -3.7, "threshold": -6.77, "pass": true },
      "trade_count": { "value": 28, "threshold": 10, "pass": true }
    },
    "verdict": "pass"
  }
}
```

### 5.4 `/wizard/apply` 요청/응답

```python
# Request
{
  "changes": {
    "strategy_switch": { "from": "STR-001", "to": "STR-003" },
    "param_optimize": { "buy_threshold": 0.48, "sell_threshold": -0.12, "macro_weight": 0.35 },
    "regime_map": { "TRENDING": "STR-009", "MEAN_REVERTING": "STR-003" }
  },
  "validation_job_id": "wiz-val-...",
  "skip_validation": false
}

# Response
{
  "applied": ["strategy_switch", "param_optimize", "regime_map"],
  "override_file": "/data/preset_overrides.json",
  "tuning_id": "tun-20260325-...",
  "monitoring_until": "2026-03-27T10:00:00Z"
}
```

---

## 6. 대시보드 위자드 UI

> 상세: `docs/design/wizard-ui-design.md` 참조

### 6.1 컴포넌트 구조

```
components/backtest/wizard/
  WizardOverlay.tsx       풀스크린 오버레이 셸 (<dialog> + showModal)
  WizardStepper.tsx       스텝 인디케이터 (상단 고정)
  WizardNavButtons.tsx    이전/다음 하단 버튼
  steps/
    StepBacktest.tsx      Step 1 — 백테스트 선택
    StepAnalyze.tsx       Step 2 — 분석
    StepOptimize.tsx      Step 3 — 최적화
    StepApply.tsx         Step 4 — 적용 리뷰
    StepValidate.tsx      Step 5 — 검증
    StepComplete.tsx      Step 6 — 완료

contexts/
  WizardContext.tsx       useReducer 기반 상태 관리

hooks/
  useAsyncJob.ts          비동기 작업 폴링 (최적화/검증 공통)

components/ui/
  ProgressBar.tsx         진행률 표시 (신규)
  CompareTable.tsx        Before/After 비교 (신규)
  ChecklistItem.tsx       체크 가능 항목 (신규)
```

### 6.2 데이터 흐름

```
useReducer + WizardContext
  state: {
    step: 1~6,
    selectedJobId: string,
    analysisResult: AnalysisResult,
    selectedAreas: string[],          // ["strategy_switch", "regime_map", "param_optimize"]
    optimizeResult: OptimizeResult,
    applyChanges: ApplyChanges,       // 토글 on/off 된 변경 목록
    validationResult: ValidationResult,
  }

actions:
  SET_STEP, SELECT_JOB, SET_ANALYSIS, SET_AREAS,
  SET_OPTIMIZE_RESULT, TOGGLE_CHANGE, SET_VALIDATION, RESET
```

### 6.3 진입점

```tsx
// backtest/page.tsx
{status === "done" && jobId && (
  <WizardLauncher jobId={jobId} result={result} startDate={startDate} endDate={endDate} />
)}
```

---

## 7. 구현 Phase

### Phase 1: 엔진 기반 (P0) — 예상 범위: 4개 파일

**목표:** JSON 오버라이드 + Gate 1 검증의 핵심 메커니즘

| # | 작업 | 파일 | 설명 |
|---|------|------|------|
| 1-1 | JSON 오버라이드 로더 | `engine/strategy/presets.py` | `load_preset()` 함수: presets.py 기본값 → JSON 오버라이드 적용 |
| 1-2 | JSON 오버라이드 저장 | `engine/strategy/preset_override.py` (신규) | `save_override()`, `load_overrides()`, `clear_override()` |
| 1-3 | Gate 1 검증 로직 | `engine/backtest/validators.py` (신규) | Walk-forward 3-window, 4개 기준 판정 (Pass/Warn/Fail) |
| 1-4 | Objective 함수 개선 | `engine/backtest/runners.py` | Sharpe 기반 복합 지표로 교체 |

**테스트:** `engine/tests/unit/test_preset_override.py`, `engine/tests/unit/test_validators.py`

### Phase 2: 위자드 API (P1) — 예상 범위: 2개 파일

**목표:** 위자드 전용 엔드포인트

| # | 작업 | 파일 | 설명 |
|---|------|------|------|
| 2-1 | 위자드 라우터 | `api/routes/wizard.py` (신규) | 4개 엔드포인트 (optimize/validate/apply/preview) |
| 2-2 | 라우터 등록 | `api/main.py` | wizard 라우터 include |

**의존:** Phase 1 완료

### Phase 3: 위자드 UI 골격 (P1) — 예상 범위: 6개 파일

**목표:** 오버레이 + 스텝 네비게이션 + 상태 관리

| # | 작업 | 파일 | 설명 |
|---|------|------|------|
| 3-1 | WizardContext | `contexts/WizardContext.tsx` (신규) | useReducer 상태관리 |
| 3-2 | WizardOverlay | `wizard/WizardOverlay.tsx` (신규) | 풀스크린 오버레이 셸 |
| 3-3 | WizardStepper | `wizard/WizardStepper.tsx` (신규) | 6단계 인디케이터 |
| 3-4 | WizardNavButtons | `wizard/WizardNavButtons.tsx` (신규) | 이전/다음 하단 버튼 |
| 3-5 | useAsyncJob | `hooks/useAsyncJob.ts` (신규) | 비동기 작업 폴링 훅 |
| 3-6 | WizardLauncher | `wizard/WizardLauncher.tsx` (신규) | 진입 버튼 + backtest/page.tsx 연결 |

### Phase 4: 위자드 UI Step 1~2 (P1) — 예상 범위: 3개 파일

**목표:** 백테스트 선택 + 분석 (기존 API 연결)

| # | 작업 | 파일 | 설명 |
|---|------|------|------|
| 4-1 | StepBacktest | `steps/StepBacktest.tsx` (신규) | 히스토리 목록, 라디오 선택, 새 백테스트 옵션 |
| 4-2 | StepAnalyze | `steps/StepAnalyze.tsx` (신규) | 4카드 지표, 인사이트, 레짐 테이블, 영역 체크리스트 |
| 4-3 | EquityCurveChart 재사용 | 기존 | Step 2에서 import |

### Phase 5: 위자드 UI Step 3~4 (P1) — 예상 범위: 4개 파일

**목표:** 최적화 + 적용 리뷰 (위자드 API 연결)

| # | 작업 | 파일 | 설명 |
|---|------|------|------|
| 5-1 | StepOptimize | `steps/StepOptimize.tsx` (신규) | 프로그레스, Baseline vs Opt 비교, Top 3 테이블 |
| 5-2 | StepApply | `steps/StepApply.tsx` (신규) | 변경 토글, Before/After, 경고 |
| 5-3 | CompareTable | `ui/CompareTable.tsx` (신규) | 범용 비교 테이블 컴포넌트 |
| 5-4 | ProgressBar | `ui/ProgressBar.tsx` (신규) | Optuna 진행률 표시 |

### Phase 6: 위자드 UI Step 5~6 (P1) — 예상 범위: 3개 파일

**목표:** 검증 + 완료

| # | 작업 | 파일 | 설명 |
|---|------|------|------|
| 6-1 | StepValidate | `steps/StepValidate.tsx` (신규) | Walk-forward 결과, 4개 Gate 체크, 판정 표시 |
| 6-2 | StepComplete | `steps/StepComplete.tsx` (신규) | 축하, 요약, 다음 액션 |
| 6-3 | ChecklistItem | `ui/ChecklistItem.tsx` (신규) | Pass/Warn/Fail 체크항목 |

---

## 8. Phase 간 의존관계

```
Phase 1 (엔진 기반) ─────────────────┐
    │                                 │
    ▼                                 ▼
Phase 2 (위자드 API) ──────► Phase 3 (UI 골격)
    │                            │
    ▼                            ▼
Phase 5 (Step 3~4) ◄──── Phase 4 (Step 1~2)
    │
    ▼
Phase 6 (Step 5~6)
```

- Phase 1은 독립 실행 가능 (최우선)
- Phase 2~3은 Phase 1 완료 후 병렬 진행 가능
- Phase 4는 Phase 3 완료 후 (UI 골격 필요)
- Phase 5는 Phase 2+4 완료 후 (API + UI 골격 필요)
- Phase 6은 Phase 5 완료 후

---

## 9. Tier별 자동화 수준 (운영 설정)

| Tier | 자동화 | 인간 개입 | 스케줄 |
|------|--------|----------|--------|
| Tier 1 (시그널) | 완전 자동 | Telegram 알림만 | 월요일 |
| Tier 2 (리스크) | 반자동 | 1시간 내 거부 없으면 적용 | 화요일 |
| Tier 3 (레짐) | 수동 승인 | Telegram 명시적 승인 | 수요일 |

**안전장치:**
- 하루 1회 이상 튜닝 적용 금지
- 연속 3회 롤백 → SUSPENDED → 1주 후 자동 해제
- `daily_max_loss_pct`는 자동 최적화에서 완전 제외
- `max_position_pct` 범위: 0.10~0.25 (축소)

**단계적 활성화:**

| Phase | 조건 | 범위 | 환경변수 |
|-------|------|------|---------|
| 1 | 즉시 | Tier 1 자동 | `TUNER_TIER2_INTERVAL_WEEKS=999` |
| 2 | 4~8주 안정 후 | + Tier 2 | `TUNER_TIER2_INTERVAL_WEEKS=2` |
| 3 | 추가 4주 후 | + Tier 3 | `TUNER_TIER3_INTERVAL_WEEKS=4` |

---

## 10. 3-Gate 검증 체계

| Gate | 시점 | 방식 | 기준 |
|------|------|------|------|
| Gate 1 | 적용 직전 | 위자드 Step 5 (백테스트) | OOS 수익률 > baseline+2%, PF > 1.2, MDD < baseline×1.3, 거래 ≥ 10 |
| Gate 2 | 적용 후 48~72h | 자동 모니터링 (`RollbackMonitor`) | MDD < eval_mdd×2, 연속 손실 < 5 |
| Gate 3 | 모니터링 종료 | 자동 비교 | 적용 전 7일 vs 적용 후 성과 비교 |

- Gate 1: 이 설계서에서 구현 (위자드)
- Gate 2: engine/tuner/rollback.py 이미 구현됨 (배선만 필요)
- Gate 3: 후속 과제

---

## 11. 참고

### 컴포넌트 재사용

| 기존 컴포넌트 | 사용 위치 |
|---------------|----------|
| EquityCurveChart | Step 2, Step 5 |
| BacktestHistory | Step 1 |
| ConfirmDialog | Step 4 (경고), 닫기 확인 |

### 데이터베이스

신규 테이블 없음 — `tuning_history`, `tuning_report`는 이미 `engine/tuner/store.py`에 정의됨.
JSON 오버라이드는 파일 시스템 저장 (DB 아님).

### 목업

`docs/design/wizard-mockup.html` — 브라우저에서 열면 6단계 인터랙티브 프로토타입 확인 가능.
