# Dashboard Help Feature Plan

## 1. Overview

대시보드의 모든 라벨, 버튼, 타이틀, 아이콘, 상태값에 대한 도움말 기능.
TopNav 우측 Logout 왼쪽에 `?` 버튼을 배치하고, 클릭 시 도움말 패널을 표시한다.

## 2. UI 구조

```
TopNav: [TraderJ] [Dashboard] [Analytics] [AI Tuner] [Control] [Settings]   [?] [Logout]
                                                                             ↓
                                                                     ┌─────────────────┐
                                                                     │ 🔍 검색...       │
                                                                     ├─────────────────┤
                                                                     │ 주요 항목         │
                                                                     │ • Total Balance  │
                                                                     │ • Regime         │
                                                                     │ • AI Tuner       │
                                                                     │ • Win Rate       │
                                                                     │ ...              │
                                                                     ├─────────────────┤
                                                                     │ 페이지별 가이드   │
                                                                     │ • Home           │
                                                                     │ • Analytics      │
                                                                     │ • AI Tuner       │
                                                                     │ • Control        │
                                                                     │ • Settings       │
                                                                     └─────────────────┘
```

- **?** 버튼 클릭 → 우측 상단에서 드롭다운 패널 오픈
- 모바일: 전체 화면 오버레이 (시트)
- ESC 또는 외부 클릭으로 닫기

## 3. 도움말 데이터 구조

```typescript
interface HelpEntry {
  id: string;            // 고유 키 (예: "total_balance")
  term: string;          // 검색/표시 용어 (예: "Total Balance")
  termKo: string;        // 한국어 용어 (예: "총 잔고")
  category: HelpCategory;
  page: PageName[];      // 표시되는 페이지들
  description: string;   // 한국어 설명 (1~3문장)
  related?: string[];    // 관련 항목 id 목록
}

type HelpCategory = "metric" | "status" | "action" | "concept" | "page" | "process";
type PageName = "home" | "analytics" | "tuner" | "control" | "settings";
```

## 4. 도움말 항목 목록 (75항목)

### 4.1 핵심 지표 (Metrics) — 12항목

| ID | Term | 한국어 | 설명 | 페이지 |
|----|------|--------|------|--------|
| total_balance | Total Balance | 총 잔고 | 현금(KRW) + BTC 보유분의 현재가 환산 합계. 초기 투자금 대비 수익률 산정 기준. | home |
| return_pct | Return | 수익률 | 초기 투자금(5천만원) 대비 현재 총 잔고의 변화율(%). 양수=수익, 음수=손실. | home |
| btc_price | BTC Price | BTC 가격 | 업비트 BTC/KRW 현재가. 24시간 전 대비 변화율(%) 함께 표시. | home |
| total_pnl | Total PnL | 총 손익 | 전체 거래에서 발생한 실현 손익 합계(KRW). | analytics |
| total_trades | Total Trades | 총 거래 수 | 선택 기간 내 완료된 매매 쌍(매수+매도) 수. | analytics |
| win_rate | Win Rate | 승률 | 수익을 낸 거래의 비율(%). 40% 이상이면 양호. | analytics, tuner |
| max_drawdown | Max Drawdown (MDD) | 최대 낙폭 | 고점 대비 최대 하락폭(%). 값이 클수록 위험. 10% 이하 권장. | analytics, tuner |
| profit_factor | PF (Profit Factor) | 수익 팩터 | 총수익 / 총손실. 1.0 이상이면 수익, 1.5 이상이면 양호. | tuner |
| fear_greed | Fear & Greed | 공포/탐욕 지수 | 시장 심리 지표(0~100). 0=극도 공포, 100=극도 탐욕. 매크로 점수에 반영. | home, settings |
| kimchi_premium | Kimchi Premium | 김치 프리미엄 | 한국 거래소와 해외 거래소 간 BTC 가격 차이(%). 양수=국내 프리미엄. | home, settings |
| funding_rate | Funding Rate | 펀딩비 | 선물시장 롱/숏 포지션 간 지불하는 수수료율. 양수=롱 과열, 음수=숏 과열. | home, settings |
| btc_dominance | BTC Dominance | BTC 도미넌스 | 전체 암호화폐 시가총액 중 BTC 비중(%). 높을수록 BTC 강세. | home, settings |

