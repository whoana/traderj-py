"use client";

import { useEffect, useRef, useCallback } from "react";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type HistogramData,
  type LineData,
  type Time,
  ColorType,
  CrosshairMode,
} from "lightweight-charts";
import type { CandleData } from "@/types/chart";
import type { EMAPoint, BBPoint } from "@/lib/indicators";

interface IndicatorOverlays {
  ema20?: EMAPoint[];
  ema50?: EMAPoint[];
  bb?: BBPoint[];
}

interface LWChartWrapperProps {
  data: CandleData[];
  width?: number;
  height?: number;
  onCrosshairMove?: (data: CandleData | null) => void;
  indicators?: IndicatorOverlays;
  visibleIndicators?: Set<string>;
}

function toChartData(candles: CandleData[]): CandlestickData<Time>[] {
  return candles.map((c) => ({
    time: c.time as Time,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  }));
}

function toVolumeData(candles: CandleData[]): HistogramData<Time>[] {
  return candles.map((c) => ({
    time: c.time as Time,
    value: c.volume,
    color: c.close >= c.open ? "rgba(38, 166, 154, 0.5)" : "rgba(239, 83, 80, 0.5)",
  }));
}

function toLineData(points: EMAPoint[]): LineData<Time>[] {
  return points.map((p) => ({ time: p.time as Time, value: p.value }));
}

export default function LWChartWrapper({
  data,
  width,
  height = 400,
  onCrosshairMove,
  indicators,
  visibleIndicators,
}: LWChartWrapperProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick", Time> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram", Time> | null>(null);
  const ema20Ref = useRef<ISeriesApi<"Line", Time> | null>(null);
  const ema50Ref = useRef<ISeriesApi<"Line", Time> | null>(null);
  const bbUpperRef = useRef<ISeriesApi<"Line", Time> | null>(null);
  const bbMiddleRef = useRef<ISeriesApi<"Line", Time> | null>(null);
  const bbLowerRef = useRef<ISeriesApi<"Line", Time> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      width: width ?? containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "var(--color-text-secondary)",
        fontSize: 12,
      },
      grid: {
        vertLines: { color: "var(--color-border)" },
        horzLines: { color: "var(--color-border)" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: {
        borderColor: "var(--color-border)",
      },
      timeScale: {
        borderColor: "var(--color-border)",
        timeVisible: true,
        secondsVisible: false,
      },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#26a69a",
      downColor: "#ef5350",
      borderVisible: false,
      wickUpColor: "#26a69a",
      wickDownColor: "#ef5350",
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });

    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    // Indicator overlay series
    const ema20Series = chart.addSeries(LineSeries, {
      color: "#f59e0b",
      lineWidth: 1,
      priceScaleId: "right",
      crosshairMarkerVisible: false,
    });
    const ema50Series = chart.addSeries(LineSeries, {
      color: "#8b5cf6",
      lineWidth: 1,
      priceScaleId: "right",
      crosshairMarkerVisible: false,
    });
    const bbUpper = chart.addSeries(LineSeries, {
      color: "#64748b",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      priceScaleId: "right",
      crosshairMarkerVisible: false,
    });
    const bbMid = chart.addSeries(LineSeries, {
      color: "#64748b",
      lineWidth: 1,
      priceScaleId: "right",
      crosshairMarkerVisible: false,
    });
    const bbLow = chart.addSeries(LineSeries, {
      color: "#64748b",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      priceScaleId: "right",
      crosshairMarkerVisible: false,
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;
    ema20Ref.current = ema20Series;
    ema50Ref.current = ema50Series;
    bbUpperRef.current = bbUpper;
    bbMiddleRef.current = bbMid;
    bbLowerRef.current = bbLow;

    if (onCrosshairMove) {
      chart.subscribeCrosshairMove((param) => {
        if (!param.time || !param.seriesData.get(candleSeries)) {
          onCrosshairMove(null);
          return;
        }
        const ohlc = param.seriesData.get(candleSeries) as CandlestickData<Time>;
        const vol = param.seriesData.get(volumeSeries) as HistogramData<Time>;
        onCrosshairMove({
          time: ohlc.time as number,
          open: ohlc.open,
          high: ohlc.high,
          low: ohlc.low,
          close: ohlc.close,
          volume: vol?.value ?? 0,
        });
      });
    }

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [height, width, onCrosshairMove]);

  useEffect(() => {
    if (candleSeriesRef.current && data.length > 0) {
      candleSeriesRef.current.setData(toChartData(data));
    }
    if (volumeSeriesRef.current && data.length > 0) {
      volumeSeriesRef.current.setData(toVolumeData(data));
    }
  }, [data]);

  // Update indicator series data
  useEffect(() => {
    const show = visibleIndicators ?? new Set<string>();

    if (ema20Ref.current) {
      ema20Ref.current.setData(
        show.has("ema20") && indicators?.ema20 ? toLineData(indicators.ema20) : [],
      );
    }
    if (ema50Ref.current) {
      ema50Ref.current.setData(
        show.has("ema50") && indicators?.ema50 ? toLineData(indicators.ema50) : [],
      );
    }
    if (bbUpperRef.current && bbMiddleRef.current && bbLowerRef.current) {
      if (show.has("bb") && indicators?.bb) {
        const bb = indicators.bb;
        bbUpperRef.current.setData(bb.map((p) => ({ time: p.time as Time, value: p.upper })));
        bbMiddleRef.current.setData(bb.map((p) => ({ time: p.time as Time, value: p.middle })));
        bbLowerRef.current.setData(bb.map((p) => ({ time: p.time as Time, value: p.lower })));
      } else {
        bbUpperRef.current.setData([]);
        bbMiddleRef.current.setData([]);
        bbLowerRef.current.setData([]);
      }
    }
  }, [indicators, visibleIndicators]);

  return (
    <div
      ref={containerRef}
      className="w-full"
      style={{ height }}
    />
  );
}
