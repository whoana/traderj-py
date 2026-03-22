/**
 * Server-side passkey credential storage via Engine API.
 */

import { engineFetch, engineGet } from "./engine";

export interface StoredPasskey {
  credential_id: string;
  public_key: string;
  counter: number;
  transports: string[];
  created_at: string;
}

export async function getPasskeys(): Promise<StoredPasskey[]> {
  return engineGet<StoredPasskey[]>("/api/v1/passkeys");
}

export async function createPasskey(data: {
  credential_id: string;
  public_key: string;
  counter: number;
  transports: string[];
}): Promise<StoredPasskey> {
  const res = await engineFetch("/api/v1/passkeys", {
    method: "POST",
    body: JSON.stringify(data),
  });
  return res.json();
}

export async function updatePasskeyCounter(
  credentialId: string,
  counter: number,
): Promise<void> {
  await engineFetch(
    `/api/v1/passkeys/${encodeURIComponent(credentialId)}/counter`,
    {
      method: "PUT",
      body: JSON.stringify({ counter }),
    },
  );
}

export async function deletePasskeyOnEngine(
  credentialId: string,
): Promise<void> {
  await engineFetch(
    `/api/v1/passkeys/${encodeURIComponent(credentialId)}`,
    {
      method: "DELETE",
    },
  );
}
