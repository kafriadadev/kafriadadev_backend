# TODO — what is left to build

Everything still to do to reach a launchable pilot, in the order it should be
built. Scope and estimates come from `KAFRIADA-CORE-Build-Plan.pdf`; screen codes
(`VER-02`, `CRD-04`) from `KAFRIADA-CORE-Wireframes.pdf`. Written 2026-09-20.

**How to use this.** One item per session: build → verify → commit → stop. Tick
the box only when it is verified, and put the commit next to it. Never tick a
database item on the strength of tests that skipped.

| Tag | Meaning |
| --- | --- |
| `[DB]` | Needs a real database. Can be verified on the private local one (CLAUDE.md → Gotchas) while Supabase is down. |
| `[ACCT]` | Needs an outside account or key before it can be finished. Build against a fake first where possible. |
| `[USER]` | A decision or action only the project lead can make. |
| `[UI]` | A screen. Must work with JavaScript off, and pass `npm run check:render`. |

## Where we are

Stage 0 and Stage 1 are done. Stage 2 is mostly built on `main`: 2.1 (ledger and
payments), 2.2 (media and verification, including ADM-03) and the backend of 2.3
(the safety net, including ADM-04) work end to end against fakes — a local object
store and a fake payment provider. Nothing has touched real Paystack or real R2 yet.
2.2's ATH-02/ATH-04 gap is closed. Left: 2.3's notification generalisation, then all
of 2.4. **22 of 46 screens are built** (15 more are for launch, 9 wait for Slice 2;
updated 2026-09-23 — this line had gone stale). Three contexts are still empty:
`clubs`, `feed`, `transfers`.

The pilot exists to answer three numbers: **2,000 registrations, 5% paid
(100+ payments), 25+ clubs each with 15+ athletes**. Registration can be tested
today. The other two cannot until Stage 2 is built — that is what this list is for.

---

## 0. Only the project lead can unblock these

- [x] `[USER]` **Supabase project.** ~~Its hostnames do not resolve at all
  (2026-09-20)... likely paused after a week idle.~~ **That diagnosis was wrong.**
  Solved 2026-09-23: the project was healthy throughout. `db.<ref>.supabase.co` is
  **IPv6-only**, so it times out from a network without working IPv6. Fixed by
  pointing `api/.env` at the IPv4 pooler
  (`aws-1-eu-west-1.pooler.supabase.com:5432`, session mode, `<role>.<ref>`
  usernames — see CLAUDE.md Gotchas). All four roles verified, `/readyz` green,
  migration 0009 applied. No longer blocks the developer's database testing.
- [x] `[USER]` **Wallets: per-athlete, or ledger tied to payments only?** Decided
  2026-09-20: payments only, no wallets table. Gross and provider fee are
  platform facts, not an athlete's balance. Wallets can come when something needs
  a balance. (The Pilot Build Spec lists wallets; the Build Plan lists ledger lines.)
- [x] `[ACCT]` **Paystack test keys** — given 2026-09-23 and run against the real
  sandbox, which found a launch-blocking bug (`.invalid` placeholder emails are
  refused, so every athlete without an email could not pay; fixed) and closed the
  `fees` unknown (it is present, so `decide()` does not freeze; ₦2,500 costs 13750
  kobo and settles at 236250). Whole money path proven end to end in test mode.
  See CLAUDE.md Status. **Live keys still need business verification, which needs a
  current CAC registration** (1–3 weeks; nobody has checked it is current). Start
  that now: it is the longest pole and only bites at launch.
- [ ] `[ACCT]` **Twilio account + Nigerian sender ID** (3–10 days). Needed for real
  OTP and for the coordinator's SMS receipt, which is a Stage 2 exit criterion.
- [ ] `[ACCT]` **Cloudflare R2 bucket** for photographs and documents (2.2). Can be
  built against a fake store first.
