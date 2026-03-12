"use client";

import { cn } from "@/lib/cn";

interface SkeletonCardProps {
  lines?: number;
  className?: string;
}

export function SkeletonCard({ lines = 3, className }: SkeletonCardProps) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-lg border border-border-default bg-bg-card p-4",
        className,
      )}
    >
      <div className="mb-3 h-4 w-1/3 rounded bg-bg-tertiary" />
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="mb-2 h-3 rounded bg-bg-tertiary"
          style={{ width: `${80 - i * 15}%` }}
        />
      ))}
    </div>
  );
}
