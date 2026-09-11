# KAFRIADA CORE — working notes for Claude

Permanent sports ID for athletes (Jigawa State pilot, Birnin Kudu first). Register
free → permanent KUID + signed QR card → anyone can scan and verify. Paid Stage-2
verification (₦2,500) adds a photo. Full context: `docs/README.md` and the PDFs in `docs/`.

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
```
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
- The link to Supabase drops intermittently (DNS `getaddrinfo failed`, connection
  timeouts). Retry before debugging. The 200-registration burst test times out at
  default load on this link; use `BURST_WORKERS=6 BURST_SIZE=100`.
- Audit metadata keys containing `session`, `token`, `password` etc. are stored as
  `[redacted]` — name keys accordingly (e.g. `logins_ended`).
- FastAPI ≥0.141 nests included routers; walk routes with `api.security.api_routes(app)`,
  not `app.routes`.
- Disk C: runs near full; `npm cache clean --force` frees several GB.

## Invariants — do not weaken
- Audit log is append-only (grants + trigger). The app role cannot write the ledger;
  only the money role can. KUIDs are immutable (DB trigger). No withdrawal/payout
  path may exist (`scripts/check-no-payout-path.sh` fails CI).
- Public profile never shows phone, date of birth or documents.
- LGA codes in `contexts/geography/jigawa.py` are printed into every KUID —
  **need CEO/state-coordinator sign-off before the first card is issued.**

## Status (as of 2026-09-11)
- Stage 0 foundations — done, except 0.6 deploy pipeline (staging, Sentry).
- 1.1 identity anchor — done. Live Supabase DB, security guarantees proved.
- 1.3 KUID minting — done, burst-tested under real contention.
- 1.4 partial — API: register, public profile, signed QR. Web: landing, register,
  card, profile, find, privacy. All verified by `check:render`.
- Phone→identity leak — fixed. A duplicate phone gets a field error on `phone`
  (no name, KUID or card); detected by the `users_phone_unique` index name, so
  still no second KUID. `?returning` path removed. Test:
  `api/tests/test_duplicate_phone_reveals_nothing.py`.
- 1.2 access — done (ADR 0002: our own revocable session cookie). API:
  `POST/DELETE /v1/sessions`, `GET /v1/me`, super_admin role grant/revoke and
  end-all-sessions under `/v1/admin` (password re-entered for grant/revoke),
  `GET /v1/lgas/{lga_id}/athletes` (LGA-scoped). `access.can()` behind
  `Requires(perm, scope=)`; `SignedIn()` for own-account routes. Migration 0003
  (applied to dev DB). Web: `/sign-in`, `/me`, sign-out. Tests: route manifest,
  `test_access_sessions.py`, `test_permission_matrix.py` (12 principals × 12 routes,
  two tenants).
- **Not built:** OTP, outbox, password reset (AUT-05), per-IP sign-in rate limit
  (needs Redis), expired-session sweep job, admin UI (ADM-02 is API only), a way to
  appoint the first super_admin (today: SQL insert into `ops.user_roles`).
  `docs/KAFRIADA-CORE-Build-Tracker.pdf` predates most of this — update it.

## Next tasks, in order
1. ~~Fix phone→identity leak (privacy bug).~~ Done 2026-09-11.
2. ~~Registration copy promised an SMS code that is never sent.~~ Done 2026-09-11:
   all SMS/code wording removed from the web. Put it back when OTP (item 4) ships.
3. ~~1.2 Access~~ Done 2026-09-11 (see Status for what is deliberately not built).
4. **OTP via outbox** (Termii; outage queues rather than fails) — Termii sender ID
   takes 3–10 days to approve.
5. **0.6 deploy pipeline** — staging, gated migrations, Sentry.
6. Stage 2 (ledger & Paystack, media & verification, outbox jobs, assisted cash
   payment & clubs) — do not compress. Then Stage 3 launch readiness.

## Outside the code (block launch, not build)
Paystack business verification needs current CAC registration (1–3 weeks; nobody
has checked it is current). Termii sender ID (3–10 days). LGA code sign-off.

## Commits
End messages with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
Push to `origin main` (github.com/kafriadadev/kafriadadev_backend).
