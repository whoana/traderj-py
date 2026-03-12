import { describe, expect, it } from "vitest";
import { calculateEMA, calculateBB, calculateRSI } from "../indicators";
import type { CandleData } from "@/types/chart";

function makeCandles(closes: number[]): CandleData[] {
  return closes.map((close, i) => ({
    time: 1000 + i * 60,
    open: close - 1,
    high: close + 2,
    low: close - 2,
    close,
    volume: 100,
  }));
}

describe("calculateEMA", () => {
  it("returns correct EMA values for known input", () => {
    const data = makeCandles([10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]);
    const ema = calculateEMA(data, 5);
    expect(ema.length).toBe(7); // 11 - 5 + 1
    // First EMA = SMA of first 5 = (10+11+12+13+14)/5 = 12
    expect(ema[0].value).toBeCloseTo(12, 5);
    // All values should be increasing
    for (let i = 1; i < ema.length; i++) {
      expect(ema[i].value).toBeGreaterThan(ema[i - 1].value);
    }
  });

  it("returns empty for insufficient data", () => {
    const data = makeCandles([10, 11, 12]);
    const ema = calculateEMA(data, 5);
    expect(ema.length).toBe(0);
  });
});

describe("calculateBB", () => {
  it("returns correct bands for known input", () => {
    const closes = Array.from({ length: 25 }, (_, i) => 100 + i);
    const data = makeCandles(closes);
    const bb = calculateBB(data, 20, 2);
    expect(bb.length).toBe(6); // 25 - 20 + 1
    // Upper should be above middle, lower should be below
    for (const point of bb) {
      expect(point.upper).toBeGreaterThan(point.middle);
      expect(point.lower).toBeLessThan(point.middle);
    }
  });
});

describe("calculateRSI", () => {
  it("returns RSI between 0-100", () => {
    const closes = [44, 44.34, 44.09, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
      45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64];
    const data = makeCandles(closes);
    const rsi = calculateRSI(data, 14);
    expect(rsi.length).toBeGreaterThan(0);
    for (const point of rsi) {
      expect(point.value).toBeGreaterThanOrEqual(0);
      expect(point.value).toBeLessThanOrEqual(100);
    }
  });
});
