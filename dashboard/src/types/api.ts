/** API response types — mirrors api/schemas/responses.py */

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

export interface BotResponse {
  strategy_id: string;
  state: string;
  trading_mode: string;
  started_at: string | null;
  updated_at: string;
}

export interface BotControlResponse {
  strategy_id: string;
  action: string;
  success: boolean;
  message: string;
}

export interface PositionResponse {
  id: string;
  symbol: string;
  side: string;
  entry_price: string;
  amount: string;
  current_price: string;
  stop_loss: string | null;
  unrealized_pnl: string;
  realized_pnl: string;
  status: string;
  strategy_id: string;
  opened_at: string;
  closed_at: string | null;
}

export interface OrderResponse {
  id: string;
  symbol: string;
  side: string;
  order_type: string;
  amount: string;
  price: string;
  status: string;
  strategy_id: string;
  idempotency_key: string;
  slippage_pct: string | null;
  created_at: string;
  filled_at: string | null;
}

export interface CandleResponse {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface SignalResponse {
  id: string;
  symbol: string;
  strategy_id: string;
  direction: string;
  score: number;
  components: Record<string, number>;
  details: Record<string, unknown>;
  created_at: string;
}

export interface DailyPnLResponse {
  date: string;
  strategy_id: string;
  realized: string;
  unrealized: string;
  trade_count: number;
}

export interface PnLSummaryResponse {
  strategy_id: string;
  total_realized: string;
  total_trades: number;
  win_rate: number;
  avg_pnl: string;
  max_drawdown: string;
}

export interface RiskStateResponse {
  strategy_id: string;
  consecutive_losses: number;
  daily_pnl: string;
  cooldown_until: string | null;
  last_updated: string;
}

export interface MacroSnapshotResponse {
  timestamp: string;
  fear_greed: number;
  funding_rate: number;
  btc_dominance: number;
  btc_dom_7d_change: number;
  dxy: number;
  kimchi_premium: number;
  market_score: number;
}

export interface PnLAnalyticsResponse {
  strategy_id: string;
  days: number;
  total_pnl: string;
  max_drawdown: string;
  peak_pnl: string;
  total_trades: number;
  curve: {
    date: string;
    daily_pnl: string;
    cumulative_pnl: string;
    drawdown: string;
    trade_count: number;
  }[];
}

export interface StrategyCompareResponse {
  days: number;
  strategies: {
    strategy_id: string;
    total_pnl: string;
    total_trades: number;
    avg_daily_pnl: string;
    sharpe_ratio: number;
    trading_days: number;
  }[];
}

export interface StrategyConfigResponse {
  scoring_mode: string;
  entry_mode: string;
  timeframes: string[];
  buy_threshold: number;
  sell_threshold: number;
  stop_loss_pct: number;
  max_position_pct: number;
  trend_filter: boolean;
}

export interface AlertRule {
  id: string;
  type: string;
  condition: string;
  value: number;
  channel: string;
  enabled: boolean;
  created_at: string;
}

export interface AlertRuleCreateRequest {
  type: string;
  condition: string;
  value: number;
  channel: string;
}

export interface BacktestResult {
  id: string;
  strategy_id: string;
  timeframe: string;
  period: string;
  params: Record<string, unknown>;
  summary: {
    sharpe: number;
    sortino: number;
    max_drawdown: number;
    calmar: number;
    win_rate: number;
    profit_factor: number;
    total_trades: number;
    total_pnl: number;
  };
  equity_curve: { time: string; equity: number }[];
  trades: {
    id: string;
    entry_time: string;
    exit_time: string;
    side: string;
    entry_price: number;
    exit_price: number;
    amount: number;
    pnl: number;
    reason: string;
  }[];
}

export interface IndicatorData {
  time: number;
  ema20?: number;
  ema50?: number;
  bb_upper?: number;
  bb_middle?: number;
  bb_lower?: number;
  rsi?: number;
}
