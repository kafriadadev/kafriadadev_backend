"""Club verification (CLB-04): a document, the ordinary payment path, a reviewer.

What must hold: the price is ours, the payment names the club it is for, nothing reaches
a reviewer without a document and a settled payment, only a reviewer can decide, a club
administrator only ever touches their own club's request, and a decision is final until
someone resubmits.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from kafriada.contexts.access import service as access
from kafriada.contexts.payments import service as payments
from kafriada.contexts.payments.provider import FakeProvider
from kafriada.contexts.payments.settlement import settle_charge
from kafriada.db.engine import money_transaction
from kafriada.main import create_app
from tests._access_helpers import audit_actions, bearer, make_user, sql
from tests._media_helpers import LGA, make_jpeg, use_local_store
from tests._payment_helpers import Athlete, charge_success_event, new_athlete

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not (os.environ.get("DATABASE_URL_APP") and os.environ.get("DATABASE_URL_MONEY")),
        reason="needs DATABASE_URL_APP and DATABASE_URL_MONEY",
    ),
]

CLUB_PRICE = 1_500_000


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture(scope="module")
def root() -> dict[str, str]:
    uid, _ = make_user("Club reviewer", grants=[("super_admin", "global", None)])
    return bearer(access.issue_session(uid, method="test").token)


@pytest.fixture(autouse=True)
def _store(monkeypatch: pytest.MonkeyPatch, tmp_path):  # type: ignore[no-untyped-def]
    from kafriada.api.v1 import club_verification

    store = use_local_store(monkeypatch, tmp_path)
    monkeypatch.setattr(club_verification, "build_store", lambda _settings=None: store)
    return store


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeProvider:
    provider = FakeProvider()
    monkeypatch.setattr(payments, "build_provider", lambda _settings=None: provider)
    return provider


def new_club(client: TestClient, root: dict[str, str], *, approve: bool = True) -> tuple[Athlete, str]:
    admin = new_athlete("Verifier")
    made = client.post(
        "/v1/clubs",
        headers=admin.headers,
        json={"name": f"Verify FC {uuid4().hex[:8]}", "sport": "Football", "lga_id": LGA,
              "contact_phone": "08031234567"},
    )
    assert made.status_code == 201, made.text
    club = str(made.json()["club_id"])
    if approve:
        assert client.post(f"/v1/admin/clubs/{club}/approve", headers=root).status_code == 204
    return admin, club


def upload(client: TestClient, admin: Athlete, club: str, data: bytes | None = None):  # type: ignore[no-untyped-def]
    data = data if data is not None else make_jpeg((600, 400), gps=False)
    slot = client.post(
        f"/v1/clubs/{club}/verification/uploads", headers=admin.headers,
        json={"content_type": "image/jpeg", "size_bytes": len(data)},
    )
    if slot.status_code != 201:
        return slot
    media_id = slot.json()["media_id"]
    put = client.put(f"/v1/clubs/{club}/verification/uploads/{media_id}/content", content=data, headers=admin.headers)
    assert put.status_code == 204, put.text
    return client.post(f"/v1/clubs/{club}/verification/uploads/{media_id}/confirm", headers=admin.headers)


def overview(client: TestClient, admin: Athlete, club: str) -> dict[str, object]:
    got = client.get(f"/v1/clubs/{club}/verification", headers=admin.headers)
    assert got.status_code == 200, got.text
    return got.json()  # type: ignore[no-any-return]


def pay(client: TestClient, admin: Athlete, club: str) -> str:
    started = client.post(f"/v1/clubs/{club}/verification/payment", headers=admin.headers)
    assert started.status_code == 201, started.text
    assert started.json()["amount_kobo"] == CLUB_PRICE
    reference = str(started.json()["reference"])
    assert settle_charge(charge_success_event(reference, amount_kobo=CLUB_PRICE)).outcome.value == "settled"
    return reference


def in_review(client: TestClient, root: dict[str, str]) -> tuple[Athlete, str]:
    admin, club = new_club(client, root)
    assert upload(client, admin, club).status_code == 204
    return admin, club


# -- the club administrator ---------------------------------------------------
def test_a_new_club_starts_with_nothing_submitted_at_the_price_we_set(
    client: TestClient, root: dict[str, str]
) -> None:
    admin, club = new_club(client, root)
    seen = overview(client, admin, club)
    assert (seen["state"], seen["verified"], seen["paid"], seen["price_kobo"]) == ("none", False, False, CLUB_PRICE)


def test_an_unapproved_club_cannot_start_and_a_stranger_cannot_touch_it(
    client: TestClient, root: dict[str, str], fake: FakeProvider
) -> None:
    admin, club = new_club(client, root, approve=False)
    assert upload(client, admin, club).status_code == 409
    assert client.post(f"/v1/clubs/{club}/verification/payment", headers=admin.headers).status_code == 409

    _other, approved = new_club(client, root)
    assert client.get(f"/v1/clubs/{approved}/verification", headers=admin.headers).status_code == 403
    assert upload(client, admin, approved).status_code == 403
    assert client.post(f"/v1/clubs/{approved}/verification/payment", headers=admin.headers).status_code == 403
    assert client.get(f"/v1/clubs/{approved}/verification").status_code == 401


def test_paying_before_a_document_is_refused_and_writes_no_payment(
    client: TestClient, root: dict[str, str], fake: FakeProvider
) -> None:
    admin, club = new_club(client, root)
    refused = client.post(f"/v1/clubs/{club}/verification/payment", headers=admin.headers)
    assert refused.status_code == 409
    assert sql("SELECT 1 FROM money.payments WHERE org_id = :c", c=club) == []


def test_a_document_that_is_not_an_image_is_refused_while_still_on_the_form(
    client: TestClient, root: dict[str, str]
) -> None:
    admin, club = new_club(client, root)
    bad = upload(client, admin, club, data=b"this is not an image at all" * 20)
    assert bad.status_code == 422 and bad.json()["error"]["message"]["field"] == "file"


def test_the_payment_names_the_club_and_the_price_is_ours(
    client: TestClient, root: dict[str, str], fake: FakeProvider
) -> None:
    admin, club = in_review(client, root)
    assert overview(client, admin, club)["state"] == "draft"
    reference = pay(client, admin, club)

    (row,) = sql(
        "SELECT purpose, expected_kobo, org_id::text AS org, paid_by, on_behalf_of, status "
        "FROM money.payments WHERE reference = :r", r=reference,
    )
    assert (row["purpose"], row["expected_kobo"], row["org"], row["paid_by"], row["on_behalf_of"], row["status"]) == (
        "stage2_org", CLUB_PRICE, club, admin.user_id, None, "success",
    )
    lines = sql(
        "SELECT l.direction, l.amount_kobo FROM money.ledger_entries l JOIN money.payments p ON p.id = l.payment_id "
        "WHERE p.reference = :r ORDER BY l.id", r=reference,
    )
    assert len(lines) == 2 and lines[0]["amount_kobo"] == CLUB_PRICE
    receipt = sql(
        "SELECT payload->>'sms' AS sms FROM ops.outbox WHERE payload->>'user_id' = :u "
        "AND payload->>'purpose' = 'payment_received'", u=str(admin.user_id),
    )
    assert receipt and "club" in str(receipt[0]["sms"])


def test_a_payment_for_the_wrong_amount_freezes_and_never_reaches_a_reviewer(
    client: TestClient, root: dict[str, str], fake: FakeProvider
) -> None:
    admin, club = in_review(client, root)
    ref = client.post(f"/v1/clubs/{club}/verification/payment", headers=admin.headers).json()["reference"]
    frozen = settle_charge(charge_success_event(ref, amount_kobo=250_000))  # the athlete price
    assert frozen.outcome.value == "frozen"
    assert overview(client, admin, club)["state"] == "draft"
    waiting = client.get("/v1/admin/club-verification/queue", headers=root).json()
    assert club not in [i["club_id"] for i in waiting]


def test_a_payment_and_its_club_cannot_be_separated_or_edited(client: TestClient, root: dict[str, str]) -> None:
    admin, club = new_club(client, root)
    ref = f"KAF-{uuid4()}"
    with pytest.raises(Exception, match="payments_org_matches_purpose"), money_transaction(reason="test") as s:
        from sqlalchemy import text

        s.execute(
            text("INSERT INTO money.payments (reference, purpose, expected_kobo, paid_by) "
                 "VALUES (:r, 'stage2_org', 1500000, :u)"),
            {"r": ref, "u": admin.user_id},
        )
    with pytest.raises(Exception, match="payments_org_matches_purpose"), money_transaction(reason="test") as s:
        s.execute(
            text("INSERT INTO money.payments (reference, purpose, expected_kobo, paid_by, org_id) "
                 "VALUES (:r, 'stage2_athlete', 250000, :u, :c)"),
            {"r": f"KAF-{uuid4()}", "u": admin.user_id, "c": club},
        )


# -- the reviewer --------------------------------------------------------------
def test_a_paid_request_is_reviewed_and_approval_makes_the_club_verified(
    client: TestClient, root: dict[str, str], fake: FakeProvider
) -> None:
    admin, club = in_review(client, root)
    pay(client, admin, club)
    assert overview(client, admin, club)["state"] == "under_review"

    waiting = client.get("/v1/admin/club-verification/queue", headers=root).json()
    assert club in [i["club_id"] for i in waiting]
    doc = client.get(f"/v1/admin/club-verification/{club}/document", headers=root)
    assert doc.status_code == 200 and doc.headers["content-type"] == "image/jpeg" and doc.content[:2] == b"\xff\xd8"

    assert client.post(f"/v1/admin/club-verification/{club}/approve", headers=root).status_code == 204
    seen = overview(client, admin, club)
    assert (seen["state"], seen["verified"]) == ("approved", True)
    assert client.get(f"/v1/clubs/{club}", headers=admin.headers).json()["verified"] is True
    (decision,) = sql(
        "SELECT d.decision FROM identity.club_verification_decisions d "
        "JOIN identity.club_verification_requests v ON v.id = d.request_id WHERE v.org_id = :c", c=club,
    )
    assert decision["decision"] == "approved"
    assert "club_verification.approved" in audit_actions(club)
    # No second payment, no more edits, and it cannot be decided twice.
    assert client.post(f"/v1/clubs/{club}/verification/payment", headers=admin.headers).status_code == 409
    assert upload(client, admin, club).status_code == 409
    assert client.post(f"/v1/admin/club-verification/{club}/approve", headers=root).status_code == 409
    # And the document is not served once it is no longer waiting.
    assert client.get(f"/v1/admin/club-verification/{club}/document", headers=root).status_code == 404


def test_a_rejection_needs_a_reason_the_club_reads_and_can_be_resubmitted_without_paying_again(
    client: TestClient, root: dict[str, str], fake: FakeProvider
) -> None:
    admin, club = in_review(client, root)
    pay(client, admin, club)

    empty = client.post(f"/v1/admin/club-verification/{club}/reject", headers=root, json={"reason": "   "})
    assert empty.status_code == 422 and empty.json()["error"]["message"]["field"] == "reason"
    assert overview(client, admin, club)["state"] == "under_review"

    words = "The letter does not name the club."
    assert client.post(f"/v1/admin/club-verification/{club}/reject", headers=root, json={"reason": words}).status_code == 204
    seen = overview(client, admin, club)
    assert (seen["state"], seen["reason"], seen["verified"]) == ("rejected", words, False)

    # A rejected club fixes the document; the payment already made carries over.
    assert upload(client, admin, club).status_code == 204
    assert client.post(f"/v1/clubs/{club}/verification/payment", headers=admin.headers).status_code == 409
    assert client.post(f"/v1/clubs/{club}/verification/resubmit", headers=admin.headers).status_code == 204
    assert overview(client, admin, club)["state"] == "under_review"
    assert client.post(f"/v1/clubs/{club}/verification/resubmit", headers=admin.headers).status_code == 409
    assert client.post(f"/v1/admin/club-verification/{club}/approve", headers=root).status_code == 204
    assert overview(client, admin, club)["verified"] is True


def test_only_a_reviewer_can_see_the_queue_the_document_or_decide(
    client: TestClient, root: dict[str, str], fake: FakeProvider
) -> None:
    admin, club = in_review(client, root)
    pay(client, admin, club)
    stranger = new_athlete("Curious")
    for who in (admin, stranger):
        assert client.get("/v1/admin/club-verification/queue", headers=who.headers).status_code == 403
        assert client.get(f"/v1/admin/club-verification/{club}/document", headers=who.headers).status_code == 403
        assert client.post(f"/v1/admin/club-verification/{club}/approve", headers=who.headers).status_code == 403
        assert client.post(f"/v1/admin/club-verification/{club}/reject", headers=who.headers, json={"reason": "no"}).status_code == 403
    assert client.get("/v1/admin/club-verification/queue").status_code == 401
    assert overview(client, admin, club)["state"] == "under_review"
    assert client.post(f"/v1/admin/club-verification/{uuid4()}/approve", headers=root).status_code == 404
    assert client.post("/v1/admin/club-verification/not-a-uuid/approve", headers=root).status_code == 404


def test_a_club_administrator_cannot_reach_into_another_clubs_request(
    client: TestClient, root: dict[str, str], fake: FakeProvider
) -> None:
    a, club_a = new_club(client, root)
    b, club_b = new_club(client, root)
    assert upload(client, a, club_a).status_code == 204
    (row,) = sql(
        "SELECT document_media_id::text AS m FROM identity.club_verification_requests WHERE org_id = :c", c=club_a
    )
    media_id = row["m"]
    # B, through their own club's path, cannot touch A's file...
    assert client.put(f"/v1/clubs/{club_b}/verification/uploads/{media_id}/content", content=b"x", headers=b.headers).status_code == 404
    assert client.post(f"/v1/clubs/{club_b}/verification/uploads/{media_id}/confirm", headers=b.headers).status_code == 404
    # ...and through A's path, B is refused outright.
    assert client.post(f"/v1/clubs/{club_a}/verification/uploads/{media_id}/confirm", headers=b.headers).status_code == 403
    assert client.post(f"/v1/clubs/{club_a}/verification/resubmit", headers=b.headers).status_code == 403


def test_one_administrator_of_two_clubs_cannot_move_a_file_between_them(
    client: TestClient, root: dict[str, str]
) -> None:
    admin, club_a = new_club(client, root)
    made = client.post(
        "/v1/clubs", headers=admin.headers,
        json={"name": f"Second FC {uuid4().hex[:8]}", "sport": "Football", "lga_id": LGA,
              "contact_phone": "08031234567"},
    )
    club_b = str(made.json()["club_id"])
    assert client.post(f"/v1/admin/clubs/{club_b}/approve", headers=root).status_code == 204
    # A slot that is open but not yet sent: the moment a file could still be redirected.
    slot = client.post(
        f"/v1/clubs/{club_a}/verification/uploads", headers=admin.headers,
        json={"content_type": "image/jpeg", "size_bytes": 500},
    )
    media_id = slot.json()["media_id"]
    # Theirs, and they administer both clubs — but it belongs to club A's request only.
    assert client.put(f"/v1/clubs/{club_b}/verification/uploads/{media_id}/content", content=b"x", headers=admin.headers).status_code == 404
    assert client.post(f"/v1/clubs/{club_b}/verification/uploads/{media_id}/confirm", headers=admin.headers).status_code == 404


# -- revoking a verified club (mirrors ADM-03) -------------------------------
PASSWORD = "a long test passphrase"


def verified_club(client: TestClient, root: dict[str, str], fake: FakeProvider) -> tuple[Athlete, str]:
    admin, club = in_review(client, root)
    pay(client, admin, club)
    assert client.post(f"/v1/admin/club-verification/{club}/approve", headers=root).status_code == 204
    return admin, club


def test_revoking_needs_a_reason_and_the_password_again(
    client: TestClient, root: dict[str, str], fake: FakeProvider
) -> None:
    from tests._media_helpers import super_admin

    boss = super_admin(PASSWORD)
    admin, club = verified_club(client, root, fake)

    empty = client.post(
        f"/v1/admin/club-verification/{club}/revoke", headers=boss.headers,
        json={"reason": "   ", "current_password": PASSWORD},
    )
    assert empty.status_code == 422 and empty.json()["error"]["message"]["field"] == "reason"

    wrong = client.post(
        f"/v1/admin/club-verification/{club}/revoke", headers=boss.headers,
        json={"reason": "forged document", "current_password": "not my password"},
    )
    assert wrong.status_code == 422 and wrong.json()["error"]["message"]["field"] == "current_password"
    assert overview(client, admin, club)["verified"] is True

    words = "The document was forged."
    ok = client.post(
        f"/v1/admin/club-verification/{club}/revoke", headers=boss.headers,
        json={"reason": words, "current_password": PASSWORD},
    )
    assert ok.status_code == 204, ok.text
    seen = overview(client, admin, club)
    # A revoked request frees the slot, the same as an athlete's — the club could start a
    # fresh submission, so its current state reads "none", not "revoked".
    assert (seen["state"], seen["verified"]) == ("none", False)
    assert client.get(f"/v1/clubs/{club}", headers=admin.headers).json()["verified"] is False
    assert "club_verification.revoked" in audit_actions(club)
    (decision,) = sql(
        "SELECT decision, reason FROM identity.club_verification_decisions d "
        "JOIN identity.club_verification_requests v ON v.id = d.request_id "
        "WHERE v.org_id = :c ORDER BY d.id DESC LIMIT 1", c=club,
    )
    assert (decision["decision"], decision["reason"]) == ("revoked", words)


def test_a_club_that_is_not_verified_cannot_be_revoked_and_it_cannot_be_revoked_twice(
    client: TestClient, root: dict[str, str], fake: FakeProvider
) -> None:
    from tests._media_helpers import super_admin

    boss = super_admin(PASSWORD)
    _admin, bare_club = new_club(client, root)  # no verification request exists at all
    nothing_to_revoke = client.post(
        f"/v1/admin/club-verification/{bare_club}/revoke", headers=boss.headers,
        json={"reason": "x", "current_password": PASSWORD},
    )
    assert nothing_to_revoke.status_code == 404

    _admin3, waiting_club = in_review(client, root)  # a request exists, but is not approved
    not_approved = client.post(
        f"/v1/admin/club-verification/{waiting_club}/revoke", headers=boss.headers,
        json={"reason": "x", "current_password": PASSWORD},
    )
    assert not_approved.status_code == 409

    _admin2, club2 = verified_club(client, root, fake)
    first = client.post(
        f"/v1/admin/club-verification/{club2}/revoke", headers=boss.headers,
        json={"reason": "once", "current_password": PASSWORD},
    )
    assert first.status_code == 204
    twice = client.post(
        f"/v1/admin/club-verification/{club2}/revoke", headers=boss.headers,
        json={"reason": "again", "current_password": PASSWORD},
    )
    # A revoked request frees the slot, so a second revoke finds nothing to act on.
    assert twice.status_code == 404
    assert client.post(
        f"/v1/admin/club-verification/{uuid4()}/revoke", headers=boss.headers,
        json={"reason": "x", "current_password": PASSWORD},
    ).status_code == 404


def test_only_a_reviewer_can_revoke(client: TestClient, root: dict[str, str], fake: FakeProvider) -> None:
    admin, club = verified_club(client, root, fake)
    stranger = new_athlete("Stranger reviewer")
    denied = client.post(
        f"/v1/admin/club-verification/{club}/revoke", headers=admin.headers,
        json={"reason": "x", "current_password": PASSWORD},
    )
    assert denied.status_code == 403
    assert client.post(
        f"/v1/admin/club-verification/{club}/revoke", headers=stranger.headers,
        json={"reason": "x", "current_password": PASSWORD},
    ).status_code == 403
    anon = client.post(f"/v1/admin/club-verification/{club}/revoke", json={"reason": "x", "current_password": PASSWORD})
    assert anon.status_code == 401
    assert overview(client, admin, club)["verified"] is True


# -- purging a decided club's document, 30 days later ------------------------
class TestClubDocumentsDoNotOutliveTheirPurpose:
    def _backdate(self, club_id: str, days: int) -> None:
        sql(
            "UPDATE identity.club_verification_requests SET decided_at = now() - make_interval(days => :d) "
            "WHERE org_id = :c", d=days, c=club_id,
        )

    def test_the_document_is_removed_thirty_days_after_approval(
        self, client: TestClient, root: dict[str, str], fake: FakeProvider, _store
    ) -> None:  # type: ignore[no-untyped-def]
        from kafriada.contexts.clubs import verification as club_verification

        _admin, club = verified_club(client, root, fake)
        (key,) = sql(
            "SELECT m.derivative_key AS key FROM identity.media_files m "
            "JOIN identity.club_verification_requests v ON v.document_media_id = m.id WHERE v.org_id = :c", c=club,
        )
        derivative = str(key["key"])

        self._backdate(club, 29)
        club_verification.purge_expired_documents(store=_store)
        assert _store.head(derivative) is not None  # not yet

        self._backdate(club, 31)
        club_verification.purge_expired_documents(store=_store)
        assert _store.head(derivative) is None
        status_row = sql("SELECT status FROM identity.media_files WHERE derivative_key = :k", k=derivative)
        assert status_row[0]["status"] == "deleted"

    def test_a_rejected_clubs_document_is_kept_for_the_next_attempt(
        self, client: TestClient, root: dict[str, str], fake: FakeProvider, _store
    ) -> None:  # type: ignore[no-untyped-def]
        from kafriada.contexts.clubs import verification as club_verification

        admin, club = in_review(client, root)
        pay(client, admin, club)
        rejected = client.post(
            f"/v1/admin/club-verification/{club}/reject", headers=root, json={"reason": "blurry"}
        )
        assert rejected.status_code == 204
        self._backdate(club, 90)
        (key,) = sql(
            "SELECT m.derivative_key AS key FROM identity.media_files m "
            "JOIN identity.club_verification_requests v ON v.document_media_id = m.id WHERE v.org_id = :c", c=club,
        )
        club_verification.purge_expired_documents(store=_store)
        assert _store.head(str(key["key"])) is not None
