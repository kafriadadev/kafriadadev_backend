# KAFRIADA CORE — Blueprint Prompts for Claude Design

Two prompts, two deliverables.

- **Prompt A** → the written blueprint. The build spec developers work from.
- **Prompt B** → the visual canvas. The board-and-stakeholder view of the same thing.

Run A first. B refers back to it.

**Settings chosen (25 Aug 2026):**
Scope = pilot in full, Phase-2 seams marked · Depth = architectural (tables, columns, endpoints, flows — *not* literal DDL or code) · Open decisions = my recommendations carried as flagged assumptions.

**Source documents to attach when you run these:**
`KAFRIADA-CORE-Target-Architecture.pdf` · `KAFRIADA-CORE-Architecture-DraftV1.pdf` · `Kaf 0100 Doc.pdf` (GDOC) · `KAFRIADA-Pilot-Build-Spec.pdf`

Both prompts are written to stand alone if the attachments are missing.

---

# PROMPT A — The written blueprint

Copy everything between the markers.

````
=============================== START OF PROMPT A ===============================

You are the Lead Solution Architect producing the definitive technical blueprint for
KAFRIADA CORE. You report to the CTO of KowaGuru Technology Limited. I am the CTO.

Write plainly. Explain every term you introduce, once, the first time it appears. Do not
flatter me. If something in this brief is wrong or internally inconsistent, say so and
explain what it will cost — but say it in Step 0, not scattered through the document.

This blueprint is the document three developers build from for eight weeks, and the
document a new engineer is handed in month six. It must be complete enough that nobody
has to ask a question that this document could have answered. Length is not a constraint.
Take the space the work needs — one hundred pages is fine, two hundred is fine. Thin is
the only failure mode.

--------------------------------------------------------------------------------
1. WHAT KAFRIADA CORE IS
--------------------------------------------------------------------------------

KAFRIADA CORE is an identity authority for African sport that also holds other people's
money. Both halves of that sentence matter and they drive every decision below.

It issues every registered athlete a permanent, never-reused identifier — the KUID — and
publishes a public profile page reachable by scanning a printed QR code. Registration is
free. Paid Stage-2 verification unlocks the athlete's photograph and a verified badge:
2,500 naira for an athlete, 15,000 naira for a club. Club rosters are free. Transfer
records are free and no transfer money ever moves through the system. An admin-authored
news feed targets users by state and LGA. A closed-loop wallet ledger records money
arriving and has no mechanism for money leaving.

Delivered as one installable PWA that works on any Android browser. Not a native app.

Pilot: Jigawa State, Nigeria. 27 LGAs. Adults 18 and over only. Anchor LGA: Birnin Kudu.
Pilot gate: 5,000 registrations, 4% paid conversion, 81 active clubs, verification decided
inside 24 hours.

--------------------------------------------------------------------------------
2. NON-NEGOTIABLES — settled, do not reopen, do not soften
--------------------------------------------------------------------------------

- The KUID is immutable and never reused. There is no update path for it anywhere in the
  design. Format: KA-{COUNTRY}-{STATE}-{LGA}-{YEAR}-{SERIAL6}, e.g. KA-NG-JG-BKD-2026-000123.
  Uniqueness is (state, year, serial). The LGA segment is informational — it records place
  of registration, not residence, and the public profile must say so in plain words.
- Money enters ONLY via Paystack. It is the only legal money door without a banking licence.
- The wallet is a RECORD BOOK, not a vault. No withdrawal endpoint and no peer-to-peer
  endpoint may exist — not disabled, not feature-flagged, ABSENT. If users could withdraw
  or send money to each other, the Central Bank of Nigeria would treat us as a bank, and
  that licensing fight would end the pilot.
- All money is stored as integer kobo. Never floats. Anywhere.
- Every critical action writes an audit row. Audit rows are insert-only and this is
  enforced by database grants, not by application code — no role in the system, including
  the one super_admin acts through, holds DELETE or UPDATE on the audit table.
