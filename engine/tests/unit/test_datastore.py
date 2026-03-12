"""Unit tests for SqliteDataStore.

Tests full CRUD operations, filtering, and DataStore Protocol compliance.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from engine.data.sqlite_store import SqliteDataStore
from shared.enums import (
    BotStateEnum,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionStatus,
    SignalDirection,
    TradingMode,
)
from shared.models import (
    BacktestResult,
    BotCommand,
    BotStateModel,
    Candle,
    DailyPnL,
    MacroSnapshot,
    Order,
    PaperBalance,
    Position,
    RiskState,
    Signal,
)


@pytest.fixture()
async def store():
    s = SqliteDataStore(":memory:")
    await s.connect()
    yield s
    await s.disconnect()


class TestCandles:
    @pytest.mark.asyncio
    async def test_upsert_and_get(self, store: SqliteDataStore) -> None:
        candles = [
            Candle(
                time=datetime(2024, 1, 1, 0, 0),
                symbol="BTC/KRW",
                timeframe="4h",
                open=Decimal("50000000"),
                high=Decimal("51000000"),
                low=Decimal("49000000"),
                close=Decimal("50500000"),
                volume=Decimal("100"),
            ),
            Candle(
                time=datetime(2024, 1, 1, 4, 0),
                symbol="BTC/KRW",
                timeframe="4h",
                open=Decimal("50500000"),
                high=Decimal("52000000"),
                low=Decimal("50000000"),
                close=Decimal("51500000"),
                volume=Decimal("120"),
            ),
        ]
        count = await store.upsert_candles(candles)
        assert count == 2

        result = await store.get_candles("BTC/KRW", "4h")
        assert len(result) == 2
        assert result[0].close == Decimal("50500000")
        assert result[1].close == Decimal("51500000")

    @pytest.mark.asyncio
    async def test_upsert_deduplicates(self, store: SqliteDataStore) -> None:
        candle = Candle(
            time=datetime(2024, 1, 1, 0, 0),
            symbol="BTC/KRW",
            timeframe="4h",
            open=Decimal("50000000"),
            high=Decimal("51000000"),
            low=Decimal("49000000"),
            close=Decimal("50500000"),
            volume=Decimal("100"),
        )
        await store.upsert_candles([candle])
        await store.upsert_candles([candle])
        result = await store.get_candles("BTC/KRW", "4h")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_filter_by_time(self, store: SqliteDataStore) -> None:
        candles = [
            Candle(
                time=datetime(2024, 1, i, 0, 0),
                symbol="BTC/KRW",
                timeframe="1d",
                open=Decimal("50000000"),
                high=Decimal("51000000"),
                low=Decimal("49000000"),
                close=Decimal("50500000"),
                volume=Decimal("100"),
            )
            for i in range(1, 11)
        ]
        await store.upsert_candles(candles)
        result = await store.get_candles(
            "BTC/KRW",
            "1d",
            start=datetime(2024, 1, 3),
            end=datetime(2024, 1, 7),
        )
        assert len(result) == 5


class TestSignals:
    @pytest.mark.asyncio
    async def test_save_and_get(self, store: SqliteDataStore) -> None:
        signal = Signal(
            id="sig-1",
            strategy_id="STR-001",
            symbol="BTC/KRW",
            direction=SignalDirection.BUY,
            score=Decimal("0.75"),
            components={"trend": 0.8, "momentum": 0.7},
            details={"reason": "strong trend"},
            created_at=datetime(2024, 1, 1, 12, 0),
        )
        await store.save_signal(signal)
        result = await store.get_signals(strategy_id="STR-001")
        assert len(result) == 1
        assert result[0].direction == "buy"
        assert result[0].score == Decimal("0.75")

    @pytest.mark.asyncio
    async def test_get_all(self, store: SqliteDataStore) -> None:
        for i in range(3):
            await store.save_signal(
                Signal(
                    id=f"sig-{i}",
                    strategy_id=f"STR-00{i}",
                    symbol="BTC/KRW",
                    direction=SignalDirection.HOLD,
                    score=Decimal("0.5"),
                    components={},
                    details={},
                    created_at=datetime(2024, 1, 1, i, 0),
                )
            )
        result = await store.get_signals()
        assert len(result) == 3


class TestOrders:
    @pytest.mark.asyncio
    async def test_save_and_filter(self, store: SqliteDataStore) -> None:
        order = Order(
            id="ord-1",
            strategy_id="STR-001",
            symbol="BTC/KRW",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=Decimal("0.001"),
            price=Decimal("50000000"),
            status=OrderStatus.FILLED,
            idempotency_key="key-1",
            created_at=datetime(2024, 1, 1, 12, 0),
            filled_at=datetime(2024, 1, 1, 12, 1),
        )
        await store.save_order(order)
        result = await store.get_orders(strategy_id="STR-001", status="filled")
        assert len(result) == 1
        assert result[0].side == OrderSide.BUY


class TestPositions:
    @pytest.mark.asyncio
    async def test_save_and_filter_by_status(self, store: SqliteDataStore) -> None:
        open_pos = Position(
            id="pos-1",
            strategy_id="STR-001",
            symbol="BTC/KRW",
            side=OrderSide.BUY,
            amount=Decimal("0.001"),
            entry_price=Decimal("50000000"),
            current_price=Decimal("51000000"),
            stop_loss=Decimal("48500000"),
            trailing_stop=None,
            unrealized_pnl=Decimal("1000"),
            realized_pnl=Decimal("0"),
            status=PositionStatus.OPEN,
            opened_at=datetime(2024, 1, 1, 12, 0),
        )
        await store.save_position(open_pos)

        result = await store.get_positions(status="open")
        assert len(result) == 1
        assert result[0].unrealized_pnl == Decimal("1000")

        result = await store.get_positions(status="closed")
        assert len(result) == 0


class TestRiskState:
    @pytest.mark.asyncio
    async def test_save_and_get(self, store: SqliteDataStore) -> None:
        rs = RiskState(
            strategy_id="STR-001",
            consecutive_losses=2,
            daily_pnl=Decimal("-5000"),
            last_updated=datetime(2024, 1, 1, 12, 0),
        )
        await store.save_risk_state(rs)
        result = await store.get_risk_state("STR-001")
        assert result is not None
        assert result.consecutive_losses == 2

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown(self, store: SqliteDataStore) -> None:
        result = await store.get_risk_state("UNKNOWN")
        assert result is None


class TestBotState:
    @pytest.mark.asyncio
    async def test_save_and_get(self, store: SqliteDataStore) -> None:
        bs = BotStateModel(
            strategy_id="STR-001",
            state=BotStateEnum.SCANNING,
            trading_mode=TradingMode.PAPER,
            last_updated=datetime(2024, 1, 1, 12, 0),
        )
        await store.save_bot_state(bs)
        result = await store.get_bot_state("STR-001")
        assert result is not None
        assert result.state == BotStateEnum.SCANNING


class TestPaperBalance:
    @pytest.mark.asyncio
    async def test_save_and_get(self, store: SqliteDataStore) -> None:
        pb = PaperBalance(
            strategy_id="STR-001",
            krw=Decimal("10000000"),
            btc=Decimal("0.1"),
            initial_krw=Decimal("10000000"),
        )
        await store.save_paper_balance(pb)
        result = await store.get_paper_balance("STR-001")
        assert result is not None
        assert result.krw == Decimal("10000000")


class TestDailyPnL:
    @pytest.mark.asyncio
    async def test_save_and_get(self, store: SqliteDataStore) -> None:
        pnl = DailyPnL(
            date=date(2024, 1, 1),
            strategy_id="STR-001",
            realized=Decimal("5000"),
            unrealized=Decimal("2000"),
            trade_count=3,
        )
        await store.save_daily_pnl(pnl)
        result = await store.get_daily_pnl("STR-001")
        assert len(result) == 1
        assert result[0].trade_count == 3


class TestMacro:
    @pytest.mark.asyncio
    async def test_save_and_get_latest(self, store: SqliteDataStore) -> None:
        snap = MacroSnapshot(
            timestamp=datetime(2024, 1, 1, 12, 0),
            fear_greed=55.0,
            funding_rate=0.01,
            btc_dominance=52.0,
            btc_dom_7d_change=-1.5,
            dxy=103.5,
            kimchi_premium=2.1,
            market_score=0.6,
        )
        await store.save_macro_snapshot(snap)
        result = await store.get_latest_macro()
        assert result is not None
        assert result.fear_greed == 55.0


class TestBotCommands:
    @pytest.mark.asyncio
    async def test_save_get_mark_processed(self, store: SqliteDataStore) -> None:
        cmd = BotCommand(
            id="cmd-1",
            command="start",
            strategy_id="STR-001",
            params={},
            status="pending",
            created_at=datetime(2024, 1, 1, 12, 0),
        )
        await store.save_bot_command(cmd)

        pending = await store.get_pending_commands("STR-001")
        assert len(pending) == 1

        await store.mark_command_processed("cmd-1")
        pending = await store.get_pending_commands("STR-001")
        assert len(pending) == 0


class TestBacktestResults:
    @pytest.mark.asyncio
    async def test_save_and_get(self, store: SqliteDataStore) -> None:
        result = BacktestResult(
            id="bt-1",
            strategy_id="STR-001",
            config_json={"initial_balance": 10000000},
            metrics_json={"total_return_pct": 5.2, "sharpe_ratio": 1.3},
            equity_curve_json=[{"bar": 0, "equity": 10000000}],
            trades_json=[{"side": "buy", "price": 50000000}],
            created_at=datetime(2024, 1, 1, 12, 0),
        )
        await store.save_backtest_result(result, params_hash="abc123")

        results = await store.get_backtest_results(strategy_id="STR-001")
        assert len(results) == 1
        assert results[0].id == "bt-1"
        assert results[0].metrics_json["total_return_pct"] == 5.2

    @pytest.mark.asyncio
    async def test_get_all(self, store: SqliteDataStore) -> None:
        for i in range(3):
            result = BacktestResult(
                id=f"bt-{i}",
                strategy_id=f"STR-00{i}",
                config_json={},
                metrics_json={"return": i},
                equity_curve_json=[],
                trades_json=[],
                created_at=datetime(2024, 1, 1, i, 0),
            )
            await store.save_backtest_result(result, params_hash=f"hash{i}")

        results = await store.get_backtest_results()
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_filter_by_strategy(self, store: SqliteDataStore) -> None:
        for i in range(3):
            sid = "STR-001" if i < 2 else "STR-002"
            result = BacktestResult(
                id=f"bt-{i}",
                strategy_id=sid,
                config_json={},
                metrics_json={},
                equity_curve_json=[],
                trades_json=[],
                created_at=datetime(2024, 1, 1, i, 0),
            )
            await store.save_backtest_result(result, params_hash=f"hash{i}")

        results = await store.get_backtest_results(strategy_id="STR-001")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_walk_forward_json(self, store: SqliteDataStore) -> None:
        result = BacktestResult(
            id="bt-wf",
            strategy_id="STR-001",
            config_json={},
            metrics_json={},
            equity_curve_json=[],
            trades_json=[],
            created_at=datetime(2024, 1, 1, 12, 0),
            walk_forward_json={"folds": 5, "avg_return": 3.2},
        )
        await store.save_backtest_result(result, params_hash="wfhash")

        results = await store.get_backtest_results(strategy_id="STR-001")
        assert results[0].walk_forward_json is not None
        assert results[0].walk_forward_json["folds"] == 5
