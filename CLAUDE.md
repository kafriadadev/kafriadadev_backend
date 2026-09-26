# KAFRIADA CORE — working notes for Claude

Permanent sports ID for athletes (Jigawa State pilot, Birnin Kudu first). Register
free → permanent KUID + signed QR card → anyone can scan and verify. Paid Stage-2
verification (₦2,500) adds a photo. Full context: `docs/README.md` and the PDFs in `docs/`.
**What is left to build, in order: `docs/TODO.md`.** **Every piece of engineering
work, from the start of the project: `docs/BUILD-LOG.md`.** Add an entry there —
newest at the top, its own template inside the file — at the end of every build
session, alongside its commit(s). This file's Status section is a summary
distilled from it; the log is the record.

A developer is testing what's built, coached by their own agent. That agent's
brief is `docs/TEAM-AGENT-BRIEF.md`; test runs land in `docs/TEST-LOG.md`,
anything that took more than one attempt lands in `docs/ISSUE-LOG.md`, and how
the developer is coming along lands in `docs/DEVELOPER-PROGRESS.md`. Check
those before assuming something untested actually works.

## Working style (user preference)
Be terse. Prefer text checks over reading screenshots. One milestone per session:
build → verify → commit → stop. Don't expand scope without asking.

**All copy — UI text, hints, error messages, docs, commit messages — must read as
professional, plainly-worded product writing, never as AI-generated filler.** No
throat-clearing, no "Note: X is a pilot stand-in for Y, remove once Z" asides in
user-facing strings, no hedging or over-explaining in a hint. State the fact the
reader needs, once, and stop. (2026-09-22: flagged on the register form's Email
hint — removed.)

## Layout
- `api/` — FastAPI domain tier, sync SQLAlchemy (see `docs/decisions/0001`). The ONLY
  holder of DB credentials. Code in `api/src/kafriada/contexts/<context>/`.
  Migrations in `api/src/kafriada/migrations/versions/`. Tests in `api/tests/`.
- `web/` — Next.js 15 presentation tier. Server-rendered, **every screen must work
  with JavaScript off** (Opera Mini). Talks only to the API, server-side (`web/src/lib/api.ts`).
- `infra/` role bootstrap SQL · `scripts/` dev/demo/CI helpers · `docs/` specs as PDF.

## Run and check
```
bash scripts/dev.sh                         # API 127.0.0.1:8010 + web localhost:3000
cd api && .venv/Scripts/python.exe -m pytest
cd web && npm run typecheck && npm run build
cd web && npm run check:render              # needs both tiers up; see below
python scripts/demo_security.py             # live demo of what the DB refuses to do
cd api && .venv/Scripts/python.exe -m kafriada.outbox.dispatch --once   # send queued SMS
cd api && .venv/Scripts/python.exe -m kafriada.contexts.media.worker --once   # re-encode uploads, purge old documents
cd api && .venv/Scripts/python.exe -m kafriada.jobs --once    # every background job now (reconcile, expire, integrity...); exits 1 if any was not clean
python scripts/check_migration_safety.py    # refuses data loss in an upgrade()
bash scripts/release.sh plan staging        # pending migrations + the SQL
bash scripts/release.sh migrate staging     # apply, after typing the name
bash scripts/release.sh smoke http://127.0.0.1:8010
```
Probes: `/healthz` (alive) and `/readyz` (can reach the database on each role;
503 otherwise, and which role failed goes to the log, not the response).
`check:render` drives the installed Edge (playwright-core, no download): WCAG
contrast of every text element, overflow, split IDs at 360px light/dark and 320px,
plus JS-off registration and sign-in round trips that write nothing. Run it after
any UI change. With `SIGNIN_PHONE`/`SIGNIN_PASSWORD` set it also signs in, audits
`/me` and signs out — register a throwaway athlete for it; never commit its password.

DB tests skip unless `DATABASE_URL_APP` is in the environment:
`export DATABASE_URL_APP="$(grep '^DATABASE_URL_APP=' .env | cut -d= -f2-)"`.
Migrations: same with `DATABASE_URL_MIGRATE`, then `python -m alembic upgrade head`.

## Gotchas (all hit for real)
- **Port 8000 belongs to another project** (a Django app). KAFRIADA API uses 8010.
- **Stop `next start` before `npm run build`**, or the server serves dead CSS chunks.
- Supabase (Frankfurt, IPv6) connects in ~8s cold. `api/.env` has
  `DB_CONNECT_TIMEOUT_SECONDS=30`. `.env` is gitignored; never commit it.
- Edge headless ignores `--window-size` for layout — narrow screenshots are cropped
  wide renders. Use `check:render` (real mobile viewport) instead.
- `Referrer-Policy` must stay `same-origin`: `no-referrer` makes no-JS form POSTs
  send `Origin: null` and server actions 500.
- CSS: anything inside `.doc`/`.notice`/`.mrz` uses `--plate-*` tokens (the document
  never inverts in dark mode). Inline `var(--muted)` etc. inside a document is a bug.