- Webhook processing is idempotent. A replayed Paystack webhook must change nothing.
- The Paystack webhook — not the browser redirect — is the source of truth for payment
  success.
- 18+ only in the pilot. This deliberately avoids children's-data compliance work.
- Every critical flow must work as server-rendered HTML with plain form POSTs. JavaScript
  is enhancement, never a dependency. Opera Mini in proxy mode is common in northern
  Nigeria: it has no service worker and severely limited JavaScript. First-load JavaScript
  budget: 150KB gzipped.

--------------------------------------------------------------------------------
3. THE ARCHITECTURE YOU ARE DOCUMENTING — decided, not up for redesign
--------------------------------------------------------------------------------

Your job is to document, complete, and make buildable the architecture below. You are not
choosing it. If you believe a specific part of it is wrong, raise it in Step 0 as a single
named exception with a cost, then proceed with what I decide.

FOUR TIERS

  Edge          Cloudflare — DNS, WAF, CDN, Lagos PoP. Caches the anonymous read surface
                for 60 seconds. Cache key includes the query string.

  Presentation  Next.js 15 App Router, TypeScript. Acts as a Backend-For-Frontend. Server
                components and server actions. Holds NO business logic and NO database
                credential. The browser talks only to this origin.

  Domain        FastAPI, Python 3.12, SQLAlchemy 2.0 + Alembic, Pydantic v2. A modular
                monolith. Holds every business rule, every state machine, every
                authorisation decision, and the only database credentials. Reached by the
                presentation tier server-side over a private network. NOT internet-
                reachable except for two surfaces: the anonymous public read endpoints,
                and the Paystack webhook.

  Work          Same image as the domain tier, no HTTP surface. Outbox consumer plus
                scheduler. Runs everything asynchronous and everything CPU-heavy.

  Data          PostgreSQL 16, primary plus streaming replica, point-in-time recovery.
                Three schemas: identity, money, ops. Cloudflare R2, private bucket,
                presigned in and out. Redis for rate limiting and the idempotency cache
                only — NOT as a job broker.

  Region        Frankfurt (eu-central). App tiers and primary database in one availability
                zone. Nigeria to Frankfurt is roughly 90-130ms.

ELEVEN BOUNDED CONTEXTS

  identity      (schema identity) Who is this person, and what is their permanent number?
                Athletes, KUID counter, career history. Sole authority on KUID minting.
  verification  (schema identity) Is this claim substantiated, by whom, and does that
                decision still stand? Cases, submissions, reviewer decisions, revocations,
                resubmission counter.
  clubs         (schema identity) Who plays for whom, right now? Clubs, rosters,
                org-account status. Invariant: at most one open membership per athlete,
                enforced by a partial unique index.
  transfers     (schema identity) How did an athlete move, and who agreed? The transfer
                state machine and its evidence trail. Moves no money, ever.
  ledger        (schema money)    What money has this system ever seen? Wallets,
                insert-only entries in integer kobo.
  payments      (schema money)    What did a provider tell us, and have we acted on it
                exactly once? Payment intents, provider events, idempotency keys,
                reconciliation state. The only context that talks to Paystack.
  access        (schema ops)      Who is this caller and what may they do, to what? Users,
                credentials, sessions, roles, permissions, and SCOPE.
  geography     (schema ops)      Where is this, and is it live? States, LGAs, rollout flags.
  feed          (schema ops)      What should this person be told about? Posts and targeting.
  media         (schema ops)      Where does this file live and who may see it? Asset
                records, presign issuance, derivative state. Enforces the photo paywall.
  audit         (schema ops)      What happened, who did it, when? Insert-only.

  RULES BETWEEN CONTEXTS
  - Each context exposes one application service with typed inputs and outputs. Nothing
    else in it is importable. Enforced by an import-linter contract in CI.
  - No context reads another's tables. Cross-context reads go through the service.
    Cross-context writes pass an explicit unit of work so they join the caller's transaction.
  - Dependencies point one way. access, geography and audit are depended on and depend on
    nothing. ledger depends on nothing but audit.
  - payments may call verification to advance a case on confirmed money. verification may
    NEVER call payments to ask whether something was paid — it is told, once, and records
    the fact. One direction only, so there is exactly one definition of "paid".

