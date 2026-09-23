"""Verification, end to end through the real routes and a real database.

What is proved here:
  - no payment without both files ready; a settled payment moves the draft to review;
    nothing else does
  - a reviewer sees only their own LGA's queue, never their own record, and cannot
    approve or reject a case they cannot see — refused by the service, not by a screen
  - a rejection needs a reason, the athlete reads it verbatim, resubmission costs
    nothing, and the third rejection escalates and closes resubmission
  - approval publishes the photo (the safe copy) and the badge; a withdrawal needs a
    reason and the password again and takes both back, and frees the athlete's slot
  - decisions cannot be edited or deleted by anyone, the owner included
  - every decision queues its SMS and writes its audit row in the same commit
  - documents are removed 30 days after a decision, and rejected ones are not
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from kafriada.contexts.media import service as media
from kafriada.contexts.verification import service as verification
from kafriada.main import create_app
from tests._access_helpers import bearer, make_user, sql
from tests._media_helpers import (
    LGA,
    OTHER_LGA,
    athlete_with_files,
    make_jpeg,
    metadata_of,
    pay,
    request_id_of,
    review_url,
    reviewer,
    super_admin,
    upload,
    use_local_store,
)
from tests._payment_helpers import new_athlete, pending_payment

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not (os.environ.get("DATABASE_URL_APP") and os.environ.get("DATABASE_URL_MONEY")
             and os.environ.get("DATABASE_URL_MIGRATE")),
        reason="needs the app, money and migrate database URLs",
    ),
]

PASSWORD = "a long test passphrase"


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture(autouse=True)
def store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):  # type: ignore[no-untyped-def]
    return use_local_store(monkeypatch, tmp_path)


def state_of(who) -> str:  # type: ignore[no-untyped-def]
    return str(sql(
        "SELECT v.status FROM identity.verification_requests v JOIN identity.athletes a "
        "ON a.id = v.athlete_id WHERE a.user_id = :u ORDER BY v.created_at DESC LIMIT 1",
        u=who.user_id,
    )[0]["status"])


def under_review(client: TestClient, name: str = "Case"):  # type: ignore[no-untyped-def]
    """An athlete with files, paid, waiting in the queue. Returns (athlete, request_id)."""
    who = athlete_with_files(client, name)
    pay(who)
    assert state_of(who) == "under_review"
    return who, request_id_of(who)


def decisions(request_id: UUID) -> list[tuple[str, str | None]]:
    return [
        (str(r["decision"]), r["reason"])  # type: ignore[misc]
        for r in sql(
            "SELECT decision, reason FROM identity.verification_decisions "
            "WHERE request_id = :r ORDER BY id", r=request_id,
        )
    ]


def sms_to(who) -> list[str]:  # type: ignore[no-untyped-def]
    """What this athlete has been told about their verification, in order.

    A decision is queued addressed to the *person*, not to a number — the
    worker decides at send time whether that reaches them by SMS or email — so
    this reads the queue by user id and takes the SMS wording of each.
    """
    return [
        str(r["body"])
        for r in sql(
            "SELECT payload->>'sms' AS body FROM ops.outbox "
            "WHERE payload->>'user_id' = :u AND payload->>'purpose' LIKE 'verification_%' "
            "ORDER BY id",
            u=str(who.user_id),
        )
    ]


class TestGettingIntoTheQueue:
    def test_no_payment_can_start_before_both_files_are_ready(self, client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        from kafriada.contexts.payments import service as payments
        from kafriada.contexts.payments.provider import FakeProvider

        monkeypatch.setattr(payments, "build_provider", lambda _s=None: FakeProvider())
        who = new_athlete("NoFiles")
        body = {"purpose": "stage2_athlete"}
        assert client.post("/v1/payments", json=body, headers=who.headers).status_code == 409

        upload(client, who, "photo", make_jpeg())
        assert client.post("/v1/payments", json=body, headers=who.headers).status_code == 409  # no document

        upload(client, who, "document", make_jpeg(gps=False))
        assert client.get("/v1/verification", headers=who.headers).json()["ready_to_pay"] is True
        assert client.post("/v1/payments", json=body, headers=who.headers).status_code == 201

    def test_a_settled_payment_moves_the_draft_to_review_and_nothing_else_does(
        self, client: TestClient
    ) -> None:
        who = athlete_with_files(client)
        assert state_of(who) == "draft"
        overview = client.get("/v1/verification", headers=who.headers).json()
        assert overview["state"] == "draft" and overview["ready_to_pay"] is True

        # A payment that has not settled changes nothing.
        pending_payment(who)
        assert state_of(who) == "draft"

        pay(who)
        overview = client.get("/v1/verification", headers=who.headers).json()
        assert overview["state"] == "under_review"
        assert overview["paid_amount_kobo"] == 250_000
        assert overview["ready_to_pay"] is False

    def test_a_frozen_payment_does_not_send_anyone_to_review(self, client: TestClient) -> None:
        from kafriada.contexts.payments.settlement import settle_charge
        from tests._payment_helpers import charge_success_event

        who = athlete_with_files(client)
        ref = pending_payment(who)
        assert settle_charge(charge_success_event(ref, amount_kobo=1_000, fees_kobo=15)).outcome.value == "frozen"
        assert state_of(who) == "draft"

    def test_money_for_someone_with_nothing_to_review_still_settles_and_raises_an_alarm(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from kafriada.contexts.payments import settlement
        from kafriada.contexts.payments.settlement import Outcome, settle_charge
        from tests._payment_helpers import charge_success_event, record_logs

        who = new_athlete("NoDraft")
        ref = pending_payment(who)
        logs = record_logs(monkeypatch, settlement)
        result = settle_charge(charge_success_event(ref))
        assert result.outcome is Outcome.SETTLED  # real money is never lost to a verification detail
        assert logs.errors() == ["payment_without_submission"]

    def test_a_file_that_is_not_an_image_is_refused_while_the_person_is_still_on_the_form(
        self, client: TestClient
    ) -> None:
        who = new_athlete("BadFile")
        slot = client.post(
            "/v1/verification/uploads",
            json={"kind": "photo", "content_type": "image/jpeg", "size_bytes": 200},
            headers=who.headers,
        ).json()
        client.put(f"/v1/verification/uploads/{slot['media_id']}/content",
                   content=b"not an image " * 20, headers=who.headers)
        confirmed = client.post(f"/v1/verification/uploads/{slot['media_id']}/confirm", headers=who.headers)
        assert confirmed.status_code == 422 and "could not read" in confirmed.text
        overview = client.get("/v1/verification", headers=who.headers).json()
        assert overview["photo"] == "unreadable" and overview["ready_to_pay"] is False

    def test_files_cannot_be_swapped_once_the_case_is_in_review(self, client: TestClient) -> None:
        who, _ = under_review(client)
        refused = client.post(
            "/v1/verification/uploads",
            json={"kind": "photo", "content_type": "image/jpeg", "size_bytes": 100},
            headers=who.headers,
        )
        assert refused.status_code == 409
        assert "being checked" in refused.text

    def test_a_case_appears_only_in_its_own_lgas_queue_and_only_when_ready(
        self, client: TestClient
    ) -> None:
        _, request_id = under_review(client)
        here, elsewhere = reviewer(LGA), reviewer(OTHER_LGA)

        listed = client.get(f"/v1/lgas/{LGA}/verification/queue", headers=here.headers).json()
        assert str(request_id) in [i["request_id"] for i in listed]
        assert client.get(f"/v1/lgas/{LGA}/verification/queue", headers=elsewhere.headers).status_code == 403
        theirs = client.get(f"/v1/lgas/{OTHER_LGA}/verification/queue", headers=elsewhere.headers).json()
        assert str(request_id) not in [i["request_id"] for i in theirs]
        # And another LGA's coordinator cannot reach the case by naming it under their own.
        assert client.get(review_url(request_id, OTHER_LGA), headers=elsewhere.headers).status_code == 404

    def test_an_athlete_cannot_reach_any_reviewer_route(self, client: TestClient) -> None:
        who, request_id = under_review(client)
        assert client.get(f"/v1/lgas/{LGA}/verification/queue", headers=who.headers).status_code == 403
        assert client.post(review_url(request_id) + "/approve", headers=who.headers).status_code == 403
        assert state_of(who) == "under_review"


class TestTheReviewersRules:
    def test_the_case_shows_what_the_reviewer_needs_and_only_the_safe_copies(
        self, client: TestClient
    ) -> None:
        who, request_id = under_review(client, "Musa")
        boss = reviewer()
        body = client.get(review_url(request_id), headers=boss.headers).json()
        assert body["kuid"] == who.kuid
        assert body["attempt"] == 1 and body["age"] >= 18 and body["paid_kobo"] == 250_000
        assert body["waiting"] >= 1

        for kind in ("photo", "document"):
            served = client.get(review_url(request_id) + f"/media/{kind}", headers=boss.headers)
            assert served.status_code == 200
            assert served.headers["cache-control"] == "private, no-store"
            assert metadata_of(served.content) == {}  # never the original, never with a location

    def test_a_reviewer_never_sees_or_decides_their_own_record(self, client: TestClient) -> None:
        me = athlete_with_files(client, "Coordinator")
        pay(me)
        request_id = request_id_of(me)
        from kafriada.contexts.access import service as access

        # The athlete is also a coordinator of their own LGA.
        sql("INSERT INTO ops.user_roles (user_id, role_code, scope_kind, scope_id, reason) "
            "VALUES (:u, 'lga_coordinator', 'lga', :l, 'test')", u=me.user_id, l=LGA)
        token = access.issue_session(me.user_id, method="test").token
        mine = bearer(token)

        queue = client.get(f"/v1/lgas/{LGA}/verification/queue", headers=mine).json()
        assert str(request_id) not in [i["request_id"] for i in queue]
        assert client.get(review_url(request_id), headers=mine).status_code == 404
        assert client.get(review_url(request_id) + "/media/photo", headers=mine).status_code == 404
        assert client.post(review_url(request_id) + "/approve", headers=mine).status_code == 404
        assert client.post(review_url(request_id) + "/reject", json={"reason": "x"}, headers=mine).status_code == 404
        assert state_of(me) == "under_review"  # and nothing happened

        # Someone else can, so the case was never in the way.
        assert client.post(review_url(request_id) + "/approve", headers=reviewer().headers).status_code == 200

    def test_the_club_half_of_the_rule_is_honestly_absent_until_clubs_exist(self) -> None:
        # Documented, not silently skipped: there is no club table to be in conflict with.
        from kafriada.db.engine import transaction

        with transaction() as session:
            assert verification._conflict_with_club(session, UUID(int=1), UUID(int=2)) is False

    def test_a_case_that_is_not_waiting_cannot_be_decided_again(self, client: TestClient) -> None:
        _, request_id = under_review(client)
        boss = reviewer()
        assert client.post(review_url(request_id) + "/approve", headers=boss.headers).status_code == 200
        again = client.post(review_url(request_id) + "/approve", headers=boss.headers)
        assert again.status_code == 409 and "no longer waiting" in again.text
        late = client.post(review_url(request_id) + "/reject", json={"reason": "late"}, headers=boss.headers)
        assert late.status_code == 409
        assert decisions(request_id) == [("approved", None)]  # the first decision stands

    def test_a_decision_on_files_that_are_not_ready_is_refused(self, client: TestClient) -> None:
        who, request_id = under_review(client)
        sql("UPDATE identity.media_files SET status = 'uploaded' WHERE id = "
            "(SELECT photo_media_id FROM identity.verification_requests WHERE id = :r)", r=request_id)
        boss = reviewer()
        assert client.post(review_url(request_id) + "/approve", headers=boss.headers).status_code == 409
        queue = client.get(f"/v1/lgas/{LGA}/verification/queue", headers=boss.headers).json()
        assert str(request_id) not in [i["request_id"] for i in queue]
        assert state_of(who) == "under_review"


class TestRejection:
    def test_a_rejection_needs_a_reason(self, client: TestClient) -> None:
        who, request_id = under_review(client)
        boss = reviewer()
        for body in ({}, {"reason": ""}, {"reason": "   "}):
            assert client.post(review_url(request_id) + "/reject", json=body, headers=boss.headers).status_code == 422
        assert state_of(who) == "under_review" and decisions(request_id) == []

    def test_the_athlete_reads_the_reason_verbatim_and_resubmits_without_paying_again(
        self, client: TestClient
    ) -> None:
        who, request_id = under_review(client)
        boss = reviewer()
        words = "The ID document photo is too blurred to read the name. Please take it again in better light."
        done = client.post(review_url(request_id) + "/reject", json={"reason": words}, headers=boss.headers)
        assert done.json() == {"outcome": "rejected"}

        overview = client.get("/v1/verification", headers=who.headers).json()
        assert overview["state"] == "rejected"
        assert overview["reason"] == words  # exactly as written
        assert overview["attempts_left"] == 2 and overview["can_replace"] is True
        assert sms_to(who)[-1].startswith("KAFRIADA: your verification was not approved")
        assert words not in sms_to(who)[-1]  # the reason is for the screen, not for a text message

        payments_before = sql("SELECT count(*) AS n FROM money.payments WHERE paid_by = :u", u=who.user_id)
        upload(client, who, "document", make_jpeg((800, 500), gps=False))
        assert client.post("/v1/verification/resubmit", headers=who.headers).status_code == 204
        assert state_of(who) == "under_review"
        assert client.get("/v1/verification", headers=who.headers).json()["attempt"] == 2
        assert payments_before == sql("SELECT count(*) AS n FROM money.payments WHERE paid_by = :u", u=who.user_id)

    def test_resubmitting_needs_both_files_ready(self, client: TestClient) -> None:
        who, request_id = under_review(client)
        client.post(review_url(request_id) + "/reject", json={"reason": "photo unclear"}, headers=reviewer().headers)
        slot = client.post(
            "/v1/verification/uploads",
            json={"kind": "photo", "content_type": "image/jpeg", "size_bytes": 100},
            headers=who.headers,
        )
        assert slot.status_code == 201  # a new photo begun but never sent
        refused = client.post("/v1/verification/resubmit", headers=who.headers)
        assert refused.status_code == 409 and state_of(who) == "rejected"

    def test_the_third_rejection_escalates_and_closes_resubmission(self, client: TestClient) -> None:
        who, request_id = under_review(client)
        boss = reviewer()
        for attempt in (1, 2):
            client.post(review_url(request_id) + "/reject", json={"reason": f"no {attempt}"}, headers=boss.headers)
            upload(client, who, "photo", make_jpeg((320, 240), gps=False))
            assert client.post("/v1/verification/resubmit", headers=who.headers).status_code == 204
        third = client.post(review_url(request_id) + "/reject", json={"reason": "still no"}, headers=boss.headers)
        assert third.json() == {"outcome": "escalated"}
        assert state_of(who) == "escalated"

        assert client.post("/v1/verification/resubmit", headers=who.headers).status_code == 409
        blocked = client.post(
            "/v1/verification/uploads",
            json={"kind": "photo", "content_type": "image/jpeg", "size_bytes": 100},
            headers=who.headers,
        )
        assert blocked.status_code == 409
        overview = client.get("/v1/verification", headers=who.headers).json()
        assert overview["state"] == "escalated" and overview["attempts_left"] == 0
        assert overview["reason"] == "still no"
        assert [d for d, _ in decisions(request_id)] == [
            "rejected", "rejected", "rejected", "escalated"
        ]
        assert "in person" in sms_to(who)[-1]


class TestApprovalAndWithdrawal:
    def test_approval_publishes_the_badge_and_the_safe_photo_and_texts_the_athlete(
        self, client: TestClient
    ) -> None:
        who, request_id = under_review(client)
        before = client.get(f"/v1/public/athletes/{who.kuid}").json()
        assert before["is_verified"] is False and before["photo_url"] is None
        assert client.get(f"/v1/public/athletes/{who.kuid}/photo").status_code == 404  # the paywall

        assert client.post(review_url(request_id) + "/approve", headers=reviewer().headers).json() == {"outcome": "approved"}

        profile = client.get(f"/v1/public/athletes/{who.kuid}").json()
        assert profile["is_verified"] is True
        assert profile["photo_url"] == f"/v1/public/athletes/{who.kuid}/photo"
        photo = client.get(profile["photo_url"])
        assert photo.status_code == 200 and photo.headers["content-type"] == "image/jpeg"
        assert metadata_of(photo.content) == {}
        assert decisions(request_id) == [("approved", None)]
        assert "approved" in sms_to(who)[-1]
        actions = [r["action"] for r in sql(
            "SELECT action FROM ops.audit_log WHERE subject_id = :s ORDER BY id", s=str(request_id))]
        assert actions == ["verification.submitted", "verification.approved"]

    def test_the_public_profile_never_exposes_the_document_or_anything_of_the_bucket(
        self, client: TestClient
    ) -> None:
        who, request_id = under_review(client)
        client.post(review_url(request_id) + "/approve", headers=reviewer().headers)
        text_ = client.get(f"/v1/public/athletes/{who.kuid}").text
        assert "document" not in text_.lower() and "verification/" not in text_
        assert "r2.cloudflarestorage" not in text_

    def test_withdrawal_needs_the_right_permission_a_reason_and_the_password_again(
        self, client: TestClient
    ) -> None:
        who, request_id = under_review(client)
        client.post(review_url(request_id) + "/approve", headers=reviewer().headers)
        boss = super_admin(PASSWORD)
        url = f"/v1/admin/verification/{request_id}/revoke"

        # A coordinator may approve, not withdraw.
        assert client.post(url, json={"reason": "forged", "current_password": PASSWORD},
                           headers=reviewer().headers).status_code == 403
        assert client.post(url, json={"reason": "forged", "current_password": "wrong wrong wrong"},
                           headers=boss.headers).status_code == 422
        assert client.post(url, json={"reason": "  ", "current_password": PASSWORD},
                           headers=boss.headers).status_code == 422
        assert state_of(who) == "approved"

        done = client.post(url, json={"reason": "Document later found to be forged.", "current_password": PASSWORD},
                           headers=boss.headers)
        assert done.status_code == 204
        assert state_of(who) == "revoked"
        assert decisions(request_id)[-1] == ("revoked", "Document later found to be forged.")

        profile = client.get(f"/v1/public/athletes/{who.kuid}").json()
        assert profile["is_verified"] is False and profile["photo_url"] is None
        assert profile["verification_withdrawn"] is True
        assert client.get(f"/v1/public/athletes/{who.kuid}/photo").status_code == 404
        assert "withdrawn" in sms_to(who)[-1]

    def test_only_an_approved_verification_can_be_withdrawn(self, client: TestClient) -> None:
        _, request_id = under_review(client)
        boss = super_admin(PASSWORD)
        refused = client.post(
            f"/v1/admin/verification/{request_id}/revoke",
            json={"reason": "not yet", "current_password": PASSWORD}, headers=boss.headers,
        )
        assert refused.status_code == 409

    def test_a_withdrawn_athlete_can_start_again_and_the_history_is_kept(self, client: TestClient) -> None:
        who, request_id = under_review(client)
        client.post(review_url(request_id) + "/approve", headers=reviewer().headers)
        client.post(f"/v1/admin/verification/{request_id}/revoke",
                    json={"reason": "forged", "current_password": PASSWORD}, headers=super_admin(PASSWORD).headers)
        upload(client, who, "photo", make_jpeg(gps=False))  # a new draft is allowed
        assert state_of(who) == "draft"
        assert len(sql("SELECT 1 FROM identity.verification_requests v JOIN identity.athletes a "
                       "ON a.id = v.athlete_id WHERE a.user_id = :u", u=who.user_id)) == 2


class TestTheDatabaseHoldsTheLine:
    def _engine(self, name: str):  # type: ignore[no-untyped-def]
        return create_engine(os.environ[f"DATABASE_URL_{name}"], future=True)

    def test_no_role_can_edit_or_delete_a_decision(self, client: TestClient) -> None:
        _, request_id = under_review(client)
        client.post(review_url(request_id) + "/reject", json={"reason": "blurred"}, headers=reviewer().headers)
        for role in ("APP", "MONEY", "MIGRATE"):
            for sql_text in (
                "UPDATE identity.verification_decisions SET reason = 'kind words' WHERE request_id = :r",
                "DELETE FROM identity.verification_decisions WHERE request_id = :r",
            ):
                with pytest.raises(DBAPIError) as caught, self._engine(role).begin() as conn:
                    conn.execute(text(sql_text), {"r": request_id})
                assert "permission denied" in str(caught.value) or "append-only" in str(caught.value)
        assert decisions(request_id) == [("rejected", "blurred")]

    def test_a_decision_without_its_reason_cannot_exist(self, client: TestClient) -> None:
        _, request_id = under_review(client)
        reviewer_id = make_user("R")[0]
        with pytest.raises(IntegrityError):
            sql("INSERT INTO identity.verification_decisions (request_id, attempt, decision, reviewer_id) "
                "VALUES (:r, 1, 'rejected', :u)", r=request_id, u=reviewer_id)

    def test_one_athlete_cannot_hold_two_live_requests(self, client: TestClient) -> None:
        who, _ = under_review(client)
        with pytest.raises(IntegrityError):
            sql("INSERT INTO identity.verification_requests (athlete_id) "
                "SELECT id FROM identity.athletes WHERE user_id = :u", u=who.user_id)

    def test_the_attempt_cap_is_structural(self, client: TestClient) -> None:
        _, request_id = under_review(client)
        with pytest.raises(IntegrityError):
            sql("UPDATE identity.verification_requests SET attempt = 4 WHERE id = :r", r=request_id)

    def test_nothing_is_under_review_without_files_or_payment(self, client: TestClient) -> None:
        who = new_athlete("Bare")
        with pytest.raises(IntegrityError):
            sql("INSERT INTO identity.verification_requests (athlete_id, status) "
                "SELECT id, 'under_review' FROM identity.athletes WHERE user_id = :u", u=who.user_id)


class TestDocumentsDoNotOutliveTheirPurpose:
    def _backdate(self, request_id: UUID, days: int) -> None:
        sql("UPDATE identity.verification_requests SET decided_at = now() - make_interval(days => :d) "
            "WHERE id = :r", d=days, r=request_id)

    def test_a_document_is_removed_thirty_days_after_approval_and_the_photo_stays(
        self, client: TestClient, store
    ) -> None:  # type: ignore[no-untyped-def]
        who, request_id = under_review(client)
        client.post(review_url(request_id) + "/approve", headers=reviewer().headers)
        rows = sql(
            "SELECT m.id, m.kind, m.derivative_key FROM identity.media_files m JOIN "
            "identity.verification_requests v ON m.id IN (v.photo_media_id, v.document_media_id) "
            "WHERE v.id = :r", r=request_id)
        keys = {str(r["kind"]): str(r["derivative_key"]) for r in rows}

        self._backdate(request_id, 29)
        media.purge_expired_documents(store=store)
        assert store.head(keys["document"]) is not None  # not yet

        self._backdate(request_id, 31)
        media.purge_expired_documents(store=store)
        assert store.head(keys["document"]) is None
        assert store.head(keys["photo"]) is not None  # "your photo stays on your profile"
        statuses = {str(r["kind"]): str(r["status"]) for r in sql(
            "SELECT kind, status FROM identity.media_files WHERE id IN (SELECT id FROM identity.media_files "
            "WHERE athlete_id = (SELECT athlete_id FROM identity.verification_requests WHERE id = :r))",
            r=request_id)}
        assert statuses["document"] == "deleted"
        assert client.get(f"/v1/public/athletes/{who.kuid}/photo").status_code == 200

    def test_a_rejected_case_keeps_its_document_for_the_next_attempt(
        self, client: TestClient, store
    ) -> None:  # type: ignore[no-untyped-def]
        _, request_id = under_review(client)
        client.post(review_url(request_id) + "/reject", json={"reason": "photo unclear"}, headers=reviewer().headers)
        self._backdate(request_id, 90)
        (doc,) = sql("SELECT m.derivative_key FROM identity.media_files m JOIN identity.verification_requests v "
                     "ON m.id = v.document_media_id WHERE v.id = :r", r=request_id)
        media.purge_expired_documents(store=store)
        assert store.head(str(doc["derivative_key"])) is not None
