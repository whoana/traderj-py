import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { BacktestTradeList } from "../BacktestTradeList";

const trades = [
  {
    id: "t1",
    entry_time: "2024-01-15T10:00:00Z",
    exit_time: "2024-01-15T12:00:00Z",
    side: "buy",
    entry_price: 50000000,
    exit_price: 51000000,
    amount: 0.1,
    pnl: 100000,
    reason: "signal",
  },
  {
    id: "t2",
    entry_time: "2024-01-16T10:00:00Z",
    exit_time: "2024-01-16T14:00:00Z",
    side: "sell",
    entry_price: 51000000,
    exit_price: 50500000,
    amount: 0.1,
    pnl: -50000,
    reason: "stop_loss",
  },
];

describe("BacktestTradeList", () => {
  it("renders trade rows", () => {
    render(<BacktestTradeList trades={trades} />);
    expect(screen.getByText("BUY")).toBeInTheDocument();
    expect(screen.getByText("SELL")).toBeInTheDocument();
  });

  it("shows empty message when no trades", () => {
    render(<BacktestTradeList trades={[]} />);
    expect(screen.getByText("No trades in this backtest")).toBeInTheDocument();
  });

  it("shows trade count in header", () => {
    render(<BacktestTradeList trades={trades} />);
    const headers = screen.getAllByText(/Trades \(2\)/);
    expect(headers.length).toBeGreaterThanOrEqual(1);
  });
});
