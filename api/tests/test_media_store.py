"""The object store: a signature Amazon published an answer for, and the walls around keys.

No database and no network. What is proved here:
  - the SigV4 presigner reproduces the signature in Amazon's own worked example
    (the one place a bug would otherwise only surface against real R2)
  - a key that is not ours — a path, a parent reference, an odd character — is refused
    before it can leave the bucket or the storage directory
  - the local store round-trips, refuses oversize reads, and cannot be walked out of
  - the R2 adapter signs the request it sends, addresses the bucket path-style, and
    sorts failures into transient and permanent
  - the settings refuse a half-configured or development-only store where it matters
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from kafriada.contexts.media import store as store_mod
from kafriada.contexts.media.store import (
    LocalStore,
    NoStore,
    NotConfigured,
    R2Store,
    StoreError,
    build_store,
    presign_url,
)
from kafriada.settings import Environment
from tests.test_settings_refuses_insecure_config import build, production

# From Amazon's documentation for query-string authentication ("Example: presigned GET").
AWS_EXAMPLE_SIGNATURE = "aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404"


def r2_settings(**over: object):  # type: ignore[no-untyped-def]
    return build(
        media_store="r2", r2_account_id="acct123", r2_access_key_id="AKIAEXAMPLE",
        r2_secret_access_key="s" * 30, r2_bucket="kafriada-media", **over,
    )


class TestSigner:
    def test_it_reproduces_amazons_published_signature(self) -> None:
        url = presign_url(
            method="GET",
            host="examplebucket.s3.amazonaws.com",
            path="/test.txt",
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            region="us-east-1",
            now=datetime(2013, 5, 24, 0, 0, 0, tzinfo=UTC),
            expires_seconds=86_400,
        )
        assert url.endswith(f"X-Amz-Signature={AWS_EXAMPLE_SIGNATURE}")

    def test_a_different_method_or_path_gives_a_different_signature(self) -> None:
        def sig(**kw: object) -> str:
            base: dict[str, object] = dict(
                method="GET", host="h.example", path="/b/k", access_key="A", secret_key="S",
                region="auto", now=datetime(2026, 1, 1, tzinfo=UTC), expires_seconds=60,
            )
            base.update(kw)
            return presign_url(**base).rsplit("=", 1)[1]  # type: ignore[arg-type]

        assert len({sig(), sig(method="PUT"), sig(path="/b/other"), sig(expires_seconds=61)}) == 4


class TestKeys:
    @pytest.mark.parametrize(
        "key",
        ["", "/abs", "a/../b", "../x", "a//b", "trailing/", "with space", "semi;colon", "x" * 400,
         "verification/a/b\nc"],
    )
    def test_a_key_that_is_not_one_of_ours_is_refused(self, tmp_path: Path, key: str) -> None:
        with pytest.raises(StoreError) as caught:
            LocalStore(tmp_path).put(key, b"x")
        assert caught.value.transient is False

    def test_our_own_keys_are_accepted(self, tmp_path: Path) -> None:
        LocalStore(tmp_path).put("verification/6f1c1f8e-2b7a/9d47/derivative.jpg", b"x")


class TestLocalStore:
    def test_it_round_trips_and_deletes(self, tmp_path: Path) -> None:
        s = LocalStore(tmp_path)
        assert s.head("a/b") is None and s.get("a/b", max_bytes=10) is None
        s.put("a/b", b"hello")
        assert s.head("a/b").size_bytes == 5  # type: ignore[union-attr]
        assert s.get("a/b", max_bytes=10) == b"hello"
        s.delete("a/b")
        assert s.head("a/b") is None
        s.delete("a/b")  # deleting what is not there is not an error

    def test_it_will_not_hand_back_more_than_asked(self, tmp_path: Path) -> None:
        s = LocalStore(tmp_path)
        s.put("big", b"x" * 100)
        with pytest.raises(StoreError):
            s.get("big", max_bytes=10)

    def test_it_relays_because_it_has_no_public_address(self, tmp_path: Path) -> None:
        assert LocalStore(tmp_path).presign_put("a", expires_seconds=60) is None


class TestR2Adapter:
    def test_a_presigned_put_addresses_the_bucket_path_style_and_carries_a_signature(self) -> None:
        url = R2Store(r2_settings()).presign_put("verification/x/original", expires_seconds=900)
        assert url is not None
        assert url.startswith(
            "https://acct123.r2.cloudflarestorage.com/kafriada-media/verification/x/original?"
        )
        assert "X-Amz-Expires=900" in url and "X-Amz-Signature=" in url
        assert "s" * 30 not in url  # the secret never appears in what a browser is given

    def test_head_get_put_delete_each_send_a_signed_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[tuple[str, str]] = []

        def request(method: str, url: str, **kw: object) -> httpx.Response:
            seen.append((method, url))
            return httpx.Response(200, content=b"data", headers={"content-length": "4"})

        monkeypatch.setattr(store_mod.httpx, "request", request)
        s = R2Store(r2_settings())
        s.put("k", b"data")
        assert s.head("k").size_bytes == 4  # type: ignore[union-attr]
        assert s.get("k", max_bytes=10) == b"data"
        s.delete("k")
        assert [m for m, _ in seen] == ["PUT", "HEAD", "GET", "DELETE"]
        assert all("X-Amz-Signature=" in u for _, u in seen)

    def test_missing_is_none_and_failures_are_sorted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        answers = iter(
            [httpx.Response(404), httpx.Response(404), httpx.Response(503), httpx.Response(403)]
        )
        monkeypatch.setattr(store_mod.httpx, "request", lambda *a, **k: next(answers))
        s = R2Store(r2_settings())
        assert s.head("k") is None
        assert s.get("k", max_bytes=1) is None
        with pytest.raises(StoreError) as transient:
            s.put("k", b"x")
        assert transient.value.transient is True
        with pytest.raises(StoreError) as permanent:
            s.put("k", b"x")
        assert permanent.value.transient is False

    def test_an_unreachable_bucket_is_transient(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def down(*a: object, **k: object) -> httpx.Response:
            raise httpx.ConnectTimeout("slow")

        monkeypatch.setattr(store_mod.httpx, "request", down)
        with pytest.raises(StoreError) as caught:
            R2Store(r2_settings()).head("k")
        assert caught.value.transient is True


class TestChoosingAStore:
    def test_none_is_the_default_and_refuses_everything(self) -> None:
        chosen = build_store(build())
        assert isinstance(chosen, NoStore)
        with pytest.raises(NotConfigured):
            chosen.put("k", b"x")

    def test_local_and_r2_are_chosen_by_configuration(self, tmp_path: Path) -> None:
        local = build(media_store="local", media_local_dir=str(tmp_path))
        assert isinstance(build_store(local), LocalStore)
        assert isinstance(build_store(r2_settings()), R2Store)

    def test_r2_with_a_missing_credential_will_not_start(self) -> None:
        with pytest.raises(ValidationError, match="r2_bucket"):
            build(
                media_store="r2", r2_account_id="a", r2_access_key_id="b",
                r2_secret_access_key="c" * 30,
            )

    def test_the_local_store_is_refused_outside_local_development(self) -> None:
        with pytest.raises(ValidationError, match="local development only"):
            build(media_store="local", environment=Environment.STAGING)

    @pytest.mark.parametrize("kind", ["none", "local"])
    def test_production_will_not_start_without_r2(self, kind: str) -> None:
        with pytest.raises(ValidationError, match="media_store"):
            production(media_store=kind)
