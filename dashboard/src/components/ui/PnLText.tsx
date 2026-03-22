import { cn } from "@/lib/cn";
import { formatKRW, formatPercent } from "@/lib/format";

interface PnLTextProps {
  value: number;
  format?: "krw" | "percent";
  className?: string;
}

export function PnLText({ value, format = "krw", className }: PnLTextProps) {
  const color =
    value > 0 ? "text-up" : value < 0 ? "text-down" : "text-neutral";
  const prefix = value > 0 ? "+" : "";
  const formatted =
    format === "percent" ? formatPercent(value) : formatKRW(value);

  return (
    <span className={cn("tabular-nums font-mono font-medium", color, className)}>
      {prefix}
      {formatted}
    </span>
  );
}
