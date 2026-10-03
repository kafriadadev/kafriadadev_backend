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

import type { ClubProfile } from "@/lib/clubProfile";

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
  /** An approved badge that was later taken back. */
  verification_withdrawn: boolean;
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
  email_verified: boolean;
  roles: RoleGrant[];
  idle_expires_at: string;
  absolute_expires_at: string;
};

export type PaymentQuote = {
  kuid: string;
  purpose: string;
  /** Whole kobo. Formatted for people in one place: lib/money.ts. */
  amount_kobo: number;
  already_paid: boolean;
};

export type StartedPayment = {
  reference: string;
  /** Where Paystack takes the card details. We never see them. */
  authorization_url: string;
  amount_kobo: number;
};

/**
 * What the person is told, decided by the API from its own record — never by
 * anything the browser reports. `review` is a payment our team is checking.
 */
export type PaymentState = "checking" | "confirmed" | "failed" | "review";

export type Payment = {
  reference: string;
  purpose: string;
  state: PaymentState;
  amount_kobo: number;
  created_at: string;
};

/** Where an athlete's verification stands, as the API recorded it. */
export type VerificationState =
  | "none"
  | "draft"
  | "under_review"
  | "approved"
  | "rejected"
  | "escalated"
  | "revoked";

/** A file's own progress: `ready` means the safe copy exists. */
export type FileStatus = "pending" | "uploaded" | "ready" | "unreadable" | "deleted" | null;

export type Verification = {
  state: VerificationState;
  attempt: number;
  attempts_left: number;
  photo: FileStatus;
  document: FileStatus;
  /** The reviewer's own words, exactly as written. */
  reason: string | null;
  submitted_at: string | null;
  paid_amount_kobo: number | null;
  paid_at: string | null;
  can_replace: boolean;
  ready_to_pay: boolean;
  price_kobo: number;
};

export type QueueItem = {
  request_id: string;
  kuid: string;
  full_name: string;
  submitted_at: string;
  attempt: number;
};

export type ReviewCase = {
  request_id: string;
  kuid: string;
  full_name: string;
  date_of_birth: string;
  age: number;
  attempt: number;
  submitted_at: string | null;
  paid_kobo: number | null;
  paid_at: string | null;
  waiting: number;
};

/** Where the person is, forwarded so the audit log records them, not us. */
export type ClientMeta = { ip?: string; userAgent?: string };

/** A rejection the person can act on: which field, and what to do about it. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly field?: string,
    readonly status?: number,
    /** Why, when the API names it: "email_unconfirmed", "email_missing". */
    readonly reason?: string,
    readonly detail?: Record<string, unknown>,
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
  let reason: string | undefined;
  let detail: Record<string, unknown> | undefined;
  try {
    const body = await response.json();
    const inner = body?.error?.message;
    if (typeof inner === "string") message = inner;
    else if (inner && typeof inner === "object") {
      message = inner.message ?? message;
      field = inner.field ?? undefined;
      reason = inner.reason ?? undefined;
      detail = inner;
    }
  } catch {
    /* a non-JSON error body is still an error; the default message stands */
  }
  throw new ApiError(message, field, response.status, reason, detail);
}

export function listLgas(): Promise<Lga[]> {
  return call<Lga[]>("/v1/public/lgas");
}

export function getProfile(kuid: string, signature?: string): Promise<PublicProfile> {
  const query = signature ? `?s=${encodeURIComponent(signature)}` : "";
  return call<PublicProfile>(`/v1/public/athletes/${encodeURIComponent(kuid)}${query}`);
}

export type RegistrationInput = {
  first_name: string;
  middle_name: string | null;
  surname: string;
  email: string;
  phone: string;
  password: string;
  date_of_birth: string;
  gender: string;
  nationality: string;
  state_of_origin: string;
  address_line: string;
  town: string;
  lga_id: string;
  sport: string;
  playing_position: string;
  secondary_position: string | null;
  dominant_side: string;
  height_cm: number;
  weight_kg: number;
  years_experience: number;
  level_played: string;
  emergency_name: string;
  emergency_relationship: string;
  emergency_phone: string;
  accept_privacy_notice: boolean;
};

