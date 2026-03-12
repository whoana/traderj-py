# Round 2: 대시보드 요구사항서

**작성일**: 2026-03-02
**작성자**: Dashboard Designer
**기반**: Round 1 UX 감사 (`round1-ux-audit.md`) + 전략/아키텍처 감사 교차 분석
**비전 문서**: `round2-dashboard-vision.md` (기술 스택 및 비전 선언 참조)

---

## 1. 기술 스택 요약

| 계층 | 기술 | 비고 |
|------|------|------|
| 프레임워크 | Next.js 15 (App Router) | SSR + API Routes + WS |
| 차트 (금융) | Lightweight Charts 4.x | TradingView OSS, Canvas 기반 |
| 차트 (통계) | Recharts | PnL/Drawdown/비교 차트 |
| 스타일 | TailwindCSS + shadcn/ui | 다크 테마 기본 |
| 상태 | Zustand | WS 스트림 상태 최적 |
| 테이블 | TanStack Table v8 | 가상 스크롤, 정렬/필터 |
| 폼 | React Hook Form + Zod | 파라미터 유효성 검증 |
| 실시간 | native WebSocket | API 서버 WS 구독 |

---

## 2. 페이지 구조 및 네비게이션

```
┌─────────────────────────────────────────────────────────────────┐
│  Top Nav (고정)                                                  │
│  [Logo] [Dashboard] [Analytics] [Settings]    [🔔 3] [Theme]   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  / (Dashboard)          메인 모니터링 + 봇 제어                   │
│  /analytics             PnL 분석 + 전략 비교 + 시그널             │
│  /settings              전략 설정 + 알림 규칙                     │
│  /backtest              백테스트 결과 뷰어                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 메인 대시보드 와이어프레임 (`/`)

### 3.1 데스크톱 레이아웃 (1280px+)

```
┌─────────────────────────────────────────────────────────────────┐
│  KPI Header (고정, 스크롤해도 상단 유지)                          │
│  BTC ₩145.2M (+2.3%) │ Portfolio ₩10.45M │ PnL +₩450K │ 3 Bots │
├───────────────────────────────────────┬─────────────────────────┤
│                                       │  Bot Cards (우측 패널)   │
│  Candlestick Chart                    │  ┌───────────────────┐ │
│  ┌─────────────────────────────────┐  │  │ STR-003  🟢 IDLE  │ │
│  │  [15m] [1H] [4H] [1D]          │  │  │ PnL: +0.0%        │ │
│  │                                 │  │  │ No Position        │ │
│  │    ╻                            │  │  │ [▶][⏸][⏹]         │ │
│  │   ╺╋╸   ╻                      │  │  └───────────────────┘ │
│  │    ╹   ╺╋╸   ╻  ╻              │  │  ┌───────────────────┐ │
│  │         ╹   ╺╋╸╺╋╸             │  │  │ STR-004  🟡 EXEC  │ │
│  │              ╹  ╹              │  │  │ PnL: +1.2%        │ │
│  │  ▲ Buy              ▼ Sell     │  │  │ 0.001 BTC @145M   │ │
│  │  Volume ████ ██ ████████ ██    │  │  │ [▶][⏸][⏹]         │ │
│  └─────────────────────────────────┘  │  └───────────────────┘ │
│                                       │  ┌───────────────────┐ │
│                                       │  │ STR-005  🔵 SCAN  │ │
│                                       │  │ PnL: -0.3%        │ │
│                                       │  │ No Position        │ │
│                                       │  │ [▶][⏸][⏹]         │ │
│                                       │  └───────────────────┘ │
│                                       │                         │
│                                       │  [🔴 EMERGENCY STOP]   │
│                                       │  [⚡ Close All Pos.]   │
├───────────────────────────────────────┴─────────────────────────┤
│  Tabs: [Open Positions] [Orders] [Closed Positions]             │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ Strategy │ Side │ Entry    │ Current  │ PnL      │ SL      ││
│  │ STR-004  │ LONG │ ₩144.8M │ ₩145.2M │ +₩4,000 │ ₩140.5M ││
│  │          │      │          │          │ (+0.28%) │         ││
│  └─────────────────────────────────────────────────────────────┘│
│  Macro Bar: F&G 11 │ BTC Dom 56% │ DXY 97.6 │ KP 1.7% │ 4.6/10│
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 모바일 레이아웃 (< 768px)

```
┌─────────────────────┐
│ KPI (축약)           │
│ BTC ₩145.2M (+2.3%) │
│ PnL +₩450K  3 Bots  │
├─────────────────────┤
│ [Chart][Bots][Orders]│  ← 탭 네비게이션
├─────────────────────┤
│ (선택된 탭 콘텐츠)    │
│                     │
│ Bots 탭:            │
│ ┌─────────────────┐ │
│ │ STR-003 🟢 IDLE │ │
│ │ PnL +0.0%       │ │
│ │ [▶] [⏸] [⏹]    │ │
│ └─────────────────┘ │
│ ┌─────────────────┐ │
│ │ STR-004 🟡 EXEC │ │
│ │ PnL +1.2%       │ │
│ │ 0.001 BTC       │ │
│ │ [▶] [⏸] [⏹]    │ │
│ └─────────────────┘ │
│                     │
│ [🔴 EMERGENCY STOP] │
└─────────────────────┘
```

---

## 4. 컴포넌트 계층 구조

