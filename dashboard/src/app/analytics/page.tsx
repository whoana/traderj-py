"use client";

import { useEffect, useState, useCallback } from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import { Card } from "@/components/ui/Card";
import { PnLText } from "@/components/ui/PnLText";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";
import { formatKRW, formatTime } from "@/lib/format";

interface PnLCurvePoint {
  date: string;
  daily_pnl: string;
  cumulative_pnl: string;
  drawdown: string;
  trade_count: number;
}

interface PnLAnalytics {
  strategy_id: string;
  days: number;
  total_pnl: string;
  max_drawdown: string;
  peak_pnl: string;
  total_trades: number;
  curve: PnLCurvePoint[];
}

interface PnLSummary {
  strategy_id: string;
  total_realized: string;
  total_trades: number;
  win_rate: number;
  avg_pnl: string;
  max_drawdown: string;
}

interface OrderData {
  id: string;
  symbol: string;
  side: string;
  amount: string;
  price: string;
  status: string;
  strategy_id: string;
  created_at: string;
}

export default function AnalyticsPage() {
  const [analytics, setAnalytics] = useState<PnLAnalytics | null>(null);
  const [summary, setSummary] = useState<PnLSummary[] | null>(null);
  const [orders, setOrders] = useState<OrderData[]>([]);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [anal, summ, ord] = await Promise.allSettled([
        api.get<PnLAnalytics>(
          `/engine/analytics/pnl?strategy_id=STR-001&days=${days}`,
        ),
        api.get<PnLSummary[]>("/engine/pnl/summary?strategy_id=STR-001"),
        api.get<{ items?: OrderData[]; orders?: OrderData[] }>(
          "/engine/orders?strategy_id=STR-001&status=filled",
        ),
      ]);

      if (anal.status === "fulfilled") setAnalytics(anal.value);
      if (summ.status === "fulfilled") setSummary(summ.value);
      if (ord.status === "fulfilled") {
        const data = ord.value;
        setOrders(data.items ?? data.orders ?? []);
      }
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
        <SkeletonCard />
      </div>
    );
  }

  const s = summary?.[0];
  const curveData = (analytics?.curve ?? []).map((p) => ({
    date: p.date,
    cumPnL: Number(p.cumulative_pnl),
    dailyPnL: Number(p.daily_pnl),
    drawdown: Number(p.drawdown),
    trades: p.trade_count,
  }));

  return (
    <div className="space-y-4">
      {/* Summary Cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Card>
          <p className="text-xs text-text-muted">Total PnL</p>
          <PnLText
            value={Number(analytics?.total_pnl ?? s?.total_realized ?? 0)}
            className="mt-1 text-xl font-bold"
          />
        </Card>
        <Card>
          <p className="text-xs text-text-muted">Total Trades</p>
          <p className="mt-1 font-mono text-xl font-bold tabular-nums">
            {analytics?.total_trades ?? s?.total_trades ?? 0}
          </p>
        </Card>
        <Card>
          <p className="text-xs text-text-muted">Win Rate</p>
          <p className="mt-1 font-mono text-xl font-bold tabular-nums">
            {s?.win_rate != null ? `${(s.win_rate * 100).toFixed(1)}%` : "--"}
          </p>
        </Card>
        <Card>
          <p className="text-xs text-text-muted">Max Drawdown</p>
          <PnLText
            value={-Math.abs(Number(analytics?.max_drawdown ?? s?.max_drawdown ?? 0))}
            className="mt-1 text-xl font-bold"
          />
        </Card>
      </div>

      {/* Period Selector */}
      <div className="flex gap-1">
        {[7, 14, 30, 60, 90].map((d) => (
          <button
            key={d}
            onClick={() => setDays(d)}
            className={`rounded px-3 py-1 text-xs font-medium transition-colors ${
              days === d
                ? "bg-accent text-white"
                : "text-text-muted hover:bg-bg-hover"
            }`}
          >
            {d}D
          </button>
        ))}
      </div>

      {/* Cumulative PnL Chart */}
      <Card title="Cumulative PnL">
        {curveData.length > 0 ? (
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={curveData}>
              <defs>
                <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#33415520" />
              <XAxis
                dataKey="date"
                tick={{ fill: "#94a3b8", fontSize: 11 }}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: "#94a3b8", fontSize: 11 }}
                tickLine={false}
                tickFormatter={(v: number) => `${(v / 1000).toFixed(0)}K`}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#1e293b",
                  border: "1px solid #334155",
                  borderRadius: 8,
                  fontSize: 12,
                }}
                labelStyle={{ color: "#94a3b8" }}
                formatter={(value: number | undefined) => [formatKRW(value ?? 0), "Cumulative PnL"]}
              />
              <Area
                type="monotone"
                dataKey="cumPnL"
                stroke="#3b82f6"
                fill="url(#pnlGrad)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <p className="py-12 text-center text-sm text-text-muted">
            No PnL data available
          </p>
        )}
      </Card>

      {/* Daily PnL Bars */}
      <Card title="Daily PnL">
        {curveData.length > 0 ? (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={curveData}>
              <CartesianGrid stroke="#33415520" />
              <XAxis
                dataKey="date"
                tick={{ fill: "#94a3b8", fontSize: 11 }}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: "#94a3b8", fontSize: 11 }}
                tickLine={false}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#1e293b",
                  border: "1px solid #334155",
                  borderRadius: 8,
                  fontSize: 12,
                }}
                formatter={(value: number | undefined) => [formatKRW(value ?? 0), "Daily PnL"]}
              />
              <Bar
                dataKey="dailyPnL"
                fill="#3b82f6"
                radius={[2, 2, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="py-8 text-center text-sm text-text-muted">
            No daily PnL data
          </p>
        )}
      </Card>

      {/* Order History */}
      <Card title="Recent Orders">
        {orders.length === 0 ? (
          <p className="py-8 text-center text-sm text-text-muted">
            No filled orders
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border text-xs text-text-muted">
                  <th className="py-2 pr-4">Time</th>
                  <th className="py-2 pr-4">Side</th>
                  <th className="py-2 pr-4">Price</th>
                  <th className="py-2 pr-4">Amount</th>
                  <th className="py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {orders.slice(0, 20).map((o) => (
                  <tr key={o.id} className="border-b border-border/50">
                    <td className="py-2 pr-4 tabular-nums text-text-muted">
                      {formatTime(o.created_at)}
                    </td>
                    <td
                      className={`py-2 pr-4 font-medium ${
                        o.side === "buy" ? "text-up" : "text-down"
                      }`}
                    >
                      {o.side.toUpperCase()}
                    </td>
                    <td className="py-2 pr-4 font-mono tabular-nums">
                      {formatKRW(Number(o.price))}
                    </td>
                    <td className="py-2 pr-4 font-mono tabular-nums">
                      {Number(o.amount).toFixed(8)}
                    </td>
                    <td className="py-2 text-text-muted">{o.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
