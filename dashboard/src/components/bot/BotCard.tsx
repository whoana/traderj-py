"use client";

import { memo } from "react";
import type { BotStatus } from "@/stores/useBotStore";
import { StatusDot } from "@/components/ui/StatusDot";
import { BOT_STATE_COLORS, BOT_STATE_LABELS } from "@/lib/constants";

interface BotCardProps {
  bot: BotStatus;
  onStart?: (strategyId: string) => void;
  onStop?: (strategyId: string) => void;
  onPause?: (strategyId: string) => void;
}

const BotCard = memo(function BotCard({ bot, onStart, onStop, onPause }: BotCardProps) {
  const stateColor = BOT_STATE_COLORS[bot.state] ?? "gray";
  const stateLabel = BOT_STATE_LABELS[bot.state] ?? bot.state;
  const isActive = ["scanning", "validating", "executing", "monitoring"].includes(bot.state);
  const isPaused = bot.state === "paused";
  const isIdle = bot.state === "idle";

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <StatusDot
            color={stateColor}
            pulse={isActive}
          />
          <div>
            <h4 className="text-sm font-semibold text-[var(--color-text-primary)]">
              {bot.strategy_id}
            </h4>
            <p className="text-xs text-[var(--color-text-secondary)]">
              {stateLabel}
            </p>
          </div>
        </div>

        <span className="rounded-full bg-[var(--color-bg-secondary)] px-2 py-0.5 text-xs text-[var(--color-text-secondary)]">
          {bot.trading_mode}
        </span>
      </div>

      {bot.started_at && (
        <p className="mt-2 text-xs text-[var(--color-text-tertiary)]">
          Started: {new Date(bot.started_at).toLocaleString()}
        </p>
      )}

      {/* Control buttons */}
      <div className="mt-3 flex gap-2">
        {isIdle && (
          <button
            onClick={() => onStart?.(bot.strategy_id)}
            className="rounded bg-[var(--color-status-success)] px-3 py-1 text-xs font-medium text-white hover:opacity-90"
          >
            Start
          </button>
        )}
        {isActive && (
          <>
            <button
              onClick={() => onPause?.(bot.strategy_id)}
              className="rounded bg-[var(--color-status-warning)] px-3 py-1 text-xs font-medium text-white hover:opacity-90"
            >
              Pause
            </button>
            <button
              onClick={() => onStop?.(bot.strategy_id)}
              className="rounded bg-[var(--color-status-error)] px-3 py-1 text-xs font-medium text-white hover:opacity-90"
            >
              Stop
            </button>
          </>
        )}
        {isPaused && (
          <>
            <button
              onClick={() => onStart?.(bot.strategy_id)}
              className="rounded bg-[var(--color-status-success)] px-3 py-1 text-xs font-medium text-white hover:opacity-90"
            >
              Resume
            </button>
            <button
              onClick={() => onStop?.(bot.strategy_id)}
              className="rounded bg-[var(--color-status-error)] px-3 py-1 text-xs font-medium text-white hover:opacity-90"
            >
              Stop
            </button>
          </>
        )}
      </div>
    </div>
  );
});

export default BotCard;
