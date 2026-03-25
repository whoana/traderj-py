# 회의 보고서: 수익률 개선 프로세스

**일시**: 2026년 03월 25일
**형식**: 회의
**주제**: 수익률 개선 프로세스 초안 검토 (Q1~Q6)

---

## 참가자

| 이름 | 역할 | 관점 |
|------|------|------|
| bot-developer | 트레이딩봇 개발전문가 | 실전 트레이딩, 수익률, 과적합 방지 |
| system-architect | 시스템 아키텍트 | 아키텍처, 유지보수, 구현 복잡도 |

---

## 핵심 발견: engine/tuner/ 이미 상당 부분 구현됨

두 전문가 모두 코드 분석 후 **동일한 발견**을 보고했다:

> `engine/tuner/` 패키지에 `TunerPipeline`, `ParameterApplier`(핫 리로드), `Guardrails`(안전장치), `RollbackMonitor`(48h 모니터링 + 자동 롤백), `TunerStore`(DB 영속화)가 이미 존재한다. 초안에서 "핵심 누락"이라고 한 적용/검증의 프레임워크 코드가 사실상 구현되어 있으며, **실전 연결(배선)만 안 된 상태**다.

---

## Q1~Q6 결론

### Q1: 최적화 프리셋 저장 방식

| | bot-developer | system-architect |
|---|---|---|
| 추천 | C+A 하이브리드 (DB + JSON) | C안 (JSON 오버라이드) |
| 핵심 | TunerStore 이미 존재, 활용하라 | async 불필요, fail-safe |

**합의: C안 (JSON 오버라이드 파일) + presets.py 기본값 유지**

- `presets.py`는 "안전한 기본값(baseline)" 역할 유지
- `/data/preset_overrides.json` (Fly.io 볼륨)에 확정된 파라미터만 저장
- 엔진 부팅 시: presets.py 로드 → JSON 오버라이드 적용
- JSON 손상/누락 시 presets.py로 자동 폴백
- 변경된 파라미터만 저장 (sparse override)
- **구현 복잡도: Low** — `load_preset()` 함수 + applier에 JSON write 추가

### Q2: 검증 통과 기준

| | bot-developer | system-architect |
|---|---|---|
| 추천 | 엄격한 수치 기준 + Walk-forward | 3-Gate 파이프라인 |
| 핵심 | 과적합 방지가 최우선 | 적용 전 백테스트 검증 추가 |

**합의: 3-Gate 검증 + Walk-forward 의무화**

| Gate | 시점 | 기준 |
|------|------|------|
| Gate 1 | 적용 직전 (백테스트) | OOS 수익률 > baseline+2%, PF > 1.2, MDD < baseline×1.3, 거래 ≥ 10건 |
| Gate 2 | 적용 후 48~72h (라이브) | MDD < eval_mdd×2, 연속 손실 < 5 |
| Gate 3 | 모니터링 종료 시 | 적용 전 7일 vs 적용 후 성과 비교 |

Walk-forward 구조:
```
Window 1: [Train: D-240~D-150] → [Test: D-150~D-120]
Window 2: [Train: D-180~D-90]  → [Test: D-90~D-60]
Window 3: [Train: D-120~D-30]  → [Test: D-30~D-0]
→ OOS 전체 평균이 기준 충족해야 통과
```

현재 Optuna objective 개선 필요:
- 현재: `return_pct + profit_factor * 0.1` (수익률 편향)
- 제안: `sharpe * 0.4 + return_pct * 0.3 + PF * 0.2 + (1/MDD) * 0.1`

**구현 복잡도: Medium** — Gate 1이 핵심 신규 구현

### Q3: 레짐 매핑 변경 범위

| | bot-developer | system-architect |
|---|---|---|
| 추천 | 같은 카테고리 내 교체만 허용 | 기존 preset_map 주입 활용 |
| 핵심 | BEAR에 BULL 전략 배정 금지 | 인터페이스 이미 존재 |

**합의: 제한적 자동 제안 + 검증 필수**

- **허용**: 같은 카테고리 내 전략 교체 (예: BULL에서 STR-002→STR-009)
- **승인 필요**: 레짐 감지 임계값 변경 (Tier 3)
- **불허**: 레짐 카테고리 간 전략 교체
- STR-009/010이 현재 매핑에 미포함 → 후보에 추가하면 즉시 개선 가능
- `RegimeSwitchManager`가 이미 `preset_map` 주입 지원 → Q1의 JSON에 `regime_map` 섹션 추가
- **구현 복잡도: Low**

### Q4: 전략 전환 시 포지션 처리

| | bot-developer | system-architect |
|---|---|---|
| 추천 | 방안3 기본 + 조건부 방안1 | 현재 구조 유지 + Tier2 지연 |
| 핵심 | BEAR 전환 시 무조건 청산 | 레짐 전환 vs AI Tuner 변경 구분 |

**합의: 상황별 차등 처리**

