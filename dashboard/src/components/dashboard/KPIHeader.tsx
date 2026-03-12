"use client";

import { useMemo } from "react";
import { NumberDisplay } from "@/components/ui/NumberDisplay";
import { PnLText } from "@/components/ui/PnLText";
import { useTickerStore } from "@/stores/useTickerStore";
import { useBotStore } from "@/stores/useBotStore";

export function KPIHeader() {
  const ticker = useTickerStore((s) => s.ticker);
  const bots = useBotStore((s) => s.bots);

  const activeBotCount = useMemo(
    () => bots.filter((b) => !["idle", "paused", "shutting_down"].includes(b.state)).length,
    [bots],
  );

  return (
    <div className="sticky top-[var(--topnav-height)] z-30 flex h-[var(--kpi-height)] items-center gap-6 border-b border-border-default bg-bg-primary/80 px-4 backdrop-blur-sm" aria-live="polite" aria-label="Market overview">
      {/* BTC Price */}
      <div className="flex flex-col">
        <span className="text-xs text-text-muted">BTC/KRW</span>
        {ticker ? (
          <NumberDisplay
            value={ticker.price}
            format="krw"
            size="lg"
          />
        ) : (
          <span className="text-lg font-semibold text-text-muted">--</span>
        )}
      </div>

      {/* 24h Change */}
      <div className="flex flex-col">
        <span className="text-xs text-text-muted">24h Change</span>
        {ticker ? (
          <PnLText value={ticker.changePct24h} format="percent" size="md" />
        ) : (
          <span className="text-text-muted">--</span>
        )}
      </div>

      {/* Portfolio */}
      <div className="flex flex-col">
        <span className="text-xs text-text-muted">Portfolio</span>
        <span className="text-lg font-semibold text-text-muted">--</span>
      </div>

      {/* Total PnL */}
      <div className="flex flex-col">
        <span className="text-xs text-text-muted">Total PnL</span>
        <span className="text-text-muted">--</span>
      </div>

      {/* Active Bots */}
      <div className="flex flex-col">
        <span className="text-xs text-text-muted">Active Bots</span>
        <NumberDisplay
          value={activeBotCount}
          format="number"
          size="lg"
        />
      </div>
    </div>
  );
}
