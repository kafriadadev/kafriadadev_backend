"""Print the newest one-time code queued for a person. Dev database only.

    api/.venv/Scripts/python.exe scripts/outbox_code.py someone@example.test
    api/.venv/Scripts/python.exe scripts/outbox_code.py 08031234567

Give an email address or a phone number. Codes go by email or by SMS depending on
OTP_CHANNEL, so both are looked at: the account's email and its phone. Used by
web/scripts/e2e-register.mjs (CODE_CMD). Reads DATABASE_URL_APP from api/.env.
Stop the outbox dispatcher first: a delivered row is scrubbed of its code.
"""
import re
import sys
from pathlib import Path

import psycopg


def as_e164(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("234"):
        return "+" + digits
    if digits.startswith("0") and len(digits) == 11:
        return "+234" + digits[1:]
    if len(digits) == 10:
        return "+234" + digits
    return None


env = Path(r"C:\Users\HP\KAFRIADA\api\.env").read_text(encoding="utf-8")
url = re.search(r"^DATABASE_URL_APP=(.+)$", env, re.M).group(1).strip().strip('"')
url = url.replace("postgresql+psycopg://", "postgresql://")
who = sys.argv[1].strip()
email = who.lower() if "@" in who else None
phone = None if email else as_e164(who)

with psycopg.connect(url, connect_timeout=30) as c:
    # The account behind either identifier, so the other one is searched too.
    user = c.execute(
        "SELECT lower(email), phone_e164 FROM ops.users WHERE anonymised_at IS NULL "
        "AND (lower(email) = %s OR phone_e164 = %s) LIMIT 1",
        (email, phone),
    ).fetchone()
    if user:
        email, phone = user
    row = c.execute(
        "SELECT payload->>'body' FROM ops.outbox "
        "WHERE event_type IN ('email.requested', 'sms.requested') AND processed_at IS NULL "
        "AND (lower(payload->>'to') = %s OR payload->>'to' = %s) "
        "ORDER BY created_at DESC LIMIT 1",
        (email, phone),
    ).fetchone()
m = re.search(r"\b(\d{6})\b", row[0] if row and row[0] else "")
print(m.group(1) if m else "")
