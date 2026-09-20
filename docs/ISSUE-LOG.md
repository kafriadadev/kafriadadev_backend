# Issue log

Anything that took the developer and their agent more than one attempt to
work out. This is the record of *how* an answer was reached, not just what
the answer was — if the project lead has to understand a complex issue
later, this is where that reasoning lives. See
[`TEAM-AGENT-BRIEF.md`](./TEAM-AGENT-BRIEF.md) §6. Newest entries at the top.
Never delete an entry, even a wrong turn — a dead end is worth recording too.

---

## Entry template

Copy this for each issue:

```
### <YYYY-MM-DD> — <short title>

**Reported by:** developer / agent
**Where:** <file, endpoint, or command>

**What was expected:**
<one or two lines>

**What actually happened:**
<paste the real output or behaviour, not a paraphrase>

**What was tried, in order:**
1. <attempt> → <what that showed, even if it didn't fix it>
2. <attempt> → <what that showed>
...

**Root cause:**
<once found — if the session ended without finding it, say so plainly
instead of guessing>

**Fix (or: still open, handed off because ___):**
<what changed, or the honest state it was left in>

**Where this is covered going forward:**
<a test that now catches this, or "nothing yet — flagged for follow-up">
```

---

### 2026-09-19 — Database unreachable on /readyz probe: Direct Supabase host is IPv6-only

**Reported by:** developer / agent
**Where:** `/readyz` probe, `db.slwlefnfdsjfeimyjhag.supabase.co:5432`

**What was expected:**
`curl http://127.0.0.1:8010/readyz` returns 200 OK once `api/.env` is configured with Supabase credentials.

**What actually happened:**
    `[error] db_unreachable error_type=OperationalError method=GET path=/readyz pool=app duration_ms=30364`
    `[error] not_ready app=False money=False read=False status=503`
Connection timed out after 30 seconds across all 3 pools.

**What was tried, in order:**
1. Verified `api/.env` exists and contains the valid Supabase direct host: `db.slwlefnfdsjfeimyjhag.supabase.co:5432`.
2. Verified `CLAUDE.md` and `TEAM-AGENT-BRIEF.md` notes: this machine's network lacks stable IPv6 routing to Frankfurt Supabase. Direct `db.*.supabase.co` addresses are IPv6-only.

**Root cause:**
Direct Supabase connection endpoints (`db.<project-ref>.supabase.co`) resolve only to IPv6 AAAA records. When the local network does not support IPv6 routing or drops IPv6 packets, PostgreSQL connections time out.

**Fix (or: still open):**
Option 1: Connect via Supabase IPv4 connection pooler (e.g. `aws-0-eu-central-1.pooler.supabase.com:6543` / `aws-0-eu-central-1.pooler.supabase.com:5432` with username format `kaf_app.slwlefnfdsjfeimyjhag`).
Option 2: Re-enable / verify IPv6 routing on the local internet connection / hotspot.

---

### 2026-09-19 — Missing dependency: `segno` used for QR codes but missing from pyproject.toml

**Reported by:** agent (from developer's terminal output)
**Where:** `src/kafriada/api/v1/athletes.py:19` (`import segno`)

**What was expected:**
Running `pytest -v` after setting up `api/.env` would collect and run tests.

**What actually happened:**
    sentry_enabled environment=local release=None traces_sample_rate=0.1
    src\kafriada\api\v1\athletes.py:19: in <module>
        import segno
    E   ModuleNotFoundError: No module named 'segno'

**What was tried, in order:**
1. Created `api/.env` with credentials → successfully resolved previous `pydantic_core.ValidationError`.
2. Ran `pytest -v` → hit `ModuleNotFoundError: No module named 'segno'` on all routes importing `athletes.py`.
3. Inspected `pyproject.toml` dependencies: confirmed `segno` is not listed in `[project.dependencies]` or optional dependencies.

**Root cause:**
`segno` (QR code generation library) is used in `athletes.py` to generate signed QR cards, but was not included in `pyproject.toml` dependencies.

**Fix:**
Install `segno` directly into `.venv` with `.venv\Scripts\python.exe -m pip install segno`.

**Where this is covered going forward:**
Once installed, route collection passes. `pyproject.toml` should formally include `segno>=1.6` in dependencies in a future build milestone (deferred under the strict no-code-mutation test mandate).

---

### 2026-09-18 — Virtual environment broken: stale absolute paths after project folder move

**Reported by:** agent (from developer's terminal output)
**Where:** `api/.venv/Scripts/pip.exe`

**What was expected:**
Running `.venv\Scripts\pip.exe install -e ".[dev]"` would install dev dependencies.

**What actually happened:**
    Fatal error in launcher: Unable to create process using
    '"C:\Users\M. Hassan Nayaya\kafriadadev_backend\api\.venv\Scripts\python.exe"'
    The system cannot find the file specified.
The path inside the launcher pointed to `kafriadadev_backend\api` (old location)
when the actual path is `kafriadadev\kafriadadev_backend\api` (current location).

**What was tried, in order:**
1. Ran `.venv\Scripts\pip.exe install -e ".[dev]"` → fatal launcher error above.
2. Identified cause: project folder was moved/renamed after .venv was created,
   embedding now-wrong absolute paths in every .venv launcher executable.
3. Re-created .venv with `python -m venv .venv --clear` → fixed the path issue.
4. Ran `pip install -e ".[dev]" --timeout 120` (needed --timeout because the
   connection dropped twice mid-download before succeeding on the third run).

**Root cause:**
Python venv launchers hardcode absolute paths at creation time. Moving the
project folder breaks them. Re-creating the venv fixes it.

**Fix:** Re-created .venv using `python -m venv .venv --clear`, then re-installed.

**Where this is covered going forward:**
Not covered by any automated test — it's a machine setup issue. Flagged here
so the next person hitting it doesn't spend time debugging.

---

### 2026-09-18 — api/.env missing: pytest cannot collect 7 of 14 test modules

**Reported by:** agent (from developer's terminal output)
**Where:** `api/tests/` — all tests that import `kafriada.main` at module level

**What was expected:**
Running `pytest -v` would collect and run the full test suite.

**What actually happened:**
    collected 113 items / 7 errors
    pydantic_core._pydantic_core.ValidationError: 4 validation errors for Settings
      database_url_app: Field required
      database_url_money: Field required
      secret_key: Field required
      qr_secret: Field required
`kafriada.main` calls `get_settings()` at import time. `get_settings()` calls
`Settings()` which reads from the environment and from `api/.env`. That file
does not exist on this machine.

**What was tried, in order:**
1. Ran `pytest -v` → 7 collection errors as above.
2. Checked whether `api/.env` exists: `dir api\.env` → "The system cannot
   find the path specified."
3. Confirmed: the file was never created on this machine. It is gitignored
   by design and must be created manually with real credentials.

**Root cause:**
`api/.env` does not exist on this machine. The Supabase connection strings
and signing secrets have never been configured here.

**Fix (still open):**
Need `api/.env` populated with real credentials:
  - DATABASE_URL_APP and DATABASE_URL_MONEY from the Supabase project
    (see docs/KAFRIADA-CORE-Accounts-and-Keys.pdf or original developer's .env)
  - SECRET_KEY and QR_SECRET (existing values from the original machine,
    or freshly generated ones if starting fresh)
All database tests will remain blocked until this is in place.

**Where this is covered going forward:**
Once .env is in place, the test suite itself will confirm everything works.
This entry stays in the log as a record of the setup state at session start.

<!-- Newest entries go here, above this line. -->
