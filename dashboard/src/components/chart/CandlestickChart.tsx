"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type HistogramData,
  type Time,
  ColorType,
} from "lightweight-charts";
import { api } from "@/lib/api";
import { Skeleton } from "@/components/ui/Skeleton";

interface CandleRaw {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

const TIMEFRAMES = ["1h", "4h", "1d"] as const;

export default function CandlestickChart() {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const [tf, setTf] = useState<string>("4h");
  const [loading, setLoading] = useState(true);

  const fetchAndRender = useCallback(async () => {
    if (!chartRef.current || !candleSeriesRef.current || !volumeSeriesRef.current) return;
    setLoading(true);
    try {
      const data = await api.get<CandleRaw[]>(
        `/engine/candles/BTC-KRW/${tf}?limit=200`,
      );

      const candles: CandlestickData<Time>[] = data.map((c) => ({
        time: (new Date(c.time).getTime() / 1000) as Time,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }));

      const volumes: HistogramData<Time>[] = data.map((c) => ({
        time: (new Date(c.time).getTime() / 1000) as Time,
        value: c.volume,
        color: c.close >= c.open ? "#16a34a40" : "#dc262640",
      }));

      candleSeriesRef.current.setData(candles);
      volumeSeriesRef.current.setData(volumes);
      chartRef.current.timeScale().fitContent();
    } catch {
      // silently fail — chart stays empty
    } finally {
      setLoading(false);
    }
  }, [tf]);

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
        priceFormatter: (price: number) => {
          if (price >= 1_000_000_000) return `${(price / 1_000_000_000).toFixed(1)}B`;
          if (price >= 1_000_000) return `${(price / 1_000_000).toFixed(1)}M`;
          if (price >= 1_000) return `${(price / 1_000).toFixed(0)}K`;
          return price.toFixed(0);
        },
      },
      timeScale: {
        borderColor: "#33415540",
        timeVisible: true,
      },
      handleScale: true,
      handleScroll: true,
    });

    const priceFormatter = (price: number) => {
      if (price >= 1_000_000_000) return `${(price / 1_000_000_000).toFixed(1)}B`;
      if (price >= 1_000_000) return `${(price / 1_000_000).toFixed(1)}M`;
      if (price >= 1_000) return `${(price / 1_000).toFixed(0)}K`;
      return price.toFixed(0);
    };

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#16a34a",
      downColor: "#dc2626",
      borderUpColor: "#16a34a",
      borderDownColor: "#dc2626",
      wickUpColor: "#16a34a",
      wickDownColor: "#dc2626",
      priceFormat: {
        type: "custom",
        formatter: priceFormatter,
      },
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });

    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        });
      }
    };

    const observer = new ResizeObserver(handleResize);
    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    fetchAndRender();
  }, [fetchAndRender]);

  return (
    <div>
      <div className="mb-2 flex gap-1">
        {TIMEFRAMES.map((t) => (
          <button
            key={t}
            onClick={() => setTf(t)}
            className={`rounded px-2 py-1 text-xs font-medium transition-colors ${
              tf === t
                ? "bg-accent text-white"
                : "text-text-muted hover:bg-bg-hover hover:text-text-primary"
            }`}
          >
            {t}
          </button>
        ))}
      </div>
      <div className="relative">
        {loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center">
            <Skeleton className="h-full w-full" />
          </div>
        )}
        <div ref={containerRef} className="h-[250px] sm:h-[400px] w-full" />
      </div>
    </div>
  );
}
