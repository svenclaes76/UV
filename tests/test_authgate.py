"""AppTest coverage for uvalu/authgate.py — cookie session recovery, logout,
and the login wall / form.

`st.context.cookies` has no public AppTest hook, so the "cookie present"
branch is exercised by monkeypatching the `cookies` property directly on
streamlit's ContextProxy CLASS (confirmed it's a plain class-level
`property`, not per-instance state).
"""
import streamlit.runtime.context as st_context
import pytest
from streamlit.testing.v1 import AppTest

import auth


@pytest.fixture(autouse=True)
def isolated_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", "unit-test-key-123")
    monkeypatch.setattr(auth, "USERS_FILE", tmp_path / ".cache" / "users.json")


def _with_cookie(monkeypatch, cookies: dict):
    monkeypatch.setattr(st_context.ContextProxy, "cookies", property(lambda self: cookies))


# ── recover_session_from_cookie ──────────────────────────────────────────

class TestRecoverSessionFromCookie:
    def test_noop_when_session_already_has_token(self, monkeypatch):
        script = """
import streamlit as st
from uvalu import authgate
st.session_state["jwt_token"] = "existing-token"
authgate.recover_session_from_cookie()
st.text(st.session_state.get("user_email", "unset"))
"""
        at = AppTest.from_string(script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.text[0].value == "unset"

    def test_noop_when_no_cookie_present(self, monkeypatch):
        _with_cookie(monkeypatch, {})
        script = """
import streamlit as st
from uvalu import authgate
authgate.recover_session_from_cookie()
st.text(st.session_state.get("user_email", "unset"))
"""
        at = AppTest.from_string(script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.text[0].value == "unset"

    def test_restores_session_from_valid_cookie(self, monkeypatch):
        auth.register("first@example.com", "password123")
        _, token = auth.login("first@example.com", "password123")
        _with_cookie(monkeypatch, {"uv_jwt": token})

        script = """
import streamlit as st
from uvalu import authgate
authgate.recover_session_from_cookie()
st.text(st.session_state.get("user_email", "unset"))
st.text(st.session_state.get("user_role", "unset"))
"""
        at = AppTest.from_string(script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.text[0].value == "first@example.com"
        assert at.text[1].value == "Admin"

    def test_invalid_cookie_token_leaves_session_unset(self, monkeypatch):
        _with_cookie(monkeypatch, {"uv_jwt": "garbage-token"})
        script = """
import streamlit as st
from uvalu import authgate
authgate.recover_session_from_cookie()
st.text(st.session_state.get("user_email", "unset"))
"""
        at = AppTest.from_string(script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.text[0].value == "unset"


# ── handle_logout ─────────────────────────────────────────────────────────

class TestHandleLogout:
    def test_noop_without_logout_query_param(self, monkeypatch):
        script = """
import streamlit as st
from uvalu import authgate
st.session_state["jwt_token"] = "tok"
authgate.handle_logout()
st.text(st.session_state.get("jwt_token", "unset"))
"""
        at = AppTest.from_string(script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.text[0].value == "tok"

    def test_clears_session_and_stops_when_logout_param_present(self, monkeypatch):
        script = """
import streamlit as st
st.session_state["jwt_token"] = "tok"
st.session_state["user_email"] = "first@example.com"
st.session_state["user_role"] = "Admin"
from uvalu import authgate
authgate.handle_logout()
st.text("unreachable")
"""
        at = AppTest.from_string(script, default_timeout=60)
        at.query_params["logout"] = "1"
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert len(at.text) == 0  # st.stop() halted before the sentinel line
        assert "jwt_token" not in at.session_state
        assert "user_email" not in at.session_state
        assert at.query_params.get("logout") is None


# ── auth_wall ─────────────────────────────────────────────────────────────

def _run_auth_wall(session_state: dict | None = None) -> AppTest:
    script = """
import streamlit as st
from uvalu import authgate
authgate.auth_wall()
st.text("past the wall")
"""
    at = AppTest.from_string(script, default_timeout=60)
    for k, v in (session_state or {}).items():
        at.session_state[k] = v
    at.run()
    return at


class TestAuthWall:
    def test_fast_path_when_token_and_email_already_set(self):
        at = _run_auth_wall({"jwt_token": "tok", "user_email": "first@example.com"})
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.text[0].value == "past the wall"

    def test_valid_token_without_cached_email_resolves_and_passes(self):
        auth.register("first@example.com", "password123")
        _, token = auth.login("first@example.com", "password123")
        at = _run_auth_wall({"jwt_token": token})
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.text[0].value == "past the wall"
        assert at.session_state["user_email"] == "first@example.com"

    def test_no_session_shows_login_form_and_stops(self):
        at = _run_auth_wall()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert len(at.text) == 0
        assert len(at.text_input) == 2
        assert any(b.label == "Sign in" for b in at.button)

    def test_expired_or_invalid_token_falls_back_to_login_form(self):
        at = _run_auth_wall({"jwt_token": "garbage"})
        assert not at.exception, [str(e.value) for e in at.exception]
        assert len(at.text) == 0
        assert any(b.label == "Sign in" for b in at.button)

    def test_empty_submission_shows_validation_error(self):
        at = _run_auth_wall()
        submit = [b for b in at.button if b.label == "Sign in"][0]
        submit.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        html = "".join(m.value for m in at.markdown)
        assert "Enter your email and password" in html

    def test_wrong_credentials_shows_error(self):
        auth.register("first@example.com", "password123")
        at = _run_auth_wall()
        at.text_input[0].set_value("first@example.com")
        at.text_input[1].set_value("wrong-password")
        submit = [b for b in at.button if b.label == "Sign in"][0]
        submit.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        html = "".join(m.value for m in at.markdown)
        assert "Invalid email or password" in html

    def test_correct_credentials_logs_in(self):
        auth.register("first@example.com", "password123")
        at = _run_auth_wall()
        at.text_input[0].set_value("first@example.com")
        at.text_input[1].set_value("password123")
        submit = [b for b in at.button if b.label == "Sign in"][0]
        submit.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.session_state["user_email"] == "first@example.com"
        assert at.session_state["user_role"] == "Admin"
        assert "jwt_token" in at.session_state

    def test_sso_button_is_disabled(self):
        at = _run_auth_wall()
        sso = [b for b in at.button if b.label == "Continue with SSO"][0]
        assert sso.disabled
