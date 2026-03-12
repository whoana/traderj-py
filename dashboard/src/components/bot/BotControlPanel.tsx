"use client";

import { toast } from "sonner";
import { useBotStore } from "@/stores/useBotStore";
import { startBot, stopBot, pauseBot, resumeBot } from "@/lib/api";
import BotCard from "./BotCard";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonCard } from "@/components/ui/SkeletonCard";
import { EmergencyStopButton } from "@/components/dashboard/EmergencyStopButton";
import { CloseAllButton } from "@/components/dashboard/CloseAllButton";

export default function BotControlPanel() {
  const { bots, loading, error, updateBot } = useBotStore();

  const handleStart = async (strategyId: string) => {
    try {
      await startBot(strategyId);
      updateBot(strategyId, { state: "scanning" });
      toast.success(`Bot ${strategyId} started`);
    } catch {
      toast.error(`Failed to start ${strategyId}`);
    }
  };

  const handleStop = async (strategyId: string) => {
    try {
      await stopBot(strategyId);
      updateBot(strategyId, { state: "idle" });
      toast.success(`Bot ${strategyId} stopped`);
    } catch {
      toast.error(`Failed to stop ${strategyId}`);
    }
  };

  const handlePause = async (strategyId: string) => {
    try {
      await pauseBot(strategyId);
      updateBot(strategyId, { state: "paused" });
      toast.success(`Bot ${strategyId} paused`);
    } catch {
      toast.error(`Failed to pause ${strategyId}`);
    }
  };

  const handleResume = async (strategyId: string) => {
    try {
      await resumeBot(strategyId);
      updateBot(strategyId, { state: "scanning" });
      toast.success(`Bot ${strategyId} resumed`);
    } catch {
      toast.error(`Failed to resume ${strategyId}`);
    }
  };

  if (loading) {
    return (
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Bot Management</h3>
        <SkeletonCard lines={3} />
        <SkeletonCard lines={3} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-[var(--color-status-error)] bg-[var(--color-bg-card)] p-4">
        <p className="text-sm text-[var(--color-status-error)]">{error}</p>
      </div>
    );
  }

  if (bots.length === 0) {
    return (
      <EmptyState
        message="No bots configured"
        description="Add a strategy to start trading"
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
          Bot Management ({bots.length})
        </h3>
        <div className="flex gap-2">
          <CloseAllButton />
          <EmergencyStopButton />
        </div>
      </div>
      {bots.map((bot) => (
        <BotCard
          key={bot.strategy_id}
          bot={bot}
          onStart={bot.state === "paused" ? handleResume : handleStart}
          onStop={handleStop}
          onPause={handlePause}
        />
      ))}
    </div>
  );
}