```
app/
├── layout.tsx                   ← 루트 레이아웃 (다크 테마, 폰트)
│   └── TopNav                   ← 네비게이션 바
│       ├── NavLinks
│       ├── NotificationBell     ← P2
│       └── ThemeToggle          ← P1
│
├── page.tsx                     ← 메인 대시보드 (/)
│   ├── KPIHeader                ← P0: 핵심 지표 상단 바
│   │   ├── PriceTicker          ← 실시간 BTC 가격
│   │   ├── PortfolioValue       ← 총 포트폴리오 가치
│   │   ├── TotalPnL             ← 총 PnL
│   │   └── ActiveBotCount       ← 활성 봇 수
│   │
│   ├── CandlestickPanel         ← P0: 가격 차트 영역
│   │   ├── TimeframeSelector    ← 15m/1H/4H/1D 버튼
│   │   ├── LWChart              ← Lightweight Charts 래퍼
│   │   ├── VolumeHistogram      ← 거래량 하단 히스토그램
│   │   └── TradeMarkers         ← 매수/매도 화살표 마커
│   │
│   ├── BotControlPanel          ← P0: 봇 관리 우측 패널
│   │   ├── BotCard[]            ← 전략별 카드
│   │   │   ├── BotStatusBadge   ← 상태 이모지 + 텍스트
│   │   │   ├── PositionSummary  ← 열린 포지션 요약
│   │   │   ├── PnLDisplay       ← 손익 (색상 코딩)
│   │   │   └── ControlButtons   ← Start/Pause/Stop
│   │   ├── EmergencyStop        ← 긴급 전체 중지 버튼
│   │   └── CloseAllPositions    ← 전 포지션 청산 버튼
│   │
│   ├── DataTabs                 ← P0: 주문/포지션 테이블
│   │   ├── OpenPositionsTab     ← 열린 포지션
│   │   ├── OrderHistoryTab      ← 주문 이력
│   │   └── ClosedPositionsTab   ← 마감 포지션
│   │
│   └── MacroBar                 ← P1: 매크로 지표 하단 바
│       ├── FearGreedGauge
│       ├── BTCDominance
│       ├── DXYIndicator
│       └── KimchiPremium
│
├── analytics/page.tsx           ← 분석 페이지 (/analytics)
│   ├── PeriodSelector           ← 7D/30D/90D/ALL
│   ├── PnLDashboard             ← P1
│   │   ├── EquityCurve          ← 누적 자산 곡선
│   │   ├── DrawdownChart        ← 고점 대비 하락
│   │   ├── DailyPnLBars         ← 일별 PnL 막대
│   │   └── MetricCards          ← Sharpe/MDD/WinRate 등
│   ├── StrategyComparison       ← P1
│   │   ├── ComparisonTable      ← 지표 비교 테이블
│   │   └── OverlayChart         ← Equity Curve 오버레이
│   └── SignalAnalysis           ← P1
│       ├── SignalHeatmap        ← 시간대별 스코어 히트맵
│       ├── SubScoreRadar        ← 서브스코어 레이더 차트
│       └── SignalTable          ← 시그널 이력 테이블
│
├── settings/page.tsx            ← 설정 페이지 (/settings)
│   ├── StrategyConfigForm       ← P2: 전략 파라미터 수정
│   └── AlertRulesManager        ← P2: 알림 규칙 관리
│
└── backtest/page.tsx            ← 백테스트 뷰어 (/backtest) - P2
    ├── BacktestEquityCurve
    ├── BacktestTradeList
    └── ThresholdSweepHeatmap
```

### Zustand 스토어 구조

```
stores/
├── useBotStore.ts       ← 봇 상태 (WS: bots.status)
├── useTickerStore.ts    ← 실시간 가격 (WS: ticker.BTC-KRW)
├── useOrderStore.ts     ← 주문/포지션 (WS: orders.*, positions.*)
├── useCandleStore.ts    ← 캔들 데이터 (REST 초기 로드 + WS 업데이트)
└── useNotificationStore.ts ← 알림 (WS: notifications) - P2
```

---

## 5. 데이터 흐름 아키텍처

```
┌─────────────┐     ┌───────────────┐     ┌──────────────────┐
│ Upbit WS    │────→│ API Server    │────→│ Dashboard (Next) │
│ (ticker,    │     │ (FastAPI)     │     │                  │
│  trade,     │     │               │     │ ┌──────────┐     │
│  orderbook) │     │ ┌───────────┐ │     │ │ Zustand  │     │
└─────────────┘     │ │ WS Bridge │─┼─WS──│ │ Stores   │     │
                    │ └───────────┘ │     │ └────┬─────┘     │
┌─────────────┐     │               │     │      │           │
│ Bot Process │────→│ ┌───────────┐ │     │ ┌────▼─────┐     │
│ (STR-003)   │     │ │ REST API  │─┼─HTTP│ │ React    │     │
│ (STR-004)   │     │ └───────────┘ │     │ │ Components│    │
│ (STR-005)   │     │               │     │ └──────────┘     │
└─────────────┘     │ ┌───────────┐ │     └──────────────────┘
                    │ │ DB (PG/   │ │
┌─────────────┐     │ │ SQLite)   │ │
│ Bot Control │←────│ │           │ │
│ (start/stop)│     │ └───────────┘ │
└─────────────┘     └───────────────┘

데이터 흐름:
1. 초기 로드: Dashboard → REST GET → API Server → DB → Response
2. 실시간: API Server → WS push → Dashboard Zustand → React re-render
3. 봇 제어: Dashboard → REST POST → API Server → Bot Process Control
4. 가격 스트림: Upbit WS → API Server WS Bridge → Dashboard WS → Ticker Store
```

---

## 6. P0 요구사항 상세 (Must Have)

### P0-1. KPI 헤더

**설명**: 화면 상단 고정 바, 스크롤해도 항상 보이는 핵심 지표 4개

**와이어프레임**:
```
┌──────────────────────────────────────────────────────────┐
│ BTC/KRW              │ Portfolio   │ Total PnL │ Bots    │
│ ₩145,230,000 (+2.3%) │ ₩10,450,000│ +₩450,000 │ 3/3 🟢  │
│ 24H Vol: 1,234 BTC   │            │ (+4.5%)   │ Active  │
└──────────────────────────────────────────────────────────┘
```

