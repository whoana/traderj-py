# Round 2: 대시보드 비전 및 요구사항 제안서

**작성일**: 2026-03-02
**작성자**: Dashboard Designer (Senior Trading Dashboard Specialist)
**기반**: Round 1 UX 감사 보고서 + 전략/아키텍처 감사 교차 분석

---

## 1. 비전 선언문

> traderj 대시보드는 **트레이더의 의사결정 속도를 극대화**하는 실시간 인터페이스다.
> 봇 상태를 한눈에 파악하고, 긴급 상황에 즉각 대응하며,
> 전략 성과를 비교 분석할 수 있는 **기관급 트레이딩 대시보드**를 구축한다.

### 핵심 설계 원칙

1. **Real-time First**: 모든 핵심 데이터가 WebSocket 기반 실시간 스트리밍
2. **Action-Oriented**: 읽기 전용이 아닌 봇 제어/설정/긴급 대응 가능한 액션 UI
3. **Glanceable**: 스크롤 없이 3초 안에 전체 상황 파악 가능한 정보 밀도
4. **Mobile-Ready**: 외출 중 모바일로 봇 상태 확인 및 긴급 조치 가능
5. **Data-Dense, Not Data-Cluttered**: 트레이더에게 필요한 정보만 밀도 높게 제공

---

## 2. 기술 스택 제안

| 계층 | 기술 | 근거 |
|------|------|------|
| **프레임워크** | Next.js 15 (App Router) | SSR/SSG + API Routes + WebSocket 지원 |
| **차트** | Lightweight Charts (TradingView OSS) | 금융 특화, 캔들스틱/지표/마커, 고성능 Canvas |
| **보조 차트** | Recharts | PnL/통계 차트 (비금융 데이터) |
| **스타일링** | TailwindCSS + shadcn/ui | 다크 테마 기본, 접근성 내장, 일관된 디자인 시스템 |
| **상태 관리** | Zustand | 경량, WebSocket 스트림 상태에 최적 |
| **실시간** | WebSocket 클라이언트 (native) | API 서버의 WS 엔드포인트 구독 |
| **테이블** | TanStack Table | 정렬/필터/가상 스크롤, 대량 데이터 처리 |
| **폼** | React Hook Form + Zod | 봇 설정 파라미터 유효성 검증 |
| **알림** | Sonner (toast) + Web Notification API | 브라우저 내 실시간 알림 |
| **모바일** | PWA (next-pwa) | 홈 화면 추가, 오프라인 기본 상태, 푸시 알림 |

---

## 3. 요구사항 (P0 / P1 / P2)

### 3.1 P0: 실시간 모니터링 코어 (MVP - 반드시 구현)

#### P0-1. 멀티봇 상태 개요 (Multi-Bot Overview Panel)

**설명**: 모든 실행 중인 봇의 상태를 단일 뷰에서 한눈에 확인

**UI 명세**:
```
┌─────────────────────────────────────────────────────────────┐
│  🟢 STR-003        🟡 STR-004        🔵 STR-005           │
│  IDLE · 0.00% PnL  EXECUTING · +1.2% SCANNING · -0.3%     │
│  No Position        0.0012 BTC @ 145M  No Position          │
│  Last Signal: HOLD  Last Signal: BUY   Last Signal: HOLD   │
│  Uptime: 48h 23m    Uptime: 48h 23m    Uptime: 48h 23m     │
└─────────────────────────────────────────────────────────────┘
```

**데이터 계약 (← API 서버)**:
```typescript
// GET /api/bots/status (REST) + WS subscribe: "bots.status"
interface BotStatusResponse {
  strategy_id: string;
  state: "IDLE" | "SCANNING" | "EXECUTING" | "PAUSED" | "SHUTTING_DOWN";
  uptime_seconds: number;
  open_position: {
    amount: number;
    entry_price: number;
    current_price: number;
    unrealized_pnl: number;
    unrealized_pnl_pct: number;
    stop_loss: number;
  } | null;
  paper_balance: {
    krw: number;
    btc: number;
    total_value_krw: number;
    pnl: number;
    pnl_pct: number;
  };
  last_signal: {
    direction: "BUY" | "SELL" | "HOLD";
    score: number;
    timestamp: string;  // ISO 8601
  } | null;
  updated_at: string;
}
```

