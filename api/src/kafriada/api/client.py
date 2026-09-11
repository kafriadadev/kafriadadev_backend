"""Who is on the other end of a request: address, browser, request id."""

from __future__ import annotations

from ipaddress import ip_address

from fastapi import Request


def client_ip(request: Request) -> str | None:
    """The caller's address, taken from the edge rather than from the socket.

    Behind Cloudflare the socket address is Cloudflare's. The header is only
    trustworthy because nothing reaches this service except through the edge — if
    that ever stops being true, this stops being trustworthy with it.

    **The value is validated before it is returned, and that is not cosmetic.**
    It is written into an ``inet`` column, so anything that is not an IP address
    makes the INSERT fail — and the INSERT is the audit row inside the
    registration transaction. Without this check, a caller sending
    ``cf-connecting-ip: nonsense`` would take registration down for everybody, at
    zero cost to themselves. Headers are attacker-controlled input, including the
    ones a trusted proxy usually sets.
    """
    candidate: str | None = None
    for header in ("cf-connecting-ip", "x-real-ip"):
        if value := request.headers.get(header):
            candidate = value.split(",")[0].strip()
            break
    if candidate is None and request.client:
        candidate = request.client.host

    if not candidate:
        return None
    try:
        return str(ip_address(candidate))
    except ValueError:
        # Not an address. Drop it rather than failing the request: knowing where
        # a request came from is useful, and it is not worth refusing somebody
        # their identity over a malformed header.
        return None


def user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def request_id(request: Request) -> str | None:
    value = request.scope.get("request_id")
    return str(value) if value else None
