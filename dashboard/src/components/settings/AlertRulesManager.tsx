"use client";

import { useState } from "react";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import type { AlertRule, AlertRuleCreateRequest } from "@/types/api";

interface AlertRulesManagerProps {
  rules: AlertRule[];
  onToggle: (id: string) => void;
  onDelete: (id: string) => void;
  onAdd: (rule: AlertRuleCreateRequest) => void;
  loading: boolean;
}

const inputClass =
  "rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-3 py-1.5 text-sm";

const defaultNewRule: AlertRuleCreateRequest = {
  type: "price_above",
  condition: "gt",
  value: 0,
  channel: "slack",
};

export function AlertRulesManager({
  rules,
  onToggle,
  onDelete,
  onAdd,
  loading,
}: AlertRulesManagerProps) {
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [newRule, setNewRule] = useState<AlertRuleCreateRequest>(defaultNewRule);

  const handleAdd = () => {
    if (newRule.value === 0) return;
    onAdd(newRule);
    setNewRule(defaultNewRule);
  };

  return (
    <div className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
      <h2 className="text-lg font-semibold">Alert Rules</h2>

      {/* Rules List */}
      {loading ? (
        <div className="flex items-center justify-center gap-2 py-8 text-sm text-[var(--color-text-secondary)]">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-[var(--color-accent-blue)] border-t-transparent" />
          Loading...
        </div>
      ) : rules.length === 0 ? (
        <p className="py-4 text-center text-sm text-[var(--color-text-secondary)]">
          No alert rules configured
        </p>
      ) : (
        <div className="space-y-2">
          {rules.map((rule) => (
            <div
              key={rule.id}
              className="flex items-center justify-between rounded border border-[var(--color-border)] px-4 py-3"
            >
              <div className="flex items-center gap-4 text-sm">
                <span className="font-medium">{rule.type}</span>
                <span className="text-[var(--color-text-secondary)]">
                  {rule.condition} {rule.value}
                </span>
                <span className="rounded bg-[var(--color-bg-secondary)] px-2 py-0.5 text-xs">
                  {rule.channel}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => onToggle(rule.id)}
                  className={`relative h-5 w-9 rounded-full transition-colors ${
                    rule.enabled
                      ? "bg-[var(--color-pnl-positive)]"
                      : "bg-[var(--color-text-muted)]"
                  }`}
                  aria-label={`Toggle rule ${rule.type}`}
                >
                  <span
                    className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform ${
                      rule.enabled ? "left-[18px]" : "left-0.5"
                    }`}
                  />
                </button>
                <button
                  onClick={() => setDeleteTarget(rule.id)}
                  className="rounded px-2 py-1 text-xs text-[var(--color-pnl-negative)] hover:bg-[var(--color-bg-secondary)]"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add Form */}
      <div className="border-t border-[var(--color-border)] pt-4">
        <h3 className="mb-3 text-sm font-medium text-[var(--color-text-secondary)]">
          Add New Rule
        </h3>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm">
            <span className="text-[var(--color-text-secondary)]">Type</span>
            <select
              value={newRule.type}
              onChange={(e) => setNewRule({ ...newRule, type: e.target.value })}
              className={`mt-1 block ${inputClass}`}
            >
              <option value="price_above">Price Above</option>
              <option value="price_below">Price Below</option>
              <option value="pnl_threshold">PnL Threshold</option>
              <option value="drawdown">Drawdown</option>
            </select>
          </label>

          <label className="text-sm">
            <span className="text-[var(--color-text-secondary)]">Condition</span>
            <select
              value={newRule.condition}
              onChange={(e) => setNewRule({ ...newRule, condition: e.target.value })}
              className={`mt-1 block ${inputClass}`}
            >
              <option value="gt">Greater Than</option>
              <option value="lt">Less Than</option>
              <option value="gte">Greater or Equal</option>
              <option value="lte">Less or Equal</option>
              <option value="eq">Equal</option>
            </select>
          </label>

          <label className="text-sm">
            <span className="text-[var(--color-text-secondary)]">Value</span>
            <input
              type="number"
              value={newRule.value}
              onChange={(e) => setNewRule({ ...newRule, value: Number(e.target.value) })}
              className={`mt-1 block w-32 ${inputClass}`}
            />
          </label>

          <label className="text-sm">
            <span className="text-[var(--color-text-secondary)]">Channel</span>
            <select
              value={newRule.channel}
              onChange={(e) => setNewRule({ ...newRule, channel: e.target.value })}
              className={`mt-1 block ${inputClass}`}
            >
              <option value="slack">Slack</option>
              <option value="email">Email</option>
              <option value="telegram">Telegram</option>
            </select>
          </label>

          <button
            type="button"
            onClick={handleAdd}
            className="rounded-lg bg-[var(--color-accent-blue)] px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-[var(--color-accent-blue)]/90"
          >
            Add Rule
          </button>
        </div>
      </div>

      {/* Confirm Delete Dialog */}
      <ConfirmDialog
        open={deleteTarget !== null}
        onConfirm={() => {
          if (deleteTarget) onDelete(deleteTarget);
          setDeleteTarget(null);
        }}
        onCancel={() => setDeleteTarget(null)}
        title="Delete Alert Rule"
        description="Are you sure you want to delete this alert rule? This action cannot be undone."
        confirmLabel="Delete"
        variant="danger"
        countdownSeconds={3}
      />
    </div>
  );
}