### 4.2 상태값 (Status) — 12항목

| ID | Term | 한국어 | 설명 |
|----|------|--------|------|
| engine_running | Running | 실행 중 | 엔진이 정상 작동 중. 자동 매매가 진행됩니다. |
| engine_stopped | Stopped | 정지 | 엔진이 멈춘 상태. 새 거래가 발생하지 않습니다. |
| regime_bull_trend | Bull Trend | 상승 추세 | ADX와 BB Width 분석 결과 상승 추세로 판단. 추세추종 전략 적용. |
| regime_bear_trend | Bear Trend | 하락 추세 | 하락 추세로 판단. 방어적 전략 적용 또는 매매 자제. |
| regime_ranging | Ranging | 횡보 | 뚜렷한 방향 없이 횡보 중. 하이브리드/반전 전략 적용. |
| tuner_idle | Idle (Tuner) | 대기 | AI Tuner가 대기 중. 다음 정기 튜닝 스케줄을 기다리는 상태. |
| tuner_monitoring | Monitoring | 모니터링 | 파라미터 변경 후 성능을 관찰 중. 7일간 모니터링 후 확정 또는 롤백. |
| tuner_suspended | Suspended | 중단 | 연속 롤백(3회)으로 자동 중단. 수동 재개 필요. |
| tuning_confirmed | Confirmed | 확정 | 튜닝 결과가 모니터링을 통과하여 파라미터가 확정됨. |
| tuning_rolled_back | Rolled Back | 롤백됨 | 성능 악화로 이전 파라미터로 복원됨. |
| tuning_pending | Pending Approval | 승인 대기 | Tier 3 변경은 사람의 승인이 필요. Tuner 페이지에서 승인/거부. |
| circuit_closed | Circuit Closed | 정상 | LLM Provider 회로 차단기 정상 상태. API 호출 가능. |

### 4.3 조작 버튼 (Actions) — 15항목

| ID | Term | 한국어 | 설명 |
|----|------|--------|------|
| emergency_stop | Emergency Stop | 긴급 정지 | 엔진을 즉시 정지. 열린 포지션은 유지되며 새 거래만 중단. |
| engine_start | Start | 엔진 시작 | 정지된 엔진을 시작하여 자동 매매를 재개합니다. |
| engine_restart | Restart | 재시작 | 엔진을 재시작합니다. 일시적 중단 후 자동 복구. |
| strategy_switch | Strategy Switch | 전략 전환 | 현재 활성 전략 프리셋을 변경합니다. 수동 전환 시 auto-regime 무시. |
| close_position | Close Position | 포지션 종료 | 현재 열린 포지션을 시장가로 즉시 청산합니다. |
| set_sl | Set SL | 손절가 설정 | Stop Loss 가격을 수동으로 조정합니다. 가격 도달 시 자동 청산. |
| set_tp | Set TP | 익절가 설정 | Take Profit 가격을 수동으로 조정합니다. 가격 도달 시 자동 청산. |
| run_tuning | Run Tuning | 튜닝 실행 | 선택한 Tier에 대해 AI 튜닝을 수동으로 실행합니다. |
| rollback | Rollback | 롤백 | 모니터링 중인 튜닝을 취소하고 이전 파라미터로 복원합니다. |
| approve | Approve | 승인 | Tier 3 (Regime) 파라미터 변경을 승인합니다. |
| reject | Reject | 거부 | Tier 3 (Regime) 파라미터 변경을 거부합니다. |
| register_passkey | Register Passkey | 패스키 등록 | Face ID/Touch ID 등 생체인증을 등록하여 비밀번호 없이 로그인. |
| remove_passkey | Remove Passkey | 패스키 삭제 | 등록된 생체인증 키를 제거합니다. |
| retry | Retry | 재시도 | 데이터 로딩 실패 시 다시 요청합니다. |
| logout | Logout | 로그아웃 | 현재 세션을 종료합니다. |

### 4.4 핵심 개념 (Concepts) — 16항목