**API 요구사항** (→ bot-developer):

| Method | Endpoint | 설명 |
|--------|----------|------|
| - | WS `ticker.BTC-KRW` | 실시간 BTC 가격, 24H 변동, 거래량 |
| GET | `/api/bots/status` | 전체 봇 상태 + 잔고 합산 |

**데이터 계약**:
```typescript
// WS ticker.BTC-KRW
interface TickerUpdate {
  price: number;          // 현재가 (KRW)
  change_pct_24h: number; // 24시간 변동률
  volume_24h: number;     // 24시간 거래량 (BTC)
  bid: number;
  ask: number;
  timestamp: number;      // Unix ms
}
```

**성공 기준**:
- [ ] 가격 업데이트 지연 < 500ms (WS 수신 → UI 반영)
- [ ] 모든 KPI가 above-the-fold에 표시 (스크롤 불필요)
- [ ] 숫자 변동 시 레이아웃 시프트 없음 (tabular-nums 적용)
- [ ] 양수=녹색, 음수=적색 색상 코딩

**구현 복잡도**: **S** (소형)

---

### P0-2. 캔들스틱 차트

**설명**: Lightweight Charts 기반 OHLCV 캔들스틱 + 거래량 + 매매 마커

**와이어프레임**:
```
┌─────────────────────────────────────────────────┐
│  [15m] [1H*] [4H] [1D]                         │
│                                                 │
│       ╻                                         │
│      ╺╋╸   ╻       ╻                           │
│       ╹   ╺╋╸    ╺╋╸  ╻                        │
│            ╹      ╹  ╺╋╸        현재가 ─── ₩145M│
│                       ╹   ╻                     │
│                          ╺╋╸                    │
│   ▲BUY                   ╹      ▼SELL          │
│  Volume ████ ██ ████████ ██ ███ ██████          │
│                                                 │
│  O: 144.8M  H: 145.5M  L: 144.2M  C: 145.2M   │
└─────────────────────────────────────────────────┘
```