FIVE MECHANISMS THAT CARRY THE SYSTEM — document each one fully

  1. CONTRACT-FIRST. Pydantic models generate OpenAPI 3.1. A typed TypeScript client is
     generated from it into the presentation tier. Three CI gates: the committed OpenAPI
     document must match the generated one; a breaking change to a /v1/ schema fails the
     build without an explicit version-bump marker; the presentation tier compiles against
     the generated client. These gates are load-bearing, not decoration.

  2. TRANSACTIONAL OUTBOX. Records are transactional; announcements are eventual. The same
     transaction that writes a domain record writes an outbox row. Workers consume with
     SELECT ... FOR UPDATE SKIP LOCKED. No message broker — a broker cannot join a database
     transaction, which is how you get a record with no announcement or an announcement
     with no record.

  3. LEAST PRIVILEGE ENFORCED BY POSTGRES. Four roles chosen by code path:
       kaf_app      ordinary domain routes. Read/write identity and ops. SELECT only on
                    money. No DELETE on audit.
       kaf_money    payment confirmation and reconciliation only. INSERT on
                    money.ledger_entries, UPDATE on money.payments, plus what it needs in
                    identity to advance a verification case.
       kaf_reader   public read surface, Metabase, analytics. SELECT only, replica only.
       kaf_migrate  release step only. DDL. Never held by a running process.
     No role anywhere holds DELETE or UPDATE on ops.audit_log or money.ledger_entries.

  4. IDEMPOTENCY AS AN API PRIMITIVE. Every mutating endpoint accepts an Idempotency-Key.
     Key, request fingerprint and response are stored; a replay returns the original
     response without re-executing. A key reused with a different body is a 422. The
     Paystack webhook is then just one more idempotent endpoint.

  5. TRACEABILITY. OpenTelemetry from edge through Next.js into FastAPI down to the SQL
     statement and out to the worker processing the resulting outbox row. One trace ID per
     request, surfaced on user-facing error screens and stamped into every audit row
     written during that request.

--------------------------------------------------------------------------------
4. CORRECTIONS ALREADY MADE — these must survive into the blueprint intact
--------------------------------------------------------------------------------

These came out of a prior architecture review. Every one is a decision, not a suggestion.
If any of them is absent from your blueprint, the blueprint is wrong.

 1. argon2id password hashing happens OUTSIDE the KUID minting transaction. Never do CPU
    work inside a lock. With hashing inside, the registration ceiling is ~4/second; with it
    outside, ~330-1,000/second.
 2. The KUID counter uses ONE atomic statement, not a read-modify-write:
    INSERT INTO kuid_counters (year, state_code, next_serial) VALUES (...)
    ON CONFLICT (year, state_code) DO UPDATE SET next_serial = kuid_counters.next_serial + 1
    RETURNING next_serial
    It is the second-to-last statement in the transaction, so the row lock is held ~2ms.
 3. A counter row is used, not a Postgres sequence, deliberately: sequences do not lock but
    they leave GAPS, and an unexplainable gap in a public identity number destroys trust in
    a register in its first month. Document this trade-off.
 4. The identity anchor is the PHONE NUMBER. One verified phone, one KUID, enforced by a
    unique constraint in the database. Changing a phone is an admin action with a reason and
    an audit row. NIN is Phase 2.
 5. The verification state machine needs two states the original spec lacked:
    revoked (from approved; super_admin only; mandatory reason; no refund; profile shows
    "verification withdrawn") and escalated (after a third rejection).
 6. Resubmission against the same payment is capped at THREE, then escalates. Uncapped, it
    is an infinite free-review coupon.
 7. A confirmed payment ALWAYS wins over expiry, whatever state the record is in and
    whatever hour the webhook lands. Expiry may only touch records with no successful charge.
 8. Refunds exist and must be representable. They are initiated by a human in Paystack's own
    dashboard, never by the application. The system only RECORDS the reversal, as a debit
    ledger line created by a super_admin action with a mandatory reason. No endpoint moves
    money; one endpoint records that money moved elsewhere.
 9. Paystack's fee (roughly 1.5% + 100 naira on local cards) is recorded as a SEPARATE
    ledger line from the gross. Without this the books never reconcile to the bank statement.
