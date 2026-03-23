"use client";

import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { Card } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { api } from "@/lib/api";

interface EngineStatus {
  status: string;
  trading_mode: string;
  uptime_seconds?: number;
  strategies?: {
    strategy_id: string;
    preset: string;
    state: string;
  }[];
}

const PRESETS = ["STR-001", "STR-002", "STR-003", "STR-004", "STR-005", "STR-006", "STR-007", "STR-008"];

export default function ControlPage() {
  const [engine, setEngine] = useState<EngineStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<{
    action: string;
    title: string;
    description: string;
    onConfirm: () => void;
  } | null>(null);

  // SL/TP form
  const [slPrice, setSlPrice] = useState("");
  const [tpPrice, setTpPrice] = useState("");

  const fetchStatus = useCallback(async () => {
    try {
      const status = await api.get<EngineStatus>("/engine/engine/status");
      setEngine(status);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 10_000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  const engineAction = async (
    action: string,
    path: string,
    body?: unknown,
  ) => {
    setActionLoading(action);
    try {
      await api.post(path, body);
      toast.success(`Engine ${action} successful`);
      await fetchStatus();
    } catch (e) {
      toast.error(
        `Failed: ${e instanceof Error ? e.message : "Unknown error"}`,
      );
    } finally {
      setActionLoading(null);
    }
  };

  const confirmAction = (
    action: string,
    title: string,
    description: string,
    path: string,
    body?: unknown,
  ) => {
    setConfirm({
      action,
      title,
      description,
      onConfirm: () => {
        setConfirm(null);
        engineAction(action, path, body);
      },
    });
  };

  return (
    <div className="space-y-4">
      {/* Engine Control */}
      <Card title="Engine Control">
        <div className="mb-4 flex items-center gap-3">
          <span className="text-sm text-text-secondary">Status:</span>
          {engine ? (
            <StatusBadge
              status={engine.status === "running" ? "running" : "stopped"}
              label={engine.status}
            />
          ) : (
            <span className="text-sm text-text-muted">
              {loading ? "Loading..." : "Unknown"}
            </span>
          )}
          {engine?.uptime_seconds != null && (
            <span className="text-xs text-text-muted">
              Uptime: {Math.floor(engine.uptime_seconds / 3600)}h{" "}
              {Math.floor((engine.uptime_seconds % 3600) / 60)}m
            </span>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            onClick={() =>
              confirmAction(
                "start",
                "Start Engine",
                "Start the trading engine?",
                "/engine/engine/start",
              )
            }
            disabled={actionLoading !== null}
            className="rounded-md bg-up px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-up/80 disabled:opacity-50"
          >
            {actionLoading === "start" ? "Starting..." : "Start"}
          </button>

          <button
            onClick={() =>
              confirmAction(
                "stop",
                "Stop Engine",
                "This will stop the trading engine. No new trades will be executed.",
                "/engine/engine/stop",
              )
            }
            disabled={actionLoading !== null}
            className="rounded-md bg-status-error px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-status-error/80 disabled:opacity-50"
          >
            {actionLoading === "stop" ? "Stopping..." : "Stop"}
          </button>

          <button
            onClick={() =>
              confirmAction(
                "restart",
                "Restart Engine",
                "Restart the trading engine? This will briefly interrupt operation.",
                "/engine/engine/restart",
              )
            }
            disabled={actionLoading !== null}
            className="rounded-md bg-status-warning px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-status-warning/80 disabled:opacity-50"
          >
            {actionLoading === "restart" ? "Restarting..." : "Restart"}
          </button>
        </div>
      </Card>

      {/* Strategy Switch */}
      <Card title="Strategy Switch">
        <p className="mb-3 text-sm text-text-muted">
          Current: <span className="font-mono font-medium text-text-primary">{engine?.strategies?.[0]?.preset ?? "--"}</span>
        </p>
        <div className="flex flex-wrap gap-2">
          {PRESETS.map((preset) => (
            <button
              key={preset}
              onClick={() =>
                confirmAction(
                  `switch-${preset}`,
                  "Switch Strategy",
                  `Switch to strategy preset ${preset}?`,
                  "/engine/strategy/switch",
                  { strategy_id: preset },
                )
              }
              disabled={actionLoading !== null || engine?.strategies?.[0]?.preset === preset}
              className={`rounded-md px-3 py-1.5 text-sm font-mono font-medium transition-colors ${
                engine?.strategies?.[0]?.preset === preset
                  ? "bg-accent text-white"
                  : "border border-border text-text-secondary hover:bg-bg-hover disabled:opacity-50"
              }`}
            >
              {preset}
            </button>
          ))}
        </div>
      </Card>

      {/* Position Management */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card title="Close Position">
          <p className="mb-3 text-sm text-text-muted">
            Close the current open position for STR-001.
          </p>
          <button
            onClick={() =>
              confirmAction(
                "close",
                "Close Position",
                "This will close the current position at market price. This action cannot be undone.",
                "/engine/position/close",
                { strategy_id: "STR-001" },
              )
            }
            disabled={actionLoading !== null}
            className="rounded-md bg-status-error px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-status-error/80 disabled:opacity-50"
          >
            Close Position
          </button>
        </Card>

        <Card title="Adjust SL / TP">
          <div className="space-y-3">
            <div>
              <label
                htmlFor="sl-price"
                className="mb-1 block text-xs text-text-muted"
              >
                Stop Loss (KRW)
              </label>
              <div className="flex gap-2">
                <input
                  id="sl-price"
                  type="number"
                  value={slPrice}
                  onChange={(e) => setSlPrice(e.target.value)}
                  placeholder="e.g. 100000000"
                  className="flex-1 rounded-md border border-border bg-bg-primary px-3 py-2 font-mono text-sm text-text-primary placeholder:text-text-muted"
                />
                <button
                  onClick={() => {
                    if (!slPrice) return;
                    confirmAction(
                      "sl",
                      "Update Stop Loss",
                      `Set SL to ${Number(slPrice).toLocaleString()} KRW?`,
                      "/engine/position/sl",
                      { strategy_id: "STR-001", stop_loss: Number(slPrice) },
                    );
                  }}
                  disabled={!slPrice || actionLoading !== null}
                  className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                >
                  Set SL
                </button>
              </div>
            </div>

            <div>
              <label
                htmlFor="tp-price"
                className="mb-1 block text-xs text-text-muted"
              >
                Take Profit (KRW)
              </label>
              <div className="flex gap-2">
                <input
                  id="tp-price"
                  type="number"
                  value={tpPrice}
                  onChange={(e) => setTpPrice(e.target.value)}
                  placeholder="e.g. 115000000"
                  className="flex-1 rounded-md border border-border bg-bg-primary px-3 py-2 font-mono text-sm text-text-primary placeholder:text-text-muted"
                />
                <button
                  onClick={() => {
                    if (!tpPrice) return;
                    confirmAction(
                      "tp",
                      "Update Take Profit",
                      `Set TP to ${Number(tpPrice).toLocaleString()} KRW?`,
                      "/engine/position/tp",
                      { strategy_id: "STR-001", take_profit: Number(tpPrice) },
                    );
                  }}
                  disabled={!tpPrice || actionLoading !== null}
                  className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                >
                  Set TP
                </button>
              </div>
            </div>
          </div>
        </Card>
      </div>

      <ConfirmDialog
        open={confirm !== null}
        title={confirm?.title ?? ""}
        description={confirm?.description ?? ""}
        confirmLabel={confirm?.action ?? "Confirm"}
        variant={
          ["stop", "close"].includes(confirm?.action ?? "") ? "danger" : "default"
        }
        onConfirm={() => confirm?.onConfirm()}
        onCancel={() => setConfirm(null)}
      />
    </div>
  );
}