**API 요구사항** (→ bot-developer):

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/candles?symbol=BTC/KRW&timeframe=1h&limit=500` | 히스토리컬 OHLCV |
| GET | `/api/orders?status=filled&limit=200` | 체결된 주문 (차트 마커용) |
| - | WS `ticker.BTC-KRW` | 실시간 현재가 (마지막 캔들 업데이트) |

**데이터 계약**:
```typescript
// GET /api/candles
interface CandleData {
  timestamp: number;  // Unix seconds (Lightweight Charts 요구)
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

// GET /api/orders (마커용)
interface TradeMarker {
  timestamp: number;  // Unix seconds
  side: "buy" | "sell";
  price: number;
  amount: number;
  strategy_id: string;
}
```

**성공 기준**:
- [ ] 캔들 500개 초기 로딩 < 1초
- [ ] 타임프레임 전환 < 500ms
- [ ] 실시간 틱으로 마지막 캔들이 실시간 업데이트
- [ ] 새 캔들 자동 생성 (시간 경과 시)
- [ ] 줌/패닝 가능, 크로스헤어 OHLCV 표시
- [ ] 체결된 매수/매도 포인트가 차트에 ▲/▼ 마커로 표시

**구현 복잡도**: **L** (대형) — Lightweight Charts 통합, 실시간 업데이트, 마커 동기화

---

### P0-3. 봇 제어 패널

**설명**: 각 봇의 상태 표시 + Start/Pause/Stop 제어 + 긴급 정지

**와이어프레임**:
```
┌───────────────────────────┐
│  Bot Control              │
├───────────────────────────┤
│ ┌───────────────────────┐ │
│ │ 🟢 STR-003   IDLE     │ │
│ │ PnL: +0.00%           │ │
│ │ Position: None         │ │
│ │ Signal: HOLD (0.05)   │ │
│ │ Uptime: 2d 3h         │ │
│ │ [▶ Start] [⏸] [⏹]    │ │
│ └───────────────────────┘ │
│ ┌───────────────────────┐ │
│ │ 🟡 STR-004   EXECUTING│ │
│ │ PnL: +1.23%           │ │
│ │ Pos: 0.001BTC @₩144.8M│ │
│ │ uPnL: +₩4,200 (+0.3%)│ │
│ │ SL: ₩140.5M           │ │
│ │ [▶] [⏸ Pause] [⏹ Stop]│ │
│ └───────────────────────┘ │
│ ┌───────────────────────┐ │
│ │ 🔵 STR-005   SCANNING │ │
│ │ PnL: -0.31%           │ │
│ │ Position: None         │ │
│ │ Signal: HOLD (-0.02)  │ │
│ │ Uptime: 2d 3h         │ │
│ │ [▶] [⏸] [⏹ Stop]      │ │
│ └───────────────────────┘ │
│                           │
│ ┌───────────────────────┐ │
│ │ 🔴 EMERGENCY STOP ALL │ │  ← 확인 다이얼로그 필수
│ └───────────────────────┘ │
│ ┌───────────────────────┐ │
│ │ ⚡ Close All Positions │ │  ← 체크박스 확인 후 활성화
│ └───────────────────────┘ │
└───────────────────────────┘
```

**API 요구사항** (→ bot-developer):

| Method | Endpoint | 설명 | 응답 |
|--------|----------|------|------|
| GET | `/api/bots/status` | 전체 봇 상태 조회 | `BotStatus[]` |
| POST | `/api/bots/{strategy_id}/start` | 봇 시작 | `BotControlResponse` |
| POST | `/api/bots/{strategy_id}/stop` | 봇 중지 | `BotControlResponse` |
| POST | `/api/bots/{strategy_id}/pause` | 봇 일시정지 | `BotControlResponse` |
| POST | `/api/bots/{strategy_id}/resume` | 봇 재개 | `BotControlResponse` |
| POST | `/api/bots/emergency-stop` | 전체 긴급 중지 | `BotControlResponse` |
| POST | `/api/positions/close-all` | 전 포지션 청산 | `CloseAllResponse` |
| - | WS `bots.status` | 상태 변화 실시간 수신 | `BotStatus` |

**데이터 계약**:
```typescript
// GET /api/bots/status → BotStatus[]
interface BotStatus {
  strategy_id: string;
  state: "IDLE" | "SCANNING" | "VALIDATING" | "EXECUTING"
       | "LOGGING" | "MONITORING" | "PAUSED" | "SHUTTING_DOWN" | "STARTING";
  uptime_seconds: number;
  paper_balance: {
    krw: number;
    btc: number;
    total_value_krw: number;
    initial_krw: number;
    pnl: number;
    pnl_pct: number;
  };
  open_position: {
    symbol: string;
    side: "long";
    amount: number;
    entry_price: number;
    current_price: number;
    stop_loss: number;
    unrealized_pnl: number;
    unrealized_pnl_pct: number;
    opened_at: string;
  } | null;
  last_signal: {
    direction: "BUY" | "SELL" | "HOLD";
    score: number;
    timestamp: string;
  } | null;
  updated_at: string;
}

// POST /api/bots/{strategy_id}/{action}
interface BotControlResponse {
  strategy_id: string;
  action: "start" | "stop" | "pause" | "resume" | "emergency_stop";
  success: boolean;
  new_state: string;
  message?: string;
}

// POST /api/bots/emergency-stop
interface EmergencyStopRequest {
  close_positions: boolean;
  reason?: string;
}
```

**UX 규칙**:
- 상태별 버튼 활성화: IDLE → Start만 활성, SCANNING/EXECUTING → Pause/Stop 활성, PAUSED → Resume/Stop 활성
- Emergency Stop: 클릭 → "정말 모든 봇을 중지하시겠습니까?" 확인 다이얼로그
- Close All Positions: "전체 포지션을 즉시 청산합니다" 체크박스 체크 후 버튼 활성화
- 작업 진행 중(EXECUTING) 중지 시: "현재 주문 완료 후 중지" vs "즉시 중지" 선택

**성공 기준**:
- [ ] 봇 상태 변화 반영 < 1초 (WS 기반)
- [ ] Emergency Stop 실행 → 전 봇 중지 < 3초
- [ ] 버튼 클릭 → 봇 상태 변화 피드백 (로딩 스피너 → 성공/실패 토스트)
- [ ] 실수 방지: Emergency Stop에 확인 다이얼로그, Close All에 체크박스

**구현 복잡도**: **M** (중형)

---

### P0-4. 주문/포지션 테이블

**설명**: 3개 탭으로 구분된 주문/포지션 데이터 테이블

**탭 구조**:

```
[Open Positions] [Order History] [Closed Positions]

── Open Positions ──────────────────────────────────────
│ Strategy │ Side │ Amount   │ Entry    │ Current  │ uPnL      │ SL      │ Duration │
│ STR-004  │ LONG │ 0.001BTC │ ₩144.8M │ ₩145.2M │ +₩4,000   │ ₩140.5M │ 2h 15m   │
│          │      │          │          │          │ (+0.28%)  │         │          │

── Order History ──────────────────────────────────────
│ Time            │ Strategy │ Side │ Amount   │ Price   │ Cost     │ Fee  │ Status │ Mode  │
│ 03-02 14:23:05 │ STR-004  │ BUY  │ 0.001BTC │ ₩144.8M│ ₩144,800│ ₩72  │ filled │ Paper │
│ 03-01 09:15:22 │ STR-003  │ SELL │ 0.002BTC │ ₩143.2M│ ₩286,400│ ₩143 │ filled │ Paper │

── Closed Positions ──────────────────────────────────
│ Strategy │ Opened     │ Closed     │ Entry    │ Exit     │ PnL       │ Duration │
│ STR-003  │ 03-01 09:00│ 03-01 15:30│ ₩142.1M │ ₩143.2M │ +₩2,200   │ 6h 30m   │
│          │            │            │          │          │ (+0.77%)  │          │
```

**API 요구사항** (→ bot-developer):

| Method | Endpoint | Query Params | 설명 |
|--------|----------|-------------|------|
| GET | `/api/positions` | `status=open` | 열린 포지션 |
| GET | `/api/positions` | `status=closed&limit=50&offset=0` | 마감 포지션 (페이지네이션) |
| GET | `/api/orders` | `strategy_id=STR-003&limit=50&offset=0` | 주문 이력 (필터+페이지네이션) |
| - | WS `orders.{strategy_id}` | - | 주문 상태 변화 실시간 |
| - | WS `positions.{strategy_id}` | - | 포지션 변화 실시간 |

**데이터 계약**:
```typescript
// GET /api/positions
interface PositionResponse {
  id: number;
  strategy_id: string;
  symbol: string;
  side: "long";
  entry_price: number;
  amount: number;
  current_price: number;
  stop_loss: number;
  unrealized_pnl: number;
  realized_pnl: number;
  status: "open" | "closed";
  opened_at: string;
  closed_at: string | null;
}

// GET /api/orders
interface OrderResponse {
  id: number;
  strategy_id: string;
  side: "buy" | "sell";
  amount: number;
  price: number;
  cost: number;
  fee: number;
  status: "pending" | "filled" | "cancelled" | "failed";
  is_paper: boolean;
  created_at: string;
  filled_at: string | null;
}

// 페이지네이션 래퍼
interface PaginatedResponse<T> {
  data: T[];
  total: number;
  limit: number;
  offset: number;
}
```

**UX 규칙**:
- PnL 양수: 녹색 배경 + 녹색 텍스트, 음수: 적색 배경 + 적색 텍스트
- 정렬: 각 컬럼 헤더 클릭으로 ASC/DESC 토글
- 필터: 전략 드롭다운, 날짜 범위, 상태 (filled/cancelled/failed)
- 가상 스크롤: 100건 이상 시 TanStack Virtual로 성능 유지

**성공 기준**:
- [ ] 테이블 초기 로딩 < 500ms (50건)
- [ ] 정렬/필터 반응 시간 < 200ms
- [ ] 새 주문 체결 시 실시간 행 추가 (WS)
- [ ] 포지션 PnL 색상 코딩 정확

**구현 복잡도**: **M** (중형)

---

### P0-5. 반응형 레이아웃 기반

**설명**: 데스크톱/태블릿/모바일 3단계 반응형 레이아웃 구조

**Breakpoints**:
| 디바이스 | 범위 | 레이아웃 |
|----------|------|----------|
| Desktop | 1280px+ | 차트(좌) + 봇 패널(우) 2컬럼 |
| Tablet | 768-1279px | 차트(전체폭) → 봇 패널(전체폭) 스태킹 |
| Mobile | < 768px | KPI 축약 + 탭 네비게이션 (Chart/Bots/Orders) |

**성공 기준**:
- [ ] 모바일에서 핵심 KPI 스크롤 없이 확인 가능
- [ ] 모바일에서 Emergency Stop 접근 가능 (2탭 이내)
- [ ] 차트 터치 제스처 지원 (줌/패닝)

**구현 복잡도**: **M** (중형)

---

## 7. P1 요구사항 상세 (Should Have)

### P1-1. PnL 분석 대시보드 (`/analytics`)

**설명**: Equity Curve + Drawdown + Daily PnL + 핵심 지표 카드

**와이어프레임**:
```
┌─────────────────────────────────────────────────────────────┐
│  PnL Analysis    Strategy: [All ▼]   Period: [7D][30D*][ALL]│
├─────────────────────────────────────────────────────────────┤
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐   │
│  │ Return │ │ Sharpe │ │  MDD   │ │WinRate │ │ Trades │   │
│  │ +4.5%  │ │  1.23  │ │ -2.8%  │ │ 61.1%  │ │   18   │   │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘   │
├─────────────────────────────────────────────────────────────┤
│  Equity Curve                                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │         ╱──╲    ╱──────╲                             │   │
│  │    ╱───╱    ╲──╱        ╲──╱──── ₩10.45M            │   │
│  │───╱                                                  │   │
│  │ ₩10.00M                                              │   │
│  └─────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│  Drawdown                                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 0%───────────────────────────────────────────       │   │
│  │          ╲     ╲                                     │   │
│  │           ╲───╱ ╲───╱     Max: -2.8%                │   │
│  └─────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│  Daily PnL                                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │     ██                    ██ ██                       │   │
│  │  ██ ██ ██    ██        ██ ██ ██ ██                   │   │
│  │──────────────────────────────────────── 0            │   │
│  │        ██ ██                   ██                    │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

**API 요구사항** (→ bot-developer):

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/analytics/pnl?strategy_id=all&period=30d` | PnL 분석 데이터 |

**데이터 계약** (→ quant-expert 계산 로직 필요):
```typescript
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
    sharpe_ratio: number | null;   // ← quant-expert: 현재 미계산
    sortino_ratio: number | null;  // ← quant-expert: 현재 미계산
    calmar_ratio: number | null;   // ← quant-expert: 현재 미계산
    max_drawdown_pct: number;
    win_rate: number;
    avg_win: number;
    avg_loss: number;
    profit_factor: number;
    total_trades: number;
    avg_holding_hours: number;
  };
}
```

**quant-expert 의존성**:
- Sharpe Ratio 계산 로직 구현 필요 (일별 수익률 기반, risk-free rate = 0)
- Sortino Ratio 계산 (하방 편차만 패널티)
- Calmar Ratio 계산 (연환산 수익 / MDD)
- bar 단위 equity curve 기반 정확한 Max Drawdown

**성공 기준**:
- [ ] 30일 데이터 분석 렌더링 < 2초
- [ ] Equity Curve가 매 거래 시점에서 정확한 자산 가치 반영
- [ ] Drawdown이 bar 단위로 계산 (거래 시점만이 아닌)
- [ ] 기간 전환 시 차트 애니메이션 전환

**구현 복잡도**: **L** (대형) — 3개 차트 + 지표 계산 + 기간 필터

---

### P1-2. 전략 비교 뷰

**설명**: 멀티 전략 성과 병렬 비교 테이블 + Equity Curve 오버레이

**와이어프레임**:
```
┌─────────────────────────────────────────────────────┐
│  Strategy Comparison     Period: [30D*]              │
│  ☑ STR-003  ☑ STR-004  ☑ STR-005                   │
├──────────┬──────────┬──────────┬────────────────────┤
│ Metric   │ STR-003  │ STR-004  │ STR-005            │
├──────────┼──────────┼──────────┼────────────────────┤
│ Return   │  +2.1%   │  +0.8%   │  +3.4% ★          │
│ Sharpe   │  0.95    │  0.42    │  1.23 ★            │
│ MDD      │  -4.2%   │  -6.1%   │  -2.8% ★          │
│ Trades   │  12      │  8       │  18                │
│ Win Rate │  58%     │  50%     │  61% ★             │
│ Avg Hold │  4.2h    │  8.1h    │  2.5h              │
├──────────┴──────────┴──────────┴────────────────────┤
│  Overlay Equity Curves                               │
│  ── STR-003 (blue)  ── STR-004 (orange)             │
│  ── STR-005 (green)                                  │
│  ┌─────────────────────────────────────────────┐    │
│  │     ╱──╲             ╱────── green           │    │
│  │  ╱╱─╱   ╲──╲╱──╱───╱                        │    │
│  │ ╱╱              ╲──────── blue               │    │
│  │╱                    ╲──── orange              │    │
│  └─────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
```

**API 요구사항** (→ bot-developer):

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/analytics/compare?strategies=STR-003,STR-004,STR-005&period=30d` | 멀티 전략 비교 |

