const krwFmt = new Intl.NumberFormat("ko-KR", {
  style: "currency",
  currency: "KRW",
  maximumFractionDigits: 0,
});

const numFmt = new Intl.NumberFormat("ko-KR", {
  maximumFractionDigits: 2,
});

const pctFmt = new Intl.NumberFormat("ko-KR", {
  style: "percent",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatKRW(value: number): string {
  return krwFmt.format(value);
}

export function formatNumber(value: number): string {
  return numFmt.format(value);
}

export function formatPercent(value: number): string {
  return pctFmt.format(value / 100);
}

export function formatBTC(value: number): string {
  return `${value.toFixed(8)} BTC`;
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleString("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
