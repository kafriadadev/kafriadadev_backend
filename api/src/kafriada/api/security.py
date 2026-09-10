"""Route authorisation, declared rather than assumed.

**Every route states who may call it.** Not in a comment, not in a wiki — as an
argument on the route itself. A route that declares nothing is refused at runtime
*and* fails the build, because the route nobody remembered to protect is exactly
the one an attacker finds.

    @router.post("/register", dependencies=[Public("anyone may register")])
    @router.get("/queue",     dependencies=[Requires("verification.review",
                                                     scope="lga")])

Two things make this worth the small ceremony.

**Deny by default.** The check is a dependency, so it runs before the handler.
There is no path where a handler executes and then decides whether it should
have. Forgetting the declaration does not silently allow access — it fails.

**Public is a decision, not an absence.** ``Public()`` takes a reason and that
reason is recorded. "Anyone may view a QR profile" is a deliberate product
choice; a route left undeclared is an oversight. The two must not look alike in
the source, which is why there is no default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import Depends, HTTPException, Request, status

ScopeKind = Literal["global", "state", "lga", "club"]


@dataclass(frozen=True, slots=True)
class RouteRule:
    """What a route requires. Attached to the route for the CI manifest test."""

    permission: str | None
    scope: ScopeKind | None = None
    public_reason: str | None = None
    tags: frozenset[str] = field(default_factory=frozenset)

    @property
    def is_public(self) -> bool:
        return self.permission is None


# Every declaration made anywhere in the application, in import order. The CI
# route-manifest test walks the application's routes and asserts each one appears
# here — a route with no rule fails the build.
DECLARED_RULES: list[RouteRule] = []


def Public(reason: str) -> Any:
    """Declare a route reachable without an account.

    ``reason`` is required and is not decoration: it is the difference between a
    route that is public on purpose and one that is public by accident.
    """
    if not reason.strip():
        raise ValueError("Public() requires a reason")

    rule = RouteRule(permission=None, public_reason=reason)
    DECLARED_RULES.append(rule)

    def _allow(request: Request) -> None:
        request.state.route_rule = rule

    return Depends(_allow)


def Requires(
    permission: str,
    *,
    scope: ScopeKind | None = None,
) -> Any:
    """Declare the permission a caller must hold, and the scope it applies within.

    ``scope`` is the part people leave out, and leaving it out is the most common
    data-leak bug in role-based systems: a club administrator who holds
    ``club.manage_roster`` without a scope check can manage *every* club's roster,
    and a naive test suite passes because the permission was indeed required.
    """
    rule = RouteRule(permission=permission, scope=scope)
    DECLARED_RULES.append(rule)

    def _check(request: Request) -> None:
        request.state.route_rule = rule
        # Sessions and the permission table arrive with the access context.
        # Until then this refuses rather than allows: an unfinished authorisation
        # check must fail closed, or every protected route is open for as long as
        # it takes to finish it.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to continue.",
        )

    return Depends(_check)
