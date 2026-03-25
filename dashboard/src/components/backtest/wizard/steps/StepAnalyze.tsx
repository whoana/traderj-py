"use client";

import { useWizard } from "@/contexts/WizardContext";
import { WizardNavButtons } from "../WizardNavButtons";
import { useCallback, useEffect, useState } from "react";
import { cn } from "@/lib/cn";

export function StepAnalyze() {
  const { state, dispatch } = useWizard();
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (state.analysis || !state.selectedJobId) return;
    async function fetchAnalysis() {
      setLoading(true);
      dispatch({ type: "SET_LOADING", loading: true });
      try {
        const res = await fetch(
          `/api/engine/backtest/analyze/${state.selectedJobId}`,
        );
        if (!res.ok) throw new Error("분석 데이터를 불러올 수 없습니다");
        const data = await res.json();
        dispatch({ type: "SET_ANALYSIS", analysis: data });
      } catch (e) {
        dispatch({
          type: "SET_ERROR",
          error: e instanceof Error ? e.message : "분석 실패",
        });
      } finally {
        setLoading(false);
        dispatch({ type: "SET_LOADING", loading: false });
      }
    }
    fetchAnalysis();
  }, [state.selectedJobId, state.analysis, dispatch]);

  const analysis = state.analysis as Record<string, unknown> | null;
  const insights = (analysis?.analysis as Record<string, unknown>) ?? {};
  const regimeSuggestions = (analysis?.regime_suggestions ?? []) as Record<string, unknown>[];

  // Extract metrics from backtest result
  const result = state.backtestResult ?? {};
  const strategies = (result.strategies ?? []) as Record<string, unknown>[];
  const metrics =
    strategies.length > 0
      ? (strategies[0].metrics as Record<string, unknown>) ?? {}
      : {};

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h3 className="text-sm font-medium text-text-primary">백테스트 분석</h3>
        <p className="mt-1 text-xs text-text-muted">
          선택한 백테스트 결과의 핵심 지표와 개선 포인트를 확인합니다.
        </p>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 animate-pulse rounded-lg bg-bg-secondary" />
          ))}
        </div>
      ) : (
        <>
          {/* Key metrics */}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {[
              { label: "수익률", key: "total_return_pct", suffix: "%" },
              { label: "승률", key: "win_rate", suffix: "%" },
              { label: "MDD", key: "max_drawdown_pct", suffix: "%" },
              { label: "Sharpe", key: "sharpe_ratio", suffix: "" },
              { label: "거래 수", key: "total_trades", suffix: "" },
              { label: "Profit Factor", key: "profit_factor", suffix: "" },
            ].map(({ label, key, suffix }) => {
              const val = metrics[key];
              if (val == null) return null;
              const num = Number(val);
              return (
                <div
                  key={key}
                  className="rounded-lg border border-border bg-bg-card p-2.5"
                >
                  <div className="text-xs text-text-muted">{label}</div>
                  <div
                    className={cn(
                      "mt-0.5 text-sm font-medium tabular-nums",
                      key.includes("return") || key === "sharpe_ratio"
                        ? num >= 0
                          ? "text-status-running"
                          : "text-status-error"
                        : "text-text-primary",
                    )}
                  >
                    {typeof num === "number" && !Number.isInteger(num)
                      ? num.toFixed(2)
                      : num}
                    {suffix}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Insights */}
          {insights.summary && (
            <div className="rounded-lg border border-border bg-bg-card p-3">
              <h4 className="mb-2 text-xs font-medium text-text-muted">
                분석 인사이트
              </h4>
              <p className="text-sm text-text-secondary">
                {String(insights.summary)}
              </p>
              {Array.isArray(insights.recommendations) && (
                <ul className="mt-2 space-y-1">
                  {(insights.recommendations as string[]).map((r, i) => (
                    <li key={i} className="text-xs text-text-muted">
                      • {r}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* Regime suggestions */}
          {regimeSuggestions.length > 0 && (
            <div className="rounded-lg border border-border bg-bg-card p-3">
              <h4 className="mb-2 text-xs font-medium text-text-muted">
                레짐 매핑 제안
              </h4>
              <div className="space-y-1">
                {regimeSuggestions.map((s, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs">
                    <span className="rounded bg-bg-secondary px-1.5 py-0.5 font-mono">
                      {String(s.regime)}
                    </span>
                    <span className="text-text-muted">→</span>
                    <span className="font-medium text-accent">
                      {String(s.suggested_strategy)}
                    </span>
                    {s.reason != null && (
                      <span className="text-text-muted">
                        ({String(s.reason)})
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Selected strategy info */}
          <div className="rounded-lg border border-accent/30 bg-accent/5 p-3">
            <div className="text-xs text-text-muted">최적화 대상 전략</div>
            <div className="mt-0.5 text-sm font-medium text-accent">
              {state.selectedStrategy}
            </div>
          </div>
        </>
      )}

      <WizardNavButtons nextDisabled={loading || !state.analysis} />
    </div>
  );
}
