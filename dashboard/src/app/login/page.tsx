"use client";

import { useState, useEffect } from "react";

export default function LoginPage() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [passkeyAvailable, setPasskeyAvailable] = useState(false);
  const [passkeyLoading, setPasskeyLoading] = useState(false);

  useEffect(() => {
    import("@simplewebauthn/browser").then((mod) => {
      setPasskeyAvailable(mod.browserSupportsWebAuthn());
    });
  }, []);

  const handlePasswordLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await fetch("/api/auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });

      if (res.ok) {
        window.location.href = "/";
        return;
      } else {
        const data = await res.json();
        setError(data.error ?? "Authentication failed");
      }
    } catch {
      setError("Network error");
    } finally {
      setLoading(false);
    }
  };

  const handlePasskeyLogin = async () => {
    setError("");
    setPasskeyLoading(true);

    try {
      // 1. Get authentication options
      const optionsRes = await fetch("/api/auth/passkey/auth-options", {
        method: "POST",
      });

      if (!optionsRes.ok) {
        const data = await optionsRes.json();
        if (optionsRes.status === 404) {
          setError("No passkeys registered. Login with password first, then register in Settings.");
          return;
        }
        setError(data.error ?? "Failed to get options");
        return;
      }

      const options = await optionsRes.json();

      // 2. Trigger biometric (Face ID / Touch ID / etc.)
      const { startAuthentication } = await import("@simplewebauthn/browser");
      const authResponse = await startAuthentication({ optionsJSON: options });

      // 3. Verify with server
      const verifyRes = await fetch("/api/auth/passkey/auth-verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(authResponse),
      });

      if (verifyRes.ok) {
        window.location.href = "/";
        return;
      } else {
        const data = await verifyRes.json();
        setError(data.error ?? "Passkey authentication failed");
      }
    } catch (err) {
      if (err instanceof Error && err.name === "NotAllowedError") {
        setError("Authentication cancelled");
      } else {
        setError("Passkey authentication failed");
      }
    } finally {
      setPasskeyLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg-primary">
      <div className="w-full max-w-sm rounded-lg border border-border bg-bg-card p-8">
        <h1 className="mb-1 font-mono text-2xl font-bold text-accent">
          TraderJ
        </h1>
        <p className="mb-6 text-sm text-text-muted">
          Dashboard authentication required
        </p>

        {/* Passkey login */}
        {passkeyAvailable && (
          <>
            <button
              type="button"
              onClick={handlePasskeyLogin}
              disabled={passkeyLoading}
              className="mb-4 flex w-full items-center justify-center gap-2 rounded-md border border-border bg-bg-primary px-4 py-2.5 text-sm font-medium text-text-primary transition-colors hover:bg-bg-hover disabled:opacity-50"
            >
              <svg
                className="h-5 w-5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={1.5}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M7.864 4.243A7.5 7.5 0 0119.5 10.5c0 2.92-.556 5.709-1.568 8.268M5.742 6.364A7.465 7.465 0 004.5 10.5a7.464 7.464 0 01-1.15 3.993m1.989 3.559A11.209 11.209 0 008.25 10.5a3.75 3.75 0 117.5 0c0 .527-.021 1.049-.064 1.565M12 10.5a14.94 14.94 0 01-3.6 9.75m6.633-4.596a18.666 18.666 0 01-2.485 5.33"
                />
              </svg>
              {passkeyLoading ? "Authenticating..." : "Login with Passkey"}
            </button>

            <div className="relative mb-4">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-border" />
              </div>
              <div className="relative flex justify-center text-xs">
                <span className="bg-bg-card px-2 text-text-muted">or</span>
              </div>
            </div>
          </>
        )}

        {/* Password login */}
        <form onSubmit={handlePasswordLogin}>
          <label
            htmlFor="password"
            className="mb-1 block text-xs text-text-muted"
          >
            Password
          </label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoFocus={!passkeyAvailable}
            required
            className="mb-4 w-full rounded-md border border-border bg-bg-primary px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none"
            placeholder="Enter dashboard password"
          />

          {error && (
            <p className="mb-4 text-sm text-status-error">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading || !password}
            className="w-full rounded-md bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent/80 disabled:opacity-50"
          >
            {loading ? "Authenticating..." : "Login with Password"}
          </button>
        </form>
      </div>
    </div>
  );
}