| ID | Term | 한국어 | 설명 |
|----|------|--------|------|
| regime | Regime | 시장 체제 | ADX + Bollinger Band 폭으로 감지한 시장 상태. Bull/Bear + High/Low Vol 4가지. |
| confidence | Confidence | 체제 신뢰도 | 현재 감지된 Regime의 확신도(0~1). 높을수록 신뢰할 수 있음. |
| preset | Strategy Preset | 전략 프리셋 | STR-001~008 중 하나. 각 프리셋은 매수/매도 기준, TF 가중치 등을 정의. |
| tier_1 | Tier 1 (Signal) | 시그널 파라미터 | 매수/매도 임계값, 점수 가중치 등. 주간 자동 조정. |
| tier_2 | Tier 2 (Risk) | 리스크 파라미터 | 포지션 크기, 손절 비율 등. 2주마다 조정. |
| tier_3 | Tier 3 (Regime) | 체제 파라미터 | 체제 전환 임계값. 월간 조정 + 사람 승인 필요. |
| llm_budget | LLM Budget | LLM 예산 | AI 튜닝에 사용하는 Claude/OpenAI API 비용 한도(월 $5). |
| circuit_breaker | Circuit Breaker | 서킷 브레이커 | LLM Provider 장애 시 자동 차단. closed=정상, open=차단. |
| macro_score | Market Score | 매크로 점수 | Fear/Greed, 김프, 펀딩비 등을 종합한 시장 환경 점수(0~1). |
| sl | Stop Loss (SL) | 손절가 | 설정 가격 이하로 떨어지면 자동 매도하여 손실을 제한. |
| tp | Take Profit (TP) | 익절가 | 설정 가격 이상으로 오르면 자동 매도하여 수익을 확정. |
| trailing_stop | Trailing Stop | 추적 손절 | 가격 상승에 따라 손절가도 함께 올라가는 동적 손절. |
| atr | ATR | 평균진폭 | Average True Range. 가격 변동성 측정. 포지션 크기와 손절폭 계산에 사용. |
| pnl | PnL | 손익 | Profit and Loss. 수익(양수)과 손실(음수)을 나타냄. |
| paper_mode | Paper Trading | 모의 매매 | 실제 자금 없이 가상으로 매매를 시뮬레이션하는 모드. |
| optuna | Optuna | 통계 최적화 | 파라미터 최적화 프레임워크. AI Tuner가 백테스트 성과를 극대화하는 파라미터를 탐색. |

### 4.5 페이지 가이드 (Pages) — 5항목

| ID | Page | 설명 |
|----|------|------|
| page_home | Home | 실시간 요약 대시보드. 잔고, 수익률, BTC 가격, 시장 체제, 차트, AI Tuner 상태, 포지션, 매크로 지표를 한눈에 확인. |
| page_analytics | Analytics | 기간별 성과 분석. 누적 PnL 차트, 일별 PnL 차트, 최근 주문 내역 테이블. 7D~90D 기간 선택. |
| page_tuner | AI Tuner | AI 자동 튜닝 관리. 튜너 상태 확인, 수동 튜닝 실행, 롤백, Tier 3 승인, 튜닝 히스토리 조회. |
| page_control | Control | 엔진 및 전략 제어. 엔진 시작/정지/재시작, 전략 프리셋 전환, 포지션 청산, SL/TP 수동 조정. |
| page_settings | Settings | 시스템 설정. 패스키 인증 관리, Regime/Risk/Macro/Strategy 현재 상태 확인. |

### 4.6 전략 프리셋 (Presets) — 8항목

| ID | Term | 설명 |
|----|------|------|
| str_001 | STR-001 Conservative Trend | 4h 기준 보수적 추세추종. 1h/4h/1d 멀티TF. 매크로 10%. Bull(Low Vol) 시장용. |
| str_002 | STR-002 Aggressive Trend | 1h 기준 공격적 추세추종. 낮은 진입 기준. Bull(High Vol) 시장용. |
| str_003 | STR-003 Hybrid Reversal | 4h/1d 하이브리드 반전. 그리드서치 최고 성과. Ranging(High Vol) 시장용. |
| str_004 | STR-004 Majority Vote | 다수결 진입 추세추종. 1h/4h 기반. 수동 전환 전용. |
| str_005 | STR-005 Low-Frequency | 4h/1d 저빈도 하이브리드. 높은 진입 기준. Ranging(Low Vol) 시장용. |
| str_006 | STR-006 Scalper | 1h/4h 단타. 모멘텀 가중치 높음. 수동 전환 전용. |
| str_007 | STR-007 Bear Defensive | 약세장 방어. 극단적 과매도 반전만 매수. Bear(High Vol) 시장용. |
| str_008 | STR-008 Bear Cautious | 약세장 신중한 반전. STR-007보다 완화. Bear(Low Vol) 시장용. |