**실시간 요구사항**:
- WebSocket `bots.status` 채널 구독 시 상태 변화 즉시 수신
- 상태별 컬러 코드: IDLE=녹색, SCANNING=파랑, EXECUTING=노랑, PAUSED=적색
- 포지션 PnL 양수=녹색, 음수=적색 (실시간 업데이트)

---

#### P0-2. 실시간 가격 차트 (Candlestick Chart)

**설명**: TradingView Lightweight Charts 기반 OHLCV 캔들스틱 + 거래 마커

**UI 명세**:
- 캔들스틱 차트 (양봉=녹색, 음봉=적색)
- 타임프레임 전환: 15m / 1H / 4H / 1D 버튼
- 볼륨 바 차트 (하단 히스토그램)
- 매수/매도 마커: 차트 위에 화살표 (▲매수=녹색, ▼매도=적색)
- 현재 가격 라인 (실시간 업데이트)
- 크로스헤어 + 가격/시간 표시

**데이터 계약 (← API 서버)**:
```typescript
// GET /api/candles?symbol=BTC/KRW&timeframe=1h&limit=500
interface CandleResponse {
  timestamp: number;  // Unix ms
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

// WS subscribe: "ticker.BTC-KRW"
interface TickerUpdate {
  symbol: string;
  price: number;
  volume_24h: number;
  change_24h: number;
  change_pct_24h: number;
  bid: number;
  ask: number;
  timestamp: number;
}

// GET /api/orders?strategy_id=STR-003&status=filled&limit=100
// → 차트 위 매수/매도 마커용
interface TradeMarker {
  timestamp: number;
  side: "buy" | "sell";
  price: number;
  amount: number;
  strategy_id: string;
}
```

**실시간 요구사항**:
- WebSocket `ticker.BTC-KRW` 구독으로 현재가 실시간 반영
- 새 캔들 형성 시 자동 업데이트 (마지막 캔들 갱신 → 새 캔들 추가)
- 초기 로딩: REST로 히스토리컬 캔들 500개 로드 → WS로 실시간 업데이트

---

#### P0-3. 핵심 KPI 헤더 (Key Metrics Bar)

**설명**: 화면 상단 고정, 스크롤해도 항상 보이는 핵심 지표

**UI 명세**:
```
┌─────────────────────────────────────────────────────────────┐
│  BTC/KRW ₩145,230,000 (+2.3%)  │  Portfolio ₩10,450,000   │
│  24H Vol: 1,234 BTC             │  PnL: +₩450,000 (+4.5%)  │
│  F&G: 11 (Extreme Fear)        │  Active Bots: 3/3         │
└─────────────────────────────────────────────────────────────┘
```

**데이터 계약**: P0-1 BotStatusResponse + P0-2 TickerUpdate + MacroSnapshot 결합

---

#### P0-4. 봇 제어 패널 (Bot Control Panel)

**설명**: 각 봇의 시작/중지/일시정지 + 긴급 전체 중지

**UI 명세**:
```
┌─────────────────────────────────────────────────────────────┐
│  [🔴 EMERGENCY STOP ALL]                                    │
├─────────────────────────────────────────────────────────────┤
│  STR-003  [▶ Start] [⏸ Pause] [⏹ Stop]  Status: IDLE      │
│  STR-004  [▶ Start] [⏸ Pause] [⏹ Stop]  Status: EXECUTING │
│  STR-005  [▶ Start] [⏸ Pause] [⏹ Stop]  Status: SCANNING  │
├─────────────────────────────────────────────────────────────┤
│  [⚡ Close All Positions]  Confirm: ☐                       │
└─────────────────────────────────────────────────────────────┘
```

