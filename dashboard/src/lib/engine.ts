/**
 * Server-side engine API client.
 * Used only in API Route handlers — API key never reaches the browser.
 */

const ENGINE_URL =
  process.env.ENGINE_URL ?? "https://traderj-engine.fly.dev";
const API_KEY = process.env.ENGINE_API_KEY ?? "";

export class EngineError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
    this.name = "EngineError";
  }
}

export async function engineFetch(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  const url = `${ENGINE_URL}${path}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": API_KEY,
      ...(options.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new EngineError(res.status, body || res.statusText);
  }
  return res;
}

export async function engineGet<T>(path: string): Promise<T> {
  const res = await engineFetch(path);
  return res.json() as Promise<T>;
}

export async function enginePost<T>(
  path: string,
  body?: unknown,
): Promise<T> {
  const res = await engineFetch(path, {
    method: "POST",
    body: body ? JSON.stringify(body) : undefined,
  });
  return res.json() as Promise<T>;
}