### 4.7 AI 전략 선택 과정 (Process) — 10항목

AI Tuner가 전략 파라미터를 선택하고 적용하는 전체 과정을 단계별로 설명합니다.

| ID | Term | 한국어 | 설명 |
|----|------|--------|------|
| process_overview | AI Tuning Process | AI 튜닝 전체 흐름 | 매주 AI가 지난 거래 성적을 분석하고, 더 나은 설정값을 찾아 적용한 뒤, 48시간 감시 후 확정하거나 자동 롤백합니다. 평가 → 최적화 → 적용 → 감시 4단계로 진행됩니다. |
| process_evaluate | Step 1: Evaluate | 1단계: 평가 | 지난 7일간 거래 기록을 분석하여 성적표를 만듭니다. 승률, 수익팩터, 최대낙폭, 시그널 정확도를 계산합니다. 최소 3건 이상의 거래가 있어야 평가가 진행됩니다. 성적이 이미 양호하면(PF>1.5, 승률>40%) 튜닝을 건너뜁니다. |
| process_optimize | Step 2: Optimize | 2단계: 최적화 | 통계 엔진(Optuna)이 50가지 설정 조합을 백테스트 시뮬레이션하여 상위 3개 후보를 추출합니다. 동시에 AI(Claude)가 성적표를 읽고 "이 시장에서는 어떤 후보가 적합한지" 분석합니다. AI가 최종 후보 1개를 선택합니다. |
| process_safety_bt | Safety Backtest | 안전 백테스트 | 최적화로 선택된 후보를 실제 적용 전에 최근 데이터로 백테스트합니다. AI가 백테스트 결과를 평가하여 "적용해도 안전한지" 최종 판단합니다. 위험하다고 판단되면 적용하지 않습니다. |
| process_apply | Step 3: Apply | 3단계: 적용 | 안전 검증을 통과한 새 파라미터를 실시간 봇에 적용합니다. 가드레일이 작동하여 한 번에 최대 20%까지만 변경 가능하고, 허용 범위를 벗어나면 자동으로 범위 내로 클램핑됩니다. 비중값은 합계가 1.0이 되도록 자동 정규화됩니다. |
| process_monitor | Step 4: Monitor | 4단계: 감시 | 새 설정 적용 후 48시간 동안 실시간 모니터링합니다. 최대낙폭이 기준의 2배를 넘거나 연속 5회 손실 시 자동 롤백됩니다. 48시간 무사 통과하면 새 설정이 확정됩니다. |
| process_optuna_role | Optuna (Statistics) | 통계 엔진 역할 | Optuna는 수학적 최적화 프레임워크입니다. 파라미터 조합을 생성하고 Walk-Forward 백테스트로 성과를 측정하여 상위 후보를 추출합니다. AI 없이도 독립적으로 동작 가능합니다(Degraded Mode). |
| process_claude_role | Claude (AI Analysis) | AI 분석 역할 | Claude는 성적표를 읽고 시장 상황을 고려한 진단을 합니다. 근본 원인 분석(예: "횡보장에서 추세추종 전략이 맞지 않음"), 파라미터 조정 방향 추천, Optuna 후보 중 최적 선택, 안전 백테스트 결과 평가를 담당합니다. |
| process_provider_chain | Provider Fallback Chain | AI 장애 대응 | 1순위 Claude → 2순위 OpenAI → 3순위 Degraded Mode(AI 없이 통계만) 3중 구조입니다. 각 서비스에 서킷 브레이커가 적용되어 3회 연속 실패 시 10분간 차단 후 재시도합니다. 월 $5 예산 초과 시 자동으로 Degraded Mode로 전환됩니다. |
| process_guardrails | Guardrails | 안전장치 | 변경 전: 최대 변경폭 ±20%, 절대 범위 제한, Tier 2 동일 방향 연속 차단, Tier 3 사람 승인 필수. 변경 후: 48시간 모니터링, 낙폭 초과 시 자동 롤백, 연속 5회 손실 시 자동 롤백, 연속 3회 롤백 시 튜너 일시 중지(사람 개입 필요). |

