# Gap Detector Memory -- traderj Dashboard

## Project Structure
- Design docs: `/Users/whoana/DEV/workspaces/claude-code/traderj/docs/`
  - Main design: `round4-dashboard-design.md` (Sections 1-8)
  - Roadmap: `round5-dashboard-roadmap.md` (Sprint 1-4 + checklist)
  - Requirements: `round2-dashboard-requirements.md` (P0/P1/P2)
- Implementation: `/Users/whoana/DEV/workspaces/claude-code/traderj/dashboard/src/`
- Analysis doc: `docs/03-analysis/traderj.analysis.md` (v4.0)

## Key Findings (2026-03-03, Post-Iteration 2)
- Overall Match Rate: 91% weighted / 84% unweighted (was 88%/80%)
- 94 total design items tracked, 76 implemented
- P0: 100%, P1: 60%, P2: 79%, Infra: 93%
- 90% THRESHOLD REACHED

## Resolved in Iteration 1 (10 items)
- EmergencyStopButton + CloseAllButton implemented (P0 safety)
- BotControlPanel wired to real API (startBot/stopBot/pauseBot/resumeBot)
- WS ticker -> candle store connected
- closeAllPositions() API wrapper added
- A11y: aria-live, role="alertdialog", scope="col" added
- Perf: React.memo on BotCard

## Resolved in Iteration 2 (6 items)
- Bug: WS ticker high/low logic fixed (Math.max/min vs existing candle)
- PageShell layout wrapper component added
- SparkLine mini chart (Recharts) added
- Perf: CSS contain on CandlestickPanel chart div
- Perf: React.memo on DataTable
- A11y: role="toolbar", arrow key nav, roving tabindex on timeframe selector

## Remaining Gaps (10 items, all P1/P2)
1. Analytics page: 7 Recharts chart components missing (P1)
2. MacroBar + MobileBottomNav (P1 layout)
3. BotStatus model minimal vs design (missing paper_balance, position, signal)
4. New candle creation at time boundary not implemented
5. Candle auto-trim (max 2000) not implemented
6. ThresholdSweepHeatmap, NotificationBell, useAlertStore (P2)

## Architecture Decisions (intentional divergences from design)
- components/dashboard/ split into chart/, bot/, data/ subfolders
- hooks/ at top-level instead of lib/hooks/
- Indicators calculated client-side (lib/indicators.ts) not server API
- WebSocket via hook pattern (useRealtimeData) not Context Provider
- DataTable is simple HTML + React.memo, not TanStack Table v8
- updateLastCandle accepts Partial<CandleData> not raw price number
