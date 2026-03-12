"""TradingLoop — main trading cycle executed on a scheduled interval.

Each tick:
  1. Fetch OHLCV candles from exchange (per strategy timeframes)
  2. Generate signal via SignalGenerator
  3. Risk pre-validation
  4. State machine transitions (SCANNING → VALIDATING → EXECUTING → LOGGING → MONITORING)
  5. Order execution (BUY/SELL) via OrderManager
  6. Publish events and save to DB
  7. Process pending IPC commands
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pandas as pd

from engine.execution.circuit_breaker import CircuitBreaker
from engine.execution.order_manager import OrderManager
from engine.execution.position_manager import PositionManager
from engine.execution.risk_manager import RiskManager
from engine.loop.event_bus import EventBus
from engine.loop.state import ACTIVE_STATES, StateMachine
from engine.strategy.dca import DCAEngine
from engine.strategy.grid import GridEngine
from engine.strategy.indicators import compute_indicators
from engine.strategy.regime import RegimeConfig, detect_regime
from engine.strategy.regime_switch import RegimeSwitchManager
from engine.strategy.signal import SignalGenerator, SignalResult
from shared.enums import (
    BotStateEnum,
    OrderSide,
    OrderType,
    SignalDirection,
    TradingMode,
)
from shared.events import (
    MarketTickEvent,
    OHLCVUpdateEvent,
    OrderRequestEvent,
    RegimeChangeEvent,
    SignalEvent,
)
from shared.models import Candle, DailyPnL, PaperBalance, Signal

logger = logging.getLogger(__name__)


class TradingLoop:
    """Main trading cycle — fetches data, generates signals, executes orders."""

    def __init__(
        self,
        strategy_id: str,
        symbol: str,
        signal_generator: SignalGenerator,
        order_manager: OrderManager,
        position_manager: PositionManager,
        risk_manager: RiskManager,
        state_machine: StateMachine,
        event_bus: EventBus,
        data_store: Any,
        exchange_client: Any,
        trading_mode: TradingMode = TradingMode.PAPER,
        tick_interval: int = 60,
        regime_switch_manager: RegimeSwitchManager | None = None,
    ) -> None:
        self._strategy_id = strategy_id
        self._symbol = symbol
        self._signal_gen = signal_generator
        self._order_mgr = order_manager
        self._position_mgr = position_manager
        self._risk_mgr = risk_manager
        self._state = state_machine
        self._bus = event_bus
        self._store = data_store
        self._exchange = exchange_client
        self._mode = trading_mode
        self._tick_interval = tick_interval
        self._tick_count = 0
        self._running = False
        self._regime_mgr = regime_switch_manager
        self._dca_engine: DCAEngine | None = None
        self._grid_engine: GridEngine | None = None
        self._last_pnl_date: datetime | None = None

    @property
    def strategy_id(self) -> str:
        return self._strategy_id

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def tick_count(self) -> int:
        return self._tick_count

    async def start(self) -> None:
        """Start the trading loop (transition to STARTING → SCANNING)."""
        if self._running:
            logger.warning("TradingLoop already running for %s", self._strategy_id)
            return

        self._running = True

        # State: IDLE → STARTING → SCANNING
        if self._state.is_idle:
            await self._state.transition(BotStateEnum.STARTING, "loop_start")
            await self._state.transition(BotStateEnum.SCANNING, "ready")

        # Load persisted state
        await self._position_mgr.load_open_positions()
        await self._risk_mgr.load_state(self._strategy_id)

        # Initialize paper balance if needed
        if self._mode == TradingMode.PAPER:
            await self._ensure_paper_balance()

        logger.info(
            "TradingLoop started — strategy=%s, interval=%ds, mode=%s",
            self._strategy_id,
            self._tick_interval,
            self._mode,
        )

    async def stop(self) -> None:
        """Stop the trading loop."""
        if not self._running:
            return
        self._running = False

        if self._state.state in ACTIVE_STATES:
            await self._state.transition(BotStateEnum.SHUTTING_DOWN, "loop_stop")
            await self._state.transition(BotStateEnum.IDLE, "stopped")

        logger.info("TradingLoop stopped — strategy=%s, ticks=%d", self._strategy_id, self._tick_count)

    async def pause(self) -> None:
        """Pause the trading loop."""
        if self._state.state in (BotStateEnum.SCANNING, BotStateEnum.MONITORING):
            await self._state.transition(BotStateEnum.PAUSED, "user_pause")
            logger.info("TradingLoop paused — strategy=%s", self._strategy_id)

    async def resume(self) -> None:
        """Resume a paused trading loop."""
        if self._state.state == BotStateEnum.PAUSED:
            await self._state.transition(BotStateEnum.SCANNING, "user_resume")
            logger.info("TradingLoop resumed — strategy=%s", self._strategy_id)

    async def tick(self) -> SignalResult | None:
        """Execute one trading cycle. Called by Scheduler every interval.

        Returns the generated signal, or None if skipped.
        """
        if not self._running:
            return None

        if self._state.state == BotStateEnum.PAUSED:
            return None

        if self._state.state not in (BotStateEnum.SCANNING, BotStateEnum.MONITORING):
            return None

        self._tick_count += 1
        logger.debug("tick #%d for %s", self._tick_count, self._strategy_id)

        try:
            # Process pending IPC commands first
            await self._process_commands()

            if self._state.state == BotStateEnum.PAUSED:
                return None

            # [1] Fetch OHLCV data
            ohlcv_by_tf = await self._fetch_ohlcv()
            if not ohlcv_by_tf:
                logger.warning("No OHLCV data fetched, skipping tick")
                return None

            # Regime detection + auto-switch
            await self._check_regime_switch(ohlcv_by_tf)

            # Publish market tick
            await self._publish_market_tick()

            # [2] SCANNING → VALIDATING
            if self._state.state == BotStateEnum.MONITORING:
                await self._state.transition(BotStateEnum.SCANNING, "new_tick")
            await self._state.transition(BotStateEnum.VALIDATING, "signal_generating")

            # Generate signal
            macro_score = await self._get_macro_score()
            signal = self._signal_gen.generate(ohlcv_by_tf, macro_score=macro_score, symbol=self._symbol)

            # Save signal to DB
            await self._save_signal(signal)

            # Publish SignalEvent
            await self._bus.publish(SignalEvent(
                strategy_id=self._strategy_id,
                symbol=self._symbol,
                direction=signal.direction,
                score=signal.score,
                components=signal.details.get("tf_scores", {}),
                details=signal.details,
            ))

            # [3] VALIDATING → EXECUTING
            if signal.direction in (SignalDirection.BUY, SignalDirection.SELL):
                await self._state.transition(BotStateEnum.EXECUTING, f"signal_{signal.direction.value}")

                # Execute order
                await self._execute_signal(signal)

            # [4] → LOGGING → MONITORING (or back to SCANNING for HOLD)
            current = self._state.state
            if current == BotStateEnum.EXECUTING:
                await self._state.transition(BotStateEnum.LOGGING, "order_done")
                await self._state.transition(BotStateEnum.MONITORING, "logged")
            elif current == BotStateEnum.VALIDATING:
                # HOLD signal: go back to SCANNING
                await self._state.transition(BotStateEnum.SCANNING, "hold_signal")

            # [5] Record daily PnL (paper mode only)
            if self._mode == TradingMode.PAPER:
                await self._record_daily_pnl()

            return signal

        except Exception:
            logger.exception("Error in tick #%d for %s", self._tick_count, self._strategy_id)
            # Try to recover to SCANNING state
            if self._state.state not in (BotStateEnum.SCANNING, BotStateEnum.MONITORING, BotStateEnum.PAUSED):
                try:
                    await self._state.force_state(BotStateEnum.SCANNING, "error_recovery")
                except Exception:
                    logger.exception("Failed to recover state")
            return None

    # ── Regime detection ────────────────────────────────────────

    async def _check_regime_switch(self, ohlcv_by_tf: dict[str, pd.DataFrame]) -> None:
        """Detect market regime and switch strategy preset if needed."""
        if self._regime_mgr is None:
            return

        # Pick the longest available timeframe for regime detection
        tf_priority = ["4h", "1h", "1d", "15m"]
        regime_df = None
        for tf in tf_priority:
            if tf in ohlcv_by_tf and len(ohlcv_by_tf[tf]) >= 30:
                regime_df = ohlcv_by_tf[tf]
                break

        if regime_df is None:
            return

        try:
            df_ind = compute_indicators(regime_df)
            regime_result = detect_regime(df_ind)
        except Exception:
            logger.debug("Regime detection failed, skipping")
            return

        decision = self._regime_mgr.evaluate(regime_result)

        if decision.should_switch:
            old_regime = self._regime_mgr.current_regime
            new_preset_id = self._regime_mgr.apply_switch(decision)
            preset = self._regime_mgr.get_preset(new_preset_id)
            if preset:
                self._signal_gen.apply_preset(preset)
                logger.info(
                    "Regime auto-switch: %s → %s (regime=%s, confidence=%.2f)",
                    decision.reason, new_preset_id,
                    decision.current_regime, decision.confidence,
                )

            # Reconfigure DCA/Grid engines for new regime
            current_price = self._get_last_close(ohlcv_by_tf)
            self._reconfigure_dca_grid(decision.current_regime, current_price)

            await self._bus.publish(RegimeChangeEvent(
                strategy_id=self._strategy_id,
                old_regime=old_regime,
                new_regime=decision.current_regime,
                overrides={"new_preset": new_preset_id},
            ))

    # ── Data fetching ────────────────────────────────────────────

    async def _fetch_ohlcv(self) -> dict[str, pd.DataFrame]:
        """Fetch OHLCV candles for all strategy timeframes."""
        tf_weights = self._signal_gen.tf_weights
        timeframes = list(tf_weights.keys())

        # If daily gate is used, also fetch 1d
        if self._signal_gen.use_daily_gate and "1d" not in timeframes:
            timeframes.append("1d")

        result: dict[str, pd.DataFrame] = {}
        for tf in timeframes:
            try:
                candles = await self._exchange.fetch_ohlcv(self._symbol, tf, limit=200)
                if candles:
                    df = self._candles_to_df(candles)
                    result[tf] = df
                    # Save to DB
                    await self._store.upsert_candles(candles)
                    logger.debug("Fetched %s %s: %d candles", self._symbol, tf, len(candles))
            except Exception:
                logger.exception("Failed to fetch OHLCV %s %s", self._symbol, tf)

        if result:
            counts = ", ".join(f"{tf}={len(df)}" for tf, df in result.items())
            logger.info("Fetched OHLCV: %s", counts)

        return result

    async def _publish_market_tick(self) -> None:
        """Publish current market tick event."""
        try:
            ticker = await self._exchange.fetch_ticker(self._symbol)
            await self._bus.publish(MarketTickEvent(
                symbol=self._symbol,
                price=Decimal(str(ticker.get("last", "0"))),
                bid=Decimal(str(ticker.get("bid", "0"))),
                ask=Decimal(str(ticker.get("ask", "0"))),
                volume_24h=Decimal(str(ticker.get("volume", "0"))),
            ))
        except Exception:
            logger.exception("Failed to publish market tick")

    async def _get_macro_score(self) -> float:
        """Get latest macro score from DB."""
        try:
            macro = await self._store.get_latest_macro()
            if macro:
                return macro.market_score
        except Exception:
            logger.debug("No macro data available")
        return 0.0

    # ── Signal execution ─────────────────────────────────────────

    async def _execute_signal(self, signal: SignalResult) -> None:
        """Execute BUY or SELL based on signal direction."""
        has_position = self._position_mgr.has_open_position(self._strategy_id)

        if signal.direction == SignalDirection.BUY and not has_position:
            await self._execute_buy(signal)
        elif signal.direction == SignalDirection.SELL and has_position:
            await self._execute_sell(signal)
        else:
            reason = "already_has_position" if has_position else "no_position_to_sell"
            logger.info("Skipping %s: %s", signal.direction.value, reason)

    async def _execute_buy(self, signal: SignalResult) -> None:
        """Execute a buy order with risk validation."""
        # Get current price and ATR for risk check
        try:
            ticker = await self._exchange.fetch_ticker(self._symbol)
            current_price = float(ticker.get("last", "0"))
        except Exception:
            logger.exception("Failed to get price for risk check")
            return

        # Get balance
        balance = await self._store.get_paper_balance(self._strategy_id)
        if balance is None:
            logger.warning("No paper balance for %s", self._strategy_id)
            return

        total_balance = float(balance.krw) + float(balance.btc) * current_price
        existing_position = float(balance.btc) * current_price

        # Risk pre-validation
        allowed, reason, suggested_krw = await self._risk_mgr.pre_validate(
            strategy_id=self._strategy_id,
            side=OrderSide.BUY,
            total_balance_krw=total_balance,
            current_price=current_price,
            current_atr=current_price * 0.03,  # fallback ATR estimate
            existing_position_krw=existing_position,
        )

        if not allowed:
            logger.info("Buy blocked by risk: %s", reason)
            return

        # Calculate order amount
        amount_krw = min(suggested_krw, float(balance.krw))
        if amount_krw <= 0 or current_price <= 0:
            return
        amount_btc = Decimal(str(round(amount_krw / current_price, 8)))

        # Submit order
        request = OrderRequestEvent(
            strategy_id=self._strategy_id,
            symbol=self._symbol,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=amount_btc,
            idempotency_key=f"{self._strategy_id}-buy-{uuid.uuid4().hex[:8]}",
        )
        result = await self._order_mgr.handle_order_request(request)

        if result.success:
            logger.info("BUY executed: %s BTC at %s", amount_btc, current_price)

            # Set SL/TP/Trailing Stop from risk decision
            decision = self._risk_mgr.get_last_decision(self._strategy_id)
            if decision:
                if decision.stop_loss_price > 0:
                    self._position_mgr.set_stop_loss(
                        self._strategy_id,
                        Decimal(str(int(decision.stop_loss_price))),
                    )
                if decision.take_profit_price > 0:
                    self._position_mgr.set_take_profit(
                        self._strategy_id,
                        Decimal(str(int(decision.take_profit_price))),
                    )
                if decision.trailing_stop_activation > 0:
                    self._position_mgr.configure_trailing_stop(
                        self._strategy_id,
                        activation_price=Decimal(
                            str(int(decision.trailing_stop_activation))
                        ),
                        distance_pct=decision.trailing_stop_distance_pct,
                    )
                logger.info(
                    "Risk params set: SL=%s, TP=%s, TrailingActivation=%s",
                    decision.stop_loss_price,
                    decision.take_profit_price,
                    decision.trailing_stop_activation,
                )
        else:
            logger.warning("BUY failed: %s", result.reason)

    async def _execute_sell(self, signal: SignalResult) -> None:
        """Execute a sell order for the full position."""
        pos = self._position_mgr.get_position(self._strategy_id)
        if pos is None:
            return

        request = OrderRequestEvent(
            strategy_id=self._strategy_id,
            symbol=self._symbol,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            amount=pos.amount,
            idempotency_key=f"{self._strategy_id}-sell-{uuid.uuid4().hex[:8]}",
        )
        result = await self._order_mgr.handle_order_request(request)

        if result.success:
            logger.info("SELL executed: %s BTC", pos.amount)
        else:
            logger.warning("SELL failed: %s", result.reason)

    # ── IPC command processing ───────────────────────────────────

    async def _process_commands(self) -> None:
        """Process pending bot commands from IPC."""
        try:
            commands = await self._store.get_pending_commands(self._strategy_id)
        except Exception:
            return

        for cmd in commands:
            try:
                await self._handle_command(cmd.command, cmd.params)
                await self._store.mark_command_processed(cmd.id)
            except Exception:
                logger.exception("Failed to process command: %s", cmd.command)

    async def _handle_command(self, command: str, params: dict) -> None:
        """Handle a single bot command."""
        if command == "pause":
            await self.pause()
        elif command == "resume":
            await self.resume()
        elif command == "stop":
            await self.stop()
        elif command == "emergency_exit":
            await self._emergency_exit()
        else:
            logger.warning("Unknown command: %s", command)

    async def _emergency_exit(self) -> None:
        """Emergency exit: close all positions and stop."""
        logger.warning("EMERGENCY EXIT for %s", self._strategy_id)

        # Close open position if any
        if self._position_mgr.has_open_position(self._strategy_id):
            pos = self._position_mgr.get_position(self._strategy_id)
            if pos:
                request = OrderRequestEvent(
                    strategy_id=self._strategy_id,
                    symbol=self._symbol,
                    side=OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    amount=pos.amount,
                    idempotency_key=f"{self._strategy_id}-emergency-{uuid.uuid4().hex[:8]}",
                )
                result = await self._order_mgr.handle_order_request(request)
                if result.success:
                    logger.info("Emergency sell executed")
                else:
                    logger.error("Emergency sell failed: %s", result.reason)

        # Force stop
        await self._state.force_state(BotStateEnum.IDLE, "emergency_exit")
        self._running = False

    # ── DCA/Grid regime reconfiguration ─────────────────────────

    def _reconfigure_dca_grid(
        self,
        regime: Any,
        current_price: float,
    ) -> None:
        """Reconfigure DCA and Grid engines based on new regime."""
        if self._regime_mgr is None or regime is None:
            return

        # DCA reconfiguration
        dca_config = self._regime_mgr.get_dca_config(regime)
        if dca_config is not None:
            old_state = None
            if self._dca_engine is not None:
                old_state = (self._dca_engine._last_buy_time, self._dca_engine._total_invested, self._dca_engine._buy_count)
            self._dca_engine = DCAEngine(config=dca_config, strategy_id=self._strategy_id)
            if old_state is not None:
                self._dca_engine._last_buy_time = old_state[0]
                self._dca_engine._total_invested = old_state[1]
                self._dca_engine._buy_count = old_state[2]
            logger.info(
                "DCA reconfigured: buy=%s KRW, interval=%dh (regime=%s)",
                dca_config.base_buy_krw, dca_config.interval_hours, regime,
            )

        # Grid reconfiguration
        grid_config = self._regime_mgr.get_grid_config(current_price, regime)
        if grid_config is not None:
            self._grid_engine = GridEngine(config=grid_config, strategy_id=self._strategy_id)
            logger.info(
                "Grid activated: %d grids, %s-%s KRW (regime=%s)",
                grid_config.num_grids, grid_config.lower_price,
                grid_config.upper_price, regime,
            )
        else:
            if self._grid_engine is not None:
                logger.info("Grid deactivated (regime=%s)", regime)
            self._grid_engine = None

    @staticmethod
    def _get_last_close(ohlcv_by_tf: dict[str, pd.DataFrame]) -> float:
        """Get the last close price from available OHLCV data."""
        for tf in ["1h", "4h", "1d", "15m"]:
            if tf in ohlcv_by_tf and len(ohlcv_by_tf[tf]) > 0:
                return float(ohlcv_by_tf[tf]["close"].iloc[-1])
        return 0.0

    # ── Daily PnL recording ─────────────────────────────────────

    async def _record_daily_pnl(self) -> None:
        """Record daily PnL snapshot for the current day."""
        today = datetime.now(UTC).date()

        # Skip if already recorded this tick-minute
        if self._last_pnl_date == today and self._tick_count % 5 != 0:
            return

        try:
            balance = await self._store.get_paper_balance(self._strategy_id)
            if not balance:
                return

            # Get current BTC price
            ticker = await self._exchange.fetch_ticker(self._symbol)
            price = Decimal(str(ticker.get("last", "0")))
            if price <= 0:
                return

            # Total portfolio value
            total = balance.krw + balance.btc * price
            unrealized = total - balance.initial_krw

            # Count today's filled orders
            orders = await self._store.get_orders(self._strategy_id, status="filled")
            today_orders = [
                o for o in orders
                if o.filled_at and o.filled_at.date() == today
            ]
            trade_count = len(today_orders)

            # Realized PnL from closed positions today
            positions = await self._store.get_positions(
                self._strategy_id, status="closed"
            )
            today_closed = [
                p for p in positions
                if p.closed_at and p.closed_at.date() == today
            ]
            realized = sum(
                (p.realized_pnl for p in today_closed), Decimal("0")
            )

            pnl = DailyPnL(
                date=today,
                strategy_id=self._strategy_id,
                realized=realized,
                unrealized=unrealized,
                trade_count=trade_count,
            )
            await self._store.save_daily_pnl(pnl)
            self._last_pnl_date = today

            logger.debug(
                "Daily PnL recorded: realized=%s, unrealized=%s, trades=%d",
                realized, unrealized, trade_count,
            )
        except Exception:
            logger.exception("Failed to record daily PnL")

    # ── Helpers ──────────────────────────────────────────────────

    async def _save_signal(self, signal: SignalResult) -> None:
        """Save signal result to DB."""
        try:
            db_signal = Signal(
                id=str(uuid.uuid4()),
                strategy_id=self._strategy_id,
                symbol=self._symbol,
                direction=signal.direction,
                score=Decimal(str(signal.score)),
                components=signal.details.get("tf_scores", {}),
                details=signal.details,
                created_at=signal.timestamp,
            )
            await self._store.save_signal(db_signal)
        except Exception:
            logger.exception("Failed to save signal")

    async def _ensure_paper_balance(self) -> None:
        """Create initial paper balance if not exists."""
        balance = await self._store.get_paper_balance(self._strategy_id)
        if balance is None:
            from engine.config.settings import TradingSettings

            settings = TradingSettings()
            initial_krw = Decimal(str(settings.initial_krw))
            balance = PaperBalance(
                strategy_id=self._strategy_id,
                krw=initial_krw,
                btc=Decimal("0"),
                initial_krw=initial_krw,
            )
            await self._store.save_paper_balance(balance)
            logger.info("Initialized paper balance: %s KRW", initial_krw)

    @staticmethod
    def _candles_to_df(candles: list[Candle]) -> pd.DataFrame:
        """Convert Candle list to pandas DataFrame with OHLCV columns."""
        data = {
            "open": [float(c.open) for c in candles],
            "high": [float(c.high) for c in candles],
            "low": [float(c.low) for c in candles],
            "close": [float(c.close) for c in candles],
            "volume": [float(c.volume) for c in candles],
        }
        index = pd.DatetimeIndex([c.time for c in candles])
        return pd.DataFrame(data, index=index)
