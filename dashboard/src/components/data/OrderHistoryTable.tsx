"use client";

import { useOrderStore, type Order } from "@/stores/useOrderStore";
import DataTable from "./DataTable";
import { formatKRW, formatDateTime } from "@/lib/format";

const ORDER_STATUS_COLORS: Record<string, string> = {
  pending: "text-[var(--color-status-warning)]",
  filled: "text-[var(--color-status-success)]",
  cancelled: "text-[var(--color-text-tertiary)]",
  failed: "text-[var(--color-status-error)]",
};

const columns = [
  {
    key: "created_at",
    header: "Time",
    render: (order: Order) => (
      <span className="text-xs">{formatDateTime(order.created_at)}</span>
    ),
  },
  { key: "strategy_id", header: "Strategy" },
  {
    key: "side",
    header: "Side",
    render: (order: Order) => (
      <span className={order.side === "buy" ? "text-[var(--color-pnl-positive)]" : "text-[var(--color-pnl-negative)]"}>
        {order.side.toUpperCase()}
      </span>
    ),
  },
  { key: "order_type", header: "Type" },
  {
    key: "amount",
    header: "Amount",
    align: "right" as const,
    render: (order: Order) => <span>{order.amount} BTC</span>,
  },
  {
    key: "price",
    header: "Price",
    align: "right" as const,
    render: (order: Order) => (
      <span>{order.price ? formatKRW(Number(order.price)) : "-"}</span>
    ),
  },
  {
    key: "status",
    header: "Status",
    render: (order: Order) => (
      <span className={`text-xs font-medium ${ORDER_STATUS_COLORS[order.status] ?? ""}`}>
        {order.status}
      </span>
    ),
  },
];

export default function OrderHistoryTable() {
  const { orders, loading } = useOrderStore();

  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold text-[var(--color-text-primary)]">
        Order History ({orders.length})
      </h3>
      <DataTable
        columns={columns}
        data={orders}
        keyExtractor={(o) => o.id}
        emptyMessage="No orders yet"
        loading={loading}
      />
    </div>
  );
}