10. The R2 bucket is PRIVATE. Uploads go direct via presigned PUT; reads go through
    short-lived presigned GET issued only after a permission check. Every image is
    re-encoded by the worker into a derivative with EXIF (and therefore GPS) stripped; the
    derivative is what is served; the original is never public. Without this the photo
    paywall is bypassable by anyone who obtains an object URL.
11. The QR signature carries a KEY VERSION: ?s=1.a1b2c3... so QR_SECRET can be rotated
    without invalidating every printed card at once. The signature proves "this QR was
    issued by KAFRIADA" — it does NOT prove the bearer is the person shown, because a
    copied URL keeps a valid signature. The page must say so in plain words.
12. Assisted payment (an LGA coordinator paying with their own card for an athlete who hands
    over cash) needs: ledger entries landing on the ATHLETE's wallet with coordinator_id
    tagged on the payment; an SMS receipt to the ATHLETE's phone at webhook confirmation
    carrying KUID, amount, timestamp and coordinator name; hard per-coordinator daily caps
    on both count and naira; and a settlement report. Architecture cannot stop a coordinator
    keeping cash — it can make it visible and bounded.
13. A reviewer may not approve their own record, nor an athlete of a club they administer.
    Enforced in the domain service, not in the UI.
14. A transfer whose buying club is not yet an approved org needs a visible state
    (awaiting_buyer_onboarding), a nudge, and an expiry. Otherwise transfers die silently.
15. Sessions: 30-minute idle timeout for staff roles (coordinators share phones), 30 days
    for athletes.
16. Reconciliation runs HOURLY, not daily, against Paystack's verify API for any payment
    pending more than an hour. It shares the exact code path the webhook uses. It may only
    ever CONFIRM a credit — it may never reverse, refund, debit or cancel. An amount
    mismatch is never auto-resolved: freeze, alert, a human decides.
17. A nightly integrity job asserts: every wallet's credits minus debits equals its cached
    balance; every athlete has exactly one KUID; no KUID appears twice; every media asset
    row points at an object that exists in R2. Any failure pages immediately.
18. The restore drill must prove eight things, including that the ledger balances in the
    restored database, that R2 and the database still agree, that the wall-clock time was
    written down (that number IS the RTO), and that the runbook was followed by someone who
    did not write it.
19. NDPR: consent is RECORDED as a row with the notice version and timestamp, not merely
    displayed. "Deletion" means anonymisation, because audit rows and financial records
    cannot be deleted and the KUID is immutable — and the privacy notice must say this in
    plain words up front. NDPR filing obligations begin above 2,000 data subjects in twelve
    months, and the pilot target of 5,000 crosses that threshold.
20. Rollout is phased by LGA behind a locations.is_live flag, so a wave opens or closes
    without a deploy.

--------------------------------------------------------------------------------
5. ASSUMPTIONS IN FORCE — carry each one visibly, do not silently absorb them
--------------------------------------------------------------------------------

