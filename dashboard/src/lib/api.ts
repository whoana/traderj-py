/**
 * Typed API call wrappers — replace MSW mock data with real endpoints.
 */

import type {
  AlertRule,
  AlertRuleCreateRequest,
  BacktestResult,
  BotControlResponse,
  BotResponse,
  CandleResponse,
  DailyPnLResponse,
  MacroSnapshotResponse,
  OrderResponse,
  PaginatedResponse,
  PnLAnalyticsResponse,
  PnLSummaryResponse,
  PositionResponse,
  RiskStateResponse,
  SignalResponse,
  StrategyCompareResponse,
  StrategyConfigResponse,
} from "@/types/api";

import { api } from "./api-client";

// ── Bots ──────────────────────────────────────────────────────────

export const fetchBots = () => api.get<BotResponse[]>("/bots");

export const fetchBot = (strategyId: string) =>
  api.get<BotResponse>(`/bots/${strategyId}`);

export const startBot = (strategyId: string) =>
  api.post<BotControlResponse>(`/bots/${strategyId}/start`);

export const stopBot = (strategyId: string) =>
  api.post<BotControlResponse>(`/bots/${strategyId}/stop`);

export const pauseBot = (strategyId: string) =>
  api.post<BotControlResponse>(`/bots/${strategyId}/pause`);

export const resumeBot = (strategyId: string) =>
  api.post<BotControlResponse>(`/bots/${strategyId}/resume`);

export const emergencyExit = (strategyId: string) =>
  api.post<BotControlResponse>(`/bots/${strategyId}/emergency-exit`);

export const emergencyStopAll = () =>
  api.post<BotControlResponse>("/bots/emergency-stop");

export const closeAllPositions = () =>
  api.post<BotControlResponse>("/positions/close-all");

// ── Positions ─────────────────────────────────────────────────────

export const fetchPositions = (params?: {
  strategy_id?: string;
  status?: string;
  page?: number;
  size?: number;
}) => api.get<PaginatedResponse<PositionResponse>>("/positions", params);

// ── Orders ────────────────────────────────────────────────────────

export const fetchOrders = (params?: {
  strategy_id?: string;
  status?: string;
  page?: number;
  size?: number;
}) => api.get<PaginatedResponse<OrderResponse>>("/orders", params);

// ── Candles ───────────────────────────────────────────────────────

export const fetchCandles = (symbol: string, timeframe: string, limit = 200) =>
  api.get<CandleResponse[]>(`/candles/${symbol}/${timeframe}`, { limit });

// ── Signals ───────────────────────────────────────────────────────

export const fetchSignals = (params?: {
  strategy_id?: string;
  page?: number;
  size?: number;
}) => api.get<PaginatedResponse<SignalResponse>>("/signals", params);

// ── PnL ───────────────────────────────────────────────────────────

export const fetchDailyPnL = (strategyId: string, days = 30) =>
  api.get<DailyPnLResponse[]>("/pnl/daily", {
    strategy_id: strategyId,
    days,
  });

export const fetchPnLSummary = (strategyId?: string) =>
  api.get<PnLSummaryResponse[]>("/pnl/summary", {
    strategy_id: strategyId,
  });

// ── Risk ──────────────────────────────────────────────────────────

export const fetchRiskState = (strategyId: string) =>
  api.get<RiskStateResponse>(`/risk/${strategyId}`);

// ── Macro ─────────────────────────────────────────────────────────

export const fetchMacro = () =>
  api.get<MacroSnapshotResponse>("/macro/latest");

// ── Analytics ─────────────────────────────────────────────────────

export const fetchPnLAnalytics = (strategyId: string, days = 30) =>
  api.get<PnLAnalyticsResponse>("/analytics/pnl", {
    strategy_id: strategyId,
    days,
  });

export const fetchStrategyCompare = (strategyIds: string[], days = 30) =>
  api.get<StrategyCompareResponse>("/analytics/compare", {
    strategy_ids: strategyIds.join(","),
    days,
  });

// ── Bot Config ───────────────────────────────────────────────────

export const fetchBotConfig = (strategyId: string) =>
  api.get<StrategyConfigResponse>(`/bots/${strategyId}/config`);

export const updateBotConfig = (
  strategyId: string,
  config: Partial<StrategyConfigResponse>,
) => api.put<StrategyConfigResponse>(`/bots/${strategyId}/config`, config);

// ── Alert Rules ──────────────────────────────────────────────────

export const fetchAlertRules = (strategyId: string) =>
  api.get<AlertRule[]>(`/bots/${strategyId}/alerts`);

export const createAlertRule = (
  strategyId: string,
  rule: AlertRuleCreateRequest,
) => api.post<AlertRule>(`/bots/${strategyId}/alerts`, rule);

export const deleteAlertRule = (strategyId: string, ruleId: string) =>
  api.delete<void>(`/bots/${strategyId}/alerts/${ruleId}`);

export const toggleAlertRule = (strategyId: string, ruleId: string) =>
  api.put<AlertRule>(`/bots/${strategyId}/alerts/${ruleId}/toggle`);

// ── Backtest ─────────────────────────────────────────────────────

export const fetchBacktestResults = (strategyId: string) =>
  api.get<BacktestResult[]>(`/backtest/${strategyId}`);