**데이터 계약 (→ API 서버)**:
```typescript
// POST /api/bots/{strategy_id}/start
// POST /api/bots/{strategy_id}/stop
// POST /api/bots/{strategy_id}/pause
// POST /api/bots/{strategy_id}/resume

// POST /api/bots/emergency-stop  (모든 봇 중지 + 전 포지션 청산)
interface EmergencyStopRequest {
  close_positions: boolean;  // true면 포지션도 즉시 청산
  reason?: string;
}

interface BotControlResponse {
  strategy_id: string;
  action: "start" | "stop" | "pause" | "resume" | "emergency_stop";
  success: boolean;
  new_state: string;
  message?: string;
}
```

**UX 요구사항**:
- Emergency Stop은 확인 다이얼로그 필수 (실수 방지)
- 봇 상태 변화 시 WebSocket으로 즉시 UI 반영
- 작업 진행 중(EXECUTING) 봇의 Stop은 "현재 주문 완료 후 중지" 옵션 제공
- Close All Positions는 체크박스 확인 후 활성화

---

#### P0-5. 주문/포지션 테이블 (Orders & Positions)

**설명**: 최근 주문 내역 + 현재/과거 포지션을 탭으로 구분

**UI 명세**:
- **Open Positions 탭**: 현재 열린 포지션 (전략별)
  - 진입가, 현재가, 수량, 미실현 PnL, 손절가, 보유 시간
  - PnL 양수=녹색 배경, 음수=적색 배경
- **Order History 탭**: 최근 주문 (필터: 전략, 방향, 상태)
  - TanStack Table로 정렬/필터/페이지네이션
- **Closed Positions 탭**: 마감된 포지션 이력
  - 실현 PnL 색상 코딩

**데이터 계약**:
```typescript
// GET /api/positions?status=open
// GET /api/positions?status=closed&limit=50&offset=0
// GET /api/orders?strategy_id=STR-003&limit=50&offset=0

// WS subscribe: "orders.{strategy_id}" → 주문 상태 변화 실시간
// WS subscribe: "positions.{strategy_id}" → 포지션 변화 실시간
```

---

### 3.2 P1: 분석 및 인사이트 (핵심 분석 기능)

#### P1-1. PnL 분석 대시보드

**설명**: 수익/손실을 다양한 시각으로 분석

**컴포넌트**:
1. **Equity Curve**: 누적 자산 가치 추이 (라인 차트)
2. **Drawdown Chart**: 고점 대비 하락률 (면적 차트, 적색)
3. **Daily PnL Bar Chart**: 일별 실현 손익 (양수=녹색 막대, 음수=적색 막대)
4. **핵심 지표 카드**:
   - Total Return, Sharpe Ratio, Sortino Ratio, Max Drawdown
   - Win Rate, Avg Win, Avg Loss, Profit Factor
   - 기간 선택: 7D / 30D / 90D / All

**데이터 계약 (← API 서버)**:
```typescript
// GET /api/analytics/pnl?strategy_id=STR-003&period=30d
interface PnLAnalytics {
  equity_curve: Array<{ date: string; value: number }>;
  drawdown_curve: Array<{ date: string; drawdown_pct: number }>;
  daily_pnl: Array<{
    date: string;
    realized: number;
    unrealized: number;
    trade_count: number;
    win_count: number;
  }>;
  summary: {
    total_return_pct: number;
    sharpe_ratio: number | null;    // ← 전략 팀 요구: 현재 미계산
    sortino_ratio: number | null;
    max_drawdown_pct: number;
    win_rate: number;
    avg_win: number;
    avg_loss: number;
    profit_factor: number;
    total_trades: number;
  };
}
```

**교차 의존성**:
- 전략 팀 감사에서 지적된 Sharpe/Sortino 미계산 → API 서버에서 계산하여 제공 필요
- 아키텍처 팀의 DB 전환(PostgreSQL/TimescaleDB) 시 시계열 집계 쿼리 최적화 가능

---

#### P1-2. 전략 비교 뷰 (Strategy Comparison)

**설명**: 3개 봇(STR-003/004/005)의 성과를 병렬 비교

