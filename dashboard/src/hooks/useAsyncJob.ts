"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface JobStatus {
  job_id: string;
  status: string;
  progress?: string;
  elapsed_sec?: number;
  result?: Record<string, unknown>;
  error?: string;
}

interface UseAsyncJobOptions {
  pollInterval?: number;
  onComplete?: (result: Record<string, unknown>) => void;
  onError?: (error: string) => void;
}

export function useAsyncJob(options: UseAsyncJobOptions = {}) {
  const { pollInterval = 2000, onComplete, onError } = options;
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("idle");
  const [progress, setProgress] = useState<string>("");
  const [elapsed, setElapsed] = useState(0);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const onCompleteRef = useRef(onComplete);
  const onErrorRef = useRef(onError);

  onCompleteRef.current = onComplete;
  onErrorRef.current = onError;

  const stopPolling = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const poll = useCallback(
    async (id: string) => {
      try {
        const res = await fetch(`/api/engine/backtest/jobs/${id}`);
        if (!res.ok) return;
        const data: JobStatus = await res.json();
        setStatus(data.status);
        setProgress(data.progress ?? "");
        setElapsed(data.elapsed_sec ?? 0);

        if (data.status === "done" && data.result) {
          setResult(data.result);
          stopPolling();
          onCompleteRef.current?.(data.result);
        } else if (data.status === "failed") {
          const errMsg = data.error ?? "Job failed";
          setError(errMsg);
          stopPolling();
          onErrorRef.current?.(errMsg);
        } else if (data.status === "cancelled") {
          setError("Job cancelled");
          stopPolling();
        }
      } catch {
        // Silently retry on network errors
      }
    },
    [stopPolling],
  );

  const startPolling = useCallback(
    (id: string) => {
      stopPolling();
      setJobId(id);
      setStatus("pending");
      setProgress("");
      setElapsed(0);
      setResult(null);
      setError(null);
      poll(id);
      timerRef.current = setInterval(() => poll(id), pollInterval);
    },
    [poll, pollInterval, stopPolling],
  );

  const reset = useCallback(() => {
    stopPolling();
    setJobId(null);
    setStatus("idle");
    setProgress("");
    setElapsed(0);
    setResult(null);
    setError(null);
  }, [stopPolling]);

  useEffect(() => stopPolling, [stopPolling]);

  const isRunning = ["pending", "fetching", "running"].includes(status);

  return {
    jobId,
    status,
    progress,
    elapsed,
    result,
    error,
    isRunning,
    startPolling,
    stopPolling,
    reset,
  };
}
