# ADR 0003 — SMS through a provider port, with Twilio first

**Status:** Accepted · 12 September 2026
**Context:** Stage 1.4 / 2.3 — one-time codes and the transactional outbox

## Context

Every document in this project names **Termii** as the SMS provider, and its
sender-id approval (3–10 business days) has been on the blocked list since the
start. Nobody has applied for it. The product owner now says the credentials
arriving will be **Twilio's**.

Meanwhile the thing that actually matters — a person cannot confirm their phone
number — was blocked on a decision that is one class in one file.

## Decision

Sending is a **port with adapters**: `outbox/providers.py` defines `Sender`, and
the queue never knows who sends.

- **Twilio** is the first adapter (`TwilioSender`), configured by
  `SMS_PROVIDER=twilio` plus account SID, auth token, and either a Messaging
  Service SID or a from-number. A Messaging Service is preferred: it holds the
  sender-id registration a Nigerian route needs.
- **`none`** is the default, and it is a working state, not a broken one:
  messages stay queued in `ops.outbox`, registrations still succeed and still
  mint IDs, and the codes go out when credentials exist. This is how the system
  runs today.
- **`console`** prints instead of sending, for local development, and the
  settings refuse it outside local — a one-time code in a log file is a code
  anybody with the log can use.
- **Termii** stays in the settings and can return as a second adapter; nothing
  outside that one file would change.

Failures are sorted into transient (retry with backoff: 30s, 2m, 10m, 30m) and
permanent (fail once, keep the row as evidence).

## Consequences

- The Termii sender-id application is no longer on the critical path. A Twilio
  account, a Nigerian sender identity and its regulatory registration are —
  Nigeria requires registered alphanumeric sender IDs, and that paperwork has
  the same shape as Termii's did. **Nobody has started it.**
- Until credentials exist, the pilot can register athletes and issue IDs but
  cannot confirm a phone number in the field. The wireframes already require
  that the ID is minted before the code is confirmed, so this degrades exactly
  as designed.

## Revisit if

- Twilio's Nigerian delivery rates or price disappoint in the pilot. Swapping
  adapters is one class and one environment variable, which was the point.
