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


def test_worker_watcher_persists_linux_launcher_failure():
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        log_path = base / "account-login-test.log"
        log_path.write_text(
            "[account-login] start accounts=1 workers=1 extract_cpa=False\n"
            "xvfb-run: error: Xvfb failed to start\n",
            encoding="utf-8",
        )
        previous_report = ops.REPORT_FILE
        ops.REPORT_FILE = base / "account_login_report.json"
        process = SimpleNamespace(pid=8765, wait=lambda: 1)
        job = {
            "created_at": "2026-07-31T00:00:00Z",
            "extract_cpa": False,
        }
        try:
            with patch.object(ops, "reset_incomplete_accounts", return_value=1) as reset:
                ops._watch_worker(process, ["d" * 20], job, log_path)
            reason = reset.call_args.args[0]
            assert "code 1" in reason
            assert "Xvfb failed to start" in reason
            assert reset.call_args.args[1] == ["d" * 20]
            report = json.loads(ops.REPORT_FILE.read_text(encoding="utf-8"))
            assert report["fatal_error"] == reason
            assert report["log"] == log_path.name
            assert "supervisor" in log_path.read_text(encoding="utf-8")
        finally:
            ops.REPORT_FILE = previous_report


def test_status_does_not_overwrite_error_while_watcher_is_finishing():
    with ops._WATCH_LOCK:
        ops._ACTIVE_WATCHERS.add(9876)
    try:
        with patch.object(ops, "_workers", return_value=[]), patch.object(
            ops, "reset_incomplete_accounts"
        ) as reset, patch.object(
            ops,
            "read_account_inventory",
            return_value={"ok": True, "items": [], "summary": {}},
        ), patch.object(ops, "_read_report", return_value={}):
            status = ops.account_login_status()
        assert status["running"] is True
        assert status["pid"] == 9876
        reset.assert_not_called()
    finally:
        with ops._WATCH_LOCK:
            ops._ACTIVE_WATCHERS.discard(9876)


def test_worker_exit_label_identifies_linux_oom_signal():
    label = ops._worker_exit_label(137)
    assert "SIGKILL" in label
    assert "OOM" in label


def test_latest_log_tail_is_bounded_and_redacted():
    with tempfile.TemporaryDirectory() as temp:
        previous_log_dir = ops.LOG_DIR
        ops.LOG_DIR = Path(temp)
        password = "private-password-99"
        sso = "private-sso-token-99"
        try:
            lines = [f"ordinary line {index}" for index in range(220)]
            lines.append(
                f"account=person@example.test password={password} sso={sso}"
            )
            (ops.LOG_DIR / "account-login-test.log").write_text(
                "\n".join(lines) + "\n",
                encoding="utf-8",
            )
            result = ops._read_latest_log_tail()
        finally:
            ops.LOG_DIR = previous_log_dir

    text = "\n".join(result["lines"])
    assert result["name"] == "account-login-test.log"
    assert result["truncated"] is True
    assert len(result["lines"]) <= ops._LOG_TAIL_LINES
    assert "pe***@example.test" in text
    assert password not in text
    assert sso not in text


if __name__ == "__main__":
    test_start_rejects_registration_or_recovery_conflicts()
    test_start_writes_id_only_job_and_launches_worker()
    test_worker_watcher_persists_linux_launcher_failure()
    test_status_does_not_overwrite_error_while_watcher_is_finishing()
    test_worker_exit_label_identifies_linux_oom_signal()
    test_latest_log_tail_is_bounded_and_redacted()
    print("OK account login ops")
