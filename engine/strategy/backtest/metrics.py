"""Backtest performance metrics calculator.

Computes standard trading performance metrics:
- Total return, CAGR
- Sharpe ratio, Sortino ratio
- Max drawdown, Calmar ratio
- Win rate, profit factor
- Trade statistics
"""

from __future__ import annotations

import math
from typing import Any

from engine.strategy.backtest.engine import BacktestTrade


def compute_metrics(
    trades: list[BacktestTrade],
    equity_curve: list[dict[str, Any]],
    initial_balance: float,
    risk_free_rate: float = 0.035,
    trading_days_per_year: int = 365,
) -> dict[str, Any]:
    """Compute comprehensive backtest metrics.

    Args:
        trades: List of completed trades.
        equity_curve: List of equity snapshots.
        initial_balance: Starting balance in KRW.
        risk_free_rate: Annual risk-free rate (default: 3.5% for KRW).
        trading_days_per_year: Trading days per year (crypto = 365).

    Returns:
        Dict with all performance metrics.
    """
    metrics: dict[str, Any] = {}

    # --- Return metrics ---
    equities = [e["equity"] for e in equity_curve] if equity_curve else [initial_balance]
    final_equity = equities[-1] if equities else initial_balance
    total_return = (final_equity - initial_balance) / initial_balance if initial_balance > 0 else 0

    # Duration
    n_bars = len(equity_curve)
    years = n_bars / trading_days_per_year / 24 if n_bars > 0 else 1  # Assuming hourly bars

    cagr = (final_equity / initial_balance) ** (1 / max(years, 0.01)) - 1 if initial_balance > 0 else 0

    metrics["total_return_pct"] = round(total_return * 100, 2)
    metrics["cagr_pct"] = round(cagr * 100, 2)
    metrics["final_equity"] = round(final_equity, 0)

    # --- Drawdown ---
    max_dd, max_dd_duration = _max_drawdown(equities)
    metrics["max_drawdown_pct"] = round(max_dd * 100, 2)
    metrics["max_drawdown_duration_bars"] = max_dd_duration
    metrics["calmar_ratio"] = round(cagr / abs(max_dd), 2) if max_dd != 0 else 0

    # --- Risk-adjusted returns ---
    daily_returns = _compute_returns(equities)
    sharpe = _sharpe_ratio(daily_returns, risk_free_rate, trading_days_per_year)
    sortino = _sortino_ratio(daily_returns, risk_free_rate, trading_days_per_year)
    metrics["sharpe_ratio"] = round(sharpe, 2)
    metrics["sortino_ratio"] = round(sortino, 2)

    # --- Trade metrics ---
    if trades:
        wins = [t for t in trades if t.pnl_krw > 0]
        losses = [t for t in trades if t.pnl_krw <= 0]

        metrics["total_trades"] = len(trades)
        metrics["winning_trades"] = len(wins)
        metrics["losing_trades"] = len(losses)
        metrics["win_rate_pct"] = round(len(wins) / len(trades) * 100, 1)

        total_profit = sum(t.pnl_krw for t in wins)
        total_loss = abs(sum(t.pnl_krw for t in losses))
        metrics["profit_factor"] = round(total_profit / total_loss, 2) if total_loss > 0 else float("inf")

        avg_win = total_profit / len(wins) if wins else 0
        avg_loss = total_loss / len(losses) if losses else 0
        metrics["avg_win_krw"] = round(avg_win, 0)
        metrics["avg_loss_krw"] = round(avg_loss, 0)
        metrics["avg_win_loss_ratio"] = round(avg_win / avg_loss, 2) if avg_loss > 0 else float("inf")

        pnls = [t.pnl_krw for t in trades]
        metrics["best_trade_krw"] = round(max(pnls), 0)
        metrics["worst_trade_krw"] = round(min(pnls), 0)

        # Consecutive wins/losses
        max_consec_wins, max_consec_losses = _max_consecutive(trades)
        metrics["max_consecutive_wins"] = max_consec_wins
        metrics["max_consecutive_losses"] = max_consec_losses

        # Average holding period
        durations = [(t.exit_time - t.entry_time).total_seconds() / 3600 for t in trades]
        metrics["avg_holding_hours"] = round(sum(durations) / len(durations), 1) if durations else 0
    else:
        metrics["total_trades"] = 0
        metrics["win_rate_pct"] = 0
        metrics["profit_factor"] = 0
        metrics["sharpe_ratio"] = 0

    return metrics


def _max_drawdown(equities: list[float]) -> tuple[float, int]:
    """Compute maximum drawdown and its duration in bars."""
    if not equities:
        return 0.0, 0

    peak = equities[0]
    max_dd = 0.0
    max_dd_duration = 0
    current_dd_start = 0

    for i, eq in enumerate(equities):
        if eq >= peak:
            peak = eq
            current_dd_start = i
        else:
            dd = (peak - eq) / peak
            if dd > max_dd:
                max_dd = dd
                max_dd_duration = i - current_dd_start

    return max_dd, max_dd_duration


def _compute_returns(equities: list[float]) -> list[float]:
    """Compute bar-to-bar returns."""
    if len(equities) < 2:
        return []
    return [
        (equities[i] - equities[i - 1]) / equities[i - 1]
        for i in range(1, len(equities))
        if equities[i - 1] > 0
    ]


def _sharpe_ratio(
    returns: list[float], risk_free_rate: float, periods_per_year: int
) -> float:
    """Annualized Sharpe ratio."""
    if not returns:
        return 0.0
    mean_r = sum(returns) / len(returns)
    std_r = _std(returns)
    if std_r == 0:
        return 0.0
    rf_per_period = risk_free_rate / periods_per_year
    return (mean_r - rf_per_period) / std_r * math.sqrt(periods_per_year)


def _sortino_ratio(
    returns: list[float], risk_free_rate: float, periods_per_year: int
) -> float:
    """Annualized Sortino ratio (downside deviation)."""
    if not returns:
        return 0.0
    mean_r = sum(returns) / len(returns)
    downside = [r for r in returns if r < 0]
    if not downside:
        return float("inf") if mean_r > 0 else 0.0
    downside_dev = _std(downside)
    if downside_dev == 0:
        return 0.0
    rf_per_period = risk_free_rate / periods_per_year
    return (mean_r - rf_per_period) / downside_dev * math.sqrt(periods_per_year)


def _std(values: list[float]) -> float:
    """Sample standard deviation."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def _max_consecutive(trades: list[BacktestTrade]) -> tuple[int, int]:
    """Find max consecutive wins and losses."""
    max_wins = 0
    max_losses = 0
    current_wins = 0
    current_losses = 0

    for t in trades:
        if t.pnl_krw > 0:
            current_wins += 1
            current_losses = 0
            max_wins = max(max_wins, current_wins)
        else:
            current_losses += 1
            current_wins = 0
            max_losses = max(max_losses, current_losses)

    return max_wins, max_losses
