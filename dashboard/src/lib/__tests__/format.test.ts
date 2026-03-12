import { describe, expect, it } from "vitest";
import {
  formatBTC,
  formatKRW,
  formatNumber,
  formatPercent,
} from "../format";

describe("formatKRW", () => {
  it("formats positive values", () => {
    expect(formatKRW(145230000)).toMatch(/145,230,000/);
  });

  it("formats zero", () => {
    expect(formatKRW(0)).toMatch(/0/);
  });

  it("formats negative values", () => {
    expect(formatKRW(-500000)).toMatch(/500,000/);
  });
});

describe("formatBTC", () => {
  it("formats with 8 decimal places", () => {
    expect(formatBTC(0.00123456)).toBe("0.00123456 BTC");
  });

  it("formats zero", () => {
    expect(formatBTC(0)).toBe("0.00000000 BTC");
  });
});

describe("formatPercent", () => {
  it("shows + sign for positive", () => {
    expect(formatPercent(2.345)).toBe("+2.35%");
  });

  it("shows - sign for negative", () => {
    expect(formatPercent(-1.5)).toBe("-1.50%");
  });

  it("hides sign when showSign=false", () => {
    expect(formatPercent(2.345, false)).toBe("2.35%");
  });

  it("formats zero", () => {
    expect(formatPercent(0)).toBe("0.00%");
  });
});

describe("formatNumber", () => {
  it("formats with thousands separator", () => {
    expect(formatNumber(1234567)).toMatch(/1,234,567/);
  });
});
