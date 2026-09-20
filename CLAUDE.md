# KAFRIADA CORE — working notes for Claude

Permanent sports ID for athletes (Jigawa State pilot, Birnin Kudu first). Register
free → permanent KUID + signed QR card → anyone can scan and verify. Paid Stage-2
verification (₦2,500) adds a photo. Full context: `docs/README.md` and the PDFs in `docs/`.
**What is left to build, in order: `docs/TODO.md`.**

A developer is testing what's built, coached by their own agent. That agent's
brief is `docs/TEAM-AGENT-BRIEF.md`; test runs land in `docs/TEST-LOG.md`,
anything that took more than one attempt lands in `docs/ISSUE-LOG.md`, and how
the developer is coming along lands in `docs/DEVELOPER-PROGRESS.md`. Check
those before assuming something untested actually works.

## Working style (user preference)
Be terse. Prefer text checks over reading screenshots. One milestone per session:
build → verify → commit → stop. Don't expand scope without asking.

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
- **2026-09-20: `db.slwlefnfdsjfeimyjhag.supabase.co` and the project's API host
  `slwlefnfdsjfeimyjhag.supabase.co` do not resolve at all** ("No such host") while
  supabase.com and github.com do — so it is not IPv6 and not the local network. Most
  likely the free project was **paused after a week idle** (or removed). Check the
  Supabase dashboard and restore it before debugging anything else.
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
  timeouts). Retry before debugging. The 200-registration burst test times out at
  default load on this link; use `BURST_WORKERS=6 BURST_SIZE=100`.
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
- The API must be restarted to pick up new routes — it runs without `--reload`.
- Disk C: runs near full; `npm cache clean --force` frees several GB.

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
  Next: 2.2 (media and verification) — or 2.3's reconciliation/72h expiry, which
  share `settle_charge`.
- **Not built:** expired-session sweep, outbox retention/scheduling (0.6 — the
  worker is started by hand today), admin UI (ADM-02 is API only), a way to
  appoint the first super_admin (today: SQL insert into `ops.user_roles`).
  `docs/KAFRIADA-CORE-Build-Tracker.pdf` predates most of this — update it.

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
   `docs/TODO.md`. Start there.** Next in line: 2.2 (media and verification).

## Outside the code (block launch, not build)
Paystack business verification needs current CAC registration (1–3 weeks; nobody
has checked it is current). **Twilio account + Nigerian sender ID registration**
(replaces the Termii sender ID; the regulatory paperwork is the same shape and
nobody has started it). LGA code sign-off.

## Commits
End messages with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
Push to `origin main` (github.com/kafriadadev/kafriadadev_backend).
