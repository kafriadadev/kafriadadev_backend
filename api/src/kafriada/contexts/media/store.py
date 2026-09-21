"""Where photographs and identity documents are kept.

One small interface, so the code that decides *who may see a file* never knows
*where the bytes live* — the same shape as the SMS and payment ports. Cloudflare
R2 is the real adapter; a directory on this machine serves development and tests.

**The bucket is private, always.** If it were public the 2,500-naira paywall could
be bypassed by anyone who guessed a URL, and identity documents would be one typo
from the open internet. Nothing here mints a public address. Bytes leave only
through a caller that has already passed a permission check.

**R2 is spoken to in the S3 dialect with hand-built SigV4 query signatures**, not
through an SDK: presigning is fifty lines and a published test vector, and an SDK
would be a large dependency for a handful of calls. The signer is pure and is
proved against Amazon's own worked example (tests/test_media_store.py).
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import httpx

from kafriada.settings import MediaStoreKind, Settings, get_settings


class StoreError(Exception):
    """The store could not do what was asked. Nothing was half-written."""

    def __init__(self, message: str, *, transient: bool = True) -> None:
        super().__init__(message)
        self.message = message
        self.transient = transient


class NotConfigured(StoreError):
    def __init__(self) -> None:
        super().__init__("no media store is configured", transient=True)


@dataclass(frozen=True, slots=True)
class ObjectInfo:
    size_bytes: int


class ObjectStore(Protocol):
    name: str
    # True when a browser can PUT straight to the bucket with a presigned URL.
    direct_upload: bool

    def presign_put(self, key: str, *, expires_seconds: int) -> str | None: ...
    def put(self, key: str, data: bytes) -> None: ...
    def head(self, key: str) -> ObjectInfo | None: ...
    def get(self, key: str, *, max_bytes: int) -> bytes | None: ...
    def delete(self, key: str) -> None: ...


# Keys are ours, built from UUIDs and fixed words. Refusing anything else here
# means a bug upstream can never turn a key into a path that leaves the bucket.
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9/_.-]{0,300}")


def _checked(key: str) -> str:
    if not _KEY.fullmatch(key) or ".." in key or "//" in key or key.endswith("/"):
        raise StoreError(f"refusing to use {key!r} as an object key", transient=False)
    return key


class NoStore:
    name = "none"
    direct_upload = False

    def presign_put(self, key: str, *, expires_seconds: int) -> str | None:
        raise NotConfigured()

    def put(self, key: str, data: bytes) -> None:
        raise NotConfigured()

    def head(self, key: str) -> ObjectInfo | None:
        raise NotConfigured()

    def get(self, key: str, *, max_bytes: int) -> bytes | None:
        raise NotConfigured()

    def delete(self, key: str) -> None:
        raise NotConfigured()


class LocalStore:
    """A directory on this machine. Development and tests only."""

    name = "local"
    direct_upload = False

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self._root / _checked(key)).resolve()
        if self._root not in path.parents:
            raise StoreError("key escapes the store", transient=False)
        return path

    def presign_put(self, key: str, *, expires_seconds: int) -> str | None:
        return None  # uploads relay through the API

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def head(self, key: str) -> ObjectInfo | None:
        path = self._path(key)
        return ObjectInfo(path.stat().st_size) if path.is_file() else None

    def get(self, key: str, *, max_bytes: int) -> bytes | None:
        path = self._path(key)
        if not path.is_file():
            return None
        if path.stat().st_size > max_bytes:
            raise StoreError("object is larger than the caller will accept", transient=False)
        return path.read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# R2
# ---------------------------------------------------------------------------
def presign_url(
    *,
    method: str,
    host: str,
    path: str,
    access_key: str,
    secret_key: str,
    region: str,
    now: datetime,
    expires_seconds: int,
) -> str:
    """A SigV4 query-string signature for one request. Pure.

    Only ``host`` is signed, so the caller may attach any body and content type;
    what actually arrives is checked after the fact, not promised in advance.
    """
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    day = amz_date[:8]
    scope = f"{day}/{region}/s3/aws4_request"
    encoded_path = quote(path, safe="/-_.~")

    query = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": f"{access_key}/{scope}",
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(expires_seconds),
        "X-Amz-SignedHeaders": "host",
    }
    canonical_query = "&".join(
        f"{quote(k, safe='-_.~')}={quote(v, safe='-_.~')}" for k, v in sorted(query.items())
    )
    canonical_request = "\n".join(
        [method, encoded_path, canonical_query, f"host:{host}\n", "host", "UNSIGNED-PAYLOAD"]
    )
    to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ]
    )

    def _hmac(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    signing_key = _hmac(
        _hmac(_hmac(_hmac(("AWS4" + secret_key).encode(), day), region), "s3"),
        "aws4_request",
    )
    signature = hmac.new(signing_key, to_sign.encode(), hashlib.sha256).hexdigest()
    return f"https://{host}{encoded_path}?{canonical_query}&X-Amz-Signature={signature}"


class R2Store:
    """A private Cloudflare R2 bucket, addressed path-style."""

    name = "r2"
    direct_upload = True

    def __init__(self, settings: Settings | None = None) -> None:
        cfg = settings or get_settings()
        if not (
            cfg.r2_account_id and cfg.r2_access_key_id and cfg.r2_secret_access_key and cfg.r2_bucket
        ):
            raise NotConfigured()
        self._host = f"{cfg.r2_account_id}.r2.cloudflarestorage.com"
        self._bucket = cfg.r2_bucket
        self._access = cfg.r2_access_key_id
        self._secret = cfg.r2_secret_access_key.get_secret_value()
        self._timeout = cfg.media_timeout_seconds

    def _url(self, method: str, key: str, expires_seconds: int = 60) -> str:
        return presign_url(
            method=method,
            host=self._host,
            path=f"/{self._bucket}/{_checked(key)}",
            access_key=self._access,
            secret_key=self._secret,
            region="auto",
            now=datetime.now(UTC),
            expires_seconds=expires_seconds,
        )

    def _call(self, method: str, key: str, **kwargs: object) -> httpx.Response:
        try:
            return httpx.request(
                method, self._url(method, key), timeout=self._timeout, **kwargs  # type: ignore[arg-type]
            )
        except httpx.HTTPError as exc:
            raise StoreError(f"r2 unreachable: {type(exc).__name__}") from exc

    def presign_put(self, key: str, *, expires_seconds: int) -> str | None:
        return self._url("PUT", key, expires_seconds)

    def put(self, key: str, data: bytes) -> None:
        response = self._call("PUT", key, content=data)
        if not response.is_success:
            raise StoreError(f"r2 refused a write ({response.status_code})", transient=response.status_code >= 500)

    def head(self, key: str) -> ObjectInfo | None:
        response = self._call("HEAD", key)
        if response.status_code == 404:
            return None
        if not response.is_success:
            raise StoreError(f"r2 head failed ({response.status_code})", transient=response.status_code >= 500)
        return ObjectInfo(int(response.headers.get("content-length", "0")))

    def get(self, key: str, *, max_bytes: int) -> bytes | None:
        response = self._call("GET", key)
        if response.status_code == 404:
            return None
        if not response.is_success:
            raise StoreError(f"r2 read failed ({response.status_code})", transient=response.status_code >= 500)
        if len(response.content) > max_bytes:
            raise StoreError("object is larger than the caller will accept", transient=False)
        return response.content

    def delete(self, key: str) -> None:
        response = self._call("DELETE", key)
        if not response.is_success and response.status_code != 404:
            raise StoreError(f"r2 delete failed ({response.status_code})", transient=response.status_code >= 500)


def build_store(settings: Settings | None = None) -> ObjectStore:
    cfg = settings or get_settings()
    match cfg.media_store:
        case MediaStoreKind.R2:
            return R2Store(cfg)
        case MediaStoreKind.LOCAL:
            return LocalStore(cfg.media_local_dir)
        case _:
            return NoStore()
