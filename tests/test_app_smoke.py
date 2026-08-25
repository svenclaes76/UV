"""Smoke tests: the full app script renders without exceptions.

Runs app.py through Streamlit's AppTest harness in both auth states.
Catches whole-file breakage (syntax, imports, scoping, st.* API misuse)
that unit tests on the calculation modules never touch.
"""
import os
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
os.chdir(PROJECT)  # app resolves .env / data paths relative to the project root

from streamlit.testing.v1 import AppTest

from uvalu import authgate

APP = str(PROJECT / "app.py")
TIMEOUT = 120


def _exceptions(at: AppTest) -> list[str]:
    return [str(e.value) for e in at.exception]


def _fake_authenticated_session(monkeypatch) -> None:
    # auth_wall() re-verifies the token AND re-checks live user status on
    # every rerun (see auth-page fixes memory) -- a bare fake session_state
    # token no longer bypasses that, so stub both checks directly instead of
    # needing a real registered user + real JWT just to smoke-test that the
    # nav + default page render.
    monkeypatch.setattr(authgate, "verify_token",
                        lambda tok: ("smoke-test@example.invalid", "Admin"))
    monkeypatch.setattr(authgate, "get_user_status", lambda email: ("Admin", "Active"))


def test_login_wall_renders_without_exceptions():
    at = AppTest.from_file(APP, default_timeout=TIMEOUT)
    at.run()
    assert not at.exception, _exceptions(at)


def test_authenticated_app_renders_without_exceptions(monkeypatch):
    _fake_authenticated_session(monkeypatch)
    at = AppTest.from_file(APP, default_timeout=TIMEOUT)
    at.session_state["jwt_token"] = "smoke-test-token"
    at.session_state["user_email"] = "smoke-test@example.invalid"
    at.session_state["user_role"] = "Admin"
    at.run()
    assert not at.exception, _exceptions(at)


def test_legacy_page_query_param_redirects_without_exceptions(monkeypatch):
    # Pre-st.navigation deep links (?page=<name>) get redirected to the new
    # url-path-based page — see app.py's "Legacy ?page= deep links" block.
    # A short default_timeout here: st.switch_page() called at a script's
    # bare top level (outside a click handler) has hung AppTest before in
    # other tests in this suite (see uvalu-test-isolation-patterns memory);
    # fail fast rather than eat the usual 120s if that recurs here too.
    _fake_authenticated_session(monkeypatch)
    at = AppTest.from_file(APP, default_timeout=20)
    at.session_state["jwt_token"] = "smoke-test-token"
    at.session_state["user_email"] = "smoke-test@example.invalid"
    at.session_state["user_role"] = "Admin"
    at.query_params["page"] = "dashboard"
    at.run()
    assert not at.exception, _exceptions(at)
    assert "page" not in at.query_params
