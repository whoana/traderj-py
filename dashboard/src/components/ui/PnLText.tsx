"use client";

import { cn } from "@/lib/cn";
import { formatKRW, formatPercent } from "@/lib/format";

interface PnLTextProps {
  value: number;
  format?: "krw" | "percent";
  size?: "sm" | "md" | "lg";
  className?: string;
}

const sizeClasses = {
  sm: "text-sm",
  md: "text-base",
  lg: "text-xl font-semibold",
} as const;

export function PnLText({
  value,
  format = "krw",
  size = "md",
  className,
}: PnLTextProps) {
  const arrow = value > 0 ? "\u2191 " : value < 0 ? "\u2193 " : "";
  const formatted =
    arrow + (format === "krw" ? formatKRW(value) : formatPercent(value, true));

  return (
    <span
      className={cn(
        "tabular-nums",
        sizeClasses[size],
        value > 0 && "text-pnl-positive",
        value < 0 && "text-pnl-negative",
        value === 0 && "text-pnl-zero",
        className,
      )}
    >
      {formatted}
    </span>
  );
}