Seven questions are commercially open. Build on the stated answer, and mark each occurrence
in the blueprint with an "ASSUMPTION" flag stating the cost of being wrong. Collect all
seven in a single register in the appendix.

  A1  2,500 naira is the PRICE, not the take-home. Roughly 2,362 naira reaches the account.
      If the revenue model assumes 2,500 net, the price becomes 2,640 and all printed
      material changes.
  A2  NIN is NOT collected in the pilot. Phone number is the identity anchor. Collecting NIN
      unverified would carry the compliance duty with none of the benefit.
  A3  Verification is decided by LGA coordinators within their own LGA, escalating to state.
      Conflict rule as correction 13.
  A4  Refunds are rare and manual, per correction 8.
  A5  The ledger is separated by SCHEMA AND DATABASE ROLE in the pilot, not extracted as a
      separate service. The seam is maintained so extraction later is a two-week job. Cost of
      being wrong: extracting it during the pilot would force a saga on payment confirmation.
  A6  The anonymous public read surface IS part of the versioned /v1/ contract from launch.
      This is what makes KAFRIADA infrastructure rather than an app.
  A7  NDPR filing is an unowned budget line. Flag it in the risk register with no assignee.

--------------------------------------------------------------------------------
6. DEPTH — read this twice, it is the most misread instruction in this brief
--------------------------------------------------------------------------------

Write at ARCHITECTURAL depth. Complete in coverage, precise in specification, and free of
implementation code.

  DO specify:
  - Every table: name, schema, purpose, every column with its type, nullability, default and
    meaning, primary key, foreign keys, unique constraints, check constraints, indexes and
    why each index exists, and its retention rule. Present as structured tables plus a
    full entity-relationship diagram.
  - Every API endpoint: method, path, which tier may call it, required permission and scope,
    request fields with types and validation rules, response fields with types, every error
    code and what causes it, whether it takes an Idempotency-Key, its rate limit, and
    whether it is cacheable.
  - Every application service operation each context exposes: name, inputs, outputs, side
    effects, which contexts may call it, whether it accepts a unit of work.
  - Every state machine: states, transitions, the actor and guard for each, side effects on
    entry, and explicitly which transitions are ILLEGAL.
  - Every flow end to end, as a numbered sequence naming every participating component in
    order, with the transaction boundary marked and the failure behaviour of each step.
  - Every screen: purpose, role that sees it, data it needs, actions, empty / loading /
    error states, and its no-JavaScript fallback.
  - Every background job, event type, notification message and alert.

  DO NOT write:
  - Literal SQL DDL (no CREATE TABLE statements).
  - Literal SQLAlchemy models, Pydantic classes, React components, or any application code.
  - Framework configuration files.

  ONE EXCEPTION: where the correctness of a mechanism depends on the ORDER of operations,
  give short annotated pseudo-code — because there the ordering IS the architecture, and
  prose loses it. This applies to exactly four places: the KUID mint transaction, the webhook
  idempotency path, the outbox consume loop, and the transfer completion transaction. Keep
  each under 30 lines and comment why each line is where it is.

--------------------------------------------------------------------------------
7. WHAT TO PRODUCE — the chapter list
--------------------------------------------------------------------------------

