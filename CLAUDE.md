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
plus a JS-off registration round trip that writes nothing. Run it after any UI change.

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
- **Not built:** 1.2 access (sessions, login, roles, permission matrix), OTP, outbox.
  `docs/KAFRIADA-CORE-Build-Tracker.pdf` predates most of this — update it.

## Next tasks, in order
1. ~~Fix phone→identity leak (privacy bug).~~ Done 2026-09-11.
2. **Registration form promises an SMS code that is never sent.** The phone hint
   ("We send a code…") is gone; still left: "You will need a phone that can
   receive SMS" in `web/src/app/page.tsx` and `web/src/app/register/page.tsx`.
   Either remove that copy until OTP exists or build OTP (next item).
3. **1.2 Access** — blocked on the sign-in decision (Supabase Auth in browser vs.
   Supabase for passwords/codes + our own revocable session cookie; tracker
   recommends the latter). Ask the user before starting. Then: sessions
   (30 min staff / 30 days athletes), `can(user, permission, scope)` deny-by-default,
   generated permission-matrix test with a second tenant, audit write on every change.
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
