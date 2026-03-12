import { describe, expect, it } from "vitest";
import { strategyConfigSchema } from "../schemas/strategy-config";

const validConfig = {
  scoring_mode: "weighted" as const,
  entry_mode: "market" as const,
  timeframes: ["1m", "5m"],
  buy_threshold: 70,
  sell_threshold: -30,
  stop_loss_pct: 5,
  max_position_pct: 25,
  trend_filter: true,
};

describe("strategyConfigSchema", () => {
  it("accepts valid config", () => {
    const result = strategyConfigSchema.safeParse(validConfig);
    expect(result.success).toBe(true);
  });

  it("rejects empty timeframes array", () => {
    const result = strategyConfigSchema.safeParse({
      ...validConfig,
      timeframes: [],
    });
    expect(result.success).toBe(false);
  });

  it("rejects buy_threshold > 100", () => {
    const result = strategyConfigSchema.safeParse({
      ...validConfig,
      buy_threshold: 101,
    });
    expect(result.success).toBe(false);
  });

  it("rejects buy_threshold < 0", () => {
    const result = strategyConfigSchema.safeParse({
      ...validConfig,
      buy_threshold: -1,
    });
    expect(result.success).toBe(false);
  });

  it("rejects sell_threshold > 0", () => {
    const result = strategyConfigSchema.safeParse({
      ...validConfig,
      sell_threshold: 1,
    });
    expect(result.success).toBe(false);
  });

  it("rejects sell_threshold < -100", () => {
    const result = strategyConfigSchema.safeParse({
      ...validConfig,
      sell_threshold: -101,
    });
    expect(result.success).toBe(false);
  });

  it("rejects stop_loss_pct < 0.1", () => {
    const result = strategyConfigSchema.safeParse({
      ...validConfig,
      stop_loss_pct: 0.05,
    });
    expect(result.success).toBe(false);
  });

  it("rejects invalid scoring_mode", () => {
    const result = strategyConfigSchema.safeParse({
      ...validConfig,
      scoring_mode: "invalid",
    });
    expect(result.success).toBe(false);
  });
});
