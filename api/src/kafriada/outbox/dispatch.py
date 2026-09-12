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

from kafriada.main import configure_logging
from kafriada.outbox import service
from kafriada.outbox.providers import build_sender
from kafriada.settings import SmsProvider, get_settings

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

    if cfg.sms_provider is SmsProvider.NONE:
        pending = service.pending_count()
        print(  # noqa: T201 — a command-line tool talking to its operator
            "No SMS provider is configured (SMS_PROVIDER=none), so nothing can be sent.\n"
            f"{pending} message(s) are waiting in ops.outbox and will go out once\n"
            "SMS_PROVIDER and the provider's credentials are set."
        )
        return 1

    sender = build_sender(cfg)
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    log.info("outbox_started", provider=sender.name, once=args.once)

    while not _stopping:
        result = service.drain(limit=args.batch, sender=sender)
        if result.sent or result.retried or result.failed:
            log.info("outbox_pass", sent=result.sent, retried=result.retried,
                     failed=result.failed)
        if args.once:
            break
        time.sleep(args.interval)

    return 0


if __name__ == "__main__":
    sys.exit(main())
