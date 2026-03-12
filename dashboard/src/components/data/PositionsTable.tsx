"use client";

import { useOrderStore, type Position } from "@/stores/useOrderStore";
import DataTable from "./DataTable";
import { formatKRW } from "@/lib/format";
import { PnLText } from "@/components/ui/PnLText";

const columns = [
  { key: "strategy_id", header: "Strategy" },
  { key: "symbol", header: "Symbol" },
  {
    key: "side",
    header: "Side",
    render: (pos: Position) => (
      <span className={pos.side === "buy" ? "text-[var(--color-pnl-positive)]" : "text-[var(--color-pnl-negative)]"}>
        {pos.side.toUpperCase()}
      </span>
    ),
  },
  {
    key: "entry_price",
    header: "Entry",
    align: "right" as const,
    render: (pos: Position) => formatKRW(Number(pos.entry_price)),
  },
  {
    key: "current_price",
    header: "Current",
    align: "right" as const,
    render: (pos: Position) => formatKRW(Number(pos.current_price)),
  },
  {
    key: "amount",
    header: "Amount",
    align: "right" as const,
    render: (pos: Position) => <span>{pos.amount} BTC</span>,
  },
  {
    key: "stop_loss",
    header: "Stop Loss",
    align: "right" as const,
    render: (pos: Position) => (
      <span className="text-[var(--color-status-error)]">
        {formatKRW(Number(pos.stop_loss))}
      </span>
    ),
  },
  {
    key: "unrealized_pnl",
    header: "PnL",
    align: "right" as const,
    render: (pos: Position) => <PnLText value={Number(pos.unrealized_pnl)} />,
  },
];

export default function PositionsTable() {
  const { openPositions, loading } = useOrderStore();

  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold text-[var(--color-text-primary)]">
        Open Positions ({openPositions.length})
      </h3>
      <DataTable
        columns={columns}
        data={openPositions}
        keyExtractor={(p) => p.id}
        emptyMessage="No open positions"
        loading={loading}
      />
    </div>
  );
}
