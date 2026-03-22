import { NextRequest, NextResponse } from "next/server";
import { verifyAuthenticationResponse } from "@simplewebauthn/server";
import type { AuthenticationResponseJSON } from "@simplewebauthn/server";
import { getPasskeys, updatePasskeyCounter } from "@/lib/passkey";

export async function POST(req: NextRequest) {
  const challenge = req.cookies.get("webauthn-challenge")?.value;
  if (!challenge) {
    return NextResponse.json(
      { error: "No challenge found. Start authentication again." },
      { status: 400 },
    );
  }

  const body = (await req.json()) as AuthenticationResponseJSON;

  const host = req.headers.get("host") ?? "localhost";
  const rpID = host.split(":")[0];
  const origin = req.headers.get("origin") ?? `http://${host}`;

  // Find matching credential
  let passkeys;
  try {
    passkeys = await getPasskeys();
  } catch {
    return NextResponse.json(
      { error: "Could not retrieve passkeys" },
      { status: 500 },
    );
  }

  const matchedCredential = passkeys.find(
    (p) => p.credential_id === body.id,
  );
  if (!matchedCredential) {
    return NextResponse.json(
      { error: "Credential not recognized" },
      { status: 400 },
    );
  }

  try {
    const verification = await verifyAuthenticationResponse({
      response: body,
      expectedChallenge: challenge,
      expectedOrigin: origin,
      expectedRPID: rpID,
      credential: {
        id: matchedCredential.credential_id,
        publicKey: new Uint8Array(
          Buffer.from(matchedCredential.public_key, "base64url"),
        ),
        counter: matchedCredential.counter,
      },
    });

    if (!verification.verified) {
      return NextResponse.json(
        { error: "Authentication failed" },
        { status: 401 },
      );
    }

    // Update counter
    await updatePasskeyCounter(
      matchedCredential.credential_id,
      verification.authenticationInfo.newCounter,
    ).catch(() => {
      /* non-critical */
    });

    // Set session cookie (same as password login)
    const sessionSecret = process.env.SESSION_SECRET ?? "fallback";
    const isProduction = process.env.NODE_ENV === "production";
    const maxAge = 60 * 60 * 24 * 7;

    const cookieValue = [
      `traderj-session=${sessionSecret}`,
      `Path=/`,
      `Max-Age=${maxAge}`,
      `HttpOnly`,
      `SameSite=Lax`,
      isProduction ? "Secure" : "",
    ]
      .filter(Boolean)
      .join("; ");

    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: {
        "Content-Type": "application/json",
        "Set-Cookie": cookieValue,
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Verification error";
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