**UI 명세**:
```
┌──────────────────────────────────────────────────────┐
│  Strategy Comparison (30D)                           │
├─────────┬───────────┬───────────┬───────────────────┤
│  Metric │  STR-003  │  STR-004  │  STR-005          │
├─────────┼───────────┼───────────┼───────────────────┤
│  Return │  +2.1%    │  +0.8%    │  +3.4% ★ Best     │
│  Sharpe │  0.95     │  0.42     │  1.23 ★ Best      │
│  MDD    │  -4.2%    │  -6.1%    │  -2.8% ★ Best     │
│  Trades │  12       │  8        │  18                │
│  WinRate│  58%      │  50%      │  61% ★ Best       │
├─────────┴───────────┴───────────┴───────────────────┤
│  [Equity Curves Overlay Chart]                       │
│  ---- STR-003 (blue)                                │
│  ---- STR-004 (orange)                              │
│  ---- STR-005 (green)                               │
└──────────────────────────────────────────────────────┘
```

**데이터 계약**:
```typescript
// GET /api/analytics/compare?strategies=STR-003,STR-004,STR-005&period=30d
interface StrategyComparison {
  strategies: Array<{
    strategy_id: string;
    metrics: PnLAnalytics["summary"];
    equity_curve: Array<{ date: string; value: number }>;
  }>;
}
```

---

#### P1-3. 시그널 분석 (Signal Analysis)

**설명**: 시그널 스코어의 시각적 분석

**컴포넌트**:
1. **Score Heatmap**: 시간대별 × 전략별 시그널 강도 (색상 그라데이션)
2. **Sub-score Radar Chart**: 선택한 시그널의 trend/momentum/volume/macro 분해
3. **Signal History Table**: 필터링 가능한 시그널 이력 (방향, 스코어 범위, 기간)

**데이터 계약**:
```typescript
// GET /api/signals?strategy_id=STR-005&limit=100
interface SignalDetail {
  id: number;
  timestamp: string;
  direction: "BUY" | "SELL" | "HOLD";
  score: number;
  trend_score: number;
  momentum_score: number;
  volume_score: number;
  macro_score: number;
  details: Record<string, unknown>;  // JSON 상세
  timeframe: string;
}
```

---

#### P1-4. 매크로 지표 패널 (Macro Dashboard)

**설명**: 매크로 스코어 구성 요소의 시각적 표시

**UI 명세**:
```
┌──────────────────────────────────────────┐
│  Macro Score: 4.58 / 10                  │
│  ████████░░░░░░░░░░░░  (Bearish)         │
├──────────────────────────────────────────┤
│  Fear & Greed: 11  ██░░░░ Extreme Fear   │
│  BTC Dominance: 56%  ████████░░          │
│  DXY: 97.6  █████████░                   │
│  Kimchi Premium: 1.7%  ████░░░           │
│  NASDAQ: [sparkline]                     │
├──────────────────────────────────────────┤
│  Updated: 6h ago · Next update: 2h       │
└──────────────────────────────────────────┘
```

**데이터 계약**:
```typescript
// GET /api/macro/latest
interface MacroData {
  timestamp: string;
  market_score: number;
  fear_greed: number;
  btc_dominance: number;
  dxy: number;
  nasdaq: number;
  kimchi_premium: number;
  // 히스토리 (스파크라인용)
  history_7d: Array<{
    timestamp: string;
    market_score: number;
    fear_greed: number;
  }>;
}
```

---

#### P1-5. 반응형 모바일 레이아웃

**설명**: 모바일에서 핵심 정보 접근 가능한 반응형 디자인

**Breakpoints**:
- **Desktop (1280px+)**: 전체 대시보드 그리드 (사이드바 + 메인)
- **Tablet (768-1279px)**: 2컬럼 그리드, 사이드바 접힘
- **Mobile (< 768px)**: 단일 컬럼, 탭 네비게이션, 핵심 KPI 상단 고정

