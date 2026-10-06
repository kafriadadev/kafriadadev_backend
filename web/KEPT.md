# Kept from the old frontend

The KAFRIADA NET redesign (`docs/design/KAFRIADA-NET-Frontend-Design-Plan.pdf`)
starts from bare markup. Every file below carried over because it decides how
the product *works*, not how it looks. Nothing else may be reused without a line
here.

## Plumbing (unchanged)

| File | Why |
|---|---|
| `src/lib/api.ts` | The only door to the API: timeouts, error parsing, field-level errors. |
| `src/lib/session.ts` | httpOnly session and pending-registration cookies. |
| `src/lib/money.ts` | Integer-kobo money formatting. |
| `src/lib/profile.ts` | The athlete record's fixed choices, mirrored from the API's validator. Adds `PILOT_SPORT` (football only). |
| `src/lib/clubProfile.ts` | The club record's fixed choices, mirrored from the API's validator. |
| every `actions.ts` | The server actions that make no-JavaScript forms work. |
| route handlers: `qr/`, `card/[kuid]/card.png`, `card.pdf`, `photo/`, `review-media/`, `admin/club-verification/[id]/document`, `coordinator/cards/pdf` | Proxy files from the API. No markup. |
| `next.config.ts` | Security headers, including `Referrer-Policy: same-origin` (without it, no-JS form posts 500). |
| `scripts/check-render.mjs` | Proves every page renders and every form round-trips with JavaScript off. Extended, not replaced. |
| `Dockerfile`, `.dockerignore` | Deployment. |

## Reduced to bare markup (rebuilt in Phase 2)

Pages keep their data loading, their forms and their copy; every class name,
the stylesheet and its fonts are gone. The shared components keep their props
so the pages still compile, and render plain semantic HTML: `PageHead`, `Flash`,
`SubmitButton`, `ResendCountdown`, `SubNav`, `AdminShell`, `CoordinatorNav`,
`Stat`, `EmptyState`, `NoAccess`, `Pager`, `VerificationBadge`, `ClubFields`,
`SiteHeader`, `SiteFooter`.

## Product rules that carry over (not code)

- "Issued by KAFRIADA NET" on the profile; the line telling a scout to check the face.
- The public profile never shows phone, date of birth or documents.
- Every error shows a reference code.
- The printed card does not invert in dark mode.
- IDs set in a font where 0/O and 1/l cannot be confused.
