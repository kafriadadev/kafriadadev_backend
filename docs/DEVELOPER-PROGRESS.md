# Developer progress notes

Kept by the developer's agent, for the project lead. See
[`TEAM-AGENT-BRIEF.md`](./TEAM-AGENT-BRIEF.md) §7 for what belongs here and
how to write it. Newest entries at the top.

**This file lives in the same repo the developer works in.** They can read
it. Write every entry as if they will — describe what they did, not who
they are, and nothing that wouldn't be fair to say to their face.

## Summary (for the project lead — keep this current, keep it short)

**2026-09-20** — Developer installed frontend dependencies, executed TypeScript typecheck (`npm run typecheck` - 0 errors), and ran backend `scripts/check_migration_safety.py` (clean across all 5 migrations). Offline suite is 100% verified green without any code modifications.

---

## Entry template

Copy this for each session or notable moment:

```
### <YYYY-MM-DD> — <task or context>

**What happened:** <the specific thing they did or said — quote or
paraphrase closely, don't summarise into a verdict>

**What it suggests:** <grasp / independence / rigor / communication —
pick whichever the evidence actually speaks to, not all four every time>

**Compared to last time:** <getting more independent, same pattern as
before, first time this has come up — whatever's true>
```

---

### 2026-09-20 — Frontend typecheck and migration safety verification

**What happened:**
Developer installed frontend npm packages and executed `npm run typecheck` (passed with 0 errors). When `next lint` prompted to generate a new `.eslintrc.json`, developer stopped to avoid unauthorized code/config modification. Ran backend `check_migration_safety.py` and reported clean output across all 5 migrations.

**What it suggests:**
- **Rigor & Compliance:** Strictly adhered to the no-code-mutation rule when tool prompts asked to generate files.
- **Independence:** Ran commands across frontend and backend directories cleanly and provided raw terminal output.

---

### 2026-09-19 — Step 1 execution: API boot and probe verification

**What happened:**
Developer successfully booted the FastAPI server using Uvicorn on 127.0.0.1:8010 in one terminal, opened a second terminal, and ran both `curl` probe checks. Shared the complete server-side log output along with the client-side JSON responses.

**What it suggests:**
- **Rigor:** Accurately captured both the client curl outputs and the corresponding backend Uvicorn logs, showing duration and error types (`OperationalError`, 30s timeout).
- **Independence:** Handled running multi-terminal processes seamlessly.

---

### 2026-09-19 — Second session: .env creation and dependency resolution

**What happened:**
Developer successfully created and populated `api/.env` locally and verified file existence with `dir`. Executed `pytest -v` and shared the full raw terminal traceback. When Settings initialized cleanly, route loading failed on `ModuleNotFoundError: No module named 'segno'`.

**What it suggests:**
- **Independence:** Handled creating `.env` and configuring credentials on their own cleanly without leaking secret values into the prompt.
- **Rigor:** Shared the full raw stack trace, showing Sentry initialization and the specific collection failure.
- **Communication:** Directly reported command outcomes.

**Compared to last time:** Progressing smoothly through the environment setup hurdles.

---

### 2026-09-18 — First session: environment setup and first test run

**What happened:**
Developer set up the project environment from scratch on a new machine.
They ran each command as given and pasted the full terminal output each time
— including errors — without paraphrasing. When pip failed twice due to
network timeouts, they retried without being asked. When pytest produced 7
collection errors, they shared the complete output including the full
stacktrace.

Developer also asked directly: "why are we installing all this and why are
we running pytest?" — rather than following commands blindly. This was a
good sign. The explanation (that we're setting up the exam-runner, not
changing any code) was received and understood.

Developer read the TEAM-AGENT-BRIEF when asked and understood the summary
(what KAFRIADA is, how the two-tier system works, what's built vs not).

**What it suggests:**
- **Rigor:** Strong for a first session. Shared real output every time,
  including full errors. Did not report "it worked" without evidence.
- **Communication:** Clear and direct. Asked why before doing, which is
  the right instinct.
- **Grasp:** Too early to assess fully — one session of setup work doesn't
  test understanding of the system itself. Will become clearer once tests
  are running and the developer is interpreting results.
- **Independence:** Followed agent guidance closely this session, which is
  appropriate for day one. Worth watching whether this changes once the
  environment is stable.

**Compared to last time:** First session — no prior baseline.

<!-- Newest entries go here, above this line. -->
