import { NextRequest, NextResponse } from "next/server";
import { verifyRegistrationResponse } from "@simplewebauthn/server";
import type { RegistrationResponseJSON } from "@simplewebauthn/server";
import { createPasskey } from "@/lib/passkey";

export async function POST(req: NextRequest) {
  // Must be authenticated to register a passkey
  const session = req.cookies.get("traderj-session")?.value;
  const expected = process.env.SESSION_SECRET ?? "";
  if (!session || session !== expected) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const challenge = req.cookies.get("webauthn-challenge")?.value;
  if (!challenge) {
    return NextResponse.json(
      { error: "No challenge found. Start registration again." },
      { status: 400 },
    );
  }

  const body = (await req.json()) as RegistrationResponseJSON;

  const host = req.headers.get("host") ?? "localhost";
  const rpID = host.split(":")[0];
  const origin = req.headers.get("origin") ?? `http://${host}`;

  try {
    const verification = await verifyRegistrationResponse({
      response: body,
      expectedChallenge: challenge,
      expectedOrigin: origin,
      expectedRPID: rpID,
    });

    if (!verification.verified || !verification.registrationInfo) {
      return NextResponse.json(
        { error: "Verification failed" },
        { status: 400 },
      );
    }

    const { credential } = verification.registrationInfo;

    // Store credential via engine API
    await createPasskey({
      credential_id: credential.id,
      public_key: Buffer.from(credential.publicKey).toString("base64url"),
      counter: credential.counter,
      transports: (body.response.transports ?? []) as string[],
    });

    const response = NextResponse.json({ verified: true });
    response.cookies.delete("webauthn-challenge");
    return response;
  } catch (err) {
    const message = err instanceof Error ? err.message : "Verification error";
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
