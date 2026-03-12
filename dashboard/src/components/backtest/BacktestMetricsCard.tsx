"use client";

import type { BacktestResult } from "@/types/api";
import { formatKRW, formatPercent } from "@/lib/format";

interface BacktestMetricsCardProps {
  summary: BacktestResult["summary"];
}

export function BacktestMetricsCard({ summary }: BacktestMetricsCardProps) {
  const metrics = [
    { label: "Sharpe Ratio", value: summary.sharpe.toFixed(2) },
    { label: "Sortino Ratio", value: summary.sortino.toFixed(2) },
    { label: "Max Drawdown", value: formatKRW(summary.max_drawdown), negative: true },
    { label: "Calmar Ratio", value: summary.calmar.toFixed(2) },
    { label: "Win Rate", value: formatPercent(summary.win_rate) },
    { label: "Profit Factor", value: summary.profit_factor.toFixed(2) },
    { label: "Total Trades", value: String(summary.total_trades) },
    { label: "Total PnL", value: formatKRW(summary.total_pnl), pnl: true },
  ];

  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
      {metrics.map((m) => (
        <div
          key={m.label}
          className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4"
        >
          <p className="text-xs text-[var(--color-text-secondary)]">{m.label}</p>
          <p
            className={`mt-1 text-lg font-semibold ${
              m.negative
                ? "text-[var(--color-pnl-negative)]"
                : m.pnl && summary.total_pnl >= 0
                  ? "text-[var(--color-pnl-positive)]"
                  : m.pnl && summary.total_pnl < 0
                    ? "text-[var(--color-pnl-negative)]"
                    : ""
            }`}
          >
            {m.value}
          </p>
        </div>
      ))}
    </div>
  );
}
