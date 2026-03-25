# 수익률 개선 위자드 UI 설계서

> **상태:** 초안 — 회의 결과 기반
> **작성일:** 2026-03-25
> **참가자:** UI 프론트 개발자, UI/UX 디자이너
> **목업:** [wizard-mockup.html](wizard-mockup.html) (브라우저에서 열기)

---

## 1. 핵심 결정

### 풀스크린 오버레이 방식 채택

모달도 아니고 별도 페이지도 아닌, **풀스크린 오버레이** 방식.

| 비교 | 모달 | 별도 페이지 | 풀스크린 오버레이 |
|------|------|------------|-----------------|
| 공간 | 좁음 | 넓음 | 넓음 |
| 컨텍스트 유지 | O | X | O |
| 모바일 UX | 스크롤 어려움 | 좋음 | 좋음 |
| 상태 관리 | 쉬움 | 복잡 | 쉬움 |

- ESC / 뒤로가기로 닫기 가능
- URL 변경 없이 백테스트 페이지 상태 유지
- `<dialog>` + `showModal()` 패턴 (기존 ConfirmDialog 확장)

### 6단계 스텝 위자드

```
① 백테스트 선택 → ② 분석 → ③ 최적화 → ④ 적용 리뷰 → ⑤ 검증 → ⑥ 완료
```

스텝 인디케이터: 상단 고정, 완료=초록, 현재=파랑(pulse), 미완료=회색
네비게이션: 이전/다음 버튼 하단 고정, 완료된 스텝 클릭 가능

---

## 2. 각 스텝 상세

### Step 1: 백테스트 선택
- 현재 백테스트 결과 요약 카드 (자동 선택)
- 히스토리에서 다른 결과 선택 가능
- "새 백테스트 실행" 옵션
- **다음 조건:** 유효한 결과 선택됨

### Step 2: 분석
- 핵심 지표 4-column 카드 (수익률, 승률, MDD, Sharpe)
- Equity Curve 차트 (EquityCurveChart 재사용)
- AI 인사이트 리스트
- **개선 영역 체크리스트** (사용자가 원하는 항목만 선택):
  - [ ] 전략 전환
  - [ ] 레짐 매핑 최적화
  - [ ] 파라미터 튜닝
- **다음 조건:** 분석 로딩 완료

### Step 3: 최적화
- 선택된 항목별 실행 (순차)
- Optuna 프로그레스 바 + 실시간 최적값 표시
- Baseline vs Optimized 비교 카드
- Top 3 후보 테이블 + 파라미터 상세 (접기/펼치기)
- **"현재 최적값으로 진행" 조기 중단 버튼**
- **다음 조건:** 모든 선택 작업 완료

### Step 4: 적용 리뷰
- Before / After 비교 테이블 (2열 그리드)
- 변경사항 체크리스트 (적용할 항목 선택)
- 파라미터 상세 (details/summary)
- "검증 없이 바로 적용" 옵션 (경고 표시)
- **다음 조건:** 적용 항목 1개 이상 선택

### Step 5: 검증
- 검증 백테스트 실행 (최적화에 사용되지 않은 기간)
- 최적화 기간 vs 검증 기간 비교 테이블
- 5개 항목 체크리스트 (수익률 > 0, MDD 범위 내, PF > 1.0, 거래 ≥ 5, Sharpe > 0)
- 판정: Pass(초록) / Warn(노랑) / Fail(빨강)
- **건너뛰기 가능** (경고 문구 포함)

### Step 6: 완료
- 축하 메시지 + 체크 아이콘
- 적용된 변경사항 요약 카드
- 예상 개선폭 표시
- "대시보드로 돌아가기" / "새 백테스트 시작" 버튼

---

## 3. 컴포넌트 구조

```
components/backtest/wizard/
  WizardOverlay.tsx       풀스크린 오버레이 셸
  WizardStepper.tsx       스텝 인디케이터
  WizardNavButtons.tsx    이전/다음 하단 버튼
  steps/
    StepBacktest.tsx      Step 1
    StepAnalyze.tsx       Step 2
    StepOptimize.tsx      Step 3
    StepApply.tsx         Step 4
    StepValidate.tsx      Step 5
    StepDeploy.tsx        Step 6

contexts/
  WizardContext.tsx        useReducer 기반 상태 관리

hooks/
  useAsyncJob.ts          비동기 작업 폴링 (최적화/검증 공통)

components/ui/
  ProgressBar.tsx         진행률 표시 (신규)
  CompareTable.tsx        Before/After 비교 (신규)
  ChecklistItem.tsx       체크 가능 항목 (신규)
```

### 기존 컴포넌트 재사용

| 컴포넌트 | 사용 스텝 |
|----------|----------|
| EquityCurveChart | Step 2, 5 |
| BacktestHistory | Step 1 |
| ConfirmDialog | Step 4 (경고), 닫기 확인 |

---

## 4. 데이터 흐름

- `useReducer` + `Context`로 위자드 전체 상태 관리
- 각 스텝은 `useWizard()` 훅으로 상태 접근
- 비동기 작업(최적화, 검증)은 `useAsyncJob` 훅으로 통합

### 진입점

```tsx
// backtest/page.tsx — ActionPanel 위치를 WizardLauncher로 교체
{status === "done" && jobId && (
  <WizardLauncher
    jobId={jobId}
    result={result}
    startDate={startDate}
    endDate={endDate}
  />
)}
```

---

## 5. 구현 우선순위

| Phase | 내용 | 범위 |
|-------|------|------|
| Phase 1 | 골격 | WizardOverlay + Stepper + NavButtons + Context |
| Phase 2 | Step 1~2 | 백테스트 선택 + 분석 (기존 API 연결) |
| Phase 3 | Step 3~4 | 최적화 + 적용 (ActionPanel 로직 이전) |
| Phase 4 | Step 5~6 | 검증 + 배포 + 완료 |

---

## 6. 시각 목업

`docs/design/wizard-mockup.html`을 브라우저에서 열면 인터랙티브 프로토타입 확인 가능.
- 6개 스텝 전환 (이전/다음 클릭, 키보드 화살표)
- 스텝 인디케이터 상태 변경
- 다크 모드 기준 디자인
- 모바일 반응형 지원
