# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webui import account_login_store as store
from webui import account_sso_check_ops as ops


def test_inventory_merges_registered_accounts_and_redacts_secrets():
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        previous = (
            store.STATE_PATH,
            store.LOCK_PATH,
            store.ACCOUNT_FILES_DIR,
            store.CONFIG_FILE,
        )
        store.STATE_PATH = base / "imported_credentials.json"
        store.LOCK_PATH = base / "imported_credentials.json.lock"
        store.ACCOUNT_FILES_DIR = base / "accounts"
        store.CONFIG_FILE = base / "config.json"
        (base / "accounts").mkdir()
        (base / "accounts" / "registered@example.test.txt").write_text(
            "registered@example.test----registered-pass----" + "r" * 80 + "\n",
            encoding="utf-8",
        )
        (base / "accounts" / "accounts_20260101.txt").write_text(
            "batch@example.test----batch-pass----" + "b" * 80 + "\n",
            encoding="utf-8",
        )
        try:
            store.import_account_credentials("registered@example.test----imported-pass")
            data = store.read_account_inventory()
            assert [item["email"] for item in data["items"]] == ["registered@example.test"]
            item = data["items"][0]
            assert item["source"] == "both"
            assert item["has_password"] is True
            assert item["has_sso"] is True
            encoded = json.dumps(data)
            assert "registered-pass" not in encoded
            assert "r" * 80 not in encoded
        finally:
            (
                store.STATE_PATH,
                store.LOCK_PATH,
                store.ACCOUNT_FILES_DIR,
                store.CONFIG_FILE,
            ) = previous


def test_delete_resources_removes_local_chain_and_side_queue():
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        previous = (
            store.STATE_PATH,
            store.LOCK_PATH,
            store.ACCOUNT_FILES_DIR,
            store.CONFIG_FILE,
        )
        store.STATE_PATH = base / "accounts" / "imported_credentials.json"
        store.LOCK_PATH = base / "accounts" / "imported_credentials.json.lock"
        store.ACCOUNT_FILES_DIR = base / "accounts"
        store.CONFIG_FILE = base / "config.json"
        cpa = base / "cpa"
        g2a = base / "g2a"
        cpa.mkdir()
        g2a.mkdir()
        store.CONFIG_FILE.write_text(
            json.dumps({"cpa_auth_dir": str(cpa), "grok2api_auth_dir": str(g2a)}),
            encoding="utf-8",
        )
        try:
            account = "remove@example.test"
            sso = "s" * 80
            store.import_account_credentials(f"{account}----password----{sso}")
            (store.ACCOUNT_FILES_DIR / "sso_pending.txt").write_text(
                f"{account}----{sso}\nkeep@example.test----{'k' * 80}\n",
                encoding="utf-8",
            )
            (cpa / "xai-remove@example.test.json").write_text(
                json.dumps({"email": account}), encoding="utf-8"
            )
            (g2a / "g2a-remove@example.test.json").write_text(
                json.dumps({"email": account}), encoding="utf-8"
            )
            item = store.private_account_inventory()[0]
            result = store.delete_account_resources([item["id"]])
            assert result["ok"] is True
            assert result["deleted"] == 1
            assert not (store.ACCOUNT_FILES_DIR / "remove@example.test.txt").exists()
            assert not (cpa / "xai-remove@example.test.json").exists()
            assert not (g2a / "g2a-remove@example.test.json").exists()
            assert "remove@example.test" not in (store.ACCOUNT_FILES_DIR / "sso_pending.txt").read_text(encoding="utf-8")
            assert not store.private_accounts()
        finally:
            (
                store.STATE_PATH,
                store.LOCK_PATH,
                store.ACCOUNT_FILES_DIR,
                store.CONFIG_FILE,
            ) = previous


def test_delete_requires_completed_latest_invalid_check():
    with tempfile.TemporaryDirectory() as temp:
        previous = ops.REPORT_FILE
        ops.REPORT_FILE = Path(temp) / "report.json"
        ops.REPORT_FILE.write_text(json.dumps({"items": []}), encoding="utf-8")
        try:
            with patch.object(ops, "find_managed_processes", return_value=[]):
                try:
                    ops.delete_checked_invalid_accounts(["a" * 20])
                except ValueError as exc:
                    assert "did not complete" in str(exc)
                else:
                    raise AssertionError("expected incomplete report rejection")
        finally:
            ops.REPORT_FILE = previous


def test_delete_resources_rechecks_sso_before_removing_data():
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        previous = store.STATE_PATH, store.LOCK_PATH, store.ACCOUNT_FILES_DIR
        store.STATE_PATH = base / "accounts" / "imported_credentials.json"
        store.LOCK_PATH = base / "accounts" / "imported_credentials.json.lock"
        store.ACCOUNT_FILES_DIR = base / "accounts"
        try:
            store.import_account_credentials(f"change@example.test----password----{'a' * 80}")
            item = store.private_accounts()[0]
            try:
                store.delete_account_resources(
                    [item["id"]],
                    expected_sso_fingerprints={item["id"]: "not-the-current-sso"},
                )
            except store.AccountImportError as exc:
                assert "changed" in str(exc)
            else:
                raise AssertionError("expected stale SSO rejection")
            assert store.private_accounts()
        finally:
            store.STATE_PATH, store.LOCK_PATH, store.ACCOUNT_FILES_DIR = previous


if __name__ == "__main__":
    test_inventory_merges_registered_accounts_and_redacts_secrets()
    test_delete_resources_removes_local_chain_and_side_queue()
    test_delete_requires_completed_latest_invalid_check()
    test_delete_resources_rechecks_sso_before_removing_data()
    print("OK account sso check")
