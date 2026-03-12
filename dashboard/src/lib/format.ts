const krwFormatter = new Intl.NumberFormat("ko-KR", {
  style: "currency",
  currency: "KRW",
  maximumFractionDigits: 0,
});

const krwCompactFormatter = new Intl.NumberFormat("ko-KR", {
  style: "currency",
  currency: "KRW",
  notation: "compact",
  maximumFractionDigits: 1,
});

export function formatKRW(value: number, compact = false): string {
  return compact
    ? krwCompactFormatter.format(value)
    : krwFormatter.format(value);
}

export function formatBTC(value: number): string {
  return `${value.toFixed(8)} BTC`;
}

export function formatPercent(value: number, showSign = true): string {
  const sign = showSign && value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

export function formatNumber(value: number, decimals = 0): string {
  return new Intl.NumberFormat("ko-KR", {
    maximumFractionDigits: decimals,
  }).format(value);
}

export function formatPrice(value: number): string {
  if (value >= 1_000_000) return formatKRW(value);
  return value.toFixed(2);
}

export function formatDate(date: Date | string): string {
  const d = typeof date === "string" ? new Date(date) : date;
  return d.toLocaleDateString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

export function formatDateTime(date: Date | string): string {
  const d = typeof date === "string" ? new Date(date) : date;
  return d.toLocaleString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}
