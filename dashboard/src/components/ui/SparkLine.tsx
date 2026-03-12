"use client";

import { LineChart, Line, ResponsiveContainer } from "recharts";

interface SparkLineProps {
  data: number[];
  color?: string;
  height?: number;
  width?: number;
}

export function SparkLine({
  data,
  color = "var(--color-accent-blue)",
  height = 24,
  width = 80,
}: SparkLineProps) {
  const chartData = data.map((v, i) => ({ i, v }));

  return (
    <ResponsiveContainer width={width} height={height}>
      <LineChart data={chartData}>
        <Line
          type="monotone"
          dataKey="v"
          stroke={color}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
