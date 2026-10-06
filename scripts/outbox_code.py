"""Print the newest email code queued for an address. Dev database only.

    api/.venv/Scripts/python.exe scripts/outbox_code.py someone@example.test

Used by web/scripts/e2e-register.mjs (CODE_CMD). Reads DATABASE_URL_APP from
api/.env. Stop the outbox dispatcher first: a delivered row is scrubbed.
"""
import re
import sys
from pathlib import Path

import psycopg

env = Path(r"C:\Users\HP\KAFRIADA\api\.env").read_text(encoding="utf-8")
url = re.search(r"^DATABASE_URL_APP=(.+)$", env, re.M).group(1).strip().strip('"')
url = url.replace("postgresql+psycopg://", "postgresql://")
with psycopg.connect(url, connect_timeout=30) as c:
    row = c.execute(
        "SELECT payload->>'body' FROM ops.outbox WHERE event_type='email.requested' "
        "AND payload->>'to' = %s ORDER BY created_at DESC LIMIT 1",
        (sys.argv[1],),
    ).fetchone()
m = re.search(r"\b(\d{6})\b", row[0] if row and row[0] else "")
print(m.group(1) if m else "")
