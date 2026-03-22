# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

TraderJ — single-user BTC/KRW automated trading bot. Async Python engine with multi-strategy support, regime-based strategy switching, and paper/live trading modes. Deployed on Fly.io (Tokyo/nrt).

## Commands

```bash
# Run all engine tests (467 tests, asyncio_mode=auto)
.venv/bin/python -m pytest engine/tests/ -v

# Run a single test file or test
.venv/bin/python -m pytest engine/tests/unit/test_signal.py -v
.venv/bin/python -m pytest engine/tests/unit/test_signal.py::test_name -v

# Lint & format (ruff, line-length=120, py313)
ruff check shared/ engine/ api/
ruff check --fix shared/ engine/ api/
ruff format shared/ engine/ api/

# Type check
cd engine && mypy engine/ --strict

# Paper trading (local)
.venv/bin/python -m scripts.run_paper --ticks 100

# Backtest all strategies
.venv/bin/python -m scripts.run_backtest_all
```

## Architecture

### Three packages, one shared layer

- **`shared/`** — Protocol definitions (`protocols.py`), data models (`models.py`), enums (`enums.py`), events (`events.py`). All other packages depend on this.
- **`engine/`** — Trading engine: signal generation, order execution, position management, risk management, regime detection. Poetry-managed.
- **`api/`** — FastAPI server exposing engine data via REST + WebSocket. Poetry-managed.
- **`dashboard/`** — Next.js monitoring UI. pnpm-managed.

### Protocol-based abstraction

All core interfaces are `@runtime_checkable` Protocol classes in `shared/protocols.py`:
- `DataStore` — async CRUD for candles, signals, orders, positions, risk state, paper balances
- `ExchangeClient` — OHLCV fetching, ticker, order creation/cancellation
- `Notifier` — Telegram trade/risk alerts

Two DataStore backends: `SqliteDataStore` (default) and `PostgresDataStore`. Selected by `DB_TYPE` env var via factory in `engine/data/__init__.py`.

### Component wiring

`engine/bootstrap.py` wires everything into `AppOrchestrator` (DI container + lifecycle manager in `engine/app.py`):

**Shared (one instance):** DataStore, EventBus, Exchange, Scheduler, IPCServer
**Per-strategy (one per strategy_id):** SignalGenerator, CircuitBreaker, OrderManager, PositionManager, RiskManager, StateMachine, TradingLoop

Multi-strategy: components registered as `"name:STR-001"`. Single strategy: plain names for backward compat.

### Event-driven pipeline

`EventBus` (async pub/sub) connects components. Key events (frozen dataclasses in `shared/events.py`):
- `OrderFilledEvent` → PositionManager, RiskManager
- `PositionClosedEvent` → RiskManager, TradingLoop (deferred regime switch)
- `StopLossTriggeredEvent` / `TakeProfitTriggeredEvent` → TradingLoop
- `MarketTickEvent` → PositionManager (SL/TP/trailing stop checks)

### Trading loop tick cycle

`TradingLoop.tick()` in `engine/loop/trading_loop.py`:
1. Fetch OHLCV (1h, 4h, 1d) from exchange
2. Detect regime (ADX + BB Width → 4 types) → auto-switch strategy preset if needed
3. Generate signal (8-stage pipeline in `SignalGenerator`)
4. State machine transitions (SCANNING → VALIDATING → EXECUTING → LOGGING → MONITORING)
5. Risk validation → position sizing (ATR-based, 5-20%)
6. Order execution → event publishing → DB persistence

### Strategy system

7 presets in `engine/strategy/presets.py` (STR-001 through STR-006 + default). Each preset configures: scoring mode (TREND_FOLLOW/HYBRID), entry mode (WEIGHTED/MAJORITY), timeframe weights, buy/sell thresholds, daily gate, macro weight.

Regime detection maps 4 market states to presets. `RegimeSwitchManager` handles debounce (3 consecutive), cooldown (60 min), and hybrid position close on switch (immediate close vs SL tightening based on loss threshold).

### Position constraints

One position per strategy_id. Position sizing uses ATR-based volatility scaling. SL/TP set at entry, persisted to DB, checked on every `MarketTickEvent`.

## Configuration

pydantic-settings based (`engine/config/settings.py`), all env var driven:
- `DB_TYPE` (sqlite|postgres), `DB_SQLITE_PATH`, `DB_URL`
- `EXCHANGE_API_KEY`, `EXCHANGE_API_SECRET`
- `TRADING_MODE` (paper|live|signal_only), `TRADING_STRATEGY_ID`, `TRADING_STRATEGY_IDS`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_ENABLED`
- `API_KEY`, `API_HOST`, `API_PORT`

## Testing

- pytest with `asyncio_mode = "auto"` (no `@pytest.mark.asyncio` needed)
- Tests use in-memory SQLite (`SqliteDataStore(":memory:")`) and fake exchange mocks
- Test files mirror source structure in `engine/tests/unit/` and `engine/tests/integration/`

## Deployment

Fly.io app `traderj-engine` in nrt (Tokyo). `fly.toml` at project root. Multi-stage Dockerfile at `engine/Dockerfile`. SQLite DB persisted on Fly volume at `/data/traderj.db`. Secrets managed via `flyctl secrets set`.
