"""The media worker.

    python -m kafriada.contexts.media.worker --once     # process what is waiting, then stop
    python -m kafriada.contexts.media.worker            # keep going, every 10s

Re-encodes confirmed uploads into their safe copies (EXIF stripped) and removes
identity documents 30 days after a decision. Scheduling belongs to 2.3; until then
it is started by hand, and uploads simply wait as ``uploaded`` — which the review
queue treats as "not ready yet", so nothing unprocessed is ever shown to anyone.
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from types import FrameType

import structlog

from kafriada.contexts.media import service
from kafriada.contexts.media.store import build_store
from kafriada.main import configure_logging
from kafriada.settings import MediaStoreKind, get_settings

log = structlog.get_logger(__name__)

_stopping = False


def _stop(_signum: int, _frame: FrameType | None) -> None:
    global _stopping
    _stopping = True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Process uploaded photographs and documents.")
    parser.add_argument("--once", action="store_true", help="one pass, then exit")
    parser.add_argument("--interval", type=float, default=10.0, help="seconds between passes")
    parser.add_argument("--batch", type=int, default=20, help="files per pass")
    args = parser.parse_args(argv)

    cfg = get_settings()
    configure_logging(cfg)
    if cfg.media_store is MediaStoreKind.NONE:
        print("No media store is configured (MEDIA_STORE=none), so there is nothing to process.")  # noqa: T201
        return 1

    store = build_store(cfg)
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    log.info("media_worker_started", store=store.name, once=args.once)

    last_purged = 0.0
    while not _stopping:
        ready = service.process_pending(args.batch, store=store)
        purged = 0
        # Documents live 30 days past a decision; hourly is far finer than that needs.
        if args.once or time.monotonic() - last_purged >= 3_600.0:
            last_purged = time.monotonic()
            purged = service.purge_expired_documents(store=store)
        if ready or purged:
            log.info("media_pass", ready=ready, purged=purged)
        if args.once:
            break
        time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
