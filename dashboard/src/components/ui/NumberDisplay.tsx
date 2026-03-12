"use client";

import { cn } from "@/lib/cn";
import { formatBTC, formatKRW, formatNumber, formatPercent } from "@/lib/format";

interface NumberDisplayProps {
  value: number;
  format: "krw" | "btc" | "percent" | "number";
  showSign?: boolean;
  colorCode?: boolean;
  size?: "sm" | "md" | "lg";
  compact?: boolean;
  className?: string;
}

const sizeClasses = {
  sm: "text-sm",
  md: "text-base",
  lg: "text-xl font-semibold",
} as const;

export function NumberDisplay({
  value,
  format,
  showSign = false,
  colorCode = false,
  size = "md",
  compact = false,
  className,
}: NumberDisplayProps) {
  let formatted: string;
  switch (format) {
    case "krw":
      formatted = formatKRW(value, compact);
      break;
    case "btc":
      formatted = formatBTC(value);
      break;
    case "percent":
      formatted = formatPercent(value, showSign);
      break;
    case "number":
      formatted = formatNumber(value);
      break;
  }

  return (
    <span
      className={cn(
        "tabular-nums",
        sizeClasses[size],
        colorCode && value > 0 && "text-pnl-positive",
        colorCode && value < 0 && "text-pnl-negative",
        colorCode && value === 0 && "text-pnl-zero",
        className,
      )}
    >
      {formatted}
    </span>
  );
}
