"use client";

import { useEffect, useState } from "react";
import { StatusDot } from "@/components/ui/StatusDot";
import { wsClient, type WsStatus } from "@/lib/ws-client";

const statusConfig: Record<WsStatus, { color: string; label: string; pulse: boolean }> = {
  connected: {
    color: "var(--color-status-monitoring)",
    label: "Connected",
    pulse: false,
  },
  connecting: {
    color: "var(--color-status-executing)",
    label: "Connecting",
    pulse: true,
  },
  reconnecting: {
    color: "var(--color-status-executing)",
    label: "Reconnecting",
    pulse: true,
  },
  disconnected: {
    color: "var(--color-status-error)",
    label: "Disconnected",
    pulse: false,
  },
};

export function ConnectionStatus() {
  const [status, setStatus] = useState<WsStatus>("disconnected");

  useEffect(() => {
    const unsub = wsClient.onStatusChange(setStatus);
    setStatus(wsClient.status);
    return unsub;
  }, []);

  const config = statusConfig[status];

  return (
    <StatusDot
      color={config.color}
      pulse={config.pulse}
      size="sm"
      label={config.label}
    />
  );
}
