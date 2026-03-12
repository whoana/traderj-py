import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { BacktestMetricsCard } from "../BacktestMetricsCard";

const summary = {
  sharpe: 1.5,
  sortino: 2.1,
  max_drawdown: -500000,
  calmar: 1.2,
  win_rate: 55.5,
  profit_factor: 1.8,
  total_trades: 120,
  total_pnl: 1500000,
};

describe("BacktestMetricsCard", () => {
  it("renders all 8 metric labels", () => {
    render(<BacktestMetricsCard summary={summary} />);
    expect(screen.getByText("Sharpe Ratio")).toBeInTheDocument();
    expect(screen.getByText("Sortino Ratio")).toBeInTheDocument();
    expect(screen.getByText("Max Drawdown")).toBeInTheDocument();
    expect(screen.getByText("Calmar Ratio")).toBeInTheDocument();
    expect(screen.getByText("Win Rate")).toBeInTheDocument();
    expect(screen.getByText("Profit Factor")).toBeInTheDocument();
    expect(screen.getByText("Total Trades")).toBeInTheDocument();
    expect(screen.getByText("Total PnL")).toBeInTheDocument();
  });

  it("formats values correctly", () => {
    render(<BacktestMetricsCard summary={summary} />);
    const sortinos = screen.getAllByText("2.10");
    expect(sortinos.length).toBeGreaterThanOrEqual(1);
    const trades = screen.getAllByText("120");
    expect(trades.length).toBeGreaterThanOrEqual(1);
  });

  it("shows drawdown with negative color", () => {
    const { container } = render(<BacktestMetricsCard summary={summary} />);
    const drawdownCard = container.querySelectorAll(".text-\\[var\\(--color-pnl-negative\\)\\]");
    expect(drawdownCard.length).toBeGreaterThan(0);
  });
});
