"""Private imported-account inventory for browser login jobs."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

try:
    from secure_files import atomic_write_json, atomic_write_text, exclusive_file_lock
    from webui.security_utils import redact_log_line
except ImportError:  # running from webui/
    import sys

    ROOT = Path(__file__).resolve().parent.parent
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from secure_files import atomic_write_json, atomic_write_text, exclusive_file_lock
    from security_utils import redact_log_line  # type: ignore


ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = Path(
    os.environ.get(
        "ACCOUNT_LOGIN_STATE_FILE",
        str(ROOT / "accounts" / "imported_credentials.json"),
    )
)
LOCK_PATH = STATE_PATH.with_suffix(STATE_PATH.suffix + ".lock")
ACCOUNT_FILES_DIR = ROOT / "accounts"

MAX_EMAIL_LENGTH = 254
MAX_PASSWORD_LENGTH = 1024
MAX_SSO_LENGTH = 16 * 1024
ALLOWED_STATUSES = {
    "pending",
    "queued",
    "running",
    "success",
    "sso_only",
    "failed",
    "cancelled",
}
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class AccountImportError(ValueError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _account_id(email: str) -> str:
    return hashlib.sha256(email.encode("utf-8")).hexdigest()[:20]


def _clean_text(value: object, limit: int = 240) -> str:
    text = redact_log_line(str(value or ""))
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _normalize_email(value: object) -> str:
    email = str(value or "").strip().lower()
    if not email or len(email) > MAX_EMAIL_LENGTH or not _EMAIL_RE.fullmatch(email):
        raise AccountImportError("invalid email address")
    return email


def _normalize_password(value: object) -> str:
    password = str(value or "").strip()
    if not password:
        raise AccountImportError("password is empty")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise AccountImportError("password is too long")
    if "\x00" in password or "\r" in password or "\n" in password:
        raise AccountImportError("password contains unsupported control characters")
    return password


def normalize_sso(value: object, *, required: bool = False) -> str:
    sso = str(value or "").strip()
    if sso.lower().startswith("sso="):
        sso = sso[4:].strip()
    if not sso:
        if required:
            raise AccountImportError("SSO is empty")
        return ""
    if len(sso) > MAX_SSO_LENGTH:
        raise AccountImportError("SSO is too long")
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in sso):
        raise AccountImportError("SSO contains unsupported whitespace or control characters")
    return sso


def parse_sso_values(text: object) -> list[str]:
    lines = [
        line.strip()
        for line in str(text or "").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not lines:
        raise AccountImportError("no SSO values found")
    values: list[str] = []
    seen: set[str] = set()
    for index, line in enumerate(lines, 1):
        try:
            sso = normalize_sso(line, required=True)
        except AccountImportError as exc:
            raise AccountImportError(f"row {index}: {exc}") from exc
        if sso not in seen:
            seen.add(sso)
            values.append(sso)
    return values


def _parse_csv_with_header(lines: list[str]) -> list[tuple[str, str, str]] | None:
    if not lines or "," not in lines[0]:
        return None
    rows = list(csv.reader(io.StringIO("\n".join(lines))))
    if not rows:
        return None
    header = [str(value or "").strip().lower() for value in rows[0]]
    try:
        email_index = header.index("email")
    except ValueError:
        return None
    password_index = next(
        (header.index(name) for name in ("password", "passwd") if name in header),
        None,
    )
    if password_index is None:
        return None
    sso_index = header.index("sso") if "sso" in header else None
    parsed = []
    for row in rows[1:]:
        if not row or not any(str(value or "").strip() for value in row):
            continue
        if max(email_index, password_index) >= len(row):
            raise AccountImportError("CSV row is missing email or password")
        sso = row[sso_index] if sso_index is not None and sso_index < len(row) else ""
        parsed.append((row[email_index], row[password_index], sso))
    return parsed


def parse_account_credentials(text: object) -> list[tuple[str, str, str]]:
    raw = str(text or "")
    lines = [line for line in raw.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if not lines:
        raise AccountImportError("no account credentials found")

    candidates = _parse_csv_with_header(lines)
    if candidates is None:
        candidates = []
        for line_number, line in enumerate(lines, 1):
            value = line.strip()
            if "----" in value:
                parts = value.split("----", 2)
                if len(parts) not in (2, 3):
                    raise AccountImportError(
                        f"line {line_number}: expected email----password[----sso]"
                    )
                email, password = parts[:2]
                sso = parts[2] if len(parts) == 3 else ""
            elif "\t" in value:
                parts = value.split("\t", 2)
                email, password = parts[:2]
                sso = parts[2] if len(parts) == 3 else ""
            elif "," in value:
                row = next(csv.reader([value]))
                if len(row) not in (2, 3):
                    raise AccountImportError(
                        f"line {line_number}: expected email,password[,sso]"
                    )
                email, password = row[:2]
                sso = row[2] if len(row) == 3 else ""
            elif ":" in value:
                email, password = value.split(":", 1)
                sso = ""
            else:
                raise AccountImportError(f"line {line_number}: unsupported account format")
            candidates.append((email, password, sso))

    deduplicated: dict[str, tuple[str, str]] = {}
    for index, (email_value, password_value, sso_value) in enumerate(candidates, 1):
        try:
            email = _normalize_email(email_value)
            password = _normalize_password(password_value)
            sso = normalize_sso(sso_value)
        except AccountImportError as exc:
            raise AccountImportError(f"row {index}: {exc}") from exc
        deduplicated[email] = (password, sso)
    result = [(email, password, sso) for email, (password, sso) in deduplicated.items()]
    if not result:
        raise AccountImportError("no account credentials found")
    return result


def _default_state() -> dict:
    return {"version": 1, "items": [], "updated_at": _utc_now()}


def _normalize_item(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    try:
        email = _normalize_email(raw.get("email"))
        password = _normalize_password(raw.get("password"))
    except AccountImportError:
        return None
    try:
        sso = normalize_sso(raw.get("sso"))
    except AccountImportError:
        sso = ""
    status = str(raw.get("status") or "pending").strip().lower()
    if status not in ALLOWED_STATUSES:
        status = "pending"
    created_at = _clean_text(raw.get("created_at"), 40) or _utc_now()
    return {
        "id": _account_id(email),
        "email": email,
        "password": password,
        "status": status,
        "sso": sso,
        "cpa_ok": bool(raw.get("cpa_ok")),
        "last_error": _clean_text(raw.get("last_error")),
        "created_at": created_at,
        "updated_at": _clean_text(raw.get("updated_at"), 40) or created_at,
        "last_login_at": _clean_text(raw.get("last_login_at"), 40),
    }


def _normalize_state(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("account login state must be an object")
    items_by_email: dict[str, dict] = {}
    for candidate in raw.get("items") or []:
        item = _normalize_item(candidate)
        if item:
            items_by_email[item["email"]] = item
    return {
        "version": 1,
        "items": list(items_by_email.values()),
        "updated_at": _clean_text(raw.get("updated_at"), 40) or _utc_now(),
    }


def _read_unlocked() -> dict:
    if not STATE_PATH.is_file():
        return _default_state()
    try:
        return _normalize_state(json.loads(STATE_PATH.read_text(encoding="utf-8") or "{}"))
    except Exception as exc:
        raise ValueError("imported account state cannot be read; refusing to overwrite it") from exc


def _write_unlocked(state: dict) -> None:
    state["updated_at"] = _utc_now()
    atomic_write_json(STATE_PATH, _normalize_state(state))


def _write_account_file(email: str, password: str, sso: str) -> None:
    safe_email = email.replace("/", "_").replace("\\", "_")
    atomic_write_text(
        ACCOUNT_FILES_DIR / f"{safe_email}.txt",
        f"{email}----{password}----{sso}\n",
    )


def _public_item(item: dict) -> dict:
    return {
        "id": item["id"],
        "email": item["email"],
        "status": item["status"],
        "has_password": bool(item.get("password")),
        "has_sso": bool(item.get("sso")),
        "cpa_ok": bool(item.get("cpa_ok")),
        "last_error": item.get("last_error") or "",
        "created_at": item.get("created_at") or "",
        "updated_at": item.get("updated_at") or "",
        "last_login_at": item.get("last_login_at") or "",
    }


def read_account_inventory() -> dict:
    with exclusive_file_lock(LOCK_PATH):
        state = _read_unlocked()
    items = sorted((_public_item(item) for item in state["items"]), key=lambda item: item["email"])
    summary = {
        "total": len(items),
        "pending": sum(1 for item in items if item["status"] in {"pending", "cancelled"}),
        "sso_missing": sum(
            1
            for item in items
            if not item["has_sso"] and item["status"] not in {"queued", "running"}
        ),
        "cpa_missing": sum(
            1
            for item in items
            if item["has_sso"] and not item["cpa_ok"] and item["status"] not in {"queued", "running"}
        ),
        "queued": sum(1 for item in items if item["status"] == "queued"),
        "running": sum(1 for item in items if item["status"] == "running"),
        "sso_success": sum(1 for item in items if item["has_sso"]),
        "cpa_success": sum(1 for item in items if item["cpa_ok"]),
        "failed": sum(1 for item in items if item["status"] == "failed"),
    }
    return {"ok": True, "items": items, "summary": summary, "updated_at": state["updated_at"]}


def import_account_credentials(text: object) -> dict:
    records = parse_account_credentials(text)
    now = _utc_now()
    with exclusive_file_lock(LOCK_PATH):
        state = _read_unlocked()
        by_email = {item["email"]: item for item in state["items"]}
        added = 0
        updated = 0
        unchanged = 0
        sso_imported = sum(1 for _email, _password, sso in records if sso)
        for email, password, sso in records:
            item_id = _account_id(email)
            existing = by_email.get(email)
            if existing is None:
                by_email[email] = {
                    "id": item_id,
                    "email": email,
                    "password": password,
                    "status": "sso_only" if sso else "pending",
                    "sso": sso,
                    "cpa_ok": False,
                    "last_error": "",
                    "created_at": now,
                    "updated_at": now,
                    "last_login_at": "",
                }
                added += 1
            elif existing["password"] != password or (sso and existing["sso"] != sso):
                next_sso = sso if sso else ("" if existing["password"] != password else existing["sso"])
                existing.update(
                    {
                        "password": password,
                        "status": "sso_only" if next_sso else "pending",
                        "sso": next_sso,
                        "cpa_ok": False,
                        "last_error": "",
                        "updated_at": now,
                    }
                )
                updated += 1
            else:
                unchanged += 1
        state["items"] = list(by_email.values())
        _write_unlocked(state)
        for email, password, sso in records:
            if sso:
                _write_account_file(email, password, sso)
    return {
        "ok": True,
        "input_count": len(records),
        "added": added,
        "updated": updated,
        "unchanged": unchanged,
        "sso_imported": sso_imported,
    }


def attach_sso_by_email(
    email: object,
    sso: object,
    *,
    cpa_ok: bool = False,
    last_error: object = "",
) -> dict | None:
    normalized_email = _normalize_email(email)
    normalized_sso = normalize_sso(sso, required=True)
    now = _utc_now()
    with exclusive_file_lock(LOCK_PATH):
        state = _read_unlocked()
        found = None
        for item in state["items"]:
            if item["email"] != normalized_email:
                continue
            item.update(
                {
                    "sso": normalized_sso,
                    "cpa_ok": bool(cpa_ok),
                    "status": "success" if cpa_ok else "sso_only",
                    "last_error": _clean_text(last_error),
                    "updated_at": now,
                }
            )
            found = dict(item)
            break
        if found is None:
            return None
        _write_unlocked(state)
    return found


def private_accounts(
    ids: object = None,
    *,
    pending_only: bool = False,
    include_sso_only: bool = False,
    pending_scope: str | None = None,
) -> list[dict]:
    requested = {str(value or "").strip() for value in (ids or []) if str(value or "").strip()}
    with exclusive_file_lock(LOCK_PATH):
        state = _read_unlocked()
    result = []
    for item in state["items"]:
        if requested and item["id"] not in requested:
            continue
        if pending_scope == "sso_missing":
            if item["sso"] or item["status"] in {"queued", "running"}:
                continue
        elif pending_scope == "cpa_missing":
            if (
                not item["sso"]
                or item["cpa_ok"]
                or item["status"] in {"queued", "running"}
            ):
                continue
        elif pending_only:
            allowed = {"pending", "failed", "cancelled"}
            if include_sso_only:
                allowed.add("sso_only")
            if item["status"] not in allowed:
                continue
        result.append(dict(item))
    return result


def update_account(account_id: str, **updates: object) -> dict | None:
    allowed = {"status", "sso", "cpa_ok", "last_error", "last_login_at"}
    now = _utc_now()
    with exclusive_file_lock(LOCK_PATH):
        state = _read_unlocked()
        found = None
        for item in state["items"]:
            if item["id"] != str(account_id or ""):
                continue
            for key, value in updates.items():
                if key not in allowed:
                    continue
                if key == "status":
                    status = str(value or "").strip().lower()
                    if status not in ALLOWED_STATUSES:
                        raise ValueError(f"invalid account status: {status}")
                    item[key] = status
                elif key == "cpa_ok":
                    item[key] = bool(value)
                elif key == "last_error":
                    item[key] = _clean_text(value)
                else:
                    item[key] = str(value or "").strip()
            item["updated_at"] = now
            found = dict(item)
            break
        if found is None:
            return None
        _write_unlocked(state)
    return found


def mark_accounts_queued(ids: list[str]) -> int:
    requested = {str(value or "").strip() for value in ids if str(value or "").strip()}
    now = _utc_now()
    changed = 0
    with exclusive_file_lock(LOCK_PATH):
        state = _read_unlocked()
        for item in state["items"]:
            if item["id"] not in requested:
                continue
            item["status"] = "queued"
            item["last_error"] = ""
            item["updated_at"] = now
            changed += 1
        if changed:
            _write_unlocked(state)
    return changed


def reset_incomplete_accounts(
    reason: object = "previous login job was interrupted",
    ids: object = None,
) -> int:
    message = _clean_text(reason) or "previous login job was interrupted"
    requested = (
        {str(value or "").strip() for value in (ids or []) if str(value or "").strip()}
        if ids is not None
        else None
    )
    now = _utc_now()
    changed = 0
    with exclusive_file_lock(LOCK_PATH):
        state = _read_unlocked()
        for item in state["items"]:
            if requested is not None and item["id"] not in requested:
                continue
            if item["status"] not in {"queued", "running"}:
                continue
            item["status"] = "pending"
            item["last_error"] = message
            item["updated_at"] = now
            changed += 1
        if changed:
            _write_unlocked(state)
    return changed


def delete_accounts(ids: object) -> dict:
    requested = {str(value or "").strip() for value in (ids or []) if str(value or "").strip()}
    if not requested:
        raise AccountImportError("no account ids selected")
    with exclusive_file_lock(LOCK_PATH):
        state = _read_unlocked()
        before = len(state["items"])
        state["items"] = [item for item in state["items"] if item["id"] not in requested]
        deleted = before - len(state["items"])
        if deleted:
            _write_unlocked(state)
    return {"ok": True, "deleted": deleted}