- `C:\Users\HP` itself is a git repo (another project). Always work inside `KAFRIADA/`.
- **`scripts/dev.sh` is broken**: sourcing `api/.env` strips the quotes from
  `TRUSTED_HOSTS=["*"]` and the API will not boot. Start the tiers directly:
  `api/.venv/Scripts/python.exe -m uvicorn kafriada.main:app --host 127.0.0.1 --port 8010`
  (from `api/`) and `node node_modules/next/dist/bin/next start -p 3000` (from `web/`).
- **SOLVED 2026-09-23 — use the IPv4 pooler, not the direct endpoint.**
  `db.<ref>.supabase.co` is **IPv6-only** (Supabase ran out of IPv4 addresses), so on
  a network without working IPv6 the name resolves and the TCP connect then hangs
  until it times out. The dashboard says "Healthy" the whole time and is *right* —
  their side is fine; this machine simply cannot route to that address. Do not read a
  timeout here as a paused project.
  **The fix, no paid add-on needed:** Supavisor's pooler is IPv4-reachable.
      host: aws-1-eu-west-1.pooler.supabase.com   (aws-0 is a different tenant
                                                   cluster — it answers, then says
                                                   "ENOTFOUND tenant/user")
      port: 5432   <- SESSION mode. Use this one.
      user: <role>.<project-ref>   e.g. kaf_app.slwlefnfdsjfeimyjhag
  Everything else (password, `postgres` db, `sslmode=require`) is unchanged, and all
  four roles keep their own identity, so the privilege boundary is untouched.
  `api/.env` now uses this; the old direct URLs are kept commented above each one.
  **Port 6543 (transaction mode) would break this app**: `kafriada.jobs` takes
  *session-level* advisory locks and psycopg auto-prepares statements — neither
  survives transaction pooling. Session mode behaves like a direct connection, so no
  application code changes were needed.
  *(Earlier note, 2026-09-20, now explained: the host "not resolving" was this same
  IPv6 path failing, not a paused project.)*
- **No reachable database? Build a private one.** Needs only the installed
  PostgreSQL binaries, no Docker, no password for any existing database:
  `initdb -D <tmp>/pgdata -U kafriada_admin -A scram-sha-256 --pwfile=<file> -E UTF8`,
  `pg_ctl -D <tmp>/pgdata -o "-p 54329 -c listen_addresses=127.0.0.1" -l pg.log start`,
  `createdb -p 54329 kafriada`, `psql -f infra/bootstrap-roles.sql` (with the four
  `-v *_password=` variables), then `alembic upgrade head`, and export **all four**
  `DATABASE_URL_*` (APP, MONEY, READER, MIGRATE) at `127.0.0.1:54329` — leaving
  READER unset lets `api/.env` supply the dead host and `/readyz` returns 503, which
  fails the permission-matrix test. Do not run `scripts/bootstrap-local-db.sh`
  as-is: it hard-codes port 5432. `pg_ctl -w start` can hang a wrapping shell; the
  server is up regardless (check `netstat` for the port).
- The link to Supabase drops intermittently (DNS `getaddrinfo failed`, connection
  timeouts). Retry before debugging — but if it is timing out *consistently*, check
  which endpoint is configured first: the direct one is IPv6-only, see above. The
  200-registration burst test times out at default load on this link; use
  `BURST_WORKERS=6 BURST_SIZE=100`.
- **Two different failures look identical and are not.** A pooled-connection
  exhaustion (too many of: the API, the outbox dispatcher, a live curl session, and a
  heavy DB test file, all holding connections at once) and an unreachable link both
  surface as `psycopg.errors.ConnectionTimeout`. Tell them apart by stopping
  everything and trying **one** bare connection: if that still times out, it is the
  link, not contention. Both were hit in one session on 2026-09-22.
- Audit metadata keys containing `session`, `token`, `password` etc. are stored as
  `[redacted]` — name keys accordingly (e.g. `logins_ended`).
- A wrong one-time code must be counted in its **own** committed transaction: the
  refusal rolls back the caller's transaction, and with it the attempt counter,
  which silently turns five guesses into unlimited (caught by a test, `_spend_code`).
- FastAPI ≥0.141 nests included routers; walk routes with `api.security.api_routes(app)`,
  not `app.routes`.
- `web/next.config.ts` sets `output: "standalone"` for the container image. `next
  start` still serves the same build, so local flow is unchanged.
- **Tests that assert on logs:** `structlog.testing.capture_logs` silently sees nothing once
  `create_app()` has run in the process (loggers are cached on first use). Use
  `tests/_payment_helpers.record_logs`, which swaps the module's `log`. And build the
  app once before spawning threads: `create_app()` racing itself breaks sentry's
  lazy imports.
- **`tests/test_codes_and_outbox.py::test_a_message_is_sent_once…` can fail once** when
  the local `ops.outbox` holds dozens of rows in long retry backoff (an earlier run of the
  retry test pushes every due row 30 s–30 min out). It passed twice in a row on the next
  runs. The verification tests queue a few SMS per run and add to that pile.
