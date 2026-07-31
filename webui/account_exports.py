"""Build authenticated account exports from the local text account store."""

from __future__ import annotations

import csv
import io
import time
from pathlib import Path

from sso_to_auth_json import load_sso_records


ROOT = Path(__file__).resolve().parent.parent
ACCOUNTS_DIR = ROOT / "accounts"


def account_records() -> list:
    """Load account and pending-SSO files using the recovery parser."""
    return load_sso_records(accounts_dir=str(ACCOUNTS_DIR))


def sso_values() -> list[str]:
    """Return unique SSO values, including records in ``sso_pending.txt``."""
    return [record.sso for record in account_records() if record.sso]


def credential_rows() -> list[dict[str, str]]:
    """Return one email/password row per locally stored account."""
    rows: dict[str, dict[str, str]] = {}
    for record in account_records():
        email = str(record.email or "").strip()
        if "@" not in email or any(char.isspace() for char in email):
            continue
        key = email.lower()
        previous = rows.get(key)
        password = str(record.password or "")
        if previous is None or (not previous["password"] and password):
            rows[key] = {"email": email, "password": password}
    return [rows[key] for key in sorted(rows)]


def sso_export() -> tuple[str, bytes]:
    values = sso_values()
    if not values:
        raise LookupError("没有可导出的 SSO")
    timestamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    body = ("\n".join(values) + "\n").encode("utf-8")
    return f"grok-register-sso-{timestamp}.txt", body


def credentials_csv_export() -> tuple[str, bytes]:
    rows = credential_rows()
    if not rows:
        raise LookupError("没有可导出的账号")
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(["email", "passwd"])
    for row in rows:
        writer.writerow([row["email"], row["password"]])
    timestamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    body = ("\ufeff" + output.getvalue()).encode("utf-8")
    return f"grok-register-accounts-{timestamp}.csv", body
