# Build log

Every piece of engineering work done on KAFRIADA, in one place, newest entry
first. Not the same thing as [`TEST-LOG.md`](./TEST-LOG.md) (the developer's
test runs) or [`ISSUE-LOG.md`](./ISSUE-LOG.md) (their stuck points) — this is
the build itself: what was shipped, why it was built that way, what was
verified and how, and what is still open. `CLAUDE.md`'s Status section is the
current-state summary distilled from this; this file is the history that
summary is distilled from. `docs/TODO.md` is what's left, in order.

Never delete or rewrite an entry. If something turns out to be wrong, say so
in a new entry and link back to the old one.

## Entry template

```
## <YYYY-MM-DD> — <title>
**Commit(s):** `<hash>` [, `<hash>` ...]

**Built:** what exists now that didn't before, in plain terms.

**Why:** the decision behind it, if it wasn't the obvious choice.

**Verified:** how, specifically — which tests, against which database, what
was checked live and what the result was. Say plainly when something is
"code done, not run for real" rather than implying more than was checked.

**Not done / open:** gaps, deferred pieces, follow-ups.
```

---

## 2026-10-06 — Frontend redesign, Phase 1: the design system
**Commit(s):** see the commit that adds this entry, on branch `redesign`.

**Built:**
- **Tokens** (`web/src/styles/tokens.css`): the logo palette, light roles and "floodlights"
  dark roles, the printed-card `--plate-*` set, type scale, space, radius, shadow, touch
  targets and motion. Every text pair's contrast is measured and written beside it.
  Tailwind v4 reads the tokens; its default palette is switched off, so no stray colour
  can reach a page.
- **Fonts, changed from the plan.** A glyph-by-glyph check found that Barlow Condensed,
  Atkinson Hyperlegible Next and Geist Mono all lack the Hausa letters Ɓ ɓ Ɗ ɗ Ƙ ƙ Ƴ ƴ.
  Display is now **Fira Sans Condensed 800 italic**, body **Andika** (SIL, made for
  literacy in African languages). Both have every letter. **Geist Mono** stays for IDs
  and codes, which are A–Z and 0–9 only. 44 KB preloaded; the ID font loads only where
  used; Latin Extended loads only when a Hausa letter appears.
- **The logo as SVG**: traced from the PNG (`scripts/design/`), in full, horizontal, mark
  and wordmark, each in colour, on-dark, white and black (`web/public/brand/`), plus
  an inline `Logo` component whose dark parts follow the theme.
- **Icons**: Tabler through one module (`components/icons`), plus whistle, yellow and
  red card, VAR screen and position shirts drawn on its grid.
- **Pitch-line kit** (`components/pitch`): full pitch, centre circle, halfway line,
  penalty arc, touchline and mowing stripes, chalked in with CSS.
- **Translation**: next-intl, server side, `messages/en.json`. Header, footer and page
  metadata read from it; screens move over as they are rebuilt.
- **`/styleguide`**: every token, the type with the Hausa test line, icons, the referee
  scale, pitch lines, scoreboard and motion. Served in development, or with `STYLEGUIDE=1`.

**Verified:** typecheck and build clean. `STYLEGUIDE=1 check:render`: 71 checks, all pass,
including `/styleguide` at 320–1280px in light and dark, and every no-JS round trip.
Logo, pitch lines and the phone dark view checked by screenshot.
- **Found:** cross-document view transitions left `<html>` intercepting clicks after a
  no-JS form POST and redirect in Edge, which stalled the password-reset round trip.
  They are held back until the Phase 8 motion pass.
- **Found:** a stroke that does not scale breaks `pathLength`-based line drawing in Edge;
  the draw animation uses a fixed screen-pixel dash.
- Black text on the logo green measures 6.48:1, not the plan's 7.0:1 (still passes).

**Not done / open:**
- **Gate: the style guide needs your approval before Phase 2.** Run the web tier with
  `STYLEGUIDE=1` and open `/styleguide`.
- The trace bakes the logo's soft red-to-black shadow in as black; a designer's source
  file would replace it.
- The Hausa letters render in the browser; not yet tried on a real Android phone.

---

## 2026-10-06 — Frontend redesign, Phase 0: clear the ground
**Commit(s):** see the commit that adds this entry, on branch `redesign`.

**Built:**
- **Product decisions recorded:** the name is KAFRIADA NET; football only; the new frontend
  lives in this repo's `web/`; English first with every string ready for translation;
  a PWA in the final phase; the card reads "Issued by KAFRIADA NET".
- **The old look is gone.** `globals.css` and its fonts are deleted. An AST codemod removed
  every `className` attribute from every page (776). The shared components render
  bare semantic HTML and keep their props. The seal, perforation, duplicate ID strip,
  silhouette and sample card are removed.
- **Football only in the forms.** `PILOT_SPORT` in `lib/profile.ts`; registration and club
  forms send it as a fixed value and offer football positions only. The API still accepts
  the other sports, so existing records and tests are unaffected.
- **Every "KAFRIADA" in web copy is now "KAFRIADA NET"** (55 strings).
- `web/KEPT.md` lists every file carried over and why.
- `check-render.mjs`: the phone-menu check (old `.nav-menu` classes) is replaced by a
  class-free check that the main navigation is reachable with JavaScript off.

**Verified:** `npm run typecheck` and `npm run build` clean. `check:render` against the
running API (Supabase, pooler) and web: all 66 page × viewport checks pass, and the
no-JavaScript registration, email confirmation, password reset and sign-in round trips
pass. Signed-in screens were not audited (no `SIGNIN_*` set).

**Not done / open:**
- The backend card renderer (`contexts/identity/card.py`) and API messages still print
  "KAFRIADA"; changed with the new card design in Phase 4.
- Every page still ships Next's ~102 KB shared runtime; PUB-01's zero-JavaScript budget is
  a Phase 3 item.
- The logo needs an SVG trace (Phase 1).
- Next: Phase 1, the design system and `/styleguide`.

---

## 2026-10-03 — Clubs sign up on their own, with a full record (migration 0015)
**Commit(s):** see the commit that adds this entry; the badge change before it is `1f21717`.

**Built:**
- **A public club sign-up** (`POST /v1/clubs/register`, `/clubs/register`). It creates the
  representative's account (no athlete record, no ID) and the club in one transaction. The
  club waits as a new status, `unconfirmed`, invisible to administrators and impossible to
  approve. It moves to `pending_review` when the representative confirms their email.
  - The record covers: registered and short name, kind, sport, category, age groups,
    level, year founded; home ground, address and town; club phone and email;
    registration number, affiliation, colours and website (optional); the
    representative's role; and a second official with a different number.
- **One validator for all entry points.** `contexts/clubs/profile.py` checks the club record
  whether a club signs up, staff register it, or it is edited. In the web tier it is one
  `ClubFields` component.
- **Athletes no longer hold `club.create`**, and "Register a club" is gone from athlete
  screens. It is in the header, footer and landing page instead.
- **Staff can still register a club for someone** at `/clubs/new`: administrators through
  `POST /v1/clubs`, coordinators through the new `POST /v1/lgas/{lga_id}/clubs`. The area
  comes from the scope-checked path.
  - **Found on the way:** coordinators held `club.create` but could never use it. The old
    route has no scope, and an LGA-scoped grant does not satisfy an unscoped check.
- **Edit and details:** `PUT /v1/clubs/{id}` and the edit screen cover the whole record; the
  details tab shows it and says when it is incomplete.
- **Verified badge (previous commit):** the ID is issued at registration and unverified
  athletes may join and move between clubs. A Verified / Unverified badge on the profile,
  card page, roster, coordinator search and `/me` marks the difference.

**Verified:**
- Migration 0015 applies, reverses and re-applies on the local PostgreSQL;
  `check_migration_safety.py` is clean. Its one deleted row is approved in the file.
- New `test_club_signup.py` (16): the club stays unseen and unapprovable until the email is
  confirmed; the representative is not an athlete and cannot sign in before confirming;
  every required field is refused by name with nothing written; the duplicate
  representative number and same-number second official are refused; an athlete gets 403.
- `test_clubs.py` gains the coordinator-only-in-own-LGA case and the new field refusals.
- Club, admin, appoint, route-manifest and permission-matrix tests: 331 passed.
- Full suite: 973 passed, 4 failed. All four pass on their own with a cleared outbox. One
  was a real assertion made too broad by registration now emailing a code
  (`test_notifications.py`: "no email at all" became "not this message by email").
- Live, JavaScript off, local DB: sign up a club through the form → the club is
  `unconfirmed` → the emailed code → `pending_review`, the representative is on `/me` with
  only the club tile → the details tab shows the record → the edit form is pre-filled.
- `check:render` passed, including `/clubs/register` at all widths and the signed-in
  `/clubs/new`, club details, club edit, `/admin/clubs`, card and `/details`. An earlier run
  had passed on an expired session (every page was the sign-in screen); it was caught by
  the text counts and re-run with a fresh session.

**Not done / open:**
- Migrations 0014 and 0015 are not yet on Supabase.
- Clubs registered before today keep empty fields until edited.
- Nothing yet lets an athlete transfer between clubs beyond accepting an invitation
  (Slice 2, TRF-01..05); unverified athletes may do that today.

## 2026-10-03 — Full athlete registration and email confirmation (migration 0014)
**Commit(s):** see the commit that adds this entry.

**Built:** registration now collects the whole athlete record, all required except middle
name and second position. The record covers:
- name in parts, sex, date of birth, nationality and state of origin;
- phone, email, home address, town and LGA;
- sport, main position or event (grouped by sport and checked against it), stronger side,
  height, weight, years playing, highest level played;
