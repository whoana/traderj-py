"use client";

import { useWizard } from "@/contexts/WizardContext";
import { WizardNavButtons } from "../WizardNavButtons";
import { useCallback, useEffect, useState } from "react";
import { cn } from "@/lib/cn";

export function StepApply() {
  const { state, dispatch } = useWizard();
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);

  const candidate = state.selectedCandidate as Record<string, unknown> | null;
  const params = (candidate?.params ?? {}) as Record<string, number>;

  // Fetch before/after preview
  useEffect(() => {
    if (!state.selectedStrategy || Object.keys(params).length === 0) return;
    async function fetchPreview() {
      setLoading(true);
      try {
        const paramStr = Object.entries(params)
          .map(([k, v]) => `${k}=${v}`)
          .join(",");
        const res = await fetch(
          `/api/engine/backtest/wizard/apply-preview?strategy_id=${state.selectedStrategy}&params=${encodeURIComponent(paramStr)}`,
        );
        if (!res.ok) return;
        const data = await res.json();
        setPreview(data);
        dispatch({ type: "SET_APPLY_PREVIEW", preview: data });
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    }
    fetchPreview();
  }, [state.selectedStrategy, params, dispatch]);

  const handleApply = useCallback(async () => {
    dispatch({ type: "SET_LOADING", loading: true });
    try {
      const res = await fetch("/api/engine/backtest/wizard/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          changes: {
            param_optimize: params,
            strategy_switch: { from: state.selectedStrategy, to: state.selectedStrategy },
          },
          skip_validation: false,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Apply failed" }));
        throw new Error(err.detail ?? "적용 실패");
      }
      const data = await res.json();
      dispatch({
        type: "SET_APPLIED",
        changes: data.applied ?? [],
        tuningId: data.tuning_id ?? "",
      });
      dispatch({ type: "SET_LOADING", loading: false });
      dispatch({ type: "NEXT_STEP" });
    } catch (e) {
      dispatch({
        type: "SET_ERROR",
        error: e instanceof Error ? e.message : "적용 실패",
      });
    }
  }, [params, state.selectedStrategy, dispatch]);

  const currentSnap = (preview?.current ?? {}) as Record<string, unknown>;
  const candidateSnap = (preview?.candidate ?? {}) as Record<string, unknown>;

  // Build comparison rows
  const comparisonKeys = [
    "buy_threshold",
    "sell_threshold",
    "macro_weight",
  ];

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h3 className="text-sm font-medium text-text-primary">적용 리뷰</h3>
        <p className="mt-1 text-xs text-text-muted">
          변경될 파라미터를 확인하고 적용합니다.
        </p>
      </div>

      {loading ? (
        <div className="h-40 animate-pulse rounded-lg bg-bg-secondary" />
      ) : (
        <>
          {/* Param diff table */}
          <div className="rounded-lg border border-border bg-bg-card overflow-hidden">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border bg-bg-secondary/50">
                  <th className="px-3 py-2 text-xs font-medium text-text-muted">파라미터</th>
                  <th className="px-3 py-2 text-xs font-medium text-text-muted">현재</th>
                  <th className="px-3 py-2 text-xs font-medium text-text-muted">변경</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(params).map(([key, newVal]) => {
                  const curVal =
                    comparisonKeys.includes(key) && currentSnap[key] != null
                      ? Number(currentSnap[key])
                      : null;
                  const changed = curVal != null && Math.abs(curVal - newVal) > 0.0001;
                  return (
                    <tr key={key} className="border-b border-border/50">
                      <td className="px-3 py-2 font-mono text-xs text-text-secondary">
                        {key}
                      </td>
                      <td className="px-3 py-2 tabular-nums text-xs text-text-muted">
                        {curVal != null ? curVal.toFixed(4) : "-"}
                      </td>
                      <td
                        className={cn(
                          "px-3 py-2 tabular-nums text-xs font-medium",
                          changed ? "text-accent" : "text-text-primary",
                        )}
                      >
                        {newVal.toFixed(4)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* TF weights if present */}
          {candidateSnap.tf_weights && (
            <div className="rounded-lg border border-border bg-bg-card p-3">
              <h4 className="text-xs font-medium text-text-muted">타임프레임 가중치</h4>
              <div className="mt-1 flex gap-3 text-xs">
                {Object.entries(
                  candidateSnap.tf_weights as Record<string, number>,
                ).map(([tf, w]) => (
                  <span key={tf} className="text-text-secondary">
                    {tf}: <span className="font-medium text-text-primary">{Number(w).toFixed(2)}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Score weights if present */}
          {candidateSnap.score_weights && (
            <div className="rounded-lg border border-border bg-bg-card p-3">
              <h4 className="text-xs font-medium text-text-muted">스코어 가중치</h4>
              <div className="mt-1 flex gap-3 text-xs">
                {Object.entries(
                  candidateSnap.score_weights as Record<string, number>,
                ).map(([k, w]) => (
                  <span key={k} className="text-text-secondary">
                    {k}: <span className="font-medium text-text-primary">{Number(w).toFixed(2)}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Candidate performance */}
          {candidate && (
            <div className="rounded-lg border border-accent/30 bg-accent/5 p-3">
              <h4 className="text-xs font-medium text-text-muted">예상 성능</h4>
              <div className="mt-1 flex gap-4 text-xs">
                <span>
                  수익률:{" "}
                  <span className="font-medium text-status-running">
                    {Number(candidate.return_pct ?? 0).toFixed(1)}%
                  </span>
                </span>
                <span>
                  Sharpe: <span className="font-medium">{Number(candidate.sharpe_ratio ?? 0).toFixed(2)}</span>
                </span>
                <span>
                  MDD: <span className="font-medium">{Number(candidate.mdd ?? 0).toFixed(1)}%</span>
                </span>
              </div>
            </div>
          )}
        </>
      )}

      <WizardNavButtons
        onNext={handleApply}
        nextLabel="적용"
        nextDisabled={Object.keys(params).length === 0}
      />
    </div>
  );
}
