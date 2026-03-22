import { cn } from "@/lib/cn";

interface CardProps {
  children: React.ReactNode;
  className?: string;
  title?: string;
}

export function Card({ children, className, title }: CardProps) {
  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-bg-card p-4",
        className,
      )}
    >
      {title && (
        <h3 className="mb-3 text-sm font-semibold text-text-secondary">
          {title}
        </h3>
      )}
      {children}
    </div>
  );
}
