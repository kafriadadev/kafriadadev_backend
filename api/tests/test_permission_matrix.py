"""Every role against every route, in two tenants.

Generated, not hand-written: the routes come from the live application, the
roles and their permissions from ``ops.role_permissions``. Add a route or a
permission and it is in the matrix without anyone editing this file.

Each scoped role is held twice — once over the place every request targets
(tenant A: Birnin Kudu, Jigawa, club A) and once somewhere else (tenant B:
Gumel, another state, club B). Tenant B must be refused everywhere tenant A is
allowed. That is what stops "manages a roster" silently meaning "manages every
roster": a check that looked only at the permission would pass tenant B too.

The probes do not change anything. Mutating routes are called with an empty
body, so an allowed caller gets 422 from validation — which runs only after the
authorisation check has passed — and a refused one gets 401 or 403. The one
route that ends the caller's own session is probed last for each principal.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest
from fastapi.routing import RouteContext
from fastapi.testclient import TestClient

from kafriada.api.security import RouteRule, api_routes, rules_of
from kafriada.contexts.access import service as access
from kafriada.main import create_app
from tests._access_helpers import Grant, bearer, make_user, sql

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not os.environ.get("DATABASE_URL_APP"),
        reason="needs DATABASE_URL_APP",
    ),
]

# What every request targets, and where tenant B sits instead.
TARGET = {"lga": "NG-JG-BKD", "state": "NG-JG", "club": "club-A"}
PARENT_STATE = {"NG-JG-BKD": "NG-JG"}
TENANT_B = {"lga": "NG-JG-GUM", "state": "NG-KN", "club": "club-B"}

SESSION_ENDING = ("DELETE", "/v1/sessions/current")


@dataclass
class Principal:
    label: str
    grants: list[Grant] = field(default_factory=list)
    token: str | None = None


def _expected(rule: RouteRule, who: Principal, role_permissions: dict[str, set[str]]) -> str:
    """The oracle, stated independently of the code under test."""
    if rule.kind == "public":
        return "allow"
    if who.token is None:
        return "401"
    if rule.kind == "signed_in":
        return "allow"
    for role, kind, scope_id in who.grants:
        if rule.permission not in role_permissions.get(role, set()):
            continue
        if kind == "global":
            return "allow"
        if rule.scope is None:
            continue  # a scoped grant never satisfies an unscoped check
        target = TARGET[rule.scope]
        if kind == rule.scope and scope_id == target:
            return "allow"
        if rule.scope == "lga" and kind == "state" and scope_id == PARENT_STATE.get(target):
            return "allow"
    return "403"


def _url(route: RouteContext, target_user: uuid.UUID) -> str:
    values = {
        "lga_id": TARGET["lga"],
        "state_id": TARGET["state"],
        "club_id": TARGET["club"],
        "user_id": str(target_user),
        "grant_id": str(uuid.uuid4()),
        "kuid": "not-a-kuid",
        "reference": f"KAF-{uuid.uuid4()}",
    }
    path = route.path
    for name, value in values.items():
        path = path.replace(f"{{{name}}}", value)
    assert "{" not in path, f"no probe value for a parameter in {route.path}"
    return path


@pytest.fixture(scope="module")
def matrix() -> Iterator[tuple[TestClient, list[RouteContext], list[Principal], dict[str, set[str]]]]:
    role_permissions: dict[str, set[str]] = {}
    for row in sql("SELECT role_code, permission_code FROM ops.role_permissions"):
        role_permissions.setdefault(str(row["role_code"]), set()).add(str(row["permission_code"]))
    roles = sql("SELECT code, scope_kind FROM ops.roles ORDER BY code")

    principals = [Principal("anonymous")]
    for row in roles:
        role, kind = str(row["code"]), str(row["scope_kind"])
        if kind == "global":
            principals.append(Principal(role, [(role, "global", None)]))
        else:
            principals.append(Principal(f"{role}@A", [(role, kind, TARGET[kind])]))
            principals.append(Principal(f"{role}@B", [(role, kind, TENANT_B[kind])]))

    for p in principals[1:]:
        user_id, _ = make_user(f"Matrix {p.label}", grants=p.grants)
        p.token = access.issue_session(user_id, method="test").token

    app = create_app()
    routes = api_routes(app)
    with TestClient(app) as client:
        yield client, routes, principals, role_permissions


def test_every_permission_a_route_names_exists(matrix) -> None:  # type: ignore[no-untyped-def]
    _, routes, _, _ = matrix
    known = {str(r["code"]) for r in sql("SELECT code FROM ops.permissions")}
    for route in routes:
        (rule,) = rules_of(route)
        if rule.permission is not None:
            assert rule.permission in known, f"{route.path} requires unknown {rule.permission}"


def test_every_role_against_every_route_in_two_tenants(matrix) -> None:  # type: ignore[no-untyped-def]
    client, routes, principals, role_permissions = matrix
    target_user, _ = make_user("Matrix target")

    probes = [(m, r) for r in routes for m in sorted(r.methods or []) if m != "HEAD"]
    # The sign-out probe ends the principal's session, so it goes last.
    probes.sort(key=lambda p: (p[0], p[1].path) == SESSION_ENDING)

    wrong: list[str] = []
    outcomes: dict[tuple[str, str, str], str] = {}
    for principal in principals:
        headers = bearer(principal.token) if principal.token else {}
        for method, route in probes:
            (rule,) = rules_of(route)
            url = _url(route, target_user)
            kwargs: dict[str, object] = {"headers": headers}
            if method in ("POST", "PUT", "PATCH"):
                kwargs["json"] = {}
            status = client.request(method, url, **kwargs).status_code  # type: ignore[arg-type]

            assert status < 500, f"{principal.label} {method} {url} -> {status}"
            got = str(status) if status in (401, 403) else "allow"
            want = _expected(rule, principal, role_permissions)
            outcomes[(principal.label, method, route.path)] = got
            if got != want:
                wrong.append(f"{principal.label:24} {method:6} {route.path:40} want {want}, got {got}")

    print(f"\n  {len(principals)} principals x {len(probes)} probes = {len(outcomes)} checks")
    assert not wrong, "authorisation differs from the permission table:\n  " + "\n  ".join(wrong)

    # The matrix must actually exercise the second tenant, or it proves nothing.
    scoped = "/v1/lgas/{lga_id}/athletes"
    for role in ("lga_coordinator", "state_coordinator"):
        assert outcomes[(f"{role}@A", "GET", scoped)] == "allow"
        assert outcomes[(f"{role}@B", "GET", scoped)] == "403"