- **Never `git stash` in this repo mid-session** — untracked new files are not stashed and
  the round trip is pointless; commit instead.
- The API must be restarted to pick up new routes — it runs without `--reload`.
- Disk C: runs near full; `npm cache clean --force` frees several GB.
- **A live `outbox.dispatch` running for manual testing races DB tests that read
  outbox bodies.** `sms_to()`/similar helpers read `payload->>'body'`, but a
  delivered row is scrubbed to `{to, purpose, provider, provider_message_id,
  scrubbed:true}` — no `body`. If a dispatcher you started earlier is still
  running against the same database, it can drain and scrub a test's row before
  the test reads it, failing on `body == 'None'`/`assert False` with no code
  bug behind it. Stop the dispatcher before running `test_verification.py` or
  anything else that inspects outbox content; restart it after.
- **`OTP_CHANNEL=email` (or any interim setting) left in `api/.env` leaks into
  every DB test**, since `create_app()`/`Settings()` load `.env` normally —
  unlike `test_settings_refuses_insecure_config.py`'s `build()`, which passes
  `_env_file=None` for exactly this reason. With it set, every test that
  registers an athlete without an email fails at `identity.register()`. Export
  the real value as an env var when running the suite (env vars win over
  `.env`): `OTP_CHANNEL=sms` — or unset the pilot lines in `.env` first.
