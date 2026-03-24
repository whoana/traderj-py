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

interface Props {
  jobId: string;
}

export default function ActionPanel({ jobId }: Props) {
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [regimeSuggestions, setRegimeSuggestions] = useState<RegimeSuggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState(false);
  const [switchResult, setSwitchResult] = useState<string | null>(null);

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
              <span className="text-[10px] text-text-muted">({analysis.best_return_pct >= 0 ? "+" : ""}{analysis.best_return_pct.toFixed(2)}%)</span>
            )}
          </button>
        )}

        {/* Action C: Parameter Optimization (placeholder) */}
        {analysis.actions.includes("optimize") && (
          <button
            disabled
            className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium text-text-muted cursor-not-allowed"
            title="AI Tuner 파이프라인 구현 후 활성화"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            파라미터 최적화
            <span className="text-[9px]">(준비중)</span>
          </button>
        )}

        {/* Action B: Regime Map (placeholder) */}
        {analysis.actions.includes("regime_map") && (
          <button
            disabled
            className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium text-text-muted cursor-not-allowed"
            title="AI Tuner 파이프라인 구현 후 활성화"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            레짐 매핑 최적화
            <span className="text-[9px]">(준비중)</span>
          </button>
        )}
      </div>

      {/* Switch result */}
      {switchResult && (
        <p className="text-[10px] text-text-muted">{switchResult}</p>
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