**데이터 계약**:
```typescript
interface StrategyComparison {
  period: string;
  strategies: Array<{
    strategy_id: string;
    metrics: PnLAnalytics["summary"];
    equity_curve: Array<{ date: string; value: number }>;
  }>;
}
```

**성공 기준**:
- [ ] 3개 전략 비교 로딩 < 2초
- [ ] 최적 전략에 ★ 표시 (각 지표별)
- [ ] Equity Curve 오버레이에서 각 전략 구분 가능 (색상 + 범례)
- [ ] 전략 체크박스로 표시/숨김 토글

**구현 복잡도**: **M** (중형)

---

### P1-3. 시그널 분석

**설명**: 시그널 스코어 시각화 (히트맵 + 레이더 차트 + 테이블)

**와이어프레임**:
```
┌─────────────────────────────────────────────────────┐
│  Signal Analysis     Strategy: [STR-005 ▼]          │
├────────────────────────────┬────────────────────────┤
│  Score Heatmap (7D)        │  Sub-score Breakdown   │
│  ┌────────────────────┐   │  (선택한 시그널)         │
│  │ 시간→               │   │  ┌────────────────┐   │
│  │ 00 ░░██░░░░██░░░░  │   │  │   Trend: 0.35  │   │
│  │ 06 ░░░░░░░░░░░░░░  │   │  │  ╱╲             │   │
│  │ 12 ░░░█░░██░░░░██  │   │  │ ╱  ╲  Mom: 0.22│   │
│  │ 18 ░░░░██░░░░░░░░  │   │  │╱    ╲           │   │
│  │                     │   │  │╲    ╱           │   │
│  │  ░ HOLD  █ BUY/SELL │   │  │ Vol: 0.18      │   │
│  └────────────────────┘   │  │ Macro: -0.08    │   │
│                            │  └────────────────┘   │
├────────────────────────────┴────────────────────────┤
│  Signal History                                      │
│  │ Time     │ Dir  │ Score │ Trend │ Mom  │ Vol │ M │
│  │ 14:20:05│ HOLD │ 0.05  │ 0.12  │ 0.08 │-0.02│-0.1│
│  │ 14:05:00│ HOLD │-0.02  │-0.05  │ 0.10 │-0.03│-0.1│
│  │ 13:50:12│ BUY  │ 0.22  │ 0.35  │ 0.22 │ 0.18│-0.1│
└─────────────────────────────────────────────────────┘
```

