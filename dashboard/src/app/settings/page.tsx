"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { useSettingsStore } from "@/stores/useSettingsStore";
import { StrategyConfigForm } from "@/components/settings/StrategyConfigForm";
import { AlertRulesManager } from "@/components/settings/AlertRulesManager";
import type { StrategyConfigFormValues } from "@/lib/schemas/strategy-config";

export default function SettingsPage() {
  const [strategyId, setStrategyId] = useState("STR-001");
  const {
    config,
    alertRules,
    loading,
    saving,
    error,
    fetchConfig,
    saveConfig,
    fetchRules,
    addRule,
    removeRule,
    toggleRule,
  } = useSettingsStore();

  useEffect(() => {
    fetchConfig(strategyId);
    fetchRules(strategyId);
  }, [strategyId, fetchConfig, fetchRules]);

  const handleSaveConfig = async (values: StrategyConfigFormValues) => {
    await saveConfig(strategyId, values);
    toast.success("Configuration saved");
  };

  return (
    <div className="mx-auto max-w-7xl p-4">
      <h1 className="mb-6 text-2xl font-bold">Settings</h1>

      {/* Strategy Selector */}
      <div className="mb-6">
        <label className="text-sm text-[var(--color-text-secondary)]">
          Strategy:
          <input
            type="text"
            value={strategyId}
            onChange={(e) => setStrategyId(e.target.value)}
            className="ml-2 rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-3 py-1.5 text-sm"
          />
        </label>
      </div>

      {loading && (
        <p className="text-sm text-[var(--color-text-secondary)]">Loading...</p>
      )}
      {error && <p className="text-sm text-red-500">{error}</p>}

      <div className="space-y-6">
        {config && (
          <StrategyConfigForm
            defaultValues={config as StrategyConfigFormValues}
            onSubmit={handleSaveConfig}
            saving={saving}
          />
        )}

        <AlertRulesManager
          rules={alertRules}
          onToggle={(id) => toggleRule(strategyId, id)}
          onDelete={(id) => {
            removeRule(strategyId, id);
            toast.success("Rule deleted");
          }}
          onAdd={(rule) => {
            addRule(strategyId, rule);
            toast.success("Rule added");
          }}
          loading={loading}
        />
      </div>
    </div>
  );
}
