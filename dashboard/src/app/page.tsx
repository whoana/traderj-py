"use client";

import { useEffect, useState, useCallback } from "react";
import dynamic from "next/dynamic";
import { Card } from "@/components/ui/Card";
import { PnLText } from "@/components/ui/PnLText";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";
import { formatKRW } from "@/lib/format";

const CandlestickChart = dynamic(
  () => import("@/components/chart/CandlestickChart"),
  { ssr: false },
);

interface BalanceData {
  strategy_id: string;
  krw: string;
  btc: string;
  total_value_krw: string;
  pnl_krw: string;
  pnl_pct: number;
  initial_krw: string;
}

interface EngineStatus {
  status: string;
  trading_mode: string;
  uptime_seconds?: number;
  strategies?: {
    strategy_id: string;
    preset: string;
    state: string;
    has_open_position: boolean;
  }[];
  regime?: {
    current: string;
    mapped_preset: string;
    confidence: number;
    last_switch_at: string;
  };
}

interface PositionData {
  strategy_id: string;
  symbol: string;
  side: string;
  entry_price: number;
  amount: number;
  current_price: number;
  unrealized_pnl: number;
  stop_loss: number | null;
  take_profit: number | null;
  status: string;
  opened_at: string;
}

interface MacroData {
  fear_greed?: number;
  funding_rate?: number;
  btc_dominance?: number;
  kimchi_premium?: number;
  market_score?: number;
}

interface CandleRaw {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

function formatUptime(seconds?: number): string {
  if (!seconds) return "--";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

function formatCompactKRW(value: number): string {
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)}B`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)}K`;
  return formatKRW(value);
}

