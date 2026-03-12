"use client";

import { useEffect } from "react";

import { wsClient } from "@/lib/ws-client";
import { useTickerStore } from "@/stores/useTickerStore";
import { useBotStore } from "@/stores/useBotStore";
import { useOrderStore } from "@/stores/useOrderStore";
import { useCandleStore } from "@/stores/useCandleStore";
import type { TickerUpdate } from "@/types/chart";

/**
 * Hook that establishes WS connection and routes channel data to stores.
 * Call once at the root layout/page level.
 */
export function useRealtimeData() {
  const updateTicker = useTickerStore((s) => s.updateTicker);
  const updateBot = useBotStore((s) => s.updateBot);
  const setOpenPositions = useOrderStore((s) => s.setOpenPositions);
  const openPositions = useOrderStore((s) => s.openPositions);
  const updateLastCandle = useCandleStore((s) => s.updateLastCandle);
  const activeTimeframe = useCandleStore((s) => s.activeTimeframe);

  useEffect(() => {
    wsClient.connect();

    let tickerRafId: number | null = null;
    const unsubTicker = wsClient.subscribe("ticker", (data) => {
      if (tickerRafId !== null) return;
      tickerRafId = requestAnimationFrame(() => {
        const d = data as TickerUpdate;
        updateTicker(d);
        // Update last candle with latest price for real-time chart.
        // high/low are computed correctly in the store's updateLastCandle
        // via Object.assign merge — we pass the price so the store can
        // compare against existing candle high/low.
        const candles = useCandleStore.getState().candles[activeTimeframe];
        const last = candles.length > 0 ? candles[candles.length - 1] : null;
        updateLastCandle(activeTimeframe, {
          close: d.price,
          ...(last ? {
            high: Math.max(last.high, d.price),
            low: Math.min(last.low, d.price),
          } : {}),
        });
        tickerRafId = null;
      });
    });

    const unsubBot = wsClient.subscribe("bot_status", (data) => {
      const d = data as { strategy_id: string; state: string; trading_mode: string };
      updateBot(d.strategy_id, { state: d.state, trading_mode: d.trading_mode });
    });

    const unsubPositions = wsClient.subscribe("positions", (data) => {
      const d = data as { position_id: string; status: string; unrealized_pnl: string };
      // Update in-memory position with latest unrealized PnL
      const updated = openPositions.map((p) =>
        p.id === d.position_id ? { ...p, unrealized_pnl: d.unrealized_pnl, status: d.status as "open" | "closed" } : p,
      );
      setOpenPositions(updated);
    });

    const unsubOrders = wsClient.subscribe("orders", (data) => {
      const d = data as { order_id: string; status: string };
      // Order status updates handled via store refresh
      void d;
    });

    return () => {
      if (tickerRafId !== null) cancelAnimationFrame(tickerRafId);
      unsubTicker();
      unsubBot();
      unsubPositions();
      unsubOrders();
      wsClient.disconnect();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
}
