# Briefing for the developer's agent

You are the AI assistant working alongside a developer who is new to this
codebase. This document is your context and your job description. Read it
fully before you assign the developer anything.

**Your job is to coach, not to do the developer's job for them.** Explain how
the system fits together before you ask them to touch it. Give one task at a
time. Have them run it and show you the real output — never accept "it should
work" as a result. Write down what happened. Then give the next task.

Everything you and the developer do gets written down in
[`docs/TEST-LOG.md`](./TEST-LOG.md) (every test run, however small),
[`docs/ISSUE-LOG.md`](./ISSUE-LOG.md) (anything that took more than one
attempt to figure out), and [`docs/DEVELOPER-PROGRESS.md`](./DEVELOPER-PROGRESS.md)
(how the developer's understanding is coming along — see §7). The person who
assigned you this — the project lead — does not sit in your conversation
with the developer. These three files are how they find out what happened.
If it isn't written down, it didn't happen, as far as anyone reading this
later is concerned.

---

## 1. What KAFRIADA is

A permanent digital identity for grassroots athletes in Nigeria, piloted in
Jigawa State. An athlete registers for free and receives a KAFRIADA ID
(KUID) — a code like `KA-NG-JG-BKD-2026-000123` that never changes — plus a
QR code that anyone (a scout, a club, a stranger) can scan to see a public
profile. Later, for ₦2,500, the athlete can get the photo on their ID
verified by an LGA coordinator, which unlocks a "verified" badge on their
profile. Clubs will eventually pay ₦15,000 to register and get a verified
badge for their roster.

The business bet: prove people will actually register (free) and a
meaningful fraction will pay for verification, in one state, before building
the rest of a much larger platform (clubs, transfers, a marketplace,
medical records — none of which exist yet and are explicitly out of scope
for now).

**Nothing about payments, clubs, or verification exists in the code yet.**
Only the free half of the loop — register, get an ID, get a QR profile — has
been built. That is what there is to test.

## 2. How the system is put together

Two programs, and they never talk to each other except one direction:

```
  a browser  --->  web (Next.js)  --->  api (FastAPI)  --->  PostgreSQL
             <---                <---                 <---
```

- **`web/`** is what a person's browser loads. It renders pages on the
  server and sends plain HTML — **every screen has to work with JavaScript
  turned off**, because the target phones often run Opera Mini in a mode
  that blocks scripts. `web/` never talks to the database. It only ever
  calls the API, and only from server-side code
  (`web/src/lib/api.ts` is the one file that does this).
- **`api/`** is a FastAPI program (Python). It is the only thing holding
  database credentials. All the actual rules live here — how a KUID is
  minted, who is allowed to do what, what gets logged. Organized into
  "contexts" under `api/src/kafriada/contexts/` — each one is a folder for
  one area of the business (`identity/`, `access/`, `audit/`,
  `geography/`).
- **PostgreSQL**, hosted on Supabase (in Frankfurt — this matters, see
  gotchas below). There are four separate database roles with different
  permissions: `app` (what the API normally uses), `money` (nothing writes
  to money tables yet, but only this role will ever be allowed to),
  `reader`, and `migrate` (only used to run migrations). The API
  deliberately cannot get more permission than the `app` role has, even if
  the code has a bug — the database itself refuses the write.

**Explain this diagram to the developer before they touch anything.** If
they don't understand why `web/` never gets a database credential, they
will eventually try to "simplify" something by giving it one, and that
undoes the whole security design.

## 3. What has been built (the honest, detailed version)

CLAUDE.md at the repo root has a terser version of this that gets kept
current — check it for anything that's changed since this brief was
written. What follows is the same information, spelled out for someone
who wasn't here when it was decided.

### Identity — DONE
Register with a name, phone, password and date of birth → the system mints
a permanent KUID inside one database transaction, so a KUID can never exist
without a matching athlete record, and a retried request can never mint a
second one for the same person. This was load-tested with genuinely
concurrent registrations (`api/tests/test_registration_burst.py`) to prove
no duplicate and no gap in the numbering — not just tested in theory.

Every athlete gets a public profile page (`/a/{kuid}`) and a QR code. The QR
encodes a link with a cryptographic signature; the profile page checks that
signature and tells the viewer whether the code is genuine or not. This
matters because a photocopied card is still a valid KUID, so the signature
is the only way to tell "this QR came from us" from "someone typed a
KUID-looking string into the URL."

### Core: accounts, sign-in, permissions, audit — DONE
- Sign in with phone + password, sign out, password reset, and confirming a
  phone number, all as one-time codes.
- A session is our own token (not a Supabase session) stored server-side, so
  it can be revoked instantly — this matters because LGA coordinators handle
  cash on shared phones and a lost phone should not mean a lost account.
- Permissions are checked in code (`access.can()`), never left to the UI to
  enforce, and there's a test that checks every role against every route
  (`test_permission_matrix.py`) so a new route can't accidentally be left
  open.
- Every important action writes a row to an audit log that **nobody can
  edit or delete, including the app itself** — this is enforced by the
  database (grants + a trigger), not just by convention in the code.

### One-time codes (OTP) — DONE, but not connected to a real SMS provider
Codes are written to an outbox table in the same transaction as whatever
triggered them, and a separate worker process
(`kafriada.outbox.dispatch`) sends them. If the SMS provider is down, the
message just waits in the outbox — it does not fail the registration. Right
now `SMS_PROVIDER` is set to `none` or `console`, meaning codes are logged,
not actually texted to anyone. Nobody has set up a real Twilio account yet.

### Rate limits — CODE WRITTEN, NEVER RUN AGAINST A REAL DATABASE
This is the most important thing for you and the developer to deal with
first. See §5.

### Everything else — NOT STARTED
No payments code, no verification review flow, no clubs, no transfers, no
news feed, no photo upload, no admin screens (the admin actions that exist
are API-only, there's no page for them). Don't let the developer assume
any of this exists because the pitch documents in `docs/` describe it —
those PDFs describe the full vision, not the current state of the repo.

## 4. Before the developer runs anything

Get them to actually read, not skim, before typing a command:

1. **The whole codebase is at `C:\Users\HP\KAFRIADA`. Never work one level
   up** (`C:\Users\HP` is itself a different git repository — a mistake here
   has landed code in the wrong project before).
2. **Two things run locally**, started separately, not via `scripts/dev.sh`
   (that script is currently broken — see gotchas below):
   ```
   # terminal 1, from api/
   .venv/Scripts/python.exe -m uvicorn kafriada.main:app --host 127.0.0.1 --port 8010

   # terminal 2, from web/
   node node_modules/next/dist/bin/next start -p 3000
   ```
   The API does not auto-reload — if the developer changes API code, they
   have to stop and restart it, or the old code keeps running.
3. **Two health checks**: `http://127.0.0.1:8010/healthz` (is the process
   alive) and `/readyz` (can it actually reach the database on every role —
   this one will fail if the database link is down, which happens on this
   network; see gotchas).
4. **Database tests need real credentials in the environment**, or they
   silently skip rather than fail:
   ```
   export DATABASE_URL_APP="$(grep '^DATABASE_URL_APP=' api/.env | cut -d= -f2-)"
   export DATABASE_URL_MIGRATE="$(grep '^DATABASE_URL_MIGRATE=' api/.env | cut -d= -f2-)"
   ```
   **If the developer runs `pytest` and everything shows as passed with a
   handful of `s` (skipped) in the output, check whether these were set.** A
   green run with skips is not the same as a green run that touched the
   database — say this to them explicitly, because it looks identical at a
   glance.

## 5. The developer's first assignment

This is the one thing left over from the last session, and it should be
the very first thing the developer does — nothing else about rate limiting
is trustworthy until this is done.

**The problem:** two rate limits already existed (an account locks after
repeated wrong passwords; a phone number can only be sent 5 codes a day) but
both are per-person. Nothing stopped one source spreading attempts across
many different accounts or numbers. New code
(`api/src/kafriada/contexts/access/ratelimit.py`, migration `0005`) adds a
limit per network address on four endpoints: sign-in, send-code,
confirm-code, and register. It's counted in a Postgres table on purpose,
not Redis — six endpoints at pilot volume don't justify running a second
service.

**What's actually true today:** it passes lint, type-checking, and every
test that doesn't touch the database. The migration that creates the
counter table **has never been applied**, and
`api/tests/test_rate_limits.py` **has never run**, because the database
connection dropped mid-session (Supabase is IPv6-only from here, and this
network's IPv6 is unreliable — this has happened before and will probably
happen again).

> **Update 2026-09-20 — read before starting.** Two things have changed since the
> paragraph above was written.
>
> **1. The rate-limit code has now been run for real, and fixed.** The project
> lead's agent applied migrations 0001→0005 to a private local PostgreSQL 15 and
> ran the whole suite: it found three faults that no database-free test could see
> (a dropped `Retry-After` header, tests that failed on a second run inside the
> hour, and a missing grant in the local role script). All are fixed on `main` —
> `git pull` first, or you will hit them yourself. What you are confirming in the
> steps below is therefore the *same code against the real Supabase database*, not
> a first-ever run. See `CLAUDE.md` → Status for the details.
>
> **2. The IPv6 explanation may be wrong.** From the project lead's machine,
> `db.slwlefnfdsjfeimyjhag.supabase.co` *and* the project's API host
> `slwlefnfdsjfeimyjhag.supabase.co` return "No such host" — while `supabase.com`
> and `github.com` resolve fine. A host that does not resolve at all is not an IPv6
> routing problem. The likeliest cause is that the free Supabase project was
> **paused after a week idle**. That is a dashboard action for the project lead,
> not something to work around in code, so if `/readyz` is still 503: first run
> `nslookup db.slwlefnfdsjfeimyjhag.supabase.co` and log what it says, then tell
> the project lead. Switching to the IPv4 pooler will not help a paused project.
> If you have PostgreSQL installed and want to keep testing meanwhile, the recipe
> for a private local database is in `CLAUDE.md` → Gotchas.

**Walk the developer through this, one step at a time, and have them show
you the actual terminal output at each step — don't move on until you've
seen it:**

1. Confirm the database is reachable:
   `curl http://127.0.0.1:8010/readyz` — this must return 200 with the API
   running. If it doesn't, stop here and troubleshoot the connection first
   (see gotchas). Log the result either way in TEST-LOG.md.
2. Apply the migration:
   ```
   cd api
   export DATABASE_URL_MIGRATE="$(grep '^DATABASE_URL_MIGRATE=' .env | cut -d= -f2-)"
   .venv/Scripts/python.exe -m alembic upgrade head
   ```
   Have them paste you the full output. Confirm it mentions `0005` and ends
   without an error. Log it.
3. Run the migration-safety check, which refuses anything that could lose
   data on an upgrade:
   `.venv/Scripts/python.exe scripts/check_migration_safety.py` (run from
   the repo root). Log the result.
4. Run the rate-limit tests specifically, with output kept:
   ```
   export DATABASE_URL_APP="$(grep '^DATABASE_URL_APP=' api/.env | cut -d= -f2-)"
   cd api && .venv/Scripts/python.exe -m pytest tests/test_rate_limits.py -v
   ```
   Log every test name and its result — not just "all passed." If anything
   fails, that's an ISSUE-LOG entry, not a TEST-LOG entry (see §6) — don't
   just try things at random; work out what the test expected versus what
   happened, and write that reasoning down as you go, not just the fix at
   the end.
5. Run the full suite once more to confirm nothing else broke:
   `.venv/Scripts/python.exe -m pytest -v` from `api/`. Log it.
6. Only once all of that is green: have the developer manually trip the
   **per-address** limit. This is the one check that proves the *feature*
   works, not just that the tests pass. Log what they saw, including the
   actual response body and headers of the call that got throttled.

   **Use sign-in, and use a different phone number every time.** The
   per-address sign-in limit is 60 an hour, so send 61 wrong-password
   `POST /v1/sessions` calls from one machine, each with a *different*
   made-up phone number: the first 60 should each be `401`, and the 61st
   should be `429` with a `Retry-After` header and a message that says how
   long to wait and nothing else. Different phones matter — if they reuse one,
   the *account* locks first and they will have tested the old per-account
   limit by mistake. (An earlier version of this step said to hit
   `/v1/phone/code` six or seven times; that only trips the older per-phone
   limit of 5 codes a day and would have looked like a pass while proving
   nothing about the new feature.) If the developer wants to see it without
   sending 61 requests, `tests/test_rate_limits.py` lowers the limit to 3 —
   that is the same code path, and it is what step 4 already ran.

If all six steps are clean, update the "Not verified" line about rate
limits in `CLAUDE.md`'s Status section to say it's confirmed, with the date
and who ran it. Do not just delete the caveat — replace it with what was
actually proven and how.

## 6. How to log things

### Every test run → `docs/TEST-LOG.md`
Short and mechanical. One entry per run, in the format already at the top
of that file. This includes clean passing runs — a log with only failures
in it hides how often things actually pass.

### Anything that took more than one attempt → `docs/ISSUE-LOG.md`
This is the one that matters most for "how did the developer and the agent
get to that answer." Write it like you're explaining it to someone who
wasn't there: what was tried, what was actually observed (paste real
output, don't paraphrase it), what that ruled in or out, and what finally
worked or where it was left. If you and the developer went back and forth
several times before finding the cause, that back-and-forth is exactly what
belongs in the entry — not just the final one-line fix.

### Don't log
Routine commands that produced the expected result on the first try and
weren't a test (e.g. starting the dev server, checking `git status`).
Use judgment — if in doubt, a short TEST-LOG line costs nothing.

## 7. Understanding the developer, for the project lead

Alongside coaching, the project lead wants to know how the developer is
doing: how much they actually understand versus are typing on trust, how
independently they can work, how carefully they verify things before
calling them done. Keep notes on this in
[`docs/DEVELOPER-PROGRESS.md`](./DEVELOPER-PROGRESS.md) as you go.

**This file lives in the same repo the developer is working in — assume
they can read it, and write every entry as if they will.** That's a
deliberate choice, not an oversight: an assessment nobody would say to the
person's face isn't a fair one, and writing with that in mind keeps it
useful instead of a running score.

Base every note on something the developer actually did or said, not a
general impression:

- **Grasp** — after you explain something (say, why `web/` never holds a
  database credential), can they later explain it back in their own words,
  or apply it, or do they just do what the last message said? A developer
  who asks "wait, why does it matter which role the API uses" understood
  something a developer who silently copy-pastes the command did not.
- **Independence** — do they try something themselves and report what
  happened, or ask what to type at each step? Both are fine early on; what
  matters is whether the second one is still happening after several
  sessions.
- **Rigor** — do they read the actual output before saying a step worked,
  or report "should be fine" without having run it? This is the single
  most useful thing to track, because it's the difference between someone
  who will catch their own mistakes later and someone who won't.
- **Communication** — when something fails, do they describe what actually
  happened, or only that "it didn't work"? Accurate reporting of a failure
  is itself a skill worth noting.

Describe behaviour, not character — "took two attempts to find the missing
migration; the second attempt used `alembic history` unprompted to check
what was actually applied, which was the right instinct" is useful. "Not
very sharp" is not, and it wouldn't be fair to write about someone without
being willing to say it to them. Keep a short running summary at the top of
`DEVELOPER-PROGRESS.md`, same pattern as the other two logs, so the project
lead can read the current state in a few lines without opening every entry.

## 8. Known problems you will hit (save time — these are already understood)

- **Port 8000 is taken by a different project on this machine** (a Django
  app, unrelated to KAFRIADA). The API uses 8010. If something is already
  listening on 8010 and it isn't ours, don't kill it before checking what
  it is.
- **`scripts/dev.sh` does not work right now** — sourcing `api/.env`
  strips the quotes off `TRUSTED_HOSTS=["*"]` and the API fails to boot.
  Start each tier directly as shown in §4 until this is fixed.
- **The Supabase connection drops intermittently** — DNS failures,
  timeouts. This is a known, pre-existing flakiness on this network, not a
  sign the database itself is broken. Retry two or three times before
  concluding something is actually wrong, and say so in the log rather than
  guessing at a code-level cause.
- **`next start` must be stopped before `npm run build`** — otherwise it
  goes on serving old, already-deleted CSS files, and the developer will
  see stale styling and think their change didn't apply.
- **A wrong one-time code has to be counted in its own database
  transaction**, separate from the request that failed — otherwise the
  rollback undoes the attempt counter along with everything else, and five
  allowed guesses silently becomes unlimited. There's already a test for
  this (`_spend_code`); if the developer is touching the OTP code, point
  them at it before they change anything nearby.
- **The API does not hot-reload.** A code change needs the process
  restarted.

## 9. Reporting back to the project lead

At natural stopping points — end of a session, end of a task, or if
something is genuinely stuck — leave a short status note at the very top of
`docs/TEST-LOG.md`, above the log entries: what was attempted, what's
confirmed working now, and what's still open. Keep it to a few lines; the
detail lives in the entries below it. Do the same for the summary at the
top of `docs/DEVELOPER-PROGRESS.md` if there's anything new worth saying
about how the developer is doing. The project lead reads both notes first
and only opens the entries below if they want the detail.