export default function DashboardPage() {
  const [balance, setBalance] = useState<BalanceData | null>(null);
  const [engine, setEngine] = useState<EngineStatus | null>(null);
  const [positions, setPositions] = useState<PositionData[]>([]);
  const [macro, setMacro] = useState<MacroData | null>(null);
  const [btcPrice, setBtcPrice] = useState<{ price: number; change: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stopping, setStopping] = useState(false);
  const [showStopDialog, setShowStopDialog] = useState(false);

  const fetchAll = useCallback(async () => {
    try {
      const [bal, eng, pos, mac, candles] = await Promise.allSettled([
        api.get<BalanceData>("/engine/balance?strategy_id=STR-001"),
        api.get<EngineStatus>("/engine/engine/status"),
        api.get<{ items?: PositionData[]; positions?: PositionData[] }>(
          "/engine/positions?strategy_id=STR-001&status=open",
        ),
        api.get<MacroData>("/engine/macro/latest"),
        api.get<CandleRaw[]>("/engine/candles/BTC-KRW/1d?limit=2"),
      ]);

      if (bal.status === "fulfilled") setBalance(bal.value);
      if (eng.status === "fulfilled") setEngine(eng.value);
      if (pos.status === "fulfilled") {
        const data = pos.value;
        setPositions(data.items ?? data.positions ?? []);
      }
      if (mac.status === "fulfilled") setMacro(mac.value);
      if (candles.status === "fulfilled" && candles.value.length >= 1) {
        const latest = candles.value[candles.value.length - 1];
        const prev = candles.value.length >= 2 ? candles.value[candles.value.length - 2] : null;
        const change = prev ? ((latest.close - prev.close) / prev.close) * 100 : 0;
        setBtcPrice({ price: latest.close, change });
      }

      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 30_000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  const handleEmergencyStop = async () => {
    setShowStopDialog(false);
    setStopping(true);
    try {
      await api.post("/engine/engine/stop");
      await fetchAll();
    } catch {
      await fetchAll();
    } finally {
      setStopping(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-2 sm:gap-4 lg:grid-cols-4">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
        <SkeletonCard />
      </div>
    );
  }

  if (error) {
    return (
      <Card className="border-status-error">
        <p className="text-sm text-status-error">{error}</p>
        <button
          onClick={fetchAll}
          className="mt-2 text-sm text-accent hover:underline"
        >
          Retry
        </button>
      </Card>
    );
  }

  return (
    <div className="space-y-2 sm:space-y-4">
      {/* Status Bar */}
      <div className="flex items-center justify-between rounded-lg border border-border bg-bg-card px-3 py-2 sm:px-4 sm:py-2.5">
        <div className="flex items-center gap-2 sm:gap-3">
          <StatusBadge
            status={engine?.status === "running" ? "running" : "stopped"}
            label={engine?.status ?? "unknown"}
          />
          {engine?.strategies?.[0] && (
            <span className="rounded border border-border bg-bg-primary px-1.5 py-0.5 font-mono text-[10px] sm:text-xs text-text-secondary">
              {engine.strategies[0].strategy_id}
            </span>
          )}
          <span className="hidden text-xs text-text-muted sm:inline">
            Uptime: {formatUptime(engine?.uptime_seconds)}
          </span>
        </div>
        <button
          onClick={() => setShowStopDialog(true)}
          disabled={stopping || engine?.status !== "running"}
          className="flex items-center gap-1 rounded-md bg-status-error px-2 py-1 sm:px-3 sm:py-1.5 text-[11px] sm:text-xs font-semibold text-white transition-colors hover:bg-status-error/80 disabled:opacity-50"
        >
          <svg className="h-3 w-3 sm:h-3.5 sm:w-3.5" fill="currentColor" viewBox="0 0 20 20">
            <rect x="4" y="4" width="12" height="12" rx="2" />
          </svg>
          <span className="hidden sm:inline">Emergency Stop</span>
          <span className="sm:hidden">STOP</span>
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 gap-2 sm:gap-4 lg:grid-cols-4">
        {/* Balance */}
        <Card className="p-2.5 sm:p-4">
          <p className="text-[10px] sm:text-xs text-text-muted">Total Balance</p>
          <p className="mt-0.5 sm:mt-1 font-mono text-base sm:text-xl font-bold tabular-nums">
            {balance ? `₩${formatCompactKRW(Number(balance.total_value_krw))}` : "--"}
          </p>
          {balance && (
            <p className="text-[10px] sm:text-xs text-text-muted">
              <PnLText value={Number(balance.pnl_krw)} className="text-[10px] sm:text-xs" />
            </p>
          )}
        </Card>

        {/* Return */}
        <Card className="p-2.5 sm:p-4">
          <p className="text-[10px] sm:text-xs text-text-muted">Return</p>
          <div className="mt-0.5 sm:mt-1">
            {balance ? (
              <PnLText value={balance.pnl_pct} format="percent" className="text-base sm:text-xl font-bold" />
            ) : (
              <span className="text-base sm:text-xl text-text-muted">--</span>
            )}
          </div>
        </Card>

        {/* BTC Price */}
        <Card className="p-2.5 sm:p-4">
          <p className="text-[10px] sm:text-xs text-text-muted">BTC Price</p>
          <p className="mt-0.5 sm:mt-1 font-mono text-base sm:text-xl font-bold tabular-nums">
            {btcPrice ? `₩${formatCompactKRW(btcPrice.price)}` : "--"}
          </p>
          {btcPrice && (
            <p className={`font-mono text-[10px] sm:text-xs tabular-nums ${btcPrice.change >= 0 ? "text-up" : "text-down"}`}>
              {btcPrice.change >= 0 ? "\u25B2" : "\u25BC"} {btcPrice.change >= 0 ? "+" : ""}{btcPrice.change.toFixed(2)}%
            </p>
          )}
        </Card>

        {/* Regime */}
        <Card className="p-2.5 sm:p-4">
          <p className="text-[10px] sm:text-xs text-text-muted">Regime</p>
          <p className={`mt-0.5 sm:mt-1 font-mono text-xs sm:text-sm font-medium truncate ${
            engine?.regime?.current?.startsWith("bull_trend") ? "text-up" :
            engine?.regime?.current?.startsWith("bear_trend") ? "text-down" :
            "text-text-primary"
          }`}>
            {engine?.regime?.current ?? "--"}
          </p>
          <p className="text-[10px] sm:text-xs text-text-muted">
            conf: {engine?.regime?.confidence?.toFixed(4) ?? "--"}
          </p>
        </Card>
      </div>

      {/* Chart */}
      <Card title="BTC/KRW" className="p-2.5 sm:p-4">
        <CandlestickChart />
      </Card>

      {/* Bottom Grid: Positions + Macro */}
      <div className="grid grid-cols-1 gap-2 sm:gap-4 lg:grid-cols-2">
        {/* Open Positions */}
        <Card title="Open Positions" className="p-2.5 sm:p-4">
          {positions.length === 0 ? (
            <div className="py-6 text-center sm:py-8">
              <p className="text-sm text-text-muted">
                현재 열린 포지션이 없습니다
              </p>
              <p className="mt-1 text-xs text-text-muted">
                봇이 다음 매수 신호를 감시 중입니다
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {positions.map((pos, i) => (
                <div
                  key={i}
                  className="rounded-md border border-border p-2.5 sm:p-3"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">
                      {pos.symbol} {pos.side.toUpperCase()}
                    </span>
                    <PnLText value={pos.unrealized_pnl} className="text-sm" />
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-text-muted">
                    <div>
                      Entry: <span className="tabular-nums font-mono">{formatKRW(pos.entry_price)}</span>
                    </div>
                    <div>
                      Current: <span className="tabular-nums font-mono">{formatKRW(pos.current_price)}</span>
                    </div>
                    {pos.stop_loss && (
                      <div>
                        SL: <span className="tabular-nums font-mono text-down">{formatKRW(pos.stop_loss)}</span>
                      </div>
                    )}
                    {pos.take_profit && (
                      <div>
                        TP: <span className="tabular-nums font-mono text-up">{formatKRW(pos.take_profit)}</span>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Macro Indicators */}
        <Card title="Macro Indicators" className="p-2.5 sm:p-4">
          <div className="space-y-0">
            <MacroRow label="Fear & Greed" value={macro?.fear_greed} />
            <MacroRow
              label="Kimchi Premium"
              value={macro?.kimchi_premium != null ? `${macro.kimchi_premium >= 0 ? "+" : ""}${macro.kimchi_premium.toFixed(1)}%` : undefined}
              color={macro?.kimchi_premium != null ? (macro.kimchi_premium >= 0 ? "text-up" : "text-down") : undefined}
            />
            <MacroRow
              label="Funding Rate"
              value={macro?.funding_rate != null ? `${macro.funding_rate.toFixed(3)}%` : undefined}
            />
            <MacroRow
              label="BTC Dominance"
              value={macro?.btc_dominance != null ? `${macro.btc_dominance.toFixed(1)}%` : undefined}
            />
            <MacroRow
              label="Market Score"
              value={macro?.market_score != null ? macro.market_score.toFixed(2) : undefined}
              last
            />
          </div>
        </Card>
      </div>

      <ConfirmDialog
        open={showStopDialog}
        title="Engine Stop"
        description="엔진을 정지합니까? 트레이딩이 중단되며, 열린 포지션은 유지됩니다. API 서버는 계속 실행됩니다."
        confirmLabel="Stop Engine"
        variant="danger"
        onConfirm={handleEmergencyStop}
        onCancel={() => setShowStopDialog(false)}
      />
    </div>
  );
}

function MacroRow({
  label,
  value,
  color,
  last,
}: {
  label: string;
  value?: string | number;
  color?: string;
  last?: boolean;
}) {
  return (
    <div className={`flex items-center justify-between py-2 text-[13px] ${last ? "" : "border-b border-border/50"}`}>
      <span className="text-text-secondary">{label}</span>
      <span className={`font-mono font-medium tabular-nums ${color ?? "text-text-primary"}`}>
        {value ?? "--"}
      </span>
    </div>
  );
}
