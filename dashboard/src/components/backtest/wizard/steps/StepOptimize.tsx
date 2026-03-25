"use client";

import { useWizard } from "@/contexts/WizardContext";
import { useAsyncJob } from "@/hooks/useAsyncJob";
import { WizardNavButtons } from "../WizardNavButtons";
import { useCallback, useState } from "react";
import { cn } from "@/lib/cn";

export function StepOptimize() {
  const { state, dispatch } = useWizard();
  const [nTrials, setNTrials] = useState(30);

  const job = useAsyncJob({
    onComplete: (result) => {
      const opt = (result.optimization ?? result) as Record<string, unknown>;
      const candidates = (opt.candidates ?? []) as Record<string, unknown>[];
      const baseline = (opt.baseline ?? {}) as Record<string, unknown>;
      if (candidates.length === 0) {
        dispatch({ type: "SET_ERROR", error: "최적화 완료되었으나 유효한 후보가 없습니다. 기간이나 전략을 변경해 보세요." });
        dispatch({ type: "SET_LOADING", loading: false });
        return;
      }
      dispatch({ type: "SET_CANDIDATES", candidates, baseline });
      dispatch({ type: "SET_LOADING", loading: false });
    },
    onError: (err) => {
      dispatch({ type: "SET_ERROR", error: err });
    },
  });

  const startOptimize = useCallback(async () => {
    if (!state.selectedStrategy) return;

    // Derive date range from backtest result
    const result = state.backtestResult ?? {};
    const config = (result.config ?? {}) as Record<string, string>;
    const startDate = config.start_date ?? "2026-01-01";
    const endDate = config.end_date ?? "2026-03-25";

    dispatch({ type: "SET_LOADING", loading: true });
    dispatch({ type: "SET_ERROR", error: null });

    try {
      const res = await fetch("/api/engine/backtest/wizard/optimize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          strategy_id: state.selectedStrategy,
          start_date: startDate,
          end_date: endDate,
          n_trials: nTrials,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Optimization failed" }));
        throw new Error(err.detail ?? "Optimization failed");
      }
      const data = await res.json();
      dispatch({ type: "SET_OPTIMIZE_JOB", jobId: data.job_id });
      job.startPolling(data.job_id);
    } catch (e) {
      dispatch({
        type: "SET_ERROR",
        error: e instanceof Error ? e.message : "최적화 시작 실패",
      });
      dispatch({ type: "SET_LOADING", loading: false });
    }
  }, [state.selectedStrategy, state.backtestResult, nTrials, dispatch, job]);

  const hasResults = state.candidates.length > 0;

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h3 className="text-sm font-medium text-text-primary">파라미터 최적화</h3>
        <p className="mt-1 text-xs text-text-muted">
          Optuna 베이지안 최적화로 최적 파라미터를 탐색합니다.
          (Sharpe 40% + 수익률 30% + PF 20% + 1/MDD 10%)
        </p>
      </div>

      {/* Config & Start */}
      {!hasResults && !job.isRunning && (
        <div className="rounded-lg border border-border bg-bg-card p-4">
          <div className="flex items-center gap-4">
            <div>
              <label className="text-xs text-text-muted">시행 횟수</label>
              <select
                value={nTrials}
                onChange={(e) => setNTrials(Number(e.target.value))}
                className="mt-1 block w-24 rounded-lg border border-border bg-bg-secondary px-2 py-1.5 text-sm text-text-primary"
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={30}>30</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
            </div>
            <div className="flex-1">
              <div className="text-xs text-text-muted">대상 전략</div>
              <div className="mt-1 text-sm font-medium text-accent">
                {state.selectedStrategy}
              </div>
            </div>
          </div>
          <button
            onClick={startOptimize}
            className="mt-3 w-full rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent/90"
          >
            최적화 시작
          </button>
        </div>
      )}

      {/* Progress */}
      {job.isRunning && (
        <div className="rounded-lg border border-border bg-bg-card p-4">
          <div className="flex items-center gap-3">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-accent/30 border-t-accent" />
            <div>
              <div className="text-sm font-medium text-text-primary">
                최적화 진행 중...
              </div>
              <div className="text-xs text-text-muted">
                {job.progress || "시작 중..."} ({job.elapsed.toFixed(0)}s)
              </div>
            </div>
          </div>
          <div className="mt-3 h-1 overflow-hidden rounded-full bg-bg-secondary">
            <div className="h-full animate-pulse rounded-full bg-accent/50" style={{ width: "60%" }} />
          </div>
        </div>
      )}

      {/* Results */}
      {hasResults && (
        <>
          {/* Baseline comparison */}
          {state.baselineMetrics && (
            <div className="rounded-lg border border-border bg-bg-card p-3">
              <h4 className="text-xs font-medium text-text-muted">현재 (baseline)</h4>
              <div className="mt-1 flex gap-4 text-xs">
                {["return_pct", "sharpe_ratio", "win_rate", "mdd"].map((key) => {
                  const val = (state.baselineMetrics as Record<string, unknown>)?.[key];
                  if (val == null) return null;
                  return (
                    <span key={key} className="text-text-secondary">
                      {key.replace(/_/g, " ")}: {Number(val).toFixed(2)}
                    </span>
                  );
                })}
              </div>
            </div>
          )}

          {/* Candidate cards */}
          <div className="space-y-2">
            {state.candidates.map((c, i) => {
              const isSelected =
                state.selectedCandidate &&
                (state.selectedCandidate as Record<string, unknown>).rank === (c as Record<string, unknown>).rank;
              return (
                <button
                  key={i}
                  onClick={() =>
                    dispatch({ type: "SELECT_CANDIDATE", candidate: c })
                  }
                  className={cn(
                    "w-full rounded-lg border p-3 text-left transition-colors",
                    isSelected
                      ? "border-accent bg-accent/10"
                      : "border-border bg-bg-card hover:border-text-muted",
                  )}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-text-muted">
                      #{String((c as Record<string, unknown>).rank ?? i + 1)}
                    </span>
                    <span className="rounded bg-accent/10 px-1.5 py-0.5 text-xs font-medium text-accent">
                      score: {Number((c as Record<string, unknown>).score ?? 0).toFixed(2)}
                    </span>
                  </div>
                  <div className="mt-1 flex gap-3 text-xs">
                    <span>
                      수익률:{" "}
                      <span className={Number((c as Record<string, unknown>).return_pct) >= 0 ? "text-status-running" : "text-status-error"}>
                        {Number((c as Record<string, unknown>).return_pct ?? 0).toFixed(1)}%
                      </span>
                    </span>
                    <span>Sharpe: {Number((c as Record<string, unknown>).sharpe_ratio ?? 0).toFixed(2)}</span>
                    <span>MDD: {Number((c as Record<string, unknown>).mdd ?? 0).toFixed(1)}%</span>
                    <span>거래: {String((c as Record<string, unknown>).trades ?? 0)}</span>
                  </div>
                </button>
              );
            })}
          </div>
        </>
      )}

      <WizardNavButtons
        nextDisabled={!hasResults || !state.selectedCandidate}
      />
    </div>
  );
}
