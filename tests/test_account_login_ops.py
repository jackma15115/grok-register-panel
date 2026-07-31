# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webui import account_login_ops as ops


def test_start_rejects_registration_or_recovery_conflicts():
    def registration_running(_root, scripts):
        return [{"pid": 10}] if "run_until_100.py" in scripts else []

    with patch.object(ops, "find_managed_processes", side_effect=registration_running):
        result = ops.start_account_login(["a" * 20])
    assert result["ok"] is False
    assert "registration" in result["error"]

    def recovery_running(_root, scripts):
        return [{"pid": 11}] if "sso_to_auth_json.py" in scripts else []

    with patch.object(ops, "find_managed_processes", side_effect=recovery_running):
        result = ops.start_account_login(["a" * 20])
    assert result["ok"] is False
    assert "recovery" in result["error"]


def test_start_writes_id_only_job_and_launches_worker():
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        worker_script = base / "account_login_worker.py"
        worker_script.write_text("# test worker\n", encoding="utf-8")
        previous = (
            ops.LOG_DIR,
            ops.WORKER_SCRIPT,
            ops.JOB_FILE,
            ops.REPORT_FILE,
            ops.PID_FILE,
            ops.VENV_PY,
        )
        ops.LOG_DIR = base / "log"
        ops.WORKER_SCRIPT = worker_script
        ops.JOB_FILE = ops.LOG_DIR / "account_login_job.json"
        ops.REPORT_FILE = ops.LOG_DIR / "account_login_report.json"
        ops.PID_FILE = ops.LOG_DIR / "account_login.pid"
        ops.VENV_PY = base / ".venv" / "bin" / "python"
        record = {
            "id": "b" * 20,
            "email": "person@example.test",
            "password": "private-password",
            "sso": "",
        }
        popen_calls = []
        try:
            with patch.object(ops, "find_managed_processes", return_value=[]), patch.object(
                ops, "reset_incomplete_accounts", return_value=0
            ), patch.object(ops, "private_accounts", return_value=[record]), patch.object(
                ops, "mark_accounts_queued", return_value=1
            ), patch.object(ops.shutil, "which", return_value=None), patch.object(
                ops.subprocess,
                "Popen",
                side_effect=lambda command, **kwargs: popen_calls.append((command, kwargs)) or SimpleNamespace(pid=4321),
            ):
                result = ops.start_account_login(
                    [record["id"]], concurrency=9, extract_cpa=True
                )
            assert result["ok"] is True
            assert result["concurrency"] == 5
            job_text = ops.JOB_FILE.read_text(encoding="utf-8")
            job = json.loads(job_text)
            assert job["ids"] == [record["id"]]
            assert job["extract_cpa"] is True
            assert "private-password" not in job_text
            assert "person@example.test" not in job_text
            assert popen_calls and str(worker_script) in popen_calls[0][0]
        finally:
            (
                ops.LOG_DIR,
                ops.WORKER_SCRIPT,
                ops.JOB_FILE,
                ops.REPORT_FILE,
                ops.PID_FILE,
                ops.VENV_PY,
            ) = previous


if __name__ == "__main__":
    test_start_rejects_registration_or_recovery_conflicts()
    test_start_writes_id_only_job_and_launches_worker()
    print("OK account login ops")
