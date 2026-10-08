"""The outbox worker.

    python -m kafriada.outbox.dispatch --once      # drain what is due, then stop
    python -m kafriada.outbox.dispatch             # keep draining, every 5s

Run as many as you like: rows are taken with FOR UPDATE SKIP LOCKED, so workers
never collide. Scheduling this properly — a service unit, a container, a cron —
belongs to the deploy pipeline (0.6). Until then it is started by hand, and the
queue simply waits when nothing is running, which is the behaviour that was
asked for: an outage delays a code, it never loses a registration.
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from types import FrameType

import structlog
from sqlalchemy.exc import OperationalError

from kafriada.contexts.access import ratelimit
from kafriada.main import configure_logging
from kafriada.outbox import email_providers, service
from kafriada.outbox.providers import build_sender
from kafriada.settings import EmailProvider, SmsProvider, get_settings

log = structlog.get_logger(__name__)

_stopping = False


def _stop(_signum: int, _frame: FrameType | None) -> None:
    global _stopping
    _stopping = True
    log.info("outbox_stopping")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send queued messages.")
    parser.add_argument("--once", action="store_true", help="drain once and exit")
    parser.add_argument("--interval", type=float, default=5.0, help="seconds between passes")
    parser.add_argument("--batch", type=int, default=20, help="messages per pass")
    args = parser.parse_args(argv)

    cfg = get_settings()
    configure_logging(cfg)

    if cfg.sms_provider is SmsProvider.NONE and cfg.email_provider is EmailProvider.NONE:
        pending = service.pending_count()
        print(  # noqa: T201 — a command-line tool talking to its operator
            "No SMS or email provider is configured, so nothing can be sent.\n"
            f"{pending} message(s) are waiting in ops.outbox and will go out once\n"
            "SMS_PROVIDER or EMAIL_PROVIDER and its credentials are set."
        )
        return 1

    sender = build_sender(cfg)
    email_sender = email_providers.build_sender(cfg)
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    log.info(
        "outbox_started", sms_provider=sender.name, email_provider=email_sender.name,
        once=args.once,
    )

    # Closed rate-limit windows are swept here rather than by a second worker:
    # this loop already runs continuously, and the sweep is one indexed DELETE.
    # An hour between sweeps is plenty for rows whose shortest window is an hour.
    last_pruned = 0.0
    DB_RETRY_SECONDS = 15
    PRUNE_EVERY = 3_600.0

    while not _stopping:
        try:
            result = service.drain(limit=args.batch, sender=sender, email_sender=email_sender)
        except OperationalError:
            # The database could not be reached (a dropped link, a DNS blip). Nothing was
            # sent or marked, so waiting and trying again loses nothing; a run with --once
            # reports the failure instead.
            if args.once:
                raise
            log.warning("outbox_database_unreachable", retry_in_seconds=DB_RETRY_SECONDS, exc_info=True)
            time.sleep(DB_RETRY_SECONDS)
            continue
        if result.sent or result.retried or result.failed:
            log.info("outbox_pass", sent=result.sent, retried=result.retried,
                     failed=result.failed)

        now = time.monotonic()
        if args.once or now - last_pruned >= PRUNE_EVERY:
            last_pruned = now
            try:
                if removed := ratelimit.prune():
                    log.info("rate_counters_pruned", removed=removed)
            except Exception:
                # Housekeeping must never stop messages going out.
                log.warning("rate_counter_prune_failed", exc_info=True)

        if args.once:
            break
        time.sleep(args.interval)

    return 0


if __name__ == "__main__":
    sys.exit(main())
