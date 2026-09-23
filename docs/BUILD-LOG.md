# Build log

Every piece of engineering work done on KAFRIADA, in one place, newest entry
first. Not the same thing as [`TEST-LOG.md`](./TEST-LOG.md) (the developer's
test runs) or [`ISSUE-LOG.md`](./ISSUE-LOG.md) (their stuck points) — this is
the build itself: what was shipped, why it was built that way, what was
verified and how, and what is still open. `CLAUDE.md`'s Status section is the
current-state summary distilled from this; this file is the history that
summary is distilled from. `docs/TODO.md` is what's left, in order.

Never delete or rewrite an entry. If something turns out to be wrong, say so
in a new entry and link back to the old one.

## Entry template

```
## <YYYY-MM-DD> — <title>
**Commit(s):** `<hash>` [, `<hash>` ...]

**Built:** what exists now that didn't before, in plain terms.

**Why:** the decision behind it, if it wasn't the obvious choice.

**Verified:** how, specifically — which tests, against which database, what
was checked live and what the result was. Say plainly when something is
"code done, not run for real" rather than implying more than was checked.

**Not done / open:** gaps, deferred pieces, follow-ups.
```

---

## 2026-09-23 — Migration 0010: clubs
**Commit(s):** *(pending)*

**Built:** three tables in the `identity` schema — `organizations` (a club:
name, sport, state/LGA, contact phone, `rep_user_id`, `status`
pending_review/approved/suspended, `stage` 1/2), `teams` (a squad within a
club: sport, age category, gender) and `roster_members` (an athlete on a
team: invited/active/released, `jersey_no`, `invited_by`). One default team
is meant to be created alongside every organization at registration, so the
schema matches the spec's three-table shape even though CLB-01–04's screens
never expose team selection. `career_events.club_id` — left bare in
migration 0002 with a comment that it would be checked "once the clubs
context exists" — now has that foreign key. `club.create` is granted to the
`athlete` role, which is the one role every account already holds.

**Why `club.create` moved to `athlete`:** migration 0001 granted it only to
`lga_coordinator`/`state_coordinator`, written before the wireframes existed.
CLB-01 says "any signed-in user" may register a club and becomes its
`club_admin` — in this system that is exactly the `athlete` role, not a new
one. Coordinators keep the permission too, since CLB-01 itself names
coordinator-entered clubs as its own fallback if the self-service screen has
to be cut.

**Why the membership rule is a global partial unique index, not a per-team
one:** the pilot build spec's own sketch was `(team_id, athlete_id)`
uniqueness for an active row. `docs/TODO.md` asks for
*at-most-one-open-membership*, and CLB-03's wireframe explains why: accepting
an invitation "moves" a player from their current club to the new one, so an
athlete can be `active` on at most one roster anywhere, not one per team.
That is `roster_members_one_active_per_athlete`, a unique index on
`athlete_id` alone — the database refuses a second active row regardless of
which team it names, rather than the service having to remember to release
the old one first. A pending `invited` row is scoped per team instead:
different clubs may invite the same athlete at once (CLB-03 warns about
this, it does not refuse it), but the same club cannot queue the same
invitation twice.

**Verified:** `check_migration_safety.py` clean (10 migrations). Applied,
reversed and re-applied cleanly against the live Supabase project (through
the IPv4 pooler). The full suite was then run three times while chasing two
false alarms, both pre-existing and both traced to a stretch of this
session's own making, not to this migration:

1. A first Supabase run showed dozens of setup errors — `OTP_CHANNEL=email`
   was still set in `api/.env` from the pilot-channel work, and every
   registering test needs an email under that setting. Exporting
   `OTP_CHANNEL=sms` for the run fixed it; this is an already-documented
   gotcha, not a new one.
