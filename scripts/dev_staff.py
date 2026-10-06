"""Create test staff accounts with a password, for driving the staff screens.

    cd api && .venv/Scripts/python.exe ../scripts/dev_staff.py

Dev database only: refuses unless the API's settings say ENVIRONMENT=local.
Uses the test suite's own fixture helper (tests/_access_helpers.make_user), the
same way the database tests create staff, and marks the names as test
fixtures. Prints each account's phone and the shared password.
"""

from __future__ import annotations

import sys
from pathlib import Path

API = Path(__file__).resolve().parents[1] / "api"
sys.path.insert(0, str(API))
sys.path.insert(0, str(API / "src"))

from kafriada.settings import Environment, get_settings  # noqa: E402

if get_settings().environment is not Environment.LOCAL:
    sys.exit("Refusing: this creates staff accounts, and ENVIRONMENT is not local.")

from tests._access_helpers import make_user  # noqa: E402

PASSWORD = "a long staff phrase 42"
LGA, STATE = "NG-JG-BKD", "NG-JG"

coordinator, coordinator_phone = make_user("Test Coordinator", password=PASSWORD, grants=[("lga_coordinator", "lga", LGA)])
admin, admin_phone = make_user("Test Administrator", password=PASSWORD, grants=[("super_admin", "global", None)])
print(f"lga_coordinator ({LGA}): {coordinator_phone}")
print(f"super_admin:               {admin_phone}")
print(f"password (both):           {PASSWORD}")
