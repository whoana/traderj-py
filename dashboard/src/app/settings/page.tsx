"use client";

import { useEffect, useState, useCallback } from "react";
import dynamic from "next/dynamic";
import { Card } from "@/components/ui/Card";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";

const PasskeyManager = dynamic(
  () => import("@/components/settings/PasskeyManager"),
  { ssr: false, loading: () => <SkeletonCard /> },
);

interface ConfigData {
  [key: string]: unknown;
}

interface EngineStatusData {
  status: string;
  trading_mode: string;
  uptime_seconds?: number;
  strategies?: {
    strategy_id: string;
    preset: string;
    state: string;
  }[];
  regime?: {
    current: string;
    mapped_preset: string;
    confidence: number;
    last_switch_at: string;
    switch_count: number;
    locked: boolean;
  };
}

interface RiskData {
  strategy_id: string;
  consecutive_losses: number;
  daily_pnl: string;
  cooldown_until: string | null;
  [key: string]: unknown;
}

interface MacroData {
  timestamp?: string;
  fear_greed?: number;
  funding_rate?: number;
  btc_dominance?: number;
  kimchi_premium?: number;
  market_score?: number;
  [key: string]: unknown;
}

interface VersionData {
  version: string;
  [key: string]: unknown;
}

function InfoRow({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div className="flex items-baseline justify-between border-b border-border/50 py-2 last:border-0">
      <span className="text-xs text-text-muted">{label}</span>
      <span className="font-mono text-sm tabular-nums text-text-primary">
        {value ?? "--"}
      </span>
    </div>
  );
}

export default function SettingsPage() {
  const [config, setConfig] = useState<ConfigData | null>(null);
  const [engineStatus, setEngineStatus] = useState<EngineStatusData | null>(null);
  const [risk, setRisk] = useState<RiskData | null>(null);
  const [macro, setMacro] = useState<MacroData | null>(null);
  const [version, setVersion] = useState<VersionData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchAll = useCallback(async () => {
    try {
      const [cfg, eng, rsk, mac, ver] = await Promise.allSettled([
        api.get<ConfigData>("/engine/config"),
        api.get<EngineStatusData>("/engine/engine/status"),
        api.get<RiskData>("/engine/risk/STR-001"),
        api.get<MacroData>("/engine/macro/latest"),
        api.get<VersionData>("/engine/version"),
      ]);

      if (cfg.status === "fulfilled") setConfig(cfg.value);
      if (eng.status === "fulfilled") setEngineStatus(eng.value);
      if (rsk.status === "fulfilled") setRisk(rsk.value);
      if (mac.status === "fulfilled") setMacro(mac.value);
      if (ver.status === "fulfilled") setVersion(ver.value);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      {/* Passkey Management — full width */}
      <div className="lg:col-span-2">
        <PasskeyManager />
      </div>

      {/* Regime */}
      <Card title="Regime Status">
        <InfoRow label="Current Regime" value={engineStatus?.regime?.current} />
        <InfoRow label="Mapped Preset" value={engineStatus?.regime?.mapped_preset} />
        <InfoRow label="Confidence" value={engineStatus?.regime?.confidence?.toFixed(4)} />
        <InfoRow label="Switch Count" value={engineStatus?.regime?.switch_count} />
        <InfoRow label="Locked" value={engineStatus?.regime?.locked ? "Yes" : "No"} />
      </Card>

      {/* Risk */}
      <Card title="Risk State">
        <InfoRow label="Strategy" value={risk?.strategy_id} />
        <InfoRow label="Consecutive Losses" value={risk?.consecutive_losses} />
        <InfoRow label="Daily PnL" value={risk?.daily_pnl} />
        <InfoRow
          label="Cooldown Until"
          value={risk?.cooldown_until ?? "None"}
        />
      </Card>

      {/* Macro */}
      <Card title="Macro Indicators">
        <InfoRow label="Fear & Greed" value={macro?.fear_greed} />
        <InfoRow label="Funding Rate" value={macro?.funding_rate} />
        <InfoRow label="BTC Dominance" value={macro?.btc_dominance} />
        <InfoRow label="Kimchi Premium" value={macro?.kimchi_premium} />
        <InfoRow label="Market Score" value={macro?.market_score} />
      </Card>

      {/* Config (read-only) */}
      <Card title="Strategy Config">
        {config ? (
          <pre className="overflow-x-auto rounded-md bg-bg-primary p-3 font-mono text-xs text-text-secondary">
            {JSON.stringify(config, null, 2)}
          </pre>
        ) : (
          <p className="text-sm text-text-muted">No config available</p>
        )}
      </Card>

      {/* Version */}
      <Card title="System Info">
        <InfoRow label="Version" value={version?.version} />
        <InfoRow label="Dashboard" value="0.1.0" />
      </Card>
    </div>
  );
}
