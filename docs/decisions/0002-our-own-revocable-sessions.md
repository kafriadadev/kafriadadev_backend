# ADR 0002 — Our own revocable session cookie, not Supabase Auth in the browser

**Status:** Accepted · 11 September 2026
**Context:** Stage 1.2 Access

## Context

Two ways to sign people in were on the table:

- **A.** Supabase (the database) holds the credentials; the domain API checks
  them and issues its own opaque session token, which the presentation tier keeps
  in an httpOnly cookie and forwards server-to-server.
- **B.** Supabase Auth (GoTrue) in the browser, issuing JWTs the browser holds.

Three facts decided it:

1. **Coordinators handle cash on shared phones.** Ending a session has to take
   effect on the next request. A self-contained JWT stays valid until it expires
   unless every request also checks a revocation list — at which point it is a
   session table with extra steps.
2. **Every screen must work with JavaScript off** (Opera Mini). B needs the
   Supabase client running in the browser.
3. **The browser never talks to the domain tier** (Target Architecture, BFF
   pattern). B puts a bearer credential in browser-reachable JavaScript.

## Decision

**A.** Chosen by the product owner on 11 September 2026.

- Passwords are Argon2id hashes in `ops.users`, which lives in the Supabase
  Postgres database. This was already built in Stage 0 (concurrency cap, timing
  equalisation). GoTrue is not used: its phone sign-in needs an SMS provider it
  supports natively, and Termii is not one of them.
- `POST /v1/sessions` checks phone + password and returns a 256-bit token once.
  `ops.sessions` stores only its SHA-256.
- The web tier sets it as `kaf_session` (httpOnly, SameSite=Lax, Secure in
  production) and forwards it as `Authorization: Bearer`. Staff get a browser-
  session cookie; athletes one that lasts until the absolute expiry.
- Two clocks per session: idle (30 min staff, 30 days athletes; slides on every
  request) and absolute (7 days staff, 90 days athletes; never moves). The idle
  window is stored on the row (`idle_seconds`, migration 0003). Any role change
  ends the holder's sessions.
- One-time codes (sign-in by code, password reset) will use the same session
  issue path (`access.issue_session`) once OTP exists.

## Rejected

- **B, Supabase Auth in the browser** — for the three reasons above.
- **Signed stateless cookies** — cannot be revoked without a server-side list.

## Revisit if

- Federations or a native app need delegated access (OAuth-style tokens for
  third parties). That is an additional surface, not a replacement.
- The per-request session lookup shows up as a measured bottleneck. It is one
  indexed UPDATE per request.
