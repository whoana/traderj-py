import { cn } from "@/lib/cn";

const variants: Record<string, string> = {
  running: "bg-status-running/20 text-status-running",
  stopped: "bg-neutral/20 text-neutral",
  error: "bg-status-error/20 text-status-error",
  warning: "bg-status-warning/20 text-status-warning",
  default: "bg-neutral/20 text-text-secondary",
};

interface StatusBadgeProps {
  status: string;
  label?: string;
  className?: string;
}

export function StatusBadge({ status, label, className }: StatusBadgeProps) {
  const variant = variants[status] ?? variants.default;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        variant,
        className,
      )}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {label ?? status}
    </span>
  );
}
