import { NextRequest, NextResponse } from "next/server";
import { engineFetch, EngineError } from "@/lib/engine";

/**
 * Catch-all proxy: /api/engine/* → ENGINE_URL/api/v1/*
 * Keeps API key server-side only.
 */

function handleEngineError(e: unknown) {
  if (e instanceof EngineError) {
    return NextResponse.json({ error: e.detail }, { status: e.status });
  }
  return NextResponse.json({ error: "Engine unreachable" }, { status: 502 });
}

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  const enginePath = `/api/v1/${path.join("/")}`;
  const qs = _req.nextUrl.searchParams.toString();
  const fullPath = qs ? `${enginePath}?${qs}` : enginePath;

  try {
    const res = await engineFetch(fullPath);
    const data = await res.json();
    return NextResponse.json(data);
  } catch (e) {
    return handleEngineError(e);
  }
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  const enginePath = `/api/v1/${path.join("/")}`;
  const text = await req.text();

  try {
    const res = await engineFetch(enginePath, {
      method: "POST",
      body: text || undefined,
    });
    const data = await res.json();
    return NextResponse.json(data);
  } catch (e) {
    return handleEngineError(e);
  }
}

export async function PUT(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  const enginePath = `/api/v1/${path.join("/")}`;
  const text = await req.text();

  try {
    const res = await engineFetch(enginePath, {
      method: "PUT",
      body: text || undefined,
    });
    const data = await res.json();
    return NextResponse.json(data);
  } catch (e) {
    return handleEngineError(e);
  }
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  const enginePath = `/api/v1/${path.join("/")}`;

  try {
    const res = await engineFetch(enginePath, { method: "DELETE" });
    const data = await res.json();
    return NextResponse.json(data);
  } catch (e) {
    return handleEngineError(e);
  }
}
