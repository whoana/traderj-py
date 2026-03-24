export type HelpCategory = "metric" | "status" | "action" | "concept" | "page" | "process" | "preset";

export interface HelpEntry {
  id: string;
  term: string;
  termKo: string;
  category: HelpCategory;
  description: string;
  related?: string[];
}

export const CATEGORY_LABELS: Record<HelpCategory, { label: string; color: string }> = {
  metric: { label: "Metric", color: "text-accent" },
  status: { label: "Status", color: "text-status-warning" },
  action: { label: "Action", color: "text-status-error" },
  concept: { label: "Concept", color: "text-text-secondary" },
  page: { label: "Page", color: "text-status-running" },
  process: { label: "Process", color: "text-up" },
  preset: { label: "Preset", color: "text-accent" },
};

export const FEATURED_IDS = [
  "process_overview",
  "total_balance",
  "return_pct",
  "regime",
  "win_rate",
  "page_tuner",
  "sl",
  "preset",
  "process_guardrails",
  "llm_budget",
  "profit_factor",
  "emergency_stop",
];

export const helpEntries: HelpEntry[] = [
  // ── Metrics (12) ──
  { id: "total_balance", term: "Total Balance", termKo: "총 잔고", category: "metric", description: "현금(KRW) + BTC 보유분의 현재가 환산 합계. 초기 투자금 대비 수익률 산정 기준.", related: ["return_pct", "pnl"] },
  { id: "return_pct", term: "Return", termKo: "수익률", category: "metric", description: "초기 투자금(5천만원) 대비 현재 총 잔고의 변화율(%). 양수=수익, 음수=손실.", related: ["total_balance", "pnl"] },
  { id: "btc_price", term: "BTC Price", termKo: "BTC 가격", category: "metric", description: "업비트 BTC/KRW 현재가. 24시간 전 대비 변화율(%) 함께 표시." },
  { id: "total_pnl", term: "Total PnL", termKo: "총 손익", category: "metric", description: "전체 거래에서 발생한 실현 손익 합계(KRW).", related: ["pnl", "win_rate"] },
  { id: "total_trades", term: "Total Trades", termKo: "총 거래 수", category: "metric", description: "선택 기간 내 완료된 매매 쌍(매수+매도) 수." },
  { id: "win_rate", term: "Win Rate", termKo: "승률", category: "metric", description: "수익을 낸 거래의 비율(%). 40% 이상이면 양호.", related: ["profit_factor", "total_trades"] },
  { id: "max_drawdown", term: "Max Drawdown (MDD)", termKo: "최대 낙폭", category: "metric", description: "고점 대비 최대 하락폭(%). 값이 클수록 위험. 10% 이하 권장.", related: ["process_monitor"] },
  { id: "profit_factor", term: "Profit Factor (PF)", termKo: "수익 팩터", category: "metric", description: "총수익 / 총손실. 1.0 이상이면 수익, 1.5 이상이면 양호.", related: ["win_rate", "total_pnl"] },
  { id: "fear_greed", term: "Fear & Greed", termKo: "공포/탐욕 지수", category: "metric", description: "시장 심리 지표(0~100). 0=극도 공포, 100=극도 탐욕. 매크로 점수에 반영.", related: ["macro_score"] },
  { id: "kimchi_premium", term: "Kimchi Premium", termKo: "김치 프리미엄", category: "metric", description: "한국 거래소와 해외 거래소 간 BTC 가격 차이(%). 양수=국내 프리미엄.", related: ["macro_score"] },
  { id: "funding_rate", term: "Funding Rate", termKo: "펀딩비", category: "metric", description: "선물시장 롱/숏 포지션 간 지불하는 수수료율. 양수=롱 과열, 음수=숏 과열.", related: ["macro_score"] },
  { id: "btc_dominance", term: "BTC Dominance", termKo: "BTC 도미넌스", category: "metric", description: "전체 암호화폐 시가총액 중 BTC 비중(%). 높을수록 BTC 강세.", related: ["macro_score"] },

  // ── Status (12) ──
  { id: "engine_running", term: "Running", termKo: "실행 중", category: "status", description: "엔진이 정상 작동 중. 자동 매매가 진행됩니다." },
  { id: "engine_stopped", term: "Stopped", termKo: "정지", category: "status", description: "엔진이 멈춘 상태. 새 거래가 발생하지 않습니다." },
  { id: "regime_bull_trend", term: "Bull Trend", termKo: "상승 추세", category: "status", description: "ADX와 BB Width 분석 결과 상승 추세로 판단. 추세추종 전략 적용.", related: ["regime"] },
  { id: "regime_bear_trend", term: "Bear Trend", termKo: "하락 추세", category: "status", description: "하락 추세로 판단. 방어적 전략 적용 또는 매매 자제.", related: ["regime"] },
  { id: "regime_ranging", term: "Ranging", termKo: "횡보", category: "status", description: "뚜렷한 방향 없이 횡보 중. 하이브리드/반전 전략 적용.", related: ["regime"] },
  { id: "tuner_idle", term: "Idle (Tuner)", termKo: "대기", category: "status", description: "AI Tuner가 대기 중. 다음 정기 튜닝 스케줄을 기다리는 상태.", related: ["process_overview"] },
  { id: "tuner_monitoring", term: "Monitoring (Tuner)", termKo: "모니터링", category: "status", description: "파라미터 변경 후 성능을 관찰 중. 48시간 후 확정 또는 롤백.", related: ["process_monitor"] },
  { id: "tuner_suspended", term: "Suspended (Tuner)", termKo: "중단", category: "status", description: "연속 롤백(3회)으로 자동 중단. 수동 재개 필요.", related: ["process_guardrails"] },
  { id: "tuning_confirmed", term: "Confirmed", termKo: "확정", category: "status", description: "튜닝 결과가 모니터링을 통과하여 파라미터가 확정됨.", related: ["process_monitor"] },
  { id: "tuning_rolled_back", term: "Rolled Back", termKo: "롤백됨", category: "status", description: "성능 악화로 이전 파라미터로 복원됨.", related: ["rollback"] },
  { id: "tuning_pending", term: "Pending Approval", termKo: "승인 대기", category: "status", description: "Tier 3 변경은 사람의 승인이 필요. Tuner 페이지에서 승인/거부.", related: ["tier_3", "approve"] },
  { id: "circuit_closed", term: "Circuit Closed/Open", termKo: "서킷 상태", category: "status", description: "LLM Provider 회로 차단기 상태. closed=정상(API 호출 가능), open=차단(장애 감지).", related: ["circuit_breaker"] },

  // ── Actions (15) ──
  { id: "emergency_stop", term: "Emergency Stop", termKo: "긴급 정지", category: "action", description: "엔진을 즉시 정지. 열린 포지션은 유지되며 새 거래만 중단.", related: ["engine_running"] },
  { id: "engine_start", term: "Start", termKo: "엔진 시작", category: "action", description: "정지된 엔진을 시작하여 자동 매매를 재개합니다." },
  { id: "engine_restart", term: "Restart", termKo: "재시작", category: "action", description: "엔진을 재시작합니다. 일시적 중단 후 자동 복구." },
  { id: "strategy_switch", term: "Strategy Switch", termKo: "전략 전환", category: "action", description: "현재 활성 전략 프리셋을 변경합니다. 수동 전환 시 auto-regime 무시.", related: ["preset", "regime"] },
  { id: "close_position", term: "Close Position", termKo: "포지션 종료", category: "action", description: "현재 열린 포지션을 시장가로 즉시 청산합니다." },
  { id: "set_sl", term: "Set SL", termKo: "손절가 설정", category: "action", description: "Stop Loss 가격을 수동으로 조정합니다. 가격 도달 시 자동 청산.", related: ["sl"] },
  { id: "set_tp", term: "Set TP", termKo: "익절가 설정", category: "action", description: "Take Profit 가격을 수동으로 조정합니다. 가격 도달 시 자동 청산.", related: ["tp"] },
  { id: "run_tuning", term: "Run Tuning", termKo: "튜닝 실행", category: "action", description: "선택한 Tier에 대해 AI 튜닝을 수동으로 실행합니다.", related: ["process_overview"] },
  { id: "rollback", term: "Rollback", termKo: "롤백", category: "action", description: "모니터링 중인 튜닝을 취소하고 이전 파라미터로 복원합니다.", related: ["tuning_rolled_back"] },
  { id: "approve", term: "Approve", termKo: "승인", category: "action", description: "Tier 3 (Regime) 파라미터 변경을 승인합니다.", related: ["tier_3", "tuning_pending"] },
  { id: "reject", term: "Reject", termKo: "거부", category: "action", description: "Tier 3 (Regime) 파라미터 변경을 거부합니다.", related: ["tier_3"] },
  { id: "register_passkey", term: "Register Passkey", termKo: "패스키 등록", category: "action", description: "Face ID/Touch ID 등 생체인증을 등록하여 비밀번호 없이 로그인." },
  { id: "remove_passkey", term: "Remove Passkey", termKo: "패스키 삭제", category: "action", description: "등록된 생체인증 키를 제거합니다." },
  { id: "retry", term: "Retry", termKo: "재시도", category: "action", description: "데이터 로딩 실패 시 다시 요청합니다." },
  { id: "logout", term: "Logout", termKo: "로그아웃", category: "action", description: "현재 세션을 종료합니다." },

  // ── Concepts (16) ──
  { id: "regime", term: "Regime", termKo: "시장 체제", category: "concept", description: "ADX + Bollinger Band 폭으로 감지한 시장 상태. Bull/Bear + High/Low Vol 4가지.", related: ["regime_bull_trend", "regime_bear_trend", "regime_ranging", "confidence"] },
  { id: "confidence", term: "Confidence", termKo: "체제 신뢰도", category: "concept", description: "현재 감지된 Regime의 확신도(0~1). 높을수록 신뢰할 수 있음.", related: ["regime"] },
  { id: "preset", term: "Strategy Preset", termKo: "전략 프리셋", category: "concept", description: "STR-001~008 중 하나. 각 프리셋은 매수/매도 기준, TF 가중치 등을 정의.", related: ["strategy_switch", "str_001"] },
  { id: "tier_1", term: "Tier 1 (Signal)", termKo: "시그널 파라미터", category: "concept", description: "매수/매도 임계값, 점수 가중치 등. 매주 자동 조정. 가장 안전한 등급.", related: ["process_optimize", "run_tuning"] },
  { id: "tier_2", term: "Tier 2 (Risk)", termKo: "리스크 파라미터", category: "concept", description: "포지션 크기, 손절 비율 등. 2주마다 조정. 같은 방향 연속 변경 불가.", related: ["process_apply", "sl"] },
  { id: "tier_3", term: "Tier 3 (Regime)", termKo: "체제 파라미터", category: "concept", description: "체제 전환 임계값. 월간 조정 + 사람 승인 필요. 가장 신중한 등급.", related: ["approve", "tuning_pending"] },
  { id: "llm_budget", term: "LLM Budget", termKo: "LLM 예산", category: "concept", description: "AI 튜닝에 사용하는 Claude/OpenAI API 비용 한도(월 $5). 초과 시 Degraded Mode 전환.", related: ["process_provider_chain"] },
  { id: "circuit_breaker", term: "Circuit Breaker", termKo: "서킷 브레이커", category: "concept", description: "LLM Provider 장애 시 자동 차단. 3회 연속 실패 시 10분간 차단 후 재시도.", related: ["circuit_closed", "process_provider_chain"] },
  { id: "macro_score", term: "Market Score", termKo: "매크로 점수", category: "concept", description: "Fear/Greed, 김프, 펀딩비 등을 종합한 시장 환경 점수(0~1).", related: ["fear_greed", "kimchi_premium", "funding_rate"] },
  { id: "sl", term: "Stop Loss (SL)", termKo: "손절가", category: "concept", description: "설정 가격 이하로 떨어지면 자동 매도하여 손실을 제한.", related: ["set_sl", "trailing_stop"] },
  { id: "tp", term: "Take Profit (TP)", termKo: "익절가", category: "concept", description: "설정 가격 이상으로 오르면 자동 매도하여 수익을 확정.", related: ["set_tp"] },
  { id: "trailing_stop", term: "Trailing Stop", termKo: "추적 손절", category: "concept", description: "가격 상승에 따라 손절가도 함께 올라가는 동적 손절.", related: ["sl"] },
  { id: "atr", term: "ATR", termKo: "평균진폭", category: "concept", description: "Average True Range. 가격 변동성 측정. 포지션 크기와 손절폭 계산에 사용.", related: ["sl", "tier_2"] },
  { id: "pnl", term: "PnL", termKo: "손익", category: "concept", description: "Profit and Loss. 수익(양수)과 손실(음수)을 나타냄.", related: ["total_pnl", "return_pct"] },
  { id: "paper_mode", term: "Paper Trading", termKo: "모의 매매", category: "concept", description: "실제 자금 없이 가상으로 매매를 시뮬레이션하는 모드." },
  { id: "optuna", term: "Optuna", termKo: "통계 최적화", category: "concept", description: "파라미터 최적화 프레임워크. AI Tuner가 백테스트 성과를 극대화하는 파라미터를 탐색.", related: ["process_optuna_role"] },

  // ── Pages (5) ──
  { id: "page_home", term: "Home", termKo: "홈 대시보드", category: "page", description: "실시간 요약 대시보드. 잔고, 수익률, BTC 가격, 시장 체제, 차트, AI Tuner 상태, 포지션, 매크로 지표를 한눈에 확인." },
  { id: "page_analytics", term: "Analytics", termKo: "분석", category: "page", description: "기간별 성과 분석. 누적 PnL 차트, 일별 PnL 차트, 최근 주문 내역 테이블. 7D~90D 기간 선택." },
  { id: "page_tuner", term: "AI Tuner", termKo: "AI 튜너", category: "page", description: "AI 자동 튜닝 관리. 튜너 상태 확인, 수동 튜닝 실행, 롤백, Tier 3 승인, 튜닝 히스토리 조회." },
  { id: "page_control", term: "Control", termKo: "제어", category: "page", description: "엔진 및 전략 제어. 엔진 시작/정지/재시작, 전략 프리셋 전환, 포지션 청산, SL/TP 수동 조정." },
  { id: "page_settings", term: "Settings", termKo: "설정", category: "page", description: "시스템 설정. 패스키 인증 관리, Regime/Risk/Macro/Strategy 현재 상태 확인." },

  // ── Presets (8) ──
  { id: "str_001", term: "STR-001 Conservative Trend", termKo: "보수적 추세추종", category: "preset", description: "4h 기준 보수적 추세추종. 1h/4h/1d 멀티TF. 매크로 10%. Bull(Low Vol) 시장용.", related: ["preset", "regime_bull_trend"] },
  { id: "str_002", term: "STR-002 Aggressive Trend", termKo: "공격적 추세추종", category: "preset", description: "1h 기준 공격적 추세추종. 낮은 진입 기준(0.05). Bull(High Vol) 시장용.", related: ["preset"] },
  { id: "str_003", term: "STR-003 Hybrid Reversal", termKo: "하이브리드 반전", category: "preset", description: "4h/1d 하이브리드 반전. 그리드서치 최고 성과. Ranging(High Vol) 시장용.", related: ["preset", "regime_ranging"] },
  { id: "str_004", term: "STR-004 Majority Vote", termKo: "다수결 추세추종", category: "preset", description: "다수결 진입 추세추종. 1h/4h 기반. 매크로 미반영. 수동 전환 전용.", related: ["preset"] },
  { id: "str_005", term: "STR-005 Low-Frequency", termKo: "저빈도 하이브리드", category: "preset", description: "4h/1d 저빈도 하이브리드. 높은 진입 기준(0.12). Ranging(Low Vol) 시장용.", related: ["preset"] },
  { id: "str_006", term: "STR-006 Scalper", termKo: "단타 스캘퍼", category: "preset", description: "1h/4h 단타. 모멘텀 가중치 높음. 수동 전환 전용.", related: ["preset"] },
  { id: "str_007", term: "STR-007 Bear Defensive", termKo: "약세장 방어", category: "preset", description: "약세장 방어. 극단적 과매도 반전만 매수(0.18). 빠른 손절. Bear(High Vol) 시장용.", related: ["preset", "regime_bear_trend"] },
  { id: "str_008", term: "STR-008 Bear Cautious", termKo: "약세장 신중 반전", category: "preset", description: "약세장 신중한 반전. STR-007보다 완화. 매크로 15%. Bear(Low Vol) 시장용.", related: ["preset"] },

  // ── AI Process (10) ──
  { id: "process_overview", term: "AI Tuning Process", termKo: "AI 튜닝 전체 흐름", category: "process", description: "매주 AI가 지난 거래 성적을 분석하고, 더 나은 설정값을 찾아 적용한 뒤, 48시간 감시 후 확정하거나 자동 롤백합니다. 평가 → 최적화 → 적용 → 감시 4단계로 진행됩니다.", related: ["process_evaluate", "process_optimize", "process_apply", "process_monitor"] },
  { id: "process_evaluate", term: "Step 1: Evaluate", termKo: "1단계: 평가", category: "process", description: "지난 7일간 거래 기록을 분석하여 성적표를 만듭니다. 승률, 수익팩터, 최대낙폭, 시그널 정확도를 계산합니다. 최소 3건 이상의 거래가 있어야 평가가 진행됩니다. 성적이 이미 양호하면(PF>1.5, 승률>40%) 튜닝을 건너뜁니다.", related: ["process_overview", "win_rate", "profit_factor"] },
  { id: "process_optimize", term: "Step 2: Optimize", termKo: "2단계: 최적화", category: "process", description: "통계 엔진(Optuna)이 50가지 설정 조합을 백테스트 시뮬레이션하여 상위 3개 후보를 추출합니다. 동시에 AI(Claude)가 성적표를 읽고 '이 시장에서는 어떤 후보가 적합한지' 분석합니다. AI가 최종 후보 1개를 선택합니다.", related: ["process_optuna_role", "process_claude_role", "process_safety_bt"] },
  { id: "process_safety_bt", term: "Safety Backtest", termKo: "안전 백테스트", category: "process", description: "최적화로 선택된 후보를 실제 적용 전에 최근 데이터로 백테스트합니다. AI가 백테스트 결과를 평가하여 '적용해도 안전한지' 최종 판단합니다. 위험하다고 판단되면 적용하지 않습니다.", related: ["process_optimize", "process_apply"] },
  { id: "process_apply", term: "Step 3: Apply", termKo: "3단계: 적용", category: "process", description: "안전 검증을 통과한 새 파라미터를 실시간 봇에 적용합니다. 가드레일이 작동하여 한 번에 최대 20%까지만 변경 가능하고, 허용 범위를 벗어나면 자동으로 클램핑됩니다. 비중값은 합계가 1.0이 되도록 자동 정규화됩니다.", related: ["process_guardrails", "process_monitor"] },
  { id: "process_monitor", term: "Step 4: Monitor", termKo: "4단계: 감시", category: "process", description: "새 설정 적용 후 48시간 동안 실시간 모니터링합니다. 최대낙폭이 기준의 2배를 넘거나 연속 5회 손실 시 자동 롤백됩니다. 48시간 무사 통과하면 새 설정이 확정됩니다.", related: ["tuner_monitoring", "tuning_confirmed", "tuning_rolled_back"] },
  { id: "process_optuna_role", term: "Optuna (Statistics Engine)", termKo: "통계 엔진 역할", category: "process", description: "Optuna는 수학적 최적화 프레임워크입니다. 파라미터 조합을 생성하고 Walk-Forward 백테스트로 성과를 측정하여 상위 후보를 추출합니다. AI 없이도 독립적으로 동작 가능합니다(Degraded Mode).", related: ["optuna", "process_optimize"] },
  { id: "process_claude_role", term: "Claude (AI Analysis)", termKo: "AI 분석 역할", category: "process", description: "Claude는 성적표를 읽고 시장 상황을 고려한 진단을 합니다. 근본 원인 분석, 파라미터 조정 방향 추천, Optuna 후보 중 최적 선택, 안전 백테스트 결과 평가를 담당합니다.", related: ["process_optimize", "process_safety_bt"] },
  { id: "process_provider_chain", term: "Provider Fallback Chain", termKo: "AI 장애 대응", category: "process", description: "1순위 Claude → 2순위 OpenAI → 3순위 Degraded Mode(AI 없이 통계만) 3중 구조입니다. 각 서비스에 서킷 브레이커가 적용되어 3회 연속 실패 시 10분간 차단 후 재시도합니다. 월 $5 예산 초과 시 자동으로 Degraded Mode로 전환됩니다.", related: ["circuit_breaker", "llm_budget"] },
  { id: "process_guardrails", term: "Guardrails", termKo: "안전장치", category: "process", description: "변경 전: 최대 변경폭 ±20%, 절대 범위 제한, Tier 2 동일 방향 연속 차단, Tier 3 사람 승인 필수. 변경 후: 48시간 모니터링, 낙폭 초과 시 자동 롤백, 연속 5회 손실 시 자동 롤백, 연속 3회 롤백 시 튜너 일시 중지.", related: ["process_apply", "process_monitor", "tuner_suspended"] },
];
