"use client";

import { useWizard } from "@/contexts/WizardContext";
import { cn } from "@/lib/cn";

export function WizardStepper() {
  const { state, steps, stepLabels } = useWizard();

  return (
    <div className="flex items-center gap-1 overflow-x-auto px-4 py-3 sm:gap-2 sm:px-6">
      {steps.map((step, i) => {
        const isCurrent = i === state.stepIndex;
        const isDone = i < state.stepIndex;
        const label = stepLabels[step];

        return (
          <div key={step} className="flex items-center gap-1 sm:gap-2">
            {i > 0 && (
              <div
                className={cn(
                  "h-px w-3 sm:w-6",
                  isDone ? "bg-accent" : "bg-border",
                )}
              />
            )}
            <div className="flex items-center gap-1.5">
              <div
                className={cn(
                  "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-medium",
                  isCurrent && "bg-accent text-white",
                  isDone && "bg-accent/20 text-accent",
                  !isCurrent && !isDone && "bg-bg-secondary text-text-muted",
                )}
              >
                {isDone ? "✓" : i + 1}
              </div>
              <span
                className={cn(
                  "hidden text-xs sm:inline",
                  isCurrent ? "font-medium text-text-primary" : "text-text-muted",
                )}
              >
                {label}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