**모바일 우선순위 뷰**:
1. KPI 헤더 (현재가, PnL, 봇 상태)
2. 봇 제어 (Emergency Stop, Pause/Resume)
3. 가격 차트 (가로 스크롤 가능)
4. 포지션/주문 (아코디언)

---

### 3.3 P2: 고급 기능 (확장 기능)

#### P2-1. 기술 지표 오버레이

**설명**: 캔들스틱 차트에 기술 지표 오버레이 토글

**지표 목록**:
- EMA 20/50/200 (라인 오버레이)
- Bollinger Bands (밴드 오버레이)
- RSI (별도 패널)
- MACD (별도 패널)
- Volume (하단 히스토그램)

**데이터 계약**:
```typescript
// GET /api/indicators?symbol=BTC/KRW&timeframe=1h&indicators=ema20,ema50,bb,rsi
interface IndicatorData {
  timestamp: number;
  ema_20?: number;
  ema_50?: number;
  ema_200?: number;
  bb_upper?: number;
  bb_middle?: number;
  bb_lower?: number;
  rsi?: number;
  macd_line?: number;
  macd_signal?: number;
  macd_hist?: number;
}
```

---

#### P2-2. 전략 파라미터 튜닝 UI

**설명**: 대시보드에서 전략 파라미터를 수정하고 적용

**UI 명세**:
```
┌──────────────────────────────────────────┐
│  Strategy Config: STR-005               │
├──────────────────────────────────────────┤
│  Entry Mode: [WEIGHTED ▼]              │
│  Timeframes:                            │
│    15m weight: [====○====] 0.20         │
│    1h  weight: [======○==] 0.30         │
│    4h  weight: [========○] 0.50         │
│  Buy Threshold:  [====○====] 0.20      │
│  Sell Threshold: [====○====] -0.20     │
│  Stop Loss %:    [===○=====] 3.0%      │
│  Position Size %:[====○====] 20%       │
├──────────────────────────────────────────┤
│  [Preview Changes] [Apply & Restart]    │
└──────────────────────────────────────────┘
```

**데이터 계약**:
```typescript
// GET /api/bots/{strategy_id}/config
// PUT /api/bots/{strategy_id}/config
interface StrategyConfig {
  strategy_id: string;
  scoring_mode: "TREND_FOLLOW" | "HYBRID";
  entry_mode: "AND" | "WEIGHTED";
  timeframe_entries: Array<{
    timeframe: string;
    weight: number;
    threshold?: number;
  }>;
  buy_threshold: number;
  sell_threshold: number;
  stop_loss_pct: number;
  max_position_pct: number;
  trend_filter: boolean;
}
```

**교차 의존성**:
- 전략 팀의 ATR 기반 동적 손절 구현 시 → UI에 "ATR 배수" 슬라이더 추가 필요
- 아키텍처 팀의 이벤트 버스 구현 시 → 설정 변경 이벤트를 봇에 전파 가능

---

#### P2-3. 알림 센터 (Notification Center)

**설명**: 대시보드 내 알림 이력 + 알림 규칙 설정

**컴포넌트**:
1. **알림 벨 아이콘**: 미읽은 알림 배지
2. **알림 드롭다운**: 최근 알림 목록 (매매, 손절, 에러, 일일 요약)
3. **알림 설정**:
   - 가격 알림: BTC가 X원 이상/이하 시
   - PnL 알림: 일일 손실이 N% 초과 시
   - 봇 상태 알림: PAUSED, SHUTTING_DOWN 전환 시
   - 채널: 브라우저 Push + 텔레그램 (기존)

**데이터 계약**:
```typescript
// GET /api/notifications?limit=50
// WS subscribe: "notifications"
interface Notification {
  id: string;
  type: "trade" | "stop_loss" | "error" | "daily_summary" | "price_alert" | "bot_state";
  title: string;
  message: string;
  severity: "info" | "warning" | "critical";
  timestamp: string;
  read: boolean;
  metadata?: Record<string, unknown>;
}

// POST /api/alerts/rules
interface AlertRule {
  type: "price" | "pnl" | "bot_state";
  condition: {
    field: string;
    operator: "gt" | "lt" | "eq" | "change";
    value: number | string;
  };
  channels: ("browser" | "telegram")[];
  enabled: boolean;
}
```

