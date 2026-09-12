# Deploy runbook — staging

Stage 0.6. What exists, what is deliberately manual, and the one decision still
open.

## The shape

```
Cloudflare  ──►  web (Next.js, :3000)  ──►  api (FastAPI, :8010)  ──►  Supabase (Frankfurt)
                 published                   private network only        migrate role, release step only
                                                   ▲
                                          outbox worker (same image)
```

Only the web tier is reachable. The API is on the internal network, which is
what makes an authorisation bug on a private route unreachable from outside.
The `kaf_migrate` credential is **never** given to a running process — it exists
only in the release step and in CI.

## Releasing

```bash
export DATABASE_URL_MIGRATE=…            # the kaf_migrate role, never the app role
bash scripts/release.sh plan     staging # prints the pending SQL; changes nothing
bash scripts/release.sh migrate  staging # asks you to type "staging" first
bash scripts/release.sh verify   staging # asserts the database is at head
bash scripts/release.sh smoke    https://staging.kafriada.ng
```

In CI the same script runs from `.github/workflows/deploy-staging.yml`:

1. **plan** — no approval needed, prints the SQL into the job summary.
2. **migrate** — waits on the `staging` GitHub Environment, which carries the
   required-reviewer rule. That rule lives in the repository settings, not in
   the workflow file, so a pull request cannot approve its own migration.
3. **images** — builds both images.
4. **smoke** — `/healthz` and `/readyz` against `STAGING_BASE_URL`.

`scripts/check_migration_safety.py` runs in CI and in `plan`: a migration whose
`upgrade()` drops a table or column, truncates, deletes rows, retypes a column
or disables a trigger fails the build unless it says why:

```python
DESTRUCTIVE_MIGRATION_APPROVED = "the column held nothing; agreed with X on DATE"
```

## Rolling back

**App code:** deploy the previous tag, and run the deploy with
`skip_migrations: true`. Migrations here are additive, so the older code runs
against the newer schema.

**A migration:** `cd api && alembic downgrade -1`, by hand, deliberately. CI
proves every migration round-trips (`downgrade base` then `upgrade head`), but a
downgrade against real data destroys whatever the upgrade created. Read the
`downgrade()` first.

**Never** roll the database back past a migration whose data another migration
has already changed. Take a Supabase point-in-time restore instead.

## What is required before staging can run

| Needed | State |
| --- | --- |
| A staging Supabase project (Frankfurt), roles created with `infra/bootstrap-roles-supabase.sql` | **not created** |
| A host for the two containers | **not chosen** — see below |
| `SECRET_KEY`, `QR_SECRET` generated fresh for staging (never the local ones) | not generated |
| GitHub Environment `staging` with a required reviewer, secret `STAGING_DATABASE_URL_MIGRATE`, variable `STAGING_BASE_URL` | not configured |
| Sentry project and DSN | not created |

### The open decision: where staging runs

The images are provider-agnostic on purpose. Any of these works, and the choice
is about money and operational taste, not about the code:

- **Fly.io** — Frankfurt region, two small machines, private networking between
  them by default. Closest to the topology above.
- **Render** or **Railway** — simplest to set up; private networking included.
- **A small Hetzner VPS in Nuremberg** with `infra/docker-compose.staging.yml` —
  cheapest, and the most to maintain.

Whichever it is, the same two images and the same release script apply; what
changes is one deploy step in the workflow.

## Observability

Sentry is wired in the API and is inert without `SENTRY_DSN`. When a DSN is set:
errors are reported, 10% of requests are traced (`SENTRY_TRACES_SAMPLE_RATE`),
`RELEASE` tags each event with the deployed commit, and every event is scrubbed
of phone numbers, bearer tokens and database URLs before it leaves the process
(`api/src/kafriada/observability.py`). Request bodies are never captured — a
registration body holds a name, a phone number and a password.

The web tier logs to stdout and is **not** wired to Sentry yet; that needs
`@sentry/nextjs` and its build-time configuration.

## Probes

- `/healthz` — is the process alive. Reveals nothing else.
- `/readyz` — can it reach the database on each role. 503 when it cannot, and
  which role failed goes to the log, not to the response.
