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

APP = str(PROJECT / "app.py")
TIMEOUT = 120


def _exceptions(at: AppTest) -> list[str]:
    return [str(e.value) for e in at.exception]


def test_login_wall_renders_without_exceptions():
    at = AppTest.from_file(APP, default_timeout=TIMEOUT)
    at.run()
    assert not at.exception, _exceptions(at)


def test_authenticated_app_renders_without_exceptions():
    at = AppTest.from_file(APP, default_timeout=TIMEOUT)
    # Fake session hits the fast path in _auth_wall (token + email already set),
    # so the whole nav + default page render without a real login.
    at.session_state["jwt_token"] = "smoke-test-token"
    at.session_state["user_email"] = "smoke-test@example.invalid"
    at.session_state["user_role"] = "user"
    at.run()
    assert not at.exception, _exceptions(at)
