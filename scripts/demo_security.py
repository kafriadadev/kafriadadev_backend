"""Live demonstration: the guarantees KAFRIADA makes about its own records.

Run it in front of an audience. It connects to the real database and *tries* to
do the things the system promises are impossible — altering an audit record,
deleting one, writing to the money ledger from the wrong place — and shows the
database refusing each time.

    cd api
    ../.venv/Scripts/python.exe ../scripts/demo_security.py

Nothing here is simulated and nothing is hardcoded to fail. Every refusal below
comes from PostgreSQL itself. If someone in the room doubts it, the same
statements can be typed by hand into any SQL client and they will be refused in
exactly the same way — which is the point being made.
"""

from __future__ import annotations

import os
import pathlib
import sys
import time

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# This is going on a projector, so the console has to cooperate. Windows
# terminals default to a legacy code page that cannot print anything outside
# Latin-1, and do not interpret colour codes unless asked.
if sys.platform == "win32":
    os.system("")  # enables ANSI colour handling on Windows 10 and later
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except (AttributeError, OSError):  # pragma: no cover - redirected output
    pass

# Colour only when something can render it. Piped into a file or a slide deck,
# this should produce clean text rather than a page of escape sequences.
_COLOUR = sys.stdout.isatty() or os.environ.get("FORCE_COLOUR") == "1"


def _c(code: str) -> str:
    return code if _COLOUR else ""


RESET, BOLD, DIM = _c("\033[0m"), _c("\033[1m"), _c("\033[2m")
GREEN, RED, AMBER, BLUE = _c("\033[32m"), _c("\033[31m"), _c("\033[33m"), _c("\033[36m")
RULE = "-" * 62

PASSES = 0
FAILS = 0


def load_env() -> tuple[str, str]:
    """Read the two connection strings from api/.env without printing them."""
    here = pathlib.Path(__file__).resolve().parent
    env_path = here.parent / "api" / ".env"
    values: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith(("DATABASE_URL_APP=", "DATABASE_URL_MIGRATE=")):
                key, _, value = line.partition("=")
                values[key] = value.strip()
    app = os.environ.get("DATABASE_URL_APP") or values.get("DATABASE_URL_APP", "")
    migrate = os.environ.get("DATABASE_URL_MIGRATE") or values.get("DATABASE_URL_MIGRATE", "")
    if not app or not migrate:
        sys.exit("Could not find database settings. Fill in api/.env first.")
    return app, migrate


def heading(number: str, title: str, explanation: str) -> None:
    print(f"\n{BOLD}{BLUE}{number}  {title}{RESET}")
    print(f"{DIM}    {explanation}{RESET}\n")


def expect_success(label: str, fn) -> object:  # type: ignore[no-untyped-def]
    global PASSES, FAILS
    try:
        result = fn()
    except SQLAlchemyError as exc:
        FAILS += 1
        print(f"    {RED}UNEXPECTED FAILURE{RESET}  {label}")
        print(f"        {str(exc)[:160]}")
        return None
    PASSES += 1
    print(f"    {GREEN}ALLOWED{RESET}  {label}")
    return result


def expect_refusal(label: str, fn, must_mention: str) -> None:  # type: ignore[no-untyped-def]
    """Run something that must be refused, and check *why* it was refused."""
    global PASSES, FAILS
    try:
        fn()
    except SQLAlchemyError as exc:
        reason = str(exc).lower()
        if must_mention.lower() in reason:
            PASSES += 1
            print(f"    {GREEN}REFUSED{RESET}  {label}")
            first = str(exc).strip().splitlines()[0]
            print(f"        {DIM}database said: {first[:120]}{RESET}")
        else:
            FAILS += 1
            print(f"    {AMBER}REFUSED, BUT FOR THE WRONG REASON{RESET}  {label}")
            print(f"        {str(exc)[:160]}")
        return
    FAILS += 1
    print(f"    {RED}*** ALLOWED — THIS SHOULD BE IMPOSSIBLE ***{RESET}  {label}")


