"""Registration, the public profile, and a coordinator's list of athletes.

The two routes that matter most: the one that issues a person their permanent
identity, and the one a stranger reaches by scanning a printed card.

Both are declared ``Public``, deliberately and with a reason. Registration is
open because the register is free and open — that is the product. The profile is
open because a QR code on a card is useless if it requires an account.

The LGA list is the opposite case: scoped to the coordinator's own LGA (or their
state's), so one coordinator can never read another area's register.
"""

from __future__ import annotations

import io
from datetime import date

import segno
from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from kafriada.api.client import client_ip, request_id
from kafriada.api.security import Public, Requires
from kafriada.contexts.geography import jigawa
from kafriada.contexts.identity import service as identity
from kafriada.security.signing import build_qr_signer
from kafriada.settings import get_settings

router = APIRouter(tags=["athletes"])


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------
class RegistrationRequest(BaseModel):
    """What the registration form sends.

    Validation here is shape only — is this a date, is this a string. Whether the
    person is old enough, whether the LGA is open, whether the phone is a real
    Nigerian number: those are business rules and they live in the service, so
    they hold for every caller rather than only for this route.
    """

    full_name: str = Field(min_length=3, max_length=120)
    phone: str = Field(min_length=7, max_length=20)
    password: str = Field(min_length=10, max_length=1024)
    date_of_birth: date
    lga_id: str = Field(min_length=3, max_length=32)
    sport: str = Field(min_length=2, max_length=40)
    playing_position: str | None = Field(default=None, max_length=40)
    accept_privacy_notice: bool


class RegistrationResponse(BaseModel):
    kuid: str
    full_name: str
    lga_name: str
    profile_url: str
    qr_url: str


class PublicProfileResponse(BaseModel):
    """Exactly what a stranger is allowed to see.

    Never the phone number, never the date of birth, never a document. Age is
    derived; the birth date itself does not leave the database.
    """

    kuid: str
    full_name: str
    sport: str
    playing_position: str | None
    lga_name: str
    state_name: str
    registered_year: int
    age: int
    is_verified: bool
    photo_url: str | None
    # Whether the link carried a signature we issued. It proves the QR code came
    # from KAFRIADA — not that the person holding the card is the person shown.
    issued_by_kafriada: bool


class LgaOption(BaseModel):
    id: str
    name: str
    is_open: bool


class AthleteListing(BaseModel):
    """One line of a coordinator's register. No phone, no date of birth."""

    kuid: str
    full_name: str
    sport: str
    playing_position: str | None
    registered_on: date


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
@router.post(
    "/register",
    response_model=RegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Public("the register is free and open; this is the product")],
    summary="Register an athlete and issue their permanent KUID",
)
def register_athlete(body: RegistrationRequest, request: Request) -> RegistrationResponse:
    if not body.accept_privacy_notice:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Please accept the privacy notice to continue.",
        )

    try:
        result = identity.register(
            identity.RegistrationInput(
                full_name=body.full_name,
                phone=body.phone,
                password=body.password,
                date_of_birth=body.date_of_birth,
                lga_id=body.lga_id,
                sport=body.sport,
                playing_position=body.playing_position,
                consent_notice_version=PRIVACY_NOTICE_VERSION,
            ),
            request_id=request_id(request),
            ip_address=client_ip(request),
        )
    except identity.RegistrationError as exc:
        # A rejected registration is an ordinary outcome, not a server fault.
        # The message is written for the person reading it, and the field lets
        # the form put it next to the input that caused it.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": exc.message, "field": exc.field},
        ) from exc

    return RegistrationResponse(
        kuid=result.kuid,
        full_name=result.full_name,
        lga_name=result.lga_name,
        profile_url=_profile_url(result.kuid),
        qr_url=f"/v1/public/athletes/{result.kuid}/qr.svg",
    )


