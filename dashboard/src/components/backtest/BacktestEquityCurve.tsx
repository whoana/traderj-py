"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { formatKRW } from "@/lib/format";

interface BacktestEquityCurveProps {
  data: { time: string; equity: number }[];
}

export function BacktestEquityCurve({ data }: BacktestEquityCurveProps) {
  if (data.length === 0) {
    return (
      <div className="flex h-[300px] items-center justify-center text-sm text-[var(--color-text-secondary)]">
        No equity curve data
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-4">
      <h3 className="mb-4 text-sm font-semibold">Equity Curve</h3>
      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={data}>
          <defs>
            <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="var(--color-accent-blue)" stopOpacity={0.3} />
              <stop offset="95%" stopColor="var(--color-accent-blue)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-default)" />
          <XAxis
            dataKey="time"
            tick={{ fontSize: 11, fill: "var(--color-text-secondary)" }}
            tickFormatter={(v) => {
              const d = new Date(v);
              return `${d.getMonth() + 1}/${d.getDate()}`;
            }}
          />
          <YAxis
            tick={{ fontSize: 11, fill: "var(--color-text-secondary)" }}
            tickFormatter={(v) => formatKRW(v, true)}
          />
          <Tooltip
            formatter={(value) => [formatKRW(Number(value)), "Equity"]}
            labelFormatter={(label) => new Date(label).toLocaleDateString("ko-KR")}
            contentStyle={{
              backgroundColor: "var(--color-bg-card)",
              border: "1px solid var(--color-border-default)",
              borderRadius: "8px",
              fontSize: "12px",
            }}
          />
          <Area
            type="monotone"
            dataKey="equity"
            stroke="var(--color-accent-blue)"
            fill="url(#equityGradient)"
            strokeWidth={2}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
