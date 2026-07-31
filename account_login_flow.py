"""Browser password-login flow used by imported account jobs."""

from __future__ import annotations

import time


SIGNIN_URL = "https://accounts.x.ai/sign-in?redirect=grok-com"


class AccountLoginError(RuntimeError):
    pass


def _sleep(seconds: float, cancel_callback=None) -> None:
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline:
        if cancel_callback and cancel_callback():
            raise AccountLoginError("login cancelled")
        time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))


def _page_flags(page) -> dict:
    try:
        value = page.run_js(
            r"""
const body = ((document.body && document.body.innerText) || '').replace(/\s+/g, ' ').trim();
const lower = body.toLowerCase();
const cf = !!document.querySelector('iframe[src*="turnstile"], .cf-turnstile, [data-sitekey], input[name="cf-turnstile-response"]');
return {
  invalid: lower.includes('invalid credentials') || lower.includes('incorrect password')
    || lower.includes('wrong password') || lower.includes('invalid password')
    || lower.includes('account not found') || lower.includes('email or password is incorrect')
    || body.includes('密码错误') || body.includes('账号或密码错误') || body.includes('找不到账号'),
  rate: lower.includes('too many attempts') || lower.includes('try again later')
    || body.includes('尝试次数过多') || body.includes('稍后再试'),
  cf,
  url: String(location.href || '')
};
            """
        )
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def login_and_extract_sso(
    email: str,
    password: str,
    *,
    log_callback=None,
    cancel_callback=None,
    timeout: int = 120,
) -> str:
    """Sign in with email/password and return the resulting SSO cookie."""
    import browser_session as browser
    import register_flow as flow

    page = browser.active_page()
    if page is None:
        raise AccountLoginError("browser session is not active")
    deadline = time.monotonic() + max(30, int(timeout or 120))
    if log_callback:
        log_callback("[*] Opening xAI sign-in page")
    page.get(SIGNIN_URL)
    try:
        page.wait.doc_loaded()
    except Exception:
        pass
    try:
        flow._dismiss_cookie_consent(log_callback=log_callback)
    except Exception:
        pass

    email_submitted = False
    password_submitted = False
    last_action = 0.0
    last_cf_attempt = 0.0

    while time.monotonic() < deadline:
        if cancel_callback and cancel_callback():
            raise AccountLoginError("login cancelled")
        browser.refresh_active_page()
        page = browser.active_page()
        if page is None:
            _sleep(0.4, cancel_callback)
            continue

        flags = _page_flags(page)
        if flags.get("invalid"):
            raise AccountLoginError("xAI rejected the account credentials")
        if flags.get("rate"):
            raise AccountLoginError("xAI rate limited the login attempt")

        now = time.monotonic()
        if flags.get("cf") and now - last_cf_attempt >= 8:
            last_cf_attempt = now
            if log_callback:
                log_callback("[*] Waiting for the login verification challenge")
            try:
                flow._try_sync_turnstile(
                    log_callback=log_callback,
                    cancel_callback=cancel_callback,
                    reason="password login challenge",
                )
            except Exception:
                pass

        password_fields = flow._native_input_candidates("password")
        email_fields = flow._native_input_candidates("email")

        if password_fields and not password_submitted and now - last_action >= 0.8:
            if not flow._native_type_element(password_fields[0], password):
                raise AccountLoginError("could not fill the xAI password field")
            clicked = flow._native_click_action(
                ("sign in", "signin", "log in", "login", "continue", "next", "登录", "继续"),
                ("google", "apple", "x.com", "twitter", "back", "返回", "forgot"),
            )
            if not clicked:
                try:
                    page.run_js(
                        "const f=document.querySelector('input[type=password]')?.form; if(!f)return false; f.requestSubmit(); return true;"
                    )
                except Exception:
                    pass
            password_submitted = True
            last_action = now
            if log_callback:
                log_callback("[*] Password submitted; waiting for SSO")
            remaining = max(8, int(deadline - time.monotonic()))
            try:
                sso = flow.wait_for_sso_cookie(
                    timeout=remaining,
                    log_callback=log_callback,
                    cancel_callback=cancel_callback,
                )
            except Exception as exc:
                final_flags = _page_flags(browser.active_page()) if browser.active_page() else {}
                if final_flags.get("invalid"):
                    raise AccountLoginError("xAI rejected the account credentials") from exc
                raise AccountLoginError("login completed without an SSO cookie") from exc
            if not str(sso or "").strip():
                raise AccountLoginError("login completed without an SSO cookie")
            return str(sso).strip()

        if email_fields and not email_submitted and now - last_action >= 0.8:
            if not flow._native_type_element(email_fields[0], email):
                raise AccountLoginError("could not fill the xAI email field")
            clicked = flow._native_click_action(
                ("continue", "next", "sign in", "signin", "email", "继续", "下一步", "登录"),
                ("google", "apple", "x.com", "twitter", "back", "返回"),
            )
            if not clicked:
                try:
                    page.run_js(
                        "const f=document.querySelector('input[type=email]')?.form; if(!f)return false; f.requestSubmit(); return true;"
                    )
                except Exception:
                    pass
            email_submitted = True
            last_action = now
            if log_callback:
                log_callback("[*] Email submitted; waiting for password page")
            _sleep(0.8, cancel_callback)
            continue

        if not email_fields and not password_fields and now - last_action >= 2:
            clicked = flow._native_click_action(
                ("sign in with email", "continue with email", "use email", "email", "邮箱登录", "使用邮箱"),
                ("google", "apple", "x.com", "twitter"),
            )
            if clicked:
                last_action = now
                if log_callback:
                    log_callback("[*] Selected email sign-in")

        _sleep(0.4, cancel_callback)

    raise AccountLoginError("timed out waiting for the xAI login form")
