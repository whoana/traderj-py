"use client";

import { useWizard } from "@/contexts/WizardContext";
import { cn } from "@/lib/cn";

interface WizardNavButtonsProps {
  onNext?: () => void | Promise<void>;
  nextLabel?: string;
  nextDisabled?: boolean;
  hideBack?: boolean;
  hideNext?: boolean;
}

export function WizardNavButtons({
  onNext,
  nextLabel,
  nextDisabled = false,
  hideBack = false,
  hideNext = false,
}: WizardNavButtonsProps) {
  const { state, dispatch } = useWizard();

  const isFirst = state.stepIndex === 0;

  return (
    <div className="flex items-center justify-between border-t border-border px-4 py-3 sm:px-6">
      <div className="flex gap-2">
        {!hideBack && !isFirst && (
          <button
            onClick={() => dispatch({ type: "PREV_STEP" })}
            disabled={state.loading}
            className="rounded-lg border border-border px-4 py-2 text-sm text-text-secondary transition-colors hover:bg-bg-secondary disabled:opacity-50"
          >
            이전
          </button>
        )}
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => dispatch({ type: "CLOSE" })}
          className="rounded-lg border border-border px-4 py-2 text-sm text-text-muted transition-colors hover:bg-bg-secondary"
        >
          취소
        </button>
        {!hideNext && (
          <button
            onClick={async () => {
              if (onNext) {
                await onNext();
              } else {
                dispatch({ type: "NEXT_STEP" });
              }
            }}
            disabled={nextDisabled || state.loading}
            className={cn(
              "rounded-lg px-4 py-2 text-sm font-medium transition-colors",
              "bg-accent text-white hover:bg-accent/90",
              "disabled:cursor-not-allowed disabled:opacity-50",
            )}
          >
            {state.loading ? (
              <span className="flex items-center gap-2">
                <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                처리 중...
              </span>
            ) : (
              nextLabel ?? "다음"
            )}
          </button>
        )}
      </div>
    </div>
  );
}
