"use client";

import { useEffect, useState } from "react";
import {
  browserSupportsWebAuthn,
  startRegistration,
} from "@simplewebauthn/browser";
import { Card } from "@/components/ui/Card";

interface PasskeyInfo {
  credential_id: string;
  created_at: string;
}

export default function PasskeyManager() {
  const [supported, setSupported] = useState(false);
  const [passkeys, setPasskeys] = useState<PasskeyInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [registering, setRegistering] = useState(false);
  const [message, setMessage] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);

  useEffect(() => {
    setSupported(browserSupportsWebAuthn());
    fetchPasskeys();
  }, []);

  const fetchPasskeys = async () => {
    try {
      const res = await fetch("/api/engine/passkeys");
      if (res.ok) {
        setPasskeys(await res.json());
      }
    } catch {
      // Engine might not have the endpoint yet
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async () => {
    setMessage(null);
    setRegistering(true);

    try {
      // 1. Get registration options
      const optionsRes = await fetch("/api/auth/passkey/register-options", {
        method: "POST",
      });

      if (!optionsRes.ok) {
        const data = await optionsRes.json();
        setMessage({ type: "error", text: data.error ?? "Failed to get options" });
        return;
      }

      const options = await optionsRes.json();

      // 2. Trigger biometric prompt
      const regResponse = await startRegistration({ optionsJSON: options });

      // 3. Verify with server
      const verifyRes = await fetch("/api/auth/passkey/register-verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(regResponse),
      });

      if (verifyRes.ok) {
        setMessage({ type: "success", text: "Passkey registered successfully!" });
        await fetchPasskeys();
      } else {
        const data = await verifyRes.json();
        setMessage({ type: "error", text: data.error ?? "Registration failed" });
      }
    } catch (err) {
      if (err instanceof Error && err.name === "NotAllowedError") {
        setMessage({ type: "error", text: "Registration cancelled" });
      } else {
        setMessage({ type: "error", text: "Registration failed" });
      }
    } finally {
      setRegistering(false);
    }
  };

  const handleDelete = async (credentialId: string) => {
    if (!confirm("Remove this passkey?")) return;

    try {
      const res = await fetch(
        `/api/engine/passkeys/${encodeURIComponent(credentialId)}`,
        { method: "DELETE" },
      );
      if (res.ok) {
        setMessage({ type: "success", text: "Passkey removed" });
        await fetchPasskeys();
      } else {
        setMessage({ type: "error", text: "Failed to remove passkey" });
      }
    } catch {
      setMessage({ type: "error", text: "Failed to remove passkey" });
    }
  };

  return (
    <Card title="Passkey Authentication">
      <div className="space-y-4">
        <p className="text-sm text-text-muted">
          Use Face ID, Touch ID, or device biometrics to log in without a password.
        </p>

        {!supported && (
          <p className="text-sm text-status-warning">
            Your browser does not support passkeys.
          </p>
        )}

        {/* Message */}
        {message && (
          <p
            className={`text-sm ${
              message.type === "success"
                ? "text-status-running"
                : "text-status-error"
            }`}
          >
            {message.text}
          </p>
        )}

        {/* Registered passkeys */}
        {!loading && passkeys.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-medium text-text-secondary">
              Registered Passkeys
            </p>
            {passkeys.map((pk) => (
              <div
                key={pk.credential_id}
                className="flex items-center justify-between rounded-md border border-border bg-bg-primary px-3 py-2"
              >
                <div className="flex items-center gap-2">
                  <svg
                    className="h-4 w-4 text-status-running"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={1.5}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z"
                    />
                  </svg>
                  <div>
                    <span className="font-mono text-xs text-text-primary">
                      {pk.credential_id.slice(0, 16)}...
                    </span>
                    <p className="text-xs text-text-muted">
                      Registered{" "}
                      {new Date(pk.created_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => handleDelete(pk.credential_id)}
                  className="rounded px-2 py-1 text-xs text-status-error transition-colors hover:bg-bg-hover"
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Register button */}
        {supported && (
          <button
            onClick={handleRegister}
            disabled={registering}
            className="flex items-center gap-2 rounded-md border border-accent bg-accent/10 px-4 py-2 text-sm font-medium text-accent transition-colors hover:bg-accent/20 disabled:opacity-50"
          >
            <svg
              className="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={1.5}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 4.5v15m7.5-7.5h-15"
              />
            </svg>
            {registering ? "Registering..." : "Register New Passkey"}
          </button>
        )}
      </div>
    </Card>
  );
}
