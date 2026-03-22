import { NextRequest, NextResponse } from "next/server";
import { generateRegistrationOptions } from "@simplewebauthn/server";
import { getPasskeys } from "@/lib/passkey";
import type { AuthenticatorTransportFuture } from "@simplewebauthn/server";

export async function POST(req: NextRequest) {
  // Must be authenticated to register a passkey
  const session = req.cookies.get("traderj-session")?.value;
  const expected = process.env.SESSION_SECRET ?? "";
  if (!session || session !== expected) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const host = req.headers.get("host") ?? "localhost";
  const rpID = host.split(":")[0];

  let existingPasskeys: { credential_id: string; transports: string[] }[] = [];
  try {
    existingPasskeys = await getPasskeys();
  } catch {
    // No passkeys yet — fine
  }

  const options = await generateRegistrationOptions({
    rpName: "TraderJ Dashboard",
    rpID,
    userName: "traderj-owner",
    userDisplayName: "TraderJ Owner",
    attestationType: "none",
    excludeCredentials: existingPasskeys.map((p) => ({
      id: p.credential_id,
      transports: p.transports as AuthenticatorTransportFuture[],
    })),
    authenticatorSelection: {
      residentKey: "preferred",
      userVerification: "preferred",
    },
  });

  const response = NextResponse.json(options);
  response.cookies.set("webauthn-challenge", options.challenge, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    maxAge: 300,
    path: "/",
  });

  return response;
}
