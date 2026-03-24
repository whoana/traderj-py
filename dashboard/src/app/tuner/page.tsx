"use client";

import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { Card } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { api } from "@/lib/api";

/* ── Types ── */

interface TunerStatus {
  state: string;
  active_monitoring: { tuning_id: string; strategy_id: string }[];
  consecutive_rollbacks: number;
  registered_strategies: string[];
  latest_tuning?: Record<string, {
    tuning_id: string;
    status: string;
    created_at: string;
    reason?: string;
    changes?: { parameter_name: string; old_value: number; new_value: number }[];
  }>;
}

interface ProviderStatus {
  claude?: { state: string; failures: number };
  openai?: { state: string; failures: number };
  budget?: { used_usd: number; limit_usd: number };
  error?: string;
}

interface TuningRecord {
  tuning_id: string;
  strategy_id: string;
  status: string;
  created_at: string;
  eval_window?: string;
  tier?: string;
  metrics?: {
    total_trades?: number;
    win_rate?: number;
    profit_factor?: number;
    max_drawdown?: number;
  };
  recommendations?: { name: string; direction: string; reason: string }[];
  applied_changes?: { parameter_name: string; old_value: number; new_value: number }[];
}

/* ── Page ── */

export default function TunerPage() {
  const [tuner, setTuner] = useState<TunerStatus | null>(null);
  const [provider, setProvider] = useState<ProviderStatus | null>(null);
  const [history, setHistory] = useState<TuningRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [selectedTier, setSelectedTier] = useState("tier_1");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<{
    action: string;
    title: string;
    description: string;
    onConfirm: () => void;
  } | null>(null);

  const fetchAll = useCallback(async () => {
    try {
      const [tun, prov, hist] = await Promise.allSettled([
        api.get<TunerStatus>("/engine/tuning/status"),
        api.get<ProviderStatus>("/engine/tuning/provider-status"),
        api.get<{ items: TuningRecord[] }>("/engine/tuning/history?limit=20"),
      ]);
      if (tun.status === "fulfilled") setTuner(tun.value);
      if (prov.status === "fulfilled") setProvider(prov.value);
      if (hist.status === "fulfilled") setHistory(hist.value.items ?? []);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 30_000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  const doAction = async (action: string, path: string, body?: unknown) => {
    setActionLoading(action);
    try {
      await api.post(path, body);
      toast.success(`${action} successful`);
      await fetchAll();
    } catch (e) {
      toast.error(`Failed: ${e instanceof Error ? e.message : "Unknown error"}`);
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-32 animate-pulse rounded-lg border border-border bg-bg-card" />
        ))}
      </div>
    );
  }

  const budgetPct = provider?.budget
    ? (provider.budget.used_usd / provider.budget.limit_usd) * 100
    : 0;

  return (
    <div className="space-y-3 sm:space-y-4">
      {/* ── Status + Provider ── */}
      <Card title="AI Tuner Status" className="p-2.5 sm:p-4">
        <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
          <div>
            <p className="text-[10px] sm:text-xs text-text-muted">State</p>
            <StatusBadge
              status={tuner?.state === "idle" ? "running" : tuner?.state === "suspended" ? "error" : "warning"}
              label={tuner?.state ?? "unknown"}
              className="mt-1"
            />
          </div>
          <div>
            <p className="text-[10px] sm:text-xs text-text-muted">Monitoring</p>
            <p className="mt-1 font-mono text-sm font-medium">
              {tuner?.active_monitoring.length ? (
                <span className="text-status-warning">{tuner.active_monitoring.length} active</span>
              ) : (
                <span className="text-text-secondary">none</span>
              )}
            </p>
          </div>
          <div>
            <p className="text-[10px] sm:text-xs text-text-muted">Rollbacks</p>
            <p className={`mt-1 font-mono text-sm font-medium ${(tuner?.consecutive_rollbacks ?? 0) >= 2 ? "text-status-error" : "text-text-primary"}`}>
              {tuner?.consecutive_rollbacks ?? 0}
            </p>
          </div>
          <div>
            <p className="text-[10px] sm:text-xs text-text-muted">LLM Budget</p>
            {provider?.budget ? (
              <>
                <p className={`mt-1 font-mono text-sm font-medium ${budgetPct > 80 ? "text-status-warning" : "text-text-primary"}`}>
                  ${provider.budget.used_usd.toFixed(2)} / ${provider.budget.limit_usd.toFixed(0)}
                </p>
                <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-border">
                  <div
                    className={`h-full rounded-full transition-all ${budgetPct > 80 ? "bg-status-warning" : "bg-accent"}`}
                    style={{ width: `${Math.min(budgetPct, 100)}%` }}
                  />
                </div>
              </>
            ) : (
              <p className="mt-1 text-sm text-text-secondary">--</p>
            )}
          </div>
        </div>

        {/* Provider pills */}
        <div className="mt-3 flex flex-wrap gap-2">
          {provider?.claude && (
            <ProviderPill name="Claude" state={provider.claude.state} failures={provider.claude.failures} />
          )}
          {provider?.openai && (
            <ProviderPill name="OpenAI" state={provider.openai.state} failures={provider.openai.failures} />
          )}
        </div>
      </Card>

      {/* ── Controls ── */}
      <Card title="Tuner Controls" className="p-2.5 sm:p-4">
        <div className="flex flex-wrap items-end gap-3">
          {/* Manual Trigger */}
          <div>
            <label htmlFor="tier-select" className="mb-1 block text-[10px] sm:text-xs text-text-muted">Tier</label>
            <select
              id="tier-select"
              value={selectedTier}
              onChange={(e) => setSelectedTier(e.target.value)}
              className="rounded-md border border-border bg-bg-primary px-2 py-1.5 text-sm text-text-primary"
            >
              <option value="tier_1">Tier 1 (Signal)</option>
              <option value="tier_2">Tier 2 (Risk)</option>
              <option value="tier_3">Tier 3 (Regime)</option>
            </select>
          </div>
          <button
            onClick={() => {
              setConfirm({
                action: "trigger",
                title: "Manual Tuning",
                description: `Run AI tuning for ${selectedTier.replace("_", " ").toUpperCase()}?\n\nThis will evaluate strategy performance and optimize parameters using LLM + Optuna.`,
                onConfirm: () => {
                  setConfirm(null);
                  doAction("Tuning trigger", "/engine/tuning/trigger", {
                    strategy_id: "STR-001",
                    tier: selectedTier,
                  });
                },
              });
            }}
            disabled={actionLoading !== null}
            className="rounded-md bg-accent px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-accent/80 disabled:opacity-50"
          >
            {actionLoading === "Tuning trigger" ? "Running..." : "Run Tuning"}
          </button>

          {/* Rollback */}
          {tuner?.active_monitoring && tuner.active_monitoring.length > 0 && (
            <button
              onClick={() => {
                const m = tuner.active_monitoring[0];
                setConfirm({
                  action: "rollback",
                  title: "Rollback Tuning",
                  description: `Roll back tuning ${m.tuning_id} for ${m.strategy_id}?\n\nThis will restore previous parameters.`,
                  onConfirm: () => {
                    setConfirm(null);
                    doAction("Rollback", "/engine/tuning/rollback", {
                      tuning_id: m.tuning_id,
                    });
                  },
                });
              }}
              disabled={actionLoading !== null}
              className="rounded-md bg-status-error px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-status-error/80 disabled:opacity-50"
            >
              Rollback
            </button>
          )}
        </div>

        {/* Pending Tier 3 Approvals */}
        {tuner?.latest_tuning && Object.entries(tuner.latest_tuning)
          .filter(([, rec]) => rec.status === "pending_approval")
          .map(([sid, rec]) => (
            <div key={sid} className="mt-3 rounded-md border border-status-warning/50 bg-status-warning/5 px-3 py-2">
              <p className="text-xs font-medium text-status-warning">Tier 3 Approval Required</p>
              <p className="mt-1 text-[10px] sm:text-xs text-text-secondary">
                {sid} — {rec.tuning_id}
              </p>
              <div className="mt-2 flex gap-2">
                <button
                  onClick={() => doAction("Approve", "/engine/tuning/approve", {
                    tuning_id: rec.tuning_id,
                    approved: true,
                  })}
                  disabled={actionLoading !== null}
                  className="rounded bg-up px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
                >
                  Approve
                </button>
                <button
                  onClick={() => doAction("Reject", "/engine/tuning/approve", {
                    tuning_id: rec.tuning_id,
                    approved: false,
                  })}
                  disabled={actionLoading !== null}
                  className="rounded bg-status-error px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
                >
                  Reject
                </button>
              </div>
            </div>
          ))
        }
      </Card>

      {/* ── Tuning History ── */}
      <Card title="Tuning History" className="p-2.5 sm:p-4">
        {history.length === 0 ? (
          <p className="py-6 text-center text-sm text-text-muted">No tuning records yet</p>
        ) : (
          <div className="space-y-2">
            {history.map((rec) => (
              <div
                key={rec.tuning_id}
                className="rounded-md border border-border/50 transition-colors hover:border-border"
              >
                {/* Summary Row */}
                <button
                  onClick={() => setExpandedId(expandedId === rec.tuning_id ? null : rec.tuning_id)}
                  className="flex w-full items-center justify-between px-3 py-2 text-left"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] sm:text-xs text-text-muted">
                      {new Date(rec.created_at).toLocaleString("ko-KR", {
                        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
                      })}
                    </span>
                    <span className="font-mono text-xs text-text-secondary">{rec.strategy_id}</span>
                    {rec.tier && (
                      <span className="rounded bg-bg-primary px-1.5 py-0.5 text-[10px] font-medium text-text-muted">
                        {rec.tier.replace("_", " ").toUpperCase()}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusBadge
                      status={
                        rec.status === "confirmed" ? "running" :
                        rec.status === "rolled_back" ? "error" :
                        rec.status === "monitoring" ? "warning" :
                        rec.status === "pending_approval" ? "warning" :
                        "default"
                      }
                      label={rec.status}
                    />
                    <svg
                      className={`h-4 w-4 text-text-muted transition-transform ${expandedId === rec.tuning_id ? "rotate-180" : ""}`}
                      fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                    </svg>
                  </div>
                </button>

                {/* Expanded Detail */}
                {expandedId === rec.tuning_id && (
                  <div className="border-t border-border/50 px-3 py-2 space-y-2">
                    {/* Metrics */}
                    {rec.metrics && (
                      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                        <MetricCell label="Trades" value={rec.metrics.total_trades} />
                        <MetricCell label="Win Rate" value={rec.metrics.win_rate != null ? `${(rec.metrics.win_rate * 100).toFixed(1)}%` : undefined} />
                        <MetricCell label="PF" value={rec.metrics.profit_factor?.toFixed(2)} />
                        <MetricCell label="MDD" value={rec.metrics.max_drawdown != null ? `${(rec.metrics.max_drawdown * 100).toFixed(1)}%` : undefined} />
                      </div>
                    )}

                    {/* Applied Changes */}
                    {rec.applied_changes && rec.applied_changes.length > 0 && (
                      <div>
                        <p className="text-[10px] font-medium text-text-muted mb-1">Parameter Changes</p>
                        <div className="space-y-1">
                          {rec.applied_changes.map((c, i) => (
                            <div key={i} className="flex items-center gap-2 text-xs font-mono">
                              <span className="text-text-secondary">{c.parameter_name}</span>
                              <span className="text-down">{c.old_value.toFixed(4)}</span>
                              <span className="text-text-muted">&rarr;</span>
                              <span className="text-up">{c.new_value.toFixed(4)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Recommendations (if no applied changes) */}
                    {(!rec.applied_changes || rec.applied_changes.length === 0) && rec.recommendations && rec.recommendations.length > 0 && (
                      <div>
                        <p className="text-[10px] font-medium text-text-muted mb-1">Recommendations</p>
                        <div className="space-y-1">
                          {rec.recommendations.map((r, i) => (
                            <div key={i} className="text-xs">
                              <span className="font-mono text-text-secondary">{r.name}</span>
                              <span className={`ml-1 ${r.direction === "increase" ? "text-up" : "text-down"}`}>
                                {r.direction === "increase" ? "\u2191" : "\u2193"}
                              </span>
                              <span className="ml-1 text-text-muted">{r.reason}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    <p className="text-[10px] text-text-muted">
                      ID: {rec.tuning_id}
                      {rec.eval_window && ` | Window: ${rec.eval_window}`}
                    </p>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      <ConfirmDialog
        open={confirm !== null}
        title={confirm?.title ?? ""}
        description={confirm?.description ?? ""}
        confirmLabel={confirm?.action ?? "Confirm"}
        variant={confirm?.action === "rollback" ? "danger" : "default"}
        onConfirm={() => confirm?.onConfirm()}
        onCancel={() => setConfirm(null)}
      />
    </div>
  );
}

/* ── Sub-components ── */

function ProviderPill({ name, state, failures }: { name: string; state: string; failures: number }) {
  const ok = state === "closed";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium ${
      ok ? "bg-status-running/15 text-status-running" : "bg-status-error/15 text-status-error"
    }`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {name} {state}
      {failures > 0 && <span className="text-text-muted">({failures})</span>}
    </span>
  );
}

function MetricCell({ label, value }: { label: string; value?: string | number }) {
  return (
    <div>
      <p className="text-[10px] text-text-muted">{label}</p>
      <p className="font-mono text-xs font-medium text-text-primary">{value ?? "--"}</p>
    </div>
  );
}
