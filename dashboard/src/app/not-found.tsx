import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4">
      <h1 className="text-6xl font-bold text-[var(--color-text-primary)]">404</h1>
      <p className="text-lg text-[var(--color-text-secondary)]">Page not found</p>
      <Link
        href="/"
        className="mt-4 rounded-lg bg-[var(--color-accent-blue)] px-6 py-2 text-sm font-medium text-white transition-colors hover:bg-[var(--color-accent-blue)]/90"
      >
        Back to Dashboard
      </Link>
    </div>
  );
}