- **`money_transaction()` (the `kaf_money` role) cannot read `ops.users` or
  `identity.athletes`** — it only has grants inside the `money` schema (plus
  `ops.audit_log`). A lookup that joins payer/athlete names onto a payment
  needs the ordinary `transaction()` (`kaf_app`), which already has SELECT on
  `money.payments` and `money.ledger_entries` (0006's append-only grants).
  `money_transaction()` is for the *write* in `record_reversal`, not a read.
- **A free-tier Supabase project's connection limit is easy to exhaust** when
  the API, the outbox dispatcher, a live curl session and a heavy DB test file
  (`test_permission_matrix.py`, `test_verification.py`) all hold pooled
  connections at once — surfaces as `psycopg.errors.ConnectionTimeout` on an
  otherwise-correct request. Not a bug; stop what you can before diagnosing.

## Invariants — do not weaken
- Audit log is append-only (grants + trigger). The app role cannot write the ledger;
  only the money role can. KUIDs are immutable (DB trigger). No withdrawal/payout
  path may exist (`scripts/check-no-payout-path.sh` fails CI).
- Public profile never shows phone, date of birth or documents.
- LGA codes in `contexts/geography/jigawa.py` are printed into every KUID —
  **need CEO/state-coordinator sign-off before the first card is issued.**

## Status (as of 2026-09-12)
- Stage 0 foundations — done. 0.6 pipeline: everything except the staging host
  itself. Sentry wired and scrubbed (`observability.py`, inert without a DSN),
  `/readyz`, gated migrations (`scripts/release.sh` + `check_migration_safety.py`),
  `deploy-staging.yml` waiting on the `staging` GitHub Environment, CI now builds
  the web tier and runs the access/OTP DB tests, Dockerfiles for both tiers.
  **Not done:** no staging Supabase project, no host chosen (see
  `docs/deploy-runbook.md`), no Sentry project, no GitHub Environment configured.
  The images have never been built — this machine has no Docker.
- 1.1 identity anchor — done. Live Supabase DB, security guarantees proved.
- 1.3 KUID minting — done, burst-tested under real contention.
- 1.4 partial — API: register, public profile, signed QR. Web: landing, register,
  card, profile, find, privacy. All verified by `check:render`.
- Phone→identity leak — fixed. A duplicate phone gets a field error on `phone`
  (no name, KUID or card); detected by the `users_phone_unique` index name, so
  still no second KUID. `?returning` path removed. Test:
  `api/tests/test_duplicate_phone_reveals_nothing.py`.
- 1.4 OTP — done (ADR 0003: SMS behind a provider port, Twilio first). Codes are
  queued in `ops.outbox` inside the same transaction as the record; a worker
  (`python -m kafriada.outbox.dispatch`) drains it. **The KUID is minted before
  the code is confirmed** (wireframe AUT-02), so a provider outage delays a
  confirmation, never a registration. Web: `/register/confirm` (AUT-02),
  `/forgot` (AUT-05). `SMS_PROVIDER=none` keeps messages queued; `console`
  prints them (local only); `twilio` sends. Migration 0004.
- 1.2 access — done (ADR 0002: our own revocable session cookie). API:
  `POST/DELETE /v1/sessions`, `GET /v1/me`, super_admin role grant/revoke and
  end-all-sessions under `/v1/admin` (password re-entered for grant/revoke),
  `GET /v1/lgas/{lga_id}/athletes` (LGA-scoped). `access.can()` behind
  `Requires(perm, scope=)`; `SignedIn()` for own-account routes. Migration 0003
  (applied to dev DB). Web: `/sign-in`, `/me`, sign-out. Tests: route manifest,
  `test_access_sessions.py`, `test_permission_matrix.py` (12 principals × 12 routes,
  two tenants).
- Per-address rate limits — code done 2026-09-12 (commit f8db7ff). Counted in
  Postgres, not Redis (`contexts/access/ratelimit.py` — six endpoints at pilot
  volume do not justify running a second service; `settings.redis_url` is now
  marked unused). `Throttle("bucket")` on sign-in, send-code, confirm-code,
  register. Migration 0005 (`ops.rate_counters`). Sweep of closed windows is
  piggybacked on the outbox worker's loop (hourly).
  **VERIFIED 2026-09-20 against a private local PostgreSQL 15** (not Supabase, which
  is unreachable — see Gotchas): migrations 0001→0005 apply, all 9 rate-limit tests
  pass three runs in a row, and the whole suite is 360 passed / 0 skipped with the
  database attached. Running it for real found three faults that every non-database
  test had missed: (1) `main.py`'s HTTP error handler dropped every response header,
  so a 429 lost its `Retry-After`; (2) the tests reused the same IPs every run, so a
  re-run inside the hour failed on its first request (now random 2001:db8::/32
  addresses); (3) the local `bootstrap-roles.sql` lacked `GRANT CREATE ON DATABASE`
  to `kaf_migrate`, so a local database failed its first migration. Still worth
  repeating against Supabase once it is reachable.
- 2.1 payments — rules, tables and settlement done 2026-09-20 (16d02cf). No route,
  no Paystack initialise call, no screen yet. `contexts/payments/rules.py`: strict
  `charge.success` parsing, `decide()` (NGN + success + amount *exactly* equal,
  else FREEZE — never approve), reference `KAF-{uuid4}`, status machine.
  `contexts/ledger/entries.py`: a settled payment is exactly two lines, gross
  credit + provider-fee debit. **Migration 0006** (`money` schema): `payments`
  (guard trigger: agreed fields immutable, `success` final), insert-only
  `ledger_entries` (unique `(payment_id, source)`) and insert-only `webhook_events`
  — both `REVOKE ALL` then SELECT/INSERT for `kaf_money`, plus the `ops.deny_mutation`
  trigger so not even the owner can edit a row. **No wallets** (decided: ledger
  lines belong to the payment). `contexts/payments/settlement.py: settle_charge()`:
  lookup → atomic `INSERT … ON CONFLICT DO NOTHING RETURNING` on `webhook_events`
  → `FOR UPDATE` → `decide()` → two lines + status + audit, one commit; a mismatch
  is `frozen` + audit + an error log emitted *after* the commit. Unknown `KAF-`
  reference writes nothing (a redelivery can still settle); a non-`KAF-` one is
  ignored. `tests/test_settlement.py`: 29 DB tests, incl. five concurrent copies × 6
  rounds → two rows. Mutations proved red: read-then-insert dedupe, no dedupe,
  always-settle, `GRANT INSERT` to `kaf_app`, `GRANT UPDATE/DELETE` to `kaf_money`,
  the owner trigger disabled. Full suite 389 passed / 0 skipped on the local DB.
  Choices to confirm: missing `fees` from Paystack → FREEZE (check a real test-mode
  payload); new `frozen` status; followed the Build Plan ("provider fee") over
  Pilot Build Spec §6. Idempotency key is `charge.success:<reference>`, not
  Paystack's transaction id (`ChargeEvent` does not carry it). An illegal
  transition (e.g. a frozen payment receiving a new settle) raises and rolls back
  rather than returning — the route must decide what Paystack is told.
- 2.1 payments — webhook route, checkout start and VER-03 done 2026-09-20 (f7269e9).
  `api/v1/payments.py`: `POST /v1/payments/webhook/paystack` (raw body → HMAC →
  parse → `settle_charge`; bad/missing signature or no key → 400 and NOTHING
  changes; 413 over 64 KB; 200 for unhandled events, unreadable bodies, non-`KAF-`
  and unknown references, illegal transitions — each logged at error where a human
  is needed; a database failure is left as 5xx so Paystack redelivers and the
  rolled-back payment can settle). `POST /v1/payments` (`payment.initiate_self`,
  throttled `start_payment`; body only `{purpose:"stage2_athlete"}` — the price is
  ours), `GET /v1/payments/quote`, `GET /v1/payments/{reference}` (own only; else
  404; states `checking|confirmed|failed|review` — a frozen payment reads as
  `review`). `contexts/payments/service.py`: pending row committed BEFORE the
  provider call; provider failure → `failed` + audit + 503 with a calm message
  (the error handler now passes a 503's message through — every other 5xx is still
  generic); paid or frozen athlete → 409; `none` provider → 503 and no row.
  `contexts/payments/provider.py`: port + `PaystackProvider` (httpx, 8s deadline,
  https-only address) + `FakeProvider` + `NoProvider`; **`PAYMENT_PROVIDER=none|fake|paystack`**
  (fake refused outside local; production must be `paystack`). Web: `/pay`
  (start + return in one address, JS off, "Check again" is a link), `lib/money.ts`,
  a "Get verified" link on `/me`. Suite: 456 passed / 0 skipped; `check:render`
  passes for `/pay` (start view). Local demo: run the API with
  `PAYMENT_PROVIDER=fake PAYSTACK_SECRET_KEY=sk_test_…` and post a signed
  `charge.success` yourself (HMAC-SHA512 of the raw body, header `x-paystack-signature`).
  **Not verified:** the Paystack adapter against the real sandbox (payload shapes,
  `fees` present?, whether Paystack accepts the `.invalid` placeholder email for an
  athlete with no email); the return-state screens (confirmed/failed/review) were
  read as text but not contrast-audited; no SMS on confirmation (2.4).
- 2.2 media and verification — done 2026-09-21 (b94dbed). **Migration 0007**:
  `identity.media_files`, `verification_requests` (one live request per athlete as a
  partial unique index; attempt 1..3; no review without both files and a payment, by
  CHECK), append-only `verification_decisions`. `contexts/media/`: `store.py` (port:
  `LocalStore`, `R2Store` with a hand-built SigV4 presigner proved against Amazon's
  vector, `NoStore`), `service.py` (slot → relay/direct PUT → confirm-only-if-the-object-
  exists → re-encode to a fresh JPEG with no EXIF, orientation applied; bomb/format
  guards; 30-day document purge), `worker.py`. `contexts/verification/service.py`: the
  state machine and the reviewer rules; `payments.settlement` calls `mark_paid` inside
  the ledger transaction. API `api/v1/verification.py`: athlete (`/v1/verification`,
  `/uploads`, `.../content` relay, `.../confirm`, `/resubmit`), reviewer
  (`/v1/lgas/{lga}/verification/queue|{id}|{id}/media/{kind}|approve|reject`, scope =
  LGA), `POST /v1/admin/verification/{id}/revoke` (reason + password), public
  `GET /v1/public/athletes/{kuid}/photo` (approved only). Payment start now REQUIRES a
  draft with both files ready. Settings: `MEDIA_STORE=none|local|r2` (local refused
  outside local, production must be r2) + `R2_*`. Web: `/verify`, `/review`,
  `/photo/[kuid]`, `/review-media/...` proxies (images never have a bucket URL);
  server-action body limit raised to 12mb. Suite: 565 passed / 0 skipped, twice.
  Mutations proved red: EXIF kept, own record allowed, LGA scope dropped, photo public
  before approval, no escalation, no password on withdraw, granted UPDATE + trigger off
  on decisions. `check:render` audits every state's screen via
  `EXTRA_SESSIONS='[{"token":"…","paths":["/verify"]}]'` and found two real contrast bugs
  (ghost/filled buttons on documents in dark/light), fixed in `globals.css`.
  **Not verified:** real R2 (never run); the direct-to-bucket upload (no JS uses it);
  Pillow's behaviour on HEIC (refused as "not JPEG/PNG/WebP" — iPhones may be common);
  SMS delivery of decisions (needs Twilio); the wireframe's coordinator contact on
  escalation and the cash route are absent (see docs/TODO.md).
- 2.3 the safety net — backend done 2026-09-21 (858feb0). **Migration 0008**:
  `ops.job_runs` (insert-only proof of every run), `GRANT DELETE ON ops.outbox`, ledger
  `reversal` source + `note`/`recorded_by` (CHECK: a reversal is a positive debit with an
  author and a reason). **`kafriada.jobs`**: `python -m kafriada.jobs [--once] [--only a,b]`
  runs outbox drain (5s), media (10s), reconcile (10min), expire, sessions, rate counters,
  documents (hourly), outbox retention (03:00), integrity (02:00 Nigeria time); last-run
  is read from `ops.job_runs`, each recorded job holds a Postgres advisory lock (session
  level, committed straight away — the engine kills idle-in-transaction after 30s), a
  failure is recorded and logged and never stops the others. `contexts/payments/reconcile.py`:
  `reconcile()` asks `provider.verify()` (new on the port; `PaystackProvider` calls
  `GET /transaction/verify/{ref}`, parsed by the webhook's own strict reader) and calls
  `settle_charge(event, source="reconciliation")` ONLY for `status == "success"`;
  `expire_stale()` asks first, expires only `pending` older than 72h that Paystack does
  not say was paid, leaves unreachable ones alone. `integrity.py`: findings, not verdicts;
  tests corrupt data inside rolled-back sessions via `integrity.reading_from(session)`
  (the ledger is append-only, so committed corruption could never be cleaned up).
  `contexts/ledger/reversal.py`: RECORD a refund made in the Paystack dashboard.
  Sweeps: `access.sweep_sessions()`, `outbox.prune_delivered()`. Suite: 681 passed / 0
  skipped. Mutations proved red: verify status ignored, expiry without asking, other-
  reference answer accepted, integrity checks removed, no lock, no password, no cap,
  sweeps too greedy. Found and fixed on the way: `amount_kobo` accepted `"100000"` and
  `true` (pydantic lax) — now `StrictInt`; the `kuid_counters.next_serial` column holds
  the LAST serial issued, not the next (a wrong first integrity check flagged it).
  **Not verified:** real Paystack verify; the runner has never run under a supervisor on
  a host; nothing pages anyone (needs a Sentry alert rule); ADM-04 screen not built.
  Next: 2.4 (assisted cash payment, clubs = migration 0009, the admin console, the first
  super_admin) — or 2.3's remaining screen.
- **Not built:** expired-session sweep, outbox retention/scheduling (0.6 — the
  worker is started by hand today), admin UI (ADM-02 is API only), a way to
  appoint the first super_admin (today: SQL insert into `ops.user_roles`).
  `docs/KAFRIADA-CORE-Build-Tracker.pdf` predates most of this — update it.
- **Email delivery (Resend) and an OTP pilot channel — done 2026-09-22**
  (356c78b). Twilio still has no Nigerian sender ID (see "Outside the code"),
  so `OTP_CHANNEL=sms|email` is a stand-in: with `email` set and an email on
  file, phone-verification and password-reset codes go by email instead —
  refused in production. `outbox/email_providers.py` (Resend adapter, same
  transient/permanent split as Twilio's), `contexts/access/email_templates.py`
  (branded HTML). Registration takes an optional email, required only under
  the pilot channel. **Not built:** email as a trigger for anything besides
  OTP (verification decisions, payment receipts still only queue SMS).
- **A branded Flash component and a live resend countdown — done 2026-09-22**
  (ee812a2). `web/src/components/Flash.tsx` replaces the copy-pasted
  `.notice` divs on register, sign-in, forgot and confirm; `ResendCountdown.tsx`
  ticks the "ask again" wait down live and re-enables the button at zero, both
  inert without JavaScript. Caught and fixed a real bug on the way (the
  warn/bad/good icon was invisible — `currentColor` resolving to itself).
- **A downloadable wallet card, PNG and PDF — done 2026-09-22** (30900a9).
  `contexts/identity/card.py` renders it server-side with Pillow (already a
  dependency) — the same information as the on-screen card, a faint repeating
  ring instead of illustrated icons, three font families vendored into
  `assets/fonts/` (OFL). `GET /v1/public/athletes/{kuid}/card.png|pdf`,
  proxied from the web tier the same way the QR code is.
- **ADM-03, withdraw a verification — done and verified 2026-09-22** (00565a6).
  `find_by_kuid()` + `GET /v1/admin/verification/by-kuid/{kuid}` is the
  missing piece the API-only `revoke` route needed; `/admin/revoke` is the
  screen. Permission-matrix test passed against Supabase; the lookup itself
  live-checked with a real super_admin token against a real approved request
  and a draft one, correct in both. `revoke()` is covered by
  `test_verification.py::TestApprovalAndWithdrawal` (passed). A live curl of
  the revoke POST specifically was inconclusive — the Supabase link dropped
  mid-attempt (see Gotchas) — not a failure.
- **ADM-04, record a refund — built and verified 2026-09-22** (`f287008`).
  `GET /v1/admin/payments/{reference}` is a lookup the API never had (the
  reversal route only ever took a reference from Paystack's own dashboard,
  with nothing to preview it against first); `/admin/reversal` is the screen.
  Full live loop against Supabase with a real super_admin token: looked up a
  settled payment, recorded a refund, confirmed `already_reversed` on
  re-lookup, a second attempt correctly refused (409). One real bug found and
  fixed on the way: the lookup used `money_transaction()` (`kaf_money`),
  which has no grant on `ops.users`/`identity.athletes` — switched to the
  ordinary `transaction()` (`kaf_app`), which already has SELECT on
  `money.payments` and `money.ledger_entries`. `test_settlement.py` re-run
  clean the next day, against a private local PostgreSQL (Supabase's link
  dropped for the rest of that session — TCP-level, not a query timeout).
- **ATH-04, my payments — done and verified 2026-09-22** (`a2db088`).
  `list_payments()`, `GET /v1/payments`, `/payments` — every payment the
  athlete has ever started, newest first, same confirmed/checking/needs-a-
  check/not-completed language `/pay` already uses.
- **Paystack sandbox — RUN FOR REAL 2026-09-23, and it found a launch-blocking
  bug.** Test keys are in `api/.env` with `PAYMENT_PROVIDER=paystack`.
  1. **`.invalid` placeholder emails are refused.** `payments.kafriada.invalid`
     (RFC 2606's reserved TLD, chosen precisely because it never resolves) gets
     `400 "email" must be a valid email` from Paystack, which fails the whole
     checkout. **Every athlete without an email would have been unable to pay.**
     A test existed and asserted `email.endswith(".invalid")` — it passed
     because it ran against `FakeProvider`, which accepts anything. Default is
     now `payments.kafriada.ng`; the test now asserts a real TLD instead.
     `[USER]` confirm the domain and give it a **null MX** record (RFC 7505).
  2. **`fees` IS present** on a real `charge.success`/verify — so `decide()`
     does *not* freeze real payments. This was the other open unknown.
     ₦2,500 costs **13750 kobo** in fees, settling at **236250 kobo**
     (₦2,362.50) — the exact number for `.env`'s OPEN QUESTION A1.
  3. **The whole money path works end to end against real Paystack**: our
     `start_payment` → a real card charge → our `reconcile()` → exactly two
     ledger lines (250000 credit, 13750 fee debit) and one idempotency row.
     That is Stage 2 exit criterion 1 in substance, still in test mode.
  4. Paystack **rate-limits** `initialize` (429 after a handful in quick
     succession). Worth knowing before the burst test.
  Accepted domains checked: `kafriada.ng`, `payments.kafriada.ng`,
  `badellafarmandranch.site`. Still not done: no webhook has been received from
  Paystack (needs a public URL), so only the reconciliation path is proven —
  both share the same strict reader and idempotency key.
- **CRD-04, coordinator pays on behalf — done and verified 2026-09-23.**
  `POST /v1/lgas/{lga_id}/athletes/{kuid}/payments`
  (`payment.initiate_behalf`, scope `lga`), `/assist-pay`. `on_behalf_of` and
  `coordinator_id` are tagged on the row; two daily caps per coordinator (count
  and naira — **`[USER]` placeholders**, 20/day and ₦50,000/day, revisit from
  Wave 1's real figures). The payment receipt already reaches the athlete
  (built on the 2.3 notification work above). One real bug found and fixed:
  `mark_paid` excluded `on_behalf_of IS NOT NULL`, so an assisted payment would
  have settled money and moved nobody's verification to review. The load-
  bearing fix is the LGA check itself: `Requires(scope="lga")` only confirms
  the coordinator's *path* matches a grant, not that the *athlete named in the
  body* is in that LGA — without `_athlete_in_lga`, a coordinator could pay for
  any athlete in the country by keeping the path correct and naming someone
  else's athlete. `tests/test_payments_on_behalf.py` (10, incl. the cross-LGA
  case) plus the full suite pass clean against a real database, twice; a live
  HTTP round trip against the running server (Supabase) confirmed both the
  route-level 403 and the service-level 404.
- **2.3 outbox generalisation — done 2026-09-23.** A third event type,
  `notification.requested`, addressed to a **person** rather than a number or an
  inbox: the caller gives both wordings, and the worker resolves how to reach
  them at send time. `outbox.service.prefers_email()` is now the single place
  the pilot's channel rule lives, shared with the OTP path so they cannot
  drift. Two things this buys that a resolved address could not: a number
  changed after queueing is still the one used, and **a role with no grant on
  `ops.users` can still notify someone** — settlement runs as `kaf_money`,
  which by design cannot read that table, so a payment could not otherwise send
  its own receipt. Wired up: all four verification decisions, and a **payment
  receipt on settlement**, which did not exist at all before (half of a Stage 2
  exit criterion; the coordinator-pays-on-behalf half is 2.4, and the receipt
  already goes to `on_behalf_of`'s athlete rather than whoever pressed pay).
  Unreachable fails once and is kept as evidence rather than retrying; a
  delivered row keeps `user_id` and the address it actually reached.
  `tests/test_notifications.py` — 6, including the money-role privilege case.
- **ATH-02, edit my details — done and verified 2026-09-23** (migration
  0009). Gender, dominant side, secondary sport, years of experience — none
  of them captured at registration, all optional, all CHECK-constrained
  rather than a lookup table. `GET`/`PUT /v1/athletes/me`, behind
  `athlete.read_self`/`athlete.update_self` — both already seeded for the
  `athlete` role since migration 0001, so this closes a gap the schema had
  been sitting on since Stage 0. `/details`. **Verified against a private
  local PostgreSQL 15** (Supabase down all session — confirmed at the TCP
  level with nothing else running, not contention): migration applies and
  reverses cleanly, `check_migration_safety.py` clean, a live GET → PUT
  (valid) → PUT (invalid, correctly refused with the right field) → GET
  loop, `test_permission_matrix.py` and `test_route_manifest.py`, and a full
  `check:render` including a signed-in contrast/overflow audit of `/details`
  and `/payments` themselves. Repeat migration 0009 against Supabase once
  it's reachable. **Also fixed while verifying:** `docs/TODO.md`'s screen
  count and "empty contexts" line had both gone stale since 2.2 — corrected
  (22 of 46 screens built, not 12; `media` and `verification` have not been
  empty contexts for a while).
- **Migration 0010, clubs — done 2026-09-23.** `identity.organizations`,
  `teams`, `roster_members`. The at-most-one-open-membership rule is a
  partial unique index on `athlete_id` alone — global, not per-team, because
  CLB-03's "accepting an invitation moves you" is a system-wide rule, not a
  per-squad one. `career_events.club_id`, left bare since migration 0002 for
  exactly this table, now has its foreign key. `club.create` moved to the
  `athlete` role — the one role every account already holds, which is what
  CLB-01's "any signed-in user may register a club" actually means here;
  coordinators keep it too, for CLB-01's own manual-entry fallback.
  **Verified:** applies, reverses and re-applies cleanly against both a live
  Supabase (through the pooler) and a from-scratch local PostgreSQL 15; the
  full suite passed clean on the local instance. Two false alarms chased and
  ruled out along the way, neither caused by this migration — full detail in
  `docs/BUILD-LOG.md`. **Schema only:** no service, routes or screens yet —
  CLB-01 through CLB-04 and ATH-05 are next.

- **CLB-01 register a club and CLB-02 club dashboard — done and verified
  2026-09-24.** `POST /v1/clubs`, `GET /v1/clubs/{club_id}` (scope `club`),
  `/clubs/new`, `/clubs/[id]`. A club is an organization + one default team + a
  `club_admin` grant scoped to its id; new clubs are `pending_review` and nothing
  approves them yet. 15 tests in `tests/test_clubs.py`, isolation proved red by
  mutation. **Not built:** CLB-03/04, ATH-05, remove player, edit details, approval.
  `check-no-payout-path.sh` now ignores line numbers when matching its allowlist —
  add a new false positive by pasting its printed line into the script.
- **CLB-03 invite, ATH-05 my clubs, remove player, club approval — done and
  verified 2026-09-25** (migration 0011: `club.approve`, held by `super_admin`).
  `/clubs/[id]/invite`, `/clubs`, `POST /v1/admin/clubs/{id}/approve|suspend` (no
  screen). One active club per athlete; accepting moves them in one transaction.
  14 tests in `tests/test_club_roster.py`; the permission matrix covers the new
  routes. **Not built:** CLB-04, edit club details, an approval screen.
- **CLB-04, verify the club — done and verified 2026-09-25** (migration 0012).
  `money.payments.org_id`, `club_verification_requests`/`_decisions`, `club_document`
  media, `payments.service.start_club_payment`, settlement branch, `/clubs/[id]/verify`.
  Reviewer is a `super_admin` under `club.approve` via API only. 12 tests; real Paystack
  accepted a ₦15,000 checkout. **Not built:** revoke, club-document purge, reviewer screen.

## Next tasks, in order
1. ~~Fix phone→identity leak (privacy bug).~~ Done 2026-09-11.
2. ~~Registration copy promised an SMS code that is never sent.~~ Done 2026-09-11,
   and restored 2026-09-12 now that the code flow exists — true as soon as a
   provider is configured; with `SMS_PROVIDER=none` the code is only queued.
3. ~~1.2 Access~~ Done 2026-09-11 (see Status for what is deliberately not built).
4. ~~OTP via outbox~~ Done 2026-09-12. Waiting on Twilio credentials: set
   `SMS_PROVIDER=twilio` with the account SID, auth token and Messaging Service
   SID in `api/.env`, then run the dispatcher. Nothing else changes.
5. ~~Per-address rate limits~~ Verified 2026-09-20 on a local database, three
   faults found and fixed (see Status). Repeat on Supabase when it is reachable.
6. **0.6 deploy pipeline** — code done 2026-09-12; blocked on accounts: a staging
   Supabase project, a host (Fly/Render/Hetzner — decide), a Sentry project, and
   the `staging` GitHub Environment with `STAGING_DATABASE_URL_MIGRATE` and a
   required reviewer. Then build the images once for real.
7. Stage 2 (ledger & Paystack, media & verification, outbox jobs, assisted cash
   payment & clubs) — do not compress. Then Stage 3 launch readiness.
   **The full, ordered list — every remaining item, screen and decision — is
   `docs/TODO.md`. Start there.**
8. ~~ADM-03~~ / ~~ADM-04~~ / ~~ATH-04~~ / ~~ATH-02~~ — all built and verified
   2026-09-22/23 (see Status; ATH-02 and ADM-04's suite re-run against a
   private local database, Supabase down the whole stretch — repeat migration
   0009 there once it's back).
9. ~~2.3 outbox generalisation~~ and ~~CRD-04~~ — done and verified
   2026-09-23 (see Status).
10. ~~Migration 0010, clubs~~, ~~CLB-01~~, ~~CLB-02~~, ~~CLB-03~~, ~~ATH-05~~,
    club approval (API), ~~CLB-04~~ — done and verified 2026-09-24/25 (see Status).
    **Next in line, in order (per the chosen build order):** edit club details, then the coordinator console
    (CRD-01, CRD-03, CRD-06), then the admin console (ADM-01, ADM-02,
    ADM-06), then a way to appoint the first super_admin — see
    `docs/TODO.md`.

## Outside the code (block launch, not build)
Paystack business verification needs current CAC registration (1–3 weeks; nobody
has checked it is current). **Twilio account + Nigerian sender ID registration**
(replaces the Termii sender ID; the regulatory paperwork is the same shape and
nobody has started it). LGA code sign-off.

## Commits
End messages with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
Push to `origin main` (github.com/kafriadadev/kafriadadev_backend).
