"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4">
      <h2 className="text-xl font-semibold text-text-primary">
        Something went wrong
      </h2>
      <p className="text-text-secondary">{error.message}</p>
      <button
        onClick={reset}
        className="rounded-lg bg-accent-blue px-4 py-2 text-white transition-colors hover:bg-accent-blue/90"
      >
        Try again
      </button>
    </div>
  );
}
