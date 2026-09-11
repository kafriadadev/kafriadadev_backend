import { cookies, headers } from "next/headers";

import type { ClientMeta } from "./api";

/**
 * The session cookie. Server-side only.
 *
 * It holds an opaque token the API issued and nothing else — no name, no role,
 * nothing a script could read or a person could edit into something useful.
 * httpOnly, so no JavaScript on the page can reach it; SameSite=Lax, so another
 * site cannot post a form with it attached. Whether it is still good is decided
 * by the API on every request, which is what makes signing out instant.
 */
export const SESSION_COOKIE = "kaf_session";

export async function sessionToken(): Promise<string | undefined> {
  return (await cookies()).get(SESSION_COOKIE)?.value;
}

/**
 * Store a freshly issued token.
 *
 * Staff get a cookie that dies with the browser: coordinators share phones,
 * and closing the browser should be enough to hand one over. Athletes keep
 * theirs until the session's absolute expiry. Either way the API's own idle
 * clock is the real limit.
 */
export async function startSession(
  token: string,
  { isStaff, absoluteExpiresAt }: { isStaff: boolean; absoluteExpiresAt: string },
): Promise<void> {
  (await cookies()).set(SESSION_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    ...(isStaff ? {} : { expires: new Date(absoluteExpiresAt) }),
  });
}

export async function endSession(): Promise<void> {
  (await cookies()).delete(SESSION_COOKIE);
}

/** The visitor's address and browser, for the audit trail. */
export async function clientMeta(): Promise<ClientMeta> {
  const h = await headers();
  // Only the edge's own header. x-forwarded-for is whatever the client typed.
  return {
    ip: h.get("cf-connecting-ip") ?? undefined,
    userAgent: h.get("user-agent") ?? undefined,
  };
}
