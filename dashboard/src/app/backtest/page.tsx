"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";

import { useBacktestStore } from "@/stores/useBacktestStore";
import { BacktestMetricsCard } from "@/components/backtest/BacktestMetricsCard";
import { BacktestTradeList } from "@/components/backtest/BacktestTradeList";
import { BacktestResultList } from "@/components/backtest/BacktestResultList";

const BacktestEquityCurve = dynamic(
  () =>
    import("@/components/backtest/BacktestEquityCurve").then(
      (m) => m.BacktestEquityCurve,
    ),
  { ssr: false },
);

export default function BacktestPage() {
  const [strategyId, setStrategyId] = useState("STR-001");
  const { results, selectedId, loading, error, fetch, selectResult } =
    useBacktestStore();

  useEffect(() => {
    fetch(strategyId);
  }, [strategyId, fetch]);

  const selected = results.find((r) => r.id === selectedId);

  return (
    <div className="mx-auto max-w-7xl p-4">
      <h1 className="mb-6 text-2xl font-bold">Backtest</h1>

      {/* Strategy Selector */}
      <div className="mb-6">
        <label className="text-sm text-[var(--color-text-secondary)]">
          Strategy:
          <input
            type="text"
            value={strategyId}
            onChange={(e) => setStrategyId(e.target.value)}
            className="ml-2 rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-3 py-1.5 text-sm"
          />
        </label>
      </div>

      {loading && (
        <p className="text-sm text-[var(--color-text-secondary)]">Loading...</p>
      )}
      {error && <p className="text-sm text-red-500">{error}</p>}

      {/* Two-column layout */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
        {/* Sidebar */}
        <div className="lg:col-span-1">
          <BacktestResultList
            results={results}
            selectedId={selectedId}
            onSelect={selectResult}
          />
        </div>

        {/* Main */}
        <div className="space-y-4 lg:col-span-3">
          {selected ? (
            <>
              <BacktestMetricsCard summary={selected.summary} />
              <BacktestEquityCurve data={selected.equity_curve} />
              <BacktestTradeList trades={selected.trades} />
            </>
          ) : (
            !loading && (
              <div className="flex h-64 items-center justify-center text-sm text-[var(--color-text-secondary)]">
                Select a backtest result to view details
              </div>
            )
          )}
        </div>
      </div>
    </div>
  );
}
