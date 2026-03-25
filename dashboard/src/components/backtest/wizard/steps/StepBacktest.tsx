"use client";

import { useWizard } from "@/contexts/WizardContext";
import { WizardNavButtons } from "../WizardNavButtons";
import { useCallback, useEffect, useState } from "react";
import { cn } from "@/lib/cn";

interface JobSummary {
  job_id: string;
  mode: string;
  status: string;
  start_date: string;
  end_date: string;
  created_at: string;
  summary: Record<string, unknown> | null;
}

export function StepBacktest() {
  const { state, dispatch } = useWizard();
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchJobs() {
      try {
        const res = await fetch("/api/engine/backtest/jobs?limit=20");
        if (!res.ok) return;
        const data = await res.json();
        const completed = (data.jobs ?? []).filter(
          (j: JobSummary) => j.status === "done",
        );
        setJobs(completed);
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    }
    fetchJobs();
  }, []);

  const selectJob = useCallback(
    async (job: JobSummary) => {
      dispatch({ type: "SET_LOADING", loading: true });
      try {
        const res = await fetch(`/api/engine/backtest/jobs/${job.job_id}`);
        if (!res.ok) throw new Error("Failed to load job");
        const data = await res.json();

        // Extract strategy from result
        const result = data.result ?? {};
        const strategyId =
          result.optimization?.strategy_id ??
          result.strategies?.[0]?.strategy_id ??
          job.summary?.best_strategy ??
          "STR-001";

        dispatch({
          type: "SET_BACKTEST",
          jobId: job.job_id,
          strategy: String(strategyId),
          result,
        });
      } catch (e) {
        dispatch({
          type: "SET_ERROR",
          error: e instanceof Error ? e.message : "Failed to load job",
        });
      } finally {
        dispatch({ type: "SET_LOADING", loading: false });
      }
    },
    [dispatch],
  );

  const handleNext = useCallback(() => {
    if (!state.selectedJobId) {
      dispatch({ type: "SET_ERROR", error: "백테스트를 선택해주세요" });
      return;
    }
    dispatch({ type: "NEXT_STEP" });
  }, [state.selectedJobId, dispatch]);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h3 className="text-sm font-medium text-text-primary">
          완료된 백테스트 선택
        </h3>
        <p className="mt-1 text-xs text-text-muted">
          분석할 백테스트 결과를 선택하세요. 이 결과를 기반으로 최적화를
          진행합니다.
        </p>
      </div>

      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-16 animate-pulse rounded-lg bg-bg-secondary"
            />
          ))}
        </div>
      ) : jobs.length === 0 ? (
        <div className="rounded-lg border border-border bg-bg-secondary p-6 text-center text-sm text-text-muted">
          완료된 백테스트가 없습니다. 먼저 백테스트를 실행해주세요.
        </div>
      ) : (
        <div className="space-y-2">
          {jobs.map((job) => {
            const isSelected = state.selectedJobId === job.job_id;
            const summary = job.summary as Record<string, unknown> | null;
            return (
              <button
                key={job.job_id}
                onClick={() => selectJob(job)}
                className={cn(
                  "w-full rounded-lg border p-3 text-left transition-colors",
                  isSelected
                    ? "border-accent bg-accent/10"
                    : "border-border bg-bg-card hover:border-text-muted",
                )}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-bg-secondary px-1.5 py-0.5 text-xs font-mono text-text-muted">
                      {job.mode}
                    </span>
                    <span className="text-sm font-medium text-text-primary">
                      {job.start_date} ~ {job.end_date}
                    </span>
                  </div>
                  <span className="text-xs text-text-muted">
                    {new Date(job.created_at).toLocaleString("ko-KR", {
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </div>
                {summary && (
                  <div className="mt-1 flex gap-3 text-xs text-text-muted">
                    {summary.best_return_pct != null && (
                      <span>
                        수익률:{" "}
                        <span
                          className={
                            Number(summary.best_return_pct) >= 0
                              ? "text-status-running"
                              : "text-status-error"
                          }
                        >
                          {Number(summary.best_return_pct).toFixed(1)}%
                        </span>
                      </span>
                    )}
                    {summary.best_strategy != null && (
                      <span>전략: {String(summary.best_strategy)}</span>
                    )}
                    {summary.return_pct != null && (
                      <span>
                        수익률:{" "}
                        <span
                          className={
                            Number(summary.return_pct) >= 0
                              ? "text-status-running"
                              : "text-status-error"
                          }
                        >
                          {Number(summary.return_pct).toFixed(1)}%
                        </span>
                      </span>
                    )}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      )}

      <WizardNavButtons
        onNext={handleNext}
        nextDisabled={!state.selectedJobId}
      />
    </div>
  );
}
