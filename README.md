# KAFRIADA CORE

An identity authority for African sport that also holds other people's money.

Free athlete registration issues a permanent, never-reused **KUID** and a public QR profile.
Paid Stage-2 verification (₦2,500 athlete / ₦15,000 club) unlocks the photograph and a verified
badge. Club rosters are free. A closed-loop ledger records money arriving and has no mechanism
for money leaving.

Pilot: Jigawa State, Nigeria — 27 LGAs, adults only, anchor LGA Birnin Kudu.

## Documents

| Document | What it is |
| --- | --- |
| `docs/KAFRIADA-CORE-Target-Architecture.pdf` | The architecture this repository implements |
| `docs/KAFRIADA-CORE-Wireframes.pdf` | All 46 screens, numbered `PUB-01`, `VER-03`, … |
| `docs/KAFRIADA-CORE-Build-Plan.pdf` | Stages, estimates, and what was deliberately cut |
| `docs/KAFRIADA-CORE-Architecture-DraftV1.pdf` | Superseded, kept for the flow and failure analysis |
| `docs/Kaf 0100 Doc.pdf` | KAF 000 GDOC v1.0 — the original 244-page specification |

Screen codes from the wireframes are the shared vocabulary. Use them in commit messages,
test names and issues: `feat(identity): AUT-01 registration form`.

## Layout

```
api/     FastAPI domain tier — every business rule, every authorisation decision,
         the only database credentials. Not internet-reachable except for the
         anonymous read surface and the Paystack webhook.
web/     Next.js presentation tier, acting as a backend-for-frontend. No business
         logic, no database credential. The browser talks only to this origin.
infra/   Local Docker Compose, deploy configuration.
docs/    Specifications and the original GDOC.
scripts/ Developer and operations scripts.
```

## The rules that are not negotiable

These are not style preferences. Each one exists because of a specific failure documented in
the architecture. Breaking any of them is a defect, not a shortcut.

1. **Money is integer kobo.** Never a float, never a `Decimal` in the database, never in a
   JSON payload as a decimal number. `2500` naira is `250000` kobo.
2. **No withdrawal path exists.** No `withdraw`, no `payout`, no `transfer_to`, for any role,
   under any name — not disabled, not feature-flagged, *absent*. CI greps for these and fails.
3. **Audit rows are insert-only, enforced by database grants.** No application role holds
   `UPDATE` or `DELETE` on `ops.audit_log`. A test asserts this on every migration run.
4. **Password hashing happens outside every database transaction.** Argon2id is deliberately
   expensive; holding a lock across it collapses registration throughput.
5. **The Paystack webhook is the source of truth for payment**, never the browser redirect.
   Read the raw body before parsing, verify the HMAC in constant time, and make the whole
   path idempotent.
6. **Every route declares a required permission.** A route without one fails the build.
   Authorisation is checked with *scope* — a club admin's authority stops at their club.
7. **Every launch screen works with JavaScript disabled.** Opera Mini in proxy mode is common
   in northern Nigeria and has no service worker. JavaScript is enhancement, never a
   dependency.
8. **Session tokens are stored hashed.** The database never holds a value that could be
   replayed as a cookie.

## Running it locally

Prerequisites: Docker Desktop, Python 3.12, [uv](https://docs.astral.sh/uv/), Node 22, pnpm.

```bash
cp .env.example .env          # then fill in the values; never commit .env
docker compose -f infra/docker-compose.yml up -d
cd api && uv sync && uv run alembic upgrade head && uv run uvicorn kafriada.main:app --reload
```

API on `http://localhost:8000`, interactive docs on `/docs` (development only — the schema
endpoints are disabled in production).

## Before you commit

```bash
cd api && uv run ruff check . && uv run mypy src && uv run pytest
```

`gitleaks` runs as a pre-commit hook. Install the hook once with `bash scripts/install-hooks.sh`.
