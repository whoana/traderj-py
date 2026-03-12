"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { cn } from "@/lib/cn";
import { ConnectionStatus } from "./ConnectionStatus";

const navLinks = [
  { href: "/", label: "Dashboard" },
  { href: "/analytics", label: "Analytics" },
  { href: "/backtest", label: "Backtest" },
  { href: "/settings", label: "Settings" },
] as const;

export function TopNav() {
  const pathname = usePathname();
  const { theme, setTheme } = useTheme();

  return (
    <header className="sticky top-0 z-40 flex h-[var(--topnav-height)] items-center border-b border-border-default bg-bg-primary/80 px-4 backdrop-blur-sm">
      <Link
        href="/"
        className="mr-8 text-lg font-bold text-text-primary"
      >
        traderj
      </Link>

      <nav className="flex items-center gap-1">
        {navLinks.map(({ href, label }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
              pathname === href
                ? "bg-bg-tertiary text-text-primary"
                : "text-text-secondary hover:bg-bg-hover hover:text-text-primary",
            )}
          >
            {label}
          </Link>
        ))}
      </nav>

      <div className="ml-auto flex items-center gap-3">
        <ConnectionStatus />
        <button
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          className="rounded-md p-2 text-text-secondary transition-colors hover:bg-bg-hover hover:text-text-primary"
          aria-label="Toggle theme"
        >
          {theme === "dark" ? "Light" : "Dark"}
        </button>
      </div>
    </header>
  );
}