- [ ] `[USER]` **Assisted-payment caps** — daily limit per coordinator, by count and
  by naira. No document sets the numbers.
- [ ] `[USER]` **Sign off the 27 LGA codes** with the CEO and state coordinator. They
  are printed into every KUID and can never change. Before any card is issued.
- [ ] `[USER]` **Which frontend copy is real?** `web/` here, or the separate
  `kafriadadev_frontend` repo (identical today, last updated 09-12, will drift).
- [ ] `[USER]` **How many days a week does KAFRIADA get?** The Build Plan's #1 risk.
  Multiply the estimates below by it and tell the CEO that date.
- [ ] `[USER]` Is the **installable PWA** (manifest + service worker, in the Pilot Build
  Spec) still wanted? Not built. And who does the **Hausa-friendly copy review**?

---

## 1. Stage 2 — money and verification

The one place not to compress. ~15 working days in the Build Plan. Every item
here is `[DB]`.

### 2.1 Ledger and payments (4–5 days)

Done: pure rules — `contexts/payments/rules.py`, `contexts/ledger/entries.py`;
migration 0006 and the settlement service (16d02cf); webhook route, checkout
start and VER-03 (f7269e9).

- [x] **Migration 0006 — the money tables** (16d02cf; applies and reverses cleanly). `payments` (our reference `KAF-{uuid}`,
  purpose, expected kobo, status incl. the new `frozen`, `paid_by`,
  `on_behalf_of`, `coordinator_id`), insert-only `ledger_entries`, and the
  webhook-idempotency table. `kaf_money` is granted UPDATE by default in the
  `money` schema, so **revoke UPDATE/DELETE/TRUNCATE explicitly** and add a trigger
  so even the owner cannot edit a ledger row (copy the `ops.audit_log` pattern).
  A unique `(payment_id, source)` makes "exactly two rows" structural. Run
  `scripts/check_migration_safety.py`.
- [x] **Settlement service** (16d02cf, `contexts/payments/settlement.py`), on `money_transaction()`. In ONE transaction:
  idempotency `INSERT … ON CONFLICT DO NOTHING RETURNING` (no row back = seen
  before: return 200, do nothing) → `decide()` → two ledger lines → status →
  audit row. On a mismatch: `frozen` + audit + an error-level alert, never approve.
- [x] **Webhook route** (f7269e9) `POST /v1/payments/webhook/paystack`: read the raw body
  first, verify the signature (`verify_paystack_signature` already exists), then
  parse. Ignore references that are not `KAF-…`. Always 200 after a valid
  signature. Register it as `Public` with its reason; update the route manifest
  and permission matrix.
- [x] **Payment intent + Paystack initialise** (f7269e9; adapter never run against
  the real sandbox — `[ACCT]` test keys) `POST /v1/payments` (athlete, own
  account only): create the `pending` row first, then call Paystack through a
  port with a fake for tests (same pattern as SMS, ADR 0003). Timeout on the call.
  Returns the redirect URL. `[ACCT]` test keys.
- [x] **Tests that must exist** (`tests/test_settlement.py`, `test_paystack_webhook.py`,
  `test_payments_api.py`; f7269e9): the same webhook five times *concurrently* → exactly
  two ledger rows; a ₦10 payment for a ₦2,500 badge → frozen + alert; bad
  signature → no state change; `abandoned` → `success` on a late payment;
  `kaf_app` cannot INSERT a ledger row; nobody, `kaf_money` and the owner
  included, can UPDATE or DELETE one.
- [x] `[UI]` **VER-03** payment (f7269e9, `/pay`) — leaving for Paystack, and coming
  back. Deliberately does NOT promise the wireframe's "we will send you an SMS":
  no confirmation SMS exists (see 2.4). Wireframe's "draft case stays open during
  an outage" waits for 2.2's verification cases.

### 2.2 Media and verification (4–5 days)

