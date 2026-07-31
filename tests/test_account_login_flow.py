# -*- coding: utf-8 -*-
from __future__ import annotations

import itertools
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import account_login_flow


class FakePage:
    def __init__(self, state):
        self.state = state
        self.wait = SimpleNamespace(doc_loaded=lambda: None)

    def get(self, url):
        self.state["url"] = url

    def run_js(self, _script):
        return {"invalid": False, "rate": False, "cf": False, "url": self.state.get("url", "")}


def test_password_login_returns_sso_without_logging_secrets():
    state = {"phase": "email", "typed": [], "logs": []}
    page = FakePage(state)
    email_element = object()
    password_element = object()

    def candidates(kind):
        if kind == "email" and state["phase"] == "email":
            return [email_element]
        if kind == "password" and state["phase"] == "password":
            return [password_element]
        return []

    def type_element(element, value):
        state["typed"].append((element, value))
        return True

    def click_action(*_args, **_kwargs):
        if state["phase"] == "email":
            state["phase"] = "password"
        return "continue"

    fake_browser = SimpleNamespace(active_page=lambda: page, refresh_active_page=lambda: page)
    fake_flow = SimpleNamespace(
        _dismiss_cookie_consent=lambda **_kwargs: None,
        _native_input_candidates=candidates,
        _native_type_element=type_element,
        _native_click_action=click_action,
        _try_sync_turnstile=lambda **_kwargs: None,
        wait_for_sso_cookie=lambda **_kwargs: "private-sso-token",
    )
    ticks = itertools.count(0, 1)
    with patch.dict(sys.modules, {"browser_session": fake_browser, "register_flow": fake_flow}), patch.object(
        account_login_flow.time, "monotonic", side_effect=lambda: next(ticks)
    ), patch.object(account_login_flow, "_sleep", return_value=None):
        sso = account_login_flow.login_and_extract_sso(
            "person@example.test",
            "private-password",
            log_callback=state["logs"].append,
        )

    assert sso == "private-sso-token"
    assert (email_element, "person@example.test") in state["typed"]
    assert (password_element, "private-password") in state["typed"]
    log_text = "\n".join(state["logs"])
    assert "private-password" not in log_text
    assert "private-sso-token" not in log_text


if __name__ == "__main__":
    test_password_login_returns_sso_without_logging_secrets()
    print("OK account login flow")
