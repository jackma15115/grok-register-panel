"""Web operation layer for imported-account browser login jobs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

try:
    from secure_files import atomic_write_json, ensure_private_dir
    from webui.account_login_store import (
        delete_accounts,
        import_account_credentials,
        mark_accounts_queued,
        private_accounts,
        read_account_inventory,
        reset_incomplete_accounts,
    )
    from webui.process_utils import find_managed_processes, terminate_managed_processes, write_pid_file
except ImportError:  # running from webui/
    ROOT = Path(__file__).resolve().parent.parent
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from secure_files import atomic_write_json, ensure_private_dir
    from account_login_store import (  # type: ignore
        delete_accounts,
        import_account_credentials,
        mark_accounts_queued,
        private_accounts,
        read_account_inventory,
        reset_incomplete_accounts,
    )
    from process_utils import find_managed_processes, terminate_managed_processes, write_pid_file  # type: ignore


ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "log"
WORKER_SCRIPT = ROOT / "account_login_worker.py"
JOB_FILE = Path(os.environ.get("ACCOUNT_LOGIN_JOB_FILE", str(LOG_DIR / "account_login_job.json")))
REPORT_FILE = Path(os.environ.get("ACCOUNT_LOGIN_REPORT_FILE", str(LOG_DIR / "account_login_report.json")))
PID_FILE = Path(os.environ.get("ACCOUNT_LOGIN_PID_FILE", str(LOG_DIR / "account_login.pid")))
VENV_PY = ROOT / ".venv" / "bin" / "python"


def _workers() -> list[dict]:
    return find_managed_processes(ROOT, ("account_login_worker.py",))


def _read_report() -> dict:
    try:
        data = json.loads(REPORT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        "started_at": str(data.get("started_at") or "")[:40],
        "finished_at": str(data.get("finished_at") or "")[:40],
        "input_count": int(data.get("input_count") or 0),
        "extract_cpa": bool(data.get("extract_cpa")),
        "success_count": int(data.get("success_count") or 0),
        "sso_only_count": int(data.get("sso_only_count") or 0),
        "failure_count": int(data.get("failure_count") or 0),
        "cancelled_count": int(data.get("cancelled_count") or 0),
    }


def account_login_status() -> dict:
    workers = _workers()
    if not workers:
        reset_incomplete_accounts()
    inventory = read_account_inventory()
    return {
        **inventory,
        "running": bool(workers),
        "pid": workers[0]["pid"] if workers else None,
        "last_report": _read_report(),
    }


def import_accounts(text: object) -> dict:
    if _workers():
        return {"ok": False, "error": "account login task is running"}
    return import_account_credentials(text)


def _python_command() -> str:
    return str(VENV_PY if VENV_PY.is_file() else Path(sys.executable))


def start_account_login(
    ids: object = None,
    *,
    concurrency: object = 1,
    extract_cpa: object = False,
    pending_only: bool = False,
) -> dict:
    if find_managed_processes(ROOT, ("run_until_100.py", "run_batch_headless.py")):
        return {"ok": False, "error": "registration task is running"}
    if find_managed_processes(ROOT, ("sso_to_auth_json.py",)):
        return {"ok": False, "error": "account recovery is running"}
    existing = _workers()
    if existing:
        return {"ok": False, "error": "account login task already running", "pid": existing[0]["pid"]}
    reset_incomplete_accounts()
    if not WORKER_SCRIPT.is_file():
        return {"ok": False, "error": f"missing worker script: {WORKER_SCRIPT}"}

    try:
        workers = max(1, min(5, int(concurrency or 1)))
    except (TypeError, ValueError):
        return {"ok": False, "error": "concurrency must be an integer from 1 to 5"}
    want_cpa = bool(extract_cpa)
    requested = [str(value or "").strip() for value in (ids or []) if str(value or "").strip()]
    records = private_accounts(
        requested,
        pending_only=bool(pending_only or not requested),
        include_sso_only=want_cpa,
    )
    if requested:
        found_ids = {item["id"] for item in records}
        missing = [item_id for item_id in requested if item_id not in found_ids]
        if missing:
            return {"ok": False, "error": "one or more selected accounts no longer exist"}
    if not records:
        return {"ok": False, "error": "no imported accounts are ready for login"}

    ids_to_run = [item["id"] for item in records]
    ensure_private_dir(LOG_DIR)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    log_path = LOG_DIR / f"account-login-{timestamp}.log"
    job = {
        "version": 1,
        "ids": ids_to_run,
        "concurrency": workers,
        "extract_cpa": want_cpa,
        "report_file": str(REPORT_FILE),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    atomic_write_json(JOB_FILE, job)
    mark_accounts_queued(ids_to_run)

    fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.fchmod(fd, 0o600)
    except OSError:
        pass
    output = os.fdopen(fd, "w", encoding="utf-8")
    command = [_python_command(), "-u", str(WORKER_SCRIPT), "--job", str(JOB_FILE)]
    if os.name != "nt" and shutil.which("xvfb-run"):
        command = ["xvfb-run", "-a", "-s", "-screen 0 1920x1080x24", *command]
    try:
        process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
    except Exception:
        reset_incomplete_accounts()
        raise
    finally:
        output.close()
    write_pid_file(PID_FILE, process.pid)
    return {
        "ok": True,
        "running": True,
        "pid": process.pid,
        "input_count": len(ids_to_run),
        "concurrency": workers,
        "extract_cpa": want_cpa,
        "log": log_path.name,
    }


def stop_account_login() -> dict:
    killed = terminate_managed_processes(ROOT, ("account_login_worker.py",))
    reset_incomplete_accounts()
    return {"ok": True, "killed": killed, "status": account_login_status()}


def delete_imported_accounts(ids: object) -> dict:
    if _workers():
        return {"ok": False, "error": "stop the account login task before deleting accounts"}
    return delete_accounts(ids)