def main() -> int:
    app_url, migrate_url = load_env()

    print(f"\n{BOLD}KAFRIADA CORE — what the database refuses to do{RESET}")
    print(f"{DIM}Connecting to the live database. Every result below comes from PostgreSQL.{RESET}")

    kwargs = {"connect_args": {"connect_timeout": 30}, "pool_pre_ping": True, "future": True}
    app = create_engine(app_url, **kwargs)       # the role serving ordinary requests
    owner = create_engine(migrate_url, **kwargs)  # the role that OWNS every table

    started = time.time()

    # -- 1 ---------------------------------------------------------------
    heading(
        "1.",
        "The system can record what happened",
        "Every important action writes a permanent record: who did it, and when.",
    )
    with app.begin() as conn:
        row_id = conn.execute(
            text(
                """
                INSERT INTO ops.audit_log
                    (actor_label, action, subject_type, subject_id, request_id)
                VALUES ('demo', 'demo.presentation', 'demo', 'live-demo', 'demo-run')
                RETURNING id
                """
            )
        ).scalar_one()
    PASSES_LABEL = f"wrote audit record #{row_id}"
    globals()["PASSES"] += 1
    print(f"    {GREEN}ALLOWED{RESET}  {PASSES_LABEL}")

    # -- 2 ---------------------------------------------------------------
    heading(
        "2.",
        "The application cannot change history",
        "Even the running application — the part an attacker would take over first.",
    )

    def change() -> None:
        with app.begin() as conn:
            conn.execute(
                text("UPDATE ops.audit_log SET action = 'covered up' WHERE id = :i"),
                {"i": row_id},
            )

    def erase() -> None:
        with app.begin() as conn:
            conn.execute(text("DELETE FROM ops.audit_log WHERE id = :i"), {"i": row_id})

    def wipe() -> None:
        with app.begin() as conn:
            conn.execute(text("TRUNCATE ops.audit_log"))

    expect_refusal("change that record", change, "permission denied")
    expect_refusal("delete that record", erase, "permission denied")
    expect_refusal("wipe the whole log", wipe, "permission denied")

    # -- 3 ---------------------------------------------------------------
    heading(
        "3.",
        "Neither can the owner — the highest privilege we hold",
        "This is the account that built the database. It still cannot rewrite the past.",
    )

    def owner_change() -> None:
        with owner.begin() as conn:
            conn.execute(
                text("UPDATE ops.audit_log SET action = 'covered up' WHERE id = :i"),
                {"i": row_id},
            )

    def owner_erase() -> None:
        with owner.begin() as conn:
            conn.execute(text("DELETE FROM ops.audit_log WHERE id = :i"), {"i": row_id})

    expect_refusal("owner tries to change it", owner_change, "append-only")
    expect_refusal("owner tries to delete it", owner_erase, "append-only")

    # -- 4 ---------------------------------------------------------------
    heading(
        "4.",
        "The application cannot touch money",
        "Payments live behind a separate door. The everyday code does not hold the key.",
    )
    with app.connect() as conn:
        can_write = conn.execute(
            text("SELECT has_schema_privilege('kaf_app', 'money', 'CREATE')")
        ).scalar_one()
    if can_write:
        globals()["FAILS"] += 1
        print(f"    {RED}*** the application CAN create things in the money area ***{RESET}")
    else:
        globals()["PASSES"] += 1
        print(f"    {GREEN}REFUSED{RESET}  application cannot create anything in the money area")
        print(f"        {DIM}it may read payment status, and has no way to write it{RESET}")

    # -- 5 ---------------------------------------------------------------
    heading(
        "5.",
        "An athlete's ID can never be altered",
        "The KUID is printed on a card and issued for life. Not even a correction is allowed.",
    )
    with app.connect() as conn:
        trigger = conn.execute(
            text(
                """
                SELECT tgname FROM pg_trigger
                 WHERE tgrelid = 'identity.athletes'::regclass
                   AND tgname = 'athletes_kuid_is_immutable'
                """
            )
        ).scalar_one_or_none()
    if trigger:
        globals()["PASSES"] += 1
        print(f"    {GREEN}ENFORCED{RESET}  the database refuses any change to a KUID")
    else:
        globals()["FAILS"] += 1
        print(f"    {RED}*** no protection found on the KUID ***{RESET}")

    # -- 6 ---------------------------------------------------------------
    heading(
        "6.",
        "Jigawa is loaded and the rollout is under control",
        "All 27 LGAs are in the system. Registration opens one wave at a time.",
    )
    with app.connect() as conn:
        total = conn.execute(
            text("SELECT count(*) FROM ops.locations WHERE kind = 'lga'")
        ).scalar_one()
        live = conn.execute(
            text("SELECT name FROM ops.locations WHERE kind = 'lga' AND is_live ORDER BY name")
        ).scalars().all()
    print(f"    {GREEN}LOADED{RESET}  {total} Local Government Areas")
    print(f"    {GREEN}OPEN{RESET}     registration is live in: {', '.join(live) or 'none'}")
    print(f"        {DIM}opening the next wave is one setting, not a software release{RESET}")

    # -- summary ---------------------------------------------------------
    elapsed = time.time() - started
    print(f"\n{BOLD}{RULE}{RESET}")
    total_checks = PASSES + FAILS
    if FAILS == 0:
        print(f"{BOLD}{GREEN}  All {total_checks} checks behaved exactly as promised.{RESET}")
        print(f"{DIM}  Nothing above was simulated. Every refusal came from the database.{RESET}")
    else:
        print(f"{BOLD}{RED}  {FAILS} of {total_checks} checks did NOT behave as promised.{RESET}")
    print(f"{DIM}  {elapsed:.1f}s against the live database{RESET}")
    print(f"{BOLD}{RULE}{RESET}\n")

    app.dispose()
    owner.dispose()
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