# ---------------------------------------------------------------------------
# Public profile
# ---------------------------------------------------------------------------
@router.get(
    "/public/athletes/{kuid}",
    response_model=PublicProfileResponse,
    dependencies=[Public("a QR code on a printed card must work without an account")],
    summary="Read a public athlete profile",
)
def public_profile(kuid: str, s: str | None = None) -> PublicProfileResponse:
    profile = identity.get_public_profile(kuid)
    if profile is None:
        # Deliberately the same answer for a malformed KUID and a well-formed one
        # that does not exist. Distinguishing them would let anyone walk the
        # register by testing which serials are in use.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No athlete with that KAFRIADA ID.",
        )

    signature = build_qr_signer().verify(profile.kuid, s)

    return PublicProfileResponse(
        kuid=profile.kuid,
        full_name=profile.full_name,
        sport=profile.sport,
        playing_position=profile.playing_position,
        lga_name=profile.lga_name,
        state_name=profile.state_name,
        registered_year=profile.registered_year,
        age=profile.age,
        is_verified=profile.is_verified,
        # The photo is the paid product. Until a verification is approved there
        # is nothing to show, and the absence is the paywall.
        photo_url=profile.photo_url if profile.is_verified else None,
        issued_by_kafriada=signature.valid,
    )


@router.get(
    "/public/athletes/{kuid}/qr.svg",
    dependencies=[Public("the QR image is printed on cards and posters")],
    summary="The signed QR code for an athlete's profile",
    response_class=Response,
)
def athlete_qr(kuid: str) -> Response:
    """Render the athlete's QR code as SVG.

    Generated on the server, always. The signature is what makes a card
    verifiable, and a browser cannot be trusted with the key that produces it.
    SVG rather than a bitmap so it prints sharply at any size — these are cut out
    and carried in wallets.
    """
    profile = identity.get_public_profile(kuid)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")

    target = _profile_url(profile.kuid, signed=True)
    # Bytes, not text: segno writes encoded SVG.
    buffer = io.BytesIO()
    # Error correction M tolerates roughly 15% damage — a card that has been in
    # a pocket for a season still scans.
    segno.make(target, error="m").save(buffer, kind="svg", scale=6, border=2)

    return Response(
        content=buffer.getvalue().decode("utf-8"),
        media_type="image/svg+xml",
        headers={
            # A KUID's QR never changes, so it can be cached hard.
            "Cache-Control": "public, max-age=86400",
            "Content-Disposition": f'inline; filename="{profile.kuid}.svg"',
        },
    )


# ---------------------------------------------------------------------------
# A coordinator's register
# ---------------------------------------------------------------------------
@router.get(
    "/lgas/{lga_id}/athletes",
    response_model=list[AthleteListing],
    dependencies=[Requires("athlete.search_scoped", scope="lga")],
    summary="Athletes currently in one LGA, newest first",
)
def athletes_in_lga(lga_id: str) -> list[AthleteListing]:
    listing = identity.list_athletes_in_lga(lga_id)
    if listing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such LGA.")
    return [
        AthleteListing(
            kuid=a.kuid,
            full_name=a.full_name,
            sport=a.sport,
            playing_position=a.playing_position,
            registered_on=a.registered_on,
        )
        for a in listing
    ]


# ---------------------------------------------------------------------------
# Supporting data for the registration form
# ---------------------------------------------------------------------------
@router.get(
    "/public/lgas",
    response_model=list[LgaOption],
    dependencies=[Public("the registration form needs the list before sign-up")],
    summary="Local Government Areas, and which are open for registration",
)
def list_lgas() -> list[LgaOption]:
    """All 27, with their rollout state.

    Closed LGAs are returned rather than hidden, so the form can say
    "registration opens in your LGA soon" instead of leaving someone unable to
    find where they live and assuming the whole thing is broken.
    """
    from sqlalchemy import text

    from kafriada.db.engine import transaction

    with transaction() as session:
        rows = session.execute(
            text(
                """
                SELECT id, name, is_live
                  FROM ops.locations
                 WHERE kind = 'lga' AND parent_id = :state
                 ORDER BY is_live DESC, name
                """
            ),
            {"state": f"NG-{jigawa.STATE_CODE}"},
        ).mappings().all()

    return [
        LgaOption(id=row["id"], name=row["name"], is_open=row["is_live"]) for row in rows
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
PRIVACY_NOTICE_VERSION = "1.0"


def _profile_url(kuid: str, *, signed: bool = False) -> str:
    """The address printed on a card.

    Relative unless signed. The signed form is what the QR encodes, and it needs
    the full public address because it is scanned by a phone camera that has no
    idea what site it came from.
    """
    if not signed:
        return f"/a/{kuid}"
    cfg = get_settings()
    base = cfg.public_base_url.rstrip("/")
    signature = build_qr_signer(cfg).sign(kuid)
    return f"{base}/a/{kuid}?s={signature}"
