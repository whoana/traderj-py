import { create } from "zustand";
import type { CandleData } from "@/types/chart";
import type { Timeframe } from "@/lib/constants";
import { fetchCandles as apiFetchCandles } from "@/lib/api";

interface CandleState {
  candles: Record<Timeframe, CandleData[]>;
  activeTimeframe: Timeframe;
  loading: boolean;
  setCandles: (timeframe: Timeframe, data: CandleData[]) => void;
  appendCandle: (timeframe: Timeframe, candle: CandleData) => void;
  updateLastCandle: (timeframe: Timeframe, candle: Partial<CandleData>) => void;
  setActiveTimeframe: (timeframe: Timeframe) => void;
  setLoading: (loading: boolean) => void;
  fetch: (symbol: string, timeframe: Timeframe) => Promise<void>;
}

export const useCandleStore = create<CandleState>((set) => ({
  candles: { "15m": [], "1h": [], "4h": [], "1d": [] },
  activeTimeframe: "4h",
  loading: false,
  setCandles: (timeframe, data) =>
    set((state) => ({
      candles: { ...state.candles, [timeframe]: data },
      loading: false,
    })),
  appendCandle: (timeframe, candle) =>
    set((state) => ({
      candles: {
        ...state.candles,
        [timeframe]: [...state.candles[timeframe], candle],
      },
    })),
  updateLastCandle: (timeframe, update) =>
    set((state) => {
      const current = state.candles[timeframe];
      if (current.length === 0) return state;
      const last = { ...current[current.length - 1], ...update };
      return {
        candles: {
          ...state.candles,
          [timeframe]: [...current.slice(0, -1), last],
        },
      };
    }),
  setActiveTimeframe: (timeframe) => set({ activeTimeframe: timeframe }),
  setLoading: (loading) => set({ loading }),
  fetch: async (symbol, timeframe) => {
    set({ loading: true });
    try {
      // API expects dash-separated: BTC-KRW
      const sym = symbol.replace("/", "-");
      const data = await apiFetchCandles(sym, timeframe);
      const candles: CandleData[] = data.map((c) => ({
        time: Math.floor(new Date(c.time).getTime() / 1000) as CandleData["time"],
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
        volume: c.volume,
      }));
      set((state) => ({
        candles: { ...state.candles, [timeframe]: candles },
        loading: false,
      }));
    } catch {
      set({ loading: false });
    }
  },
}));