export function register(input: RegistrationInput): Promise<RegistrationResult> {
  return call<RegistrationResult>("/v1/register", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function signIn(
  input: { phone: string; password: string; email?: string },
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

export function sendEmailCode(phone: string, meta: ClientMeta): Promise<CodeSent> {
  return call<CodeSent>("/v1/email/code", {
    method: "POST",
    body: JSON.stringify({ phone }),
    meta,
  });
}

export function confirmEmail(
  input: { phone: string; code: string },
  meta: ClientMeta,
): Promise<PhoneConfirmed> {
  return call<PhoneConfirmed>("/v1/email/confirm", {
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

export function getPaymentQuote(token: string): Promise<PaymentQuote> {
  return call<PaymentQuote>("/v1/payments/quote", { token });
}

export function startPayment(token: string, meta: ClientMeta): Promise<StartedPayment> {
  return call<StartedPayment>("/v1/payments", {
    method: "POST",
    body: JSON.stringify({ purpose: "stage2_athlete" }),
    token,
    meta,
  });
}

/** CRD-04: a coordinator starts a checkout for an athlete in their own LGA. */
export function startPaymentOnBehalf(
  token: string,
  lga: string,
  kuid: string,
  meta: ClientMeta,
): Promise<StartedPayment> {
  return call<StartedPayment>(
    `/v1/lgas/${encodeURIComponent(lga)}/athletes/${encodeURIComponent(kuid)}/payments`,
    {
      method: "POST",
      body: JSON.stringify({ purpose: "stage2_athlete" }),
      token,
      meta,
    },
  );
}

export type ClubRosterRow = {
  roster_id: string;
  full_name: string;
  kuid: string;
  position: string | null;
  state: "verified" | "unverified" | "invited";
};

export type ClubDashboard = {
  club_id: string;
  name: string;
  sport: string;
  type: string;
  year_founded: number | null;
  lga_name: string;
  contact_phone: string;
  status: "unconfirmed" | "pending_review" | "approved" | "suspended";
  verified: boolean;
  players: number;
  verified_players: number;
  invites_out: number;
  roster: ClubRosterRow[];
  created_at: string;
  /** The full record; fields are null for a club registered before they were asked. */
  profile: (Partial<Record<keyof ClubProfile | "rep_role", unknown>>) | null;
};

export type ClubInput = ClubProfile & {
  name: string;
  sport: string;
  lga_id: string;
  contact_phone: string;
  confirm_duplicate: boolean;
};

/** CLB-01: register a club. The caller becomes its administrator. */
/**
 * Staff register a club: an administrator anywhere, a coordinator only in their own
 * LGA (pass `inLga`). Clubs themselves use signUpClub.
 */
export function registerClub(
  token: string,
  input: ClubInput,
  meta: ClientMeta,
  inLga?: string,
): Promise<{ club_id: string; name: string }> {
  const path = inLga ? `/v1/lgas/${encodeURIComponent(inLga)}/clubs` : "/v1/clubs";
  return call<{ club_id: string; name: string }>(path, {
    method: "POST",
    body: JSON.stringify(input),
    token,
    meta,
  });
}

export type ClubSignUp = ClubInput & {
  rep_first_name: string;
  rep_surname: string;
  rep_role: string;
  rep_phone: string;
  rep_email: string;
  password: string;
  accept_privacy_notice: boolean;
};

/** A club signs itself up: its representative's account and the club, together. */
export function signUpClub(
  input: ClubSignUp,
  meta: ClientMeta,
): Promise<{ club_id: string; name: string; email: string }> {
  return call<{ club_id: string; name: string; email: string }>("/v1/clubs/register", {
    method: "POST",
    body: JSON.stringify(input),
    meta,
  });
}

/** Edit the club's record. Sport and area are not editable. */
export function updateClub(
  token: string,
  clubId: string,
  details: ClubProfile & { name: string; contact_phone: string },
  meta: ClientMeta,
): Promise<void> {
  return call<void>(`/v1/clubs/${encodeURIComponent(clubId)}`, {
    method: "PUT",
    body: JSON.stringify(details),
    token,
    meta,
  });
}

/** CLB-02: one club's dashboard. The API refuses any club the caller does not administer. */
export function getClub(token: string, clubId: string): Promise<ClubDashboard> {
  return call<ClubDashboard>(`/v1/clubs/${encodeURIComponent(clubId)}`, { token });
}

export type PlayerMatch = {
  full_name: string;
  kuid: string;
  position: string | null;
  lga_name: string;
  verified: boolean;
  current_club: string | null;
  state: "found" | "on_roster" | "invited";
};

/** CLB-03: an exact match on a KAFRIADA ID or phone number, or a 404. */
export function findPlayer(token: string, clubId: string, q: string): Promise<PlayerMatch> {
  return call<PlayerMatch>(
    `/v1/clubs/${encodeURIComponent(clubId)}/players/find?${new URLSearchParams({ q })}`,
    { token },
  );
}

export function invitePlayer(
  token: string,
  clubId: string,
  kuid: string,
  meta: ClientMeta,
): Promise<void> {
  return call<void>(`/v1/clubs/${encodeURIComponent(clubId)}/invitations`, {
    method: "POST",
    body: JSON.stringify({ kuid }),
    token,
    meta,
  });
}

export function removePlayer(
  token: string,
  clubId: string,
  rosterId: string,
  meta: ClientMeta,
): Promise<void> {
  return call<void>(
    `/v1/clubs/${encodeURIComponent(clubId)}/roster/${encodeURIComponent(rosterId)}`,
    { method: "DELETE", token, meta },
  );
}

export type Membership = {
  roster_id: string;
  club_id: string;
  club_name: string;
  sport: string;
  lga_name: string;
  verified_club: boolean;
};

export type MyClubs = { current: Membership | null; invitations: Membership[] };

/** ATH-05: the caller's current club and the invitations waiting for an answer. */
export function getMyClubs(token: string): Promise<MyClubs> {
  return call<MyClubs>("/v1/athletes/me/clubs", { token });
}

export function answerInvitation(
  token: string,
  rosterId: string,
  answer: "accept" | "decline",
  meta: ClientMeta,
): Promise<void> {
  return call<void>(
    `/v1/athletes/me/invitations/${encodeURIComponent(rosterId)}/${answer}`,
    { method: "POST", token, meta },
  );
}

export type ClubVerification = {
  club_id: string;
  club_name: string;
  club_status: "pending_review" | "approved" | "suspended";
  verified: boolean;
  state: "none" | "draft" | "under_review" | "approved" | "rejected";
  /** The document's own processing state, once one was sent. */
  document: "pending" | "uploaded" | "ready" | "unreadable" | "deleted" | null;
  price_kobo: number;
  paid: boolean;
  reason: string | null;
};

/** CLB-04: where the club's verification stands. */
export function getClubVerification(token: string, clubId: string): Promise<ClubVerification> {
  return call<ClubVerification>(`/v1/clubs/${encodeURIComponent(clubId)}/verification`, { token });
}

/** Open a slot for the club's document, send the bytes through the API, confirm. */
export async function uploadClubDocument(
  token: string,
  clubId: string,
  file: { type: string; size: number; bytes: ArrayBuffer },
  meta: ClientMeta,
): Promise<void> {
  const base = `/v1/clubs/${encodeURIComponent(clubId)}/verification/uploads`;
  const slot = await call<{ media_id: string }>(base, {
    method: "POST",
    body: JSON.stringify({ content_type: file.type, size_bytes: file.size }),
    token,
    meta,
  });
  await call<void>(`${base}/${slot.media_id}/content`, {
    method: "PUT",
    body: file.bytes,
    headers: { "content-type": "application/octet-stream" },
    token,
    meta,
  });
  await call<void>(`${base}/${slot.media_id}/confirm`, { method: "POST", token, meta });
}

export function startClubPayment(
  token: string,
  clubId: string,
  meta: ClientMeta,
): Promise<StartedPayment> {
  return call<StartedPayment>(`/v1/clubs/${encodeURIComponent(clubId)}/verification/payment`, {
    method: "POST",
    token,
    meta,
  });
}

export function resubmitClubVerification(
  token: string,
  clubId: string,
  meta: ClientMeta,
): Promise<void> {
  return call<void>(`/v1/clubs/${encodeURIComponent(clubId)}/verification/resubmit`, {
    method: "POST",
    token,
    meta,
  });
}

export type CoordinatorDashboard = {
  lga_id: string;
  lga_name: string;
  registered: number;
  paid: number;
  to_review: number;
  /** Whole hours the oldest waiting case has sat; null when nothing is waiting. */
  oldest_waiting_hours: number | null;
  clubs: number;
  /** Whether this person can start assisted (cash) payments in this LGA. */
  can_assist: boolean;
  collected_kobo: number;
  collected_count: number;
  limit_kobo: number;
  limit_count: number;
  cap_reached: boolean;
};

/** CRD-01: one LGA's numbers, and the caller's own cash total for today. */
export function getCoordinatorDashboard(token: string, lga: string): Promise<CoordinatorDashboard> {
  return call<CoordinatorDashboard>(`/v1/lgas/${encodeURIComponent(lga)}/dashboard`, { token });
}

export type FoundAthlete = {
  kuid: string;
  full_name: string;
  playing_position: string | null;
  verified: boolean;
};

export type AthleteSearch = { people: FoundAthlete[]; page: number; has_more: boolean };

/** CRD-03: find an athlete in one LGA by name, ID or phone. Elsewhere is simply not found. */
export function searchAthletes(
  token: string,
  lga: string,
  q: string,
  page: number,
): Promise<AthleteSearch> {
  return call<AthleteSearch>(
    `/v1/lgas/${encodeURIComponent(lga)}/athlete-search?${new URLSearchParams({ q, page: String(page) })}`,
    { token },
  );
}

// ---------------------------------------------------------------------------
// The administrator console (ADM-01, ADM-02, ADM-06, club approval and review)
// ---------------------------------------------------------------------------
export type AdminOverview = {
  collected_kobo: number;
  payments: number;
  unresolved: number;
  /** null until the nightly integrity check has ever run. */
  ledger_ok: boolean | null;
  ledger_checked_at: string | null;
  registered: number;
  paid: number;
  conversion_percent: number;
  clubs: number;
  verified_clubs: number;
  clubs_waiting: number;
  review_median_hours: number | null;
  live_lgas: number;
};

export function getAdminOverview(token: string): Promise<AdminOverview> {
  return call<AdminOverview>("/v1/admin/overview", { token });
}

export type AdminGrant = {
  grant_id: string;
  role: string;
  scope_kind: string;
  scope_id: string | null;
  scope_name: string | null;
};

export type AdminUser = {
  user_id: string;
  full_name: string;
  phone_masked: string;
  kuid: string | null;
  last_seen: string | null;
  roles: AdminGrant[];
};

export type AdminUsers = { users: AdminUser[]; page: number; has_more: boolean };

export function findAdminUsers(
  token: string,
  q: string,
  role: string,
  page: number,
): Promise<AdminUsers> {
  return call<AdminUsers>(
    `/v1/admin/users?${new URLSearchParams({ q, role, page: String(page) })}`,
    { token },
  );
}

export function getAdminUser(token: string, userId: string): Promise<AdminUser> {
  return call<AdminUser>(`/v1/admin/users/${encodeURIComponent(userId)}`, { token });
}

export type RoleKind = { code: string; description: string; scope_kind: string };

export function getRoleKinds(token: string): Promise<RoleKind[]> {
  return call<RoleKind[]>("/v1/admin/roles", { token });
}

export function grantRole(
  token: string,
  userId: string,
  role: string,
  scopeId: string | null,
  reason: string,
  currentPassword: string,
  meta: ClientMeta,
): Promise<{ grant_id: string }> {
  return call<{ grant_id: string }>(`/v1/admin/users/${encodeURIComponent(userId)}/roles`, {
    method: "POST",
    body: JSON.stringify({
      role,
      scope_id: scopeId,
      reason,
      current_password: currentPassword,
    }),
    token,
    meta,
  });
}

export function revokeGrant(
  token: string,
  grantId: string,
  reason: string,
  currentPassword: string,
  meta: ClientMeta,
): Promise<void> {
  return call<void>(`/v1/admin/role-grants/${encodeURIComponent(grantId)}/revoke`, {
    method: "POST",
    body: JSON.stringify({ reason, current_password: currentPassword }),
    token,
    meta,
  });
}

export function endUserSessions(
  token: string,
  userId: string,
  reason: string,
  meta: ClientMeta,
): Promise<{ sessions_ended: number }> {
  return call<{ sessions_ended: number }>(
    `/v1/admin/users/${encodeURIComponent(userId)}/sessions/end`,
    { method: "POST", body: JSON.stringify({ reason }), token, meta },
  );
}

export type AdminClub = {
  club_id: string;
  name: string;
  sport: string;
  lga_name: string;
  status: "pending_review" | "approved" | "suspended";
  verified: boolean;
  representative: string;
  verification: string | null;
  created_at: string;
};

export type AdminClubs = { clubs: AdminClub[]; page: number; has_more: boolean };

export function listAdminClubs(token: string, status: string, page: number): Promise<AdminClubs> {
  return call<AdminClubs>(`/v1/admin/clubs?${new URLSearchParams({ status, page: String(page) })}`, {
    token,
  });
}

export function setClubStatus(
  token: string,
  clubId: string,
  status: "approve" | "suspend",
  meta: ClientMeta,
): Promise<void> {
  return call<void>(`/v1/admin/clubs/${encodeURIComponent(clubId)}/${status}`, {
    method: "POST",
    token,
    meta,
  });
}

export type ClubVerificationWaiting = {
  club_id: string;
  club_name: string;
  lga_name: string;
  submitted_at: string;
};

export function getClubVerificationQueue(token: string): Promise<ClubVerificationWaiting[]> {
  return call<ClubVerificationWaiting[]>("/v1/admin/club-verification/queue", { token });
}

export function decideClubVerification(
  token: string,
  clubId: string,
  decision: "approve" | "reject",
  reason: string,
  meta: ClientMeta,
): Promise<void> {
  return call<void>(`/v1/admin/club-verification/${encodeURIComponent(clubId)}/${decision}`, {
    method: "POST",
    body: decision === "reject" ? JSON.stringify({ reason }) : undefined,
    token,
    meta,
  });
}

/** Withdraw a club's verified badge (reason and password required, like ADM-03). */
export function revokeClubVerification(
  token: string,
  clubId: string,
  reason: string,
  currentPassword: string,
  meta: ClientMeta,
): Promise<void> {
  return call<void>(`/v1/admin/club-verification/${encodeURIComponent(clubId)}/revoke`, {
    method: "POST",
    body: JSON.stringify({ reason, current_password: currentPassword }),
    token,
    meta,
  });
}

export type AuditEntry = {
  entry_id: number;
  occurred_at: string;
  actor: string;
  actor_role: string | null;
  action: string;
  subject_type: string;
  subject_id: string;
  reference: string | null;
};

export type AuditPage = { entries: AuditEntry[]; page: number; has_more: boolean };

export function getAuditLog(
  token: string,
  filters: { actor: string; action: string; since: string; until: string; page: number },
): Promise<AuditPage> {
  const params = new URLSearchParams({ page: String(filters.page) });
  for (const key of ["actor", "action", "since", "until"] as const) {
    if (filters[key]) params.set(key, filters[key]);
  }
  return call<AuditPage>(`/v1/admin/audit?${params}`, { token });
}

export type CardBatch = {
  people: { kuid: string; full_name: string; registered_on: string; printed: boolean }[];
  total: number;
  page: number;
  pages: number;
  per_sheet: number;
};

export type CardFilters = { since: string; until: string; unprinted: boolean; page: number };

const cardQuery = (f: CardFilters): string => {
  const params = new URLSearchParams({ unprinted: String(f.unprinted), page: String(f.page) });
  if (f.since) params.set("since", f.since);
  if (f.until) params.set("until", f.until);
  return params.toString();
};

/** CRD-06: athletes in one LGA whose cards can be printed, one page of the batch. */
export function getCardBatch(token: string, lga: string, filters: CardFilters): Promise<CardBatch> {
  return call<CardBatch>(`/v1/lgas/${encodeURIComponent(lga)}/cards?${cardQuery(filters)}`, { token });
}

/** The same page as A4 sheets of eight cards. Slow to draw, so it gets a long deadline. */
export function getCardSheets(token: string, lga: string, filters: CardFilters): Promise<Response | null> {
  return getImage(`/v1/lgas/${encodeURIComponent(lga)}/cards.pdf?${cardQuery(filters)}`, token, 90_000);
}

export function markCardsPrinted(
  token: string,
  lga: string,
  kuids: string[],
  meta: ClientMeta,
): Promise<{ marked: number }> {
  return call<{ marked: number }>(`/v1/lgas/${encodeURIComponent(lga)}/cards/printed`, {
    method: "POST",
    body: JSON.stringify({ kuids }),
    token,
    meta,
  });
}

export function getVerification(token: string): Promise<Verification> {
  return call<Verification>("/v1/verification", { token });
}

/** Open a slot, send the bytes through the API, confirm. The no-JavaScript upload. */
export async function uploadFile(
  token: string,
  kind: "photo" | "document",
  file: { type: string; size: number; bytes: ArrayBuffer },
  meta: ClientMeta,
): Promise<void> {
  const slot = await call<{ media_id: string }>("/v1/verification/uploads", {
    method: "POST",
    body: JSON.stringify({ kind, content_type: file.type, size_bytes: file.size }),
    token,
    meta,
  });
  await call<void>(`/v1/verification/uploads/${slot.media_id}/content`, {
    method: "PUT",
    body: file.bytes,
    headers: { "content-type": "application/octet-stream" },
    token,
    meta,
  });
  await call<void>(`/v1/verification/uploads/${slot.media_id}/confirm`, {
    method: "POST",
    token,
    meta,
  });
}

export function resubmitVerification(token: string, meta: ClientMeta): Promise<void> {
  return call<void>("/v1/verification/resubmit", { method: "POST", token, meta });
}

export function getReviewQueue(token: string, lga: string): Promise<QueueItem[]> {
  return call<QueueItem[]>(`/v1/lgas/${encodeURIComponent(lga)}/verification/queue`, { token });
}

export function getReviewCase(token: string, lga: string, id: string): Promise<ReviewCase> {
  return call<ReviewCase>(
    `/v1/lgas/${encodeURIComponent(lga)}/verification/${encodeURIComponent(id)}`,
    { token },
  );
}

export type AdminVerificationLookup = {
  request_id: string;
  kuid: string;
  full_name: string;
  status: string;
  attempt: number;
  decided_at: string | null;
  revocable: boolean;
};

/** ADM-03: find an athlete's verification request by KUID, to withdraw it. */
export function findVerificationByKuid(
  token: string,
  kuid: string,
): Promise<AdminVerificationLookup> {
  return call<AdminVerificationLookup>(
    `/v1/admin/verification/by-kuid/${encodeURIComponent(kuid)}`,
    { token },
  );
}

export function revokeVerification(
  token: string,
  requestId: string,
  reason: string,
  currentPassword: string,
  meta: ClientMeta,
): Promise<void> {
  return call<void>(`/v1/admin/verification/${encodeURIComponent(requestId)}/revoke`, {
    method: "POST",
    body: JSON.stringify({ reason, current_password: currentPassword }),
    token,
    meta,
  });
}

export type AdminPaymentLookup = {
  reference: string;
  purpose: string;
  status: string;
  expected_kobo: number;
  payer_name: string;
  athlete_kuid: string | null;
  athlete_name: string | null;
  gross_kobo: number | null;
  already_reversed: boolean;
  reversible: boolean;
};

/** ADM-04: look up a payment by reference, before recording a refund against it. */
export function findPaymentByReference(
  token: string,
  reference: string,
): Promise<AdminPaymentLookup> {
  return call<AdminPaymentLookup>(`/v1/admin/payments/${encodeURIComponent(reference)}`, { token });
}

export function recordReversal(
  token: string,
  reference: string,
  amountKobo: number,
  reason: string,
  currentPassword: string,
  meta: ClientMeta,
): Promise<{ reference: string; amount_kobo: number; gross_kobo: number }> {
  return call(`/v1/admin/payments/${encodeURIComponent(reference)}/reversal`, {
    method: "POST",
    body: JSON.stringify({ amount_kobo: amountKobo, reason, current_password: currentPassword }),
    token,
    meta,
  });
}

export function decideCase(
  token: string,
  lga: string,
  id: string,
  decision: { approve: true } | { reject: string },
  meta: ClientMeta,
): Promise<{ outcome: string }> {
  const base = `/v1/lgas/${encodeURIComponent(lga)}/verification/${encodeURIComponent(id)}`;
  return "approve" in decision
    ? call(`${base}/approve`, { method: "POST", token, meta })
    : call(`${base}/reject`, {
        method: "POST",
        body: JSON.stringify({ reason: decision.reject }),
        token,
        meta,
      });
}

/** An image the API would only give to someone allowed to see it. Bytes, or null. */
export async function getImage(
  path: string,
  token?: string,
  timeoutMs: number = TIMEOUT_MS,
): Promise<Response | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      signal: controller.signal,
      cache: "no-store",
      headers: token ? { authorization: `Bearer ${token}` } : {},
    });
    return response.ok ? response : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

export function getPayment(token: string, reference: string): Promise<Payment> {
  return call<Payment>(`/v1/payments/${encodeURIComponent(reference)}`, { token });
}

/** ATH-04: every payment the caller has ever started, newest first. */
export function listPayments(token: string): Promise<Payment[]> {
  return call<Payment[]>("/v1/payments", { token });
}

export type AthleteDetails = {
  kuid: string | null;
  full_name: string;
  gender: string | null;
  date_of_birth: string;
  nationality: string | null;
  state_of_origin: string | null;
  sport: string;
  lga_name: string;
  email: string | null;
  playing_position: string | null;
  secondary_position: string | null;
  dominant_side: string | null;
  secondary_sport: string | null;
  years_experience: number | null;
  height_cm: number | null;
  weight_kg: number | null;
  level_played: string | null;
  address_line: string | null;
  town: string | null;
  emergency_name: string | null;
  emergency_relationship: string | null;
  emergency_phone: string | null;
};

export type DetailsUpdate = {
  playing_position: string;
  secondary_position: string | null;
  dominant_side: string;
  secondary_sport: string | null;
  years_experience: number;
  height_cm: number;
  weight_kg: number;
  level_played: string;
  address_line: string;
  town: string;
  emergency_name: string;
  emergency_relationship: string;
  emergency_phone: string;
};

/** ATH-02: the signed-in athlete's own record, for the details screen. */
export function getMyAthleteDetails(token: string): Promise<AthleteDetails> {
  return call<AthleteDetails>("/v1/athletes/me", { token });
}

export function updateMyAthleteDetails(
  token: string,
  input: DetailsUpdate,
): Promise<AthleteDetails> {
  return call<AthleteDetails>("/v1/athletes/me", {
    method: "PUT",
    body: JSON.stringify(input),
    token,
  });
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

/** The wallet card — name, KUID and QR in one image — as PNG or PDF bytes. */
export async function getCardFile(
  kuid: string,
  format: "png" | "pdf",
): Promise<ArrayBuffer | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(
      `${API_BASE}/v1/public/athletes/${encodeURIComponent(kuid)}/card.${format}`,
      { signal: controller.signal, cache: "no-store" },
    );
    return response.ok ? await response.arrayBuffer() : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

export { API_BASE };
