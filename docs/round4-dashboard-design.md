# Round 4: 대시보드 상세 설계서

**작성일**: 2026-03-02
**작성자**: dashboard-designer
**기반**: TDR (round3-tech-decisions.md), 대시보드 요구사항서 (round2-dashboard-requirements.md), 아키텍처 요구사항서 (round2-architecture-requirements.md)
**기술 스택**: Next.js 15 + TailwindCSS + shadcn/ui + Zustand + Lightweight Charts 4.x + Recharts

---

## 목차

1. [페이지 구조 및 라우팅](#1-페이지-구조-및-라우팅)
2. [컴포넌트 계층 및 Props/State 정의](#2-컴포넌트-계층-및-propsstate-정의)
3. [실시간 데이터 흐름 설계](#3-실시간-데이터-흐름-설계)
4. [봇 관리 UI 상세 설계](#4-봇-관리-ui-상세-설계)
5. [차트 설계](#5-차트-설계)
6. [디자인 시스템](#6-디자인-시스템)
7. [반응형 설계](#7-반응형-설계)
8. [API 연동 설계](#8-api-연동-설계)

---

## 1. 페이지 구조 및 라우팅

### 1.1 App Router 구조

```
dashboard/src/app/
├── layout.tsx              # RootLayout: 폰트, ThemeProvider, WS Provider
├── page.tsx                # / — 메인 대시보드 (P0)
├── analytics/
│   └── page.tsx            # /analytics — PnL 분석 + 전략 비교 (P1)
├── settings/
│   └── page.tsx            # /settings — 전략 파라미터 + 알림 규칙 (P2)
├── backtest/
│   └── page.tsx            # /backtest — 백테스트 뷰어 (P2)
├── globals.css             # TailwindCSS 기본 + 디자인 토큰
├── loading.tsx             # 전역 로딩 스켈레톤
├── error.tsx               # 전역 에러 바운더리
└── not-found.tsx           # 404 페이지
```

### 1.2 레이아웃 계층

```
RootLayout (layout.tsx)
├── ThemeProvider (next-themes)
├── WebSocketProvider (Context)
├── Toaster (sonner)
└── children
    ├── TopNav (모든 페이지 공통)
    │   ├── Logo + 앱 이름
    │   ├── NavLinks: [Dashboard, Analytics, Settings]
    │   ├── ConnectionStatus (WS 상태 인디케이터)
    │   ├── NotificationBell (P2)
    │   └── ThemeToggle
    └── <main> (페이지별 콘텐츠)
```

### 1.3 라우트별 데이터 페칭 전략

| 라우트 | 초기 로드 | 실시간 업데이트 | 캐시 전략 |
|--------|----------|---------------|----------|
| `/` | REST: bots/status, candles, positions | WS: ticker, bots.status, orders, positions | stale-while-revalidate, 5s |
| `/analytics` | REST: analytics/pnl, analytics/compare, signals | 없음 (정적 분석) | cache 30s, 기간 변경 시 refetch |
| `/settings` | REST: bots/{strategy_id}/config (P2), alerts/rules (P2) | 없음 | no-cache |
| `/backtest` | REST: backtest/results (P2) | 없음 | cache 5min |

### 1.4 네비게이션 설계

```
Desktop TopNav:
┌──────────────────────────────────────────────────────────────────────┐
│ [◆ traderj]  [Dashboard]  [Analytics]  [Settings]    [●] [🔔] [◑] │
└──────────────────────────────────────────────────────────────────────┘
               active=underline                         WS  P2  Theme

Mobile Bottom Nav:
┌──────────────────────────────────────┐
│          (페이지 콘텐츠)               │
├──────────────────────────────────────┤
│  [📊 Dashboard] [📈 Analytics] [⚙]  │
└──────────────────────────────────────┘
```

- `Dashboard` 탭: `/` 메인 모니터링
- `Analytics` 탭: `/analytics` 성과 분석
- `Settings` (⚙ 아이콘): `/settings` 드롭다운 메뉴에서 Settings, Backtest 진입

---

## 2. 컴포넌트 계층 및 Props/State 정의

### 2.1 전체 컴포넌트 트리

```
dashboard/src/
├── app/                           # Next.js App Router 페이지
│
├── components/
│   ├── layout/                    # 레이아웃 컴포넌트
│   │   ├── TopNav.tsx             # 상단 네비게이션
│   │   ├── MobileBottomNav.tsx    # 모바일 하단 탭
│   │   ├── ConnectionStatus.tsx   # WS 연결 상태 표시
│   │   └── PageShell.tsx          # 페이지 래퍼 (max-width, padding)
│   │
│   ├── dashboard/                 # 메인 대시보드 (/) 전용
│   │   ├── KPIHeader.tsx          # P0-1: 핵심 지표 상단 바
│   │   ├── PriceTicker.tsx        # KPI: BTC 실시간 가격
│   │   ├── PortfolioValue.tsx     # KPI: 총 포트폴리오 가치
│   │   ├── TotalPnL.tsx           # KPI: 총 PnL
│   │   ├── ActiveBotCount.tsx     # KPI: 활성 봇 수
│   │   ├── CandlestickPanel.tsx   # P0-2: 차트 영역 컨테이너
│   │   ├── LWChartWrapper.tsx     # Lightweight Charts 래퍼
│   │   ├── TimeframeSelector.tsx  # 타임프레임 버튼 그룹
│   │   ├── BotControlPanel.tsx    # P0-3: 봇 관리 패널
│   │   ├── BotCard.tsx            # 개별 봇 카드
│   │   ├── BotStatusBadge.tsx     # 상태 배지 (색상 + 텍스트)
│   │   ├── ControlButtons.tsx     # Start/Pause/Stop 버튼 그룹
│   │   ├── EmergencyStopButton.tsx # 긴급 전체 중지
│   │   ├── CloseAllButton.tsx     # 전 포지션 청산
│   │   ├── DataTabs.tsx           # P0-4: 주문/포지션 탭 컨테이너
│   │   ├── OpenPositionsTab.tsx   # 열린 포지션 테이블
│   │   ├── OrderHistoryTab.tsx    # 주문 이력 테이블
│   │   ├── ClosedPositionsTab.tsx # 마감 포지션 테이블
│   │   └── MacroBar.tsx           # P1-4: 매크로 지표 하단 바
│   │
│   ├── analytics/                 # 분석 페이지 (/analytics) 전용
│   │   ├── PeriodSelector.tsx     # 기간 선택 (7D/30D/90D/ALL)
│   │   ├── MetricCards.tsx        # 성과 지표 카드 그리드
│   │   ├── EquityCurve.tsx        # 누적 자산 곡선 (Recharts)
│   │   ├── DrawdownChart.tsx      # 고점 대비 하락 (Recharts)
│   │   ├── DailyPnLBars.tsx       # 일별 PnL 막대 차트 (Recharts)
│   │   ├── StrategyComparison.tsx # 전략 비교 컨테이너
│   │   ├── ComparisonTable.tsx    # 지표 비교 테이블
│   │   ├── OverlayChart.tsx       # Equity Curve 오버레이 (Recharts)
│   │   ├── SignalHeatmap.tsx      # 시간대별 스코어 히트맵
│   │   ├── SubScoreRadar.tsx      # 서브스코어 레이더 차트 (Recharts)
│   │   └── SignalTable.tsx        # 시그널 이력 테이블
│   │
│   ├── settings/                  # 설정 페이지 (P2) 전용
│   │   ├── StrategyConfigForm.tsx # 전략 파라미터 폼
│   │   └── AlertRulesManager.tsx  # 알림 규칙 관리
│   │
│   └── ui/                        # 공유 UI 컴포넌트 (shadcn/ui 확장)
│       ├── NumberDisplay.tsx       # 숫자 포맷팅 (KRW/BTC/%)
│       ├── PnLText.tsx            # 양수/음수 색상 텍스트
│       ├── ConfirmDialog.tsx      # 확인 다이얼로그
│       ├── DataTable.tsx          # TanStack Table 래퍼
│       ├── SparkLine.tsx          # 미니 스파크라인 (Recharts)
│       ├── StatusDot.tsx          # 상태 인디케이터 원형
│       ├── SkeletonCard.tsx       # 로딩 스켈레톤
│       └── EmptyState.tsx         # 빈 상태 표시
│
├── stores/                        # Zustand 스토어
│   ├── useBotStore.ts
│   ├── useTickerStore.ts
│   ├── useOrderStore.ts
│   ├── useCandleStore.ts
│   └── useAlertStore.ts            # (구 useNotificationStore) alerts 채널과 명칭 통일
│
├── lib/                           # 유틸리티 & 설정
│   ├── api-client.ts              # fetch 래퍼 (base URL, headers)
│   ├── ws-client.ts               # WebSocket 클라이언트
│   ├── format.ts                  # 숫자/날짜 포맷 유틸
│   ├── constants.ts               # 상수 (색상, 브레이크포인트)
│   └── hooks/                     # 커스텀 훅
│       ├── useWebSocket.ts        # WS 연결 관리
│       ├── useBots.ts             # 봇 데이터 fetch + mutation
│       ├── useCandles.ts          # 캔들 데이터 fetch
│       └── useAnalytics.ts        # 분석 데이터 fetch
│
└── types/                         # TypeScript 타입
    ├── api.ts                     # OpenAPI 자동 생성 타입
    └── chart.ts                   # 차트 전용 타입
```

### 2.2 핵심 컴포넌트 Props/State 정의

#### KPIHeader

```typescript
// components/dashboard/KPIHeader.tsx
// 외부 Props: 없음 (스토어에서 직접 구독)
// 내부 State: 없음 (순수 표시 컴포넌트)

export function KPIHeader() {
  const ticker = useTickerStore((s) => s.ticker);
  const bots = useBotStore((s) => s.bots);

  const portfolioValue = useMemo(() =>
    bots.reduce((sum, b) => sum + b.paper_balance.total_value_krw, 0),
    [bots]
  );

  const totalPnL = useMemo(() =>
    bots.reduce((sum, b) => sum + b.paper_balance.pnl, 0),
    [bots]
  );

  return (
    // sticky top-0, z-10, backdrop-blur
    // 4개 KPI: PriceTicker, PortfolioValue, TotalPnL, ActiveBotCount
  );
}
```

#### BotCard

```typescript
// components/dashboard/BotCard.tsx
interface BotCardProps {
  bot: BotStatus;
  onStart: (strategyId: string) => Promise<void>;
  onStop: (strategyId: string) => Promise<void>;
  onPause: (strategyId: string) => Promise<void>;
  onResume: (strategyId: string) => Promise<void>;
}

// 내부 State:
// - isActionPending: boolean (버튼 로딩 상태)
// - actionError: string | null (실패 메시지)
```

#### LWChartWrapper

```typescript
// components/dashboard/LWChartWrapper.tsx
interface LWChartWrapperProps {
  candles: CandleData[];
  markers: TradeMarker[];
  currentPrice: number | null;  // 실시간 가격 → 마지막 캔들 업데이트
  timeframe: Timeframe;
  height: number;
}

// 내부 State:
// - chartRef: IChartApi (Lightweight Charts 인스턴스)
// - candleSeriesRef: ISeriesApi<"Candlestick">
// - volumeSeriesRef: ISeriesApi<"Histogram">
// - crosshairData: { time, open, high, low, close, volume } | null
```

#### DataTable (공유)

```typescript
// components/ui/DataTable.tsx
interface DataTableProps<T> {
  data: T[];
  columns: ColumnDef<T>[];
  pagination?: {
    total: number;
    page: number;
    pageSize: number;
    onPageChange: (page: number) => void;
  };
  loading?: boolean;
  emptyMessage?: string;
  onRowClick?: (row: T) => void;
  virtualScroll?: boolean;     // 100건+ 시 활성화
}
```

#### NumberDisplay (공유)

```typescript
// components/ui/NumberDisplay.tsx
interface NumberDisplayProps {
  value: number;
  format: "krw" | "btc" | "percent" | "number";
  showSign?: boolean;          // +/- 부호 표시
  colorCode?: boolean;         // 양수=green, 음수=red
  size?: "sm" | "md" | "lg";
  mono?: boolean;              // 모노스페이스 폰트 (tabular-nums)
}

// 포맷 규칙:
// krw:     ₩145,230,000
// btc:     0.00123456 BTC
// percent: +2.34%
// number:  1,234
```

### 2.3 Zustand 스토어 상세 설계

```typescript
// stores/useTickerStore.ts
interface TickerState {
  ticker: TickerUpdate | null;
  isConnected: boolean;
  lastUpdated: number;

  // Actions
  updateTicker: (data: TickerUpdate) => void;
  setConnected: (connected: boolean) => void;
}

// stores/useBotStore.ts
interface BotState {
  bots: BotStatus[];
  isLoading: boolean;
  error: string | null;

  // Actions
  setBots: (bots: BotStatus[]) => void;
  updateBot: (strategyId: string, update: Partial<BotStatus>) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
}

// stores/useOrderStore.ts
interface OrderState {
  openPositions: PositionResponse[];
  orders: OrderResponse[];
  closedPositions: PositionResponse[];

  // Pagination state
  ordersPagination: { total: number; page: number; pageSize: number };

  // Actions
  setOpenPositions: (positions: PositionResponse[]) => void;
  addOrder: (order: OrderResponse) => void;
  updatePosition: (id: number, update: Partial<PositionResponse>) => void;
  setOrders: (orders: OrderResponse[], pagination: PaginationMeta) => void;
}

// stores/useCandleStore.ts
interface CandleState {
  candles: Record<Timeframe, CandleData[]>;  // 타임프레임별 캐시
  activeTimeframe: Timeframe;
  markers: TradeMarker[];

  // Actions
  setCandles: (tf: Timeframe, candles: CandleData[]) => void;
  appendCandle: (tf: Timeframe, candle: CandleData) => void;
  updateLastCandle: (tf: Timeframe, price: number) => void;
  setActiveTimeframe: (tf: Timeframe) => void;
  setMarkers: (markers: TradeMarker[]) => void;
}

// stores/useAlertStore.ts (P2) — WS alerts 채널과 명칭 통일
interface AlertState {
  alerts: AlertNotification[];
  unreadCount: number;

  // Actions
  addAlert: (a: AlertNotification) => void;
  markAsRead: (id: string) => void;
  markAllAsRead: () => void;
}
```

**스토어 선택자 최적화**:

```typescript
// shallow 비교로 불필요한 리렌더 방지
const botCount = useBotStore(
  (s) => s.bots.filter((b) => b.state !== "SHUTTING_DOWN").length
);

// 파생 상태를 스토어 외부에서 useMemo로 계산
const totalPnL = useMemo(
  () => bots.reduce((sum, b) => sum + b.paper_balance.pnl, 0),
  [bots]
);
```

---

## 3. 실시간 데이터 흐름 설계

### 3.1 WebSocket 연결 관리

```typescript
// lib/ws-client.ts

const WS_BASE_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

interface WSConfig {
  reconnect: {
    initialDelay: 1000;        // 1초
    maxDelay: 30000;           // 30초
    backoffMultiplier: 2;
    jitter: true;              // ±20% 랜덤 변동
    maxRetries: Infinity;      // 무한 재시도
  };
  heartbeat: {
    interval: 30000;           // 30초마다 ping
    timeout: 10000;            // pong 미수신 시 연결 끊김 판단
  };
}
```

**WebSocket 프로토콜** (bot-developer 합의):

```typescript
// 클라이언트 → 서버 메시지
type WSClientMessage =
  | { type: "subscribe"; channel: string }
  | { type: "unsubscribe"; channel: string }
  | { type: "ping" };

// 서버 → 클라이언트 메시지
type WSServerMessage =
  | { type: "data"; channel: string; data: unknown; timestamp: number }
  | { type: "pong" }
  | { type: "error"; message: string; channel?: string }
  | { type: "subscribed"; channel: string }
  | { type: "unsubscribed"; channel: string };
```

### 3.2 연결 생명주기

```
앱 초기화
  │
  ▼
WebSocketProvider 마운트
  │
  ├─ connect(WS_BASE_URL)
  │    │
  │    ▼
  │  onopen
  │    ├─ subscribe("ticker.BTC-KRW")
  │    ├─ subscribe("bots.status")
  │    ├─ subscribe("orders.*")
  │    └─ subscribe("positions.*")
  │
  ├─ 메시지 수신 루프
  │    │
  │    ├─ type:"data", channel:"ticker.BTC-KRW"
  │    │    → useTickerStore.updateTicker(data)
  │    │    → useCandleStore.updateLastCandle(activeTimeframe, data.price)
  │    │
  │    ├─ type:"data", channel:"bots.status"
  │    │    → useBotStore.updateBot(data.strategy_id, data)
  │    │
  │    ├─ type:"data", channel:"orders.*"
  │    │    → useOrderStore.addOrder(data)
  │    │    → toast 알림 ("STR-004 BUY 주문 체결")
  │    │
  │    ├─ type:"data", channel:"positions.*"
  │    │    → useOrderStore.updatePosition(data.id, data)
  │    │
  │    └─ type:"pong"
  │         → heartbeat 타이머 리셋
  │
  ├─ Heartbeat 루프 (30초마다)
  │    └─ send({ type: "ping" })
  │         └─ 10초 내 pong 미수신 → 연결 끊김 판단 → reconnect
  │
  └─ onclose / onerror
       └─ Reconnection 전략 실행
            ├─ delay = min(initialDelay * 2^attempt, maxDelay)
            ├─ jitter = delay * (0.8 + Math.random() * 0.4)
            ├─ setTimeout(connect, jitter)
            └─ 연결 성공 시:
                 ├─ attempt = 0
                 └─ 모든 채널 재구독 (subscription 목록 유지)
```

### 3.3 WebSocket Provider (React Context)

```typescript
// lib/hooks/useWebSocket.ts

interface WebSocketContextValue {
  status: "connecting" | "connected" | "disconnected" | "reconnecting";
  subscribe: (channel: string) => void;
  unsubscribe: (channel: string) => void;
  reconnectAttempt: number;
}

// 사용 예:
function DashboardPage() {
  const { status } = useWebSocket();

  // 페이지 마운트 시 자동 구독 (Provider가 관리)
  // 페이지 언마운트 시 자동 구독 해제 (채널 참조 카운팅)
}
```

### 3.4 데이터 흐름 다이어그램

```
┌──────────┐   REST (초기 로드)    ┌────────────┐
│ Next.js  │◄─────────────────────│ FastAPI     │
│ Dashboard│                      │ API Server  │
│          │   WebSocket (실시간)  │             │
│ ┌──────┐ │◄═════════════════════│ ┌─────────┐ │
│ │Zustand│ │                      │ │WS Bridge│ │
│ │Stores │ │                      │ └────┬────┘ │
│ └──┬───┘ │                      │      │      │
│    │     │                      │      │      │
│ ┌──▼───┐ │                      │ ┌────▼────┐ │    ┌──────────┐
│ │React │ │                      │ │EventBus │ │◄───│ Trading  │
│ │ UI   │ │   POST (봇 제어)     │ │(asyncio)│ │    │ Engine   │
│ └──────┘ │─────────────────────►│ └─────────┘ │    │ (STR-*)  │
└──────────┘                      │             │    └──────────┘
                                  │ ┌─────────┐ │    ┌──────────┐
                                  │ │PostgreSQL│ │◄───│ Upbit WS │
                                  │ │+Timescale│ │    │ (ticker) │
                                  │ └─────────┘ │    └──────────┘
                                  └────────────┘

데이터 흐름 번호:
① 초기 로드: Dashboard → GET /api/v1/bots → API → DB → Response → Zustand
② 실시간 틱: Upbit WS → EventBus → WS Bridge → Dashboard WS → tickerStore
③ 봇 상태: Engine state change → EventBus → WS Bridge → botStore
④ 봇 제어: Dashboard → POST /api/v1/bots/{id}/pause → API → Engine
⑤ 주문 이벤트: Engine → EventBus → WS Bridge → orderStore + toast
```

### 3.5 Optimistic Update 패턴

봇 제어 버튼 클릭 시 UI를 즉시 업데이트하고, 서버 확인 후 최종 반영:

```typescript
async function handlePauseBot(strategyId: string) {
  // 1. Optimistic: 즉시 UI에 PAUSED 표시 + 버튼 비활성화
  useBotStore.getState().updateBot(strategyId, {
    state: "PAUSED",
    _optimistic: true,
  });

  try {
    // 2. 서버 요청
    const res = await apiClient.post(`/api/v1/bots/${strategyId}/pause`);

    // 3. 성공: WS에서 확정 상태 수신 대기 (자동 반영)
    toast.success(`${strategyId} 일시정지됨`);
  } catch (err) {
    // 4. 실패: Optimistic 롤백
    useBotStore.getState().updateBot(strategyId, {
      state: previousState,
      _optimistic: false,
    });
    toast.error(`${strategyId} 일시정지 실패: ${err.message}`);
  }
}
```

---

## 4. 봇 관리 UI 상세 설계

### 4.1 봇 상태 모델

```typescript
type BotState =
  | "IDLE"           // 대기 (스캔 안 함)
  | "SCANNING"       // 시그널 스캔 중
  | "VALIDATING"     // 리스크 체크 중
  | "EXECUTING"      // 주문 실행 중
  | "LOGGING"        // 거래 기록 중
  | "MONITORING"     // 포지션 모니터링 중
  | "PAUSED"         // 사용자에 의해 일시정지
  | "SHUTTING_DOWN"  // 종료 진행 중
  | "STARTING";      // 기동 중
```

### 4.2 상태별 시각화 규칙

| 상태 | 색상 | 아이콘 | 배지 스타일 | 설명 |
|------|------|--------|------------|------|
| IDLE | `--color-muted` (gray-400) | `○` | ghost | 대기 중 |
| SCANNING | `--color-info` (blue-500) | `◉` pulse | outline-blue | 시그널 탐색 중 |
| VALIDATING | `--color-info` (blue-500) | `◉` | outline-blue | 리스크 검증 중 |
| EXECUTING | `--color-warning` (amber-500) | `◉` pulse | solid-amber | 주문 실행 중 (주의) |
| LOGGING | `--color-info` (blue-500) | `◉` | outline-blue | 기록 중 |
| MONITORING | `--color-positive` (green-500) | `●` | solid-green | 포지션 감시 중 |
| PAUSED | `--color-negative` (red-400) | `❚❚` | solid-red | 일시정지 |
| SHUTTING_DOWN | `--color-muted` (gray-500) | `↓` spin | ghost | 종료 중 |
| STARTING | `--color-muted` (gray-500) | `↑` spin | ghost | 시작 중 |

### 4.3 상태별 버튼 활성화 매트릭스

| 현재 상태 | Start | Pause | Resume | Stop |
|-----------|-------|-------|--------|------|
| IDLE | **활성** | 비활성 | 비활성 | 비활성 |
| SCANNING | 비활성 | **활성** | 비활성 | **활성** |
| VALIDATING | 비활성 | **활성** | 비활성 | **활성** |
| EXECUTING | 비활성 | 비활성(주1) | 비활성 | **활성**(주2) |
| LOGGING | 비활성 | 비활성 | 비활성 | 비활성 |
| MONITORING | 비활성 | **활성** | 비활성 | **활성** |
| PAUSED | 비활성 | 비활성 | **활성** | **활성** |
| SHUTTING_DOWN | 비활성 | 비활성 | 비활성 | 비활성 |
| STARTING | 비활성 | 비활성 | 비활성 | 비활성 |

- 주1: EXECUTING 중 Pause 누르면 "현재 주문 완료 후 일시정지됩니다" 토스트
- 주2: EXECUTING 중 Stop 누르면 확인 다이얼로그 (아래 참조)

### 4.4 확인 다이얼로그 설계

#### Emergency Stop 다이얼로그

```
┌─────────────────────────────────────────────┐
│  ⚠ 긴급 전체 중지                              │
│                                              │
│  모든 봇을 즉시 중지합니다.                      │
│                                              │
│  ☐ 열린 포지션도 즉시 시장가 청산               │
│                                              │
│  현재 상태:                                    │
│  • STR-003: SCANNING (포지션 없음)             │
│  • STR-004: MONITORING (0.001 BTC 보유)       │
│  • STR-005: SCANNING (포지션 없음)             │
│                                              │
│  ┌─────────────┐  ┌──────────────────────┐  │
│  │   취소       │  │  🔴 긴급 중지 실행    │  │
│  └─────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────┘
```

- "열린 포지션도 즉시 시장가 청산" 체크 시 → `EmergencyStopRequest.close_positions = true`
- 확인 버튼: 3초 카운트다운 후 활성화 (실수 방지)
- 확인 버튼 색상: `bg-red-600 hover:bg-red-700`

#### Close All Positions 다이얼로그

```
┌─────────────────────────────────────────────┐
│  ⚡ 전체 포지션 청산                           │
│                                              │
│  현재 열린 포지션:                              │
│  • STR-004: 0.001 BTC @ ₩144,800,000        │
│    미실현 PnL: +₩4,200 (+0.29%)              │
│                                              │
│  ☑ "전체 포지션을 즉시 시장가 청산합니다"       │
│    를 확인했습니다.                             │
│                                              │
│  ┌─────────────┐  ┌──────────────────────┐  │
│  │   취소       │  │  ⚡ 전체 청산 실행    │  │
│  └─────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────┘
```

- 체크박스 체크 전: 확인 버튼 비활성
- 포지션이 없으면: "현재 열린 포지션이 없습니다" 표시, 확인 버튼 비활성

#### EXECUTING 중 Stop 다이얼로그

```
┌─────────────────────────────────────────────┐
│  ⚠ STR-004 중지                              │
│                                              │
│  현재 주문이 실행 중입니다.                     │
│                                              │
│  ○ 현재 주문 완료 후 중지 (권장)               │
│  ○ 즉시 중지 (미체결 주문 취소)                │
│                                              │
│  ┌─────────────┐  ┌──────────────────────┐  │
│  │   취소       │  │  중지 실행            │  │
│  └─────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────┘
```

### 4.5 BotCard 상세 와이어프레임

```
포지션 있는 봇 (확장 상태):
┌─────────────────────────────────────────┐
│  ● STR-004                    MONITORING │  ← BotStatusBadge
│─────────────────────────────────────────│
│  PnL: +₩45,200 (+1.23%)                 │  ← PnLText (green)
│                                          │
│  Position                                │
│  ├─ Side: LONG                           │
│  ├─ Amount: 0.001 BTC                    │
│  ├─ Entry: ₩144,800,000                  │
│  ├─ Current: ₩145,230,000               │
│  ├─ uPnL: +₩4,200 (+0.29%)             │  ← PnLText (green)
│  └─ Stop Loss: ₩140,500,000             │
│                                          │
│  Signal: HOLD (0.05)    3분 전            │
│  Uptime: 2d 3h 15m                       │
│                                          │
│  [⏸ Pause]  [⏹ Stop]                    │  ← ControlButtons
└─────────────────────────────────────────┘

포지션 없는 봇 (축소 상태):
┌─────────────────────────────────────────┐
│  ◉ STR-003                      SCANNING │
│  PnL: +₩0 (0.00%)   Signal: HOLD (0.02) │
│  Uptime: 2d 3h 15m                       │
│  [⏸ Pause]  [⏹ Stop]                    │
└─────────────────────────────────────────┘
```

### 4.6 액션 피드백 UX

| 단계 | 시각적 피드백 |
|------|-------------|
| 버튼 클릭 | 버튼 → spinner + 비활성화 |
| 서버 응답 수신 (성공) | spinner 해제, toast.success |
| 서버 응답 수신 (실패) | spinner 해제, toast.error + 상태 롤백 |
| WS 상태 확인 수신 | BotStatusBadge 업데이트 + 미묘한 펄스 애니메이션 |
| 타임아웃 (10초) | spinner → 경고 아이콘, "응답 지연 중. 새로고침하세요." |

---

## 5. 차트 설계

### 5.1 Lightweight Charts 캔들스틱 구성

```typescript
// components/dashboard/LWChartWrapper.tsx

import { createChart, ColorType } from "lightweight-charts";

function createChartInstance(container: HTMLElement, isDark: boolean) {
  return createChart(container, {
    layout: {
      background: {
        type: ColorType.Solid,
        color: isDark ? "#0a0a0f" : "#ffffff",
      },
      textColor: isDark ? "#e4e4e7" : "#1a1a2e",
      fontFamily: "'Inter', sans-serif",
      fontSize: 12,
    },
    grid: {
      vertLines: { color: isDark ? "#1a1a2e" : "#f0f0f0" },
      horzLines: { color: isDark ? "#1a1a2e" : "#f0f0f0" },
    },
    crosshair: {
      mode: 0,                       // Normal
      vertLine: { labelBackgroundColor: isDark ? "#3b82f6" : "#2563eb" },
      horzLine: { labelBackgroundColor: isDark ? "#3b82f6" : "#2563eb" },
    },
    rightPriceScale: {
      borderColor: isDark ? "#1a1a2e" : "#e0e0e0",
      autoScale: true,
      scaleMargins: { top: 0.1, bottom: 0.25 },  // 하단 25% = 볼륨 영역
    },
    timeScale: {
      borderColor: isDark ? "#1a1a2e" : "#e0e0e0",
      timeVisible: true,
      secondsVisible: false,
      tickMarkFormatter: (time: number) => {
        // KST 변환 + 타임프레임별 포맷
      },
    },
    localization: {
      priceFormatter: (price: number) =>
        `₩${price.toLocaleString("ko-KR")}`,
    },
  });
}
```

### 5.2 캔들스틱 + 볼륨 시리즈

```typescript
// 캔들스틱 시리즈
const candleSeries = chart.addCandlestickSeries({
  upColor: "#22c55e",           // green-500
  downColor: "#ef4444",         // red-500
  borderUpColor: "#22c55e",
  borderDownColor: "#ef4444",
  wickUpColor: "#22c55e80",     // 50% 투명
  wickDownColor: "#ef444480",
});

// 볼륨 히스토그램 시리즈 (하단 영역)
const volumeSeries = chart.addHistogramSeries({
  priceFormat: { type: "volume" },
  priceScaleId: "volume",       // 별도 price scale
});

chart.priceScale("volume").applyOptions({
  scaleMargins: { top: 0.8, bottom: 0 },  // 하단 20%만 사용
});
```

### 5.3 거래 마커

```typescript
// 체결된 주문을 차트 마커로 표시
interface ChartMarker {
  time: number;                 // Unix seconds
  position: "aboveBar" | "belowBar";
  color: string;
  shape: "arrowUp" | "arrowDown";
  text: string;
}

function createTradeMarkers(trades: TradeMarker[]): ChartMarker[] {
  return trades.map((t) => ({
    time: t.timestamp,
    position: t.side === "buy" ? "belowBar" : "aboveBar",
    color: t.side === "buy" ? "#22c55e" : "#ef4444",
    shape: t.side === "buy" ? "arrowUp" : "arrowDown",
    text: `${t.side.toUpperCase()} ${t.amount}`,
  }));
}

// candleSeries.setMarkers(markers);
```

### 5.4 실시간 캔들 업데이트 로직

```typescript
// WS ticker → 마지막 캔들 업데이트
function handleTickerUpdate(ticker: TickerUpdate, activeTimeframe: Timeframe) {
  const store = useCandleStore.getState();
  const candles = store.candles[activeTimeframe];
  if (!candles.length) return;

  const lastCandle = candles[candles.length - 1];
  const currentPrice = ticker.price;
  const candleInterval = TIMEFRAME_MS[activeTimeframe];

  // 현재 시간이 마지막 캔들의 다음 구간에 해당하면 새 캔들 생성
  if (ticker.timestamp >= lastCandle.time * 1000 + candleInterval) {
    store.appendCandle(activeTimeframe, {
      time: Math.floor(ticker.timestamp / 1000 / (candleInterval / 1000))
            * (candleInterval / 1000),
      open: currentPrice,
      high: currentPrice,
      low: currentPrice,
      close: currentPrice,
      volume: 0,
    });
  } else {
    // 마지막 캔들 업데이트
    store.updateLastCandle(activeTimeframe, currentPrice);
  }
}

// Zustand store 내부:
updateLastCandle: (tf, price) => {
  set((state) => {
    const candles = [...state.candles[tf]];
    const last = { ...candles[candles.length - 1] };
    last.close = price;
    last.high = Math.max(last.high, price);
    last.low = Math.min(last.low, price);
    candles[candles.length - 1] = last;
    return { candles: { ...state.candles, [tf]: candles } };
  });
},
```

### 5.5 타임프레임 전환

```typescript
const TIMEFRAMES: Timeframe[] = ["15m", "1h", "4h", "1d"];

const TIMEFRAME_MS: Record<Timeframe, number> = {
  "15m": 15 * 60 * 1000,
  "1h": 60 * 60 * 1000,
  "4h": 4 * 60 * 60 * 1000,
  "1d": 24 * 60 * 60 * 1000,
};

// TimeframeSelector: 선택 시 캔들 데이터 fetch
async function handleTimeframeChange(tf: Timeframe) {
  const store = useCandleStore.getState();
  store.setActiveTimeframe(tf);

  // 캐시에 데이터가 있으면 즉시 표시 (stale-while-revalidate)
  if (store.candles[tf].length > 0) {
    // 이미 표시됨 — 백그라운드에서 최신 데이터 fetch
  }

  const candles = await apiClient.get<CandleData[]>(
    `/api/v1/candles/BTC-KRW/${tf}?limit=500`
  );
  store.setCandles(tf, candles);
}
```

### 5.6 크로스헤어 OHLCV 표시

```typescript
// 차트 하단에 OHLCV 텍스트 오버레이
chart.subscribeCrosshairMove((param) => {
  if (!param.time || !param.seriesData) {
    setCrosshairData(null);
    return;
  }

  const candle = param.seriesData.get(candleSeries) as CandleData;
  if (candle) {
    setCrosshairData({
      time: param.time,
      open: candle.open,
      high: candle.high,
      low: candle.low,
      close: candle.close,
    });
  }
});

// 렌더링: 차트 상단 오버레이
// O: ₩144,800,000  H: ₩145,500,000  L: ₩144,200,000  C: ₩145,230,000
```

### 5.7 P2: 기술 지표 오버레이

```typescript
// P2 구현 — EMA/BB 라인 오버레이
const ema20Series = chart.addLineSeries({
  color: "#3b82f6",         // blue
  lineWidth: 1,
  title: "EMA 20",
});

const ema50Series = chart.addLineSeries({
  color: "#f59e0b",         // amber
  lineWidth: 1,
  title: "EMA 50",
});

// BB: 3개 라인 (upper, middle, lower)
const bbUpperSeries = chart.addLineSeries({
  color: "#8b5cf680",       // violet 50% 투명
  lineWidth: 1,
  lineStyle: 2,             // dashed
});

// RSI: 별도 차트 인스턴스 (아래 패널)
const rsiChart = createChart(rsiContainer, { height: 100, ... });
const rsiSeries = rsiChart.addLineSeries({
  color: "#8b5cf6",
  lineWidth: 2,
});
// 과매수/과매도 라인
rsiChart.addLineSeries({ /* 70선 */ });
rsiChart.addLineSeries({ /* 30선 */ });
```

---

## 6. 디자인 시스템

### 6.1 컬러 팔레트

```css
/* globals.css — CSS Custom Properties */

:root {
  /* ── 배경 ── */
  --bg-primary: #ffffff;
  --bg-card: #f8f9fa;
  --bg-hover: #f0f1f3;
  --bg-elevated: #ffffff;

  /* ── 텍스트 ── */
  --text-primary: #09090b;
  --text-secondary: #71717a;
  --text-muted: #a1a1aa;

  /* ── 시맨틱 ── */
  --color-positive: #16a34a;     /* green-600 */
  --color-negative: #dc2626;     /* red-600 */
  --color-warning: #d97706;      /* amber-600 */
  --color-info: #2563eb;         /* blue-600 */
  --color-accent: #7c3aed;       /* violet-600 */

  /* ── 보더 ── */
  --border-primary: #e4e4e7;
  --border-subtle: #f4f4f5;

  /* ── 차트 전용 ── */
  --chart-candle-up: #16a34a;
  --chart-candle-down: #dc2626;
  --chart-grid: #f0f0f0;
  --chart-crosshair: #2563eb;
}

.dark {
  /* ── 배경 ── */
  --bg-primary: #0a0a0f;
  --bg-card: #12121a;
  --bg-hover: #1a1a2e;
  --bg-elevated: #16161f;

  /* ── 텍스트 ── */
  --text-primary: #e4e4e7;
  --text-secondary: #71717a;
  --text-muted: #52525b;

  /* ── 시맨틱 ── */
  --color-positive: #22c55e;     /* green-500 */
  --color-negative: #ef4444;     /* red-500 */
  --color-warning: #f59e0b;      /* amber-500 */
  --color-info: #3b82f6;         /* blue-500 */
  --color-accent: #8b5cf6;       /* violet-500 */

  /* ── 보더 ── */
  --border-primary: #27272a;
  --border-subtle: #1e1e24;

  /* ── 차트 전용 ── */
  --chart-candle-up: #22c55e;
  --chart-candle-down: #ef4444;
  --chart-grid: #1a1a2e;
  --chart-crosshair: #3b82f6;
}
```

### 6.2 타이포그래피

```css
/* 폰트 정의 */
:root {
  --font-ui: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono: "JetBrains Mono", "Fira Code", monospace;
}

/* 타이포그래피 스케일 */
.text-kpi {
  font-family: var(--font-ui);
  font-size: 1.5rem;        /* 24px */
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
}

.text-price {
  font-family: var(--font-mono);
  font-size: 0.875rem;      /* 14px */
  font-variant-numeric: tabular-nums;
}

.text-label {
  font-family: var(--font-ui);
  font-size: 0.75rem;       /* 12px */
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.text-data {
  font-family: var(--font-mono);
  font-size: 0.8125rem;     /* 13px */
  font-variant-numeric: tabular-nums;
}
```

### 6.3 숫자 포맷팅 규칙

```typescript
// lib/format.ts

export function formatKRW(value: number): string {
  // ₩145,230,000
  return `₩${Math.round(value).toLocaleString("ko-KR")}`;
}

export function formatKRWCompact(value: number): string {
  // ₩145.2M (KPI 헤더용)
  if (Math.abs(value) >= 1_000_000_000) {
    return `₩${(value / 1_000_000_000).toFixed(1)}B`;
  }
  if (Math.abs(value) >= 1_000_000) {
    return `₩${(value / 1_000_000).toFixed(1)}M`;
  }
  if (Math.abs(value) >= 1_000) {
    return `₩${(value / 1_000).toFixed(1)}K`;
  }
  return `₩${Math.round(value).toLocaleString("ko-KR")}`;
}

export function formatBTC(value: number): string {
  // 0.00123456 BTC
  return `${value.toFixed(8)} BTC`;
}

export function formatPercent(value: number, showSign = true): string {
  // +2.34% or -1.23%
  const sign = showSign && value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

export function formatPnL(value: number): string {
  // +₩450,000 or -₩123,000
  const sign = value >= 0 ? "+" : "";
  return `${sign}₩${Math.abs(Math.round(value)).toLocaleString("ko-KR")}`;
}

export function formatRelativeTime(timestamp: string | Date): string {
  // "5분 전", "2시간 전", "3일 전"
  const now = Date.now();
  const then = new Date(timestamp).getTime();
  const diffMs = now - then;
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);

  if (diffSec < 60) return `${diffSec}초 전`;
  if (diffMin < 60) return `${diffMin}분 전`;
  if (diffHour < 24) return `${diffHour}시간 전`;
  return `${diffDay}일 전`;
}

export function formatUptime(seconds: number): string {
  // "2d 3h 15m"
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const parts: string[] = [];
  if (d > 0) parts.push(`${d}d`);
  if (h > 0) parts.push(`${h}h`);
  parts.push(`${m}m`);
  return parts.join(" ");
}
```

### 6.4 PnL 색상 코딩

```typescript
// components/ui/PnLText.tsx

interface PnLTextProps {
  value: number;
  format?: "krw" | "percent";
  size?: "sm" | "md" | "lg";
}

export function PnLText({ value, format = "krw", size = "md" }: PnLTextProps) {
  const colorClass = value > 0
    ? "text-[var(--color-positive)]"
    : value < 0
    ? "text-[var(--color-negative)]"
    : "text-[var(--text-secondary)]";

  const formatted = format === "krw" ? formatPnL(value) : formatPercent(value);

  return (
    <span className={cn("font-mono tabular-nums", colorClass, sizeClasses[size])}>
      {formatted}
    </span>
  );
}
```

### 6.5 상태 색상 체계

```typescript
// lib/constants.ts

export const BOT_STATE_COLORS: Record<BotState, {
  bg: string;
  text: string;
  dot: string;
  label: string;
}> = {
  IDLE:          { bg: "bg-gray-500/10",   text: "text-gray-400",   dot: "bg-gray-400",   label: "대기" },
  SCANNING:      { bg: "bg-blue-500/10",   text: "text-blue-500",   dot: "bg-blue-500",   label: "스캔" },
  VALIDATING:    { bg: "bg-blue-500/10",   text: "text-blue-500",   dot: "bg-blue-500",   label: "검증" },
  EXECUTING:     { bg: "bg-amber-500/10",  text: "text-amber-500",  dot: "bg-amber-500",  label: "실행" },
  LOGGING:       { bg: "bg-blue-500/10",   text: "text-blue-500",   dot: "bg-blue-500",   label: "기록" },
  MONITORING:    { bg: "bg-green-500/10",  text: "text-green-500",  dot: "bg-green-500",  label: "감시" },
  PAUSED:        { bg: "bg-red-400/10",    text: "text-red-400",    dot: "bg-red-400",    label: "정지" },
  SHUTTING_DOWN: { bg: "bg-gray-500/10",   text: "text-gray-500",   dot: "bg-gray-500",   label: "종료중" },
  STARTING:      { bg: "bg-gray-500/10",   text: "text-gray-500",   dot: "bg-gray-500",   label: "시작중" },
};
```

---

## 7. 반응형 설계

### 7.1 Breakpoint 정의

```typescript
// tailwind.config.ts screens (기본값 활용)
// sm: 640px, md: 768px, lg: 1024px, xl: 1280px, 2xl: 1536px

// 대시보드 맞춤:
// Mobile:  < 768px  (md 미만)
// Tablet:  768px - 1279px (md ~ xl 미만)
// Desktop: 1280px+ (xl 이상)
```

### 7.2 메인 대시보드 (/) 레이아웃 변형

#### Desktop (1280px+)

```
┌──────────────────────────────────────────────────────────────────────┐
│  TopNav                                                              │
├──────────────────────────────────────────────────────────────────────┤
│  KPI Header (sticky, full width)                                     │
│  BTC ₩145.2M (+2.3%) │ Portfolio ₩10.45M │ PnL +₩450K │ 3 Bots 🟢  │
├────────────────────────────────────────────┬─────────────────────────┤
│                                            │  Bot Control Panel       │
│  Candlestick Chart (flex-1)               │  (w-[320px], sticky)     │
│  ┌──────────────────────────────────────┐  │  ┌───────────────────┐  │
│  │  [15m] [1h*] [4h] [1d]              │  │  │ BotCard × N       │  │
│  │                                      │  │  └───────────────────┘  │
│  │  (Lightweight Charts)               │  │                          │
│  │  height: calc(100vh - 400px)        │  │  [🔴 EMERGENCY STOP]    │
│  │  min-height: 400px                  │  │  [⚡ Close All]          │
│  └──────────────────────────────────────┘  │                          │
├────────────────────────────────────────────┴─────────────────────────┤
│  DataTabs (full width)                                               │
│  [Open Positions] [Orders] [Closed Positions]                        │
│  ┌──────────────────────────────────────────────────────────────────┐│
│  │  TanStack Table                                                  ││
│  └──────────────────────────────────────────────────────────────────┘│
├──────────────────────────────────────────────────────────────────────┤
│  MacroBar (full width)                                               │
│  F&G 11 │ BTC Dom 56% │ DXY 97.6 │ KP 1.7% │ Score 4.6/10          │
└──────────────────────────────────────────────────────────────────────┘
```

CSS 구현:

```tsx
// app/page.tsx
<div className="flex flex-col min-h-screen">
  <KPIHeader />
  <div className="flex flex-1 gap-4 px-4">
    {/* 차트: 남은 공간 전체 차지 */}
    <div className="flex-1 min-w-0">
      <CandlestickPanel />
    </div>
    {/* 봇 패널: 고정 너비, 데스크톱만 표시 */}
    <div className="hidden xl:block w-[320px] flex-shrink-0">
      <BotControlPanel />
    </div>
  </div>
  <DataTabs />
  <MacroBar />
</div>
```

#### Tablet (768px - 1279px)

```
┌────────────────────────────────────────────┐
│  TopNav                                     │
├────────────────────────────────────────────┤
│  KPI Header (sticky)                        │
│  BTC ₩145.2M │ PnL +₩450K │ 3 Bots        │
├────────────────────────────────────────────┤
│  Candlestick Chart (full width)            │
│  height: 50vh                               │
├────────────────────────────────────────────┤
│  Bot Control Panel (full width, 수평 카드)  │
│  ┌──────┐ ┌──────┐ ┌──────┐              │
│  │003   │ │004   │ │005   │              │
│  └──────┘ └──────┘ └──────┘              │
│  [🔴 EMERGENCY STOP]                       │
├────────────────────────────────────────────┤
│  DataTabs (full width)                      │
├────────────────────────────────────────────┤
│  MacroBar                                   │
└────────────────────────────────────────────┘
```

#### Mobile (< 768px)

```
┌────────────────────────┐
│  TopNav (간소화)         │
├────────────────────────┤
│  KPI (축약, 2줄)         │
│  BTC ₩145.2M (+2.3%)   │
│  PnL +₩450K  3 Bots    │
├────────────────────────┤
│  Tab Bar:               │
│  [📊 Chart][🤖 Bots][📋]│
├────────────────────────┤
│  (선택된 탭 콘텐츠)       │
│                         │
│  Chart 탭:              │
│  ┌─────────────────┐   │
│  │ LW Charts        │   │
│  │ height: 300px    │   │
│  │ (터치 지원)       │   │
│  └─────────────────┘   │
│                         │
│  Bots 탭:              │
│  BotCard × N (세로 배치) │
│  [🔴 EMERGENCY STOP]   │
│                         │
│  Orders 탭:            │
│  DataTabs (수평 스크롤)  │
│                         │
├────────────────────────┤
│  Mobile Bottom Nav      │
│  [Dashboard][Analytics] │
└────────────────────────┘
```

### 7.3 모바일 전용 고려사항

| 항목 | 데스크톱 | 모바일 |
|------|---------|--------|
| KPI | 4개 전체 표시 | 핵심 3개 (Portfolio 생략) |
| 차트 높이 | calc(100vh - 400px) | 300px 고정 |
| 봇 카드 배치 | 우측 패널 세로 | 탭 콘텐츠 세로 |
| 테이블 | 전체 컬럼 | 핵심 컬럼 + 수평 스크롤 |
| Emergency Stop | 봇 패널 하단 | Bots 탭 최상단 (즉시 접근) |
| 매크로 바 | 하단 full width | 숨김 (Analytics에서 확인) |
| 차트 인터랙션 | 마우스 줌/패닝 | 터치 핀치 줌, 스와이프 패닝 |

### 7.4 터치 제스처 지원

```typescript
// LWChartWrapper — Lightweight Charts 터치 기본 지원
// 추가 설정:
chart.applyOptions({
  handleScroll: {
    mouseWheel: true,
    pressedMouseMove: true,
    horzTouchDrag: true,         // 수평 스와이프 → 패닝
    vertTouchDrag: false,        // 수직 스와이프 → 페이지 스크롤 (간섭 방지)
  },
  handleScale: {
    axisPressedMouseMove: true,
    mouseWheel: true,
    pinch: true,                 // 터치 핀치 줌
  },
});
```

---

## 8. API 연동 설계

### 8.1 API 클라이언트 구조

```typescript
// lib/api-client.ts

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class ApiClient {
  private baseUrl: string;
  private headers: Record<string, string>;

  constructor() {
    this.baseUrl = API_BASE_URL;
    this.headers = {
      "Content-Type": "application/json",
      "X-API-Key": process.env.NEXT_PUBLIC_API_KEY || "",
    };
  }

  async get<T>(path: string, params?: Record<string, string>): Promise<T> {
    const url = new URL(path, this.baseUrl);
    if (params) {
      Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
    }

    const res = await fetch(url.toString(), {
      headers: this.headers,
      next: { revalidate: 5 },     // Next.js ISR 5초 캐시
    });

    if (!res.ok) {
      throw new ApiError(res.status, await res.text());
    }

    return res.json();
  }

  async post<T>(path: string, body?: unknown): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: this.headers,
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!res.ok) {
      throw new ApiError(res.status, await res.text());
    }

    return res.json();
  }
}

export const apiClient = new ApiClient();
```

### 8.2 데이터 Fetch 훅 패턴

SWR이나 React Query 대신 **간단한 커스텀 훅 + Zustand** 조합:

```typescript
// lib/hooks/useBots.ts

export function useBots() {
  const { bots, setBots, setLoading, setError } = useBotStore();

  // 초기 로드
  useEffect(() => {
    let cancelled = false;

    async function fetchBots() {
      setLoading(true);
      try {
        const data = await apiClient.get<BotStatus[]>("/api/v1/bots");
        if (!cancelled) {
          setBots(data);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to fetch bots");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchBots();
    return () => { cancelled = true; };
  }, []);

  // 봇 제어 mutation
  const startBot = useCallback(async (strategyId: string) => {
    return apiClient.post<BotControlResponse>(`/api/v1/bots/${strategyId}/start`);
  }, []);

  const stopBot = useCallback(async (strategyId: string) => {
    return apiClient.post<BotControlResponse>(`/api/v1/bots/${strategyId}/stop`);
  }, []);

  const pauseBot = useCallback(async (strategyId: string) => {
    return apiClient.post<BotControlResponse>(`/api/v1/bots/${strategyId}/pause`);
  }, []);

  const resumeBot = useCallback(async (strategyId: string) => {
    return apiClient.post<BotControlResponse>(`/api/v1/bots/${strategyId}/resume`);
  }, []);

  const emergencyStop = useCallback(async (closePositions: boolean) => {
    return apiClient.post<BotControlResponse>("/api/v1/bots/emergency-stop", {
      close_positions: closePositions,
    });
  }, []);

  return { bots, startBot, stopBot, pauseBot, resumeBot, emergencyStop };
}
```

### 8.3 REST API 엔드포인트 매핑 (bot-developer 인터페이스)

| 대시보드 컴포넌트 | API 엔드포인트 (아키텍처 설계서 기준) | 호출 시점 |
|------------------|--------------------------------------|----------|
| KPIHeader | `GET /api/v1/bots` | 초기 로드 + WS bots.status |
| KPIHeader (가격) | WS `ticker.BTC-KRW` | 실시간 |
| CandlestickPanel | `GET /api/v1/candles/{symbol}/{tf}?limit=500` | 초기 + 타임프레임 변경 |
| CandlestickPanel (마커) | `GET /api/v1/orders?status=filled&limit=200` | 초기 로드 |
| BotControlPanel | `GET /api/v1/bots` | 초기 + WS |
| BotCard (제어) | `POST /api/v1/bots/{id}/{action}` | 버튼 클릭 |
| EmergencyStop | `POST /api/v1/bots/{id}/emergency-exit` | 버튼 클릭 |
| OpenPositionsTab | `GET /api/v1/positions?status=open` | 초기 + WS positions.* |
| OrderHistoryTab | `GET /api/v1/orders?page=1&size=20` | 초기 + 페이지네이션 |
| ClosedPositionsTab | `GET /api/v1/positions?status=closed&page=1&size=20` | 초기 + 페이지네이션 |
| MacroBar | `GET /api/v1/macro/latest` | 초기 (30분 캐시) |
| EquityCurve | `GET /api/v1/pnl/daily?strategy_id=all&days=30` | Analytics 진입 |
| StrategyComparison | `GET /api/v1/pnl/summary` | Analytics 진입 |
| SignalTable | `GET /api/v1/signals?strategy_id=X&page=1&size=50` | Analytics 진입 |

### 8.4 WebSocket 채널 매핑

| 채널 | Zustand Store | UI 컴포넌트 | 업데이트 빈도 |
|------|-------------|------------|-------------|
| `ticker.BTC-KRW` | useTickerStore | PriceTicker, LWChartWrapper | ~100ms |
| `bots.status` | useBotStore | BotCard[], KPIHeader | 상태 변화 시 |
| `orders.*` | useOrderStore | OrderHistoryTab + toast | 이벤트 |
| `positions.*` | useOrderStore | OpenPositionsTab | 이벤트 |
| `risk.*` (P2) | - | RiskPanel | 변화 시 |
| `alerts` (P2) | useAlertStore | NotificationBell | 이벤트 |

### 8.5 OpenAPI → TypeScript 타입 자동생성

```bash
# scripts/generate_api_types.sh

#!/bin/bash
set -e

API_URL="${API_URL:-http://localhost:8000}"
OUTPUT="dashboard/src/types/api.ts"

echo "Fetching OpenAPI schema from ${API_URL}/openapi.json..."
curl -s "${API_URL}/openapi.json" -o /tmp/openapi.json

echo "Generating TypeScript types..."
npx openapi-typescript /tmp/openapi.json -o "${OUTPUT}"

echo "Types generated at ${OUTPUT}"
```

```json
// dashboard/package.json (scripts)
{
  "scripts": {
    "generate:types": "../scripts/generate_api_types.sh",
    "dev": "next dev",
    "build": "next build",
    "lint": "next lint"
  }
}
```

**CI 타입 검증**:

```yaml
# .github/workflows/frontend.yml
- name: Generate API types
  run: pnpm run generate:types
- name: Check for uncommitted type changes
  run: git diff --exit-code dashboard/src/types/api.ts
```

### 8.6 에러 처리 패턴

```typescript
// API 에러 타입
class ApiError extends Error {
  constructor(
    public status: number,
    public body: string,
  ) {
    super(`API Error ${status}: ${body}`);
  }
}

// 컴포넌트 레벨 에러 처리
function BotControlPanel() {
  const { bots, pauseBot } = useBots();

  async function handlePause(strategyId: string) {
    try {
      await pauseBot(strategyId);
      toast.success(`${strategyId} 일시정지됨`);
    } catch (err) {
      if (err instanceof ApiError) {
        switch (err.status) {
          case 409:
            toast.error("이미 일시정지 상태입니다.");
            break;
          case 503:
            toast.error("서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요.");
            break;
          default:
            toast.error(`오류 발생: ${err.body}`);
        }
      }
    }
  }
}

// WS 연결 에러 → ConnectionStatus 컴포넌트에 표시
function ConnectionStatus() {
  const { status, reconnectAttempt } = useWebSocket();

  if (status === "connected") {
    return <StatusDot color="green" label="연결됨" />;
  }
  if (status === "reconnecting") {
    return <StatusDot color="amber" label={`재연결 중 (${reconnectAttempt})`} pulse />;
  }
  return <StatusDot color="red" label="연결 끊김" />;
}
```

---

## 부록 A: 파일 목록 (생성 순서)

### Sprint 1 (Week 1-2): 기반 설정

| # | 파일 | 설명 |
|---|------|------|
| 1 | `dashboard/package.json` | pnpm, Next.js 15, 의존성 |
| 2 | `dashboard/next.config.ts` | standalone output, env |
| 3 | `dashboard/tailwind.config.ts` | 커스텀 색상, 폰트 |
| 4 | `dashboard/src/app/globals.css` | CSS 변수, 다크/라이트 토큰 |
| 5 | `dashboard/src/app/layout.tsx` | RootLayout, ThemeProvider |
| 6 | `dashboard/src/lib/format.ts` | 숫자/시간 포맷 유틸 |
| 7 | `dashboard/src/lib/constants.ts` | 색상, 상태 매핑 |
| 8 | `dashboard/src/lib/api-client.ts` | fetch 래퍼 |
| 9 | `dashboard/src/lib/ws-client.ts` | WebSocket 클라이언트 |
| 10 | `dashboard/src/stores/useTickerStore.ts` | 실시간 가격 |
| 11 | `dashboard/src/stores/useBotStore.ts` | 봇 상태 |
| 12 | `dashboard/src/stores/useOrderStore.ts` | 주문/포지션 |
| 13 | `dashboard/src/stores/useCandleStore.ts` | 캔들 데이터 |
| 14 | `dashboard/src/components/ui/NumberDisplay.tsx` | 숫자 포맷 |
| 15 | `dashboard/src/components/ui/PnLText.tsx` | PnL 색상 텍스트 |
| 16 | `dashboard/src/components/ui/StatusDot.tsx` | 상태 인디케이터 |
| 17 | `dashboard/src/components/ui/ConfirmDialog.tsx` | 확인 다이얼로그 |
| 18 | `dashboard/src/components/layout/TopNav.tsx` | 상단 네비게이션 |
| 19 | `dashboard/src/components/layout/ConnectionStatus.tsx` | WS 상태 |
| 20 | `dashboard/src/components/dashboard/KPIHeader.tsx` | P0-1 |

### Sprint 2 (Week 3-4): P0 완성

| # | 파일 | 설명 |
|---|------|------|
| 21 | `dashboard/src/components/dashboard/LWChartWrapper.tsx` | LW Charts 래퍼 |
| 22 | `dashboard/src/components/dashboard/CandlestickPanel.tsx` | P0-2 차트 |
| 23 | `dashboard/src/components/dashboard/TimeframeSelector.tsx` | TF 전환 |
| 24 | `dashboard/src/components/dashboard/BotCard.tsx` | 봇 카드 |
| 25 | `dashboard/src/components/dashboard/BotStatusBadge.tsx` | 상태 배지 |
| 26 | `dashboard/src/components/dashboard/ControlButtons.tsx` | 제어 버튼 |
| 27 | `dashboard/src/components/dashboard/BotControlPanel.tsx` | P0-3 |
| 28 | `dashboard/src/components/dashboard/EmergencyStopButton.tsx` | 긴급 중지 |
| 29 | `dashboard/src/components/dashboard/CloseAllButton.tsx` | 전체 청산 |
| 30 | `dashboard/src/components/ui/DataTable.tsx` | TanStack 래퍼 |
| 31 | `dashboard/src/components/dashboard/DataTabs.tsx` | P0-4 탭 |
| 32 | `dashboard/src/components/dashboard/OpenPositionsTab.tsx` | 열린 포지션 |
| 33 | `dashboard/src/components/dashboard/OrderHistoryTab.tsx` | 주문 이력 |
| 34 | `dashboard/src/components/dashboard/ClosedPositionsTab.tsx` | 마감 포지션 |
| 35 | `dashboard/src/app/page.tsx` | 메인 대시보드 조합 |
| 36 | `dashboard/src/components/layout/MobileBottomNav.tsx` | 모바일 하단 |

### Sprint 3 (Week 5-6): P1 분석

| # | 파일 | 설명 |
|---|------|------|
| 37 | `dashboard/src/components/analytics/PeriodSelector.tsx` | 기간 선택 |
| 38 | `dashboard/src/components/analytics/MetricCards.tsx` | 성과 카드 |
| 39 | `dashboard/src/components/analytics/EquityCurve.tsx` | Recharts |
| 40 | `dashboard/src/components/analytics/DrawdownChart.tsx` | Recharts |
| 41 | `dashboard/src/components/analytics/DailyPnLBars.tsx` | Recharts |
| 42 | `dashboard/src/components/analytics/ComparisonTable.tsx` | 전략 비교 |
| 43 | `dashboard/src/components/analytics/OverlayChart.tsx` | 오버레이 |
| 44 | `dashboard/src/components/analytics/SignalHeatmap.tsx` | 히트맵 |
| 45 | `dashboard/src/components/analytics/SubScoreRadar.tsx` | 레이더 |
| 46 | `dashboard/src/components/analytics/SignalTable.tsx` | 시그널 테이블 |
| 47 | `dashboard/src/components/dashboard/MacroBar.tsx` | P1-4 매크로 |
| 48 | `dashboard/src/app/analytics/page.tsx` | 분석 페이지 조합 |

---

## 부록 B: 성능 목표

| 지표 | 목표 | 측정 방법 |
|------|------|----------|
| 초기 페이지 로딩 (/) | < 2초 (LCP) | Lighthouse |
| 캔들 500개 렌더링 | < 1초 | Performance.now() |
| 타임프레임 전환 | < 500ms | User-perceived |
| WS 틱 → UI 반영 | < 500ms | timestamp diff |
| 봇 제어 버튼 → 피드백 | < 1초 | User-perceived |
| 테이블 50행 렌더링 | < 200ms | React Profiler |
| 메모리 사용량 | < 150MB | Chrome DevTools |
| 번들 크기 (gzip) | < 300KB (JS) | next build |

---

## 부록 C: 접근성 요구사항

| 항목 | 구현 |
|------|------|
| 색상 대비 | WCAG AA (4.5:1 텍스트, 3:1 UI 요소) |
| PnL 색상 외 보조 신호 | 양수: ↑ 화살표, 음수: ↓ 화살표 (색맹 대응) |
| 키보드 네비게이션 | Tab 순서: KPI → Chart → Bot Panel → Tables |
| 스크린 리더 | 차트 대체 텍스트: "BTC/KRW 1시간 캔들스틱 차트, 현재가 ₩145,230,000" |
| Emergency Stop | `aria-label="긴급 전체 중지"`, 키보드 단축키 Ctrl+Shift+E |
| 테이블 | `role="table"`, 정렬 상태 `aria-sort` |
| 토스트 알림 | `role="alert"`, 자동 읽기 |