**API 요구사항** (→ bot-developer):

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/signals?strategy_id=STR-005&limit=200` | 시그널 이력 |

**데이터 계약** (→ quant-expert: details JSON 스키마 정의 필요):
```typescript
interface SignalDetail {
  id: number;
  timestamp: string;
  direction: "BUY" | "SELL" | "HOLD";
  score: number;
  timeframe: string;
  trend_score: number;
  momentum_score: number;
  volume_score: number;
  macro_score: number;
  details: {
    // quant-expert가 정의할 구조화된 상세 데이터
    ema_alignment?: string;
    rsi?: number;
    macd_hist?: number;
    adx?: number;
    stoch_rsi?: number;
    volume_ratio?: number;
    [key: string]: unknown;
  };
}
```

**성공 기준**:
- [ ] 히트맵에서 BUY/SELL 시그널이 시각적으로 즉시 식별 가능
- [ ] 시그널 행 클릭 시 레이더 차트에 서브스코어 표시
- [ ] 테이블 정렬/필터 (방향, 스코어 범위)

**구현 복잡도**: **L** (대형) — 히트맵 + 레이더 차트 + 인터랙티브 테이블

---

### P1-4. 매크로 지표 패널

**설명**: 매크로 스코어 구성 요소의 시각적 게이지 표시

**API 요구사항** (→ bot-developer):

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/macro/latest` | 최신 매크로 데이터 |
| GET | `/api/macro/history?days=7` | 7일 히스토리 (스파크라인용) |

**데이터 계약**:
```typescript
interface MacroData {
  timestamp: string;
  market_score: number;  // 0-10
  fear_greed: number;    // 0-100
  btc_dominance: number; // %
  dxy: number;
  nasdaq: number;
  kimchi_premium: number; // %
}
```

**성공 기준**:
- [ ] 각 매크로 지표에 프로그레스 바 또는 게이지 시각화
- [ ] 7일 변화 추이 스파크라인
- [ ] 마지막 업데이트 시간 + 다음 업데이트 예정 시간 표시

**구현 복잡도**: **S** (소형)

---

### P1-5. 다크/라이트 테마

**설명**: 다크 테마 기본, 라이트 테마 토글 지원

**구현**: shadcn/ui의 `ThemeProvider` + `next-themes` 활용

**성공 기준**:
- [ ] 테마 전환 시 깜박임 없음 (SSR hydration 처리)
- [ ] 차트 색상도 테마에 맞게 변경
- [ ] 시스템 설정 따르기 옵션

**구현 복잡도**: **S** (소형)

---

## 8. P2 요구사항 상세 (Nice to Have)

### P2-1. 기술 지표 오버레이

**설명**: 캔들스틱 차트에 EMA/BB/RSI/MACD 오버레이 토글