Produce all 28 chapters. Number them. Cross-reference between them by number. Where a
chapter would be empty, say so and say why rather than omitting it.

   1  Executive summary, and how to read this document
   2  Business context, objectives, and the pilot gate
   3  Scope — in, out, and deferred-with-a-named-seam
   4  Assumptions, constraints, and external dependencies
   5  Actors, stakeholders and roles — 8 live, the GDOC's other 20 mapped as future rows
   6  Domain model and glossary — the ubiquitous language, every term defined once
   7  Architecture overview — the four tiers, the topology, and why each boundary is where
      it is
   8  The eleven bounded contexts — responsibility, exposed operations, owned data,
      dependencies, and where a change in one ripples into another
   9  Data architecture — full ERD, every table specified, schema separation, roles and
      grants, indexes, invariants, retention
  10  API architecture — every endpoint fully specified, versioning policy, error catalogue,
      idempotency policy, pagination, the public contract
  11  State machines — verification, transfer, payment, membership, media, session
  12  Functional flows — every flow in the system, end to end. At minimum: registration;
      OTP send and verify; login, logout, password reset; profile edit; QR generation and
      bulk printing; public profile view by a stranger; club registration; club verification;
      roster invite, accept, decline, leave; transfer full lifecycle including cancellation
      and expiry; verification submit, pay, review, approve, reject, resubmit, escalate,
      revoke; assisted payment by a coordinator; the Paystack webhook; hourly reconciliation;
      72-hour expiry; feed publish, target and read; media upload, derivative, permissioned
      read; admin user and role management; data export request; anonymisation request;
      audit read; coordinator settlement; rollout flag toggle. Add any flow I have missed.
  13  Screen and UI inventory — every screen, by role, with states and no-JS fallback
  14  Security architecture — authentication, the full role-by-route permission matrix with
      scope, session policy, secrets and rotation, TLS and edge posture, CSRF and the webhook
      exemption with the raw-body rule, input validation, file upload safety, rate limits,
      and a threat model covering at least: forged webhook, replayed webhook, amount
      tampering, paywall bypass via object URL, coordinator fraud, reviewer self-approval,
      cross-tenant data access, session theft on a shared phone, and enumeration of athletes
  15  Money architecture — the ledger model, kobo discipline, entry kinds, gross versus fee,
      reconciliation, reversal recording, and a written proof that no payout path exists
  16  Asynchronous architecture — the outbox, every event type with its payload and consumers,
      every scheduled job with its schedule, idempotency and failure behaviour
  17  Notifications — every message the system sends, its channel, trigger, variables,
      deduplication key and retry policy
  18  Observability — what is logged and what must never be logged, trace propagation,
      metrics, the alert list split into page-someone and open-a-ticket, and the three
      dashboards
  19  Failure modes and resilience — a dependency-by-dependency matrix of what the user sees
      and what the system does, degraded modes, RPO and RTO, backup and the restore drill
  20  Performance and capacity — latency budgets per route group, the load model, named
      bottlenecks in the order they will be hit, and the scaling path to the Year-1 target of
      10,000 athletes and 300+ clubs
  21  Compliance and data protection — NDPR obligations, lawful basis, consent recording,
      retention schedule per data class, export and anonymisation procedures, breach response
  22  Environments, CI/CD, migration discipline, release and rollback
  23  Rollout plan — waves, numeric go/no-go gates, feature flags, and the operations runbook
      the coordinators need
  24  Testing strategy — unit, integration, contract, the generated permission matrix, load,
      the registration burst test, and the restore drill; plus acceptance criteria for every
      flow in chapter 12
  25  Operational runbooks — incident response, reconciliation mismatch, suspected coordinator
      fraud, verification revocation, database restore, secret rotation
  26  Decision log — every architectural decision as a short ADR: context, decision,
      alternatives considered, consequences, and cost to reverse. Include the decisions
      already made in sections 3 and 4 above, with their reasoning.
  27  Phase-2 seams — for each deferred feature (minors and guardian consent, NIN linkage,
      medical records, marketplace, scout subscriptions, transfer money, native app,
      multi-state and multi-country, the GDOC's remaining 20 roles) state exactly which
      table, endpoint, context or state machine it attaches to, and what in the pilot design
      makes that attachment cheap
  28  Appendices — glossary; the KUID specification; the complete permission key list; the
      event catalogue; the error catalogue; the assumption register (A1-A7); the open
      questions

--------------------------------------------------------------------------------
8. HOW TO WORK
--------------------------------------------------------------------------------

STEP 0 — before writing anything, do this and stop:
  a) Tell me anything in this brief that is internally inconsistent, or that will cause a
     problem you can see from here.
  b) Tell me what this brief assumes without saying so.
  c) Name the three things in this design that will be most expensive to change after the
     pilot ships, so I give them proper attention now.
  d) Ask me any clarifying question whose answer would change the blueprint.
  e) Propose your chapter running order if you would change mine, and say why.
  Then wait for my response before producing the document.

Then write the blueprint. While writing:

- Every architectural statement must connect to a business goal or to a stated
  non-negotiable. If it connects to neither, cut it and tell me in the decision log that
  you cut it and why.
