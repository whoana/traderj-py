import { create } from "zustand";

import { fetchBacktestResults } from "@/lib/api";
import type { BacktestResult } from "@/types/api";

interface BacktestState {
  results: BacktestResult[];
  selectedId: string | null;
  loading: boolean;
  error: string | null;
  setResults: (results: BacktestResult[]) => void;
  selectResult: (id: string) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  fetch: (strategyId: string) => Promise<void>;
}

export const useBacktestStore = create<BacktestState>((set) => ({
  results: [],
  selectedId: null,
  loading: false,
  error: null,
  setResults: (results) => set({ results }),
  selectResult: (id) => set({ selectedId: id }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error, loading: false }),
  fetch: async (strategyId) => {
    set({ loading: true, error: null });
    try {
      const results = await fetchBacktestResults(strategyId);
      set({
        results,
        selectedId: results.length > 0 ? results[0].id : null,
        loading: false,
      });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },
}));
