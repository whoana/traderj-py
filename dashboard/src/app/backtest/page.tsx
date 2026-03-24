"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import dynamic from "next/dynamic";

const EquityCurveChart = dynamic(
  () => import("@/components/backtest/EquityCurveChart"),
  { ssr: false },
);
import ActionPanel from "@/components/backtest/ActionPanel";
import BacktestHistory from "@/components/backtest/BacktestHistory";

type Mode = "compare" | "single" | "ai_regime";
type JobStatus = "idle" | "pending" | "fetching" | "running" | "done" | "failed" | "cancelled";

interface JobData {
  job_id: string;
  status: string;
  mode: Mode;
  progress: string;
  elapsed_sec: number;
  error?: string | null;
  result?: Record<string, unknown> | null;
}

interface HistoryItem {
  job_id: string;
  mode: Mode;
  status: string;
  start_date: string;
  end_date: string;
  created_at: string;
  summary?: Record<string, unknown> | null;
}

const PRESETS = [
  { id: "STR-001", name: "Conservative Trend (4h)" },
  { id: "STR-002", name: "Aggressive Trend (1h)" },
  { id: "STR-003", name: "Hybrid Reversal (4h/1d)" },
  { id: "STR-004", name: "Majority Vote Trend" },
  { id: "STR-005", name: "Low-Frequency Hybrid" },
  { id: "STR-006", name: "Scalper (1h/4h)" },
  { id: "STR-007", name: "Bear Defensive (1d)" },
  { id: "STR-008", name: "Bear Cautious Reversal (4h/1d)" },
];

const MODE_LABELS: Record<Mode, string> = {
  compare: "전략 비교",
  single: "단일 전략",
  ai_regime: "AI Regime",
};

function getQuickPeriod(months: number): { start: string; end: string } {
  const end = new Date();
  end.setDate(end.getDate() - 1); // yesterday
  const start = new Date(end);
  start.setMonth(start.getMonth() - months);
  start.setDate(start.getDate() + 1);
  return {
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
  };
}