- Prefer maintainable and boring over clever and fragile. Say so where you chose boring.
- Flag anything EXPENSIVE TO CHANGE LATER inline, visibly, so it cannot be skimmed past.
- Use mermaid for every diagram: an ERD for chapter 9, state diagrams for chapter 11,
  sequence diagrams for the flows in chapter 12, and component diagrams for chapters 7
  and 8. Diagrams must show the real mechanism, not a decorative box-and-arrow picture.
- Number everything and cross-reference by number. A reader in chapter 24 must be able to
  find the flow in chapter 12 that a test covers.
- Where two chapters would repeat each other, write it once and reference it. Repetition in
  a specification is how two versions of the truth get born.
- Write for two readers at once: a developer who needs to build it this week, and an
  engineer who joins in month six and needs to understand why.

--------------------------------------------------------------------------------
9. WHAT NOT TO DO
--------------------------------------------------------------------------------

- Do not reintroduce microservices, JWT-in-localStorage, Elasticsearch, GraphQL, a message
  broker, Kubernetes, or multiple payment gateways. Each was excluded by a deliberate CTO
  decision with a reason. If you believe one is genuinely needed, argue it in Step 0 as a
  named exception with a cost — do not simply design it in.
- Do not design a withdrawal, payout, or peer-to-peer transfer feature in any form, for any
  role, under any name, however helpful it seems.
- Do not soften the non-negotiables in section 2 into recommendations.
- Do not scale the deliverable down. If a chapter is large, write the large chapter.
- Do not fill gaps with plausible-sounding invention. Where you genuinely do not know
  something, write "OPEN:" followed by the question, and put it in the appendix register.

--------------------------------------------------------------------------------
10. THE STANDARD
--------------------------------------------------------------------------------

6,750 people will hand this system their identity and their money. The invisible work —
payments that never miss, records that cannot be quietly altered, tested backups, doors that
are locked by the database rather than by a promise in a document — is what earns that
trust. Nothing in this blueprint should be clever. Everything in it should be right.

================================ END OF PROMPT A ================================
````

---

# PROMPT B — The visual canvas

Run this after Prompt A, so the canvas summarises a blueprint that already exists.

````
=============================== START OF PROMPT B ===============================

You are the design lead producing the VISUAL BLUEPRINT for KAFRIADA CORE — a multi-artboard
design canvas that a CEO, a board member, a state sports commissioner and a new developer
can each read and understand within minutes.

This is the companion to the written blueprint. It does not replace it and it does not try
to contain it. Its job is to make the system LEGIBLE AT A GLANCE. Where the written document
is exhaustive, this is selective — but everything it does show must be exactly true to the
written blueprint.

CONTEXT — the system

KAFRIADA CORE is an identity authority for African sport that also holds other people's
money. It issues every registered athlete a permanent, never-reused number — the KUID — and
a public profile reachable by scanning a printed QR code. Registration is free. Paid Stage-2
verification (2,500 naira athlete, 15,000 naira club) unlocks the photograph and a verified
badge. Club rosters are free. Transfer records are free and no transfer money moves through
the system. A closed-loop wallet ledger records money arriving and has no way for money to
leave. Pilot: Jigawa State, Nigeria, 27 LGAs, adults only, anchor LGA Birnin Kudu. Gate:
5,000 registrations, 4% paid conversion, 81 clubs, verification inside 24 hours.

Architecture: four tiers — Cloudflare edge; Next.js 15 as a backend-for-frontend;
FastAPI modular monolith holding all business rules and the only database credentials, not
internet-reachable except for anonymous reads and the Paystack webhook; a worker tier;
PostgreSQL 16 with three schemas (identity, money, ops) and four least-privilege roles, plus
private R2 storage. Eleven bounded contexts: identity, verification, clubs, transfers,
ledger, payments, access, geography, feed, media, audit.

