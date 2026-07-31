# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webui import account_login_store as store


def _with_temp_store(temp: str):
    previous = store.STATE_PATH, store.LOCK_PATH
    store.STATE_PATH = Path(temp) / "imported_credentials.json"
    store.LOCK_PATH = Path(temp) / "imported_credentials.json.lock"
    return previous


def test_import_formats_and_public_secret_redaction():
    with tempfile.TemporaryDirectory() as temp:
        previous = _with_temp_store(temp)
        try:
            inputs = [
                "one@example.test----Pass-One!",
                "two@example.test,Pass-Two!",
                "three@example.test:Pass:Three!",
                "four@example.test\tPass-Four!",
                'email,passwd\nfive@example.test,"Pass,Five!"',
            ]
            for value in inputs:
                result = store.import_account_credentials(value)
                assert result["ok"] is True

            public = store.read_account_inventory()
            assert public["summary"]["total"] == 5
            encoded = json.dumps(public, ensure_ascii=False)
            for secret in ("Pass-One!", "Pass-Two!", "Pass:Three!", "Pass-Four!", "Pass,Five!"):
                assert secret not in encoded
            assert all(item["has_password"] for item in public["items"])
            assert all("password" not in item and "sso" not in item for item in public["items"])

            private = {item["email"]: item for item in store.private_accounts()}
            assert private["three@example.test"]["password"] == "Pass:Three!"
            assert private["five@example.test"]["password"] == "Pass,Five!"
        finally:
            store.STATE_PATH, store.LOCK_PATH = previous


def test_deduplicate_update_and_status_changes():
    with tempfile.TemporaryDirectory() as temp:
        previous = _with_temp_store(temp)
        try:
            result = store.import_account_credentials(
                "Same@Example.Test----old-pass\nsame@example.test----new-pass"
            )
            assert result["input_count"] == 1
            assert result["added"] == 1
            item = store.private_accounts()[0]
            assert item["password"] == "new-pass"
            assert store.read_account_inventory()["summary"]["total"] == 1

            store.update_account(
                item["id"],
                status="success",
                sso="secret-sso-value",
                cpa_ok=True,
                last_login_at="2026-07-31T00:00:00Z",
            )
            public = store.read_account_inventory()
            assert public["summary"]["sso_success"] == 1
            assert public["summary"]["cpa_success"] == 1
            assert "secret-sso-value" not in json.dumps(public)

            changed = store.import_account_credentials("same@example.test----replacement")
            assert changed["updated"] == 1
            item = store.private_accounts()[0]
            assert item["status"] == "pending"
            assert item["sso"] == ""
            assert item["cpa_ok"] is False
        finally:
            store.STATE_PATH, store.LOCK_PATH = previous


def test_import_has_no_account_count_limit():
    text = "\n".join(
        f"person{index}@example.test----password-{index}"
        for index in range(501)
    )
    records = store.parse_account_credentials(text)
    assert len(records) == 501


if __name__ == "__main__":
    test_import_formats_and_public_secret_redaction()
    test_deduplicate_update_and_status_changes()
    test_import_has_no_account_count_limit()
    print("OK account login store")
