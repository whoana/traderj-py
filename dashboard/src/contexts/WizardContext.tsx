"use client";

import { createContext, useContext, useReducer, type ReactNode } from "react";

// ── Types ──────────────────────────────────────────────────

export type WizardStep =
  | "backtest"
  | "analyze"
  | "optimize"
  | "apply"
  | "validate"
  | "complete";

const STEPS: WizardStep[] = [
  "backtest",
  "analyze",
  "optimize",
  "apply",
  "validate",
  "complete",
];

const STEP_LABELS: Record<WizardStep, string> = {
  backtest: "백테스트 선택",
  analyze: "분석",
  optimize: "최적화",
  apply: "적용 리뷰",
  validate: "검증",
  complete: "완료",
};

export interface WizardState {
  open: boolean;
  step: WizardStep;
  stepIndex: number;

  // Step 1: Selected backtest
  selectedJobId: string | null;
  selectedStrategy: string | null;
  backtestResult: Record<string, unknown> | null;

  // Step 2: Analysis
  analysis: Record<string, unknown> | null;

  // Step 3: Optimization
  optimizeJobId: string | null;
  candidates: Record<string, unknown>[];
  selectedCandidate: Record<string, unknown> | null;
  baselineMetrics: Record<string, unknown> | null;

  // Step 4: Apply preview
  applyPreview: Record<string, unknown> | null;
  appliedChanges: string[];

  // Step 5: Validation
  validateJobId: string | null;
  validationResult: Record<string, unknown> | null;

  // Step 6: Complete
  tuningId: string | null;

  // Global
  loading: boolean;
  error: string | null;
}

type WizardAction =
  | { type: "OPEN" }
  | { type: "CLOSE" }
  | { type: "GO_TO_STEP"; step: WizardStep }
  | { type: "NEXT_STEP" }
  | { type: "PREV_STEP" }
  | { type: "SET_BACKTEST"; jobId: string; strategy: string; result: Record<string, unknown> }
  | { type: "SET_ANALYSIS"; analysis: Record<string, unknown> }
  | { type: "SET_OPTIMIZE_JOB"; jobId: string }
  | { type: "SET_CANDIDATES"; candidates: Record<string, unknown>[]; baseline: Record<string, unknown> }
  | { type: "SELECT_CANDIDATE"; candidate: Record<string, unknown> }
  | { type: "SET_APPLY_PREVIEW"; preview: Record<string, unknown> }
  | { type: "SET_APPLIED"; changes: string[]; tuningId: string }
  | { type: "SET_VALIDATE_JOB"; jobId: string }
  | { type: "SET_VALIDATION"; result: Record<string, unknown> }
  | { type: "SET_LOADING"; loading: boolean }
  | { type: "SET_ERROR"; error: string | null }
  | { type: "RESET" };

// ── Initial state ──────────────────────────────────────────

const initialState: WizardState = {
  open: false,
  step: "backtest",
  stepIndex: 0,
  selectedJobId: null,
  selectedStrategy: null,
  backtestResult: null,
  analysis: null,
  optimizeJobId: null,
  candidates: [],
  selectedCandidate: null,
  baselineMetrics: null,
  applyPreview: null,
  appliedChanges: [],
  validateJobId: null,
  validationResult: null,
  tuningId: null,
  loading: false,
  error: null,
};

// ── Reducer ────────────────────────────────────────────────

function wizardReducer(state: WizardState, action: WizardAction): WizardState {
  switch (action.type) {
    case "OPEN":
      return { ...initialState, open: true };
    case "CLOSE":
      return { ...initialState };
    case "GO_TO_STEP": {
      const idx = STEPS.indexOf(action.step);
      return { ...state, step: action.step, stepIndex: idx, error: null };
    }
    case "NEXT_STEP": {
      const next = Math.min(state.stepIndex + 1, STEPS.length - 1);
      return { ...state, step: STEPS[next], stepIndex: next, error: null };
    }
    case "PREV_STEP": {
      const prev = Math.max(state.stepIndex - 1, 0);
      return { ...state, step: STEPS[prev], stepIndex: prev, error: null };
    }
    case "SET_BACKTEST":
      return {
        ...state,
        selectedJobId: action.jobId,
        selectedStrategy: action.strategy,
        backtestResult: action.result,
      };
    case "SET_ANALYSIS":
      return { ...state, analysis: action.analysis };
    case "SET_OPTIMIZE_JOB":
      return { ...state, optimizeJobId: action.jobId };
    case "SET_CANDIDATES":
      return {
        ...state,
        candidates: action.candidates,
        baselineMetrics: action.baseline,
        selectedCandidate: action.candidates[0] ?? null,
      };
    case "SELECT_CANDIDATE":
      return { ...state, selectedCandidate: action.candidate };
    case "SET_APPLY_PREVIEW":
      return { ...state, applyPreview: action.preview };
    case "SET_APPLIED":
      return {
        ...state,
        appliedChanges: action.changes,
        tuningId: action.tuningId,
      };
    case "SET_VALIDATE_JOB":
      return { ...state, validateJobId: action.jobId };
    case "SET_VALIDATION":
      return { ...state, validationResult: action.result };
    case "SET_LOADING":
      return { ...state, loading: action.loading };
    case "SET_ERROR":
      return { ...state, error: action.error, loading: false };
    case "RESET":
      return { ...initialState };
    default:
      return state;
  }
}

// ── Context ────────────────────────────────────────────────

interface WizardContextValue {
  state: WizardState;
  dispatch: React.Dispatch<WizardAction>;
  steps: typeof STEPS;
  stepLabels: typeof STEP_LABELS;
}

const WizardContext = createContext<WizardContextValue | null>(null);

export function WizardProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(wizardReducer, initialState);
  return (
    <WizardContext.Provider value={{ state, dispatch, steps: STEPS, stepLabels: STEP_LABELS }}>
      {children}
    </WizardContext.Provider>
  );
}

export function useWizard() {
  const ctx = useContext(WizardContext);
  if (!ctx) throw new Error("useWizard must be used within WizardProvider");
  return ctx;
}