export default function BacktestPage() {
  // ── Form state ──
  const [mode, setMode] = useState<Mode>("compare");
  const [startDate, setStartDate] = useState(() => getQuickPeriod(1).start);
  const [endDate, setEndDate] = useState(() => getQuickPeriod(1).end);
  const [strategyId, setStrategyId] = useState("STR-001");
  const [initialBalance, setInitialBalance] = useState(50_000_000);

  // ── Job state ──
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus>("idle");
  const [progress, setProgress] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  // ── History ──
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [showHistory, setShowHistory] = useState(false);

  // ── Load history on mount ──
  useEffect(() => {
    fetch("/api/engine/backtest/jobs?limit=10")
      .then((r) => r.json())
      .then((d) => setHistory(d.jobs || []))
      .catch(() => {});
  }, []);

  // ── Poll job status ──
  useEffect(() => {
    if (!jobId || status === "done" || status === "failed" || status === "cancelled" || status === "idle") return;

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/engine/backtest/jobs/${jobId}`);
        const data: JobData = await res.json();
        setStatus(data.status as JobStatus);
        setProgress(data.progress);
        setElapsed(data.elapsed_sec);

        if (data.status === "done" && data.result) {
          setResult(data.result as Record<string, unknown>);
          refreshHistory();
        }
        if (data.status === "failed") {
          setError(data.error || "Unknown error");
          refreshHistory();
        }
      } catch {}
    }, 3000);

    return () => clearInterval(interval);
  }, [jobId, status]);

  const refreshHistory = useCallback(() => {
    fetch("/api/engine/backtest/jobs?limit=10")
      .then((r) => r.json())
      .then((d) => setHistory(d.jobs || []))
      .catch(() => {});
  }, []);

  // ── View result from history ──
  const handleViewResult = useCallback(async (historyJobId: string) => {
    try {
      const res = await fetch(`/api/engine/backtest/jobs/${historyJobId}`);
      const data = await res.json();
      if (data.status === "done" && data.result) {
        setJobId(historyJobId);
        setResult(data.result as Record<string, unknown>);
        setStatus("done");
        setError(null);
      }
    } catch {}
  }, []);

  // ── Quick period buttons ──
  const setQuickPeriod = (months: number) => {
    const p = getQuickPeriod(months);
    setStartDate(p.start);
    setEndDate(p.end);
  };

  // ── Submit ──
  const handleRun = async () => {
    setStatus("pending");
    setError(null);
    setResult(null);
    setProgress("");
    setElapsed(0);

    try {
      const body: Record<string, unknown> = {
        mode,
        start_date: startDate,
        end_date: endDate,
        initial_balance: initialBalance,
      };
      if (mode === "single") body.strategy_id = strategyId;

      const res = await fetch("/api/engine/backtest/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Request failed");
      }
      const data: JobData = await res.json();
      setJobId(data.job_id);
      setStatus(data.status as JobStatus);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
      setStatus("failed");
    }
  };

  // ── Cancel ──
  const handleCancel = async () => {
    if (!jobId) return;
    await fetch(`/api/engine/backtest/jobs/${jobId}`, { method: "DELETE" }).catch(() => {});
    setStatus("cancelled");
  };

  const isRunning = status === "pending" || status === "fetching" || status === "running";
  const periodDays = Math.max(0, Math.round((new Date(endDate).getTime() - new Date(startDate).getTime()) / 86400000) + 1);

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-3 sm:p-6">
      <h1 className="text-lg font-bold text-text-primary sm:text-xl">Backtest</h1>

      {/* ── Settings Card ── */}
      <div className="rounded-lg border border-border bg-bg-card p-4 space-y-4">
        {/* Period */}
        <div>
          <label className="mb-1.5 block text-xs font-medium text-text-muted">기간</label>
          <div className="mb-2 flex flex-wrap gap-1.5">
            {[1, 3, 6, 12].map((m) => (
              <button
                key={m}
                onClick={() => setQuickPeriod(m)}
                className="rounded-md border border-border bg-bg-primary px-3 py-1 text-xs text-text-secondary transition-colors hover:border-accent hover:text-accent"
              >
                {m >= 12 ? `${m / 12}Y` : `${m}M`}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="rounded-md border border-border bg-bg-primary px-3 py-1.5 text-sm text-text-primary"
            />
            <span className="text-text-muted">~</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="rounded-md border border-border bg-bg-primary px-3 py-1.5 text-sm text-text-primary"
            />
            <span className="text-xs text-text-muted">({periodDays}일)</span>
          </div>
        </div>

        {/* Mode */}
        <div>
          <label className="mb-1.5 block text-xs font-medium text-text-muted">모드</label>
          <div className="flex gap-2">
            {(["compare", "single", "ai_regime"] as Mode[]).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
                  mode === m
                    ? "border-accent bg-accent-dim text-accent"
                    : "border-border bg-bg-primary text-text-secondary hover:border-accent/50"
                }`}
              >
                {MODE_LABELS[m]}
              </button>
            ))}
          </div>
        </div>

        {/* Strategy (single mode only) */}
        {mode === "single" && (
          <div>
            <label className="mb-1.5 block text-xs font-medium text-text-muted">전략</label>
            <select
              value={strategyId}
              onChange={(e) => setStrategyId(e.target.value)}
              className="w-full rounded-md border border-border bg-bg-primary px-3 py-1.5 text-sm text-text-primary"
            >
              {PRESETS.map((p) => (
                <option key={p.id} value={p.id}>{p.id} {p.name}</option>
              ))}
            </select>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-3">
          <button
            onClick={handleRun}
            disabled={isRunning || periodDays < 7 || periodDays > 180}
            className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent/90 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isRunning ? "실행 중..." : "백테스트 실행"}
          </button>
          {isRunning && (
            <button
              onClick={handleCancel}
              className="rounded-md border border-border px-3 py-2 text-xs text-text-muted hover:text-text-primary"
            >
              취소
            </button>
          )}
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="ml-auto rounded-md border border-border px-3 py-2 text-xs text-text-muted hover:text-text-primary"
          >
            히스토리 {showHistory ? "▲" : "▼"}
          </button>
        </div>
        {periodDays < 7 && <p className="text-[10px] text-status-error">최소 7일 이상</p>}
        {periodDays > 180 && <p className="text-[10px] text-status-error">최대 180일 이하</p>}
      </div>

      {/* ── Progress ── */}
      {isRunning && (
        <div className="rounded-lg border border-border bg-bg-card p-4">
          <div className="mb-2 flex items-center justify-between text-xs text-text-muted">
            <span>{progress || "준비 중..."}</span>
            <span>{elapsed.toFixed(1)}s</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-bg-primary">
            <div className="h-full animate-pulse rounded-full bg-accent/60" style={{ width: "100%" }} />
          </div>
        </div>
      )}

      {/* ── Error ── */}
      {status === "failed" && error && (
        <div className="rounded-lg border border-status-error/30 bg-status-error/10 p-3 text-sm text-status-error">
          {error}
        </div>
      )}

      {/* ── Result ── */}
      {status === "done" && result && <BacktestResult data={result} />}

      {/* ── Action Panel ── */}
      {status === "done" && jobId && <ActionPanel jobId={jobId} />}

      {/* ── History ── */}
      {showHistory && (
        <div className="rounded-lg border border-border bg-bg-card p-4">
          <h3 className="mb-3 text-sm font-medium text-text-primary">백테스트 히스토리</h3>
          <BacktestHistory items={history} onViewResult={handleViewResult} />
        </div>
      )}
    </div>
  );
}

