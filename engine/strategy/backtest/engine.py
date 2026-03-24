"""Backtest Engine — vectorized event-driven backtesting.

Runs the full strategy pipeline (signal generation + risk evaluation)
on historical candle data to produce trade records and equity curves.
Strictly avoids look-ahead bias by processing candles sequentially.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from engine.strategy.indicators import compute_indicators
from engine.strategy.regime import detect_regime
from engine.strategy.regime_switch import RegimeSwitchManager
from engine.strategy.risk import RiskConfig, RiskDecision, RiskEngine
from engine.strategy.signal import SignalGenerator, SignalResult
from shared.enums import SignalDirection

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BacktestTrade:
    """A single trade in the backtest."""

    trade_id: str
    entry_time: datetime
    exit_time: datetime
    side: str
    entry_price: float
    exit_price: float
    amount_btc: float
    pnl_krw: float
    pnl_pct: float
    exit_reason: str


@dataclass
class BacktestConfig:
    """Backtest execution parameters."""

    initial_balance_krw: float = 50_000_000.0
    fee_rate: float = 0.0005
    slippage_bps: float = 5.0
    max_bars: int | None = None


@dataclass
class BacktestState:
    """Mutable state during backtest execution."""

    balance_krw: float = 50_000_000.0
    position_btc: float = 0.0
    entry_price: float = 0.0
    entry_time: datetime | None = None
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[dict[str, Any]] = field(default_factory=list)

    # Stop loss / Take profit / Trailing stop state
    stop_loss_price: float = 0.0
    take_profit_price: float = 0.0
    trailing_stop_activation: float = 0.0
    trailing_stop_distance_pct: float = 0.0
    trailing_high: float = 0.0


class BacktestEngine:
    """Event-driven backtest engine with sequential bar processing."""

    def __init__(
        self,
        signal_generator: SignalGenerator,
        risk_config: RiskConfig | None = None,
        config: BacktestConfig | None = None,
        regime_switch_manager: RegimeSwitchManager | None = None,
    ) -> None:
        self.signal_gen = signal_generator
        self.risk_engine = RiskEngine(
            config=risk_config or RiskConfig(),
            strategy_id=signal_generator.strategy_id,
        )
        self.config = config or BacktestConfig()
        self._regime_mgr = regime_switch_manager

    def run(
        self,
        ohlcv_by_tf: dict[str, pd.DataFrame],
        macro_scores: pd.Series | None = None,
        primary_tf: str = "1h",
    ) -> BacktestResult:
        """Run backtest on historical data.

        Args:
            ohlcv_by_tf: Historical candle data by timeframe.
            macro_scores: Optional Series of macro scores indexed by datetime.
            primary_tf: Primary timeframe for bar iteration.

        Returns:
            BacktestResult with trades, equity curve, and metrics.
        """
        primary_df = ohlcv_by_tf.get(primary_tf)
        if primary_df is None or primary_df.empty:
            raise ValueError(f"No data for primary timeframe {primary_tf}")

        state = BacktestState(balance_krw=self.config.initial_balance_krw)
        min_bars = 50  # Minimum bars needed for indicators

        bars = primary_df.iloc[min_bars:]
        if self.config.max_bars:
            bars = bars.iloc[: self.config.max_bars]

        for idx in range(len(bars)):
            bar = bars.iloc[idx]
            bar_time = bar.name if isinstance(bar.name, datetime) else pd.Timestamp(bar.name).to_pydatetime()
            current_price = float(bar["close"])
            bar_high = float(bar["high"])
            bar_low = float(bar["low"])

            # Check price-based exits BEFORE signal processing
            if state.position_btc > 0:
                exit_reason = self._check_price_exit(state, bar_high, bar_low)
                if exit_reason:
                    exit_price = (
                        state.stop_loss_price if "stop_loss" in exit_reason
                        else state.take_profit_price if "take_profit" in exit_reason
                        else state.trailing_high * (1 - state.trailing_stop_distance_pct)
                    )
                    self._close_position(state, exit_price, bar_time, exit_reason)

            # Build look-back window per TF (no look-ahead)
            window: dict[str, pd.DataFrame] = {}
            for tf, df in ohlcv_by_tf.items():
                mask = df.index <= bar.name
                window[tf] = df.loc[mask].tail(200)

            # Macro score
            macro = 0.0
            if macro_scores is not None and bar.name in macro_scores.index:
                macro = float(macro_scores.loc[bar.name])

            # Regime detection + auto-switch
            self._check_regime(window)

            # Generate signal
            signal = self.signal_gen.generate(window, macro_score=macro)

            # ATR for risk evaluation
            atr = self._compute_atr(window.get(primary_tf, primary_df.iloc[:1]))

            # Process signal
            self._process_signal(state, signal, current_price, bar_time, atr)

            # Record equity
            position_value = state.position_btc * current_price
            equity = state.balance_krw + position_value
            state.equity_curve.append({
                "time": bar_time.isoformat(),
                "equity": round(equity, 0),
                "balance": round(state.balance_krw, 0),
                "position_value": round(position_value, 0),
                "price": current_price,
            })

        # Force close any open position at end
        if state.position_btc > 0:
            final_price = float(bars.iloc[-1]["close"])
            final_time = bars.index[-1]
            if not isinstance(final_time, datetime):
                final_time = pd.Timestamp(final_time).to_pydatetime()
            self._close_position(state, final_price, final_time, "backtest_end")

        from engine.strategy.backtest.metrics import compute_metrics

        metrics = compute_metrics(
            trades=state.trades,
            equity_curve=state.equity_curve,
            initial_balance=self.config.initial_balance_krw,
        )

        regime_history = self._regime_mgr.get_history() if self._regime_mgr else []

        return BacktestResult(
            strategy_id=self.signal_gen.strategy_id,
            config={
                "initial_balance": self.config.initial_balance_krw,
                "fee_rate": self.config.fee_rate,
                "slippage_bps": self.config.slippage_bps,
                "primary_tf": primary_tf,
                "bars_processed": len(bars),
                "regime_switches": len(regime_history),
                "regime_history": regime_history,
            },
            trades=state.trades,
            equity_curve=state.equity_curve,
            metrics=metrics,
        )

    def _process_signal(
        self,
        state: BacktestState,
        signal: SignalResult,
        price: float,
        bar_time: datetime,
        atr: float,
    ) -> None:
        """Process a signal: open or close position."""
        if signal.direction == SignalDirection.BUY and state.position_btc == 0:
            # Evaluate risk
            decision = self.risk_engine.evaluate_buy(
                total_balance_krw=state.balance_krw,
                current_price=price,
                current_atr=atr,
            )
            if decision.allowed and decision.position_size_krw > 0:
                self._open_position(state, price, bar_time, decision)

        elif signal.direction == SignalDirection.SELL and state.position_btc > 0:
            self._close_position(state, price, bar_time, "signal_sell")

    def _open_position(
        self,
        state: BacktestState,
        price: float,
        bar_time: datetime,
        decision: RiskDecision,
    ) -> None:
        """Open a long position."""
        slippage = price * self.config.slippage_bps / 10000
        entry_price = price + slippage
        fee = decision.position_size_krw * self.config.fee_rate
        net_krw = decision.position_size_krw - fee
        amount_btc = net_krw / entry_price

        state.balance_krw -= decision.position_size_krw
        state.position_btc = amount_btc
        state.entry_price = entry_price
        state.entry_time = bar_time

        # Store risk levels from RiskDecision
        state.stop_loss_price = decision.stop_loss_price
        state.take_profit_price = decision.take_profit_price
        state.trailing_stop_activation = decision.trailing_stop_activation
        state.trailing_stop_distance_pct = decision.trailing_stop_distance_pct
        state.trailing_high = entry_price

    def _close_position(
        self,
        state: BacktestState,
        price: float,
        bar_time: datetime,
        reason: str,
    ) -> None:
        """Close the current position."""
        if state.position_btc <= 0:
            return

        slippage = price * self.config.slippage_bps / 10000
        exit_price = price - slippage
        gross_krw = state.position_btc * exit_price
        fee = gross_krw * self.config.fee_rate
        net_krw = gross_krw - fee
        pnl = net_krw - (state.position_btc * state.entry_price)
        pnl_pct = pnl / (state.position_btc * state.entry_price) if state.entry_price > 0 else 0

        trade = BacktestTrade(
            trade_id=str(uuid.uuid4())[:8],
            entry_time=state.entry_time or bar_time,
            exit_time=bar_time,
            side="long",
            entry_price=state.entry_price,
            exit_price=exit_price,
            amount_btc=state.position_btc,
            pnl_krw=round(pnl, 0),
            pnl_pct=round(pnl_pct, 6),
            exit_reason=reason,
        )
        state.trades.append(trade)

        # Update risk engine
        self.risk_engine.record_trade_result(pnl)

        state.balance_krw += net_krw
        state.position_btc = 0.0
        state.entry_price = 0.0
        state.entry_time = None
        state.stop_loss_price = 0.0
        state.take_profit_price = 0.0
        state.trailing_stop_activation = 0.0
        state.trailing_stop_distance_pct = 0.0
        state.trailing_high = 0.0

    def _check_price_exit(
        self,
        state: BacktestState,
        bar_high: float,
        bar_low: float,
    ) -> str | None:
        """Check if price hit stop loss, take profit, or trailing stop.

        Returns exit reason string or None.
        """
        # 1. Stop loss
        if state.stop_loss_price > 0 and bar_low <= state.stop_loss_price:
            return "stop_loss"

        # 2. Take profit
        if state.take_profit_price > 0 and bar_high >= state.take_profit_price:
            return "take_profit"

        # 3. Trailing stop: update trailing_high, then check
        if bar_high > state.trailing_high:
            state.trailing_high = bar_high

        if (
            state.trailing_stop_activation > 0
            and state.trailing_high >= state.trailing_stop_activation
            and state.trailing_stop_distance_pct > 0
        ):
            trail_stop_price = state.trailing_high * (1 - state.trailing_stop_distance_pct)
            if bar_low <= trail_stop_price:
                return "trailing_stop"

        return None

    def _check_regime(self, window: dict[str, pd.DataFrame]) -> None:
        """Detect regime and switch strategy preset if needed."""
        if self._regime_mgr is None:
            return

        tf_priority = ["4h", "1h", "1d", "15m"]
        regime_df = None
        for tf in tf_priority:
            if tf in window and len(window[tf]) >= 30:
                regime_df = window[tf]
                break

        if regime_df is None:
            return

        try:
            df_ind = compute_indicators(regime_df)
            regime_result = detect_regime(df_ind)
        except Exception:
            return

        decision = self._regime_mgr.evaluate(regime_result)
        if decision.should_switch:
            new_preset_id = self._regime_mgr.apply_switch(decision)
            preset = self._regime_mgr.get_preset(new_preset_id)
            if preset:
                self.signal_gen.apply_preset(preset)

    @staticmethod
    def _compute_atr(df: pd.DataFrame, period: int = 14) -> float:
        """Compute ATR from recent candles."""
        if len(df) < period + 1:
            return 0.0
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        close = df["close"].astype(float)
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        return float(tr.rolling(period).mean().iloc[-1])


@dataclass
class BacktestResult:
    """Complete backtest results."""

    strategy_id: str
    config: dict[str, Any]
    trades: list[BacktestTrade]
    equity_curve: list[dict[str, Any]]
    metrics: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "strategy_id": self.strategy_id,
            "config": self.config,
            "trades": [
                {
                    "trade_id": t.trade_id,
                    "entry_time": t.entry_time.isoformat(),
                    "exit_time": t.exit_time.isoformat(),
                    "side": t.side,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "amount_btc": t.amount_btc,
                    "pnl_krw": t.pnl_krw,
                    "pnl_pct": t.pnl_pct,
                    "exit_reason": t.exit_reason,
                }
                for t in self.trades
            ],
            "equity_curve": self.equity_curve,
            "metrics": self.metrics,
        }
