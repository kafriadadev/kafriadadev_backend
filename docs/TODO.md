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

Stage 0 and Stage 1 are done. Stage 2 has started: the pure half of 2.1 (what a
Paystack event is worth, and what the ledger writes) is on `main` with 131 tests.
No money table, route or migration exists yet. **12 of 46 screens are built**
(37 are for launch, 9 wait for Slice 2). Five contexts are still empty:
`clubs`, `feed`, `media`, `transfers`, `verification`.

The pilot exists to answer three numbers: **2,000 registrations, 5% paid
(100+ payments), 25+ clubs each with 15+ athletes**. Registration can be tested
today. The other two cannot until Stage 2 is built — that is what this list is for.

---

## 0. Only the project lead can unblock these

- [ ] `[USER]` **Supabase project.** Its hostnames do not resolve at all (2026-09-20)
  while supabase.com does — likely paused after a week idle. Check the dashboard
  and restore it. Blocks the developer's database testing.
- [ ] `[USER]` **Wallets: per-athlete, or ledger tied to payments only?** Blocks the
  2.1 migration. Recommendation: payments only — gross and provider fee are
  platform facts, not an athlete's balance. Wallets can come when something needs
  a balance. (The Pilot Build Spec lists wallets; the Build Plan lists ledger lines.)
- [ ] `[ACCT]` **Paystack test keys** — needed to build initialise and the webhook
  against the sandbox. Live keys need business verification, which needs a
  **current CAC registration** (1–3 weeks; nobody has checked it is current).
  Start this now: it is the longest pole and only bites at launch.
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

Done: pure rules — `contexts/payments/rules.py`, `contexts/ledger/entries.py`.

- [ ] **Migration 0006 — the money tables.** `payments` (our reference `KAF-{uuid}`,
  purpose, expected kobo, status incl. the new `frozen`, `paid_by`,
  `on_behalf_of`, `coordinator_id`), insert-only `ledger_entries`, and the
  webhook-idempotency table. `kaf_money` is granted UPDATE by default in the
  `money` schema, so **revoke UPDATE/DELETE/TRUNCATE explicitly** and add a trigger
  so even the owner cannot edit a ledger row (copy the `ops.audit_log` pattern).
  A unique `(payment_id, source)` makes "exactly two rows" structural. Run
  `scripts/check_migration_safety.py`.
- [ ] **Settlement service**, on `money_transaction()`. In ONE transaction:
  idempotency `INSERT … ON CONFLICT DO NOTHING RETURNING` (no row back = seen
  before: return 200, do nothing) → `decide()` → two ledger lines → status →
  audit row. On a mismatch: `frozen` + audit + an error-level alert, never approve.
- [ ] **Webhook route** `POST /v1/payments/webhook/paystack`: read the raw body
  first, verify the signature (`verify_paystack_signature` already exists), then
  parse. Ignore references that are not `KAF-…`. Always 200 after a valid
  signature. Register it as `Public` with its reason; update the route manifest
  and permission matrix.
- [ ] **Payment intent + Paystack initialise** `POST /v1/payments` (athlete, own
  account only): create the `pending` row first, then call Paystack through a
  port with a fake for tests (same pattern as SMS, ADR 0003). Timeout on the call.
  Returns the redirect URL. `[ACCT]` test keys.
- [ ] **Tests that must exist:** the same webhook five times *concurrently* → exactly
  two ledger rows; a ₦10 payment for a ₦2,500 badge → frozen + alert; bad
  signature → no state change; `abandoned` → `success` on a late payment;
  `kaf_app` cannot INSERT a ledger row; nobody, `kaf_money` and the owner
  included, can UPDATE or DELETE one.
- [ ] `[UI]` **VER-03** payment — leaving for Paystack, and coming back.

### 2.2 Media and verification (4–5 days)

- [ ] **Migration 0007:** `media_files`, `verification_requests` (state machine incl.
  `revoked` and `escalated`, resubmission capped at three, links to `payments`).
- [ ] **Media pipeline:** private R2 bucket, presigned PUT, the asset row written
  only after the object is confirmed to exist, a worker that re-encodes and
  **strips EXIF**, and a permission-checked signed read. Photos and documents
  never touch the API server. `[ACCT]`
- [ ] **Verification service:** payment success → `under_review`. The **reviewer
  rule lives in the service, not the UI**: no approving your own record, or an
  athlete of a club you administer.
- [ ] `[UI]` **VER-01** what it gets you (cash route must be prominent), **VER-02**
  upload, **VER-04** under review, **VER-05** rejected — fix and resubmit.
- [ ] `[UI]` **CRD-02** review queue: deliberately plain — a list, a document
  viewer, approve, reject with a reason.
- [ ] `[UI]` **ADM-03** withdraw a verification (the `revoked` path).
- [ ] `[UI]` **ATH-02** edit my details (gender, dominant side, secondary sport,
  years of experience are in the spec but not in registration) and **ATH-04** my
  payments. Public profile already shows the photo once verified.

### 2.3 Outbox, workers, safety net (3–4 days)

- [ ] **Scheduling.** The SMS worker is started by hand today. Decide how jobs run
  (cron or a worker process) and make every job below use it.
- [ ] **Outbox for every notification**, not only SMS (`FOR UPDATE SKIP LOCKED`
  consumer exists; extend it). Add retention.
- [ ] **Hourly reconciliation** against Paystack's verify API, sharing the exact
  code path the webhook uses. It may only ever *confirm* a credit — never
  reverse, refund or cancel. Mismatches freeze for a human.
- [ ] **72-hour expiry** — only for payments with no successful charge.
- [ ] **Nightly integrity check:** every ledger balances, every athlete has exactly
  one KUID, no KUID appears twice, every media row points at a real object. Pages
  someone on failure.
- [ ] **Expired-session sweep** (listed as not built).
- [ ] `wallet.record_reversal()` — super_admin, password re-entered, mandatory
  reason; records a refund made by hand in Paystack. **No endpoint moves money.**
  `[UI]` **ADM-04**.

### 2.4 Assisted payment, clubs and the admin console (3–4 days)

- [ ] **Coordinator pays on behalf** (`[UI]` **CRD-04**): the ledger lands on the athlete,
  `coordinator_id` is tagged on the payment, daily caps by count and by naira
  (`[USER]` numbers), and an **SMS receipt to the athlete's phone** at confirmation.
- [ ] **Migration 0008 — clubs:** organizations, teams, roster members, with the
  *at-most-one-open-membership* rule as a **partial unique index** — the database
  enforces it, not the code.
- [ ] **Clubs** `[UI]`: **CLB-01** register, **CLB-02** dashboard (scope is the
  security story), **CLB-03** invite by KUID, **CLB-04** verify the club ₦15,000,
  **ATH-05** my clubs and invitations. Club approval by an admin.
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

**Built (12):** PUB-01 profile · PUB-02 home · PUB-03 look-up · PUB-04 privacy ·
PUB-05 error · AUT-01 register · AUT-02 confirm phone · AUT-03 ID ready · AUT-04
sign in · AUT-05 forgot password · ATH-01 my profile *(first cut)* · ATH-03 my QR
card.

**To build for launch (25):** ATH-02, ATH-04, ATH-05 · VER-01 to VER-05 · CLB-01 to
CLB-04 · CRD-01 to CRD-06 · ADM-01 to ADM-07.

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
