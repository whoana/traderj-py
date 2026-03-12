import { describe, expect, it, vi, beforeEach } from "vitest";
import { useSettingsStore } from "../useSettingsStore";

vi.mock("@/lib/api", () => ({
  fetchBotConfig: vi.fn().mockResolvedValue({
    scoring_mode: "weighted",
    entry_mode: "market",
    timeframes: ["1m"],
    buy_threshold: 70,
    sell_threshold: -30,
    stop_loss_pct: 5,
    max_position_pct: 25,
    trend_filter: true,
  }),
  updateBotConfig: vi.fn().mockResolvedValue({
    scoring_mode: "majority",
    entry_mode: "market",
    timeframes: ["1m"],
    buy_threshold: 70,
    sell_threshold: -30,
    stop_loss_pct: 5,
    max_position_pct: 25,
    trend_filter: true,
  }),
  fetchAlertRules: vi.fn().mockResolvedValue([
    { id: "1", type: "price_above", condition: "gt", value: 100, channel: "slack", enabled: true, created_at: "2024-01-01" },
  ]),
  createAlertRule: vi.fn().mockResolvedValue({
    id: "2", type: "price_below", condition: "lt", value: 50, channel: "email", enabled: true, created_at: "2024-01-02",
  }),
  deleteAlertRule: vi.fn().mockResolvedValue(undefined),
  toggleAlertRule: vi.fn().mockResolvedValue({
    id: "1", type: "price_above", condition: "gt", value: 100, channel: "slack", enabled: false, created_at: "2024-01-01",
  }),
}));

describe("useSettingsStore", () => {
  beforeEach(() => {
    useSettingsStore.setState({
      config: null,
      alertRules: [],
      loading: false,
      saving: false,
      error: null,
    });
  });

  it("starts with null config and empty rules", () => {
    const state = useSettingsStore.getState();
    expect(state.config).toBeNull();
    expect(state.alertRules).toEqual([]);
  });

  it("fetchConfig sets config from API", async () => {
    await useSettingsStore.getState().fetchConfig("STR-001");
    const state = useSettingsStore.getState();
    expect(state.config).not.toBeNull();
    expect(state.config?.scoring_mode).toBe("weighted");
    expect(state.loading).toBe(false);
  });

  it("saveConfig updates config", async () => {
    await useSettingsStore.getState().saveConfig("STR-001", { scoring_mode: "majority" });
    const state = useSettingsStore.getState();
    expect(state.config?.scoring_mode).toBe("majority");
  });

  it("addRule appends to alertRules", async () => {
    await useSettingsStore.getState().fetchRules("STR-001");
    expect(useSettingsStore.getState().alertRules.length).toBe(1);
    await useSettingsStore.getState().addRule("STR-001", {
      type: "price_below", condition: "lt", value: 50, channel: "email",
    });
    expect(useSettingsStore.getState().alertRules.length).toBe(2);
  });
});
