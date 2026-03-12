export const BOT_STATE_COLORS: Record<string, string> = {
  idle: "var(--color-status-idle)",
  starting: "var(--color-status-scanning)",
  scanning: "var(--color-status-scanning)",
  validating: "var(--color-status-scanning)",
  executing: "var(--color-status-executing)",
  logging: "var(--color-status-monitoring)",
  monitoring: "var(--color-status-monitoring)",
  paused: "var(--color-status-paused)",
  shutting_down: "var(--color-status-error)",
} as const;

export const BOT_STATE_LABELS: Record<string, string> = {
  idle: "Idle",
  starting: "Starting",
  scanning: "Scanning",
  validating: "Validating",
  executing: "Executing",
  logging: "Logging",
  monitoring: "Monitoring",
  paused: "Paused",
  shutting_down: "Shutting Down",
} as const;

export const TIMEFRAMES = ["15m", "1h", "4h", "1d"] as const;
export type Timeframe = (typeof TIMEFRAMES)[number];

export const TIMEFRAME_MS: Record<Timeframe, number> = {
  "15m": 15 * 60 * 1000,
  "1h": 60 * 60 * 1000,
  "4h": 4 * 60 * 60 * 1000,
  "1d": 24 * 60 * 60 * 1000,
} as const;

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
export const WS_BASE_URL =
  process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws/v1/stream";

export function getWsUrl(): string {
  if (typeof window === "undefined") return WS_BASE_URL;
  const apiKey = localStorage.getItem("traderj-api-key") ?? "dev-api-key";
  return `${WS_BASE_URL}?api_key=${apiKey}`;
}

/** @deprecated Use WS_BASE_URL */
export const WS_URL = WS_BASE_URL;
