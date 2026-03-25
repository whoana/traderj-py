"use client";

import { useWizard } from "@/contexts/WizardContext";
import { useCallback, useEffect, useRef } from "react";
import { WizardStepper } from "./WizardStepper";
import { StepAnalyze } from "./steps/StepAnalyze";
import { StepApply } from "./steps/StepApply";
import { StepBacktest } from "./steps/StepBacktest";
import { StepComplete } from "./steps/StepComplete";
import { StepOptimize } from "./steps/StepOptimize";
import { StepValidate } from "./steps/StepValidate";

const STEP_COMPONENTS = {
  backtest: StepBacktest,
  analyze: StepAnalyze,
  optimize: StepOptimize,
  apply: StepApply,
  validate: StepValidate,
  complete: StepComplete,
} as const;

export function WizardOverlay() {
  const { state, dispatch, stepLabels } = useWizard();
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (state.open && !dialog.open) {
      dialog.showModal();
    } else if (!state.open && dialog.open) {
      dialog.close();
    }
  }, [state.open]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        dispatch({ type: "CLOSE" });
      }
    },
    [dispatch],
  );

  if (!state.open) return null;

  const StepComponent = STEP_COMPONENTS[state.step];

  return (
    <dialog
      ref={dialogRef}
      onKeyDown={handleKeyDown}
      className="m-0 h-full w-full max-h-dvh max-w-full border-none bg-transparent p-0 backdrop:bg-black/60"
    >
      <div className="flex h-full w-full flex-col bg-bg-primary text-text-primary">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-4 py-3 sm:px-6">
          <div>
            <h2 className="text-base font-semibold sm:text-lg">
              수익률 개선 위자드
            </h2>
            <p className="text-xs text-text-muted">
              {stepLabels[state.step]}
            </p>
          </div>
          <button
            onClick={() => dispatch({ type: "CLOSE" })}
            className="rounded-lg p-2 text-text-muted transition-colors hover:bg-bg-secondary hover:text-text-primary"
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path d="M5 5l10 10M15 5L5 15" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        {/* Stepper */}
        <WizardStepper />

        {/* Error banner */}
        {state.error && (
          <div className="mx-4 rounded-lg border border-status-error/30 bg-status-error/10 px-4 py-2 text-sm text-status-error sm:mx-6">
            {state.error}
          </div>
        )}

        {/* Step content */}
        <div className="flex-1 overflow-y-auto px-4 py-4 sm:px-6">
          <StepComponent />
        </div>
      </div>
    </dialog>
  );
}
