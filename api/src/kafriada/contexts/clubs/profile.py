"""A club's record: the fixed choices, and the check every entry point shares.

Public sign-up, a coordinator registering a club, and a club editing its details all
validate through :func:`clean`, so a club is held to the same standard however it
was created.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from kafriada.clock import today_in_nigeria
from kafriada.contexts.access import phone as phone_mod

TYPES = {"club": "Club", "academy": "Academy", "school": "School team"}
CATEGORIES = {"men": "Men", "women": "Women", "mixed": "Mixed"}
AGE_GROUPS = {"senior": "Senior", "u20": "Under 20", "u17": "Under 17", "u15": "Under 15",
              "u13": "Under 13"}
LEVELS = {"grassroots": "Grassroots", "amateur": "Amateur league",
          "semi_pro": "Semi-professional", "professional": "Professional"}
OFFICIAL_ROLES = ("Chairman", "Secretary", "Manager", "Head coach", "Owner", "Treasurer")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ProfileError(Exception):
    def __init__(self, message: str, *, field: str) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


@dataclass(frozen=True, slots=True)
class ClubProfile:
    """Everything about a club beyond its name, sport, area and phone."""

    short_name: str
    type: str
    category: str
    age_groups: tuple[str, ...]
    level: str
    year_founded: int
    ground_name: str
    ground_address: str
    town: str
    club_email: str
    official2_name: str
    official2_role: str
    official2_phone: str
    cac_number: str | None = None
    affiliation: str | None = None
    colours: str | None = None
    website: str | None = None


def clean(p: ClubProfile) -> dict[str, object]:
    """The values to store, or :class:`ProfileError` naming the first field to fix."""

    def need(value: str, field: str, message: str, longest: int) -> str:
        cleaned = " ".join((value or "").split())
        if len(cleaned) < 2:
            raise ProfileError(message, field=field)
        if len(cleaned) > longest:
            raise ProfileError(f"Keep this under {longest} characters.", field=field)
        return cleaned

    def optional(value: str | None, field: str, longest: int) -> str | None:
        cleaned = " ".join((value or "").split()) or None
        if cleaned is not None and len(cleaned) > longest:
            raise ProfileError(f"Keep this under {longest} characters.", field=field)
        return cleaned

    if p.type not in TYPES:
        raise ProfileError("Choose what kind of club this is.", field="type")
    if p.category not in CATEGORIES:
        raise ProfileError("Choose men, women or mixed.", field="category")
    groups = tuple(dict.fromkeys(p.age_groups))
    if not groups or any(g not in AGE_GROUPS for g in groups):
        raise ProfileError("Tick at least one age group.", field="age_groups")
    if p.level not in LEVELS:
        raise ProfileError("Choose the level the club plays at.", field="level")
    if not 1900 <= p.year_founded <= today_in_nigeria().year:
        raise ProfileError("Enter the year the club was founded.", field="year_founded")
    email = (p.club_email or "").strip().lower()
    if not _EMAIL_RE.match(email):
        raise ProfileError("Enter the club's email address.", field="club_email")
    if p.official2_role not in OFFICIAL_ROLES:
        raise ProfileError("Choose the second official's role.", field="official2_role")
    try:
        official2_phone = phone_mod.normalise(p.official2_phone)
    except phone_mod.InvalidPhoneNumberError as exc:
        raise ProfileError(str(exc), field="official2_phone") from exc

    return {
        "short_name": need(p.short_name, "short_name", "Enter a short name, for example JFC.", 20),
        "type": p.type,
        "category": p.category,
        "age_groups": list(groups),
        "level": p.level,
        "year_founded": p.year_founded,
        "ground_name": need(p.ground_name, "ground_name", "Enter where the club trains or plays.", 120),
        "ground_address": need(p.ground_address, "ground_address", "Enter the ground's address.", 200),
        "town": need(p.town, "town", "Enter the town.", 80),
        "club_email": email,
        "official2_name": need(p.official2_name, "official2_name",
                               "Enter a second official's full name.", 120),
        "official2_role": p.official2_role,
        "official2_phone": official2_phone,
        "cac_number": optional(p.cac_number, "cac_number", 40),
        "affiliation": optional(p.affiliation, "affiliation", 120),
        "colours": optional(p.colours, "colours", 60),
        "website": optional(p.website, "website", 200),
    }


COLUMNS = (
    "short_name", "type", "category", "age_groups", "level", "year_founded", "ground_name",
    "ground_address", "town", "club_email", "official2_name", "official2_role",
    "official2_phone", "cac_number", "affiliation", "colours", "website",
)
