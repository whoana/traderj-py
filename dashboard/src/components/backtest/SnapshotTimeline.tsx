"use client";

import { useState, useEffect } from "react";

interface Snapshot {
  snapshot_id: string;
  strategy_id: string;
  created_at: string;
  source: string;
  description: string;
  is_active: boolean;
}

const SOURCE_LABELS: Record<string, string> = {
  tuning: "Optuna 최적화",
  backtest: "백테스트 기반",
  manual: "수동 변경",
  rollback: "롤백",
};

export default function SnapshotTimeline() {
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/engine/tuning/snapshots?limit=10")
      .then((r) => {
        if (!r.ok) throw new Error("not available");
        return r.json();
      })
      .then((d) => setSnapshots(d.snapshots || []))
      .catch(() => setSnapshots([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="rounded-lg border border-border bg-bg-card p-4">
        <div className="h-4 w-40 animate-pulse rounded bg-bg-hover" />
      </div>
    );
  }

  if (snapshots.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-bg-card p-4">
        <h3 className="mb-2 text-sm font-medium text-text-primary">파라미터 히스토리</h3>
        <p className="text-xs text-text-muted">
          스냅샷 데이터가 없습니다. AI Tuner 파이프라인 구현 후 파라미터 변경 히스토리가 여기에 표시됩니다.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-bg-card p-4">
      <h3 className="mb-3 text-sm font-medium text-text-primary">파라미터 히스토리</h3>
      <div className="relative space-y-0 pl-4">
        {/* Timeline line */}
        <div className="absolute left-[7px] top-2 bottom-2 w-px bg-border" />

        {snapshots.map((snap, i) => (
          <div key={snap.snapshot_id} className="relative flex items-start gap-3 py-2">
            {/* Dot */}
            <div className={`relative z-10 mt-0.5 h-3.5 w-3.5 rounded-full border-2 ${
              snap.is_active
                ? "border-accent bg-accent"
                : "border-border bg-bg-primary"
            }`} />

            {/* Content */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 text-xs">
                <span className="font-medium text-text-primary">
                  {snap.snapshot_id}
                </span>
                <span className="text-text-muted">{snap.created_at.slice(5, 16)}</span>
                <span className="rounded bg-bg-hover px-1.5 py-0.5 text-[10px] text-text-muted">
                  {SOURCE_LABELS[snap.source] || snap.source}
                </span>
                {snap.is_active && (
                  <span className="rounded bg-accent/10 px-1.5 py-0.5 text-[10px] font-medium text-accent">
                    현재
                  </span>
                )}
              </div>
              <p className="mt-0.5 text-[10px] text-text-muted truncate">{snap.description}</p>
              {!snap.is_active && i > 0 && (
                <button
                  disabled
                  className="mt-1 text-[10px] text-text-muted cursor-not-allowed"
                  title="AI Tuner 파이프라인 구현 후 활성화"
                >
                  이 시점으로 롤백 (준비중)
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
