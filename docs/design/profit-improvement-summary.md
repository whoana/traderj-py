# 수익률 개선 프로세스 — 요약본

> 상세: `profit-improvement-process.design.md` 참조

---

## 한눈에 보기

```
① 백테스트 선택 → ② 분석 → ③ 최적화 → ④ 적용 리뷰 → ⑤ 검증 → ⑥ 완료
```

6단계 위자드 (풀스크린 오버레이) 로 전체 사이클을 UI에서 완결.

---

## 핵심 결정 사항 (Q1~Q6 회의 결론)

| Q | 주제 | 결론 |
|---|------|------|
| Q1 | 프리셋 저장 | JSON 오버라이드 파일 (`/data/preset_overrides.json`) + presets.py 기본값 유지 |
| Q2 | 검증 기준 | 3-Gate: ①OOS 백테스트 ②48h 라이브 모니터링 ③적용 전후 비교 |
| Q3 | 레짐 매핑 | 같은 카테고리 내 교체만 자동, 임계값 변경은 승인 필요 |
| Q4 | 포지션 처리 | 상황별 차등 (이익→SL이동, 소손실→타이트닝, 큰손실→청산, BEAR→무조건 청산) |
| Q5 | 자동화 수준 | Tier별 차등 (T1 완전자동, T2 반자동, T3 수동승인) |
| Q6 | Tier 2/3 포함 | 전체 포함하되 단계적 활성화 (환경변수로 제어) |

---

## 구현 Phase

| Phase | 내용 | 파일 수 | 의존 |
|-------|------|---------|------|
| **1** | **엔진 기반 (P0)** — JSON 오버라이드 + Gate 1 검증 + Objective 개선 | 4 | 없음 |
| **2** | **위자드 API** — optimize/validate/apply/preview 엔드포인트 | 2 | Phase 1 |
| **3** | **UI 골격** — Overlay + Stepper + Nav + Context + useAsyncJob | 6 | Phase 1 |
| **4** | **UI Step 1~2** — 백테스트 선택 + 분석 (기존 API 연결) | 3 | Phase 3 |
| **5** | **UI Step 3~4** — 최적화 + 적용 리뷰 (위자드 API 연결) | 4 | Phase 2+4 |
| **6** | **UI Step 5~6** — 검증 + 완료 | 3 | Phase 5 |

```
Phase 1 ──┬──► Phase 2 ──────► Phase 5 ──► Phase 6
          └──► Phase 3 ──► Phase 4 ──┘
```

Phase 2와 3은 병렬 진행 가능.

---

## Phase 1 상세 (최우선)

| # | 작업 | 파일 |
|---|------|------|
| 1-1 | `load_preset()` — JSON 오버라이드 로더 | `engine/strategy/presets.py` |
| 1-2 | `preset_override.py` — 저장/로드/삭제 | `engine/strategy/preset_override.py` (신규) |
| 1-3 | `validators.py` — Walk-forward 검증 | `engine/backtest/validators.py` (신규) |
| 1-4 | Objective 개선 — Sharpe 복합 지표 | `engine/backtest/runners.py` |

---

## 이미 있는 것 vs 새로 만들 것

### 이미 있음 (활용)
- `engine/tuner/` 15개 모듈 (평가/최적화/적용/모니터링/롤백)
- `engine/backtest/` 4개 모드 + 분석기 + 캔들 캐시
- `api/routes/backtest.py` 6개 엔드포인트
- `ActionPanel.tsx` 3개 액션 버튼
- 11개 전략 프리셋 (STR-001~010)

### 새로 만들 것
- **엔진:** JSON 오버라이드 (preset_override.py), Walk-forward 검증 (validators.py)
- **API:** 위자드 전용 4개 엔드포인트 (wizard.py)
- **UI:** 위자드 오버레이 + 6개 스텝 + Context + 훅 (~15개 파일)

---

## Optuna Objective 변경

```
AS-IS: return_pct + profit_factor * 0.1         ← 수익률 편향, 위험
TO-BE: sharpe * 0.4 + return * 0.3 + PF * 0.2 + (1/MDD) * 0.1  ← 리스크 조정
```

---

## 3-Gate 검증

```
Gate 1 (위자드 Step 5)     Gate 2 (자동)           Gate 3 (자동)
적용 직전 OOS 백테스트     48~72h 라이브 모니터링    7일 전후 비교
─────────────────────────────────────────────────────────────
OOS 수익 > baseline+2%    MDD < eval_mdd×2        적용 후 > 적용 전
PF > 1.2                  연속 손실 < 5
MDD < baseline×1.3
거래 ≥ 10건
```

Gate 2는 `engine/tuner/rollback.py`에 이미 구현됨 (배선만 필요).

---

## 파일 맵

```
engine/
  strategy/
    presets.py              ← 수정 (load_preset 추가)
    preset_override.py      ← 신규
  backtest/
    runners.py              ← 수정 (objective 개선)
    validators.py           ← 신규

api/
  routes/
    wizard.py               ← 신규

dashboard/src/
  components/backtest/
    wizard/
      WizardOverlay.tsx     ← 신규
      WizardStepper.tsx     ← 신규
      WizardNavButtons.tsx  ← 신규
      WizardLauncher.tsx    ← 신규
      steps/
        StepBacktest.tsx    ← 신규
        StepAnalyze.tsx     ← 신규
        StepOptimize.tsx    ← 신규
        StepApply.tsx       ← 신규
        StepValidate.tsx    ← 신규
        StepComplete.tsx    ← 신규
  contexts/
    WizardContext.tsx        ← 신규
  hooks/
    useAsyncJob.ts          ← 신규
  components/ui/
    ProgressBar.tsx          ← 신규
    CompareTable.tsx         ← 신규
    ChecklistItem.tsx        ← 신규
```
