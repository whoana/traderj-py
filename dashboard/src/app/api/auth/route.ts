import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  try {
    const body = (await req.json()) as { password?: string };
    const expected = process.env.DASHBOARD_PASSWORD;

    if (!expected) {
      return NextResponse.json(
        { error: "DASHBOARD_PASSWORD not configured" },
        { status: 500 },
      );
    }

    if (body.password !== expected) {
      return NextResponse.json({ error: "Invalid password" }, { status: 401 });
    }

    const sessionSecret = process.env.SESSION_SECRET ?? "fallback";
    const maxAge = 60 * 60 * 24 * 7; // 7 days

    const res = NextResponse.json({ ok: true });
    res.cookies.set("traderj-session", sessionSecret, {
      path: "/",
      maxAge,
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
    });
    return res;
  } catch (e) {
    return NextResponse.json(
      { error: "Internal error", detail: String(e) },
      { status: 500 },
    );
  }
}

export async function DELETE() {
  const cookieValue =
    "traderj-session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax";

  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      "Set-Cookie": cookieValue,
    },
  });
}
