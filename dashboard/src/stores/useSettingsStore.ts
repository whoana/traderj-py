import { create } from "zustand";

import {
  fetchBotConfig,
  updateBotConfig,
  fetchAlertRules,
  createAlertRule,
  deleteAlertRule,
  toggleAlertRule,
} from "@/lib/api";
import type {
  StrategyConfigResponse,
  AlertRule,
  AlertRuleCreateRequest,
} from "@/types/api";

interface SettingsState {
  config: StrategyConfigResponse | null;
  alertRules: AlertRule[];
  loading: boolean;
  saving: boolean;
  error: string | null;
  setConfig: (config: StrategyConfigResponse) => void;
  setAlertRules: (rules: AlertRule[]) => void;
  setLoading: (loading: boolean) => void;
  setSaving: (saving: boolean) => void;
  setError: (error: string | null) => void;
  fetchConfig: (strategyId: string) => Promise<void>;
  saveConfig: (strategyId: string, values: Partial<StrategyConfigResponse>) => Promise<void>;
  fetchRules: (strategyId: string) => Promise<void>;
  addRule: (strategyId: string, rule: AlertRuleCreateRequest) => Promise<void>;
  removeRule: (strategyId: string, ruleId: string) => Promise<void>;
  toggleRule: (strategyId: string, ruleId: string) => Promise<void>;
}

export const useSettingsStore = create<SettingsState>((set, get) => ({
  config: null,
  alertRules: [],
  loading: false,
  saving: false,
  error: null,
  setConfig: (config) => set({ config }),
  setAlertRules: (alertRules) => set({ alertRules }),
  setLoading: (loading) => set({ loading }),
  setSaving: (saving) => set({ saving }),
  setError: (error) => set({ error, loading: false }),
  fetchConfig: async (strategyId) => {
    set({ loading: true, error: null });
    try {
      const config = await fetchBotConfig(strategyId);
      set({ config, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },
  saveConfig: async (strategyId, values) => {
    set({ saving: true, error: null });
    try {
      const config = await updateBotConfig(strategyId, values);
      set({ config, saving: false });
    } catch (e) {
      set({ error: (e as Error).message, saving: false });
    }
  },
  fetchRules: async (strategyId) => {
    set({ loading: true, error: null });
    try {
      const alertRules = await fetchAlertRules(strategyId);
      set({ alertRules, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },
  addRule: async (strategyId, rule) => {
    set({ saving: true, error: null });
    try {
      const newRule = await createAlertRule(strategyId, rule);
      set({ alertRules: [...get().alertRules, newRule], saving: false });
    } catch (e) {
      set({ error: (e as Error).message, saving: false });
    }
  },
  removeRule: async (strategyId, ruleId) => {
    set({ saving: true, error: null });
    try {
      await deleteAlertRule(strategyId, ruleId);
      set({
        alertRules: get().alertRules.filter((r) => r.id !== ruleId),
        saving: false,
      });
    } catch (e) {
      set({ error: (e as Error).message, saving: false });
    }
  },
  toggleRule: async (strategyId, ruleId) => {
    try {
      const updated = await toggleAlertRule(strategyId, ruleId);
      set({
        alertRules: get().alertRules.map((r) => (r.id === ruleId ? updated : r)),
      });
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },
}));