/* ── Result Display ── */

interface ResultPeriod { start: string; end: string; days: number }
interface ResultMarket { start_price: number; end_price: number; change_pct: number }
interface ResultMetrics { total_return_pct?: number; total_trades?: number; win_rate_pct?: number; sharpe_ratio?: number; profit_factor?: number | null; max_drawdown_pct?: number; [k: string]: unknown }
interface EquityPoint { time: string; equity: number }
interface ResultStrategy { strategy_id: string; name: string; metrics?: ResultMetrics; equity_curve?: EquityPoint[]; trades?: ResultTrade[]; error?: string }
interface ResultTrade { entry_time: string; exit_time: string; pnl_pct: number; exit_reason: string; [k: string]: unknown }
interface WeekDecision { week: number; start: string; end: string; regime: string; preset: string; name: string; return_pct: number; trades: number }
interface AiRegimeData { weekly_decisions: WeekDecision[]; regime_distribution: Record<string, number>; strategy_usage: Record<string, number>; aggregate_metrics: ResultMetrics; equity_curve: EquityPoint[]; trades: ResultTrade[] }
interface ResultData { mode: string; period: ResultPeriod; market?: ResultMarket; strategies: ResultStrategy[]; ranking?: string[]; ai_regime?: AiRegimeData }

function BacktestResult({ data }: { data: Record<string, unknown> }) {
  const d = data as unknown as ResultData;
  const mode = d.mode;
  const period = d.period;
  const market = d.market;
  const strategies = d.strategies || [];
  const aiRegime = d.ai_regime;

  return (
    <div className="space-y-4">
      {/* Market Summary */}
      {market && market.start_price != null && (
        <div className="rounded-lg border border-border bg-bg-card p-4">
          <h3 className="mb-2 text-sm font-medium text-text-primary">시장 요약</h3>
          <div className="flex flex-wrap gap-4 text-xs">
            <span className="text-text-secondary">
              BTC/KRW {market.start_price.toLocaleString()} → {market.end_price.toLocaleString()}
            </span>
            <span className={market.change_pct >= 0 ? "text-status-running" : "text-status-error"}>
              {market.change_pct >= 0 ? "+" : ""}{market.change_pct.toFixed(1)}%
            </span>
            <span className="text-text-muted">{period.start} ~ {period.end} ({period.days}일)</span>
          </div>
        </div>
      )}

      {/* Equity Curve Chart */}
      <EquityCurveChart
        mode={mode as "compare" | "single" | "ai_regime"}
        strategies={strategies}
        aiEquity={aiRegime?.equity_curve}
        initialBalance={50_000_000}
      />

      {/* AI Regime Timeline */}
      {aiRegime && (
        <div className="rounded-lg border border-border bg-bg-card p-4">
          <h3 className="mb-3 text-sm font-medium text-text-primary">AI 레짐 타임라인</h3>
          <div className="space-y-1">
            {(aiRegime.weekly_decisions || []).map((w) => {
              const isBull = w.regime.includes("bull");
              const isBear = w.regime.includes("bear");
              return (
                <div key={w.week} className="flex items-center gap-2 text-xs">
                  <span className="w-8 font-medium text-text-muted">W{w.week}</span>
                  <span className="w-20 text-text-muted">{w.start}~{w.end}</span>
                  <span className={`w-3 h-3 rounded-sm ${isBull ? "bg-status-running/60" : isBear ? "bg-status-error/60" : "bg-text-muted/30"}`} />
                  <span className="w-40 truncate text-text-secondary">{w.regime}</span>
                  <span className="text-text-primary">{w.preset} {w.name}</span>
                  <span className={`ml-auto font-mono ${w.return_pct >= 0 ? "text-status-running" : "text-status-error"}`}>
                    {w.return_pct >= 0 ? "+" : ""}{w.return_pct.toFixed(2)}%
                  </span>
                </div>
              );
            })}
          </div>
          {/* AI aggregate */}
          {aiRegime.aggregate_metrics && (
            <div className="mt-3 border-t border-border/50 pt-3 flex flex-wrap gap-4 text-xs">
              <span className="font-medium text-text-primary">AI 종합:</span>
              <MetricPill label="수익률" value={`${Number(aiRegime.aggregate_metrics.total_return_pct ?? 0).toFixed(2)}%`} />
              <MetricPill label="거래" value={String(aiRegime.aggregate_metrics.total_trades ?? 0)} />
              <MetricPill label="승률" value={`${Number(aiRegime.aggregate_metrics.win_rate_pct ?? 0).toFixed(1)}%`} />
              <MetricPill label="MDD" value={`${Number(aiRegime.aggregate_metrics.max_drawdown_pct ?? 0).toFixed(2)}%`} />
            </div>
          )}
        </div>
      )}

      {/* Strategy Ranking Table */}
      {strategies.length > 0 && (
        <div className="rounded-lg border border-border bg-bg-card p-4 overflow-x-auto">
          <h3 className="mb-3 text-sm font-medium text-text-primary">
            {mode === "single" ? "전략 결과" : "전략 비교 랭킹"}
          </h3>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border text-left text-text-muted">
                <th className="pb-2 pr-2">#</th>
                <th className="pb-2 pr-2">전략</th>
                <th className="pb-2 pr-2 text-right">수익률</th>
                <th className="pb-2 pr-2 text-right">거래</th>
                <th className="pb-2 pr-2 text-right">승률</th>
                <th className="pb-2 pr-2 text-right">Sharpe</th>
                <th className="pb-2 pr-2 text-right">PF</th>
                <th className="pb-2 text-right">MDD</th>
              </tr>
            </thead>
            <tbody>
              {strategies.map((s, i) => {
                const m = s.metrics || {} as ResultMetrics;
                const ret = Number(m.total_return_pct ?? 0);
                return (
                  <tr key={s.strategy_id} className="border-b border-border/30">
                    <td className="py-1.5 pr-2 text-text-muted">{i + 1}</td>
                    <td className="py-1.5 pr-2 text-text-primary font-medium">
                      {s.strategy_id}
                      <span className="ml-1.5 text-text-muted font-normal">{s.name}</span>
                    </td>
                    <td className={`py-1.5 pr-2 text-right font-mono ${ret >= 0 ? "text-status-running" : "text-status-error"}`}>
                      {ret >= 0 ? "+" : ""}{ret.toFixed(2)}%
                    </td>
                    <td className="py-1.5 pr-2 text-right text-text-secondary">{String(m.total_trades ?? 0)}</td>
                    <td className="py-1.5 pr-2 text-right text-text-secondary">{Number(m.win_rate_pct ?? 0).toFixed(1)}%</td>
                    <td className="py-1.5 pr-2 text-right text-text-secondary">{Number(m.sharpe_ratio ?? 0).toFixed(2)}</td>
                    <td className="py-1.5 pr-2 text-right text-text-secondary">{m.profit_factor != null ? Number(m.profit_factor).toFixed(2) : "-"}</td>
                    <td className="py-1.5 text-right text-text-secondary">{Number(m.max_drawdown_pct ?? 0).toFixed(2)}%</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Trade List (single & ai_regime) */}
      {(mode === "single" || mode === "ai_regime") && <TradeList data={data} />}
    </div>
  );
}

function TradeList({ data }: { data: Record<string, unknown> }) {
  const [open, setOpen] = useState(false);
  const d = data as unknown as ResultData;

  let trades: ResultTrade[] = [];
  if (d.mode === "ai_regime" && d.ai_regime) {
    trades = d.ai_regime.trades || [];
  } else if (d.strategies?.[0]?.trades) {
    trades = d.strategies[0].trades;
  }

  if (trades.length === 0) return null;
  const wins = trades.filter((t) => t.pnl_pct > 0).length;

  return (
    <div className="rounded-lg border border-border bg-bg-card p-4">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center justify-between text-sm font-medium text-text-primary">
        <span>거래 목록 ({trades.length}건, {wins}승 {trades.length - wins}패)</span>
        <svg className={`h-4 w-4 text-text-muted transition-transform ${open ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <div className="mt-3 space-y-1">
          {trades.map((t, i) => (
            <div key={i} className="flex items-center gap-2 text-[10px] sm:text-xs">
              <span className="w-6 text-text-muted">#{i + 1}</span>
              <span className="w-28 text-text-secondary">{t.entry_time.slice(5, 16)}</span>
              <span className="text-text-muted">→</span>
              <span className="w-28 text-text-secondary">{t.exit_time.slice(5, 16)}</span>
              <span className={`w-16 text-right font-mono ${t.pnl_pct >= 0 ? "text-status-running" : "text-status-error"}`}>
                {t.pnl_pct >= 0 ? "+" : ""}{t.pnl_pct.toFixed(2)}%
              </span>
              <span className="text-text-muted">{t.exit_reason}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function MetricPill({ label, value }: { label: string; value: string }) {
  return (
    <span className="text-text-secondary">
      <span className="text-text-muted">{label}:</span> {value}
    </span>
  );
}