2. The Supabase run then became too slow to trust (connection contention
   after an earlier `kill -9` of a stuck pytest process left connections
   open against the free-tier project's connection cap), so the suite was
   run instead against a local, disposable PostgreSQL 15 that this project's
   own gotchas describe building. It failed twice more, on two tests neither
   of which touches clubs: `test_integrity.py`'s media-object-missing check
   (a stray-data problem — this local instance had accumulated 948 `ready`
   media rows across many sessions today, and the check's own `LIMIT 500`
   random sample only catches the row a given test cares about about half
   the time) and one rate-limit timing test. Dropping and recreating the
   local database, re-running `infra/bootstrap-roles.sql` and `alembic
   upgrade head` from empty, and running the full suite again gave a clean
   pass with zero failures — confirming both were pre-existing environment
   noise, not a regression from this migration.

**Not done / open:** no service layer, no API routes, no screens yet — this
entry is schema only. CLB-01 through CLB-04 and ATH-05 are next, per the
build order already agreed (`docs/TODO.md`).

---

## 2026-09-23 — CRD-04: coordinator pays on behalf
**Commit(s):** `e34ad39`

**Built:** `POST /v1/lgas/{lga_id}/athletes/{kuid}/payments`
(`payment.initiate_behalf`, scope `lga`) and `/assist-pay` — a coordinator
enters an athlete's KUID and is sent to Paystack, exactly one step ahead of
the athlete's own `/pay`. `on_behalf_of` and `coordinator_id` are set on the
row; two new settings, `assisted_payments_per_coordinator_daily` and
`assisted_kobo_per_coordinator_daily`, cap what one coordinator may start in
a day.

**Why the caps exist from the first line, with placeholder numbers:** nothing
here asks the athlete to confirm before their record is charged for, so the
only thing bounding a compromised coordinator session is these two numbers.
No document sets them. Rather than block the feature on a number nobody can
give yet, the code enforces a placeholder (20/day, ₦50,000/day — chosen to be
obviously survivable, not obviously right) and says plainly in three places
(the setting's own docstring, `TODO.md`, `CLAUDE.md`) that it needs the
project lead's real number, ideally from Wave 1's actual figures rather than
guessed in advance of any.

**Two real bugs found while building this, both the kind that only show up
once a second payer exists:**

1. **`mark_paid` would have taken the money and reviewed nobody.** It read
   `AND pay.on_behalf_of IS NULL` — correct while only self-payment existed,
   silently wrong the moment a second kind of payer did. An assisted payment
   would have settled into the ledger exactly as it should, and moved no
   verification to review at all, because the row it looked for belonged to
   the *payer* and the payer is now sometimes not the athlete. Fixed by
   resolving whose draft to move — `on_behalf_of` if set, the payer's own
   athlete row otherwise — rather than assuming there is only one kind of
   answer.
2. **The route's own scope check cannot catch a coordinator naming the wrong
   athlete.** `Requires(..., scope="lga")` reads `lga_id` from the *path* and
   confirms the coordinator holds a grant on it — that is all it can do. It
   has no way to know whether the *athlete named in the same path* is
   actually in that LGA. Get this backwards — trust the permission layer to
   have covered it — and any LGA coordinator could pay for any athlete in the
   country, so long as the `lga_id` segment matched their own grant. The
   check belongs to the service, against the database, not the caller's
   claim: `_athlete_in_lga()` joins the athlete's `current_lga_id` against the
   path before anything else runs.

**Verified:** `tests/test_payments_on_behalf.py`, 10 tests — the ledger and
the review both land on the athlete, the receipt reaches the athlete's phone
and not the coordinator's, an athlete outside the coordinator's LGA is
refused (proved with a real second coordinator scoped to a real second LGA,
not a mock), an athlete with no files yet or already paid is refused, both
caps refuse at the right moment, and a failed attempt does not count against
either cap. Full suite green against a real database, twice. A live HTTP
round trip against the running server (Supabase, through the pooler)
confirmed both the outer 403 (coordinator has no grant at all on the path's
LGA) and the inner 404 (grant matches the path, athlete does not).

One flake surfaced and was chased down rather than waved through: the
existing `test_a_message_is_sent_once…` failed twice in a row on the local
database, which had accumulated **1,109** outbox rows across a day of
repeated full-suite runs, itself worsened by this session's new
`notification.requested` rows (payment receipts, decision emails). Confirmed
as pile-up, not a regression, by clearing the table and rerunning clean.

**Not done / open:** no separate "look up the athlete first" preview step —
the single form either starts the checkout or bounces back with the exact
refusal, unlike ADM-03/04's two-step pattern. Deliberate, for now: proportional
to what a checkout redirect needs versus what withdrawing a badge or writing a
ledger line by hand needs, but worth revisiting once real coordinators use it.

---

## 2026-09-23 — Paystack run against the real sandbox; a launch-blocking bug found
**Commit(s):** *(with the notification work; `api/.env` holds the keys and is not committed)*

**Built:** nothing new — this was *verification*, and it earned its keep. Test
keys arrived, so `PAYMENT_PROVIDER=paystack` was switched on and the adapter
pointed at the live sandbox for the first time since 2.1 was written.

**What it found:**

1. **`.invalid` placeholder emails are refused — this would have broken
   payments at launch.** An athlete need not have an email, so one is invented
   for Paystack, which insists on the field. It was built on
   `payments.kafriada.invalid`: RFC 2606 reserves `.invalid` for exactly this,
   it never resolves, and a receipt sent there can never reach a stranger. It
   is the *correct* choice on paper. Paystack answers `400 "email" must be a
   valid email` and refuses the checkout outright — so **every athlete without
   an email on file could not have paid at all**.
   Worse, a test covered this and asserted the bug: `email.endswith(".invalid")`.
   It passed for months because it ran against `FakeProvider`, which accepts
   anything given to it. A fake proving the opposite of the truth is the whole
   argument for running the real thing before launch and not after.
   Fixed: the default is now `payments.kafriada.ng`, and the test asserts a
   deliverable TLD instead. Domains checked and accepted: `kafriada.ng`,
   `payments.kafriada.ng`, `badellafarmandranch.site`.

2. **`fees` is present, so real payments will not freeze.** `decide()` FREEZES
   a payment whose event carries no fee — a deliberate refusal to guess. Nobody
   had confirmed Paystack actually sends one. It does: ₦2,500 costs **13750
   kobo**, settling at **236250 kobo (₦2,362.50)**. That is also the exact
   figure `.env`'s OPEN QUESTION A1 was waiting on — whether ₦2,500 is the
   price or the take-home is now a decision with a real number behind it.

3. **The money path works end to end against real Paystack.** Our
   `start_payment` created a checkout, a real test card paid it, and our own
   `reconcile()` job settled it: exactly two ledger lines (250000 credit,
   13750 fee debit) and one idempotency row. That is Stage 2 exit criterion 1
   in substance, in test mode.

4. Paystack **rate-limits** `initialize` — 429 after a handful in quick
   succession. Worth knowing before the 200-registration burst test.

**Not done / open:** no webhook has actually been *received* from Paystack —
that needs a publicly reachable URL, so only the reconciliation path is proven
directly. Both feed the same strict reader and the same idempotency key, so the
parsing and settlement halves are covered; the HMAC signature check over a real
Paystack body is not. Live keys still need business verification, which needs a
current CAC registration.

---

## 2026-09-23 — 2.3: the outbox carries every notification, not just SMS
**Commit(s):** *(see below)*

**Built:** a third outbox event type, `notification.requested`, addressed to a
**person** rather than to a phone number or an inbox. The caller supplies both
wordings (`sms` and `subject`/`email`) and says who to tell; the worker looks
up how to reach them and picks the channel when it actually sends.
`outbox.service.prefers_email()` is now the one place the pilot's channel rule
lives, and the OTP path was changed to call it too, so the two cannot drift.

Wired to the two things that needed it:
* **All four verification decisions** (approved, rejected, escalated, revoked),
  which previously only ever queued SMS and so reached nobody while Twilio is
  unregistered.
* **A payment receipt on settlement**, which did not exist at all. It goes to
  the athlete the payment is *for* (`on_behalf_of`), not to whoever pressed
  pay — which is what makes it half of the Stage 2 exit criterion "a
  coordinator pays for someone else and that person receives the receipt". The
  other half is the coordinator flow itself, in 2.4.

**Why addressed to a person rather than an address:** two reasons, and the
second is load-bearing. A number changed between queueing and sending is still
the one used. And **a caller with no grant on `ops.users` can still notify
somebody** — settlement runs as `kaf_money`, which by design cannot read that
table at all, so if the address had to be resolved by the caller, a payment
could not send its own receipt. That constraint was found by checking the
grants rather than assumed: `kaf_money` has `INSERT` on `ops.outbox` and
`SELECT` on `identity.athletes`, and nothing on `ops.users`.

Someone unreachable is a **permanent** failure, not a retry — there is no
number to try again later — and the row is kept as the evidence that nobody
was told.

**Verified:** `tests/test_notifications.py`, six new tests, including the
money-role case that connects as `kaf_money`, asserts the `ops.users` read is
refused, and then queues and delivers a notification to that same person
anyway. The settlement, OTP/outbox and verification suites all re-run clean
(70 tests), plus the full suite. Writing the tests found two real things: the
delivered-row scrub was dropping `user_id`, which is the only link from a sent
message back to who was told (now kept), and `phone_e164` is `NOT NULL`, so
"unreachable" in this schema means anonymised rather than blank.

**Not done / open:** the receipt wording is plain text; no HTML template like
the OTP email has. Nothing yet notifies on a payment that *fails* or freezes —
deliberate, since a frozen payment is an alarm for a person to look at, not
something to tell the athlete about automatically.

---

## 2026-09-23 — Supabase reachable again: the direct endpoint is IPv6-only
**Commit(s):** *(config + docs; `api/.env` is gitignored and not committed)*

**Built:** nothing in the application — this was a connection problem, and the
fix is configuration. `api/.env`'s four `DATABASE_URL_*` now point at
Supabase's Supavisor pooler instead of the direct endpoint:

    host  aws-1-eu-west-1.pooler.supabase.com
    port  5432                       (session mode)
    user  <role>.slwlefnfdsjfeimyjhag

The old direct URLs are kept commented above each one, and
`.env.backup-before-pooler` holds the original file.

**Why:** `db.<ref>.supabase.co` resolves **IPv6-only** — Supabase ran out of
IPv4 addresses — so on a network without working IPv6 the name resolves and
the TCP connect then hangs to timeout. That is the whole of the "Supabase is
down" story that ran through 2026-09-20 to 09-23: the project was healthy the
entire time and the dashboard was right to say so; this machine simply could
not route to that address. The pooler publishes A records and is reachable.
Credit where due — the project lead pushed back on the diagnosis and asked
whether IPv4 could be used, which is exactly what unblocked it.

Two choices inside that fix worth keeping:
* **Session mode (5432), not transaction mode (6543).** `kafriada.jobs` takes
  *session-level* advisory locks and psycopg auto-prepares statements; neither
  survives transaction pooling. Session mode behaves like a direct connection,
  so no application code changed at all.
* **`<role>.<ref>` usernames keep all four roles distinct**, so the privilege
  boundary — the thing every other invariant leans on — is untouched. Verified
  by connecting as each of the four and reading back `current_user`.

Also note: `aws-0-eu-west-1` is a *different* tenant cluster. It answers, then
refuses with `ENOTFOUND tenant/user`, which reads like a credentials problem
and is not one.

**Verified:** all four roles connect and report their own identity; `/readyz`
(which probes every role) returns `{"status":"ready"}`; the web tier renders
live LGA data from Supabase through the API; migration 0009 applied to
Supabase, bringing it to the same head the local database was on.

**Also cleared while the link was up:** the throwaway super_admin account made
for ADM-04's live check. It could **not** be deleted — `ledger_entries
.recorded_by` still references it and the ledger is append-only, so the
database refused to erase the authorship of a ledger line. That is the
invariant doing its job, so the account was neutralised instead: password
cleared, role grant removed, sessions deleted, `status='anonymised'`. The
ledger line it authored stays.

---

## 2026-09-23 — ATH-02: edit my details
**Commit(s):** `ef30b84`

**Built:** migration 0009 — four nullable columns on `identity.athletes`
(`gender`, `dominant_side`, `secondary_sport`, `years_experience`), each
CHECK-constrained to a small fixed set. `get_athlete_details()` /
`update_athlete_details()` in `contexts/identity/service.py`; `GET`/
`PUT /v1/athletes/me`; `/details`, one form, sport and position shown for
context but not editable there.

**Why:** the permission model was already waiting for this —
`athlete.read_self` and `athlete.update_self` have been seeded for the
`athlete` role since migration 0001 (Stage 0), with nothing behind either
until now. The four fixed-set CHECKs over a lookup table: none of the four
is likely to grow a fifth option that needs its own migration, and a CHECK
is one statement instead of a table, a foreign key and a seed data insert.

**Verified:** against a private local PostgreSQL 15, stood up fresh for
this (`initdb`/`pg_ctl`/`bootstrap-roles.sql`/`alembic upgrade head`,
per `CLAUDE.md`'s documented recipe) because Supabase had been unreachable
all session — confirmed at the TCP level with nothing else running
(pool contention had been the cause of an earlier batch of failures that
same day; this was the link itself, checked in isolation). Migration
applies and reverses cleanly; `check_migration_safety.py` clean; a live
GET → PUT(valid) → PUT(invalid, correctly refused with the right field) →
GET loop against a real registered athlete; `test_permission_matrix.py`
and `test_route_manifest.py` both pass; a full `check:render` run —
including, for the first time, a signed-in contrast/overflow audit of
`/details` and `/payments` themselves via `EXTRA_SESSIONS` — all pass.

**Not done / open:** migration 0009 not yet applied to Supabase — repeat
once it's reachable. Two choices the migration flags for the project lead
to confirm before launch: the four gender options offered, and the 0–100
bound on years of experience — neither is pinned down by the spec as built
here. Also fixed in passing: `docs/TODO.md`'s screen-built count (said 12,
was actually 22) and its "empty contexts" line (said `media` and
`verification` were empty; they haven't been since 2.2) — both corrected.

---

## 2026-09-22 — ATH-04: my payments
**Commit(s):** `a2db088`

**Built:** `list_payments()` — every payment the caller has ever started,
newest first, same shape as the existing single-payment lookup. `GET
/v1/payments` (same `payment.read_self` permission the single-payment route
already uses). `/payments`: one card per payment — purpose, reference, date,
amount, and the same confirmed/checking/needs-a-check/not-completed language
`/pay` already uses, never the internal status. Linked from `/me`. New
`.pill--bad` CSS variant, for "not completed".

**Verified:** full non-DB suite (no regressions), `npm run typecheck`,
`npm run build`. `check:render`'s other failures (profile/card 404, register
JS-off) are the same Supabase-outage signature as the ADM-03/ADM-04 entries
below — confirmed unrelated (TCP-level).

**Not done / open:** not yet checked signed-in against live data — Supabase
was still down. Repeat once it's back.

---

## 2026-09-22 — This file
**Commit(s):** `7270af8`

**Built:** `docs/BUILD-LOG.md` itself, at the project lead's direct request:
a standing, chronological, append-only record of every piece of engineering
work, kept distinct from the developer's own `TEST-LOG.md`/`ISSUE-LOG.md`/
`DEVELOPER-PROGRESS.md`. Backfilled 17 entries from `git log` and
`CLAUDE.md`'s Status section, covering Stage 0 (2026-09-09) through that
day's ADM-04. `CLAUDE.md` now points here and carries the going-forward
rule: an entry per build session, alongside its commit(s).

---

## 2026-09-22 — ADM-04: record a refund
**Commit(s):** `f287008`

**Built:** `GET /v1/admin/payments/{reference}` — a lookup the reversal API
never had (the existing `POST .../reversal` only ever took a reference an
admin already had from Paystack's own dashboard, with nothing to preview it
against first) — and `/admin/reversal`, the screen: look up by reference,
then an amount, reason and password to confirm. Same two-step shape as
ADM-03, since this is the one screen that writes an amount into the ledger
by hand.

**Why:** `record_reversal()` itself was untouched — it already re-checks the
password, refuses anything not settled or already refunded, and caps the
amount at what was actually paid. The gap was purely "how does an admin see
what they're about to touch before typing a number in."

**Verified:** live, end to end, against Supabase with a real minted
super_admin token: looked up a settled payment (`reversible: true`), looked
up a pending one (`reversible: false`), recorded a refund, confirmed
`already_reversed: true` on re-lookup, and a second attempt was correctly
refused (409). One real bug found and fixed in the process: the lookup used
`money_transaction()` (the `kaf_money` role), which has no grant on
`ops.users` or `identity.athletes` at all — switched to the ordinary
`transaction()` (`kaf_app`), which already has SELECT on `money.payments`
and `money.ledger_entries` (migration 0006's append-only grants). Permission-
matrix test passed the same session (it discovers routes automatically, so
the new one needed no manual entry). `npm run typecheck` and `npm run build`
pass.

**Not done / open:** `test_verification.py` and `test_settlement.py` were
not re-run against this specific change — Supabase's link dropped mid-
session (a bare, unloaded connection attempt timed out; not contention, see
`CLAUDE.md` Gotchas). Run both once it's back.

---

## 2026-09-22 — ADM-03: withdraw a verification
**Commit(s):** `00565a6`

**Built:** `find_by_kuid()` + `GET /v1/admin/verification/by-kuid/{kuid}` —
the API-only `revoke` route (built in 2.2) had no way for a super_admin to
get from a KUID to the request id it needs. `/admin/revoke` is the screen:
look up by KUID, see the athlete and current status, and if it's approved,
a reason and password form to withdraw it.

**Verified:** permission-matrix test passed against Supabase. The lookup
live-checked with a real super_admin token against a real approved request
(`revocable: true`) and a real draft one (`revocable: false`) — both
correct. `revoke()` itself is covered by
`test_verification.py::TestApprovalAndWithdrawal`, which passed. A live curl
of the revoke POST specifically was inconclusive — Supabase's link dropped
mid-attempt — not a failure.

**Not done / open:** the revoke POST itself has not been confirmed by a live
curl call (only via the pre-existing automated test and the in-app flow).

---

## 2026-09-22 — Downloadable wallet card, PNG and PDF
**Commit(s):** `30900a9`

**Built:** `contexts/identity/card.py` draws the card — wordmark, KUID,
name, sport, LGA, the same signed QR the on-screen card uses — with Pillow
(already a dependency), saved as either PNG or a one-page PDF from the same
drawing. `GET /v1/public/athletes/{kuid}/card.png` and `.../card.pdf`, same
`Public`/404 shape as the existing `qr.svg` route, proxied from the web tier
the same way. Three font families (Instrument Serif, Atkinson Hyperlegible,
JetBrains Mono — the same ones the website uses) vendored into
`assets/fonts/` from Google's font repository, OFL licence files included.

**Why:** generated server-side rather than in the browser, because a print
dialog's own "save as PDF" isn't available on every browser this project
targets (Opera Mini among them), so the file needed to be produced directly
rather than assumed. The background is a faint repeating ring — the same
idea as a certificate's security pattern — rather than illustrated icons:
this is a permanent ID, and restraint suited it better than decoration.

**Verified:** rendered and visually inspected; both formats generate
correctly through the live API and the web proxy for a real athlete
(headers, filenames, content-type all correct). Full API test suite,
`npm run typecheck`, `npm run build` and `check:render` all pass.

**Not done / open:** no photo on the card even for verified athletes (the
public profile only exposes one after Stage-2 approval — could be composited
in as a follow-up).

---

## 2026-09-22 — Email at registration, branded Flash + live resend countdown
**Commit(s):** `ee812a2`

**Built:** the register form gained an email field (required only while the
interim email OTP channel is on — see the entry below); the confirm page
says "Sent by email to …" when that's what happened. `components/Flash.tsx`
replaced copy-pasted `.notice` divs on register, sign-in, forgot and confirm
with one component: entrance animation, auto-dismiss on success, focus-on-
error, all inert without JavaScript (renders the same static markup either
way). `components/ResendCountdown.tsx` makes "ask again in N seconds" tick
live and disables the button, re-enabling automatically at zero — with JS
off, the real, always-clickable form is what's there from first paint, and
the server still enforces the wait either way.

**Why:** house rule written down the same day (see `CLAUDE.md`, "Working
style"): copy must read as plain product writing, not AI-generated filler —
prompted by a hint here needing rephrasing.

**Verified:** `npm run typecheck`, `npm run build`, and `check:render`
(contrast, overflow, JS-off round trips) all pass. `check:render` also
caught a real bug mid-build: the Flash bad/warn/good icon was invisible
(`#fffdf7` on `#fffdf7`, a `currentColor` mistake) — found, fixed, confirmed
at 0 low-contrast.

---

## 2026-09-22 — Email delivery via Resend, OTP pilot channel
**Commit(s):** `356c78b`

**Built:** a second, independent notification channel alongside SMS, since
Twilio still has no Nigerian sender ID (see `CLAUDE.md`, "Outside the
code"). `outbox/email_providers.py`: a `Sender` port (`NoSender` /
`ConsoleSender` / `ResendSender`), same transient/permanent failure split as
the Twilio SMS adapter. `contexts/access/email_templates.py`: branded HTML
for the OTP email, table-based and inline-styled so it survives Gmail and
Outlook, using the same document colour tokens as the web app. The outbox
(`outbox/service.py`, `outbox/dispatch.py`) now routes `sms.requested` and
`email.requested` rows to their own sender in one worker. New
`OTP_CHANNEL` setting (`sms`/`email`) — a pilot stand-in, refused in
production — that sends phone-verification and password-reset codes by
email instead of SMS when the account has an email on file; the phone
stays the identity anchor and still gets marked verified. No email on file
still falls back to SMS.

**Verified:** 13 new unit tests plus the full non-DB suite pass; the DB-
backed OTP/outbox tests pass against Supabase; a real registration
delivered a real HTML-templated code to a real inbox via Resend.

**Not done / open:** email is not yet a trigger for anything besides OTP —
verification decisions and payment confirmations still only queue SMS.

---

## 2026-09-21 — 2.3, the safety net: jobs runner, reconciliation, expiry, integrity, refunds
**Commit(s):** `858feb0`, `a801e42` (status)

**Built:** migration 0008 (`ops.job_runs`, an insert-only record of every
background job's run; `GRANT DELETE ON ops.outbox`; a ledger `reversal`
source with `note`/`recorded_by`). `python -m kafriada.jobs` — one process,
no broker — running outbox drain, media re-encoding, reconciliation (every
10 minutes), expiry, session/rate-counter/document sweeps, and a nightly
integrity check, each holding its own Postgres advisory lock so one failing
job never stops the others. `contexts/payments/reconcile.py`: asks
Paystack's verify API and settles only a confirmed `success`, never
reverses anything itself. `expire_stale()`: only `pending` payments older
than 72 hours that Paystack does not say were paid. `integrity.py`: findings
rather than verdicts, checking ledger shape, KUID uniqueness and the
counter, verification consistency, and that media objects exist.
`contexts/ledger/reversal.py`: `record_reversal()` — recording a refund made
by hand in Paystack's dashboard, never calling Paystack itself.

**Verified:** 681 passed / 0 skipped on the local DB. Mutations proved red:
verify status ignored, expiry without asking, wrong-reference acceptance,
integrity checks disabled, missing lock, missing password, no cap, sweeps
too greedy. Found and fixed on the way: `amount_kobo` accepted `"100000"`
and `true` under pydantic's lax parsing — now `StrictInt`; the
`kuid_counters.next_serial` column held the last serial issued, not the
next one (caught by a first, wrong integrity check).

**Not done / open:** never run against real Paystack; the job runner has
never run under a process supervisor on an actual host; nothing pages a
human yet (needs a Sentry alert rule); ADM-04's screen was still unbuilt at
this point (see the 2026-09-22 entry above).

---

## 2026-09-21 — 2.2: media pipeline, verification service and screens
**Commit(s):** `b94dbed`, `aca04f4`, `5c550ae` (status)

**Built:** migration 0007 (`identity.media_files`, `verification_requests`
with the full state machine including `revoked` and `escalated`, resubmission
capped at three attempts; append-only `verification_decisions`).
`contexts/media/`: an object-store port (local disk, R2, or none), a slot →
upload → confirm-only-if-the-object-exists → re-encode-to-a-fresh-JPEG
pipeline that strips EXIF and applies orientation first, with bomb/format
guards and a 30-day document purge. `contexts/verification/service.py`: the
reviewer rules (never your own record) and the state machine; payment
success moves a request to `under_review` inside the same ledger
transaction. Web: `/verify` (upload, status, resubmit), `/review` (one case
at a time, approve/reject/skip), `/photo/[kuid]` and proxied review-media
routes so images never carry a bucket URL.

**Why (R2 signer):** hand-built rather than borrowed, and proved against
Amazon's own published SigV4 test vector before trusting it with real
uploads.

**Verified:** 565 passed / 0 skipped, twice. Mutations proved red: EXIF
kept, own-record review allowed, LGA scope dropped, a photo public before
approval, no escalation on the third rejection, no password required to
withdraw, direct `UPDATE` grants and the decisions trigger disabled.
`check:render` audited every state's screen and found two real contrast
bugs (ghost/filled buttons on documents in dark/light) — fixed in
`globals.css`.

**Not done / open:** never run against a real R2 bucket; the direct-to-
bucket presigned upload exists but no JavaScript path uses it yet; Pillow's
handling of HEIC untested (refused as "not JPEG/PNG/WebP" — iPhones may be
common); SMS on a decision is queued but nothing sends it without a
configured provider; the wireframe's cash route and coordinator-contact-on-
escalation are both absent.

---

## 2026-09-20 — 2.1 complete: payment webhook, checkout start, VER-03
**Commit(s):** `f7269e9`, `2497d1b` (status)

**Built:** `POST /v1/payments/webhook/paystack` (raw body → HMAC signature
check → parse → settle; a bad or missing signature changes nothing; always
200 after a valid signature, even for events it doesn't act on, so Paystack
never needlessly redelivers). `POST /v1/payments` (starts a charge; the
price is the server's, never the client's), `GET /v1/payments/quote`,
`GET /v1/payments/{reference}` (own payments only). `contexts/payments/
provider.py`: a port with `PaystackProvider` (https-only, an 8-second
deadline), `FakeProvider` (local only) and `NoProvider`. Web: `/pay` — start
and return in one address, works with JavaScript off, "Check again" is a
plain link.

**Verified:** 456 passed / 0 skipped; `check:render` passes for `/pay`'s
start view. Demonstrated locally by posting a self-signed `charge.success`
against the fake provider.

**Not done / open:** never run against the real Paystack sandbox (payload
shapes and whether `fees` is present are both unconfirmed); the confirmed/
failed/review return states were read as text but not contrast-audited; no
SMS on confirmation (that's 2.4).

---

## 2026-09-20 — 2.1 core: money tables and the settlement service
**Commit(s):** `16d02cf`, `ce41809` (pure rules), `8fd22b5` (status)

**Built:** `contexts/payments/rules.py` — strict parsing of a
`charge.success` event and `decide()`, which approves only on an *exact*
NGN amount match and freezes everything else, never approving on a
mismatch. `contexts/ledger/entries.py` — a settled payment is exactly two
lines, the gross credit and the provider-fee debit. Migration 0006 (the
`money` schema): `payments` (a guard trigger makes the agreed fields and a
final `success` immutable), insert-only `ledger_entries` and
`webhook_events`, both `REVOKE ALL` then `SELECT`/`INSERT` for `kaf_money`
only, plus the same append-only trigger the audit log uses so not even the
table owner can edit a row. **Decided: no wallets** — ledger lines belong to
the payment, not to a per-athlete balance. `contexts/payments/
settlement.py`: idempotent (`INSERT … ON CONFLICT DO NOTHING RETURNING` on
`webhook_events`, so a redelivery is a safe no-op), one transaction, one
commit.

**Verified:** 389 passed / 0 skipped on the local database, including five
concurrent copies of the same webhook × six rounds → exactly two ledger
rows every time. Mutations proved red: read-then-insert dedupe (a real
race), no dedupe at all, always-settle, granting `kaf_app` INSERT or
`kaf_money` UPDATE/DELETE, the owner trigger disabled.

---

## 2026-09-20 — Per-address rate limits, verified on a real database
**Commit(s):** `f8db7ff` (code), `4b68ca8` (fixes), `4a8c399`, `e0f605e`
(status)

**Built:** `contexts/access/ratelimit.py` — counted in Postgres, not Redis
(six endpoints at pilot volume don't justify a second service).
`Throttle("bucket")` on sign-in, send-code, confirm-code and register.
Migration 0005 (`ops.rate_counters`); the sweep of closed windows piggybacks
on the outbox worker's own loop.

**Why not Redis:** `settings.redis_url` is kept (marked unused) for the day
Paystack-webhook idempotency might want a cache, but a handful of counters
at pilot traffic is not that day.

**Verified 2026-09-20 against a private local PostgreSQL 15** (Supabase was
unreachable that day). Migrations 0001→0005 applied clean; all 9 rate-limit
tests passed three runs in a row; 360 passed / 0 skipped with the database
attached. Running it for real found three faults every non-database test
had missed: (1) the HTTP error handler dropped every response header, so a
429 lost its `Retry-After`; (2) the tests reused the same source IPs every
run, so a re-run inside the hour failed on its own first request; (3) the
local role-bootstrap SQL lacked `GRANT CREATE ON DATABASE` to the migration
role, so a fresh local database failed its first migration. All three
fixed the same day.

**Not done / open:** still worth repeating against Supabase once reachable
(noted repeatedly since — see the 2026-09-22 ADM entries above for what
"Supabase reachable" looked like weeks later).

---

## 2026-09-17 — A developer's agent, and two logs to keep
**Commit(s):** `f9a2bf6`, `0ebd747`

**Built:** `docs/TEAM-AGENT-BRIEF.md` — the brief for a separate agent
coaching a human developer through testing the build, including what
belongs in `docs/TEST-LOG.md` versus `docs/ISSUE-LOG.md`, and
`docs/DEVELOPER-PROGRESS.md` to track how that developer is coming along,
openly.

**Why this file exists too:** those three documents are about the
developer's own testing sessions. Nothing before this build-log entry
tracked the engineering work itself, chronologically, in one place — this
file (added 2026-09-22, backfilled from `git log` and `CLAUDE.md`'s Status
section) is that record.

---

## 2026-09-12 — OTP through a transactional outbox; Sentry, readiness, gated migrations
**Commit(s):** `962b3f7`, `bb578ac`, `f8db7ff` (see rate-limits entry above)

**Built:** ADR 0003 — SMS behind a provider port, Twilio first. Migration
0004: `ops.outbox` and `ops.otp_codes`. A code is queued in the same
transaction as the record it belongs to; `python -m kafriada.outbox.dispatch`
drains it. **The KUID is minted before the code is confirmed** (per the
AUT-02 wireframe), so a provider outage delays a confirmation, never a
registration. Web: `/register/confirm`, `/forgot`. Separately: Sentry wired
and scrubbed (inert without a DSN), `/readyz` (checks the database on every
role, 503 otherwise), `scripts/release.sh` and
`scripts/check_migration_safety.py` gating migrations, Dockerfiles for both
tiers.

**Not done / open at the time:** no Twilio credentials yet (`SMS_PROVIDER=
none` kept codes queued) — still true as of the 2026-09-22 email-pilot-
channel entry above, which is precisely why that channel exists.

---

## 2026-09-11 — Access: sessions, sign-in, scoped permissions, the permission matrix
**Commit(s):** `63c8782`; privacy fixes `8efdde4`, `659a608`; handoff `f733fb2`

**Built:** ADR 0002 — a revocable session cookie, not a third-party auth
service. `POST`/`DELETE /v1/sessions`, `GET /v1/me`, super_admin role grant/
revoke and end-all-sessions, LGA-scoped athlete search. `access.can()`
behind `Requires(permission, scope=)`. Migration 0003. Web: `/sign-in`,
`/me`, sign-out. `test_permission_matrix.py` — 12 principals × 12 routes,
two tenants, generated from the live app and the database's own role-
permission table rather than hand-written (this is the same test that
later verified ADM-03 and ADM-04 without any manual updates).

**Also fixed the same day:** a duplicate phone number no longer reveals
whose it is (detected only by the unique-index name, so still no second
KUID minted); registration copy stopped promising an SMS code before any
provider could send one.

---

## 2026-09-11 — Web: registration, the issued card, the public profile
**Commit(s):** `192f39e`, `b4172f2` (JS-off fix)

**Built:** the first three real screens — `/register`, the card handed over
immediately on success, and the public profile a QR code resolves to.
**Every screen works with JavaScript off**, by design, for the Opera Mini
proxy-browser reality of the pilot's actual users — caught for real the same
day, when registration turned out to be broken with JS off, and a render
check was added on the spot rather than trusted to stay working.

---

## 2026-09-10 — Registration API, public profile, signed QR; the database proved live
**Commit(s):** `3d6c176`, `d7c2e4e`, `ba69605`, `3c46b6b`

**Built:** the register/public-profile/QR API endpoints. The Supabase
database connected for the first time and its security guarantees —
role separation, the audit trigger, KUID immutability — were demonstrated
live (`scripts/demo_security.py`) rather than only asserted in a test.
Registration and the KUID mint were proved under real concurrent
contention: two hundred people registering in the same minute must never
collide on the counter row for longer than milliseconds.

---

## 2026-09-09 — Stage 0: the foundation
**Commit(s):** `6e450fd`, `6840572`

**Built:** the repository itself, the four-role database privilege
boundary (`kaf_app`, `kaf_money`, `kaf_reader`, `kaf_migrate` — the
architecture every later invariant leans on), the audit log's append-only
trigger, and the identity anchor: KUID structure, phone normalisation, the
Jigawa LGA table. Nothing runs yet without a database, but the shape
everything else was built inside was decided here.

---

*Entries above this line were reconstructed 2026-09-22 from `git log` and
`CLAUDE.md`'s Status section, to give this log a complete history from the
project's start rather than only from the day it was created. Going
forward, add a new entry here — newest at the top — at the end of each
build session, before or alongside the commit it describes.*
