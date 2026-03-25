"use client";

import { useWizard } from "@/contexts/WizardContext";
import { WizardNavButtons } from "../WizardNavButtons";

export function StepComplete() {
  const { state, dispatch } = useWizard();

  const validation = state.validationResult as Record<string, unknown> | null;
  const verdict = validation?.verdict as string | undefined;
  const candidate = state.selectedCandidate as Record<string, unknown> | null;

  return (
    <div className="flex flex-col gap-4">
      <div className="text-center">
        <div className="text-4xl">
          {verdict === "pass" ? "🎉" : verdict === "warn" ? "⚠️" : "📋"}
        </div>
        <h3 className="mt-2 text-lg font-semibold text-text-primary">
          수익률 개선 프로세스 완료
        </h3>
        <p className="mt-1 text-sm text-text-muted">
          {verdict === "pass"
            ? "검증을 통과했습니다. 변경사항이 엔진에 적용되었습니다."
            : verdict === "warn"
              ? "일부 기준이 미달이지만 변경사항이 적용되었습니다."
              : "검증 실패로 주의가 필요합니다. 변경사항은 적용되었습니다."}
        </p>
      </div>

      {/* Summary card */}
      <div className="rounded-lg border border-border bg-bg-card p-4">
        <h4 className="text-xs font-medium text-text-muted">적용 요약</h4>

        <div className="mt-3 space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-text-secondary">전략</span>
            <span className="font-medium text-accent">{state.selectedStrategy}</span>
          </div>

          {state.tuningId && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-text-secondary">Tuning ID</span>
              <span className="font-mono text-xs text-text-muted">{state.tuningId}</span>
            </div>
          )}

          {state.appliedChanges.length > 0 && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-text-secondary">적용 항목</span>
              <span className="text-text-primary">
                {state.appliedChanges.join(", ")}
              </span>
            </div>
          )}

          {candidate && (
            <div className="mt-2 border-t border-border pt-2">
              <div className="text-xs text-text-muted">최적화 파라미터 성능</div>
              <div className="mt-1 flex gap-4 text-xs">
                <span>
                  수익률:{" "}
                  <span className="font-medium text-status-running">
                    {Number(candidate.return_pct ?? 0).toFixed(1)}%
                  </span>
                </span>
                <span>
                  Sharpe: <span className="font-medium">{Number(candidate.sharpe_ratio ?? 0).toFixed(2)}</span>
                </span>
                <span>
                  Score: <span className="font-medium text-accent">{Number(candidate.score ?? 0).toFixed(2)}</span>
                </span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Next steps */}
      <div className="rounded-lg border border-border bg-bg-card p-4">
        <h4 className="text-xs font-medium text-text-muted">다음 단계</h4>
        <ul className="mt-2 space-y-1.5 text-sm text-text-secondary">
          <li className="flex items-start gap-2">
            <span className="mt-0.5 text-accent">1.</span>
            <span>Gate 2: 48시간 라이브 모니터링이 자동 시작됩니다</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-0.5 text-accent">2.</span>
            <span>MDD가 검증 시 MDD의 2배를 초과하면 자동 롤백됩니다</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-0.5 text-accent">3.</span>
            <span>Gate 3: 7일 후 적용 전후 비교가 자동 실행됩니다</span>
          </li>
        </ul>
      </div>

      <WizardNavButtons
        hideBack
        hideNext
      />

      {/* Action buttons */}
      <div className="flex gap-2">
        <button
          onClick={() => {
            dispatch({ type: "RESET" });
            dispatch({ type: "OPEN" });
          }}
          className="flex-1 rounded-lg border border-border px-4 py-3 text-sm font-medium text-text-secondary transition-colors hover:bg-bg-secondary"
        >
          새 백테스트 시작
        </button>
        <button
          onClick={() => dispatch({ type: "CLOSE" })}
          className="flex-1 rounded-lg bg-accent px-4 py-3 text-sm font-medium text-white transition-colors hover:bg-accent/90"
        >
          위자드 닫기
        </button>
      </div>
    </div>
  );
}