ARTBOARDS TO PRODUCE

  1  Title board — what KAFRIADA CORE is, in one sentence a board member repeats correctly
  2  The system in one picture — four tiers, what talks to what, where the internet stops
  3  The eleven contexts — one grid, each with its single question and what it owns
  4  Data map — the entity-relationship diagram, grouped by the three schemas, colour-coded
  5  The KUID — anatomy of the number, segment by segment, with a real example, plus what it
     does and does not mean
  6  Journey: an athlete registers — from arriving at a drive to holding a printed QR card
  7  Journey: an athlete pays for verification — initialise, Paystack, webhook, review,
     badge; showing where the truth comes from
  8  Journey: a coordinator pays for someone with cash — and every control that makes it
     visible
  9  Journey: a transfer completes — the five parties, and the club-recruitment gate
 10  Journey: a stranger scans a QR code at a match — and what the tick does and does not
     prove
 11  The money boundary — one board making it unmistakable that money can enter and cannot
     leave, and that the ledger is behind a database lock rather than a promise
 12  The two state machines — verification and transfer, as clean diagrams
 13  Who can do what — the role-by-permission grid, eight roles, deny by default, with scope
     shown as a visual property rather than a footnote
 14  Screen inventory — every screen, grouped by role, as labelled wireframe thumbnails
 15  What happens when things break — dependency by dependency: what the user sees, what the
     system does
 16  Rollout map — Jigawa's 27 LGAs, the wave sequence from Birnin Kudu outward, and the
     numeric gate between each wave
 17  Numbers that matter — the pilot gate, the latency budgets, the capacity headroom, as
     readable figures rather than prose
 18  The road after the pilot — Phase-2 features and exactly where each attaches

DESIGN DIRECTION

- The subject is a public register and an identity document. Draw on that world: record
  cards, stamps, serial numbers, index rules, official forms — not generic SaaS dashboard
  styling, and not startup-pitch gradients.
- Nigerian and Jigawa context should be present and specific — real LGA names, real KUIDs in
  the format KA-NG-JG-BKD-2026-000123, naira figures, real Hausa-belt place names — not
  placeholder content.
- Every diagram must be readable printed in monochrome at A3. This will be printed and put
  on a wall in an office in Dutse.
- Colour should carry meaning consistently across all boards: pick one hue for money, one for
  identity, one for operations, and use them the same way everywhere.
- Typography must survive being projected in a room with bad lighting. Real hierarchy, no
  body text below 14px equivalent.
- No lorem ipsum anywhere. Every label, every number, every name is real.

RULES

- Everything shown must be true to the written blueprint. If the two disagree, the written
  blueprint wins and you should tell me where the disagreement was.
- Never show a withdrawal, payout or peer-to-peer money path. It does not exist, and a
  diagram that implies otherwise is a regulatory problem, not a drawing mistake.
- Where a board would be too dense to read, split it into two boards. Legibility beats
  completeness on this deliverable — completeness is the written blueprint's job.
- Before you start, tell me which of the 18 boards you think is weakest or redundant, and
  what board you would add that I have not asked for.

================================ END OF PROMPT B ================================
````

---

## Notes for me — not part of the prompts

**Why Step 0 is in Prompt A.** Agents drift toward being helpful, which on a brief this size means inventing plausible detail to fill gaps. Forcing a challenge-and-question step before any writing surfaces the gaps while they are still cheap.

**Why the non-negotiables are stated so bluntly.** Without the explicit CBN framing, an agent will cheerfully design a withdrawal feature because a wallet "obviously" needs one. Without the explicit deferral list, the GDOC's microservices and GraphQL walk back in.

**Why the depth section is repeated and emphasised.** "Every function and every table" reads as "write the code" to most models. The DO / DO NOT / ONE EXCEPTION structure is what keeps the output a specification rather than a half-finished codebase.

**Why the four pseudo-code exceptions exist.** In the KUID mint, the webhook path, the outbox loop and transfer completion, the ORDER of operations is the architecture. Prose loses ordering; those four are where correctness lives.
