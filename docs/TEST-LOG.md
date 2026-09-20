# Test log

Every test run, documented here — passing or failing. See
[`TEAM-AGENT-BRIEF.md`](./TEAM-AGENT-BRIEF.md) §6 for what belongs here
versus in [`ISSUE-LOG.md`](./ISSUE-LOG.md). Newest entries at the top.
Never delete an entry; if something changes, add a new one that says so.

## Status note (for the project lead — keep this current, keep it short)

**2026-09-19** — Started API server on port 8010. `/healthz` returned 200 OK. `/readyz` returned 503 Service Unavailable (`OperationalError` connecting to PostgreSQL pools `app`, `money`, `read` after 30s timeout). Troubleshooting database connectivity (IPv6 / network link / host config) before proceeding with migration 0005.

---

## Entry template

Copy this for each run:

```
### <YYYY-MM-DD HH:MM> — <who ran it: developer / agent> — <one-line task>

**Command:**
    <the exact command>

**Result:** PASS / FAIL / ERROR / SKIPPED

**Output (relevant excerpt, not the whole scrollback):**
    <paste>

**Notes:** <anything that needs explaining — why it was run, what it proves,
what's still not covered>
```

### 2026-09-19 19:28 — developer — API Health & Readyz Probes (Step 1 of §5)

**Command:**
    curl http://127.0.0.1:8010/healthz
    curl http://127.0.0.1:8010/readyz

**Result:** /healthz PASS (200 OK), /readyz FAIL (503 Service Unavailable)

**Output (relevant excerpt):**
    GET /healthz -> 200 OK {"status":"ok"}
    GET /readyz -> 503 Service Unavailable {"status":"not ready"}
    Server logs:
      [error] db_unreachable error_type=OperationalError pool=app duration_ms=30364
      [error] db_unreachable error_type=OperationalError pool=money
      [error] db_unreachable error_type=OperationalError pool=read
      [error] not_ready app=False money=False read=False

**Notes:** Server booted cleanly. Database connection timed out after 30 seconds across all 3 pools. Per TEAM-AGENT-BRIEF §8, intermittent IPv6 / DNS connection drops to Supabase are a known condition on this network. Retrying and verifying host reachability.

---

### 2026-09-19 19:15 — developer — Full pytest suite (post-segno install)

**Command:**
    cd api && .venv\Scripts\python.exe -m pytest -v

**Result:** PASS (176 passed, 53 skipped in 10.71s)

**Output (relevant excerpt):**
    collected 229 items
    tests\test_access_sessions.py sssssssssssssssss                                  [  7%]
    tests\test_audit_log_is_immutable.py sssssssss                                   [ 11%]
    tests\test_codes_and_outbox.py ssssssssssss                                      [ 16%]
    tests\test_duplicate_phone_reveals_nothing.py s                                  [ 17%]
    tests\test_identity_anchor.py ..............................................     [ 37%]
    tests\test_permission_matrix.py ss                                               [ 37%]
    tests\test_rate_limits.py sssssssss                                              [ 41%]
    tests\test_registration_burst.py sss                                             [ 43%]
    tests\test_release_and_observability.py ....................                     [ 51%]
    tests\test_route_manifest.py ................................................... [ 75%]
    tests\test_security_primitives.py ....................................           [ 91%]
    tests\test_settings_refuses_insecure_config.py ...................               [100%]
    ================== 176 passed, 53 skipped, 3 warnings in 10.71s ==================

**Notes:** All 176 non-database unit tests pass cleanly. The 53 skipped tests (`s`) require `DATABASE_URL_APP` / database connection to execute. Ready to proceed with database connectivity check and rate-limit verification.

---

### 2026-09-19 18:52 — developer — Full pytest suite (post-.env creation)

**Command:**
    cd api && .venv\Scripts\python.exe -m pytest -v

**Result:** ERROR (7 collection errors due to missing package `segno`)

**Output (relevant excerpt):**
    sentry_enabled environment=local release=None traces_sample_rate=0.1
    collected 113 items / 7 errors
    src\kafriada\api\v1\athletes.py:19: in <module>
        import segno
    E   ModuleNotFoundError: No module named 'segno'

**Notes:** `api/.env` was verified present and correctly loaded (Settings() validation errors are resolved). All 7 collection errors are now caused by `import segno` in `src/kafriada/api/v1/athletes.py` (QR code generation). `segno` is used in code but was missing in the newly installed environment. Fix is installing `segno` into `.venv`.

---

### 2026-09-18 19:51 — developer — Full pytest suite (first run on this machine)

**Command:**
    cd api && .venv\Scripts\python.exe -m pytest -v

**Result:** ERROR (7 collection errors, 0 tests ran)

**Output (relevant excerpt):**
    collected 113 items / 7 errors
    ERROR tests/test_access_sessions.py - pydantic_core._pydantic_core.ValidationError: 4 validation errors for Settings
    ERROR tests/test_codes_and_outbox.py - same
    ERROR tests/test_duplicate_phone_reveals_nothing.py - same
    ERROR tests/test_permission_matrix.py - same
    ERROR tests/test_rate_limits.py - same
    ERROR tests/test_release_and_observability.py - same
    ERROR tests/test_route_manifest.py - same
    Root cause in all 7: Settings() fails with missing fields:
      database_url_app, database_url_money, secret_key, qr_secret

**Notes:** api/.env does not exist on this machine. These 7 tests import
`kafriada.main` at module level, which calls `get_settings()` at import time,
which requires real credentials to be present. The remaining 7 test modules
(test_audit_log_is_immutable, test_identity_anchor, test_registration_burst,
test_security_primitives, test_settings_refuses_insecure_config) were not
collected either — session was interrupted before them. No source code was
touched. Blocked: need api/.env with real Supabase credentials before tests
can run.

<!-- Newest entries go here, above this line. -->
