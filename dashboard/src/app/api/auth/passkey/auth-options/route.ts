import { NextRequest, NextResponse } from "next/server";
import { generateAuthenticationOptions } from "@simplewebauthn/server";
import type { AuthenticatorTransportFuture } from "@simplewebauthn/server";
import { getPasskeys } from "@/lib/passkey";

export async function POST(req: NextRequest) {
  const host = req.headers.get("host") ?? "localhost";
  const rpID = host.split(":")[0];

  let passkeys: { credential_id: string; transports: string[] }[] = [];
  try {
    passkeys = await getPasskeys();
  } catch {
    return NextResponse.json(
      { error: "Could not retrieve passkeys" },
      { status: 500 },
    );
  }

  if (passkeys.length === 0) {
    return NextResponse.json(
      { error: "No passkeys registered" },
      { status: 404 },
    );
  }

  const options = await generateAuthenticationOptions({
    rpID,
    allowCredentials: passkeys.map((p) => ({
      id: p.credential_id,
      transports: p.transports as AuthenticatorTransportFuture[],
    })),
    userVerification: "preferred",
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
