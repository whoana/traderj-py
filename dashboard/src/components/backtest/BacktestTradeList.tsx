"use client";

import DataTable from "@/components/data/DataTable";
import { PnLText } from "@/components/ui/PnLText";
import { formatKRW, formatNumber } from "@/lib/format";
import type { BacktestResult } from "@/types/api";

type Trade = BacktestResult["trades"][number];

interface BacktestTradeListProps {
  trades: Trade[];
}

const columns = [
  {
    key: "entry_time",
    header: "Entry Time",
    render: (t: Trade) => new Date(t.entry_time).toLocaleString("ko-KR"),
  },
  {
    key: "exit_time",
    header: "Exit Time",
    render: (t: Trade) => new Date(t.exit_time).toLocaleString("ko-KR"),
  },
  {
    key: "side",
    header: "Side",
    render: (t: Trade) => (
      <span
        className={
          t.side === "buy"
            ? "text-[var(--color-pnl-positive)]"
            : "text-[var(--color-pnl-negative)]"
        }
      >
        {t.side.toUpperCase()}
      </span>
    ),
  },
  {
    key: "entry_price",
    header: "Entry Price",
    align: "right" as const,
    render: (t: Trade) => formatKRW(t.entry_price),
  },
  {
    key: "exit_price",
    header: "Exit Price",
    align: "right" as const,
    render: (t: Trade) => formatKRW(t.exit_price),
  },
  {
    key: "amount",
    header: "Amount",
    align: "right" as const,
    render: (t: Trade) => formatNumber(t.amount),
  },
  {
    key: "pnl",
    header: "PnL",
    align: "right" as const,
    render: (t: Trade) => <PnLText value={t.pnl} format="krw" size="sm" />,
  },
  {
    key: "reason",
    header: "Reason",
    render: (t: Trade) => t.reason,
  },
];

export function BacktestTradeList({ trades }: BacktestTradeListProps) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)]">
      <h3 className="border-b border-[var(--color-border)] px-4 py-3 text-sm font-semibold">
        Trades ({trades.length})
      </h3>
      <DataTable
        columns={columns}
        data={trades}
        keyExtractor={(t) => t.id}
        emptyMessage="No trades in this backtest"
      />
    </div>
  );
}
