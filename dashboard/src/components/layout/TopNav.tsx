"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/cn";

const navLinks = [
  { href: "/", label: "Dashboard", icon: "M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" },
  { href: "/analytics", label: "Analytics", icon: "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" },
  { href: "/control", label: "Control", icon: "M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z" },
  { href: "/settings", label: "Settings", icon: "M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" },
] as const;

function NavIcon({ d }: { d: string }) {
  return (
    <svg className="h-4 w-4 sm:h-5 sm:w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d={d} />
    </svg>
  );
}

export function TopNav() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-40 flex h-11 sm:h-14 items-center border-b border-border bg-bg-primary/80 px-2 sm:px-4 backdrop-blur-sm">
      <Link href="/" className="mr-3 sm:mr-8 font-mono text-sm sm:text-lg font-bold text-accent">
        TraderJ
      </Link>

      <nav className="flex items-center gap-0.5 sm:gap-1">
        {navLinks.map(({ href, label, icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-2 py-1 sm:px-3 sm:py-1.5 text-xs sm:text-sm font-medium transition-colors",
                active
                  ? "bg-accent-dim text-accent"
                  : "text-text-secondary hover:bg-bg-hover hover:text-text-primary",
              )}
            >
              <NavIcon d={icon} />
              <span className="hidden sm:inline">{label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="ml-auto flex items-center gap-2 sm:gap-3">
        <EngineStatusDot />
        <LogoutButton />
      </div>
    </header>
  );
}

function EngineStatusDot() {
  return (
    <div className="flex items-center gap-1.5 text-[10px] sm:text-xs text-text-muted" title="Engine connection">
      <span className="relative flex h-2 w-2">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-status-running opacity-75" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-status-running" />
      </span>
      <span className="hidden sm:inline">Engine</span>
    </div>
  );
}

function LogoutButton() {
  const handleLogout = async () => {
    await fetch("/api/auth", { method: "DELETE" });
    window.location.href = "/login";
  };

  return (
    <button
      onClick={handleLogout}
      className="rounded-md px-1.5 py-0.5 sm:px-2 sm:py-1 text-[10px] sm:text-xs text-text-muted transition-colors hover:bg-bg-hover hover:text-text-primary"
      title="Logout"
    >
      Logout
    </button>
  );
}
