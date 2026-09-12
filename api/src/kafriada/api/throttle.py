"""The per-address brake, declared on a route the way its permission rule is.

Kept apart from ``api/security.py`` on purpose. That module answers "is this
caller allowed to do this at all", and its answers are recorded in the route
manifest. This one answers "have they done it too many times just now", which is
not an authorisation decision and must not be mistaken for one: passing here
grants nothing.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request, status

from kafriada.api.client import client_ip
from kafriada.contexts.access import ratelimit


def Throttle(bucket: str) -> Any:
    """Count this request against ``bucket``; refuse with 429 once past the limit.

    The message says what to do and nothing else. It deliberately does not say
    which limit was hit or how much allowance remains — that would tell someone
    probing exactly how to pace themselves to stay underneath it.
    """
    # Fail at import time rather than on the first request in production if a
    # route names a bucket that does not exist.
    ratelimit.limits_for(bucket)

    def _count(request: Request) -> None:
        try:
            ratelimit.hit(bucket, client_ip(request), ratelimit.limits_for(bucket))
        except ratelimit.RateLimited as exc:
            minutes = max(round(exc.retry_after / 60), 1)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "message": (
                        "Too many attempts from this connection. Please wait "
                        f"{minutes} minute{'s' if minutes != 1 else ''} and try again."
                    ),
                    "field": None,
                },
                headers={"Retry-After": str(exc.retry_after)},
            ) from None

    return Depends(_count)
