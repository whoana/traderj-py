import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { StrategyConfigForm } from "../StrategyConfigForm";

const defaultValues = {
  scoring_mode: "weighted" as const,
  entry_mode: "market" as const,
  timeframes: ["1m"],
  buy_threshold: 70,
  sell_threshold: -30,
  stop_loss_pct: 5,
  max_position_pct: 25,
  trend_filter: true,
};

describe("StrategyConfigForm", () => {
  it("renders all form sections", () => {
    render(
      <StrategyConfigForm defaultValues={defaultValues} onSubmit={vi.fn()} saving={false} />,
    );
    expect(screen.getAllByText("Strategy Configuration").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Scoring Mode").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Entry Mode").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Buy Threshold (0-100)").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Stop Loss %").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Enable Trend Filter").length).toBeGreaterThanOrEqual(1);
  });

  it("renders default values correctly", () => {
    render(
      <StrategyConfigForm defaultValues={defaultValues} onSubmit={vi.fn()} saving={false} />,
    );
    const buyInputs = screen.getAllByDisplayValue("70");
    expect(buyInputs.length).toBeGreaterThanOrEqual(1);
  });

  it("disables submit button when saving", () => {
    render(
      <StrategyConfigForm defaultValues={defaultValues} onSubmit={vi.fn()} saving={true} />,
    );
    const btn = screen.getByText("Saving...");
    expect(btn).toBeDisabled();
  });

  it("shows Save Configuration when not saving", () => {
    render(
      <StrategyConfigForm defaultValues={defaultValues} onSubmit={vi.fn()} saving={false} />,
    );
    const buttons = screen.getAllByText("Save Configuration");
    expect(buttons.length).toBeGreaterThanOrEqual(1);
  });

  it("renders timeframe fields", () => {
    render(
      <StrategyConfigForm defaultValues={defaultValues} onSubmit={vi.fn()} saving={false} />,
    );
    const inputs = screen.getAllByDisplayValue("1m");
    expect(inputs.length).toBeGreaterThanOrEqual(1);
    const addButtons = screen.getAllByText("+ Add Timeframe");
    expect(addButtons.length).toBeGreaterThanOrEqual(1);
  });
});
