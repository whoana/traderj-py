"use client";

import { useState, useEffect } from "react";

interface Analysis {
  best_strategy_id: string | null;
  best_strategy_name: string | null;
  best_return_pct: number | null;
  worst_strategy_id: string | null;
  worst_return_pct: number | null;
  market_change_pct: number | null;
  beat_market_count: number;
  total_strategies: number;
  insights: string[];
  actions: string[];
}

interface RegimeSuggestion {
  regime: string;
  current_strategy: string;
  suggested_strategy: string;
  current_return_pct: number;
  suggested_return_pct: number;
  improvement_pct: number;
  sample_weeks: number;
}

interface OptCandidate {
  rank: number;
  params: Record<string, number>;
  return_pct: number;
  win_rate: number;
  mdd: number;
  trades: number;
  score: number;
}

interface OptResult {
  strategy_id: string;
  strategy_name: string;
  baseline: {
    return_pct: number | null;
    win_rate: number | null;
    mdd: number | null;
    trades: number | null;
    profit_factor: number | null;
  };
  candidates: OptCandidate[];
  study_stats: { n_trials: number; n_completed: number; best_value: number | null };
}

interface Props {
  jobId: string;
  startDate: string;
  endDate: string;
}

export default function ActionPanel({ jobId, startDate, endDate }: Props) {
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [regimeSuggestions, setRegimeSuggestions] = useState<RegimeSuggestion[]>([]);
  const [loading, setLoading] = useState(true);

  // Action A: Strategy switch
  const [switching, setSwitching] = useState(false);
  const [switchResult, setSwitchResult] = useState<string | null>(null);

  // Action B: Regime map
  const [applyingRegime, setApplyingRegime] = useState(false);
  const [regimeResult, setRegimeResult] = useState<string | null>(null);

  // Action C: Optimize
  const [optimizing, setOptimizing] = useState(false);
  const [optProgress, setOptProgress] = useState("");
  const [optResult, setOptResult] = useState<OptResult | null>(null);
  const [optError, setOptError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/engine/backtest/analyze/${jobId}`)
      .then((r) => r.json())
      .then((d) => {
        setAnalysis(d.analysis || null);
        setRegimeSuggestions(d.regime_suggestions || []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [jobId]);

  if (loading) {
    return (
      <div className="rounded-lg border border-border bg-bg-card p-4">
        <div className="h-4 w-32 animate-pulse rounded bg-bg-hover" />
      </div>
    );
  }

  if (!analysis) return null;

  // ── Action A: Strategy Switch ──
  const handleSwitch = async (strategyId: string) => {
    setSwitching(true);
    setSwitchResult(null);
    try {
      const res = await fetch("/api/engine/strategy/switch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ strategy_id: strategyId }),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        setSwitchResult(`${data.old_preset} -> ${data.new_preset} 전환 완료`);
      } else {
        setSwitchResult(data.detail || "전환 실패 (엔진 미연결)");
      }
    } catch {
      setSwitchResult("전환 실패 (엔진 미연결)");
    } finally {
      setSwitching(false);
    }
  };

  // ── Action B: Apply Regime Map ──
  const handleApplyRegimeMap = async () => {
    if (regimeSuggestions.length === 0) return;
    setApplyingRegime(true);
    setRegimeResult(null);
    try {
      const suggestions = regimeSuggestions.map((s) => ({
        regime: s.regime,
        suggested_strategy: s.suggested_strategy,
      }));
      const res = await fetch("/api/engine/backtest/apply-regime-map", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ suggestions }),
      });
      const data = await res.json();
      if (res.ok) {
        const applied = data.applied?.length || 0;
        const errors = data.errors?.length || 0;
        setRegimeResult(
          errors > 0
            ? `${applied}개 적용, ${errors}개 오류`
            : `${applied}개 레짐 매핑 업데이트 완료`
        );
      } else {
        setRegimeResult(data.error || "적용 실패");
      }
    } catch {
      setRegimeResult("적용 실패 (엔진 미연결)");
    } finally {
      setApplyingRegime(false);
    }
  };

  // ── Action C: Parameter Optimization ──
  const handleOptimize = async () => {
    if (!analysis.best_strategy_id) return;
    setOptimizing(true);
    setOptProgress("최적화 job 시작 중...");
    setOptResult(null);
    setOptError(null);
    try {
      // Start optimize job
      const runRes = await fetch("/api/engine/backtest/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode: "optimize",
          start_date: startDate,
          end_date: endDate,
          strategy_id: analysis.best_strategy_id,
          n_trials: 30,
        }),
      });
      const runData = await runRes.json();
      if (!runRes.ok) {
        setOptError(runData.detail || "최적화 시작 실패");
        setOptimizing(false);
        return;
      }

      const optJobId = runData.job_id;
      setOptProgress("Optuna 최적화 실행 중...");

      // Poll for completion
      let attempts = 0;
      const maxAttempts = 120; // 2 minutes
      while (attempts < maxAttempts) {
        await new Promise((r) => setTimeout(r, 2000));
        attempts++;

        const pollRes = await fetch(`/api/engine/backtest/jobs/${optJobId}`);
        const pollData = await pollRes.json();

        if (pollData.progress) setOptProgress(pollData.progress);

        if (pollData.status === "done") {
          const optimization = pollData.result?.optimization as OptResult | undefined;
          if (optimization) {
            setOptResult(optimization);
          } else {
            setOptError("최적화 결과 없음");
          }
          break;
        }
        if (pollData.status === "failed") {
          setOptError(pollData.error || "최적화 실패");
          break;
        }
      }
      if (attempts >= maxAttempts) {
        setOptError("최적화 시간 초과");
      }
    } catch {
      setOptError("최적화 실패 (엔진 미연결)");
    } finally {
      setOptimizing(false);
      setOptProgress("");
    }
  };

  const fmtPct = (v: number | null | undefined) =>
    v != null ? `${v >= 0 ? "+" : ""}${v.toFixed(2)}%` : "-";

  return (
    <div className="rounded-lg border border-accent/30 bg-bg-card p-4 space-y-3">
      <h3 className="text-sm font-medium text-text-primary">분석 요약 & 액션</h3>

      {/* Insights */}
      {analysis.insights.length > 0 && (
        <ul className="space-y-0.5 text-xs text-text-secondary">
          {analysis.insights.map((insight, i) => (
            <li key={i} className="flex items-start gap-1.5">
              <span className="mt-0.5 text-text-muted">-</span>
              <span>{insight}</span>
            </li>
          ))}
        </ul>
      )}

      {/* Action buttons */}
      <div className="flex flex-wrap gap-2 pt-1">
        {/* Action A: Strategy Switch */}
        {analysis.actions.includes("switch") && analysis.best_strategy_id && (
          <button
            onClick={() => handleSwitch(analysis.best_strategy_id!)}
            disabled={switching}
            className="flex items-center gap-1.5 rounded-md border border-accent/50 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/20 disabled:opacity-50"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
            </svg>
            {analysis.best_strategy_id}로 전환
            {analysis.best_return_pct != null && (
              <span className="text-[10px] text-text-muted">({fmtPct(analysis.best_return_pct)})</span>
            )}
          </button>
        )}

        {/* Action C: Parameter Optimization */}
        {analysis.actions.includes("optimize") && analysis.best_strategy_id && (
          <button
            onClick={handleOptimize}
            disabled={optimizing}
            className="flex items-center gap-1.5 rounded-md border border-accent/50 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/20 disabled:opacity-50"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            {optimizing ? "최적화 중..." : "파라미터 최적화"}
            {!optimizing && (
              <span className="text-[10px] text-text-muted">({analysis.best_strategy_id})</span>
            )}
          </button>
        )}

        {/* Action B: Regime Map */}
        {analysis.actions.includes("regime_map") && regimeSuggestions.length > 0 && (
          <button
            onClick={handleApplyRegimeMap}
            disabled={applyingRegime}
            className="flex items-center gap-1.5 rounded-md border border-accent/50 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/20 disabled:opacity-50"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            {applyingRegime ? "적용 중..." : "레짐 매핑 적용"}
          </button>
        )}
      </div>

      {/* Action results */}
      {switchResult && (
        <p className="text-[10px] text-text-muted">{switchResult}</p>
      )}
      {regimeResult && (
        <p className="text-[10px] text-status-running">{regimeResult}</p>
      )}

      {/* Optimize progress */}
      {optimizing && optProgress && (
        <div className="flex items-center gap-2 text-xs text-text-muted">
          <div className="h-3 w-3 animate-spin rounded-full border-2 border-accent/30 border-t-accent" />
          {optProgress}
        </div>
      )}
      {optError && (
        <p className="text-[10px] text-status-error">{optError}</p>
      )}

      {/* Optimize results */}
      {optResult && (
        <div className="mt-2 border-t border-border/50 pt-2 space-y-2">
          <p className="text-[10px] font-medium text-text-muted">
            Optuna 최적화 결과 ({optResult.study_stats.n_trials} trials)
          </p>

          {/* Baseline vs Best */}
          <div className="grid grid-cols-2 gap-3 text-[10px]">
            <div className="rounded border border-border/50 p-2">
              <p className="mb-1 font-medium text-text-secondary">현재 ({optResult.strategy_id})</p>
              <div className="space-y-0.5 text-text-muted">
                <p>수익률: {fmtPct(optResult.baseline.return_pct)}</p>
                <p>승률: {optResult.baseline.win_rate != null ? (optResult.baseline.win_rate * 100).toFixed(1) + "%" : "-"}</p>
                <p>MDD: {optResult.baseline.mdd != null ? optResult.baseline.mdd.toFixed(2) + "%" : "-"}</p>
                <p>거래수: {optResult.baseline.trades ?? "-"}</p>
              </div>
            </div>
            {optResult.candidates[0] && (
              <div className="rounded border border-accent/30 bg-accent/5 p-2">
                <p className="mb-1 font-medium text-accent">최적화 #1</p>
                <div className="space-y-0.5 text-text-muted">
                  <p>수익률: <span className="text-accent">{fmtPct(optResult.candidates[0].return_pct)}</span></p>
                  <p>승률: {(optResult.candidates[0].win_rate * 100).toFixed(1)}%</p>
                  <p>MDD: {optResult.candidates[0].mdd.toFixed(2)}%</p>
                  <p>거래수: {optResult.candidates[0].trades}</p>
                </div>
              </div>
            )}
          </div>

          {/* Top candidates table */}
          {optResult.candidates.length > 1 && (
            <div className="overflow-x-auto">
              <table className="w-full text-[10px]">
                <thead>
                  <tr className="text-text-muted border-b border-border/30">
                    <th className="text-left py-1 pr-2">#</th>
                    <th className="text-right py-1 px-2">수익률</th>
                    <th className="text-right py-1 px-2">승률</th>
                    <th className="text-right py-1 px-2">MDD</th>
                    <th className="text-right py-1 px-2">거래</th>
                  </tr>
                </thead>
                <tbody>
                  {optResult.candidates.map((c) => (
                    <tr key={c.rank} className="text-text-secondary border-b border-border/10">
                      <td className="py-1 pr-2">{c.rank}</td>
                      <td className="text-right py-1 px-2 font-mono">{fmtPct(c.return_pct)}</td>
                      <td className="text-right py-1 px-2">{(c.win_rate * 100).toFixed(1)}%</td>
                      <td className="text-right py-1 px-2">{c.mdd.toFixed(2)}%</td>
                      <td className="text-right py-1 px-2">{c.trades}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Best candidate params */}
          {optResult.candidates[0] && (
            <details className="text-[10px] text-text-muted">
              <summary className="cursor-pointer hover:text-text-secondary">최적 파라미터 상세</summary>
              <pre className="mt-1 overflow-x-auto rounded bg-bg-hover p-2 text-[9px]">
                {JSON.stringify(optResult.candidates[0].params, null, 2)}
              </pre>
            </details>
          )}
        </div>
      )}

      {/* Regime suggestions preview (if available) */}
      {regimeSuggestions.length > 0 && (
        <div className="mt-2 border-t border-border/50 pt-2">
          <p className="mb-1 text-[10px] font-medium text-text-muted">레짐 매핑 제안</p>
          <div className="space-y-1">
            {regimeSuggestions.map((s) => (
              <div key={s.regime} className="flex items-center gap-2 text-[10px]">
                <span className="w-32 truncate text-text-secondary">{s.regime}</span>
                <span className="text-text-muted">{s.current_strategy}</span>
                <span className="text-text-muted">{"->"}</span>
                <span className="text-accent">{s.suggested_strategy}</span>
                <span className="ml-auto font-mono text-status-running">+{s.improvement_pct.toFixed(2)}%</span>
                <span className="text-text-muted">({s.sample_weeks}w)</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
