# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import account_login_worker as worker


def test_worker_writes_canonical_account_file_and_cpa():
    with tempfile.TemporaryDirectory() as temp:
        account_path = Path(temp) / "person@example.test.txt"
        updates = []
        runtime = SimpleNamespace(
            pick_proxy_for_worker=lambda *_args: "",
            set_thread_proxy=lambda _value: None,
            record_proxy_boot_failure=lambda *_args: None,
            account_file_for_email=lambda _email: str(account_path),
            add_sso_to_cpa=lambda _sso, **_kwargs: True,
        )
        fake_flow = SimpleNamespace(login_and_extract_sso=lambda *_args, **_kwargs: "private-sso-token")
        fake_browser = SimpleNamespace(
            start_browser=lambda **_kwargs: (object(), object()),
            stop_browser=lambda **_kwargs: None,
        )
        record = {
            "id": "a" * 20,
            "email": "person@example.test",
            "password": "private-password",
            "sso": "",
        }
        worker.STOP_EVENT.clear()
        with patch.dict(sys.modules, {"account_login_flow": fake_flow, "browser_session": fake_browser}), patch.object(
            worker, "update_account", side_effect=lambda account_id, **values: updates.append((account_id, values))
        ):
            result = worker.process_one_account(record, runtime, worker_index=1, extract_cpa=True)

        assert result["status"] == "success"
        assert account_path.read_text(encoding="utf-8") == (
            "person@example.test----private-password----private-sso-token\n"
        )
        assert any(values.get("status") == "success" and values.get("cpa_ok") is True for _, values in updates)


if __name__ == "__main__":
    test_worker_writes_canonical_account_file_and_cpa()
    print("OK account login worker")
