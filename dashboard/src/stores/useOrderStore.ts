import { create } from "zustand";

import { fetchOrders as apiFetchOrders, fetchPositions as apiFetchPositions } from "@/lib/api";

export interface Position {
  id: string;
  symbol: string;
  side: string;
  entry_price: string;
  amount: string;
  current_price: string;
  stop_loss: string | null;
  unrealized_pnl: string;
  realized_pnl: string;
  status: "open" | "closed";
  strategy_id: string;
  opened_at: string;
  closed_at: string | null;
}

export interface Order {
  id: string;
  symbol: string;
  side: "buy" | "sell";
  order_type: "market" | "limit";
  amount: string;
  price: string;
  status: "pending" | "filled" | "cancelled" | "failed";
  strategy_id: string;
  idempotency_key: string;
  slippage_pct: string | null;
  created_at: string;
  filled_at: string | null;
}

interface OrderState {
  openPositions: Position[];
  closedPositions: Position[];
  orders: Order[];
  loading: boolean;
  setOpenPositions: (positions: Position[]) => void;
  setClosedPositions: (positions: Position[]) => void;
  setOrders: (orders: Order[]) => void;
  updatePosition: (id: string, update: Partial<Position>) => void;
  setLoading: (loading: boolean) => void;
  fetchPositions: () => Promise<void>;
  fetchOrders: () => Promise<void>;
}

export const useOrderStore = create<OrderState>((set) => ({
  openPositions: [],
  closedPositions: [],
  orders: [],
  loading: false,
  setOpenPositions: (positions) => set({ openPositions: positions }),
  setClosedPositions: (positions) => set({ closedPositions: positions }),
  setOrders: (orders) => set({ orders }),
  updatePosition: (id, update) =>
    set((state) => ({
      openPositions: state.openPositions.map((p) =>
        p.id === id ? { ...p, ...update } : p,
      ),
    })),
  setLoading: (loading) => set({ loading }),
  fetchPositions: async () => {
    set({ loading: true });
    try {
      const open = await apiFetchPositions({ status: "open", size: 100 });
      const closed = await apiFetchPositions({ status: "closed", size: 50 });
      set({
        openPositions: open.items as Position[],
        closedPositions: closed.items as Position[],
        loading: false,
      });
    } catch {
      set({ loading: false });
    }
  },
  fetchOrders: async () => {
    set({ loading: true });
    try {
      const result = await apiFetchOrders({ size: 100 });
      set({ orders: result.items as Order[], loading: false });
    } catch {
      set({ loading: false });
    }
  },
}));
