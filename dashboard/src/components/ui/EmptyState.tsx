"use client";

import { cn } from "@/lib/cn";

interface EmptyStateProps {
  message: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

export function EmptyState({
  message,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center py-12 text-center",
        className,
      )}
    >
      <div className="mb-4 text-4xl text-text-muted">---</div>
      <p className="text-lg font-medium text-text-primary">{message}</p>
      {description && (
        <p className="mt-1 text-sm text-text-secondary">{description}</p>
      )}
      {action && (
        <button
          onClick={action.onClick}
          className="mt-4 rounded-lg bg-accent-blue px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-blue/90"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
