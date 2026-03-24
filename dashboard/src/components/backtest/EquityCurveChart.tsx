"use client";

import { useEffect, useRef, useState } from "react";
import {
  createChart,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type Time,
  ColorType,
  LineStyle,
} from "lightweight-charts";

/* ── Strategy colors (from design §9.2) ── */
const STRATEGY_COLORS: Record<string, string> = {
  "STR-001": "#6366f1",
  "STR-002": "#f59e0b",
  "STR-003": "#10b981",
  "STR-004": "#ef4444",
  "STR-005": "#8b5cf6",
  "STR-006": "#06b6d4",
  "STR-007": "#f97316",
  "STR-008": "#ec4899",
};

const AI_COLOR = "#3b82f6";

interface EquityPoint {
  time: string;
  equity: number;
}

interface StrategyEquity {
  strategy_id: string;
  name: string;
  equity_curve?: EquityPoint[];
}

interface Props {
  mode: "compare" | "single" | "ai_regime";
  strategies: StrategyEquity[];
  aiEquity?: EquityPoint[];
  initialBalance: number;
}

function toLineData(curve: EquityPoint[], init: number): LineData<Time>[] {
  return curve
    .filter((p) => p.time && p.equity != null)
    .map((p) => ({
      time: (new Date(p.time).getTime() / 1000) as Time,
      value: ((p.equity - init) / init) * 100, // normalize to % return
    }));
}

function pctFormatter(v: number): string {
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

export default function EquityCurveChart({ mode, strategies, aiEquity, initialBalance }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesMapRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const [hidden, setHidden] = useState<Set<string>>(new Set());

  // Collect legend entries
  const legendEntries: { id: string; label: string; color: string }[] = [];
  if (mode === "ai_regime" && aiEquity?.length) {
    legendEntries.push({ id: "__ai__", label: "AI Regime", color: AI_COLOR });
  }
  for (const s of strategies) {
    if (s.equity_curve?.length) {
      legendEntries.push({
        id: s.strategy_id,
        label: `${s.strategy_id} ${s.name}`,
        color: STRATEGY_COLORS[s.strategy_id] || "#94a3b8",
      });
    }
  }

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#94a3b8",
        fontFamily: "Inter, sans-serif",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "#33415520" },
        horzLines: { color: "#33415520" },
      },
      crosshair: {
        vertLine: { color: "#64748b80", width: 1 },
        horzLine: { color: "#64748b80", width: 1 },
      },
      rightPriceScale: {
        borderColor: "#33415540",
      },
      localization: {
        priceFormatter: pctFormatter,
      },
      timeScale: {
        borderColor: "#33415540",
        timeVisible: true,
      },
      handleScale: true,
      handleScroll: true,
    });

    chartRef.current = chart;
    const newMap = new Map<string, ISeriesApi<"Line">>();

    // AI Regime equity line
    if (mode === "ai_regime" && aiEquity?.length) {
      const data = toLineData(aiEquity, initialBalance);
      if (data.length > 0) {
        const series = chart.addSeries(LineSeries, {
          color: AI_COLOR,
          lineWidth: 3,
          priceFormat: { type: "custom", formatter: pctFormatter },
        });
        series.setData(data);
        newMap.set("__ai__", series);
      }
    }

    // Strategy lines
    for (const s of strategies) {
      if (!s.equity_curve?.length) continue;
      const data = toLineData(s.equity_curve, initialBalance);
      if (data.length === 0) continue;

      const color = STRATEGY_COLORS[s.strategy_id] || "#94a3b8";
      const isCompare = mode === "compare";
      const isAiMode = mode === "ai_regime";

      const series = chart.addSeries(LineSeries, {
        color,
        lineWidth: isCompare ? 2 : isAiMode ? 1 : 2,
        lineStyle: isAiMode ? LineStyle.Dashed : LineStyle.Solid,
        priceFormat: { type: "custom", formatter: pctFormatter },
        ...(isAiMode ? { priceScaleId: "right" } : {}),
      });
      series.setData(data);
      newMap.set(s.strategy_id, series);
    }

    seriesMapRef.current = newMap;
    chart.timeScale().fitContent();

    // Resize observer
    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        });
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesMapRef.current.clear();
    };
  }, [mode, strategies, aiEquity, initialBalance]);

  // Toggle series visibility
  const toggleSeries = (id: string) => {
    const series = seriesMapRef.current.get(id);
    if (!series) return;

    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
        series.applyOptions({ visible: true });
      } else {
        next.add(id);
        series.applyOptions({ visible: false });
      }
      return next;
    });
  };

  if (legendEntries.length === 0) return null;

  return (
    <div className="rounded-lg border border-border bg-bg-card p-4">
      <h3 className="mb-2 text-sm font-medium text-text-primary">Equity Curve (수익률 %)</h3>
      {/* Legend */}
      <div className="mb-2 flex flex-wrap gap-x-3 gap-y-1">
        {legendEntries.map((e) => (
          <button
            key={e.id}
            onClick={() => toggleSeries(e.id)}
            className={`flex items-center gap-1.5 text-[10px] sm:text-xs transition-opacity ${hidden.has(e.id) ? "opacity-30" : "opacity-100"}`}
          >
            <span className="inline-block h-2 w-4 rounded-sm" style={{ backgroundColor: e.color }} />
            <span className="text-text-secondary">{e.label}</span>
          </button>
        ))}
      </div>
      {/* Chart */}
      <div ref={containerRef} className="h-[280px] sm:h-[360px] w-full" />
    </div>
  );
}
