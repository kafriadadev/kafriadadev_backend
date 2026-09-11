"""Every route declares who may call it, and every declaration can be enforced.

Runs without a database. It walks the real application's routes, so a route
added tomorrow without a rule fails here before it is ever deployed.
"""

from __future__ import annotations

import pytest
from fastapi.routing import RouteContext

from kafriada.api.security import Public, Requires, SignedIn, api_routes, rules_of
from kafriada.main import create_app

ROUTES = api_routes(create_app())


def _name(route: RouteContext) -> str:
    return f"{sorted(route.methods or [])} {route.path}"


def test_the_application_has_routes() -> None:
    assert len(ROUTES) >= 10


@pytest.mark.parametrize("route", ROUTES, ids=_name)
def test_every_route_declares_exactly_one_rule(route: RouteContext) -> None:
    rules = rules_of(route)
    assert len(rules) == 1, f"{_name(route)} declares {len(rules)} rules; exactly one is required"


@pytest.mark.parametrize("route", ROUTES, ids=_name)
def test_a_scoped_rule_reads_its_target_from_the_path(route: RouteContext) -> None:
    (rule,) = rules_of(route)
    if rule.scope_param is not None:
        assert f"{{{rule.scope_param}}}" in route.path, (
            f"{_name(route)} requires scope '{rule.scope}' but has no "
            f"{{{rule.scope_param}}} path parameter to take it from"
        )


@pytest.mark.parametrize("route", ROUTES, ids=_name)
def test_public_and_signed_in_routes_give_a_reason(route: RouteContext) -> None:
    (rule,) = rules_of(route)
    if rule.kind in ("public", "signed_in"):
        assert rule.reason and rule.reason.strip()


def test_staff_routes_are_not_public() -> None:
    """Belt and braces over the matrix: nothing under /admin or a scoped path is open."""
    for route in ROUTES:
        (rule,) = rules_of(route)
        if "/admin/" in route.path or "/lgas/{" in route.path:
            assert rule.kind == "permission", f"{_name(route)} is {rule.kind}"


def test_a_declaration_without_a_reason_is_refused() -> None:
    with pytest.raises(ValueError):
        Public("  ")
    with pytest.raises(ValueError):
        SignedIn("")


def test_requires_records_permission_and_scope() -> None:
    dep = Requires("club.manage_roster", scope="club")
    rule = dep.dependency.__kafriada_route_rule__
    assert rule.permission == "club.manage_roster"
    assert rule.scope_param == "club_id"
