"use client";

import { TopNav } from "./TopNav";

interface PageShellProps {
  children: React.ReactNode;
  className?: string;
}

export function PageShell({ children, className }: PageShellProps) {
  return (
    <div className="min-h-screen">
      <TopNav />
      <main className={className ?? "mx-auto max-w-7xl p-4"}>
        {children}
      </main>
    </div>
  );
}
