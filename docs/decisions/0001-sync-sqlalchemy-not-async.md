# ADR 0001 — Synchronous SQLAlchemy, not async

**Status:** Accepted · 9 September 2026
**Context:** Stage 0 foundations

## Context

The target architecture describes FastAPI with "async I/O for the webhook and
Paystack path". FastAPI is async-first, so async SQLAlchemy is the default
expectation. This decision deviates from that and needs recording, because a
reader of the architecture document will otherwise think the implementation
drifted by accident.

The hardest problems in this system are not I/O concurrency. They are:

- A **single contended row** — `identity.kuid_counters` — that every registration
  in the state serialises on. Lock hold time is the throughput ceiling.
- A **ledger that must balance**, written inside transactions that span two
  schemas and must be all-or-nothing.
- `SELECT … FOR UPDATE` semantics that have to behave exactly as documented.

The actual load is small: 5,000 athletes, a peak burst of roughly 200
registrations per minute, and a public read surface that is answered at
Cloudflare's Lagos edge and never reaches the origin.

## Decision

Use **synchronous SQLAlchemy 2.0 with `def` endpoints**. FastAPI runs sync
handlers in a thread pool. Outbound HTTP to Paystack uses a sync `httpx` client
with strict timeouts.

## Consequences

**What this buys.** Transaction boundaries are visible in the code and cannot be
accidentally suspended: there is no `await` that could yield inside a held lock,
which in an async codebase is an easy way to turn a 2ms lock hold into a 200ms one
and collapse registration throughput. Row locking behaves exactly as the
PostgreSQL manual describes. Stack traces are complete. Every library in the money
path has a mature sync API.

**What it costs.** Concurrency is bounded by the thread pool rather than the event
loop, so a slow Paystack call occupies a worker thread instead of yielding. At
pilot load this is comfortably within budget; at roughly 40 default workers and an
8-second Paystack timeout, the theoretical worst case is still far above expected
traffic. Argon2id hashing is separately capped by its own semaphore, so it cannot
consume the pool.

**When to revisit.** Only with a measurement showing the thread pool is the
bottleneck — not on principle, and not because async is the newer style. The
public read surface is edge-cached, so the origin sees a small fraction of total
requests; the pool is unlikely to be the constraint before the Year-1 target.

## Alternatives considered

**Async SQLAlchemy throughout.** Higher ceiling on I/O concurrency, which this
system does not need. Costs correctness clarity in exactly the two places where
correctness is the whole product.

**Async for reads, sync for writes.** Two idioms in one codebase, with the
boundary between them being a thing a solo developer has to remember at 1am. The
worst option of the three.
