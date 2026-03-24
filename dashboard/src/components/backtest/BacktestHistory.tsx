"use client";

import { useState } from "react";

type Mode = "compare" | "single" | "ai_regime";

const MODE_LABELS: Record<string, string> = {
  compare: "전략 비교",
  single: "단일 전략",
  ai_regime: "AI Regime",
};

const STATUS_ICON: Record<string, { icon: string; color: string }> = {
  done: { icon: "✓", color: "text-status-running" },
  failed: { icon: "✗", color: "text-status-error" },
  running: { icon: "…", color: "text-accent" },
  pending: { icon: "…", color: "text-text-muted" },
  fetching: { icon: "…", color: "text-text-muted" },
  cancelled: { icon: "—", color: "text-text-muted" },
};

interface HistoryItem {
  job_id: string;
  mode: Mode;
  status: string;
  start_date: string;
  end_date: string;
  created_at: string;
  summary?: Record<string, unknown> | null;
}

interface Props {
  items: HistoryItem[];
  onViewResult: (jobId: string) => void;
}

export default function BacktestHistory({ items, onViewResult }: Props) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (items.length === 0) {
    return <p className="text-xs text-text-muted">히스토리가 없습니다</p>;
  }

  return (
    <div className="space-y-1.5">
      {items.map((h) => {
        const s = STATUS_ICON[h.status] || STATUS_ICON.pending;
        const isExpanded = expanded === h.job_id;
        const isDone = h.status === "done";

        return (
          <div key={h.job_id} className="rounded-md bg-bg-primary overflow-hidden">
            {/* Main row */}
            <button
              onClick={() => setExpanded(isExpanded ? null : h.job_id)}
              className="flex w-full items-center gap-2 p-2 text-xs text-left hover:bg-bg-hover transition-colors"
            >
              <span className={`font-medium ${s.color}`}>{s.icon}</span>
              <span className="w-16 text-text-muted">{h.created_at?.slice(5, 10)}</span>
              <span className="rounded bg-bg-hover px-1.5 py-0.5 text-[10px] text-text-muted">
                {MODE_LABELS[h.mode] || h.mode}
              </span>
              <span className="text-text-primary">{h.start_date} ~ {h.end_date}</span>

              {h.summary && (
                <span className="ml-auto text-text-muted">
                  {h.summary.best_strategy ? `${String(h.summary.best_strategy)}` : ""}
                  {h.summary.best_return_pct != null && (
                    <span className={Number(h.summary.best_return_pct) >= 0 ? "text-status-running" : "text-status-error"}>
                      {" "}{Number(h.summary.best_return_pct) >= 0 ? "+" : ""}
                      {Number(h.summary.best_return_pct).toFixed(2)}%
                    </span>
                  )}
                </span>
              )}

              <svg
                className={`h-3 w-3 text-text-muted transition-transform ml-1 ${isExpanded ? "rotate-180" : ""}`}
                fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {/* Expanded detail */}
            {isExpanded && (
              <div className="border-t border-border/30 px-2 py-2 flex items-center gap-3">
                <span className="text-[10px] text-text-muted">
                  Job: {h.job_id.slice(0, 8)}...
                </span>
                {h.summary?.ai_return_pct != null && (
                  <span className="text-[10px] text-text-muted">
                    AI: {Number(h.summary.ai_return_pct) >= 0 ? "+" : ""}
                    {Number(h.summary.ai_return_pct).toFixed(2)}%
                  </span>
                )}
                {isDone && (
                  <button
                    onClick={(e) => { e.stopPropagation(); onViewResult(h.job_id); }}
                    className="ml-auto rounded-md border border-accent/50 px-2 py-0.5 text-[10px] font-medium text-accent hover:bg-accent/10"
                  >
                    결과 보기
                  </button>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
