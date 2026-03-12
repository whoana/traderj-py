import { z } from "zod";

export const strategyConfigSchema = z.object({
  scoring_mode: z.enum(["weighted", "majority", "unanimous"]),
  entry_mode: z.enum(["market", "limit", "scaled"]),
  timeframes: z
    .array(z.string().min(1, "Timeframe is required"))
    .min(1, "At least one timeframe is required"),
  buy_threshold: z
    .number()
    .min(0, "Must be >= 0")
    .max(100, "Must be <= 100"),
  sell_threshold: z
    .number()
    .min(-100, "Must be >= -100")
    .max(0, "Must be <= 0"),
  stop_loss_pct: z
    .number()
    .min(0.1, "Must be >= 0.1%")
    .max(50, "Must be <= 50%"),
  max_position_pct: z
    .number()
    .min(1, "Must be >= 1%")
    .max(100, "Must be <= 100%"),
  trend_filter: z.boolean(),
});

export type StrategyConfigFormValues = z.infer<typeof strategyConfigSchema>;
