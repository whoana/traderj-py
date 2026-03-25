"use client";

import { useWizard } from "@/contexts/WizardContext";
import { useAsyncJob } from "@/hooks/useAsyncJob";
import { WizardNavButtons } from "../WizardNavButtons";
import { useCallback, useEffect } from "react";
import { cn } from "@/lib/cn";

export function StepValidate() {
  const { state, dispatch } = useWizard();

  const job = useAsyncJob({
    pollInterval: 3000,
    onComplete: (result) => {
      dispatch({ type: "SET_VALIDATION", result: result.validation as Record<string, unknown> ?? result });
      dispatch({ type: "SET_LOADING", loading: false });
    },
    onError: (err) => {
      dispatch({ type: "SET_ERROR", error: err });
    },
  });

  // Auto-start validation on mount
  useEffect(() => {
    if (state.validationResult || job.isRunning || job.jobId) return;

    const candidate = state.selectedCandidate as Record<string, unknown> | null;
    const params = (candidate?.params ?? {}) as Record<string, number>;
    if (!state.selectedStrategy || Object.keys(params).length === 0) return;

    const result = state.backtestResult ?? {};
    const config = (result.config ?? {}) as Record<string, string>;

    async function startValidation() {
      dispatch({ type: "SET_LOADING", loading: true });
      try {
        // Build baseline from analysis
        const baseline = (state.baselineMetrics ?? {}) as Record<string, unknown>;

        const res = await fetch("/api/engine/backtest/wizard/validate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            strategy_id: state.selectedStrategy,
            params,
            start_date: config.start_date ?? "2026-01-01",
            end_date: config.end_date ?? "2026-03-25",
            baseline_metrics: baseline,
          }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: "Validation request failed" }));
          throw new Error(err.detail ?? "검증 시작 실패");
        }
        const data = await res.json();
        dispatch({ type: "SET_VALIDATE_JOB", jobId: data.job_id });
        job.startPolling(data.job_id);
      } catch (e) {
        dispatch({
          type: "SET_ERROR",
          error: e instanceof Error ? e.message : "검증 시작 실패",
        });
        dispatch({ type: "SET_LOADING", loading: false });
      }
    }
    startValidation();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const validation = state.validationResult as Record<string, unknown> | null;
  const gates = (validation?.gates ?? {}) as Record<string, Record<string, unknown>>;
  const verdict = validation?.verdict as string | undefined;
  const windows = (validation?.windows ?? []) as Record<string, unknown>[];

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h3 className="text-sm font-medium text-text-primary">Gate 1 검증</h3>
        <p className="mt-1 text-xs text-text-muted">
          Walk-forward OOS 백테스트로 최적화 결과를 검증합니다.
        </p>
      </div>

      {/* Running state */}
      {job.isRunning && (
        <div className="rounded-lg border border-border bg-bg-card p-4">
          <div className="flex items-center gap-3">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-accent/30 border-t-accent" />
            <div>
              <div className="text-sm font-medium text-text-primary">
                검증 진행 중...
              </div>
              <div className="text-xs text-text-muted">
                {job.progress || "Walk-forward 백테스트 실행 중..."} ({job.elapsed.toFixed(0)}s)
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Results */}
      {validation && (
        <>
          {/* Verdict banner */}
          <div
            className={cn(
              "rounded-lg border p-4 text-center",
              verdict === "pass" && "border-status-running/30 bg-status-running/10",
              verdict === "warn" && "border-yellow-500/30 bg-yellow-500/10",
              verdict === "fail" && "border-status-error/30 bg-status-error/10",
            )}
          >
            <div className="text-2xl">
              {verdict === "pass" ? "✅" : verdict === "warn" ? "⚠️" : "❌"}
            </div>
            <div
              className={cn(
                "mt-1 text-sm font-semibold",
                verdict === "pass" && "text-status-running",
                verdict === "warn" && "text-yellow-500",
                verdict === "fail" && "text-status-error",
              )}
            >
              {verdict === "pass"
                ? "검증 통과"
                : verdict === "warn"
                  ? "주의 (일부 기준 미달)"
                  : "검증 실패"}
            </div>
          </div>

          {/* Gate criteria */}
          <div className="rounded-lg border border-border bg-bg-card p-3">
            <h4 className="mb-2 text-xs font-medium text-text-muted">
              4-Gate 기준
            </h4>
            <div className="space-y-2">
              {Object.entries(gates).map(([key, gate]) => (
                <div key={key} className="flex items-center justify-between text-xs">
                  <span className="text-text-secondary">{key.replace(/_/g, " ")}</span>
                  <div className="flex items-center gap-2">
                    <span className="tabular-nums text-text-muted">
                      {Number(gate.value ?? 0).toFixed(2)} / {Number(gate.threshold ?? 0).toFixed(2)}
                    </span>
                    <span
                      className={cn(
                        "rounded px-1.5 py-0.5 text-xs font-medium",
                        gate.pass
                          ? "bg-status-running/10 text-status-running"
                          : "bg-status-error/10 text-status-error",
                      )}
                    >
                      {gate.pass ? "PASS" : "FAIL"}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Window details */}
          {windows.length > 0 && (
            <div className="rounded-lg border border-border bg-bg-card p-3">
              <h4 className="mb-2 text-xs font-medium text-text-muted">
                Walk-forward 윈도우 ({windows.length}개)
              </h4>
              <div className="space-y-1">
                {windows.map((w, i) => (
                  <div key={i} className="flex items-center justify-between text-xs">
                    <span className="text-text-muted">Window {Number(w.window_id ?? i + 1)}</span>
                    <div className="flex gap-3 tabular-nums text-text-secondary">
                      <span>수익: {Number(w.return_pct ?? 0).toFixed(1)}%</span>
                      <span>PF: {Number(w.pf ?? 0).toFixed(2)}</span>
                      <span>MDD: {Number(w.mdd ?? 0).toFixed(1)}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Summary metrics */}
          <div className="grid grid-cols-3 gap-2">
            <div className="rounded-lg border border-border bg-bg-card p-2 text-center">
              <div className="text-xs text-text-muted">평균 수익률</div>
              <div className="text-sm font-medium tabular-nums text-status-running">
                {Number(validation.avg_return_pct ?? 0).toFixed(2)}%
              </div>
            </div>
            <div className="rounded-lg border border-border bg-bg-card p-2 text-center">
              <div className="text-xs text-text-muted">평균 PF</div>
              <div className="text-sm font-medium tabular-nums text-text-primary">
                {Number(validation.avg_pf ?? 0).toFixed(2)}
              </div>
            </div>
            <div className="rounded-lg border border-border bg-bg-card p-2 text-center">
              <div className="text-xs text-text-muted">총 거래</div>
              <div className="text-sm font-medium tabular-nums text-text-primary">
                {String(validation.total_trades ?? 0)}
              </div>
            </div>
          </div>
        </>
      )}

      {/* Re-optimize button on fail */}
      {verdict === "fail" && (
        <button
          onClick={() => dispatch({ type: "GO_TO_STEP", step: "optimize" })}
          className="w-full rounded-lg border border-accent/50 px-4 py-2.5 text-sm font-medium text-accent transition-colors hover:bg-accent/10"
        >
          다시 최적화로 돌아가기
        </button>
      )}

      <WizardNavButtons
        nextDisabled={!validation}
        nextLabel={verdict === "fail" ? "그래도 진행" : "다음"}
      />
    </div>
  );
}