- an emergency contact (name, relationship, phone; must differ from the athlete's own).

Every account must confirm its email with a code before it can sign in. Sign-in with the
right password but an unconfirmed email issues no session, sends a fresh code and goes to
the confirm screen. An account with no email is asked for one at sign-in. Phone codes
are off (`REQUIRE_PHONE_CONFIRMATION=false`) until the Twilio sender ID exists.

Other changes:
- New routes `POST /v1/email/code` and `/v1/email/confirm`, and a new code purpose
  `email_verification` that always goes by email.
- `/details` shows what registration fixed (read-only) and edits the rest; every field is
  required on save.
- The privacy notice is now v1.1, listing the new data. Consent is recorded as 1.1.
- `appoint` requires a confirmed email.
- Fixed on the way: the `kaf_pending` cookie silently dropped the email.

**Why:** the project lead asked for complete records and strict email confirmation. No
NIN, by their decision.

**Verified:**
- Migration 0014 applies, reverses and re-applies on the local PostgreSQL;
  `check_migration_safety.py` is clean.
- Full suite: 950 passed, 2 failed. The 2 are `test_notifications.py`, which drains only
  50 messages; the local outbox held 83 pending from other tests. With the backlog
  cleared, all 6 pass.
- New `test_full_registration.py` (24): every missing or invalid field is refused by
  name, the full record is stored, nothing private reaches the public profile, and the
  details update works and cannot change identity fields.
- New tests in `test_codes_and_outbox.py`: the email code is sent at registration with
  no SMS, sign-in waits for the email, and the missing-email path.
- Live, JavaScript off, against the local DB (API 8011, web 3001): register through the
  form → the confirm screen shows the masked address → signing in early goes to confirm
  with no session → the emailed code opens the account → `/details` shows the stored
  address.
- `check:render`: 85 checks passed.

**Not done / open:**
- Migration 0014 is not yet applied to Supabase.
- There is no erasure routine yet (already a Stage 3 item); it must cover the new fields.
- Accounts registered before today keep empty fields until the athlete saves `/details`,
  which then requires all of them.
- Decided after this entry: the ID stays issued at registration (the "ID only after paid
  verification" plan is withdrawn), and unverified athletes may join and move between
  clubs. The badge marks the difference.

## 2026-10-03 — Interface overhaul: navigation, layouts and components for every screen
**Commit(s):** see the commit that adds this entry.

**Built:** a structural redesign of all 36 screens, keeping the existing visual identity
(paper, green and gold, the document card, every `--plate-*` token). New in
`globals.css`: two page widths (680px reading, 1180px working screens), a site header
with a no-JavaScript `<details>` menu on phones, a footer, page heads with back links and
actions, section tabs, an administrator sidebar from 1024px, stat tiles, action tiles,
tables that restack as labelled cards below 720px, filter chips, toolbars, pager, empty
states, form fieldsets and two-column field rows, and layout utilities. New components:
`SiteHeader`, `SiteFooter`, `PageHead`, `SubNav`, `AdminShell` (in `AdminNav.tsx`),
`CoordinatorNav`, `Stat`, `EmptyState`, `Pager`, `NoAccess`. Every one of the 213
inline `style={{}}` attributes is gone. Screens reworked beyond restyling: `/me` is a
hub of tiles grouped into My ID, Clubs and Work areas, with the account card beside
them; the admin overview, coordinator dashboard and club page lead with stat tiles;
users, audit log, roster, coordinator search and payments are tables; the review and
club-review screens put the evidence beside the decision on a desktop; the landing
page shows a sample card next to the headline. Copy: removed internal screen codes
("Admin · ADM-04", "Coordinator · CRD-04") from page eyebrows and a stale "Payment
opens shortly" line on the card page.

**Why:** the identity was right; the structure was not. There was no navigation (the
header said "Sign in" to people already signed in), every screen was a 660px column
including tables and dashboards on a desktop, and `/me` was a wall of equal buttons.
The header reads no cookie on purpose: doing so made every page dynamic, including the
cached public profile. "My account" goes to `/me`, which already sends anyone not
signed in to sign-in; signing out moved to `/me`'s page head. Tabs wrap rather than
scroll sideways, because a tab off the edge of a phone is a screen nobody finds.

**Verified:** `npm run typecheck` and `npm run build` clean. `check:render` now runs at
320, 360, 768 and 1280px (light and dark) and checks the phone menu opens with
JavaScript off: all public pages, the JS-off registration, confirm, reset and sign-in
round trips, plus 26 signed-in screens via `EXTRA_SESSIONS` (every athlete, club,
coordinator and admin screen) — 164 checks, all passed. Signed-in screens were
audited against the private local PostgreSQL with one throwaway account holding
athlete, super_admin, lga_coordinator and club_admin; nothing was written to Supabase.
The audit found three real faults, all fixed: tab bars overflowing at 360px,
visually-hidden table headings extending past the screen edge, and a single-column
grid sized by a 320px evidence image. Four screens were also looked at directly
(`/me` and `/admin/users` at 1280px, `/coordinator` at 390px, the landing page).

**Not done / open:** the signed-in sign-in/sign-out loop (`SIGNIN_PHONE`) was not run
this session; payment return states (confirmed/failed/review) and the verification
states other than "start" still have not been contrast-audited, as before.

## 2026-09-24 — CI green end to end: four latent gate failures
**Commit(s):** the four commits after `92c5de7` (SQLAlchemy pin, gitleaks config, pip-audit).

**Built:** nothing new. Three gates that had never run, and one that broke overnight,
each failed behind the one before it. In the order they surfaced: (1) `sqlalchemy`
was unpinned and CI picked up 2.1.0, whose typing broke `mypy` in files nobody
touched — pinned `<2.1` (everything here is built and tested on 2.0.x; 2.1 is its own
change). (2) The payout-path allowlist compared line numbers, so any edit above an
allowlisted line re-broke it — fixed in the clubs commit. (3) The secrets scan
panicked before scanning: `.gitleaks.toml`'s Postgres-URL rule used `(?!...)`, which
Go's RE2 does not support; the placeholders are now excluded by the rule's allowlist.
(4) `pip-audit --strict` audited the runner's whole interpreter and failed on `bcc`, a
system package that is not ours and not on PyPI; it now audits the project
(`pip-audit --strict --desc=on .` — `--desc` had been taking the path as its value).

**Verified:** the run on the last commit passes all four jobs (static, web,
database, security).

**Worth knowing:** on a push, the gitleaks action scans only the pushed commits
(`--log-opts=-1` in its log), so "no leaks detected" means that commit, not the whole
history. A one-off full-history scan has not been run. The dependency audit passing
means no known vulnerabilities in what `pyproject.toml` resolves today.

**Not done / open:** a full-history gitleaks run; SQLAlchemy 2.1 is unadopted.

---

## 2026-09-27 — Club leftovers: revoking a verified club, purging its document
**Commit(s):** `781d431`

**Built:** `contexts/clubs/verification.revoke()` — reason and password required, exactly
ADM-03's shape (`access.reauthenticate`, a `Refused("password")` field mapped to 422 the same
way): moves an `approved` request to `revoked`, sets `organizations.stage` back to 1, writes
the decision (append-only, `decision='revoked'`) and an audit row, and tells the club's
representative why. A revoked request frees the slot the same as an athlete's — the club's
own `overview()` then reads "none", not "revoked", so it can be verified again from scratch.
Route: `POST /v1/admin/club-verification/{id}/revoke`, under the same `club.approve`
permission as approve/reject. Screen: `/admin/clubs/[id]/revoke`, reached from a "Withdraw
verification" link next to every verified club on `/admin/clubs`. Also
`contexts/clubs/verification.purge_expired_documents()` — the same shape as the athlete
purge (a rejected request is excluded, since it may still be resubmitted against the same
document), joined into the hourly `documents` job in `kafriada/jobs.py` alongside it.

**Verified:** `tests/test_club_verification.py` grew to 17 tests. Revoking: a reason is
required, the password is checked again, a club with no verification request at all is 404,
one with a request that is not approved is 409, a second revoke on an already-revoked one is
404 (the slot was freed), only a reviewer may call it, and a revoked club's `overview()`
correctly reads "none" rather than "revoked". Purging: the document is gone and its row marked
`deleted` at 31 days but not at 29, and a rejected club's document survives 90 days untouched.
Mutations proved red: dropping the password re-check, and dropping the "must be approved"
guard. The full suite, `ruff`, `mypy`, `check_migration_safety` and the payout gate are clean;
`kafriada.jobs --once --only documents` runs both purges cleanly with a local store configured.
Live against Supabase: registered, approved, paid and settled a real club through
`settle_charge` (not a hand-edited row), approved it, refused a wrong password (422), then
revoked it for real and confirmed `verified` flipped from `true` to `false`; `check:render`
audits the new screen for both the reviewer and the club administrator, signed in.

**Not done / open:** the athlete-side and club-side purges still run as two separate SQL
scans in the same job; a single combined query would be a later tidy-up, not a correctness
gap. There is no screen listing what has already been revoked (the audit log and each
club's own decisions cover it).

---

## 2026-09-27 — CRD-06: bulk QR card printing
**Commit(s):** `5314045`

**Built:** **Migration 0013**: `identity.card_prints` (athlete, who printed, when), insert-only
by privilege and trigger like every record later used as evidence; a reprint is another row and
"not yet printed" means no row. `contexts/coordination/cards.py`, three routes in
`api/v1/coordination.py` (`GET /v1/lgas/{id}/cards`, `.../cards.pdf`, `POST .../cards/printed`),
and `/coordinator/cards` with a PDF proxy. Filters are registration date (Nigeria time) and
"not yet printed" or all; a page is at most five sheets of eight cards, so a very large batch is
paged rather than built as one document. Printing is the browser's own: a print stylesheet lays
the cards out two across and four down at exactly credit-card size (85.6 x 54 mm) on A4, and the
page hides everything that is not a card when printed; for a browser that cannot print there is
a PDF of the same page. "Mark these as printed" records the page and writes an audit row; athletes
outside the LGA are ignored. A "Print QR cards" link joins the coordinator's dashboard.

**Why the PDF is drawn from one query:** the first version loaded each athlete's profile in turn,
which is forty round trips per page, and over the Supabase link that is minutes. One query returns
what the cards need, and forty cards now come back as five sheets in about eight seconds.

**Verified:** `tests/test_cards.py`, 8 tests: the batch and its sheet arithmetic; the date window;
what was marked leaves the unprinted list and stays in the full one, and a reprint is a new row;
marking ignores anyone outside the LGA, unknown ids and malformed ones, and refuses too many;
scope is the LGA, its state and nothing else (403 elsewhere and for an athlete, 401 anonymous) on
all three routes; a batch is paged; the PDF is real, an attachment, two sheets
for nine cards, and a 404 when nothing matches; a print record cannot be updated or deleted.
Mutations proved red: dropping the LGA from marking, and ignoring the unprinted filter. The full
suite, `ruff`, `mypy`, `check_migration_safety` and the payout gate are clean, and a full
`alembic downgrade base` then `upgrade head` round-trips. Live against Supabase with a throwaway
coordinator: 1,149 unprinted athletes over 29 pages, a 40-card page as a five-sheet 1.3 MB PDF,
another LGA refused with 403; `check:render` audits the new page.

**Also:** a lesson worth keeping. After a restart the API answered every request with 401, which
looked like a broken session and was not: the restart had inherited the local-test-database
variables exported earlier in the same shell, so the API was reading a different database from
the one that held the session. Restart the tiers from a shell with those variables unset.

**Not done / open:** the printed layout was checked by structure (page count, sizes), not by
printing on paper; the browser's own print is what a coordinator will use, so the first real
print should be looked at. Cutting guides between cards are not drawn.

---

## 2026-09-27 — The administrator console, and the first super administrator
**Commit(s):** `5ee7830`

**Built:** `python -m kafriada.appoint`, `contexts/admin/service.py` (read models),
routes in `api/v1/admin.py`, and `/admin`, `/admin/users`, `/admin/users/[id]`,
`/admin/clubs`, `/admin/club-verification` (with a document proxy), `/admin/audit`,
`AdminNav`, and an "Administrator console" button on `/me`. **First administrator:** nobody
holds the authority to ask for a password yet, so it is a command run by someone with the
database credentials; it grants only `super_admin`, only to a registered person whose
number is confirmed, refuses to do it twice, and writes an audit row with the operator's
reason. **ADM-01** shows money in the last 24 hours, unresolved (frozen) payments, the
last nightly ledger check and when it ran, the funnel and conversion, clubs, and the
30-day review median; a failed ledger check takes over the top of the screen, and
unresolved payments and a slow median get their own notice. **ADM-02** finds people by name
(partial), whole phone number or ID (partial) and role, with masked numbers and last-seen
time; a person's page grants, revokes and ends sessions through the existing password-checked
routes, with role and scope in one form. **ADM-06** is filters plus paging over an
append-only table and has no write path at all. The two club screens are the reviewer side
of CLB-01 and CLB-04, which until now were API only. `grant_role` used to refuse every club
scope ("clubs do not exist yet"); it now checks the club exists.

**Verified:** `tests/test_appoint.py` (8) and `tests/test_admin_console.py` (10). Appoint: a
confirmed person, once, an audit row naming the operator, a local-format number works,
unknown / unconfirmed / no reason / bad number / erased account are all refused and grant
nothing; a club-scoped grant needs a real club (a malformed id, an unknown club, an LGA id
and no scope are all refused) and the role then works on that club only. Console: only a
super administrator can read any of it (a plain athlete, an LGA coordinator and a state
coordinator holding a *scoped* `admin.read_audit` are all 403, anonymous 401), the audit
log has no POST, PUT, PATCH or DELETE, the overview moves with a paid athlete, a frozen
payment and the ledger check, people are found by name, phone and ID with roles and no
full number, erased people do not show, paging, clubs waiting come first, the audit log
filters by actor, action and date and pages. Mutations proved red: dropping the club
existence check, and listing erased people. The permission matrix and route manifest pass
with the new routes. Live against Supabase with a throwaway super administrator: overview,
users, clubs and audit read; a grant (201), a grant with the wrong password (422), and a
revoke (204); the throwaway was revoked afterwards. `check:render` audits every new
screen.

**Also:** one existing test (`test_coordination`) counted waiting cases more loosely than
the real queue, which needs both files ready, and failed only when other tests left
half-built requests behind; its count now follows the queue's rules. The overview on
Supabase shows 16 unresolved payments: they are frozen wrong-amount payments from earlier
testing, and the screen is doing its job.

**Not done / open:** ADM-01's state-scoped subset for a state coordinator; ADM-02's "reset a
phone number"; ADM-06's export; the older `/admin/revoke` and `/admin/reversal` screens do
not carry the new navigation; revoking a verified club; the 30-day purge of club documents.

---

## 2026-09-27 — The coordinator console (CRD-01, CRD-03) and editing a club
**Commit(s):** `8527517`

**Built:** `contexts/coordination/service.py`, `api/v1/coordination.py`, `/coordinator` and
`/coordinator/find`. **CRD-01:** registered, paid, to review, clubs and the oldest
waiting case for one LGA (amber past 18 hours, red past the 24-hour target, and "nothing
is waiting" said plainly), links to review, find and pay, and, for someone who can start
assisted payments, today's cash total and the two daily limits with the payment link
withdrawn once a cap is reached. The review count comes from the reviewer's own queue
query, so it excludes their own record and cannot drift from what they can act on. A
state coordinator or an administrator picks the LGA. **CRD-03:** name or ID (partial) or a
whole phone number, inside one LGA, paged with plain links; wildcard characters match
literally; under two characters returns nothing. Also **edit club details** (CLB-02's
last action): `PUT /v1/clubs/{id}` and `/clubs/[id]/edit` change name, contact number and
founding year; sport and area are not editable, because a club's rosters and reviews
belong to what it registered as. The audit row records which fields changed.

**Why an athlete elsewhere is "no results":** the wireframe is explicit — "not permitted"
would let a coordinator probe who exists in other LGAs. The LGA is a query condition in
the service, not something the caller can widen, so out-of-scope athletes are not filtered
out afterwards, they are never selected.

**Verified:** `tests/test_coordination.py`, 8 tests: the numbers move with the register;
a coordinator's own record is never counted as waiting; the cash total is the caller's
own and a started-but-unpaid payment counts against the cap, not as cash; scope is the
LGA, its state and global, and nothing else (403 for another LGA and for an athlete, 401
anonymous, 404 unknown LGA); find by name, ID (any case, or a serial fragment) and phone
with no private field in the response; short queries and `%`/`_` match nothing; an athlete
moved to another LGA gives exactly the same response as someone who does not exist, by
name, ID and phone, and is found by the coordinator whose LGA it now is; paging.
`tests/test_clubs.py` gains three tests for editing (fields, team renamed, audit, bad
input, only the club's own administrator). Mutations proved red: dropping the LGA from
the search (five tests) and dropping the coordinator from the cash total. Full suite,
`ruff`, `mypy`, `check_migration_safety` and the payout gate clean. Live against Supabase
with a throwaway LGA coordinator: dashboard (1,149 registered, 16 waiting), search, and
another LGA refused with 403; `check:render` audits the new screens.

**Also:** the machine's temporary directory had been cleaned, which took the private local
PostgreSQL with it (the earlier "could not open pg_notify" error). It was rebuilt from the
documented recipe, now under `C:\Users\HP\.kaf-localdb` so Windows does not clean it.

**Not done / open:** CRD-06 (bulk QR printing); a coordinator's read-only view of clubs in
their LGA. The throwaway coordinator used for the live check on Supabase had its role and
session revoked afterwards (the user row remains: users are never deleted).

---

## 2026-09-25 — CLB-04: verify the club (₦15,000)
**Commit(s):** `3050919`

**Built:** **Migration 0012.** `money.payments.org_id` names the club a `stage2_org`
payment is for; a CHECK makes purpose and club go together and `guard_payment` treats it
as an agreed field, immutable like the amount. `identity.club_verification_requests` is
the machine (draft, under_review, approved, rejected, revoked; one live request per club
by partial unique index; cannot leave draft without a document and a payment, by CHECK)
and `club_verification_decisions` is append-only with a required reason for a rejection.
`media_files` accepts `club_document`, uploaded by the administrator and linked by the
request. `contexts/clubs/verification.py` is the state machine and reviewer; the payment
side is `payments.service.start_club_payment` and a purpose branch in settlement
(`club_verification.mark_paid` beside the athlete's, inside the ledger transaction, and a
club-worded receipt). Routes in `api/v1/club_verification.py`; `/clubs/[id]/verify`
(document, pay, wait, rejected-with-reason, resubmit), a Verify club button on the
dashboard, a "Club verification" label on `/payments`.

**Why the shape:** the wireframe says one payment path, two prices, so a club payment is
the ordinary payment with a different beneficiary column rather than a second path. The
document reuses the media pipeline, owned by the uploading administrator's athlete row,
so nothing about storage, re-encoding or EXIF stripping is new.

**Verified:** `tests/test_club_verification.py`, 12 tests: price and state at start;
an unapproved club, a stranger and an anonymous caller are refused; paying before a
document is refused and writes no payment; a non-image is refused on the form; the
payment names the club, is the club price, settles to exactly two ledger lines and sends
a club receipt; a payment at the athlete price freezes and never reaches a reviewer; the
database refuses an org payment without a club and a club on an athlete payment; the
whole review (queue, document served only while waiting, approve makes the club stage 2,
no second payment or edit, cannot be decided twice); rejection needs a reason the club
reads, and resubmit reuses the payment; only a reviewer can see the queue, the document
or decide; one administrator of two clubs cannot move a file between them. Mutations
proved red: dropping the club from the media ownership query (needed an open,
unsent slot to show, so the test uses one) and matching a payment to any club's draft.
The permission matrix and route manifest pass with the new routes. The full suite,
`ruff`, `mypy` and `check_migration_safety` are clean, and a full `alembic downgrade
base` then `upgrade head` round-trips with these rows present. Live: a throwaway club on
Supabase uploaded a document (ready) and real Paystack accepted a ₦15,000 checkout for
it. `check:render` audits the new screen.

**Not done / open:** revoking a verified club (the state exists, no route or screen); the
30-day purge of club documents (the athlete purge is keyed to athlete requests); a
reviewer screen (approval and review are API calls until the admin console and a first
super_admin exist; test clubs on Supabase are approved by a one-line SQL update); a real
card payment for a club has not been made (only checkout creation, against real
Paystack, and settlement in tests).

---

## 2026-09-25 — Clubs: invite a player (CLB-03), my clubs (ATH-05), approval
**Commit(s):** `8a1e74b`

**Built:** `find_player`, `invite_player`, `remove_player`, `my_clubs`,
`accept_invitation`, `decline_invitation` and `set_status` in `contexts/clubs/service.py`;
routes for each in `api/v1/clubs.py`; `/clubs/[id]/invite` (search one exact match,
send an invitation), `/clubs` (my current club and invitations, Accept / Decline), Add,
Remove and Withdraw on the dashboard, "My clubs" on `/me`. **Migration 0011** adds the
`club.approve` permission and grants it to `super_admin` (0001 only granted what
existed then). Approving or suspending is `POST /v1/admin/clubs/{id}/approve|suspend`;
there is no screen for it yet. Invitations and approval each queue a notification.

**Why the shape:** a lookup needs the full KAFRIADA ID or phone and returns no phone,
date of birth or document — browsing would turn the register into a directory anyone
could harvest by registering a club (CLB-03's own note). Accepting is one transaction:
release the current membership, activate the new one, write the career events; the
partial unique index from 0010 makes a second active membership impossible even if
that code were wrong. Only an approved club can invite, and a suspended one stops
recruiting and drops out of a player's invitation list. The two scope checks that a
route's `Requires` cannot make live in the service: remove looks the roster row up
*through the club in the path*, and an invitation is only found for the athlete who
owns it.

**Verified:** `tests/test_club_roster.py`, 14 tests, plus `test_clubs.py` (29 together):
approval needs the permission (403 for a club admin, 401 anonymous, 404 unknown);
unapproved and suspended clubs cannot recruit; exact lookup by ID or phone, and misses
for a partial ID, a name, a short number and an empty query; no private field in the
response; a club cannot invite for, look up through, or remove from another club, and
naming another club's roster row through its own path finds nothing; an athlete cannot
answer someone else's invitation; accept, decline and re-invite; a second accept
moves the player (`joined_club`, `left_club`, `transferred`); malformed ids are 404,
not 500. Mutations proved red: dropping the club from the remove query, dropping the
owner from the invitation query. The permission matrix (every role x every route x two
tenants) needed a probe value for the new `roster_id` parameter and then passes with
the new routes. Full local suite, `ruff`, `mypy`, `check_migration_safety` clean.
Live against Supabase: invite before approval 409, after 204, the player sees it,
accepts (204), the roster shows them; `check:render` audits the dashboard tabs, the
invite page in its empty, match and no-match states, `/clubs` and a refused view,
signed in as each role, light and dark — all pass.

**Not done / open:** CLB-04 (club verification payment), edit club details, an approval
screen (the throwaway test clubs on Supabase were approved with a one-line SQL update,
since no super_admin exists yet), and a coordinator's read-only view of clubs in their
LGA (`club.read_scoped` is granted to them but the club scope check does not resolve
LGA or state hierarchy). The web forms were not driven in a browser.

---

## 2026-09-24 — Clubs: register a club (CLB-01) and its dashboard (CLB-02)
**Commit(s):** `a23d25f`

**Built:** `contexts/clubs/service.py`, `api/v1/clubs.py`, `/clubs/new` and
`/clubs/[id]`. `POST /v1/clubs` (`club.create`, throttled `register_club`, default 10
per address per hour) creates the club, its one default team and a `club_admin` grant
scoped to the club id, and writes an audit row, in one transaction. `GET
/v1/clubs/{club_id}` (`club.read_scoped`, scope `club`) returns counts, roster and
details. A repeated name in the same LGA comes back as a 409 the form turns into a
tick box (CLB-01: warn, not block). `/me` shows the club's name for a `club_admin`
grant (the role list previously resolved names only for places) and links to it. The
same change also spinner-locks the slow forms (`SubmitButton`, `d9459c7`).

**Why the scope is the interesting part:** `Requires(scope="club")` only proves the
caller holds a grant on the club id in the path. That is enough here because a club
is a leaf — there is no second entity in the request to mismatch, unlike CRD-04's
athlete-in-an-LGA — so the service's job is narrower: every query takes the club id
and filters on it, and nothing takes a bare athlete or team id from the caller.

**Verified:** `tests/test_clubs.py`, 15 tests: registration writes the club, team,
grant and audit row; bad input is refused on its own field and writes nothing (8
cases); the duplicate question; an administrator cannot read another club (403 both
ways), a stranger gets 403, anonymous 401; a super administrator reads any club and
gets 404 for an unknown or malformed id; the roster holds only this club's people; a
second active membership is refused by the database. Mutation proved red: removing
the club filter from the roster query fails two tests. Route manifest and permission
matrix pass. `ruff` and `mypy` clean. Live against Supabase: registered a club (201)
and a second user was refused (403); `check:render` audits `/clubs/new` and the
dashboard's three tabs signed in, plus the refused view, in light and dark — all
pass. The local suite passed except `test_a_message_is_sent_once…`, which is the
documented outbox pile-up (965 stale rows) and passes once they are cleared.

**Also:** `scripts/check-no-payout-path.sh` compared allowlisted lines by line
number, so any edit above one (this session touched two files) re-broke the gate. It
now compares path and text only. Probed: a new withdraw line in an allowlisted file,
a new file with `cash_out`, and a reworded allowlisted line are all still refused.

**Not done / open:** CLB-03, CLB-04, ATH-05, remove player, edit club details, and
club approval — a new club stays `pending_review` and nothing can approve it yet. The
form's POST through the web tier was not driven in a browser (the API path and the
rendered pages were).

---

## 2026-09-23 — Payout-path gate's false positive resolved
**Commit(s):** `1b803ee`

**Built:** a content-based allowlist in `scripts/check-no-payout-path.sh` —
each of the 38 known "withdraw a verification badge" matches (ADM-03, see
previous entry) is now listed by its exact `path:line:content` text and
skipped; anything else still fails the build.

**Why:** the project lead's call, made directly — since the feature isn't a
money-out path, ignore it in the script rather than rename the feature's
copy. Also directed: handle the same class of false positive the same way
going forward, without asking each time.

**Why content-based rather than excluding whole files:** an allowlist entry
only exempts that exact wording. A real payout line added later to
`contexts/access/service.py` or `contexts/ledger/reversal.py` — both
general-purpose files that stay on the search path — still fails the build,
and editing an allowlisted line's wording makes it fail again until it's
re-checked and re-added. Excluding the whole file would have been simpler
but would have gone blind to those files for good.

**Verified:** the script passes clean; a planted `cash_out_to_bank()` in a
new file is still caught and refused. Not yet confirmed on GitHub Actions
itself, but the earlier fixes already turned every other job green, so this
should be the last piece.

**Not done / open:** none.

---

## 2026-09-23 — CI's static job could never run its unit tests; a live compliance gate found broken
**Commit(s):** `8835626`

**Built:** an `env:` block on the `static` job in `.github/workflows/ci.yml`
(`DATABASE_URL_APP`, `DATABASE_URL_MONEY`, `ENVIRONMENT`, `SECRET_KEY`,
`QR_SECRET`, `SMS_PROVIDER`), the same values the `database` job already
uses. `src/kafriada/main.py` builds the real `Settings()` at import time
(`app = create_app()` at module scope), so importing `kafriada.main` — which
most test files do, including ones marked `not db` — needs all four of
`Settings()`'s required fields to exist somewhere. The `static` job set none
of them, so `pytest -m "not db"` failed to even collect its first file. This
looks to have been true since the test suite first needed `create_app()` at
import time; nothing about it is new today.

**Verified:** reproduced the job's exact conditions locally — `api/.env`
moved aside, only the six new variables set, `pytest -m "not db"` — clean,
where the same command previously failed collection with four
`pydantic_core.ValidationError`s.

**Found, not fixed, and worth a decision:** with the two bugs above out of
the way, the `database` job and the `static` job's own Lint/Types/module-
boundary/migration-safety steps are all green on GitHub Actions — but
`security` still fails, on `scripts/check-no-payout-path.sh`. That script is
a flat `grep -rInE` for `withdraw|payout|...` across `api/src` and `web/src`
with no allowlist, by design (per its own comment: a keyword the CI can
check beats a comment nobody reads). ADM-03 (withdraw a *verification*,
built 2026-09-22) uses exactly this word for an unrelated feature — 37
matches across 14 files, every one of them "withdraw a badge", not money.
Two of those matches are `contexts/ledger/reversal.py` and
`admin/reversal/page.tsx` **explaining that there is no payout path** — the
check is tripping on its own documentation. This means the gate has almost
certainly been permanently red since ADM-03 shipped, which is the worst
failure mode for a check like this: a gate that never passes stops meaning
anything, and a real money-out path added the same week would have been
just one more red line nobody looked at.

This one was **not touched**. `CLAUDE.md` lists this exact script under
"Invariants — do not weaken," and choosing how to scope an allowlist against
a regulatory gate is the project lead's call, not a lint fix — unlike the
mechanical fixes above, there's a real way to get this wrong (too narrow
still blocks nothing new; too broad quietly opens a hole). Flagged for a
decision: an allowlist inside the script (by file or by phrase), or renaming
the verification feature's wording away from "withdraw" — the second is a
UI copy change under the project's own copy-tone rules, not this script's.

**Not done / open:** the payout-path check itself, pending that decision. The
security job's later steps (secrets scan, `pip-audit`) have not run at all
yet — they're gated behind this one failing first.

---

## 2026-09-23 — CI was red on main: lint, mypy, and a migration downgrade bug
**Commit(s):** `45e01fa`

**Built:** nothing new — this is main going green again after two commits
earlier the same day (`e34ad39`, `a3c91e9`) had left it red. Fixed: seven
ruff findings across files touched earlier in the day's session (an en dash
in a docstring, two unsorted import blocks, two unused test imports, one
unparenthesized `and`/`or`); four mypy errors that had never actually run in
CI because the Lint step fails before Types does (`outbox/service.py`'s
drain result typed against one `Sent` dataclass when a second, structurally
identical one could also flow into it; `card.py` using Pillow's pre-10 name
for a resampling filter; `otp.py` passing `str | None` where
`queue_email` wants `str`, asserted rather than re-typed since
`prefers_email()` already guarantees it on that path).

**The real bug:** migration 0008's `downgrade()` re-narrows
`ledger_entries`' `source` CHECK back to `('paystack', 'fee')` — but CI's own
"Database guarantees" step (`pytest -m db`) runs first and leaves a real
`source='reversal'` row behind, which the narrower constraint then refuses.
Chasing the reverse chain all the way to base surfaced a second, older bug
of the same shape: migration 0001's `downgrade()` drops the `ops` schema,
which is where `alembic`'s own version table lives (`env.py`'s
`version_table_schema`) — the cascade takes it with it mid-command, so
alembic has nowhere to record "now at base". Between the two, `alembic
downgrade base` had likely never actually succeeded once in this project's
history; nothing before today exercised the full chain in one run.

**Why these are safe fixes and not scope creep on 0001/0008:** both
downgrades already say, in their own docstrings, that they are destructive
and for a scratch database only. Deleting a reversal row under a
temporarily disabled trigger (0008) and recreating an empty
`ops.alembic_version` with the one row alembic's bookkeeping expects to
delete (0001) stay entirely inside that same charter — neither migration's
`upgrade()` changed, and no real environment is affected (a live database is
never downgraded to base).

**Verified:** reproduced CI's exact three-step sequence against a
from-scratch local PostgreSQL 15 — `alembic upgrade head`, `pytest -m db`
(the same command CI's "Database guarantees" step runs, which is what plants
the reversal row), `alembic downgrade base`, `alembic upgrade head` again —
all clean. `ruff check .` and `mypy src` both clean. Full suite (`pytest -q`)
clean on the resulting database. Not yet confirmed on GitHub Actions itself;
the push that should turn CI green is `45e01fa`.

**Not done / open:** none — this was a pure fix, no follow-up work implied.

---

## 2026-09-23 — Migration 0010: clubs
**Commit(s):** `5d8dc5e`

**Built:** three tables in the `identity` schema — `organizations` (a club:
name, sport, state/LGA, contact phone, `rep_user_id`, `status`
pending_review/approved/suspended, `stage` 1/2), `teams` (a squad within a
club: sport, age category, gender) and `roster_members` (an athlete on a
team: invited/active/released, `jersey_no`, `invited_by`). One default team
is meant to be created alongside every organization at registration, so the
schema matches the spec's three-table shape even though CLB-01–04's screens
never expose team selection. `career_events.club_id` — left bare in
migration 0002 with a comment that it would be checked "once the clubs
context exists" — now has that foreign key. `club.create` is granted to the
`athlete` role, which is the one role every account already holds.

**Why `club.create` moved to `athlete`:** migration 0001 granted it only to
`lga_coordinator`/`state_coordinator`, written before the wireframes existed.
CLB-01 says "any signed-in user" may register a club and becomes its
`club_admin` — in this system that is exactly the `athlete` role, not a new
one. Coordinators keep the permission too, since CLB-01 itself names
coordinator-entered clubs as its own fallback if the self-service screen has
to be cut.

**Why the membership rule is a global partial unique index, not a per-team
one:** the pilot build spec's own sketch was `(team_id, athlete_id)`
uniqueness for an active row. `docs/TODO.md` asks for
*at-most-one-open-membership*, and CLB-03's wireframe explains why: accepting
an invitation "moves" a player from their current club to the new one, so an
athlete can be `active` on at most one roster anywhere, not one per team.
That is `roster_members_one_active_per_athlete`, a unique index on
`athlete_id` alone — the database refuses a second active row regardless of
which team it names, rather than the service having to remember to release
the old one first. A pending `invited` row is scoped per team instead:
different clubs may invite the same athlete at once (CLB-03 warns about
this, it does not refuse it), but the same club cannot queue the same
invitation twice.

**Verified:** `check_migration_safety.py` clean (10 migrations). Applied,
reversed and re-applied cleanly against the live Supabase project (through
the IPv4 pooler). The full suite was then run three times while chasing two
false alarms, both pre-existing and both traced to a stretch of this
session's own making, not to this migration:

1. A first Supabase run showed dozens of setup errors — `OTP_CHANNEL=email`
   was still set in `api/.env` from the pilot-channel work, and every
   registering test needs an email under that setting. Exporting
   `OTP_CHANNEL=sms` for the run fixed it; this is an already-documented
   gotcha, not a new one.
2. The Supabase run then became too slow to trust (connection contention
   after an earlier `kill -9` of a stuck pytest process left connections
   open against the free-tier project's connection cap), so the suite was
   run instead against a local, disposable PostgreSQL 15 that this project's
   own gotchas describe building. It failed twice more, on two tests neither
   of which touches clubs: `test_integrity.py`'s media-object-missing check
   (a stray-data problem — this local instance had accumulated 948 `ready`
   media rows across many sessions today, and the check's own `LIMIT 500`
   random sample only catches the row a given test cares about about half
   the time) and one rate-limit timing test. Dropping and recreating the
   local database, re-running `infra/bootstrap-roles.sql` and `alembic
   upgrade head` from empty, and running the full suite again gave a clean
   pass with zero failures — confirming both were pre-existing environment
   noise, not a regression from this migration.

**Not done / open:** no service layer, no API routes, no screens yet — this
entry is schema only. CLB-01 through CLB-04 and ATH-05 are next, per the
build order already agreed (`docs/TODO.md`).

---

## 2026-09-23 — CRD-04: coordinator pays on behalf
**Commit(s):** `e34ad39`

**Built:** `POST /v1/lgas/{lga_id}/athletes/{kuid}/payments`
(`payment.initiate_behalf`, scope `lga`) and `/assist-pay` — a coordinator
enters an athlete's KUID and is sent to Paystack, exactly one step ahead of
the athlete's own `/pay`. `on_behalf_of` and `coordinator_id` are set on the
row; two new settings, `assisted_payments_per_coordinator_daily` and
`assisted_kobo_per_coordinator_daily`, cap what one coordinator may start in
a day.

**Why the caps exist from the first line, with placeholder numbers:** nothing
here asks the athlete to confirm before their record is charged for, so the
only thing bounding a compromised coordinator session is these two numbers.
No document sets them. Rather than block the feature on a number nobody can
give yet, the code enforces a placeholder (20/day, ₦50,000/day — chosen to be
obviously survivable, not obviously right) and says plainly in three places
(the setting's own docstring, `TODO.md`, `CLAUDE.md`) that it needs the
project lead's real number, ideally from Wave 1's actual figures rather than
guessed in advance of any.

**Two real bugs found while building this, both the kind that only show up
once a second payer exists:**

1. **`mark_paid` would have taken the money and reviewed nobody.** It read
   `AND pay.on_behalf_of IS NULL` — correct while only self-payment existed,
   silently wrong the moment a second kind of payer did. An assisted payment
   would have settled into the ledger exactly as it should, and moved no
   verification to review at all, because the row it looked for belonged to
   the *payer* and the payer is now sometimes not the athlete. Fixed by
   resolving whose draft to move — `on_behalf_of` if set, the payer's own
   athlete row otherwise — rather than assuming there is only one kind of
   answer.
2. **The route's own scope check cannot catch a coordinator naming the wrong
   athlete.** `Requires(..., scope="lga")` reads `lga_id` from the *path* and
   confirms the coordinator holds a grant on it — that is all it can do. It
   has no way to know whether the *athlete named in the same path* is
   actually in that LGA. Get this backwards — trust the permission layer to
   have covered it — and any LGA coordinator could pay for any athlete in the
   country, so long as the `lga_id` segment matched their own grant. The
   check belongs to the service, against the database, not the caller's
   claim: `_athlete_in_lga()` joins the athlete's `current_lga_id` against the
   path before anything else runs.

**Verified:** `tests/test_payments_on_behalf.py`, 10 tests — the ledger and
the review both land on the athlete, the receipt reaches the athlete's phone
and not the coordinator's, an athlete outside the coordinator's LGA is
refused (proved with a real second coordinator scoped to a real second LGA,
not a mock), an athlete with no files yet or already paid is refused, both
caps refuse at the right moment, and a failed attempt does not count against
either cap. Full suite green against a real database, twice. A live HTTP
round trip against the running server (Supabase, through the pooler)
confirmed both the outer 403 (coordinator has no grant at all on the path's
LGA) and the inner 404 (grant matches the path, athlete does not).

One flake surfaced and was chased down rather than waved through: the
existing `test_a_message_is_sent_once…` failed twice in a row on the local
database, which had accumulated **1,109** outbox rows across a day of
repeated full-suite runs, itself worsened by this session's new
`notification.requested` rows (payment receipts, decision emails). Confirmed
as pile-up, not a regression, by clearing the table and rerunning clean.

**Not done / open:** no separate "look up the athlete first" preview step —
the single form either starts the checkout or bounces back with the exact
refusal, unlike ADM-03/04's two-step pattern. Deliberate, for now: proportional
to what a checkout redirect needs versus what withdrawing a badge or writing a
ledger line by hand needs, but worth revisiting once real coordinators use it.

---

## 2026-09-23 — Paystack run against the real sandbox; a launch-blocking bug found
**Commit(s):** *(with the notification work; `api/.env` holds the keys and is not committed)*

**Built:** nothing new — this was *verification*, and it earned its keep. Test
keys arrived, so `PAYMENT_PROVIDER=paystack` was switched on and the adapter
pointed at the live sandbox for the first time since 2.1 was written.

**What it found:**

1. **`.invalid` placeholder emails are refused — this would have broken
   payments at launch.** An athlete need not have an email, so one is invented
   for Paystack, which insists on the field. It was built on
   `payments.kafriada.invalid`: RFC 2606 reserves `.invalid` for exactly this,
   it never resolves, and a receipt sent there can never reach a stranger. It
   is the *correct* choice on paper. Paystack answers `400 "email" must be a
   valid email` and refuses the checkout outright — so **every athlete without
   an email on file could not have paid at all**.
   Worse, a test covered this and asserted the bug: `email.endswith(".invalid")`.
   It passed for months because it ran against `FakeProvider`, which accepts
   anything given to it. A fake proving the opposite of the truth is the whole
   argument for running the real thing before launch and not after.
   Fixed: the default is now `payments.kafriada.ng`, and the test asserts a
   deliverable TLD instead. Domains checked and accepted: `kafriada.ng`,
   `payments.kafriada.ng`, `badellafarmandranch.site`.

2. **`fees` is present, so real payments will not freeze.** `decide()` FREEZES
   a payment whose event carries no fee — a deliberate refusal to guess. Nobody
   had confirmed Paystack actually sends one. It does: ₦2,500 costs **13750
   kobo**, settling at **236250 kobo (₦2,362.50)**. That is also the exact
   figure `.env`'s OPEN QUESTION A1 was waiting on — whether ₦2,500 is the
   price or the take-home is now a decision with a real number behind it.

3. **The money path works end to end against real Paystack.** Our
   `start_payment` created a checkout, a real test card paid it, and our own
   `reconcile()` job settled it: exactly two ledger lines (250000 credit,
   13750 fee debit) and one idempotency row. That is Stage 2 exit criterion 1
   in substance, in test mode.

4. Paystack **rate-limits** `initialize` — 429 after a handful in quick
   succession. Worth knowing before the 200-registration burst test.

**Not done / open:** no webhook has actually been *received* from Paystack —
that needs a publicly reachable URL, so only the reconciliation path is proven
directly. Both feed the same strict reader and the same idempotency key, so the
parsing and settlement halves are covered; the HMAC signature check over a real
Paystack body is not. Live keys still need business verification, which needs a
current CAC registration.

---

## 2026-09-23 — 2.3: the outbox carries every notification, not just SMS
**Commit(s):** *(see below)*

**Built:** a third outbox event type, `notification.requested`, addressed to a
**person** rather than to a phone number or an inbox. The caller supplies both
wordings (`sms` and `subject`/`email`) and says who to tell; the worker looks
up how to reach them and picks the channel when it actually sends.
`outbox.service.prefers_email()` is now the one place the pilot's channel rule
lives, and the OTP path was changed to call it too, so the two cannot drift.

Wired to the two things that needed it:
* **All four verification decisions** (approved, rejected, escalated, revoked),
  which previously only ever queued SMS and so reached nobody while Twilio is
  unregistered.
* **A payment receipt on settlement**, which did not exist at all. It goes to
  the athlete the payment is *for* (`on_behalf_of`), not to whoever pressed
  pay — which is what makes it half of the Stage 2 exit criterion "a
  coordinator pays for someone else and that person receives the receipt". The
  other half is the coordinator flow itself, in 2.4.

**Why addressed to a person rather than an address:** two reasons, and the
second is load-bearing. A number changed between queueing and sending is still
the one used. And **a caller with no grant on `ops.users` can still notify
somebody** — settlement runs as `kaf_money`, which by design cannot read that
table at all, so if the address had to be resolved by the caller, a payment
could not send its own receipt. That constraint was found by checking the
grants rather than assumed: `kaf_money` has `INSERT` on `ops.outbox` and
`SELECT` on `identity.athletes`, and nothing on `ops.users`.

Someone unreachable is a **permanent** failure, not a retry — there is no
number to try again later — and the row is kept as the evidence that nobody
was told.

**Verified:** `tests/test_notifications.py`, six new tests, including the
money-role case that connects as `kaf_money`, asserts the `ops.users` read is
refused, and then queues and delivers a notification to that same person
anyway. The settlement, OTP/outbox and verification suites all re-run clean
(70 tests), plus the full suite. Writing the tests found two real things: the
delivered-row scrub was dropping `user_id`, which is the only link from a sent
message back to who was told (now kept), and `phone_e164` is `NOT NULL`, so
"unreachable" in this schema means anonymised rather than blank.

**Not done / open:** the receipt wording is plain text; no HTML template like
the OTP email has. Nothing yet notifies on a payment that *fails* or freezes —
deliberate, since a frozen payment is an alarm for a person to look at, not
something to tell the athlete about automatically.

---

## 2026-09-23 — Supabase reachable again: the direct endpoint is IPv6-only
**Commit(s):** *(config + docs; `api/.env` is gitignored and not committed)*

**Built:** nothing in the application — this was a connection problem, and the
fix is configuration. `api/.env`'s four `DATABASE_URL_*` now point at
Supabase's Supavisor pooler instead of the direct endpoint:

    host  aws-1-eu-west-1.pooler.supabase.com
    port  5432                       (session mode)
    user  <role>.slwlefnfdsjfeimyjhag

The old direct URLs are kept commented above each one, and
`.env.backup-before-pooler` holds the original file.

**Why:** `db.<ref>.supabase.co` resolves **IPv6-only** — Supabase ran out of
IPv4 addresses — so on a network without working IPv6 the name resolves and
the TCP connect then hangs to timeout. That is the whole of the "Supabase is
down" story that ran through 2026-09-20 to 09-23: the project was healthy the
entire time and the dashboard was right to say so; this machine simply could
not route to that address. The pooler publishes A records and is reachable.
Credit where due — the project lead pushed back on the diagnosis and asked
whether IPv4 could be used, which is exactly what unblocked it.

Two choices inside that fix worth keeping:
* **Session mode (5432), not transaction mode (6543).** `kafriada.jobs` takes
  *session-level* advisory locks and psycopg auto-prepares statements; neither
  survives transaction pooling. Session mode behaves like a direct connection,
  so no application code changed at all.
* **`<role>.<ref>` usernames keep all four roles distinct**, so the privilege
  boundary — the thing every other invariant leans on — is untouched. Verified
  by connecting as each of the four and reading back `current_user`.

Also note: `aws-0-eu-west-1` is a *different* tenant cluster. It answers, then
refuses with `ENOTFOUND tenant/user`, which reads like a credentials problem
and is not one.

**Verified:** all four roles connect and report their own identity; `/readyz`
(which probes every role) returns `{"status":"ready"}`; the web tier renders
live LGA data from Supabase through the API; migration 0009 applied to
Supabase, bringing it to the same head the local database was on.

**Also cleared while the link was up:** the throwaway super_admin account made
for ADM-04's live check. It could **not** be deleted — `ledger_entries
.recorded_by` still references it and the ledger is append-only, so the
database refused to erase the authorship of a ledger line. That is the
invariant doing its job, so the account was neutralised instead: password
cleared, role grant removed, sessions deleted, `status='anonymised'`. The
ledger line it authored stays.

---

## 2026-09-23 — ATH-02: edit my details
**Commit(s):** `ef30b84`

**Built:** migration 0009 — four nullable columns on `identity.athletes`
(`gender`, `dominant_side`, `secondary_sport`, `years_experience`), each
CHECK-constrained to a small fixed set. `get_athlete_details()` /
`update_athlete_details()` in `contexts/identity/service.py`; `GET`/
`PUT /v1/athletes/me`; `/details`, one form, sport and position shown for
context but not editable there.

**Why:** the permission model was already waiting for this —
`athlete.read_self` and `athlete.update_self` have been seeded for the
`athlete` role since migration 0001 (Stage 0), with nothing behind either
until now. The four fixed-set CHECKs over a lookup table: none of the four
is likely to grow a fifth option that needs its own migration, and a CHECK
is one statement instead of a table, a foreign key and a seed data insert.

**Verified:** against a private local PostgreSQL 15, stood up fresh for
this (`initdb`/`pg_ctl`/`bootstrap-roles.sql`/`alembic upgrade head`,
per `CLAUDE.md`'s documented recipe) because Supabase had been unreachable
all session — confirmed at the TCP level with nothing else running
(pool contention had been the cause of an earlier batch of failures that
same day; this was the link itself, checked in isolation). Migration
applies and reverses cleanly; `check_migration_safety.py` clean; a live
GET → PUT(valid) → PUT(invalid, correctly refused with the right field) →
GET loop against a real registered athlete; `test_permission_matrix.py`
and `test_route_manifest.py` both pass; a full `check:render` run —
including, for the first time, a signed-in contrast/overflow audit of
`/details` and `/payments` themselves via `EXTRA_SESSIONS` — all pass.

**Not done / open:** migration 0009 not yet applied to Supabase — repeat
once it's reachable. Two choices the migration flags for the project lead
to confirm before launch: the four gender options offered, and the 0–100
bound on years of experience — neither is pinned down by the spec as built
here. Also fixed in passing: `docs/TODO.md`'s screen-built count (said 12,
was actually 22) and its "empty contexts" line (said `media` and
`verification` were empty; they haven't been since 2.2) — both corrected.

---

## 2026-09-22 — ATH-04: my payments
**Commit(s):** `a2db088`

**Built:** `list_payments()` — every payment the caller has ever started,
newest first, same shape as the existing single-payment lookup. `GET
/v1/payments` (same `payment.read_self` permission the single-payment route
already uses). `/payments`: one card per payment — purpose, reference, date,
amount, and the same confirmed/checking/needs-a-check/not-completed language
`/pay` already uses, never the internal status. Linked from `/me`. New
`.pill--bad` CSS variant, for "not completed".

**Verified:** full non-DB suite (no regressions), `npm run typecheck`,
`npm run build`. `check:render`'s other failures (profile/card 404, register
JS-off) are the same Supabase-outage signature as the ADM-03/ADM-04 entries
below — confirmed unrelated (TCP-level).

**Not done / open:** not yet checked signed-in against live data — Supabase
was still down. Repeat once it's back.

---

## 2026-09-22 — This file
**Commit(s):** `7270af8`

**Built:** `docs/BUILD-LOG.md` itself, at the project lead's direct request:
a standing, chronological, append-only record of every piece of engineering
work, kept distinct from the developer's own `TEST-LOG.md`/`ISSUE-LOG.md`/
`DEVELOPER-PROGRESS.md`. Backfilled 17 entries from `git log` and
`CLAUDE.md`'s Status section, covering Stage 0 (2026-09-09) through that
day's ADM-04. `CLAUDE.md` now points here and carries the going-forward
rule: an entry per build session, alongside its commit(s).

---

## 2026-09-22 — ADM-04: record a refund
**Commit(s):** `f287008`

**Built:** `GET /v1/admin/payments/{reference}` — a lookup the reversal API
never had (the existing `POST .../reversal` only ever took a reference an
admin already had from Paystack's own dashboard, with nothing to preview it
against first) — and `/admin/reversal`, the screen: look up by reference,
then an amount, reason and password to confirm. Same two-step shape as
ADM-03, since this is the one screen that writes an amount into the ledger
by hand.

**Why:** `record_reversal()` itself was untouched — it already re-checks the
password, refuses anything not settled or already refunded, and caps the
amount at what was actually paid. The gap was purely "how does an admin see
what they're about to touch before typing a number in."

**Verified:** live, end to end, against Supabase with a real minted
super_admin token: looked up a settled payment (`reversible: true`), looked
up a pending one (`reversible: false`), recorded a refund, confirmed
`already_reversed: true` on re-lookup, and a second attempt was correctly
refused (409). One real bug found and fixed in the process: the lookup used
`money_transaction()` (the `kaf_money` role), which has no grant on
`ops.users` or `identity.athletes` at all — switched to the ordinary
`transaction()` (`kaf_app`), which already has SELECT on `money.payments`
and `money.ledger_entries` (migration 0006's append-only grants). Permission-
matrix test passed the same session (it discovers routes automatically, so
the new one needed no manual entry). `npm run typecheck` and `npm run build`
pass.

**Not done / open:** `test_verification.py` and `test_settlement.py` were
not re-run against this specific change — Supabase's link dropped mid-
session (a bare, unloaded connection attempt timed out; not contention, see
`CLAUDE.md` Gotchas). Run both once it's back.

---

## 2026-09-22 — ADM-03: withdraw a verification
**Commit(s):** `00565a6`

**Built:** `find_by_kuid()` + `GET /v1/admin/verification/by-kuid/{kuid}` —
the API-only `revoke` route (built in 2.2) had no way for a super_admin to
get from a KUID to the request id it needs. `/admin/revoke` is the screen:
look up by KUID, see the athlete and current status, and if it's approved,
a reason and password form to withdraw it.

**Verified:** permission-matrix test passed against Supabase. The lookup
live-checked with a real super_admin token against a real approved request
(`revocable: true`) and a real draft one (`revocable: false`) — both
correct. `revoke()` itself is covered by
`test_verification.py::TestApprovalAndWithdrawal`, which passed. A live curl
of the revoke POST specifically was inconclusive — Supabase's link dropped
mid-attempt — not a failure.

**Not done / open:** the revoke POST itself has not been confirmed by a live
curl call (only via the pre-existing automated test and the in-app flow).

---

## 2026-09-22 — Downloadable wallet card, PNG and PDF
**Commit(s):** `30900a9`

**Built:** `contexts/identity/card.py` draws the card — wordmark, KUID,
name, sport, LGA, the same signed QR the on-screen card uses — with Pillow
(already a dependency), saved as either PNG or a one-page PDF from the same
drawing. `GET /v1/public/athletes/{kuid}/card.png` and `.../card.pdf`, same
`Public`/404 shape as the existing `qr.svg` route, proxied from the web tier
the same way. Three font families (Instrument Serif, Atkinson Hyperlegible,
JetBrains Mono — the same ones the website uses) vendored into
`assets/fonts/` from Google's font repository, OFL licence files included.

**Why:** generated server-side rather than in the browser, because a print
dialog's own "save as PDF" isn't available on every browser this project
targets (Opera Mini among them), so the file needed to be produced directly
rather than assumed. The background is a faint repeating ring — the same
idea as a certificate's security pattern — rather than illustrated icons:
this is a permanent ID, and restraint suited it better than decoration.

**Verified:** rendered and visually inspected; both formats generate
correctly through the live API and the web proxy for a real athlete
(headers, filenames, content-type all correct). Full API test suite,
`npm run typecheck`, `npm run build` and `check:render` all pass.

**Not done / open:** no photo on the card even for verified athletes (the
public profile only exposes one after Stage-2 approval — could be composited
in as a follow-up).

---

## 2026-09-22 — Email at registration, branded Flash + live resend countdown
**Commit(s):** `ee812a2`

**Built:** the register form gained an email field (required only while the
interim email OTP channel is on — see the entry below); the confirm page
says "Sent by email to …" when that's what happened. `components/Flash.tsx`
replaced copy-pasted `.notice` divs on register, sign-in, forgot and confirm
with one component: entrance animation, auto-dismiss on success, focus-on-
error, all inert without JavaScript (renders the same static markup either
way). `components/ResendCountdown.tsx` makes "ask again in N seconds" tick
live and disables the button, re-enabling automatically at zero — with JS
off, the real, always-clickable form is what's there from first paint, and
the server still enforces the wait either way.

**Why:** house rule written down the same day (see `CLAUDE.md`, "Working
style"): copy must read as plain product writing, not AI-generated filler —
prompted by a hint here needing rephrasing.

**Verified:** `npm run typecheck`, `npm run build`, and `check:render`
(contrast, overflow, JS-off round trips) all pass. `check:render` also
caught a real bug mid-build: the Flash bad/warn/good icon was invisible
(`#fffdf7` on `#fffdf7`, a `currentColor` mistake) — found, fixed, confirmed
at 0 low-contrast.

---

## 2026-09-22 — Email delivery via Resend, OTP pilot channel
**Commit(s):** `356c78b`

**Built:** a second, independent notification channel alongside SMS, since
Twilio still has no Nigerian sender ID (see `CLAUDE.md`, "Outside the
code"). `outbox/email_providers.py`: a `Sender` port (`NoSender` /
`ConsoleSender` / `ResendSender`), same transient/permanent failure split as
the Twilio SMS adapter. `contexts/access/email_templates.py`: branded HTML
for the OTP email, table-based and inline-styled so it survives Gmail and
Outlook, using the same document colour tokens as the web app. The outbox
(`outbox/service.py`, `outbox/dispatch.py`) now routes `sms.requested` and
`email.requested` rows to their own sender in one worker. New
`OTP_CHANNEL` setting (`sms`/`email`) — a pilot stand-in, refused in
production — that sends phone-verification and password-reset codes by
email instead of SMS when the account has an email on file; the phone
stays the identity anchor and still gets marked verified. No email on file
still falls back to SMS.

**Verified:** 13 new unit tests plus the full non-DB suite pass; the DB-
backed OTP/outbox tests pass against Supabase; a real registration
delivered a real HTML-templated code to a real inbox via Resend.

**Not done / open:** email is not yet a trigger for anything besides OTP —
verification decisions and payment confirmations still only queue SMS.

---

## 2026-09-21 — 2.3, the safety net: jobs runner, reconciliation, expiry, integrity, refunds
**Commit(s):** `858feb0`, `a801e42` (status)

**Built:** migration 0008 (`ops.job_runs`, an insert-only record of every
background job's run; `GRANT DELETE ON ops.outbox`; a ledger `reversal`
source with `note`/`recorded_by`). `python -m kafriada.jobs` — one process,
no broker — running outbox drain, media re-encoding, reconciliation (every
10 minutes), expiry, session/rate-counter/document sweeps, and a nightly
integrity check, each holding its own Postgres advisory lock so one failing
job never stops the others. `contexts/payments/reconcile.py`: asks
Paystack's verify API and settles only a confirmed `success`, never
reverses anything itself. `expire_stale()`: only `pending` payments older
than 72 hours that Paystack does not say were paid. `integrity.py`: findings
rather than verdicts, checking ledger shape, KUID uniqueness and the
counter, verification consistency, and that media objects exist.
`contexts/ledger/reversal.py`: `record_reversal()` — recording a refund made
by hand in Paystack's dashboard, never calling Paystack itself.

**Verified:** 681 passed / 0 skipped on the local DB. Mutations proved red:
verify status ignored, expiry without asking, wrong-reference acceptance,
integrity checks disabled, missing lock, missing password, no cap, sweeps
too greedy. Found and fixed on the way: `amount_kobo` accepted `"100000"`
and `true` under pydantic's lax parsing — now `StrictInt`; the
`kuid_counters.next_serial` column held the last serial issued, not the
next one (caught by a first, wrong integrity check).

**Not done / open:** never run against real Paystack; the job runner has
never run under a process supervisor on an actual host; nothing pages a
human yet (needs a Sentry alert rule); ADM-04's screen was still unbuilt at
this point (see the 2026-09-22 entry above).

---

## 2026-09-21 — 2.2: media pipeline, verification service and screens
**Commit(s):** `b94dbed`, `aca04f4`, `5c550ae` (status)

**Built:** migration 0007 (`identity.media_files`, `verification_requests`
with the full state machine including `revoked` and `escalated`, resubmission
capped at three attempts; append-only `verification_decisions`).
`contexts/media/`: an object-store port (local disk, R2, or none), a slot →
upload → confirm-only-if-the-object-exists → re-encode-to-a-fresh-JPEG
pipeline that strips EXIF and applies orientation first, with bomb/format
guards and a 30-day document purge. `contexts/verification/service.py`: the
reviewer rules (never your own record) and the state machine; payment
success moves a request to `under_review` inside the same ledger
transaction. Web: `/verify` (upload, status, resubmit), `/review` (one case
at a time, approve/reject/skip), `/photo/[kuid]` and proxied review-media
routes so images never carry a bucket URL.

**Why (R2 signer):** hand-built rather than borrowed, and proved against
Amazon's own published SigV4 test vector before trusting it with real
uploads.

**Verified:** 565 passed / 0 skipped, twice. Mutations proved red: EXIF
kept, own-record review allowed, LGA scope dropped, a photo public before
approval, no escalation on the third rejection, no password required to
withdraw, direct `UPDATE` grants and the decisions trigger disabled.
`check:render` audited every state's screen and found two real contrast
bugs (ghost/filled buttons on documents in dark/light) — fixed in
`globals.css`.

**Not done / open:** never run against a real R2 bucket; the direct-to-
bucket presigned upload exists but no JavaScript path uses it yet; Pillow's
handling of HEIC untested (refused as "not JPEG/PNG/WebP" — iPhones may be
common); SMS on a decision is queued but nothing sends it without a
configured provider; the wireframe's cash route and coordinator-contact-on-
escalation are both absent.

---

## 2026-09-20 — 2.1 complete: payment webhook, checkout start, VER-03
**Commit(s):** `f7269e9`, `2497d1b` (status)

**Built:** `POST /v1/payments/webhook/paystack` (raw body → HMAC signature
check → parse → settle; a bad or missing signature changes nothing; always
200 after a valid signature, even for events it doesn't act on, so Paystack
never needlessly redelivers). `POST /v1/payments` (starts a charge; the
price is the server's, never the client's), `GET /v1/payments/quote`,
`GET /v1/payments/{reference}` (own payments only). `contexts/payments/
provider.py`: a port with `PaystackProvider` (https-only, an 8-second
deadline), `FakeProvider` (local only) and `NoProvider`. Web: `/pay` — start
and return in one address, works with JavaScript off, "Check again" is a
plain link.

**Verified:** 456 passed / 0 skipped; `check:render` passes for `/pay`'s
start view. Demonstrated locally by posting a self-signed `charge.success`
against the fake provider.

**Not done / open:** never run against the real Paystack sandbox (payload
shapes and whether `fees` is present are both unconfirmed); the confirmed/
failed/review return states were read as text but not contrast-audited; no
SMS on confirmation (that's 2.4).

---

## 2026-09-20 — 2.1 core: money tables and the settlement service
**Commit(s):** `16d02cf`, `ce41809` (pure rules), `8fd22b5` (status)

**Built:** `contexts/payments/rules.py` — strict parsing of a
`charge.success` event and `decide()`, which approves only on an *exact*
NGN amount match and freezes everything else, never approving on a
mismatch. `contexts/ledger/entries.py` — a settled payment is exactly two
lines, the gross credit and the provider-fee debit. Migration 0006 (the
`money` schema): `payments` (a guard trigger makes the agreed fields and a
final `success` immutable), insert-only `ledger_entries` and
`webhook_events`, both `REVOKE ALL` then `SELECT`/`INSERT` for `kaf_money`
only, plus the same append-only trigger the audit log uses so not even the
table owner can edit a row. **Decided: no wallets** — ledger lines belong to
the payment, not to a per-athlete balance. `contexts/payments/
settlement.py`: idempotent (`INSERT … ON CONFLICT DO NOTHING RETURNING` on
`webhook_events`, so a redelivery is a safe no-op), one transaction, one
commit.

**Verified:** 389 passed / 0 skipped on the local database, including five
concurrent copies of the same webhook × six rounds → exactly two ledger
rows every time. Mutations proved red: read-then-insert dedupe (a real
race), no dedupe at all, always-settle, granting `kaf_app` INSERT or
`kaf_money` UPDATE/DELETE, the owner trigger disabled.

---

## 2026-09-20 — Per-address rate limits, verified on a real database
**Commit(s):** `f8db7ff` (code), `4b68ca8` (fixes), `4a8c399`, `e0f605e`
(status)

**Built:** `contexts/access/ratelimit.py` — counted in Postgres, not Redis
(six endpoints at pilot volume don't justify a second service).
`Throttle("bucket")` on sign-in, send-code, confirm-code and register.
Migration 0005 (`ops.rate_counters`); the sweep of closed windows piggybacks
on the outbox worker's own loop.

**Why not Redis:** `settings.redis_url` is kept (marked unused) for the day
Paystack-webhook idempotency might want a cache, but a handful of counters
at pilot traffic is not that day.

**Verified 2026-09-20 against a private local PostgreSQL 15** (Supabase was
unreachable that day). Migrations 0001→0005 applied clean; all 9 rate-limit
tests passed three runs in a row; 360 passed / 0 skipped with the database
attached. Running it for real found three faults every non-database test
had missed: (1) the HTTP error handler dropped every response header, so a
429 lost its `Retry-After`; (2) the tests reused the same source IPs every
run, so a re-run inside the hour failed on its own first request; (3) the
local role-bootstrap SQL lacked `GRANT CREATE ON DATABASE` to the migration
role, so a fresh local database failed its first migration. All three
fixed the same day.

**Not done / open:** still worth repeating against Supabase once reachable
(noted repeatedly since — see the 2026-09-22 ADM entries above for what
"Supabase reachable" looked like weeks later).

---

## 2026-09-17 — A developer's agent, and two logs to keep
**Commit(s):** `f9a2bf6`, `0ebd747`

**Built:** `docs/TEAM-AGENT-BRIEF.md` — the brief for a separate agent
coaching a human developer through testing the build, including what
belongs in `docs/TEST-LOG.md` versus `docs/ISSUE-LOG.md`, and
`docs/DEVELOPER-PROGRESS.md` to track how that developer is coming along,
openly.

**Why this file exists too:** those three documents are about the
developer's own testing sessions. Nothing before this build-log entry
tracked the engineering work itself, chronologically, in one place — this
file (added 2026-09-22, backfilled from `git log` and `CLAUDE.md`'s Status
section) is that record.

---

## 2026-09-12 — OTP through a transactional outbox; Sentry, readiness, gated migrations
**Commit(s):** `962b3f7`, `bb578ac`, `f8db7ff` (see rate-limits entry above)

**Built:** ADR 0003 — SMS behind a provider port, Twilio first. Migration
0004: `ops.outbox` and `ops.otp_codes`. A code is queued in the same
transaction as the record it belongs to; `python -m kafriada.outbox.dispatch`
drains it. **The KUID is minted before the code is confirmed** (per the
AUT-02 wireframe), so a provider outage delays a confirmation, never a
registration. Web: `/register/confirm`, `/forgot`. Separately: Sentry wired
and scrubbed (inert without a DSN), `/readyz` (checks the database on every
role, 503 otherwise), `scripts/release.sh` and
`scripts/check_migration_safety.py` gating migrations, Dockerfiles for both
tiers.

**Not done / open at the time:** no Twilio credentials yet (`SMS_PROVIDER=
none` kept codes queued) — still true as of the 2026-09-22 email-pilot-
channel entry above, which is precisely why that channel exists.

---

## 2026-09-11 — Access: sessions, sign-in, scoped permissions, the permission matrix
**Commit(s):** `63c8782`; privacy fixes `8efdde4`, `659a608`; handoff `f733fb2`

**Built:** ADR 0002 — a revocable session cookie, not a third-party auth
service. `POST`/`DELETE /v1/sessions`, `GET /v1/me`, super_admin role grant/
revoke and end-all-sessions, LGA-scoped athlete search. `access.can()`
behind `Requires(permission, scope=)`. Migration 0003. Web: `/sign-in`,
`/me`, sign-out. `test_permission_matrix.py` — 12 principals × 12 routes,
two tenants, generated from the live app and the database's own role-
permission table rather than hand-written (this is the same test that
later verified ADM-03 and ADM-04 without any manual updates).

**Also fixed the same day:** a duplicate phone number no longer reveals
whose it is (detected only by the unique-index name, so still no second
KUID minted); registration copy stopped promising an SMS code before any
provider could send one.

---

## 2026-09-11 — Web: registration, the issued card, the public profile
**Commit(s):** `192f39e`, `b4172f2` (JS-off fix)

**Built:** the first three real screens — `/register`, the card handed over
immediately on success, and the public profile a QR code resolves to.
**Every screen works with JavaScript off**, by design, for the Opera Mini
proxy-browser reality of the pilot's actual users — caught for real the same
day, when registration turned out to be broken with JS off, and a render
check was added on the spot rather than trusted to stay working.

---

## 2026-09-10 — Registration API, public profile, signed QR; the database proved live
**Commit(s):** `3d6c176`, `d7c2e4e`, `ba69605`, `3c46b6b`

**Built:** the register/public-profile/QR API endpoints. The Supabase
database connected for the first time and its security guarantees —
role separation, the audit trigger, KUID immutability — were demonstrated
live (`scripts/demo_security.py`) rather than only asserted in a test.
Registration and the KUID mint were proved under real concurrent
contention: two hundred people registering in the same minute must never
collide on the counter row for longer than milliseconds.

---

## 2026-09-09 — Stage 0: the foundation
**Commit(s):** `6e450fd`, `6840572`

**Built:** the repository itself, the four-role database privilege
boundary (`kaf_app`, `kaf_money`, `kaf_reader`, `kaf_migrate` — the
architecture every later invariant leans on), the audit log's append-only
trigger, and the identity anchor: KUID structure, phone normalisation, the
Jigawa LGA table. Nothing runs yet without a database, but the shape
everything else was built inside was decided here.

---

*Entries above this line were reconstructed 2026-09-22 from `git log` and
`CLAUDE.md`'s Status section, to give this log a complete history from the
project's start rather than only from the day it was created. Going
forward, add a new entry here — newest at the top — at the end of each
build session, before or alongside the commit it describes.*