**레짐 전환 시 (RegimeSwitchManager):**
| 조건 | 처리 |
|------|------|
| 미실현 이익 (PnL > 0) | SL을 손익분기점으로 올림 + 새 전략 TP 적용 |
| 소규모 손실 (0 > PnL > -1.5%) | SL 타이트닝 (현재 로직) |
| 큰 손실 (PnL < -1.5%) | 즉시 청산 |
| BEAR 레짐 전환 | 무조건 즉시 청산 |

**AI Tuner 파라미터 변경 시:**
- Tier 1(시그널): 기존 포지션 영향 없음 (진입 판단만 변경)
- Tier 2(리스크): 열린 포지션 있으면 "다음 포지션부터 적용"
- 방안2(독립 포지션)은 단일 페어 시스템에 비효율 → 제외

**구현 복잡도: Low** — `RegimeSwitchConfig` 하이브리드 로직 이미 존재

### Q5: 자동화 수준

| | bot-developer | system-architect |
|---|---|---|
| 추천 | 감독 있는 자동화 (Tier별 차등) | 현재 반자동화 유지 |
| 핵심 | Telegram 알림 기반 인간 감독 | Fly.io 단일 인스턴스 제약 |

**합의: Tier별 차등 자동화 (현재 구조 유지)**

| Tier | 자동화 | 인간 개입 |
|------|--------|----------|
| Tier 1 (시그널) | 완전 자동 | Telegram 알림만. 72h 모니터링 후 자동 확정/롤백 |
| Tier 2 (리스크) | 반자동 | "1시간 내 거부 없으면 적용" 알림 |
| Tier 3 (레짐) | 수동 승인 | Telegram에서 명시적 승인 |

추가 권고:
- 스케줄 분산: Tier 1=월요일, Tier 2=화요일, Tier 3=수요일 (리소스 분산)
- 하루 1회 이상 튜닝 적용 금지
- 연속 3회 롤백 → SUSPENDED → 1주 후 자동 해제
- **구현 복잡도: Low** — 이미 구현됨, 설정 조정만

### Q6: Tier 2/3 파라미터 포함

| | bot-developer | system-architect |
|---|---|---|
| 추천 | 단계적 확장, Tier 1 먼저 | 전체 포함, env var로 단계 활성화 |
| 핵심 | 검색 공간 폭발 (9→20차원) | 코드 이미 구현됨, 설정만 변경 |

**합의: 전체 포함하되 단계적 활성화**

| Phase | 기간 | 범위 | 활성화 방법 |
|-------|------|------|------------|
| Phase 1 | 즉시 | Tier 1 자동 | `TUNER_TIER2_INTERVAL_WEEKS=999` |
| Phase 2 | 4~8주 안정 후 | + Tier 2 | `TUNER_TIER2_INTERVAL_WEEKS=2` |
| Phase 3 | 추가 4주 후 | + Tier 3 | `TUNER_TIER3_INTERVAL_WEEKS=4` |

핵심 주의:
- Tier별 **독립 최적화** (동시 최적화 금지 — 20차원 탐색 불가)
- `daily_max_loss_pct`는 안전장치 → 자동 최적화에서 완전 제외
- `max_position_pct` 범위 축소: 0.05~0.30 → 0.10~0.25
- `flyctl secrets set`만으로 제어 가능 (코드 변경 없음)
- **구현 복잡도: Low** — 이미 구현 완료

---

## 우선순위 합의

| 순위 | 작업 | 근거 |
|------|------|------|
| **P0** | Q1: JSON 오버라이드 구현 | 없으면 모든 튜닝이 재시작 시 소멸 |
| **P0** | Q2: Gate 1 백테스트 검증 추가 | 과적합 방지의 핵심 |
| **P1** | Q2: Optuna objective 함수 개선 | 현재 수익률 편향, 리스크 조정 필요 |
| **P1** | Q4: 레짐 전환 포지션 처리 세분화 | BEAR 전환 시 즉시 청산 등 |
| **P2** | Q3: STR-009/010 레짐 매핑 포함 | 빠른 수익률 개선 가능 |
| **P2** | Q5: 스케줄 분산 + SUSPENDED 자동 해제 | 운영 안정성 |

---

## 핵심 인사이트

1. **"코드는 이미 있다"** — `engine/tuner/` 15개 모듈이 구현되어 있으나 실전 배선이 안 됨. 신규 개발보다 **연결(wiring)이 핵심**
2. **검증이 수익의 열쇠** — bot-developer: "아무리 좋은 최적화도 검증이 부실하면 오히려 악화". Walk-forward + 엄격한 Gate가 최우선
3. **JSON 오버라이드가 가장 시급** — system-architect: "재시작마다 튜닝이 사라지면 전체 사이클이 무의미"
4. **Objective 함수 개선** — 현재 `return_pct + PF*0.1`은 위험. 리스크 조정 복합 지표 필수
5. **BEAR 전환 = 무조건 청산** — 하락장 진입 시 포지션 유지는 치명적

---

## 향후 과제

이 회의 결론을 기반으로:
1. `docs/design/profit-improvement-process.design.md` 상세설계서 작성
2. P0 작업부터 구현 시작 (JSON 오버라이드 + Gate 1 검증)

---

*이 보고서는 AI 에이전트 팀 회의 시뮬레이션을 통해 자동 생성되었습니다.*
