import { create } from "zustand";

import { fetchBots as apiFetchBots } from "@/lib/api";

export interface BotStatus {
  strategy_id: string;
  state: string;
  trading_mode: string;
  started_at: string | null;
  updated_at: string;
}

interface BotState {
  bots: BotStatus[];
  loading: boolean;
  error: string | null;
  setBots: (bots: BotStatus[]) => void;
  updateBot: (strategyId: string, update: Partial<BotStatus>) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  fetch: () => Promise<void>;
}

export const useBotStore = create<BotState>((set) => ({
  bots: [],
  loading: false,
  error: null,
  setBots: (bots) => set({ bots, loading: false, error: null }),
  updateBot: (strategyId, update) =>
    set((state) => ({
      bots: state.bots.map((b) =>
        b.strategy_id === strategyId ? { ...b, ...update } : b,
      ),
    })),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error, loading: false }),
  fetch: async () => {
    set({ loading: true, error: null });
    try {
      const bots = await apiFetchBots();
      set({ bots, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },
}));
