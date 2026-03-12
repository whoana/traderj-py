import { create } from "zustand";
import type { TickerUpdate } from "@/types/chart";

interface TickerState {
  ticker: TickerUpdate | null;
  lastUpdated: number;
  updateTicker: (data: TickerUpdate) => void;
}

export const useTickerStore = create<TickerState>((set) => ({
  ticker: null,
  lastUpdated: 0,
  updateTicker: (data) =>
    set({ ticker: data, lastUpdated: Date.now() }),
}));