---

#### P2-4. 백테스트 결과 뷰어

**설명**: 백테스트 결과를 대시보드에서 시각적으로 확인

**컴포넌트**:
1. 백테스트 Equity Curve + Drawdown
2. 거래 목록 + 차트 마커 오버레이
3. 성과 지표 요약 카드
4. Threshold Sweep 히트맵 (X축: buy_th, Y축: sell_th, 색상: Sharpe)

---

#### P2-5. 리스크 모니터링 패널

**설명**: 리스크 엔진 상태의 실시간 시각화

**UI 명세**:
```
┌──────────────────────────────────────────┐
│  Risk Monitor                            │
├──────────────────────────────────────────┤
│  Consecutive Losses: 1/3  [██░░░]       │
│  Daily PnL: -1.2% / -5.0%  [██████░░]  │
│  Cooldown: None                         │
│  Position Size: 15% / 20%  [███████░]   │
│  Stop Loss: -3.0% (set at ₩140,723,100)│
├──────────────────────────────────────────┤
│  Risk Status: ✅ NORMAL                  │
└──────────────────────────────────────────┘
```

**데이터 계약**:
```typescript
// GET /api/risk/{strategy_id}/status
// WS subscribe: "risk.{strategy_id}"
interface RiskStatus {
  strategy_id: string;
  consecutive_losses: number;
  max_consecutive_losses: number;
  daily_pnl: number;
  daily_pnl_limit: number;
  cooldown_until: string | null;
  current_position_pct: number;
  max_position_pct: number;
  stop_loss_price: number | null;
  status: "NORMAL" | "WARNING" | "COOLDOWN" | "LIMIT_REACHED";
}
```

**교차 의존성**:
- 아키텍처 팀의 RiskManager 상태 영속화(C1) 구현이 선행 필요
- 전략 팀의 ATR 기반 동적 손절 시 → 동적 stop_loss_price 표시

---

## 4. 페이지 구조 (Information Architecture)

```
/                           ← 메인 대시보드 (P0 전체)
├── Overview Panel          ← P0-1 멀티봇 상태 + P0-3 KPI 헤더
├── Chart Panel             ← P0-2 캔들스틱 + P2-1 지표 오버레이
├── Control Panel           ← P0-4 봇 제어
├── Orders/Positions Panel  ← P0-5 주문/포지션 테이블
│
/analytics                  ← 분석 페이지 (P1)
├── PnL Dashboard           ← P1-1
├── Strategy Comparison     ← P1-2
├── Signal Analysis         ← P1-3
├── Macro Dashboard         ← P1-4
│
/settings                   ← 설정 페이지 (P2)
├── Strategy Config         ← P2-2 전략 파라미터
├── Alert Rules             ← P2-3 알림 설정
│
/backtest                   ← 백테스트 뷰어 (P2-4)
```

---

## 5. 대시보드 ↔ API 서버 인터페이스 계약

### 5.1 REST API 엔드포인트 요약

| Method | Endpoint | 용도 | 우선순위 |
|--------|----------|------|----------|
| GET | `/api/bots/status` | 모든 봇 상태 | P0 |
| POST | `/api/bots/{id}/start` | 봇 시작 | P0 |
| POST | `/api/bots/{id}/stop` | 봇 중지 | P0 |
| POST | `/api/bots/{id}/pause` | 봇 일시정지 | P0 |
| POST | `/api/bots/{id}/resume` | 봇 재개 | P0 |
| POST | `/api/bots/emergency-stop` | 긴급 전체 중지 | P0 |
| GET | `/api/candles` | OHLCV 데이터 | P0 |
| GET | `/api/orders` | 주문 이력 | P0 |
| GET | `/api/positions` | 포지션 이력 | P0 |
| GET | `/api/analytics/pnl` | PnL 분석 | P1 |
| GET | `/api/analytics/compare` | 전략 비교 | P1 |
| GET | `/api/signals` | 시그널 이력 | P1 |
| GET | `/api/macro/latest` | 매크로 데이터 | P1 |
| GET | `/api/indicators` | 기술 지표 | P2 |
| GET/PUT | `/api/bots/{id}/config` | 전략 설정 | P2 |
| GET/POST | `/api/alerts/rules` | 알림 규칙 | P2 |
| GET | `/api/risk/{id}/status` | 리스크 상태 | P2 |
| GET | `/api/notifications` | 알림 이력 | P2 |

