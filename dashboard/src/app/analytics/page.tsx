"use client";

import { useEffect, useState } from "react";

import { fetchPnLAnalytics, fetchStrategyCompare, fetchPnLSummary } from "@/lib/api";
import type { PnLAnalyticsResponse, StrategyCompareResponse, PnLSummaryResponse } from "@/types/api";
import { formatKRW, formatPercent } from "@/lib/format";

export default function AnalyticsPage() {
  const [analytics, setAnalytics] = useState<PnLAnalyticsResponse | null>(null);
  const [compare, setCompare] = useState<StrategyCompareResponse | null>(null);
  const [summaries, setSummaries] = useState<PnLSummaryResponse[]>([]);
  const [strategyId, setStrategyId] = useState("STR-001");
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, [strategyId, days]);

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const [pnl, summary] = await Promise.all([
        fetchPnLAnalytics(strategyId, days),
        fetchPnLSummary(),
      ]);
      setAnalytics(pnl);
      setSummaries(summary);

      if (summary.length > 1) {
        const ids = summary.map((s) => s.strategy_id);
        const cmp = await fetchStrategyCompare(ids, days);
        setCompare(cmp);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-7xl p-4">
      <h1 className="mb-6 text-2xl font-bold">Analytics</h1>

      {/* Controls */}
      <div className="mb-6 flex items-center gap-4">
        <label className="text-sm text-[var(--color-text-secondary)]">
          Strategy:
          <input
            type="text"
            value={strategyId}
            onChange={(e) => setStrategyId(e.target.value)}
            className="ml-2 rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-3 py-1.5 text-sm"
          />
        </label>
        <label className="text-sm text-[var(--color-text-secondary)]">
          Days:
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="ml-2 rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-3 py-1.5 text-sm"
          >
            <option value={7}>7</option>
            <option value={14}>14</option>
            <option value={30}>30</option>
            <option value={90}>90</option>
          </select>
        </label>
      </div>

      {loading && <p className="text-sm text-[var(--color-text-secondary)]">Loading...</p>}
      {error && <p className="text-sm text-red-500">{error}</p>}

      {/* Summary Cards */}
      {analytics && (
        <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
          <SummaryCard label="Total PnL" value={formatKRW(Number(analytics.total_pnl))} />
          <SummaryCard label="Max Drawdown" value={formatKRW(Number(analytics.max_drawdown))} negative />
          <SummaryCard label="Peak PnL" value={formatKRW(Number(analytics.peak_pnl))} />
          <SummaryCard label="Total Trades" value={String(analytics.total_trades)} />
        </div>
      )}

      {/* Equity Curve Table */}
      {analytics && analytics.curve.length > 0 && (
        <div className="mb-6 overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)]">
          <h2 className="border-b border-[var(--color-border)] px-4 py-3 text-sm font-medium">
            Equity Curve ({analytics.curve.length} days)
          </h2>
          <div className="max-h-80 overflow-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--color-bg-primary)] text-left text-xs text-[var(--color-text-secondary)]">
                <tr>
                  <th className="px-4 py-2">Date</th>
                  <th className="px-4 py-2 text-right">Daily PnL</th>
                  <th className="px-4 py-2 text-right">Cumulative</th>
                  <th className="px-4 py-2 text-right">Drawdown</th>
                  <th className="px-4 py-2 text-right">Trades</th>
                </tr>
              </thead>
              <tbody>
                {analytics.curve.map((row) => (
                  <tr key={row.date} className="border-t border-[var(--color-border)]">
                    <td className="px-4 py-2">{row.date}</td>
                    <td className={`px-4 py-2 text-right ${Number(row.daily_pnl) >= 0 ? "text-[var(--color-pnl-positive)]" : "text-[var(--color-pnl-negative)]"}`}>
                      {formatKRW(Number(row.daily_pnl))}
                    </td>
                    <td className="px-4 py-2 text-right">{formatKRW(Number(row.cumulative_pnl))}</td>
                    <td className="px-4 py-2 text-right text-[var(--color-pnl-negative)]">
                      {Number(row.drawdown) > 0 ? `-${formatKRW(Number(row.drawdown))}` : "-"}
                    </td>
                    <td className="px-4 py-2 text-right">{row.trade_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Strategy Comparison */}
      {compare && compare.strategies.length > 1 && (
        <div className="overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)]">
          <h2 className="border-b border-[var(--color-border)] px-4 py-3 text-sm font-medium">
            Strategy Comparison
          </h2>
          <table className="w-full text-sm">
            <thead className="bg-[var(--color-bg-primary)] text-left text-xs text-[var(--color-text-secondary)]">
              <tr>
                <th className="px-4 py-2">Strategy</th>
                <th className="px-4 py-2 text-right">Total PnL</th>
                <th className="px-4 py-2 text-right">Trades</th>
                <th className="px-4 py-2 text-right">Avg Daily</th>
                <th className="px-4 py-2 text-right">Sharpe</th>
              </tr>
            </thead>
            <tbody>
              {compare.strategies.map((s) => (
                <tr key={s.strategy_id} className="border-t border-[var(--color-border)]">
                  <td className="px-4 py-2 font-medium">{s.strategy_id}</td>
                  <td className={`px-4 py-2 text-right ${Number(s.total_pnl) >= 0 ? "text-[var(--color-pnl-positive)]" : "text-[var(--color-pnl-negative)]"}`}>
                    {formatKRW(Number(s.total_pnl))}
                  </td>
                  <td className="px-4 py-2 text-right">{s.total_trades}</td>
                  <td className="px-4 py-2 text-right">{formatKRW(Number(s.avg_daily_pnl))}</td>
                  <td className="px-4 py-2 text-right">{s.sharpe_ratio.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function SummaryCard({ label, value, negative }: { label: string; value: string; negative?: boolean }) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
      <p className="text-xs text-[var(--color-text-secondary)]">{label}</p>
      <p className={`mt-1 text-lg font-semibold ${negative ? "text-[var(--color-pnl-negative)]" : ""}`}>
        {value}
      </p>
    </div>
  );
}
