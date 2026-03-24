# Round 5: 대시보드 구현 로드맵

**작성일**: 2026-03-03
**작성자**: dashboard-designer
**기반**: Round 3 TDR (Rev.1), Round 4 대시보드 상세 설계서, Round 4 아키텍처 설계서, Round 4 전략 엔진 설계서
**기술 스택**: Next.js 15 (App Router) + TailwindCSS + shadcn/ui + Zustand + Lightweight Charts 4.x + Recharts + TanStack Table v8

---

## 목차

1. [Sprint별 UI 구현 순서](#1-sprint별-ui-구현-순서)
2. [디자인 시스템 완성도 기준](#2-디자인-시스템-완성도-기준)
3. [접근성 목표](#3-접근성-목표)
4. [성능 목표](#4-성능-목표)
5. [API 의존성](#5-api-의존성)
6. [실시간 데이터 흐름](#6-실시간-데이터-흐름)
7. [리스크 & 완화 전략](#7-리스크--완화-전략)

---

## 1. Sprint별 UI 구현 순서

### 1.1 전체 타임라인 개요

```
Sprint 1 (Week 1-2)   Sprint 2 (Week 3-4)   Sprint 3 (Week 5-6)   Sprint 4 (Week 7-8)
 디자인 시스템 기반       핵심 페이지 (P0)       고급 기능 (P1+P2)     최적화 / 폴리싱
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ 프로젝트 초기화   │  │ 캔들스틱 차트    │  │ Analytics 페이지 │  │ Lighthouse 최적화│
│ 디자인 토큰       │  │ 봇 관리 패널    │  │ 기술 지표 오버레이│  │ 번들 사이즈 최적화│
│ 기본 UI 컴포넌트  │  │ 데이터 테이블    │  │ 매크로 바         │  │ E2E 테스트       │
│ WS/API 클라이언트 │  │ 메인 대시보드    │  │ 설정 페이지 (P2)  │  │ 접근성 감사       │
│ Zustand 스토어    │  │ 반응형 레이아웃   │  │ 백테스트 뷰어(P2) │  │ 크로스 브라우저    │
│ KPI 헤더          │  │ 실시간 데이터 통합│  │ 알림 시스템 (P2)  │  │ PWA / 모바일 UX  │
└─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────────┘
    API 불필요           API 필수 (P0)         API 필수 (P1+P2)      API 안정화 필요
```

### 1.2 Sprint 1: 디자인 시스템 기반 (Week 1-2)

**목표**: API 서버 없이 독립적으로 구현 가능한 프론트엔드 기반 구축. Mock 데이터로 UI 개발.

#### Week 1: 프로젝트 초기화 + 디자인 토큰

| # | 파일 | 설명 | 선행 조건 |
|---|------|------|----------|
| 1 | `dashboard/package.json` | pnpm + Next.js 15 + 의존성 정의 | 없음 |
| 2 | `dashboard/next.config.ts` | standalone output, env, images 설정 | 없음 |
| 3 | `dashboard/tailwind.config.ts` | 커스텀 색상, 폰트, breakpoint 확장 | 없음 |
| 4 | `dashboard/src/app/globals.css` | CSS Custom Properties: 라이트/다크 토큰 38개 | 없음 |
| 5 | `dashboard/src/app/layout.tsx` | RootLayout: ThemeProvider, WebSocketProvider, Toaster | 없음 |
| 6 | `dashboard/src/app/loading.tsx` | 전역 로딩 스켈레톤 | 없음 |
| 7 | `dashboard/src/app/error.tsx` | 전역 에러 바운더리 | 없음 |
| 8 | `dashboard/src/lib/format.ts` | 숫자/날짜 포맷 유틸 (formatKRW, formatBTC, formatPercent 등 7개) | 없음 |
| 9 | `dashboard/src/lib/constants.ts` | BOT_STATE_COLORS, TIMEFRAMES, TIMEFRAME_MS | 없음 |
| 10 | `dashboard/src/types/chart.ts` | 차트 전용 타입 (CandleData, TradeMarker, Timeframe) | 없음 |

#### Week 2: 기본 UI 컴포넌트 + 인프라

| # | 파일 | 설명 | 선행 조건 |
|---|------|------|----------|
| 11 | `dashboard/src/components/ui/NumberDisplay.tsx` | KRW/BTC/% 포맷 + tabular-nums | #8 |
| 12 | `dashboard/src/components/ui/PnLText.tsx` | 양수(green)/음수(red)/제로(gray) 색상 텍스트 | #4, #8 |
| 13 | `dashboard/src/components/ui/StatusDot.tsx` | 상태 인디케이터 원형 (pulse 애니메이션 포함) | #4 |
| 14 | `dashboard/src/components/ui/ConfirmDialog.tsx` | shadcn/ui AlertDialog 래퍼 (3초 카운트다운 포함) | 없음 |
| 15 | `dashboard/src/components/ui/SkeletonCard.tsx` | 로딩 스켈레톤 (shimmer 애니메이션) | 없음 |
| 16 | `dashboard/src/components/ui/EmptyState.tsx` | 빈 상태 표시 (아이콘 + 메시지 + 액션) | 없음 |
| 17 | `dashboard/src/lib/api-client.ts` | fetch 래퍼 (base URL, X-API-Key, 에러 처리) | 없음 |
| 18 | `dashboard/src/lib/ws-client.ts` | WebSocket 클라이언트 (재연결, 하트비트, 채널 관리) | 없음 |
| 19 | `dashboard/src/stores/useTickerStore.ts` | 실시간 가격 스토어 | 없음 |
| 20 | `dashboard/src/stores/useBotStore.ts` | 봇 상태 스토어 | 없음 |
| 21 | `dashboard/src/stores/useOrderStore.ts` | 주문/포지션 스토어 | 없음 |
| 22 | `dashboard/src/stores/useCandleStore.ts` | 캔들 데이터 스토어 (타임프레임별 캐시) | 없음 |
| 23 | `dashboard/src/components/layout/TopNav.tsx` | 상단 네비게이션 (로고, NavLinks, ThemeToggle) | #4, #13 |
| 24 | `dashboard/src/components/layout/ConnectionStatus.tsx` | WS 상태 인디케이터 (connected/reconnecting/disconnected) | #13, #18 |
| 25 | `dashboard/src/components/dashboard/KPIHeader.tsx` | 핵심 KPI 상단 바 (BTC가격, 포트폴리오, PnL, 활성봇) | #11, #12 |

**Sprint 1 산출물**:
- 디자인 토큰 38개 (CSS Custom Properties) 라이트/다크 테마 완비
- 공유 UI 컴포넌트 6종 (NumberDisplay, PnLText, StatusDot, ConfirmDialog, SkeletonCard, EmptyState)
- WebSocket/API 인프라 (클라이언트 + Zustand 스토어 4개)
- 레이아웃 셸 (TopNav + ConnectionStatus + KPIHeader)
- Storybook 스토리 10개 이상

**검증 기준**: Mock 데이터로 KPI 헤더가 다크/라이트 테마에서 정상 렌더링, WS 클라이언트가 재연결 로직 테스트 통과

---

### 1.3 Sprint 2: 핵심 페이지 — P0 완성 (Week 3-4)

**목표**: 메인 대시보드(/) 완전 동작. API 서버 연동 필수.

**선행 조건**: bot-developer 팀의 P0 API 엔드포인트 7개 완성 (아래 §5 참조)

#### Week 3: 차트 + 봇 관리

| # | 파일 | 설명 | API 의존성 |
|---|------|------|----------|
| 26 | `dashboard/src/components/dashboard/LWChartWrapper.tsx` | Lightweight Charts 래퍼 (다크/라이트 테마 전환) | 없음 (로컬 데이터) |
| 27 | `dashboard/src/components/dashboard/CandlestickPanel.tsx` | 차트 컨테이너 (캔들 + 볼륨 + 거래 마커 + OHLCV 크로스헤어) | `GET /candles/{symbol}/{tf}` |
| 28 | `dashboard/src/components/dashboard/TimeframeSelector.tsx` | [15m][1h][4h][1d] 버튼 그룹 + stale-while-revalidate | `GET /candles/{symbol}/{tf}` |
| 29 | `dashboard/src/components/dashboard/BotCard.tsx` | 개별 봇 카드 (상태배지, PnL, 포지션 정보, 제어 버튼) | `GET /bots` |
| 30 | `dashboard/src/components/dashboard/BotStatusBadge.tsx` | 9개 상태별 색상 + 아이콘 + pulse 애니메이션 | 없음 |
| 31 | `dashboard/src/components/dashboard/ControlButtons.tsx` | Start/Pause/Resume/Stop 상태별 활성화 매트릭스 | `POST /bots/{id}/{action}` |
| 32 | `dashboard/src/components/dashboard/BotControlPanel.tsx` | 봇 카드 목록 + 긴급 중지/전체 청산 버튼 | `GET /bots` |
| 33 | `dashboard/src/components/dashboard/EmergencyStopButton.tsx` | 긴급 중지 (3초 카운트다운 + 확인 다이얼로그) | `POST /bots/emergency-stop` |
| 34 | `dashboard/src/components/dashboard/CloseAllButton.tsx` | 전체 청산 (체크박스 확인 필수) | `POST /positions/close-all` |

#### Week 4: 데이터 테이블 + 메인 대시보드 조합

| # | 파일 | 설명 | API 의존성 |
|---|------|------|----------|
| 35 | `dashboard/src/components/ui/DataTable.tsx` | TanStack Table v8 래퍼 (가상 스크롤, 정렬, 필터) | 없음 |
| 36 | `dashboard/src/components/dashboard/DataTabs.tsx` | [Open Positions][Orders][Closed Positions] 탭 컨테이너 | 없음 |
| 37 | `dashboard/src/components/dashboard/OpenPositionsTab.tsx` | 열린 포지션 테이블 (실시간 uPnL 업데이트) | `GET /positions?status=open`, WS `positions.*` |
| 38 | `dashboard/src/components/dashboard/OrderHistoryTab.tsx` | 주문 이력 테이블 (페이지네이션) | `GET /orders?page=1&size=20` |
| 39 | `dashboard/src/components/dashboard/ClosedPositionsTab.tsx` | 마감 포지션 테이블 (페이지네이션) | `GET /positions?status=closed` |
| 40 | `dashboard/src/app/page.tsx` | 메인 대시보드 조합 (KPI + Chart + BotPanel + DataTabs) | 전체 |
| 41 | `dashboard/src/components/layout/MobileBottomNav.tsx` | 모바일 하단 탭 네비게이션 | 없음 |
| 42 | `dashboard/src/components/layout/PageShell.tsx` | 페이지 래퍼 (max-width, padding, responsive) | 없음 |
| 43 | `dashboard/src/lib/hooks/useWebSocket.ts` | WS 연결 관리 Context (구독/해지/상태) | WS `/ws/v1/stream` |
| 44 | `dashboard/src/lib/hooks/useBots.ts` | 봇 데이터 fetch + mutation 훅 | `GET /bots`, `POST /bots/{id}/*` |
| 45 | `dashboard/src/lib/hooks/useCandles.ts` | 캔들 데이터 fetch 훅 | `GET /candles/{symbol}/{tf}` |

**Sprint 2 산출물**:
- 메인 대시보드 (`/`) P0 4개 섹션 완전 동작: KPI 헤더, 캔들스틱 차트, 봇 관리 패널, 데이터 테이블
- 실시간 데이터: WS ticker → 차트 마지막 캔들 업데이트, WS bots.status → 봇 상태 반영
- 봇 제어: Start/Pause/Resume/Stop + Emergency Stop + Close All
- Optimistic Update: 봇 제어 버튼 즉시 반영 → 서버 확인 후 최종 확정 (롤백 포함)
- 반응형: Desktop(1280px+), Tablet(768px-1279px), Mobile(<768px) 3단계

**검증 기준**: Docker 환경에서 API 서버 연동, WS 재연결 10회 이상 안정, Emergency Stop 3초 카운트다운 동작, LCP < 2s

---

### 1.4 Sprint 3: 고급 기능 — P1 + P2 (Week 5-6)

**목표**: Analytics 페이지, 매크로 바, 기술 지표 오버레이. P2 설정/백테스트 기초.

**선행 조건**: bot-developer 팀의 P1 API 엔드포인트 8개 + P2 API 5개 (아래 §5 참조)

#### Week 5: Analytics 페이지 (P1)

| # | 파일 | 설명 | API 의존성 |
|---|------|------|----------|
| 46 | `dashboard/src/components/analytics/PeriodSelector.tsx` | 기간 선택 [7D][30D][90D][ALL] 버튼 그룹 | 없음 |
| 47 | `dashboard/src/components/analytics/MetricCards.tsx` | 성과 지표 카드 그리드 (Sharpe, Sortino, MDD, Win Rate 등) | `GET /analytics/pnl` |
| 48 | `dashboard/src/components/analytics/EquityCurve.tsx` | 누적 자산 곡선 (Recharts AreaChart) | `GET /pnl/daily` |
| 49 | `dashboard/src/components/analytics/DrawdownChart.tsx` | 고점 대비 하락률 (Recharts AreaChart, 음수 영역 red) | `GET /pnl/daily` |
| 50 | `dashboard/src/components/analytics/DailyPnLBars.tsx` | 일별 PnL 막대 차트 (양수=green, 음수=red) | `GET /pnl/daily` |
| 51 | `dashboard/src/components/analytics/ComparisonTable.tsx` | 전략별 지표 비교 테이블 | `GET /analytics/compare` |
| 52 | `dashboard/src/components/analytics/OverlayChart.tsx` | Equity Curve 오버레이 (멀티 전략) | `GET /pnl/daily` |
| 53 | `dashboard/src/components/analytics/SignalHeatmap.tsx` | 시간대별 시그널 스코어 히트맵 (CSS Grid 기반) | `GET /signals` |
| 54 | `dashboard/src/components/analytics/SubScoreRadar.tsx` | 서브스코어 레이더 차트 (Recharts RadarChart) | `GET /signals` |
| 55 | `dashboard/src/components/analytics/SignalTable.tsx` | 시그널 이력 테이블 (score 컴포넌트 분해 표시) | `GET /signals` |
| 56 | `dashboard/src/app/analytics/page.tsx` | Analytics 페이지 조합 | 전체 |
| 57 | `dashboard/src/lib/hooks/useAnalytics.ts` | 분석 데이터 fetch 훅 | `GET /analytics/*`, `GET /pnl/*` |

#### Week 6: 매크로 바 + P2 기초 + 기술 지표

| # | 파일 | 설명 | API 의존성 |
|---|------|------|----------|
| 58 | `dashboard/src/components/dashboard/MacroBar.tsx` | 매크로 하단 바 (F&G, BTC Dom, DXY, 김프, Score) | `GET /macro/latest` |
| 59 | LWChartWrapper 확장: EMA 오버레이 | EMA 20/50 라인 시리즈 추가 | `GET /candles` (지표 포함) |
| 60 | LWChartWrapper 확장: BB 오버레이 | BB upper/mid/lower 라인 (dashed) | `GET /candles` (지표 포함) |
| 61 | RSI 별도 차트 패널 | 하단 100px RSI 차트 (70/30 기준선) | `GET /candles` (지표 포함) |
| 62 | `dashboard/src/components/settings/StrategyConfigForm.tsx` | 전략 파라미터 폼 (React Hook Form + Zod) | `GET /bots/{id}/config`, `PUT /bots/{id}/config` |
| 63 | `dashboard/src/components/settings/AlertRulesManager.tsx` | 알림 규칙 관리 (CRUD) | `GET /alerts/rules`, P2 API |
| 64 | `dashboard/src/app/settings/page.tsx` | Settings 페이지 조합 (P2) | 전체 |
| 65 | `dashboard/src/app/backtest/page.tsx` | Backtest 뷰어 스켈레톤 (P2) | `GET /backtest/results` |
| 66 | `dashboard/src/stores/useNotificationStore.ts` | 알림 스토어 (P2) | WS `notifications` |

**Sprint 3 산출물**:
- Analytics 페이지 (`/analytics`) 완전 동작: 성과 지표, Equity Curve, Drawdown, Daily PnL, 전략 비교, 시그널 히트맵
- 매크로 바: Fear & Greed, BTC Dominance, DXY, 김치 프리미엄, 종합 점수
- 기술 지표 오버레이: EMA 20/50, Bollinger Bands, RSI 하단 패널
- Settings 페이지 기초: 전략 파라미터 수정, 알림 규칙 관리 (P2)
- Backtest 뷰어 스켈레톤 (P2)

**검증 기준**: Recharts 6종 차트 정상 렌더링, 30일 PnL 데이터 로드 < 500ms, 기술 지표 오버레이 차트 동기화

---

### 1.5 Sprint 4: 최적화 / 폴리싱 (Week 7-8)

**목표**: 성능 최적화, 접근성 감사, E2E 테스트, 크로스 브라우저 검증, 모바일 UX 폴리싱.

#### Week 7: 성능 최적화 + 테스트

| # | 작업 | 설명 | 목표 |
|---|------|------|------|
| 67 | 번들 분석 + 코드 스플리팅 | `@next/bundle-analyzer`로 분석, 라우트별 dynamic import | JS gzip < 300KB |
| 68 | LW Charts lazy loading | 차트 라이브러리 dynamic import (`next/dynamic`) | 초기 번들 -50KB |
| 69 | Recharts tree-shaking 최적화 | 사용 컴포넌트만 named import | Recharts 번들 -30KB |
| 70 | 이미지/폰트 최적화 | `next/font`로 Inter/JetBrains Mono 로드, 폰트 서브셋 | FOUT 제거 |
| 71 | DataTable 가상 스크롤 검증 | 1000행+ 테이블에서 TanStack virtualizer 성능 테스트 | 렌더 < 50ms |
| 72 | WS 메시지 쓰로틀링 | ticker 100ms+ → UI 업데이트 16ms(60fps) 제한 | requestAnimationFrame 활용 |
| 73 | React Profiler 분석 | 불필요한 리렌더 식별 + Zustand selector 최적화 | KPI 리렌더 < 5ms |
| 74 | E2E 테스트 (Playwright) | 핵심 플로우: 대시보드 로드, 봇 제어, Analytics 진입, 테마 전환 | 커버리지 80% |

#### Week 8: 접근성 + 크로스 브라우저 + 모바일 폴리싱

| # | 작업 | 설명 | 목표 |
|---|------|------|------|
| 75 | WCAG AA 접근성 감사 | axe-core 자동 검사 + 수동 스크린 리더 테스트 | 위반 0건 |
| 76 | 키보드 네비게이션 검증 | Tab 순서: KPI → Chart → BotPanel → Tables | 전체 기능 접근 |
| 77 | 차트 대체 텍스트 | `aria-label`로 차트 요약 (현재가, 변동) | 스크린 리더 지원 |
| 78 | Emergency Stop 단축키 | `Ctrl+Shift+E` → Emergency Stop 다이얼로그 | 키보드 긴급 접근 |
| 79 | 크로스 브라우저 테스트 | Chrome, Firefox, Safari, Edge (최신 2 버전) | 주요 기능 동작 |
| 80 | 모바일 터치 UX 폴리싱 | 터치 타겟 48px, 스와이프 제스처, 안전 영역 대응 | iOS Safari + Android Chrome |
| 81 | PWA manifest + 오프라인 배너 | service worker (캐시 전략: network-first), install prompt | 오프라인 알림 표시 |
| 82 | Docker 빌드 최적화 | 멀티스테이지 빌드, .dockerignore, standalone output | 이미지 < 200MB |

**Sprint 4 산출물**:
- Lighthouse Performance 스코어 ≥ 90
- 접근성 위반 0건 (axe-core)
- E2E 테스트 커버리지 80%+
- 크로스 브라우저 호환 확인서
- Docker 프로덕션 빌드 최적화

---

## 2. 디자인 시스템 완성도 기준

### 2.1 디자인 토큰 (CSS Custom Properties)

| 카테고리 | 토큰 수 | 완성 기준 |
|---------|--------|----------|
| 배경 (Background) | 4 | `--bg-primary`, `--bg-card`, `--bg-hover`, `--bg-elevated` |
| 텍스트 (Text) | 3 | `--text-primary`, `--text-secondary`, `--text-muted` |
| 시맨틱 (Semantic) | 5 | `--color-positive`, `--color-negative`, `--color-warning`, `--color-info`, `--color-accent` |
| 보더 (Border) | 2 | `--border-primary`, `--border-subtle` |
| 차트 (Chart) | 4 | `--chart-candle-up`, `--chart-candle-down`, `--chart-grid`, `--chart-crosshair` |
| **총계** | **18** (라이트) + **18** (다크) = **36개** | Sprint 1 Week 1 완성 |

**완성 기준**: 라이트/다크 테마 전환 시 모든 토큰이 즉시 반영 (CSS 변수 기반, JS 재계산 없음)

### 2.2 타이포그래피

| 클래스 | 용도 | 폰트 | 사이즈 |
|--------|------|------|--------|
| `.text-kpi` | KPI 대형 숫자 | Inter Bold | 24px, tabular-nums |
| `.text-price` | 가격 표시 | JetBrains Mono | 14px, tabular-nums |
| `.text-label` | 라벨/캡션 | Inter Regular | 12px, uppercase, letter-spacing 0.05em |
| `.text-data` | 테이블 데이터 | JetBrains Mono | 13px, tabular-nums |

### 2.3 컴포넌트 라이브러리

| 컴포넌트 | 소스 | Sprint | Storybook |
|---------|------|--------|-----------|
| NumberDisplay | 커스텀 | 1 | 필수 |
| PnLText | 커스텀 | 1 | 필수 |
| StatusDot | 커스텀 | 1 | 필수 |
| ConfirmDialog | shadcn AlertDialog 래퍼 | 1 | 필수 |
| SkeletonCard | 커스텀 | 1 | 필수 |
| EmptyState | 커스텀 | 1 | 필수 |
| DataTable | TanStack Table 래퍼 | 2 | 필수 |
| SparkLine | Recharts 래퍼 | 3 | 필수 |
| Button, Input, Select, Tabs, Badge, Card | shadcn/ui | 1-2 | shadcn 기본 |

### 2.4 Storybook 커버리지 기준

| Sprint | 대상 | 최소 스토리 수 | 커버리지 목표 |
|--------|------|--------------|-------------|
| Sprint 1 | 공유 UI 컴포넌트 6종 + 레이아웃 3종 | 15개 | 100% |
| Sprint 2 | 대시보드 컴포넌트 15종 | 20개 | 80% |
| Sprint 3 | Analytics 컴포넌트 10종 | 12개 | 70% |
| Sprint 4 | 통합 스토리 + 접근성 테스트 | 5개 | 유지 |
| **누적** | **전체 커스텀 컴포넌트** | **52개+** | **80%+** |

**Storybook 설정**:
- `@storybook/nextjs` 프레임워크 어댑터
- `@storybook/addon-a11y` (접근성 자동 검사)
- `@storybook/addon-themes` (다크/라이트 토글)
- Mock Service Worker (MSW) 연동: API 의존 컴포넌트 스토리

---

## 3. 접근성 목표

### 3.1 WCAG 2.1 AA 준수 항목

| 기준 | 요구사항 | 구현 방법 | 검증 Sprint |
|------|---------|----------|------------|
| **1.1.1 Non-text Content** | 차트에 대체 텍스트 | `aria-label="BTC/KRW {tf} 캔들스틱 차트, 현재가 ₩{price}"` | Sprint 4 |
| **1.3.1 Info and Relationships** | 테이블 시맨틱 구조 | TanStack Table `role="table"`, `<th>` + `scope` | Sprint 2 |
| **1.4.3 Contrast** | 텍스트 4.5:1, UI 3:1 | 디자인 토큰 검증 (다크/라이트 모두) | Sprint 1 |
| **1.4.11 Non-text Contrast** | UI 컴포넌트 3:1 | StatusDot, BotStatusBadge 대비율 검증 | Sprint 2 |
| **2.1.1 Keyboard** | 모든 기능 키보드 접근 | `tabIndex`, `onKeyDown`, focus trap (Dialog) | Sprint 2-4 |
| **2.4.3 Focus Order** | 논리적 Tab 순서 | KPI → Chart → BotPanel → Tables → MacroBar | Sprint 2 |
| **2.4.7 Focus Visible** | 포커스 인디케이터 표시 | `focus-visible:ring-2 ring-blue-500` (TailwindCSS) | Sprint 1 |
| **4.1.2 Name, Role, Value** | ARIA 속성 완비 | 동적 상태: `aria-sort`, `aria-pressed`, `aria-live` | Sprint 2-3 |

### 3.2 키보드 네비게이션

| 단축키 | 기능 | 구현 Sprint |
|--------|------|------------|
| `Tab` / `Shift+Tab` | 순방향/역방향 포커스 이동 | Sprint 1 |
| `Enter` / `Space` | 버튼/링크 활성화 | Sprint 1 (네이티브) |
| `Escape` | 다이얼로그/드롭다운 닫기 | Sprint 2 |
| `Ctrl+Shift+E` | Emergency Stop 다이얼로그 열기 | Sprint 4 |
| `←` / `→` | 타임프레임 전환 (차트 포커스 시) | Sprint 4 |
| `1-4` 숫자키 | 탭 전환 (DataTabs 포커스 시) | Sprint 4 |

### 3.3 스크린 리더 지원

| 컴포넌트 | aria 구현 |
|---------|----------|
| PriceTicker | `aria-live="polite"` — 가격 변동 시 읽기 |
| BotStatusBadge | `aria-label="{strategy_id} 상태: {state_label}"` |
| EmergencyStopButton | `aria-label="긴급 전체 중지"`, `role="button"` |
| DataTable 정렬 | `aria-sort="ascending"` / `"descending"` / `"none"` |
| Toast 알림 | `role="alert"`, sonner 기본 지원 |
| ConfirmDialog | `role="alertdialog"`, `aria-describedby` |

### 3.4 색맹 대응

PnL 양수/음수 구분에서 색상만 의존하지 않는 보조 신호:

| 구분 | 색상 | 보조 신호 |
|------|------|----------|
| 양수 | green | `+` 접두사 + `↑` 화살표 |
| 음수 | red | `-` 접두사 + `↓` 화살표 |
| 제로 | gray | `0` 또는 `-` 표시 |

---

## 4. 성능 목표

### 4.1 Core Web Vitals

| 지표 | 목표 | 측정 방법 | 달성 Sprint |
|------|------|----------|------------|
| **LCP** (Largest Contentful Paint) | < 2.0s | Lighthouse lab mode | Sprint 4 |
| **FID** (First Input Delay) / **INP** | < 100ms | Chrome UX Report 또는 web-vitals | Sprint 4 |
| **CLS** (Cumulative Layout Shift) | < 0.1 | Lighthouse | Sprint 2 (스켈레톤으로 방지) |

### 4.2 번들 사이즈 목표

| 대상 | 목표 (gzip) | 전략 |
|------|-----------|------|
| **전체 JS** | < 300KB | 코드 스플리팅, tree-shaking |
| **초기 로드 JS** (/) | < 150KB | Lightweight Charts dynamic import |
| **Lightweight Charts** | ~50KB | 라우트별 lazy load |
| **Recharts** | ~70KB | Analytics 페이지에서만 로드 |
| **TanStack Table** | ~30KB | 라우트별 lazy load |
| **CSS** | < 50KB | TailwindCSS purge |

### 4.3 런타임 성능

| 시나리오 | 목표 | 측정 |
|---------|------|------|
| 캔들 500개 초기 렌더링 | < 1,000ms | `performance.now()` |
| 타임프레임 전환 (캐시 히트) | < 200ms | User-perceived |
| 타임프레임 전환 (캐시 미스) | < 500ms | API 호출 포함 |
| WS 틱 → UI 반영 | < 500ms | timestamp diff |
| 봇 제어 → 시각 피드백 | < 1,000ms | Optimistic UI 기준 |
| DataTable 50행 렌더링 | < 200ms | React Profiler |
| DataTable 1000행 가상 스크롤 | < 50ms/frame | 60fps 유지 |
| 메모리 사용량 (8시간 운영) | < 150MB | Chrome DevTools Memory |
| WS 메시지 처리 (ticker 100ms) | < 16ms/frame | requestAnimationFrame 스로틀링 |

### 4.4 최적화 전략

```
성능 최적화 계층:

1. 네트워크 계층
   ├── Next.js standalone output (서버 사이드)
   ├── stale-while-revalidate 캐시 (REST API)
   ├── WebSocket 바이너리 메시지 (P2 고려)
   └── API 응답 gzip 압축

2. 렌더링 계층
   ├── Zustand selector → 세밀한 구독 (리렌더 최소화)
   ├── React.memo: BotCard, DataTable Row
   ├── useMemo: 파생 상태 (totalPnL, portfolioValue)
   ├── requestAnimationFrame: ticker → chart 업데이트 스로틀링
   └── CSS containment: `contain: layout style paint`

3. 데이터 계층
   ├── 캔들 데이터: 타임프레임별 메모리 캐시 (useCandleStore)
   ├── 오래된 캔들 자동 trim (최대 2000개 유지)
   ├── WS 메시지 배치: 100ms 내 다수 메시지 → 단일 state 업데이트
   └── Zustand middleware: immer 미사용 (shallow copy 직접 관리)

4. 빌드 계층
   ├── next/dynamic: 차트 라이브러리 지연 로딩
   ├── Recharts named import (tree-shaking)
   ├── next/font: 폰트 최적화 (서브셋 + swap)
   └── @next/bundle-analyzer: 번들 분석 CI 연동
```

---

## 5. API 의존성

### 5.1 Sprint별 필요 API 엔드포인트

#### Sprint 1 (Week 1-2): API 불필요

Sprint 1은 Mock 데이터로 UI를 개발하므로 백엔드 API가 필요하지 않습니다. MSW(Mock Service Worker)로 API 응답을 시뮬레이션합니다.

#### Sprint 2 (Week 3-4): P0 핵심 API — 7개 REST + 4개 WS

> **bot-developer 팀 선행 필요** — Sprint 2 시작 전 아래 API가 완성되어야 합니다.

| # | Method | Endpoint | 용도 | 컴포넌트 |
|---|--------|----------|------|---------|
| 1 | GET | `/api/v1/health` | 시스템 상태 확인 | ConnectionStatus |
| 2 | GET | `/api/v1/bots` | 전체 봇 상태 | KPIHeader, BotControlPanel |
| 3 | GET | `/api/v1/candles/{symbol}/{tf}?limit=500` | 캔들 데이터 | CandlestickPanel |
| 4 | GET | `/api/v1/positions?status=open` | 열린 포지션 | OpenPositionsTab |
| 5 | GET | `/api/v1/orders?page=1&size=20` | 주문 이력 | OrderHistoryTab |
| 6 | POST | `/api/v1/bots/{strategy_id}/{action}` | 봇 제어 (start/stop/pause/resume) | ControlButtons |
| 7 | POST | `/api/v1/bots/emergency-stop` | 긴급 전체 중지 | EmergencyStopButton |

| # | WS 채널 | 용도 | 업데이트 빈도 |
|---|---------|------|-------------|
| W1 | `ticker` | 실시간 BTC 가격 | ~1/sec |
| W2 | `bot_status` | 봇 상태 변화 | on change |
| W3 | `orders` | 주문 체결 이벤트 | on trade |
| W4 | `positions` | 포지션 변화 이벤트 | on change |

#### Sprint 3 (Week 5-6): P1 분석 API — 8개 REST + 2개 WS

| # | Method | Endpoint | 용도 | 컴포넌트 |
|---|--------|----------|------|---------|
| 8 | GET | `/api/v1/pnl/daily?strategy_id=all&days=30` | 일일 PnL | EquityCurve, DrawdownChart, DailyPnLBars |
| 9 | GET | `/api/v1/pnl/summary` | 전략별 성과 요약 | MetricCards, ComparisonTable |
| 10 | GET | `/api/v1/analytics/pnl?period=30d` | PnL 분석 (Sharpe, Sortino 등) | MetricCards |
| 11 | GET | `/api/v1/analytics/compare` | 전략 비교 | StrategyComparison |
| 12 | GET | `/api/v1/signals?strategy_id=X&page=1&size=50` | 시그널 이력 | SignalTable, SignalHeatmap |
| 13 | GET | `/api/v1/macro/latest` | 최신 매크로 데이터 | MacroBar |
| 14 | GET | `/api/v1/positions?status=closed&page=1&size=20` | 마감 포지션 | ClosedPositionsTab |
| 15 | POST | `/api/v1/positions/close-all` | 전 포지션 청산 | CloseAllButton |

| # | WS 채널 | 용도 | 업데이트 빈도 |
|---|---------|------|-------------|
| W5 | `signals` | 시그널 생성 이벤트 | per eval cycle |
| W6 | `alerts` | 리스크 알림 이벤트 | on alert |

#### Sprint 3 (Week 6): P2 설정/백테스트 API — 5개 REST

| # | Method | Endpoint | 용도 | 컴포넌트 |
|---|--------|----------|------|---------|
| 16 | GET | `/api/v1/bots/{id}/config` | 전략 설정 조회 | StrategyConfigForm |
| 17 | PUT | `/api/v1/bots/{id}/config` | 전략 설정 수정 | StrategyConfigForm |
| 18 | GET | `/api/v1/risk/{strategy_id}` | 리스크 상태 | RiskPanel (P2) |
| 19 | GET | `/api/v1/alerts/rules` | 알림 규칙 목록 | AlertRulesManager |
| 20 | GET | `/api/v1/backtest/results` | 백테스트 결과 | Backtest 뷰어 |

### 5.2 API 의존성 타임라인

```
                    Week 1    Week 2    Week 3    Week 4    Week 5    Week 6    Week 7    Week 8
Dashboard Sprint:   ┣━━ Sprint 1 ━━┫  ┣━━ Sprint 2 ━━┫  ┣━━ Sprint 3 ━━┫  ┣━━ Sprint 4 ━━┫
                    (Mock 데이터)      (P0 API 필수)     (P1+P2 API 필수)  (안정화)

API 필요 시점:       │                 │                  │
                    └─ API 불필요      └─ P0 7개 REST    └─ P1 8개 REST
                       (MSW Mock)         4개 WS 채널        P2 5개 REST
                                                             2개 WS 채널

bot-developer 팀:   ┣━━ Phase 0-1 ━━┫  ┣━━ Phase 2-3 ━━┫  ┣━━ Phase 4 ━━━┫
                    (shared, DB,        (Engine, API       (분석/설정 API)
                     EventBus)           P0 REST+WS)
```

### 5.3 OpenAPI 타입 동기화

```bash
# API 서버가 실행 중일 때 TypeScript 타입 자동 생성
pnpm run generate:types
# → dashboard/src/types/api.ts 생성

# CI에서 스키마 변경 감지
git diff --exit-code dashboard/src/types/api.ts
```

**타입 동기화 주기**: API 스키마 변경 시 자동 재생성 (CI 워크플로우)

---

## 6. 실시간 데이터 흐름

### 6.1 WebSocket 연동 아키텍처

```
거래소 (Upbit)                  Engine                API Server            Dashboard
┌──────────┐              ┌──────────────┐       ┌──────────────┐     ┌──────────────┐
│ WebSocket │─ ticker ──→ │ MarketTick   │──→───→│ WS Bridge    │═══→ │ WS Client    │
│ Stream    │             │ Event        │       │              │     │              │
└──────────┘              │              │       │ channel:     │     │ useTickerStore│
                          │ EventBus     │       │  "ticker"    │     │  .updateTicker│
                          │              │       │              │     │              │
   OHLCV Scheduler ──→───│ OHLCVUpdate  │       │ channel:     │     │ useCandleStore│
                          │ Event        │       │  N/A (REST)  │     │  .updateLast  │
                          │              │       │              │     │              │
                          │ SignalEvent  │──→───→│ channel:     │═══→ │ toast 알림    │
                          │              │       │  "signals"   │     │              │
                          │ OrderFilled  │──→───→│ channel:     │═══→ │ useOrderStore │
                          │ Event        │       │  "orders"    │     │  .addOrder    │
                          │              │       │              │     │              │
                          │ BotState     │──→───→│ channel:     │═══→ │ useBotStore   │
                          │ ChangeEvent  │       │ "bot_status" │     │  .updateBot   │
                          │              │       │              │     │              │
                          │ Position     │──→───→│ channel:     │═══→ │ useOrderStore │
                          │ Events       │       │ "positions"  │     │ .updatePosition│
                          │              │       │              │     │              │
                          │ RiskAlert    │──→───→│ channel:     │═══→ │ toast + 알림벨│
                          │ Event        │       │  "alerts"    │     │ (P2)          │
                          └──────────────┘       └──────────────┘     └──────────────┘
```

### 6.2 채널별 업데이트 주기 및 처리

| 채널 | 서버 발행 빈도 | 클라이언트 처리 주기 | 스로틀링 | Zustand 업데이트 |
|------|-------------|-------------------|---------|----------------|
| `ticker` | ~100ms (거래소 원본) | 1/sec 스로틀링 | `requestAnimationFrame` | `useTickerStore.updateTicker` |
| `bot_status` | on change (불규칙) | 즉시 반영 | 없음 | `useBotStore.updateBot` |
| `orders` | on trade (불규칙) | 즉시 반영 | 없음 | `useOrderStore.addOrder` + toast |
| `positions` | on change (불규칙) | 즉시 반영 | 없음 | `useOrderStore.updatePosition` |
| `signals` | per eval cycle (~4h) | 즉시 반영 | 없음 | toast 알림 |
| `alerts` | on alert (드물게) | 즉시 반영 | 없음 | toast.warning + 알림벨 |

### 6.3 WebSocket 연결 관리

```typescript
// WebSocket 재연결 설정
const WS_RECONNECT_CONFIG = {
  maxRetries: Infinity,       // 무한 재시도 (대시보드는 항상 연결)
  baseDelay: 1000,            // 1초
  maxDelay: 30000,            // 최대 30초
  backoffMultiplier: 2,       // 지수 백오프
  jitter: true,               // ±20% 랜덤 변동
};

// 하트비트 설정
const WS_HEARTBEAT_CONFIG = {
  interval: 30000,            // 30초마다 ping
  timeout: 10000,             // pong 10초 미수신 → 연결 끊김 판정
};
```

**연결 생명주기**:
1. **앱 초기화** → WebSocketProvider 마운트 → `connect(WS_BASE_URL)`
2. **연결 성공** → 기본 채널 자동 구독 (`ticker`, `bot_status`, `orders`, `positions`)
3. **메시지 수신** → 채널별 Zustand store 업데이트
4. **하트비트** → 30초 간격 ping/pong
5. **연결 끊김** → 지수 백오프 재연결 + ConnectionStatus "재연결 중" 표시
6. **재연결 성공** → 구독 목록 재전송 + ConnectionStatus "연결됨" 표시
7. **페이지 이동** → 채널 참조 카운팅으로 불필요한 채널 자동 해지

### 6.4 차트 실시간 업데이트 흐름

```
WS ticker 메시지 수신 (매 ~100ms)
    │
    ▼
requestAnimationFrame 스로틀링 (16ms 단위)
    │
    ▼
현재 타임프레임의 마지막 캔들 시간 확인
    │
    ├─ (같은 구간) → useCandleStore.updateLastCandle(tf, price)
    │                  → close = price
    │                  → high = max(high, price)
    │                  → low = min(low, price)
    │                  → LW Charts candleSeries.update(lastCandle)
    │
    └─ (새 구간)   → useCandleStore.appendCandle(tf, newCandle)
                      → LW Charts candleSeries.update(newCandle)
```

### 6.5 Optimistic Update 패턴 (봇 제어)

```
버튼 클릭 (예: Pause)
    │
    ├─ 1. Zustand 즉시 업데이트: state = "PAUSED", _optimistic = true
    │     → UI 즉시 반영 (배지 색상 변경, 버튼 비활성화)
    │
    ├─ 2. API 호출: POST /api/v1/bots/{id}/pause
    │
    ├─ 성공 → toast.success("일시정지됨")
    │         → WS bot_status 이벤트로 최종 확정 (_optimistic = false)
    │
    └─ 실패 → Zustand 롤백: state = previousState
              → toast.error("일시정지 실패: {message}")
```

---

## 7. 리스크 & 완화 전략

### 7.1 대용량 데이터 렌더링 성능

| 리스크 | 영향도 | 발생 확률 | 완화 전략 |
|--------|--------|----------|----------|
| 캔들 2000개+ 렌더링 지연 | 높 | 중 | Lightweight Charts는 Canvas 기반으로 2000개도 < 1초. 2000개 초과 시 서버에서 집계(연속 집계 활용) |
| 테이블 1000행+ 렌더링 지연 | 중 | 중 | TanStack Table `@tanstack/virtual` 가상 스크롤 적용. 한 번에 50행만 DOM 렌더링 |
| WS ticker 100ms → UI 지터 | 중 | 높 | `requestAnimationFrame`으로 16ms 스로틀링. 100ms 내 다수 틱은 마지막 값만 반영 |
| Recharts 대형 데이터셋 (365일 PnL) | 중 | 중 | 데이터 포인트 > 365개 시 서버에서 주간 집계. 클라이언트에서 데시메이션(decimation) 적용 |
| 메모리 누수 (8시간+ 연속 운영) | 높 | 중 | 캔들 스토어 자동 trim (최대 2000개/타임프레임). WS 연결 cleanup (useEffect cleanup). Chrome DevTools Memory Profiler Sprint 4 검증 |

### 7.2 브라우저 호환성

| 리스크 | 영향도 | 발생 확률 | 완화 전략 |
|--------|--------|----------|----------|
| Safari WebSocket 타임아웃 차이 | 중 | 중 | Safari에서 WS idle timeout이 더 짧을 수 있음. 하트비트 20초로 단축 시 테스트. `visibilitychange` 이벤트로 백그라운드 탭 감지 → 재연결 |
| Lightweight Charts Safari 호환 | 낮 | 낮 | LW Charts 4.x는 Safari 15+ 공식 지원. Canvas 2D API 기반으로 호환성 문제 드묾 |
| CSS Custom Properties IE 미지원 | 해당없음 | 없음 | IE 미지원 (타겟: 최신 2 버전 Chrome/Firefox/Safari/Edge) |
| `font-variant-numeric: tabular-nums` 미지원 | 낮 | 낮 | JetBrains Mono 자체가 tabular 기본. 폰트 폴백으로 해결 |
| Next.js 15 App Router + Safari | 중 | 낮 | Next.js 15 캐나리 기능(PPR 등) 미사용. 안정 기능만 활용 |

**지원 브라우저 매트릭스**:

| 브라우저 | 최소 버전 | 테스트 환경 |
|---------|----------|-----------|
| Chrome | 120+ | macOS, Windows |
| Firefox | 120+ | macOS, Windows |
| Safari | 17+ | macOS, iOS |
| Edge | 120+ | Windows |
| Chrome (Android) | 120+ | Android 13+ |
| Safari (iOS) | 17+ | iOS 17+ |

### 7.3 모바일 대응

| 리스크 | 영향도 | 발생 확률 | 완화 전략 |
|--------|--------|----------|----------|
| 차트 터치 제스처와 페이지 스크롤 충돌 | 높 | 높 | LW Charts `vertTouchDrag: false` (수직 스와이프 → 페이지 스크롤). `horzTouchDrag: true` (수평 → 차트 패닝). `pinch: true` (핀치 줌) |
| 모바일 화면에서 테이블 가독성 | 중 | 높 | 핵심 컬럼(전략ID, PnL, 상태)만 표시 + 수평 스크롤. 행 클릭 → 상세 시트(Bottom Sheet) |
| 모바일 Emergency Stop 접근성 | 높 | 중 | Bots 탭 최상단에 Emergency Stop 고정 (즉시 접근). 터치 타겟 48px 이상 |
| 소형 화면에서 KPI 정보 손실 | 중 | 높 | 4개 KPI → 3개로 축약 (Portfolio 생략). 2줄 레이아웃 |
| 모바일 WS 연결 불안정 (네트워크 전환) | 중 | 중 | `online`/`offline` 이벤트 감지 → 즉시 재연결 시도. `visibilitychange`로 백그라운드 탭 복귀 시 재연결 |

### 7.4 API 서버 의존성 리스크

| 리스크 | 영향도 | 발생 확률 | 완화 전략 |
|--------|--------|----------|----------|
| API 서버 개발 지연 → 대시보드 블로킹 | 높 | 중 | Sprint 1 전체를 API 독립적으로 설계. MSW Mock으로 Sprint 2 초반까지 개발 가능. OpenAPI 스펙 선행 합의 |
| API 스키마 변경 → 타입 불일치 | 중 | 중 | `openapi-typescript` 자동 생성 + CI 스키마 diff 검사. Zod 런타임 검증 (WS 메시지) |
| WS 연결 실패 → 실시간 데이터 중단 | 높 | 낮 | 무한 재시도 (Infinity maxRetries). 재연결 중 "마지막 업데이트: N초 전" 표시. 30초 이상 끊김 시 REST 폴백 fetch |
| API 응답 지연 → UX 저하 | 중 | 중 | 모든 데이터 로드에 스켈레톤 표시. stale-while-revalidate: 캐시된 데이터 즉시 표시 + 백그라운드 갱신 |

### 7.5 통합 리스크 매트릭스

| ID | 리스크 | 영향도 | 확률 | Sprint | 완화 |
|----|--------|--------|------|--------|------|
| D-R1 | WS ticker → UI 지터 | 중 | 높 | 2, 4 | rAF 스로틀링 |
| D-R2 | 모바일 차트-스크롤 충돌 | 높 | 높 | 2, 4 | vertTouchDrag: false |
| D-R3 | API 개발 지연 → 블로킹 | 높 | 중 | 2 | MSW Mock + 선행 스펙 합의 |
| D-R4 | 메모리 누수 (장시간 운영) | 높 | 중 | 4 | 캔들 trim + cleanup + Memory Profiler |
| D-R5 | 테이블 대량 데이터 렌더링 | 중 | 중 | 2, 4 | TanStack virtual 스크롤 |
| D-R6 | Safari WS 호환성 | 중 | 중 | 4 | 하트비트 단축 + visibilitychange |
| D-R7 | 모바일 Emergency Stop 접근성 | 높 | 중 | 2 | Bots 탭 최상단 고정 |
| D-R8 | Recharts 대형 데이터셋 | 중 | 중 | 3, 4 | 서버 집계 + 데시메이션 |
| D-R9 | API 스키마 변경 → 타입 불일치 | 중 | 중 | 2-4 | openapi-typescript + CI 검사 |
| D-R10 | 번들 사이즈 초과 (>300KB) | 중 | 낮 | 4 | dynamic import + tree-shaking |

---

## 부록: Sprint 완료 체크리스트

### Sprint 1 완료 기준
- [ ] 디자인 토큰 36개 (라이트 18 + 다크 18) 정의 완료
- [ ] 공유 UI 컴포넌트 6종 Storybook 스토리 작성
- [ ] WS 클라이언트 재연결 테스트 통과 (10회 연속)
- [ ] Zustand 스토어 4개 단위 테스트
- [ ] KPI 헤더 다크/라이트 테마 전환 정상
- [ ] Storybook 15+ 스토리

### Sprint 2 완료 기준
- [ ] 메인 대시보드 (`/`) P0 완전 동작
- [ ] Docker 환경에서 API 서버 연동 확인
- [ ] 봇 제어 전체 플로우 동작 (Start → Pause → Resume → Stop)
- [ ] Emergency Stop 3초 카운트다운 동작
- [ ] 반응형 3단계 (Desktop/Tablet/Mobile) 확인
- [ ] CLS < 0.1 (스켈레톤 적용)
- [ ] LCP < 2.5s (최적화 전)

### Sprint 3 완료 기준
- [ ] Analytics 페이지 (`/analytics`) Recharts 6종 차트 정상
- [ ] 30일 PnL 데이터 로드 < 500ms
- [ ] 기술 지표 오버레이 (EMA, BB, RSI) 차트 동기화
- [ ] MacroBar 5개 지표 표시
- [ ] Settings 페이지 전략 파라미터 수정 동작
- [ ] Storybook 누적 47+ 스토리

### Sprint 4 완료 기준
- [ ] Lighthouse Performance ≥ 90
- [ ] JS 번들 gzip < 300KB
- [ ] axe-core 접근성 위반 0건
- [ ] E2E 테스트 (Playwright) 핵심 플로우 4개 통과
- [ ] 크로스 브라우저 4종 (Chrome/Firefox/Safari/Edge) 확인
- [ ] 메모리 사용량 < 150MB (8시간 시뮬레이션)
- [ ] Docker 이미지 < 200MB

---

> **문서 상태**: Draft — Round 5 최초 작성
> **다음 단계**: bot-developer 팀과 API 엔드포인트 완성 시점 조율, Sprint 2 시작 전 OpenAPI 스펙 선행 합의
