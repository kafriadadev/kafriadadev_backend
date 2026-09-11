"""Route authorisation, declared rather than assumed.

**Every route states who may call it.** Not in a comment, not in a wiki — as an
argument on the route itself. A route that declares nothing fails the route
manifest test, because the route nobody remembered to protect is exactly the one
an attacker finds.

    @router.post("/register",   dependencies=[Public("anyone may register")])
    @router.get("/me",          dependencies=[SignedIn("your own account")])
    @router.get("/lgas/{lga_id}/athletes",
                dependencies=[Requires("athlete.search_scoped", scope="lga")])

**Deny by default.** The check is a dependency, so it runs before the handler —
and before the request body is even validated. There is no path where a handler
executes and then decides whether it should have.

**Public is a decision, not an absence.** ``Public()`` and ``SignedIn()`` take a
reason. "Anyone may view a QR profile" is a deliberate product choice; a route
left undeclared is an oversight. The two must not look alike in the source.

**Scope comes from the path.** ``Requires(..., scope="lga")`` reads the target
from the ``lga_id`` path parameter, so the thing being checked is the thing the
handler acts on. A scoped rule on a route without that parameter is refused at
request time and fails the manifest test.

The caller is identified by the session token the presentation tier forwards as
``Authorization: Bearer <token>``. The browser never sees this service.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.routing import APIRoute, RouteContext, iter_route_contexts

from kafriada.contexts.access import service as access

RuleKind = Literal["public", "signed_in", "permission"]
ScopeKind = Literal["state", "lga", "club"]

SIGN_IN_REQUIRED = "Sign in to continue."
NOT_ALLOWED = "You do not have access to this."

# The dependency callables carry their rule under this attribute, which is how
# the manifest and matrix tests find the rule for each route.
_RULE_ATTRIBUTE = "__kafriada_route_rule__"


@dataclass(frozen=True, slots=True)
class RouteRule:
    """What a route requires."""

    kind: RuleKind
    permission: str | None = None
    # None means the check names no target, and only a global grant satisfies it.
    scope: ScopeKind | None = None
    reason: str | None = None

    @property
    def scope_param(self) -> str | None:
        return f"{self.scope}_id" if self.scope else None


def api_routes(app: FastAPI) -> list[RouteContext]:
    """Every API route as served, with its full path, including router prefixes.

    FastAPI keeps included routers as nested objects rather than copying their
    routes into ``app.routes``, so walking ``app.routes`` alone misses them.
    """
    return [c for c in iter_route_contexts(app.routes) if isinstance(c.original_route, APIRoute)]


def rules_of(route: RouteContext | APIRoute) -> list[RouteRule]:
    """Every rule declared on a route. Exactly one is correct."""
    return [
        rule
        for dep in route.dependant.dependencies
        if (rule := getattr(dep.call, _RULE_ATTRIBUTE, None)) is not None
    ]


def _declare(rule: RouteRule, check: Callable[[Request], None]) -> Any:
    setattr(check, _RULE_ATTRIBUTE, rule)
    return Depends(check)


def Public(reason: str) -> Any:
    """Declare a route reachable without an account.

    ``reason`` is required and is not decoration: it is the difference between a
    route that is public on purpose and one that is public by accident.
    """
    if not reason.strip():
        raise ValueError("Public() requires a reason")

    def _allow(request: Request) -> None:
        request.state.route_rule = rule

    rule = RouteRule(kind="public", reason=reason)
    return _declare(rule, _allow)


def SignedIn(reason: str) -> Any:
    """Declare a route open to anyone with a valid session, whatever their roles.

    For routes that act only on the caller's own account — signing out, reading
    one's own details. Anything touching another person's data needs Requires.
    """
    if not reason.strip():
        raise ValueError("SignedIn() requires a reason")

    def _check(request: Request) -> None:
        request.state.route_rule = rule
        _authenticate(request)

    rule = RouteRule(kind="signed_in", reason=reason)
    return _declare(rule, _check)


def Requires(permission: str, *, scope: ScopeKind | None = None) -> Any:
    """Declare the permission a caller must hold, and the scope it applies within.

    ``scope`` is the part people leave out, and leaving it out is the most common
    data-leak bug in role-based systems: a club administrator who holds
    ``club.manage_roster`` without a scope check can manage *every* club's roster,
    and a naive test suite passes because the permission was indeed required.
    """

    def _check(request: Request) -> None:
        request.state.route_rule = rule
        principal = _authenticate(request)

        target: access.Scope | None = None
        if rule.scope is not None:
            scope_id = request.path_params.get(f"{rule.scope}_id")
            if not scope_id:
                # A declaration the route cannot satisfy. Fail closed.
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED)
            target = access.Scope(kind=rule.scope, id=str(scope_id))

        if not access.can(principal.user_id, permission, target):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_ALLOWED)

    rule = RouteRule(kind="permission", permission=permission, scope=scope)
    return _declare(rule, _check)


def current_principal(request: Request) -> access.Principal:
    """The caller, as established by the route's SignedIn or Requires rule."""
    principal: access.Principal | None = getattr(request.state, "principal", None)
    if principal is None:
        # Only reachable if a handler asks for a caller on a Public route: a bug
        # in this codebase, not something a request can cause.
        raise RuntimeError("current_principal() used on a route with no session rule")
    return principal


def _authenticate(request: Request) -> access.Principal:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    principal = (
        access.authenticate(token.strip()) if scheme.lower() == "bearer" else None
    )
    if principal is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=SIGN_IN_REQUIRED)
    request.state.principal = principal
    return principal