### 5.2 WebSocket 채널 요약

| 채널 | 페이로드 | 업데이트 빈도 | 우선순위 |
|------|---------|-------------|----------|
| `ticker.BTC-KRW` | TickerUpdate | 실시간 (100ms~) | P0 |
| `bots.status` | BotStatusResponse[] | 상태 변화 시 | P0 |
| `orders.{strategy_id}` | Order 변경 | 이벤트 기반 | P0 |
| `positions.{strategy_id}` | Position 변경 | 이벤트 기반 | P0 |
| `risk.{strategy_id}` | RiskStatus | 변화 시 | P2 |
| `notifications` | Notification | 이벤트 기반 | P2 |

### 5.3 아키텍처 팀에 대한 API 서버 요구사항

1. **REST + WebSocket 통합 서버**: FastAPI (uvicorn) 권장
   - REST: 히스토리컬 데이터 조회, 봇 제어 명령
   - WebSocket: 실시간 데이터 스트림, 상태 변화 푸시

2. **UpbitWebSocket → API WS 브릿지**:
   - 기존 `UpbitWebSocket` (ticker/trade/orderbook) 데이터를 API WebSocket으로 릴레이
   - 대시보드가 Upbit에 직접 연결하지 않고 API 서버를 통해 구독

3. **봇 프로세스 관리 API**:
   - API 서버가 봇 프로세스의 시작/중지/상태 조회를 관리
   - 현재 PID 파일 기반 → 프로세스 매니저 추상화 필요

4. **CORS 설정**:
   - 대시보드(Next.js dev: localhost:3000)에서 API 서버(localhost:8000)로의 크로스 오리진 허용

---

## 6. 디자인 시스템 기초 요구사항

### 6.1 컬러 팔레트 (다크 테마 기본)

| 용도 | 토큰 | 값 (Dark) |
|------|------|-----------|
| 배경 (기본) | `--bg-primary` | `#0a0a0f` |
| 배경 (카드) | `--bg-card` | `#12121a` |
| 배경 (호버) | `--bg-hover` | `#1a1a2e` |
| 텍스트 (기본) | `--text-primary` | `#e4e4e7` |
| 텍스트 (보조) | `--text-secondary` | `#71717a` |
| 양수/매수 | `--color-positive` | `#22c55e` (green-500) |
| 음수/매도 | `--color-negative` | `#ef4444` (red-500) |
| 경고 | `--color-warning` | `#f59e0b` (amber-500) |
| 정보 | `--color-info` | `#3b82f6` (blue-500) |
| 액센트 | `--color-accent` | `#8b5cf6` (violet-500) |

### 6.2 타이포그래피

| 용도 | 폰트 | 비고 |
|------|------|------|
| UI 일반 | Inter | 가독성 최적화 |
| 숫자/가격 | JetBrains Mono | 모노스페이스, 자릿수 정렬 |
| 큰 숫자(KPI) | Inter Tight (Tabular) | 숫자 변동 시 레이아웃 시프트 방지 |

### 6.3 숫자 포맷팅 규칙

| 데이터 | 포맷 | 예시 |
|--------|------|------|
| KRW 가격 | 천단위 콤마 | ₩145,230,000 |
| BTC 수량 | 8자리 소수점 | 0.00123456 BTC |
| 퍼센트 | 소수점 2자리 + 부호 | +2.34%, -1.23% |
| PnL 금액 | 부호 + 천단위 콤마 | +₩450,000, -₩123,000 |
| 시간 | 상대 시간 + 절대 시간 툴팁 | "5분 전" (2026-03-02 14:23:05 KST) |

