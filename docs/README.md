# KAFRIADA CORE — documentation

Everything written about this project, as PDFs you can open any time. No internet
needed, nothing to log into.

## Start here

| Read this | When you want |
| --- | --- |
| **KAFRIADA-CORE-Handbook.pdf** | **The complete record of what has actually been built** — every file, every table, every endpoint, every guarantee and how it is enforced. If you read one document, read this one. |
| **KAFRIADA-CORE-Build-Tracker.pdf** | Where the build is right now: what is done, what is next, what is blocked. |
| **KAFRIADA-CORE-Accounts-and-Keys.pdf** | Every account and credential needed to build, test and launch, with lead times and costs. Hand this to whoever does the paperwork. |

## The design

| Document | Contents |
| --- | --- |
| **KAFRIADA-CORE-Target-Architecture.pdf** | The architecture being built. Four tiers, eleven contexts, why each boundary is where it is. |
| **KAFRIADA-CORE-Wireframes.pdf** | All 46 screens drawn, each annotated with purpose, data, states and no-JavaScript behaviour. Screen codes (`PUB-01`, `VER-03`) are used in the code and commits. |
| **KAFRIADA-CORE-Build-Plan.pdf** | Four stages, what was cut and why, the paperwork that governs the launch date. |
| **KAFRIADA-CORE-Architecture-DraftV1.pdf** | Superseded by the Target Architecture, kept because its failure analysis and flow diagrams still hold. |

## The decisions behind it

| Document | Contents |
| --- | --- |
| **KAFRIADA-MVP-Recommendation.pdf** | The memo that set the pilot scope. |
| **KAFRIADA-Pilot-Plan-CEO.pdf** | The plan as presented to the CEO. |
| **KAFRIADA-Pilot-Build-Spec.pdf** | The original build specification. |
| **Kaf 0100 Doc.pdf** | KAF 000 GDOC v1.0 — the original 244-page specification. |

## For a developer joining to test what's built

| Document | Contents |
| --- | --- |
| **TEAM-AGENT-BRIEF.md** | Written for the developer's AI agent: what's actually built (not the vision — the current repo), how the system fits together, and the coaching process — one task at a time, verified with real output, everything logged. Start here if you're new. |
| **TEST-LOG.md** | Every test run, dated, with command and result. A status note at the top for a quick read. |
| **ISSUE-LOG.md** | Anything that took more than one attempt — the back-and-forth that led to the answer, not just the fix. |
| **DEVELOPER-PROGRESS.md** | How the developer's understanding is coming along, for the project lead — evidence-based, and written knowing the developer can read it too. |

## Also here

- `deploy-runbook.md` — how a release runs, how to roll one back, and what is
  still needed before staging exists.
- `decisions/` — architecture decision records. Each one states what was decided,
  what was rejected, and what would justify revisiting it.
- `prompts/` — the prompts used to produce the architecture and blueprint documents.

---

**Keeping these current.** These are generated from source and re-exported when
something changes. The Handbook is the one that goes stale fastest, because it
describes code — check its date against the latest commit before relying on it.