## 5. 구현 계획

### 5.1 파일 구조

```
dashboard/src/
├── components/
│   └── help/
│       ├── HelpButton.tsx         # TopNav에 배치되는 ? 버튼
│       ├── HelpPanel.tsx          # 드롭다운 패널 (검색 + 목록)
│       └── helpData.ts            # 도움말 데이터 (65항목)
└── ...
```

### 5.2 컴포넌트 설계

#### HelpButton
- TopNav의 Logout 왼쪽에 `?` 아이콘 버튼 배치
- 클릭 시 HelpPanel 토글
- 활성 시 accent 색상 강조

#### HelpPanel
- 우측 상단 고정 드롭다운 (데스크톱: w-80, 모바일: 전체 폭)
- **상단**: 검색 입력란 (한국어/영어 모두 검색 가능)
- **중단**: 주요 항목 바로가기 링크 (8~10개)
  - Total Balance, Return, Regime, Win Rate, AI Tuner, Stop Loss, Strategy Preset, LLM Budget
- **하단**: 페이지별 가이드 링크 (5개)
- 검색 입력 시: 실시간 필터링으로 매칭 항목 표시
- 항목 클릭 시: 인라인 확장으로 설명 표시 (관련 항목 링크 포함)
- ESC 또는 외부 클릭으로 닫기

#### helpData.ts
- 위 75개 항목을 `HelpEntry[]` 배열로 정의
- term + termKo 모두 검색 대상
- category별 아이콘: metric=차트, status=원, action=번개, concept=책, page=페이지, process=화살표흐름

### 5.3 검색 로직

```typescript
function searchHelp(query: string): HelpEntry[] {
  const q = query.toLowerCase().trim();
  if (!q) return []; // 빈 입력 시 주요 항목 표시

  return helpEntries.filter(entry =>
    entry.term.toLowerCase().includes(q) ||
    entry.termKo.includes(q) ||
    entry.description.includes(q) ||
    entry.id.includes(q)
  );
}
```

### 5.4 주요 항목 바로가기 (기본 표시)

검색란이 비어있을 때 표시되는 항목 (12개):

1. **AI Tuning Process** — AI 전략 선택 전체 흐름
2. **Total Balance** — 총 잔고
3. **Return** — 수익률
4. **Regime** — 시장 체제
5. **Win Rate** — 승률
6. **AI Tuner** — AI 자동 튜닝
7. **Stop Loss / Take Profit** — 손절/익절
8. **Strategy Preset** — 전략 프리셋
9. **Guardrails** — 안전장치
10. **LLM Budget** — AI 비용
11. **Profit Factor** — 수익 팩터
12. **Emergency Stop** — 긴급 정지

### 5.5 페이지별 가이드

각 페이지에 대한 개요 설명 + 해당 페이지의 항목 필터 링크:
- Home (8항목) → Analytics (4항목) → AI Tuner (12항목) → Control (10항목) → Settings (5항목)

## 6. 구현 순서

| Step | 작업 | 파일 |
|------|------|------|
| 1 | helpData.ts 생성 (65항목 데이터) | components/help/helpData.ts |
| 2 | HelpPanel 컴포넌트 구현 | components/help/HelpPanel.tsx |
| 3 | HelpButton 컴포넌트 구현 | components/help/HelpButton.tsx |
| 4 | TopNav에 HelpButton 삽입 | components/layout/TopNav.tsx |
| 5 | 빌드 테스트 + 배포 | - |

예상 변경: 4개 파일 신규 생성, 1개 파일 수정

## 7. 디자인 노트

- 다크 테마 기본, 기존 디자인 시스템 색상 활용
- 카테고리별 태그 색상: metric(accent), status(warning), action(error), concept(muted), page(running), process(up/green)
- 모바일 우선: 터치 친화적 목록 간격
- 애니메이션: 패널 슬라이드 다운 (150ms ease-out)
- 접근성: 키보드 네비게이션, aria-label, focus trap