---

## 7. 교차 의존성 요약

### 대시보드 → 아키텍처 팀 의존

| 항목 | 필요 사항 | 우선순위 |
|------|-----------|----------|
| API 서버 | REST + WebSocket 통합 서버 (FastAPI) | P0 |
| WS 브릿지 | UpbitWebSocket → API WS 릴레이 | P0 |
| 봇 제어 API | 봇 프로세스 시작/중지/상태 관리 | P0 |
| DB 접근 계층 | 대시보드가 DB 직접 접근하지 않도록 API 계층화 | P0 |
| 리스크 상태 영속화 | RiskManager 상태 DB 저장 (리스크 패널용) | P2 |
| CORS/인증 | API 서버 CORS 설정, 향후 인증 토큰 | P1 |

### 대시보드 → 전략 팀 의존

| 항목 | 필요 사항 | 우선순위 |
|------|-----------|----------|
| Sharpe/Sortino 계산 | PnL 분석 대시보드에 필요 | P1 |
| 시그널 상세 데이터 | details JSON의 구조화된 스키마 정의 | P1 |
| 전략 파라미터 스키마 | 튜닝 UI에 필요한 파라미터 유효 범위 정의 | P2 |
| ATR 기반 동적 손절 | 리스크 패널에서 동적 손절가 표시 | P2 |

### 대시보드 ← 다른 팀 의존 (대시보드가 제공)

| 항목 | 소비자 | 설명 |
|------|--------|------|
| 봇 제어 UI 스펙 | 아키텍처 팀 | API 엔드포인트 설계의 기준 |
| 데이터 표시 요구사항 | 전략 팀 | 어떤 지표를 어떻게 시각화할지 |
| 알림 채널 요구사항 | 전략/아키텍처 팀 | 브라우저 Push + 텔레그램 연동 |

---

## 8. 구현 로드맵 제안

### Phase 1 (Sprint 1-2): P0 코어 - 2~3주
1. Next.js 프로젝트 세팅 (TailwindCSS + shadcn/ui + 다크 테마)
2. 디자인 시스템 토큰 + 기본 레이아웃 컴포넌트
3. WebSocket 클라이언트 + Zustand 스토어
4. 멀티봇 상태 개요 패널 (P0-1)
5. KPI 헤더 (P0-3)
6. Lightweight Charts 캔들스틱 (P0-2)
7. 봇 제어 패널 (P0-4) - API 연동
8. 주문/포지션 테이블 (P0-5)

### Phase 2 (Sprint 3-4): P1 분석 - 2~3주
9. PnL 분석 대시보드 (P1-1)
10. 전략 비교 뷰 (P1-2)
11. 시그널 분석 (P1-3)
12. 매크로 지표 패널 (P1-4)
13. 모바일 반응형 (P1-5)

### Phase 3 (Sprint 5-6): P2 고급 - 2~3주
14. 기술 지표 오버레이 (P2-1)
15. 전략 파라미터 튜닝 UI (P2-2)
16. 알림 센터 (P2-3)
17. 리스크 모니터링 (P2-5)
18. 백테스트 뷰어 (P2-4)

---

## 9. 성공 지표

| 지표 | 현재 (Streamlit) | 목표 (traderj) |
|------|------------------|----------------|
| 상황 파악 시간 | ~105초 (3전략 확인) | **< 5초** (한눈에 전체 파악) |
| 긴급 대응 시간 | ~40초+ (터미널 필요) | **< 5초** (Emergency Stop 버튼) |
| 전략 비교 시간 | ~180초+ (수동 전환) | **< 10초** (비교 뷰 클릭) |
| 데이터 지연 | 수동 새로고침 | **< 1초** (WebSocket 실시간) |
| 모바일 사용 가능성 | 불가 | **완전 지원** (PWA) |
| UX 성숙도 | 2/10 | **8/10** (기관급 수준) |
