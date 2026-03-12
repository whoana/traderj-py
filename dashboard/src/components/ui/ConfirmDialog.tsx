"use client";

import { useCallback, useEffect, useState } from "react";
import { cn } from "@/lib/cn";

interface ConfirmDialogProps {
  open: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  countdownSeconds?: number;
  variant?: "default" | "danger";
}

export function ConfirmDialog({
  open,
  onConfirm,
  onCancel,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  countdownSeconds = 3,
  variant = "default",
}: ConfirmDialogProps) {
  const [countdown, setCountdown] = useState(countdownSeconds);

  useEffect(() => {
    if (!open) {
      setCountdown(countdownSeconds);
      return;
    }
    if (countdown <= 0) return;

    const timer = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(timer);
  }, [open, countdown, countdownSeconds]);

  const handleConfirm = useCallback(() => {
    if (countdown > 0) return;
    onConfirm();
  }, [countdown, onConfirm]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="fixed inset-0 bg-black/50" onClick={onCancel} />
      <div role="alertdialog" aria-labelledby="confirm-dialog-title" aria-describedby="confirm-dialog-desc" className="relative z-10 w-full max-w-md rounded-lg bg-bg-card p-6 shadow-xl">
        <h3 id="confirm-dialog-title" className="text-lg font-semibold text-text-primary">{title}</h3>
        <p id="confirm-dialog-desc" className="mt-2 text-sm text-text-secondary">{description}</p>
        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="rounded-lg border border-border-default px-4 py-2 text-sm text-text-secondary transition-colors hover:bg-bg-hover"
          >
            {cancelLabel}
          </button>
          <button
            onClick={handleConfirm}
            disabled={countdown > 0}
            className={cn(
              "rounded-lg px-4 py-2 text-sm font-medium text-white transition-colors disabled:opacity-50",
              variant === "danger"
                ? "bg-pnl-negative hover:bg-pnl-negative/90"
                : "bg-accent-blue hover:bg-accent-blue/90",
            )}
          >
            {countdown > 0
              ? `${confirmLabel} (${countdown}s)`
              : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
