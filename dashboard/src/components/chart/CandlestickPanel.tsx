"use client";

import { useState, useCallback, useMemo } from "react";
import LWChartWrapper from "./LWChartWrapper";
import { useCandleStore } from "@/stores/useCandleStore";
import { TIMEFRAMES, type Timeframe } from "@/lib/constants";
import { formatKRW, formatNumber } from "@/lib/format";
import { calculateEMA, calculateBB } from "@/lib/indicators";
import type { CandleData } from "@/types/chart";

export default function CandlestickPanel() {
  const { candles, activeTimeframe, setActiveTimeframe, loading } = useCandleStore();
  const [crosshair, setCrosshair] = useState<CandleData | null>(null);

  const [visibleIndicators, setVisibleIndicators] = useState<Set<string>>(
    () => new Set(["ema20"]),
  );

  const data = candles[activeTimeframe];
  const lastCandle = data.length > 0 ? data[data.length - 1] : null;
  const display = crosshair ?? lastCandle;

  const indicators = useMemo(() => {
    if (data.length === 0) return {};
    return {
      ema20: calculateEMA(data, 20),
      ema50: calculateEMA(data, 50),
      bb: calculateBB(data, 20, 2),
    };
  }, [data]);

  const toggleIndicator = useCallback((key: string) => {
    setVisibleIndicators((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const handleCrosshairMove = useCallback((d: CandleData | null) => {
    setCrosshair(d);
  }, []);

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)]" aria-label="BTC/KRW candlestick chart">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-2">
        <div className="flex items-center gap-4">
          <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
            BTC/KRW
          </h3>
          {display && (
            <div className="flex items-center gap-3 text-xs text-[var(--color-text-secondary)]">
              <span>O <span className="text-[var(--color-text-primary)]">{formatKRW(display.open)}</span></span>
              <span>H <span className="text-[var(--color-text-primary)]">{formatKRW(display.high)}</span></span>
              <span>L <span className="text-[var(--color-text-primary)]">{formatKRW(display.low)}</span></span>
              <span>C <span className="text-[var(--color-text-primary)]">{formatKRW(display.close)}</span></span>
              <span>V <span className="text-[var(--color-text-primary)]">{formatNumber(display.volume)}</span></span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-3">
          {/* Indicator toggles */}
          <div className="flex gap-1">
            {(["ema20", "ema50", "bb"] as const).map((key) => (
              <button
                key={key}
                onClick={() => toggleIndicator(key)}
                aria-pressed={visibleIndicators.has(key)}
                className={`rounded px-2 py-1 text-xs transition-colors ${
                  visibleIndicators.has(key)
                    ? "bg-[var(--color-accent)] text-white"
                    : "text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)]"
                }`}
              >
                {key.toUpperCase()}
              </button>
            ))}
          </div>

          {/* Timeframe selector */}
          <div
            className="flex gap-1"
            role="toolbar"
            aria-label="Timeframe selector"
            onKeyDown={(e) => {
              const idx = TIMEFRAMES.indexOf(activeTimeframe);
              if (e.key === "ArrowRight" && idx < TIMEFRAMES.length - 1) {
                setActiveTimeframe(TIMEFRAMES[idx + 1] as Timeframe);
              } else if (e.key === "ArrowLeft" && idx > 0) {
                setActiveTimeframe(TIMEFRAMES[idx - 1] as Timeframe);
              }
            }}
          >
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf}
                onClick={() => setActiveTimeframe(tf as Timeframe)}
                aria-pressed={activeTimeframe === tf}
                tabIndex={activeTimeframe === tf ? 0 : -1}
                className={`rounded px-2 py-1 text-xs transition-colors ${
                  activeTimeframe === tf
                    ? "bg-[var(--color-accent)] text-white"
                    : "text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)]"
                }`}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Chart */}
      <div className="relative" style={{ contain: "layout style paint" }}>
        {loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-[var(--color-bg-card)]/80">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-[var(--color-accent)] border-t-transparent" />
          </div>
        )}
        {data.length > 0 ? (
          <LWChartWrapper
            data={data}
            height={400}
            onCrosshairMove={handleCrosshairMove}
            indicators={indicators}
            visibleIndicators={visibleIndicators}
          />
        ) : (
          <div className="flex h-[400px] items-center justify-center text-[var(--color-text-tertiary)]">
            No data available
          </div>
        )}
      </div>
    </div>
  );
}
