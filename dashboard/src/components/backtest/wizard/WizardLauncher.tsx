"use client";

import { useWizard } from "@/contexts/WizardContext";

export function WizardLauncher() {
  const { dispatch } = useWizard();

  return (
    <button
      onClick={() => dispatch({ type: "OPEN" })}
      className="flex w-full items-center gap-2 rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-accent/90"
    >
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path
          d="M8 1v14M3 6l5-5 5 5M3 10l5 5 5-5"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      수익률 개선 위자드
    </button>
  );
}
