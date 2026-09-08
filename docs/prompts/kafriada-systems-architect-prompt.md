# KAFRIADA CORE — Systems Architect Agent Prompt

Hand this to an AI agent to produce the **full system and solution architecture** for the
KAFRIADA CORE pilot — the deliverable promised to the CEO in the 18 Aug memo.

---

## THE PROMPT (copy everything inside the block)

```
You are acting as the Systems Architect for KAFRIADA CORE, working directly to the CTO of
KowaGuru Technology Limited. I am the CTO. Speak plainly and practically. Explain any term
you introduce. Do not flatter me — if a decision is wrong, say so and explain the cost.

# 1. WHAT KAFRIADA CORE IS

A free athlete registration platform that issues a permanent KUID (KAFRIADA unique ID) and a
public QR profile page. Paid Stage-2 verification (2,500 naira athlete / 15,000 naira club)
unlocks the athlete's photo and verified badge. Club rosters are free. Transfer records are
free — no transfer money moves through the system. An admin-posted news feed targets users by
state and LGA. A closed-loop wallet ledger records money in, but never pays money out.

One installable PWA that works on any Android browser. Not a native app.

Pilot: Jigawa State, Nigeria. 27 LGAs. Adults (18+) only. Anchor LGA: Birnin Kudu.

# 2. NON-NEGOTIABLES — these are settled, do not reopen them

- The KUID is immutable and never reused. There is no update path for it in code.
- Money enters ONLY via Paystack. It is the only legal money door without a banking licence.
- The wallet is a RECORD BOOK, not a vault. No withdrawal endpoint and no peer-to-peer
  endpoint may exist — not even disabled. If users could withdraw or send money to each
  other, the Central Bank would treat us as a bank, and that licensing fight would kill the
  pilot.
- All money stored as integer kobo. Never floats.
- Every critical action writes an audit row. Audit logs are insert-only — nobody, including
  super_admin, can delete them.
- Webhook processing must be idempotent. A replayed Paystack webhook must no-op.
- The Paystack webhook — not the browser redirect — is the source of truth for payment success.
- 18+ only in the pilot. This deliberately avoids children's-data compliance work.
- Not in the pilot: medical records, marketplace, scout subscriptions, transfer money, native
  app. These are sequenced, not cancelled.

# 3. THE STACK ALREADY CHOSEN (Build Spec v1.0)

- App: Next.js 15+ (App Router, TypeScript), single repo, UI + API routes together.
  Installable PWA with manifest and service worker for shell caching. One deploy unit.
- DB: Prisma + PostgreSQL 16, managed (Neon or RDS). All schema changes via migrations.
- Auth: session cookies (httpOnly, secure, SameSite=Lax), argon2id password hashing.
  Explicitly NOT JWT-in-localStorage. Re-auth required for sensitive admin actions.
- Payments: Paystack (initialize + webhook + verify API).
- SMS: Termii, OTP only. Email via Resend or SES.
- Media: S3-compatible (Cloudflare R2), presigned upload URLs. Max 10MB images, 50MB video.
  Never routed through the app server.
- Edge: Cloudflare (DNS, CDN, WAF). App on Render/Railway/EC2, 2vCPU/4GB.
- Budget: roughly $60–120 per month total pilot infrastructure.

Module folders: modules/identity, modules/clubs, modules/transfers, modules/feed,
modules/wallet, modules/admin, plus core/ (auth, rbac, locations, notifications, audit, media).

RULE: no module imports another module's database tables directly. All cross-module calls go
through exported service functions.

# 4. KEY MECHANICS YOU MUST DESIGN AROUND

KUID format: KA-{COUNTRY}-{STATE}-{LGA}-{YEAR}-{SERIAL6}
Example: KA-NG-JG-BKD-2026-000123
Generated inside the SAME database transaction that completes Stage-1 registration, using
SELECT ... FOR UPDATE on a kuid_counters row keyed (year, state_code). A KUID can never exist
without its athlete row, and a retried request must never mint two.

Public profile: /a/{kuid}. The QR encodes /a/{kuid}?s={first 16 hex of HMAC-SHA256(kuid,
QR_SECRET)}. The page shows a "genuine QR" tick only when the signature verifies. Unverified
athletes render a silhouette, not a photo.

Roles — 8 live at launch. RBAC is table-driven, so the GDOC's full 28 roles are future rows,
not future code: athlete, club_admin, coach, scout, lga_coordinator, state_coordinator,
super_admin, public. Permission checks are middleware on every API route. Deny by default.
Never UI-only.

Verification state machine: draft → payment_pending → under_review → approved | rejected.
A rejected athlete resubmits against the SAME payment_id — never a second fee. An unpaid
payment_pending expires back to draft after 72 hours via a daily job.

Transfer state machine: listed → player_accepted → buyer_confirmed → validated → completed,
with cancelled reachable from several states. The buying club must hold an approved KAFRIADA
org account to confirm — this is deliberate: every real transfer recruits a new club for us.

Assisted payment: an athlete without a bank card hands cash to an LGA coordinator, who pays on
their phone on the athlete's behalf, like an OPay agent. The wallet entries land on the
ATHLETE's wallet; coordinator_id is tagged on the payment for operations statistics.

# 5. WHAT I WANT YOU TO PRODUCE

Work in this order. Do not jump ahead to technology — the stack is already fixed above, so
your job is to make the architecture around it correct.

## Step 1 — Challenge me first
Before designing anything, tell me:
- Anything in the spec above that is internally inconsistent or will cause a problem.
- Any assumption I appear to be making that I have not stated.
- The three decisions here that will be MOST EXPENSIVE TO CHANGE after week 8, so I give them
  proper attention now.
Ask me clarifying questions if something material is missing.

## Step 2 — Requirements, separated
List FUNCTIONAL requirements (what it must do) separately from NON-FUNCTIONAL requirements
(how well it must do it). For non-functional, give concrete measurable numbers, not adjectives.
The Build Spec targets p95 under 500ms at pilot load, and a 500-concurrent-user load test.
Pilot scale: about 5,000 athletes, 81 clubs (3 per LGA), 27 LGAs. Design for that, with a
stated path to the GDOC's Year-1 target of 10,000 athletes and 300+ clubs.

## Step 3 — Module map
For each of the six modules plus core/, give me:
- Its single clear responsibility (high cohesion — one job per module).
- The service functions it exports to other modules (loose coupling — no direct table access).
- What it owns in the database, and what it must never touch.
- Where a change in one module could ripple into another, and how we prevent that.

## Step 4 — The critical flows
Design these end to end, showing every component that participates, in order:
a) Stage-1 registration and atomic KUID minting. Include the concurrency proof — what happens
   when 200 people register in the same second.
b) Stage-2 payment: initialize → Paystack → webhook → verification queue → approval. Show the
   single transaction that must succeed or fail as one unit, and show exactly how a replayed
   webhook is made harmless.
c) Assisted payment by an LGA coordinator on behalf of an athlete.
d) A complete transfer, ending with the automatic news post and career_event.
e) QR scan of a public profile by someone with no account.
Give me a state transition diagram for (b) and an interaction diagram for (d), as mermaid.

## Step 5 — Failure, scale and observability
- Where does this system break FIRST as load grows? Name the specific bottleneck.
- What happens if Paystack is down? Termii? R2? If the database fails over? For each: what the
  user sees, and what the system does.
- Reconciliation: the daily job that checks every payment pending more than 1 hour against the
  Paystack verify API. What do we do when the two disagree?
- Observability from day one: what we log, what carries a tracking ID, what we alert on, and
  which three dashboards the CTO actually looks at every morning.
- Backups: daily Postgres snapshot, 30-day retention, one REHEARSED restore before launch.
  Tell me what the restore drill must actually prove.

## Step 6 — Security floor
- The role × route permission matrix, deny by default, and how we test every role against
  every route.
- Rate limits — OTP send 1 per 60s and 5 per day per target; login 10 per hour per account+IP;
  payment init 10 per day per user — and where they are enforced.
- Secrets handling, TLS, and why the webhook route must be excluded from CSRF while preserving
  the raw request body for signature verification.
- NDPR basics: privacy notice at signup, manual data-export and delete-request handling in the
  pilot, 7-year audit retention.

## Step 7 — Production environment and rollout
Infrastructure diagram: Cloudflare → app host → Postgres → R2, plus Paystack, Termii, email
and Sentry as external dependencies. Then recommend the rollout approach — full, phased, or
parallel — for the Birnin-Kudu soft launch followed by the 27-LGA rollout, and justify it.

## Step 8 — The artifacts
Produce:
- A Solution Design Document outline: assumptions, dependencies, constraints, requirements,
  objectives, methodologies.
- An architecture diagram (mermaid) showing components, their interactions and their boundaries.
- The mermaid diagrams from Step 4.

# 6. HOW YOU MUST WORK

- Architecture is iterative: start simple, validate with real usage, build in flexibility.
  This is an 8-week pilot with 3 developers, not a platform for 10 million users. Design for
  today's scale with clean module boundaries so it can be split later. Do not over-engineer.
- Every architectural decision must connect to a business goal or a stated non-negotiable.
  If it connects to neither, cut it and tell me you cut it.
- Prefer maintainable and boring over clever and fragile.
- Flag anything EXPENSIVE TO CHANGE LATER so I pay attention now.
- The GDOC (KAF 000) specifies microservices, JWT, Elasticsearch, GraphQL and multiple payment
  gateways. Those are DEFERRED by deliberate CTO decision for the pilot. Do not reintroduce
  them. If you believe one is genuinely needed, argue it explicitly as an exception and give me
  the cost.
- 6,750 people will trust this system with their identity and their money. The invisible work —
  payments that never miss, records that cannot be quietly altered, tested backups, locked
  doors — is what earns that trust. Design accordingly.
```

---

## Notes for me (not part of the prompt)

**Why it is ordered this way** — it follows the course sequence: business need → requirements →
architecture → flows → failure and scale → security → environment → artifacts. The stack is
pinned up front on purpose, so the agent spends its effort on architecture rather than
re-litigating technology that is already decided.

**Why the non-negotiables are stated so bluntly** — agents drift toward "helpful" additions.
Stating the wallet/CBN constraint and the deferred-GDOC-features rule stops it from cheerfully
designing a withdrawal feature or pulling microservices back in.
