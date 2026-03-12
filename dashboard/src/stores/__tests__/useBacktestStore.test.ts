import { describe, expect, it, vi, beforeEach } from "vitest";
import { useBacktestStore } from "../useBacktestStore";

vi.mock("@/lib/api", () => ({
  fetchBacktestResults: vi.fn().mockResolvedValue([
    {
      id: "bt-1",
      strategy_id: "STR-001",
      timeframe: "1h",
      period: "2024-01-01~2024-06-30",
      params: {},
      summary: {
        sharpe: 1.5, sortino: 2.0, max_drawdown: -5000, calmar: 1.2,
        win_rate: 55, profit_factor: 1.8, total_trades: 100, total_pnl: 50000,
      },
      equity_curve: [],
      trades: [],
    },
  ]),
}));

describe("useBacktestStore", () => {
  beforeEach(() => {
    useBacktestStore.setState({
      results: [],
      selectedId: null,
      loading: false,
      error: null,
    });
  });

  it("starts with empty results", () => {
    const state = useBacktestStore.getState();
    expect(state.results).toEqual([]);
    expect(state.selectedId).toBeNull();
  });

  it("fetch sets results and selects first", async () => {
    await useBacktestStore.getState().fetch("STR-001");
    const state = useBacktestStore.getState();
    expect(state.results.length).toBe(1);
    expect(state.selectedId).toBe("bt-1");
  });

  it("selectResult updates selectedId", () => {
    useBacktestStore.getState().selectResult("bt-2");
    expect(useBacktestStore.getState().selectedId).toBe("bt-2");
  });
});