**API 요구사항** (→ bot-developer):

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/indicators?symbol=BTC/KRW&tf=1h&indicators=ema20,ema50,bb,rsi,macd` | 지표 데이터 |

**데이터 계약** (→ quant-expert: 지표 계산 로직 제공):
```typescript
interface IndicatorData {
  timestamp: number;
  ema_20?: number;
  ema_50?: number;
  ema_200?: number;
  bb_upper?: number;
  bb_middle?: number;
  bb_lower?: number;
  rsi?: number;            // 별도 패널
  macd_line?: number;      // 별도 패널
  macd_signal?: number;
  macd_hist?: number;
}
```

**구현 복잡도**: **L** (대형) — 멀티 시리즈 오버레이 + 별도 패널 + 토글 UI

---

### P2-2. 전략 파라미터 튜닝 UI

**설명**: 봇 재시작 없이 대시보드에서 전략 파라미터 수정

**API 요구사항** (→ bot-developer):

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/bots/{strategy_id}/config` | 현재 설정 조회 |
| PUT | `/api/bots/{strategy_id}/config` | 설정 변경 + 봇 재시작 |

**데이터 계약** (→ quant-expert: 파라미터 유효 범위 정의):
```typescript
interface StrategyConfig {
  strategy_id: string;
  scoring_mode: "TREND_FOLLOW" | "HYBRID";
  entry_mode: "AND" | "WEIGHTED";
  timeframe_entries: Array<{
    timeframe: "15m" | "1h" | "4h" | "1d";
    weight: number;      // 0.0 ~ 1.0
    threshold?: number;  // 0.0 ~ 1.0
  }>;
  buy_threshold: number;   // 0.05 ~ 0.50
  sell_threshold: number;  // -0.50 ~ -0.05
  stop_loss_pct: number;   // 0.01 ~ 0.10
  max_position_pct: number; // 0.05 ~ 0.50
  trend_filter: boolean;
}
```

**구현 복잡도**: **M** (중형)

---

### P2-3. 알림 센터

**설명**: 브라우저 내 알림 이력 + 알림 규칙 설정

**API 요구사항** (→ bot-developer):

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/notifications?limit=50` | 알림 이력 |
| POST | `/api/alerts/rules` | 알림 규칙 생성 |
| GET | `/api/alerts/rules` | 알림 규칙 목록 |
| DELETE | `/api/alerts/rules/{id}` | 알림 규칙 삭제 |
| - | WS `notifications` | 실시간 알림 수신 |

**데이터 계약**:
```typescript
interface Notification {
  id: string;
  type: "trade" | "stop_loss" | "error" | "daily_summary" | "price_alert" | "bot_state";
  title: string;
  message: string;
  severity: "info" | "warning" | "critical";
  timestamp: string;
  read: boolean;
}

