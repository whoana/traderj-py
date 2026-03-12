"use client";

import { cn } from "@/lib/cn";

interface StatusDotProps {
  color: string;
  pulse?: boolean;
  size?: "sm" | "md" | "lg";
  label?: string;
  className?: string;
}

const sizeClasses = {
  sm: "h-2 w-2",
  md: "h-3 w-3",
  lg: "h-4 w-4",
} as const;

export function StatusDot({
  color,
  pulse = false,
  size = "md",
  label,
  className,
}: StatusDotProps) {
  return (
    <span className={cn("inline-flex items-center gap-1.5", className)}>
      <span className="relative inline-flex">
        <span
          className={cn("rounded-full", sizeClasses[size])}
          style={{ backgroundColor: color }}
        />
        {pulse && (
          <span
            className={cn(
              "absolute inset-0 animate-ping rounded-full opacity-75",
              sizeClasses[size],
            )}
            style={{ backgroundColor: color }}
          />
        )}
      </span>
      {label && <span className="text-sm text-text-secondary">{label}</span>}
    </span>
  );
}
