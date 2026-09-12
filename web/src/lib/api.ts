/**
 * The only place this tier talks to the domain tier.
 *
 * Every call here runs on the SERVER. The browser never reaches the API
 * directly, which is the whole point of the arrangement: no CORS, no session
 * token in a browser-reachable surface, and the authenticated API is not
 * addressable from the internet at all.
 *
 * There is no database client in this tier and there never will be. If a page
 * needs data it asks the API, in one place, through the functions below.
 */

// 8010, not the usual 8000: another project on this machine already holds
// 8000, and a port clash presents as a baffling 404 from the wrong server.
const API_BASE = process.env.KAFRIADA_API_URL ?? "http://127.0.0.1:8010";

/** Every request gets a deadline. A hung upstream must not hold a render open. */
const TIMEOUT_MS = 10_000;

export type Lga = {
  id: string;
  name: string;
  is_open: boolean;
};

export type PublicProfile = {
  kuid: string;
  full_name: string;
  sport: string;
  playing_position: string | null;
  lga_name: string;
  state_name: string;
  registered_year: number;
  age: number;
  is_verified: boolean;
  photo_url: string | null;
  /** The link carried a signature we issued: this QR came from KAFRIADA. */
  issued_by_kafriada: boolean;
};

export type RegistrationResult = {
  kuid: string;
  full_name: string;
  lga_name: string;
  profile_url: string;
  qr_url: string;
  /** Masked. The ID exists already; only the confirmation is outstanding. */
  phone: string;
  phone_verified: boolean;
  code_resend_seconds: number;
};

export type CodeSent = { resend_in: number; daily_limit_reached: boolean };

export type PhoneConfirmed = {
  kuid: string | null;
  token: string;
  idle_expires_at: string;
  absolute_expires_at: string;
  is_staff: boolean;
};

export type IssuedSession = {
  /** Shown once. Goes into an httpOnly cookie and nowhere else. */
  token: string;
  idle_expires_at: string;
  absolute_expires_at: string;
  is_staff: boolean;
  phone_verified: boolean;
};

export type RoleGrant = {
  grant_id: string;
  role: string;
  scope_kind: string;
  scope_id: string | null;
  scope_name: string | null;
};

export type Me = {
  full_name: string;
  /** Masked by the API. The full number never comes back out. */
  phone: string;
  kuid: string | null;
  lga_name: string | null;
  is_staff: boolean;
  phone_verified: boolean;
  roles: RoleGrant[];
  idle_expires_at: string;
  absolute_expires_at: string;
};

/** Where the person is, forwarded so the audit log records them, not us. */
export type ClientMeta = { ip?: string; userAgent?: string };

/** A rejection the person can act on: which field, and what to do about it. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly field?: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function call<T>(
  path: string,
  init?: RequestInit & { token?: string; meta?: ClientMeta },
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  const { token, meta, ...rest } = init ?? {};
  const extra: Record<string, string> = {};
  // The session travels server to server as a bearer token. The browser holds
  // it only in an httpOnly cookie that no script can read.
  if (token) extra.authorization = `Bearer ${token}`;
  if (meta?.ip) extra["x-real-ip"] = meta.ip;
  if (meta?.userAgent) extra["user-agent"] = meta.userAgent;

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...rest,
      signal: controller.signal,
      headers: { "content-type": "application/json", ...extra, ...rest.headers },
      // Nothing is cached. These are personal records and a registration is a
      // write; a stale profile would be worse than a slow one.
      cache: "no-store",
    });
  } catch {
    // Unreachable or too slow. Say so plainly — never show a stack trace or a
    // hostname to someone standing at a registration desk.
    throw new ApiError(
      "We could not reach KAFRIADA just now. Please try again in a moment.",
    );
  } finally {
    clearTimeout(timer);
  }

  if (response.status === 204) return undefined as T;
  if (response.ok) return (await response.json()) as T;

  // The API returns { error: { message, reference } }, where message may itself
  // be { message, field } for a rejection the form should point at.
  let message = "Something went wrong. Please try again.";
  let field: string | undefined;
  try {
    const body = await response.json();
    const inner = body?.error?.message;
    if (typeof inner === "string") message = inner;
    else if (inner && typeof inner === "object") {
      message = inner.message ?? message;
      field = inner.field ?? undefined;
    }
  } catch {
    /* a non-JSON error body is still an error; the default message stands */
  }
  throw new ApiError(message, field, response.status);
}

export function listLgas(): Promise<Lga[]> {
  return call<Lga[]>("/v1/public/lgas");
}

export function getProfile(kuid: string, signature?: string): Promise<PublicProfile> {
  const query = signature ? `?s=${encodeURIComponent(signature)}` : "";
  return call<PublicProfile>(`/v1/public/athletes/${encodeURIComponent(kuid)}${query}`);
}

export function register(input: {
  full_name: string;
  phone: string;
  password: string;
  date_of_birth: string;
  lga_id: string;
  sport: string;
  playing_position: string | null;
  accept_privacy_notice: boolean;
}): Promise<RegistrationResult> {
  return call<RegistrationResult>("/v1/register", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function signIn(
  input: { phone: string; password: string },
  meta: ClientMeta,
): Promise<IssuedSession> {
  return call<IssuedSession>("/v1/sessions", {
    method: "POST",
    body: JSON.stringify(input),
    meta,
  });
}

export function signOut(token: string, meta: ClientMeta): Promise<void> {
  return call<void>("/v1/sessions/current", { method: "DELETE", token, meta });
}

export function sendPhoneCode(phone: string, meta: ClientMeta): Promise<CodeSent> {
  return call<CodeSent>("/v1/phone/code", {
    method: "POST",
    body: JSON.stringify({ phone }),
    meta,
  });
}

export function confirmPhone(
  input: { phone: string; code: string },
  meta: ClientMeta,
): Promise<PhoneConfirmed> {
  return call<PhoneConfirmed>("/v1/phone/confirm", {
    method: "POST",
    body: JSON.stringify(input),
    meta,
  });
}

export function sendResetCode(phone: string, meta: ClientMeta): Promise<CodeSent> {
  return call<CodeSent>("/v1/password-reset/code", {
    method: "POST",
    body: JSON.stringify({ phone }),
    meta,
  });
}

export function resetPassword(
  input: { phone: string; code: string; new_password: string },
  meta: ClientMeta,
): Promise<void> {
  return call<void>("/v1/password-reset/confirm", {
    method: "POST",
    body: JSON.stringify(input),
    meta,
  });
}

export function getMe(token: string): Promise<Me> {
  return call<Me>("/v1/me", { token });
}

/** Raw SVG for an athlete's QR code, fetched server-side and inlined. */
export async function getQrSvg(kuid: string): Promise<string | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(
      `${API_BASE}/v1/public/athletes/${encodeURIComponent(kuid)}/qr.svg`,
      { signal: controller.signal, cache: "no-store" },
    );
    return response.ok ? await response.text() : null;
  } catch {
    // A missing QR must not take the card page down with it — the KUID itself
    // is the thing that matters, and it is printed beside the code.
    return null;
  } finally {
    clearTimeout(timer);
  }
}

export { API_BASE };
