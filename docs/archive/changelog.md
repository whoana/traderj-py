# TraderJ Changelog

All notable changes to the TraderJ BTC/KRW Automated Trading Bot project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.1.0] - 2026-03-18

### Added
- **P0-1**: `async set_stop_loss()` and `async set_take_profit()` with database persistence
  - Positions now correctly save SL/TP values to database on each assignment
  - Prevents SL/TP data loss on engine restart
- **P0-2**: Event handlers for SL/TP trigger → automatic liquidation
  - `_on_stop_loss_triggered()` executes market SELL on stop loss trigger
  - `_on_take_profit_triggered()` executes market SELL on take profit trigger
  - Event subscriptions wired in bootstrap for immediate activation
- **P0-3**: Real API integration for macro economic indicators
  - BTC dominance: CoinGecko API (`/api/v3/global`)
  - Funding rate: Binance Futures API (`/fapi/v1/fundingRate`)
  - Graceful error handling with fallback to neutral defaults
- New unit tests for SL/TP DB persistence and event-to-order execution (4 tests)
- Structured logging for SL/TP liquidation events

### Changed
- `PositionManager.set_stop_loss()`: Converted from sync to async function
- `PositionManager.set_take_profit()`: Converted from sync to async function
- `TradingLoop._execute_buy()`: Now awaits SL/TP assignment to ensure DB persistence
- `bootstrap._wire_event_subscriptions()`: Added `trading_loop` parameter for event handler registration

### Fixed
- **Critical**: Stop loss / take profit values were lost on engine restart (DB save missing)
- **Critical**: SL/TP triggers did not execute liquidation orders (event handlers not wired)
- **High**: Macro economic data was hardcoded placeholder values instead of real feeds

### Security
- External API calls use public endpoints (no authentication required)
- No sensitive data changes
- Graceful degradation prevents API failures from crashing trading engine

### Testing
- All 467 unit tests passing (100% pass rate)
- New P0 functionality covered by 4 additional tests
- Integration verified via gap analysis (100% design match rate)

### Documentation
- Completion report: [`docs/04-report/features/traderj-improvement.report.md`](./features/traderj-improvement.report.md)
- Design spec: [`docs/02-design/features/traderj-improvement.design.md`](../02-design/features/traderj-improvement.design.md)
- Gap analysis: [`docs/03-analysis/traderj-improvement.analysis.md`](../03-analysis/traderj-improvement.analysis.md)

---

## [1.0.0] - 2026-03-03

### Initial Release
- Complete BTC/KRW automated trading bot with:
  - **Engine**: Async Python event-driven core
  - **API Server**: FastAPI with REST endpoints
  - **Dashboard**: Next.js React frontend with real-time charts
  - **Database**: SQLite with 14 tables (TimescaleDB-compatible)
- 7 strategy presets (DCA, Mean Reversion, Momentum, etc.)
- Paper trading mode for backtesting
- Historical candle data management
- Position and order management
- 262 unit tests (100% pass rate)
- Docker Compose stack (6 containers)
- Comprehensive PDCA documentation

---

## Planned Features (Next Cycles)

### P1 - Dashboard Analytics
- [ ] DailyPnL bar chart (realized + unrealized)
- [ ] Drawdown visualization (MDD tracking)
- [ ] MacroBar footer (Fear&Greed, BTC dominance, funding rate, Kimchi premium)
- [ ] RSI sub-panel (technical indicator overlay)
- [ ] Backtest API endpoints

### P2 - Infrastructure
- [ ] Code quality configuration (ruff.toml, mypy.ini)
- [ ] Integration test CI/CD workflow
- [ ] Prometheus/Grafana monitoring setup

### Future
- [ ] Real trading (live exchange connection)
- [ ] Mobile app
- [ ] Multi-asset support
- [ ] Portfolio optimization algorithms