- [x] **Migration 0007** (b94dbed): `media_files`, `verification_requests` (state machine incl.
  `revoked` and `escalated`, resubmission capped at three, links to `payments`).
- [x] **Media pipeline** (b94dbed): object-store port (local + R2), the row becomes `uploaded`
  only after the object is confirmed to exist, a worker that re-encodes and **strips
  EXIF** (orientation applied first), decompression-bomb and format guards, a 30-day
  document purge, permission-checked reads. R2 adapter's SigV4 signer is proved
  against Amazon's published vector.
  **Still open, `[ACCT]`:** run against a real private R2 bucket (never done); the web
  tier uploads through the API (the wireframe's no-JS fallback) — the direct-to-bucket
  presigned PUT exists in the API (`upload_url`) but no JavaScript enhancement uses it
  yet, so today photos DO touch the API server; reads are streamed through the API
  after the permission check, not by presigned GET; the worker is started by hand
  (`python -m kafriada.contexts.media.worker --once`, scheduling is 2.3).
- [x] **Verification service** (b94dbed): payment success → `under_review` (in the ledger
  transaction, guarded so it can never fail it). The reviewer rule lives in the
  service: no seeing or deciding your own record. **Still open:** the "athlete of a
  club you administer" half — needs clubs (0008); `_conflict_with_club` is the marked
  place and is tested as absent. SMS on every decision is queued, but nothing sends
  it until an SMS provider is configured.
- [x] `[UI]` **VER-01** what it gets you, **VER-02** upload, **VER-04** under review,
  **VER-05** rejected — fix and resubmit (b94dbed, all at `/verify`). **Missing: the cash
  route** VER-01 says must be prominent — it needs CRD-04 (2.4), and a button that
  promises a coordinator flow that does not exist would be worse than none. The
  wireframe's "coordinator's contact details" on escalation are not shown either.
- [x] `[UI]` **CRD-02** review queue (b94dbed, `/review`): one case at a time, the two safe
  images, approve, reject with a reason, skip.
- [ ] `[UI]` **ADM-03** withdraw a verification (the `revoked` path). Built 2026-09-22
  (00565a6): `find_by_kuid()` + `GET /v1/admin/verification/by-kuid/{kuid}` is the
  lookup that was missing, `/admin/revoke` is the screen. **Verified 2026-09-22**:
  permission-matrix test passed against Supabase; the new lookup live-checked with a
  real super_admin token against a real approved request (`revocable: true`) and a
  draft one (`revocable: false`). `revoke()` itself is covered by
  `test_verification.py::TestApprovalAndWithdrawal`, which passed the same session —
  a live curl of the POST specifically was inconclusive (Supabase's link dropped
  mid-attempt; see Gotchas), not a failure. Tick this box once that one POST is
  confirmed live too.
- [x] `[UI]` **ATH-04** my payments. Done and live-verified against Supabase
  2026-09-22 (`a2db088`): `GET /v1/payments` (every payment, newest first),
  `/payments`.
- [x] `[UI]` **ATH-02** edit my details — gender, dominant side, secondary
  sport, years of experience, none of them in registration. Done 2026-09-23
  (migration 0009): `GET`/`PUT /v1/athletes/me` (behind `athlete.read_self`/
  `athlete.update_self`, both already seeded for the `athlete` role since
  migration 0001 — this was always the intended shape), `/details`.
  **Verified against a private local PostgreSQL 15** (Supabase was down all
  session — TCP-level, not just a query timeout): migration 0009 applies and
  reverses cleanly, `check_migration_safety.py` clean, a full live GET →
  PUT(valid) → PUT(invalid, refused with the right field) → GET loop, the
  permission-matrix and route-manifest tests, and `check:render` — including
  a signed-in audit of `/details` and `/payments` themselves — all pass.
  Repeat migration 0009 against Supabase once it's reachable. Public profile
  already shows the photo once verified.

### 2.3 Outbox, workers, safety net (3–4 days)

- [x] **Scheduling** (858feb0): `python -m kafriada.jobs` — one small process, no broker.
  "When did it last run" is in `ops.job_runs`, each recorded job takes a Postgres
  advisory lock, a failing job never stops the others, `--once` exits non-zero on a dirty
  run (for cron to page on). **Not deployed anywhere:** it needs a process supervisor
  on whichever host is chosen (`docs/deploy-runbook.md`); the standalone `outbox.dispatch`
  and `media.worker` still work and the runner subsumes them.
- [x] **Outbox for every notification**, not only SMS. Done 2026-09-23. A third event
  type, `notification.requested`, is addressed to a **person** rather than to a number
  or an inbox: the caller supplies both wordings, and the worker resolves how to reach
  them at send time (`outbox.service.prefers_email` is the single place the channel
  rule lives, shared with the OTP path so the two cannot drift). Two things this buys
  that a resolved address could not: a number changed after queueing is still the one
  used, and **a role with no grant on `ops.users` can still notify somebody** —
  settlement runs as `kaf_money`, which by design cannot read that table, so a payment
  could not otherwise send its own receipt. Wired up: all four verification decisions
  (approved / rejected / escalated / revoked), and a **payment receipt on settlement**,
  which did not exist at all before and is half of a Stage 2 exit criterion. Somebody
  unreachable fails once and is kept as evidence rather than retrying. Retention was
  already done (858feb0). Tests: `tests/test_notifications.py` (6, including the
  money-role privilege case); the settlement, OTP/outbox and verification suites all
  re-run clean.
- [x] **Reconciliation** (858feb0, every 10 minutes rather than hourly — a missed webhook
  is a customer waiting): asks Paystack's verify API and hands only a `success` to the
  same `settle_charge`, same idempotency key. Never reverses, refunds or cancels;
  mismatches freeze. **Never run against the real Paystack:** the verify adapter's
  request and response shapes are from memory.
- [x] **72-hour expiry** (858feb0) — only for payments Paystack has been asked about and
  has not said were paid; a payment it could not ask about is left alone.
- [x] **Nightly integrity check** (858feb0, `kafriada/integrity.py`, 02:00 Nigeria time):
  ledger shape and totals, KUID uniqueness and the counter (never behind, no gaps),
  verification consistency, media objects exist. Writes `ops.job_runs`, so "green" is a
  query. **"Pages someone" is only an error-level log plus a non-zero `--once` exit**;
  turning that into a real page needs a Sentry alert rule `[ACCT]`.
- [x] **Expired-session sweep** (858feb0): sessions dead for 30 days, hourly.
- [x] **`record_reversal`** (858feb0, `POST /v1/admin/payments/{reference}/reversal`) —
  super_admin, password re-entered, mandatory reason, once per payment, never more
  than was paid; makes no call to Paystack. Ledger line `source='reversal'` with
  `recorded_by` and `note` enforced by CHECK. (There are no wallets, so it is against
  the payment.)
- [x] `[UI]` **ADM-04** — the screen for the above. Built 2026-09-22: `GET
  /v1/admin/payments/{reference}` (a lookup the API didn't have — reversal only ever
  took a reference an admin already had from Paystack's dashboard, but nothing let
  them preview it first) plus `/admin/reversal`. Live-verified end to end against
  Supabase: looked up a settled payment, recorded a refund, confirmed
  `already_reversed`, a second attempt correctly refused (409). Suite re-run
  2026-09-23 once the link was fixed (see section 0): `test_settlement.py` and
  `test_route_manifest.py`, 156 tests, clean against Supabase through the pooler.

### 2.4 Assisted payment, clubs and the admin console (3–4 days)

- [x] **Coordinator pays on behalf** (`[UI]` **CRD-04**). Done and verified 2026-09-23.
  `POST /v1/lgas/{lga_id}/athletes/{kuid}/payments` (`payment.initiate_behalf`, scope
  `lga`), `/assist-pay`. The ledger lands on the athlete (`on_behalf_of`), never the
  coordinator; `coordinator_id` is tagged; two daily caps per coordinator (count and
  naira, both `[USER]` **placeholders** — 20/day and ₦50,000/day, chosen to be
  obviously survivable rather than obviously right — revisit from Wave 1's real
  figures, not before it); the **payment receipt already reaches the athlete's phone**
  at confirmation (built with the 2.3 notification work above, which already routes by
  `on_behalf_of`). One real bug found and fixed while building this: `mark_paid` had
  `AND pay.on_behalf_of IS NULL`, so an assisted payment would have settled into the
  ledger and moved *nobody's* verification to review — money taken for a review that
  never starts. **The scope check the route itself cannot make** is the one this
  needed most: `Requires(scope="lga")` only confirms the coordinator holds a grant on
  the `lga_id` in the *path* — it has no way to know the athlete named in the body is
  actually in that LGA, so a coordinator scoped to their own LGA could otherwise pay
  for any athlete in the country by naming one in a different LGA while keeping the
  path correct. Enforced in the service (`_athlete_in_lga`), proved with a dedicated
  test using a real cross-LGA coordinator. Verified: `tests/test_payments_on_behalf.py`
  (10, incl. both caps, the on_behalf_of routing, the receipt destination, and the
  scope case) plus the full suite, twice, clean against a real database; a live HTTP
  round trip against the running server confirmed both the route-level scope refusal
  (403, wrong LGA in the path) and the service-level one (404, wrong-LGA athlete via a
  correct path).
- [x] **Migration 0010 — clubs.** Done 2026-09-23. `organizations`, `teams`,
  `roster_members`; *at-most-one-open-membership* is
  `roster_members_one_active_per_athlete`, a partial unique index on
  `athlete_id` alone (global, not per-team — CLB-03's "accepting moves you"
  wording needs that, not the spec's per-team sketch). `career_events.club_id`
  now has its foreign key. `club.create` moved to the `athlete` role (every
  account holds it), matching CLB-01's "any signed-in user registers a club"
  — coordinators keep it too, for CLB-01's own manual-entry fallback.
  Verified against a live Supabase and a from-scratch local PostgreSQL 15
  (all 10 migrations, up/down/up, full suite clean on the local instance
  after two pre-existing, migration-unrelated flakes were traced and ruled
  out — see `docs/BUILD-LOG.md`). Schema only: no service, routes or screens
  yet.
- [ ] **Clubs** `[UI]` — done 2026-09-24/25: **CLB-01** register, **CLB-02** dashboard,
  **CLB-03** invite by exact KUID or phone, **ATH-05** my clubs and invitations (accept
  or decline), remove a player or withdraw an invitation, and club approval as an API
  (`POST /v1/admin/clubs/{id}/approve|suspend`, migration 0011, `club.approve` held by
  `super_admin`). An athlete is active in one club at a time: accepting a second
  invitation ends the first in the same transaction and writes `left_club` and
  `transferred` to their history. **CLB-04** verify the club ₦15,000 done 2026-09-25
  (migration 0012; see below). **Still to do:** **edit club details** (CLB-02), and a
  **screen for approval and for reviewing club documents** — until the admin console
  (ADM-02) and a first super_admin exist, both are API calls.
- [x] **CLB-04 verify the club** (2026-09-25, migration 0012). The athlete money path
  unchanged with a different price and beneficiary: `money.payments.org_id` (a CHECK ties
  it to `stage2_org`, and the guard trigger makes it immutable), `club_verification_requests`
  (one live per club) and append-only `club_verification_decisions`, a `club_document`
  media kind through the same re-encoding pipeline. Club admin: `/clubs/[id]/verify`,
  `GET|POST /v1/clubs/{id}/verification/...` (uploads, payment, resubmit). Reviewer (a
  super_admin, `club.approve`): `/v1/admin/club-verification/queue|{id}/document|approve|
  reject`, no screen. Approval sets the club to stage 2. **Not built:** revoking a
  verified club (the state exists, no route), the 30-day purge of club documents, a
  reviewer screen, and Slice 2's transfers (the wireframe's "accept transfers" benefit).
- [ ] **Coordinator console** `[UI]`: **CRD-01** dashboard, **CRD-03** find an athlete,
  **CRD-06** bulk QR card printing. **CRD-05** settlement is Metabase SQL against
  the read replica, not a built screen.
- [ ] **Admin console** `[UI]`: **ADM-01** dashboard, **ADM-02** users and roles (API
  exists, no screen), **ADM-06** audit log viewer.
- [ ] **A way to appoint the first super_admin** (today: a SQL insert).

### Stage 2 exit criteria — do not soften any of these

Stage 3 does not begin until every one is true:
1. A real ₦2,500 moves through Paystack **live** and lands in the ledger as two lines.
2. The same webhook replayed five times changes nothing.
3. A deliberately wrong amount is rejected and alerts.
4. The nightly integrity check is green.
5. A coordinator pays for someone else and that person's phone receives the receipt.

---

## 2. Stage 3 — launch readiness (~10 days)

- [ ] **Compliance.** Consent is already stored with a notice version and timestamp
  (`consent_version`). Remaining: export and anonymise as scripts that write audit
  rows; `[UI]` **ADM-07** data requests. Deletion means anonymisation — the privacy
  notice already says so.
- [ ] **Security sweep.** Full permission matrix across every role and route,
  including cross-tenant cases (extend `test_permission_matrix.py` as routes are
  added). Rate limits verified on the real database *(in progress — developer)*.
  TLS full-strict with authenticated origin pulls. Secret-rotation procedure
  written **and tested once**.
- [ ] **Restore drill**, eight points: the ledger balances in the restored
  database, R2 and the database still agree, and the wall-clock time is written
  down — that number is the RTO.
- [ ] **Dependency-failure drills:** kill Paystack, SMS and R2 in staging and check
  the user sees the right message.
- [ ] **Observability.** Sentry live (wired, inert without a DSN). Three dashboards
  — Money, Funnel, Health. The alert list split into *page someone* and *open a
  ticket*.
- [ ] **Performance.** Load test at 500 virtual users, mixed profile. Lighthouse in
  CI with the 150 KB first-load JS budget enforced (currently 102 KB). Every
  critical flow retested with JavaScript off.
- [ ] **Operations.** Coordinator runbook and training. Incident runbook.
  Reconciliation-mismatch runbook. **A printed receipt book and a posted complaint
  number in every LGA** — the cash controls software cannot provide.
- [ ] `[UI]` **ADM-05** LGA rollout control. The `is_live` and `rollout_wave` columns
  already exist on `ops.locations`; only Birnin Kudu is open.
- [ ] **Deploy pipeline (0.6 remainder — deferred by the project lead).** Staging
  Supabase project, a host (Fly / Render / Hetzner), a Sentry project, the
  `staging` GitHub Environment, and the images built once for real. The code is
  written; see `docs/deploy-runbook.md`.

### Launch, in the agreed order

- [ ] **Wave 0** — team plus 20 invited athletes, three days, real money in live
  mode, including **one deliberate refund and one deliberately duplicated webhook**.
  The restore drill runs here, before any member of the public is exposed.
- [ ] **Wave 1** — Birnin Kudu only, two weeks, with someone physically at a
  registration drive watching people use it.
- [ ] **Waves 2–4** — open behind `is_live`, gated on the five numeric criteria,
  no deploy needed to open or close one.

---

## 3. Slice 2 — after Birnin Kudu is live (~4–6 weeks)

Named and scheduled so it reads as sequenced, not cancelled. The natural point to
bring in more developers if the pilot's early figures justify it.

- [ ] **Transfers** — TRF-01 to TRF-05: the full state machine including
  `awaiting_buyer_onboarding`, and the completion transaction with all five effects
  atomic. Free — no money moves through the system. The recruitment gate is the
  growth engine, and needs clubs already on the platform.
- [ ] **News feed** — FED-01, FED-02, with state and LGA targeting, and the automatic
  transfer announcement through the outbox.
- [ ] **Scout search** — SCT-01, verified athletes only. **Public club page** — CLB-05.
- [ ] Coordinator console proper: settlement reporting, per-LGA statistics.
- [ ] Career history UI on the public profile (the table already exists).
- [ ] Data export automation, if requests pass about one a week.

---

## 4. Housekeeping backlog

- [ ] **ADR for the stack divergence.** The Pilot Build Spec says one Next.js repo with
  Prisma, Neon and Termii; what is built is FastAPI + SQLAlchemy behind a separate
  Next.js tier, Supabase and Twilio. The spec says changes need a version bump and a
  decision-log note; none was written.
- [ ] **Regenerate the Build Tracker and Handbook PDFs** — both are stale.
- [ ] **Fix `scripts/dev.sh`** — sourcing `api/.env` strips the quotes from
  `TRUSTED_HOSTS=["*"]` and the API will not boot.
- [ ] **Sync or retire the duplicate frontend repo** (see section 0).
- [ ] **Remove `settings.redis_url`** if it stays unused, along with the `redis`
  dependency.
- [ ] Guardian consent for under-18s is out of scope for the pilot (adults only). Keep
  it out; do not let it creep in.

---

## 5. Rules that do not bend

**Never cut** — these five are the difference between a pilot and a liability:
the reconciliation job, the nightly integrity check, the permission-matrix test,
the restore drill, and the burst test.

**If time slips, cut in this order:** 1. Slice 2 slips further. 2. Coordinator
tooling becomes pure Metabase SQL. 3. Club registration becomes an admin-entered
record instead of self-service. 4. Waves 3 and 4 slip, so the pilot runs in fewer
LGAs for longer. **Never take time from the money path** — take it from Stage 3's
polish or from Slice 2.

**Invariants** (CLAUDE.md): the audit log is append-only; only the money role
writes the ledger; KUIDs are immutable; no withdrawal or payout path may exist;
the public profile never shows phone, date of birth or documents; every screen
works with JavaScript off.

---

## 6. Screens — 46 in the wireframes

**Built (22, updated 2026-09-23 — this count had gone stale since 2.2):**
PUB-01 profile · PUB-02 home · PUB-03 look-up · PUB-04 privacy · PUB-05 error ·
AUT-01 register · AUT-02 confirm phone · AUT-03 ID ready · AUT-04 sign in ·
AUT-05 forgot password · ATH-01 my profile *(first cut)* · ATH-02 edit my
details · ATH-03 my QR card · ATH-04 my payments · VER-01 to VER-05 (all at
`/verify`, VER-03 at `/pay`) · CRD-02 review queue · ADM-03 withdraw a
verification · ADM-04 record a refund.

**To build for launch (15):** ATH-05 · CLB-01 to CLB-04 · CRD-01, CRD-03 to
CRD-06 · ADM-01, ADM-02, ADM-05 to ADM-07.

**Slice 2 (9):** SCT-01 · CLB-05 · TRF-01 to TRF-05 · FED-01, FED-02.

---

## Done so far

Stage 0 foundations (four roles, audit immutability, security primitives, CI) ·
identity anchor and KUID mint, burst-tested · registration, signed QR, public
profile · sessions, sign-in, scoped permissions and the permission matrix · OTP
through a transactional outbox · per-address rate limits, verified on a local
database 2026-09-20 (commit `4b68ca8`) · pure payment rules and ledger planning
(`ce41809`) · Sentry, readiness probe, gated migrations. Suite: 360 passed, 0
skipped with the database attached.
