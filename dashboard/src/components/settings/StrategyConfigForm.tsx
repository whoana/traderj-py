"use client";

import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  strategyConfigSchema,
  type StrategyConfigFormValues,
} from "@/lib/schemas/strategy-config";

interface StrategyConfigFormProps {
  defaultValues: StrategyConfigFormValues;
  onSubmit: (values: StrategyConfigFormValues) => Promise<void>;
  saving: boolean;
}

const inputClass =
  "rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-3 py-1.5 text-sm";

export function StrategyConfigForm({
  defaultValues,
  onSubmit,
  saving,
}: StrategyConfigFormProps) {
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<StrategyConfigFormValues>({
    resolver: zodResolver(strategyConfigSchema),
    defaultValues,
  });

  const { fields, append, remove } = useFieldArray({
    control,
    name: "timeframes" as never,
  });

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className="space-y-6 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6"
    >
      <h2 className="text-lg font-semibold">Strategy Configuration</h2>

      {/* Mode Section */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="text-[var(--color-text-secondary)]">Scoring Mode</span>
          <select {...register("scoring_mode")} className={`mt-1 block w-full ${inputClass}`}>
            <option value="weighted">Weighted</option>
            <option value="majority">Majority</option>
            <option value="unanimous">Unanimous</option>
          </select>
          {errors.scoring_mode && (
            <p className="mt-1 text-xs text-[var(--color-pnl-negative)]">{errors.scoring_mode.message}</p>
          )}
        </label>

        <label className="block text-sm">
          <span className="text-[var(--color-text-secondary)]">Entry Mode</span>
          <select {...register("entry_mode")} className={`mt-1 block w-full ${inputClass}`}>
            <option value="market">Market</option>
            <option value="limit">Limit</option>
            <option value="scaled">Scaled</option>
          </select>
          {errors.entry_mode && (
            <p className="mt-1 text-xs text-[var(--color-pnl-negative)]">{errors.entry_mode.message}</p>
          )}
        </label>
      </div>

      {/* Timeframes Section */}
      <div>
        <span className="text-sm text-[var(--color-text-secondary)]">Timeframes</span>
        <div className="mt-1 space-y-2">
          {fields.map((field, index) => (
            <div key={field.id} className="flex items-center gap-2">
              <input
                {...register(`timeframes.${index}` as const)}
                className={`flex-1 ${inputClass}`}
                placeholder="e.g. 1m, 5m, 1h"
              />
              <button
                type="button"
                onClick={() => remove(index)}
                className="rounded px-2 py-1 text-xs text-[var(--color-pnl-negative)] hover:bg-[var(--color-bg-secondary)]"
              >
                Remove
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() => append("" as never)}
            className="rounded border border-dashed border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)]"
          >
            + Add Timeframe
          </button>
        </div>
        {errors.timeframes && (
          <p className="mt-1 text-xs text-[var(--color-pnl-negative)]">
            {errors.timeframes.message ?? errors.timeframes.root?.message}
          </p>
        )}
      </div>

      {/* Thresholds Section */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="text-[var(--color-text-secondary)]">Buy Threshold (0-100)</span>
          <input
            type="number"
            step="1"
            {...register("buy_threshold", { valueAsNumber: true })}
            className={`mt-1 block w-full ${inputClass}`}
          />
          {errors.buy_threshold && (
            <p className="mt-1 text-xs text-[var(--color-pnl-negative)]">{errors.buy_threshold.message}</p>
          )}
        </label>

        <label className="block text-sm">
          <span className="text-[var(--color-text-secondary)]">Sell Threshold (-100 to 0)</span>
          <input
            type="number"
            step="1"
            {...register("sell_threshold", { valueAsNumber: true })}
            className={`mt-1 block w-full ${inputClass}`}
          />
          {errors.sell_threshold && (
            <p className="mt-1 text-xs text-[var(--color-pnl-negative)]">{errors.sell_threshold.message}</p>
          )}
        </label>
      </div>

      {/* Risk Section */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="text-[var(--color-text-secondary)]">Stop Loss %</span>
          <input
            type="number"
            step="0.1"
            {...register("stop_loss_pct", { valueAsNumber: true })}
            className={`mt-1 block w-full ${inputClass}`}
          />
          {errors.stop_loss_pct && (
            <p className="mt-1 text-xs text-[var(--color-pnl-negative)]">{errors.stop_loss_pct.message}</p>
          )}
        </label>

        <label className="block text-sm">
          <span className="text-[var(--color-text-secondary)]">Max Position %</span>
          <input
            type="number"
            step="1"
            {...register("max_position_pct", { valueAsNumber: true })}
            className={`mt-1 block w-full ${inputClass}`}
          />
          {errors.max_position_pct && (
            <p className="mt-1 text-xs text-[var(--color-pnl-negative)]">{errors.max_position_pct.message}</p>
          )}
        </label>
      </div>

      {/* Filters Section */}
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          {...register("trend_filter")}
          className="rounded border-[var(--color-border)]"
        />
        <span className="text-[var(--color-text-secondary)]">Enable Trend Filter</span>
      </label>

      {/* Submit */}
      <button
        type="submit"
        disabled={saving}
        className="rounded-lg bg-[var(--color-accent-blue)] px-6 py-2 text-sm font-medium text-white transition-colors hover:bg-[var(--color-accent-blue)]/90 disabled:opacity-50"
      >
        {saving ? "Saving..." : "Save Configuration"}
      </button>
    </form>
  );
}
