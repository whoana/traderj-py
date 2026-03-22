import { NextResponse } from "next/server";

const ENGINE_URL =
  process.env.ENGINE_URL ?? "https://traderj-engine.fly.dev";

export async function GET() {
  try {
    const res = await fetch(`${ENGINE_URL}/health`, { cache: "no-store" });
    const data = await res.json();
    return NextResponse.json({ dashboard: "ok", engine: data });
  } catch {
    return NextResponse.json(
      { dashboard: "ok", engine: "unreachable" },
      { status: 200 },
    );
  }
}