interface AlertRule {
  id?: string;
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

**구현 복잡도**: **L** (대형)

---

### P2-4. 백테스트 결과 뷰어

**설명**: 백테스트 실행 결과를 시각적으로 확인

**API 요구사항** (→ bot-developer, quant-expert):

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/backtest/results` | 백테스트 결과 목록 |
| GET | `/api/backtest/results/{id}` | 특정 백테스트 상세 |

**데이터 계약** (→ quant-expert: 백테스트 엔진 출력 형식 정의):
```typescript
interface BacktestResult {
  id: string;
  strategy_id: string;
  timeframe: string;
  period: { start: string; end: string };
  params: StrategyConfig;
  summary: PnLAnalytics["summary"];
  equity_curve: Array<{ timestamp: number; value: number }>;
  trades: Array<TradeMarker & { pnl: number }>;
  buy_and_hold_return: number;
  alpha: number;
}

// Threshold Sweep용
interface SweepResult {
  buy_threshold: number;
  sell_threshold: number;
  return_pct: number;
  sharpe: number;
  trades: number;
  max_drawdown: number;
}
```

**구현 복잡도**: **XL** (특대형) — 차트 마커 동기화 + Sweep 히트맵 + 다량 데이터

---

### P2-5. 리스크 모니터링 패널

**설명**: RiskManager 상태의 실시간 시각화

**API 요구사항** (→ bot-developer):

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/risk/{strategy_id}/status` | 리스크 상태 |
| - | WS `risk.{strategy_id}` | 리스크 상태 변화 |

**데이터 계약**:
```typescript
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

**bot-developer 의존**: 아키텍처 감사에서 지적된 `RiskManager 상태 영속화(C1)` 구현 선행 필요

**구현 복잡도**: **S** (소형) — API 데이터 있으면 UI는 단순

---

### P2-6. PWA 지원

**설명**: Progressive Web App으로 모바일 홈 화면 추가 + 푸시 알림

**구현**: `next-pwa` + Service Worker + Web Push API

**성공 기준**:
- [ ] 모바일에서 "홈 화면에 추가" 가능
- [ ] 오프라인 시 마지막 캐시된 데이터 표시
- [ ] 브라우저 Push 알림 수신 (매매, 긴급 상황)

**구현 복잡도**: **M** (중형)

---

## 9. API 엔드포인트 종합 (bot-developer 제공 필요)

### REST API 전체 목록

| # | Priority | Method | Endpoint | 설명 |
|---|----------|--------|----------|------|
| 1 | P0 | GET | `/api/bots/status` | 전체 봇 상태 |
| 2 | P0 | POST | `/api/bots/{id}/start` | 봇 시작 |
| 3 | P0 | POST | `/api/bots/{id}/stop` | 봇 중지 |
| 4 | P0 | POST | `/api/bots/{id}/pause` | 봇 일시정지 |
| 5 | P0 | POST | `/api/bots/{id}/resume` | 봇 재개 |
| 6 | P0 | POST | `/api/bots/emergency-stop` | 긴급 전체 중지 |
| 7 | P0 | POST | `/api/positions/close-all` | 전 포지션 청산 |
| 8 | P0 | GET | `/api/candles` | OHLCV 히스토리 |
| 9 | P0 | GET | `/api/orders` | 주문 이력 |
| 10 | P0 | GET | `/api/positions` | 포지션 이력 |
| 11 | P1 | GET | `/api/analytics/pnl` | PnL 분석 |
| 12 | P1 | GET | `/api/analytics/compare` | 전략 비교 |
| 13 | P1 | GET | `/api/signals` | 시그널 이력 |
| 14 | P1 | GET | `/api/macro/latest` | 최신 매크로 |
| 15 | P1 | GET | `/api/macro/history` | 매크로 히스토리 |
| 16 | P2 | GET | `/api/indicators` | 기술 지표 |
| 17 | P2 | GET/PUT | `/api/bots/{id}/config` | 전략 설정 |
| 18 | P2 | GET/POST/DEL | `/api/alerts/rules` | 알림 규칙 |
| 19 | P2 | GET | `/api/risk/{id}/status` | 리스크 상태 |
| 20 | P2 | GET | `/api/notifications` | 알림 이력 |
| 21 | P2 | GET | `/api/backtest/results` | 백테스트 결과 |

### WebSocket 채널 전체 목록

| # | Priority | Channel | Payload | 빈도 |
|---|----------|---------|---------|------|
| 1 | P0 | `ticker.BTC-KRW` | TickerUpdate | 실시간 (~100ms) |
| 2 | P0 | `bots.status` | BotStatus[] | 상태 변화 시 |
| 3 | P0 | `orders.{strategy_id}` | OrderResponse | 이벤트 기반 |
| 4 | P0 | `positions.{strategy_id}` | PositionResponse | 이벤트 기반 |
| 5 | P2 | `risk.{strategy_id}` | RiskStatus | 변화 시 |
| 6 | P2 | `notifications` | Notification | 이벤트 기반 |

---

## 10. quant-expert 제공 필요 데이터

| # | Priority | 데이터 | 현재 상태 | 필요 이유 |
|---|----------|--------|-----------|-----------|
| 1 | P1 | Sharpe Ratio 계산 로직 | 미구현 | PnL 분석 대시보드 |
| 2 | P1 | Sortino Ratio 계산 | 미구현 | PnL 분석 대시보드 |
| 3 | P1 | Calmar Ratio 계산 | 미구현 | PnL 분석 대시보드 |
| 4 | P1 | Bar 단위 Equity Curve | 거래 시점만 계산 | 정확한 MDD 계산 |
| 5 | P1 | Signal details JSON 스키마 | 비구조화 dict | 시그널 분석 레이더 차트 |
| 6 | P2 | 전략 파라미터 유효 범위 | params.py 하드코딩 | 파라미터 튜닝 UI 슬라이더 |
| 7 | P2 | 백테스트 결과 출력 형식 | CLI stdout 전용 | 백테스트 뷰어 |
| 8 | P2 | 지표 계산 함수 | Python 전용 | API 서버에서 지표 계산 |

---

## 11. 구현 복잡도 요약

| ID | 요구사항 | Priority | 복잡도 | 의존성 |
|----|---------|----------|--------|--------|
| P0-1 | KPI 헤더 | P0 | S | WS ticker |
| P0-2 | 캔들스틱 차트 | P0 | L | REST candles + WS ticker |
| P0-3 | 봇 제어 패널 | P0 | M | REST bot control + WS bots.status |
| P0-4 | 주문/포지션 테이블 | P0 | M | REST orders/positions + WS |
| P0-5 | 반응형 레이아웃 | P0 | M | - |
| P1-1 | PnL 분석 | P1 | L | quant: Sharpe/Sortino |
| P1-2 | 전략 비교 | P1 | M | P1-1 데이터 |
| P1-3 | 시그널 분석 | P1 | L | quant: details 스키마 |
| P1-4 | 매크로 패널 | P1 | S | REST macro |
| P1-5 | 다크/라이트 테마 | P1 | S | - |
| P2-1 | 기술 지표 오버레이 | P2 | L | quant: 지표 계산 |
| P2-2 | 파라미터 튜닝 | P2 | M | quant: 파라미터 범위 |
| P2-3 | 알림 센터 | P2 | L | WS notifications |
| P2-4 | 백테스트 뷰어 | P2 | XL | quant: 백테스트 형식 |
| P2-5 | 리스크 모니터링 | P2 | S | arch: 리스크 영속화(C1) |
| P2-6 | PWA | P2 | M | - |

**총 추정**: P0 5항목 (S+L+M+M+M), P1 5항목 (L+M+L+S+S), P2 6항목 (L+M+L+XL+S+M)

---

## 12. 구현 로드맵 제안

### Sprint 1 (Week 1-2): P0 기반
- Next.js 프로젝트 초기화 + TailwindCSS + shadcn/ui + 다크 테마
- 디자인 시스템 토큰 (색상, 타이포그래피, 숫자 포맷)
- WebSocket 클라이언트 + Zustand 스토어
- P0-1 KPI 헤더
- P0-5 반응형 레이아웃 기반 그리드

### Sprint 2 (Week 3-4): P0 완성
- P0-2 Lightweight Charts 캔들스틱 + 거래 마커
- P0-3 봇 제어 패널 (API 연동)
- P0-4 주문/포지션 테이블 (TanStack Table)
- **의존**: API 서버 P0 REST/WS 엔드포인트 완료 필요

### Sprint 3 (Week 5-6): P1 분석
- P1-1 PnL 분석 (Equity Curve + Drawdown + Daily PnL)
- P1-2 전략 비교 뷰
- P1-4 매크로 패널
- P1-5 테마 토글
- **의존**: quant-expert Sharpe/Sortino 계산 로직

### Sprint 4 (Week 7-8): P1 완성 + P2 시작
- P1-3 시그널 분석 (히트맵 + 레이더)
- P2-1 기술 지표 오버레이
- P2-2 파라미터 튜닝 UI
- P2-6 PWA 설정

### Sprint 5 (Week 9-10): P2 완성
- P2-3 알림 센터
- P2-4 백테스트 뷰어
- P2-5 리스크 모니터링
- 전체 QA + 성능 최적화
