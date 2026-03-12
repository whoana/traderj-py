"use client";

import type { BacktestResult } from "@/types/api";
import { formatKRW, formatPercent } from "@/lib/format";

interface BacktestResultListProps {
  results: BacktestResult[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function BacktestResultList({
  results,
  selectedId,
  onSelect,
}: BacktestResultListProps) {
  if (results.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-[var(--color-text-secondary)]">
        No backtest results
      </p>
    );
  }

  return (
    <div className="space-y-1 overflow-y-auto">
      {results.map((r) => (
        <button
          key={r.id}
          onClick={() => onSelect(r.id)}
          className={`w-full rounded-lg border px-4 py-3 text-left transition-colors ${
            selectedId === r.id
              ? "border-[var(--color-accent-blue)] bg-[var(--color-bg-tertiary)]"
              : "border-[var(--color-border)] hover:bg-[var(--color-bg-secondary)]"
          }`}
        >
          <div className="text-sm font-medium">{r.strategy_id}</div>
          <div className="mt-1 flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
            <span>{r.timeframe}</span>
            <span>{r.period}</span>
          </div>
          <div className="mt-1 flex items-center gap-3 text-xs">
            <span
              className={
                r.summary.total_pnl >= 0
                  ? "text-[var(--color-pnl-positive)]"
                  : "text-[var(--color-pnl-negative)]"
              }
            >
              {formatKRW(r.summary.total_pnl)}
            </span>
            <span className="text-[var(--color-text-secondary)]">
              WR {formatPercent(r.summary.win_rate)}
            </span>
          </div>
        </button>
      ))}
    </div>
  );
}
