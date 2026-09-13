"""AppTest coverage for uvalu/authgate.py — cookie session recovery, logout,
and the login wall / form.

`st.context.cookies` has no public AppTest hook, so the "cookie present"
branch is exercised by monkeypatching the `cookies` property directly on
streamlit's ContextProxy CLASS (confirmed it's a plain class-level
`property`, not per-instance state).
"""
import streamlit as st
import streamlit.runtime.context as st_context
import pytest
from streamlit.testing.v1 import AppTest

import auth
import settings
from uvalu import oauth


class FakeUser(dict):
    """Minimal stand-in for streamlit.user_info.UserInfoProxy — see
    tests/test_oauth.py's identical class for why this suffices."""
    def __init__(self, is_logged_in: bool, **claims):
        super().__init__(**claims)
        self.is_logged_in = is_logged_in


@pytest.fixture(autouse=True)
def isolated_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", "unit-test-key-123")
    monkeypatch.setattr(auth, "USERS_FILE", tmp_path / ".cache" / "users.json")
    monkeypatch.setattr(settings, "_SHARED_FILE", tmp_path / "data" / "settings" / "shared.json")
    # No real st.user session by default -- individual OAuth tests opt in via
    # monkeypatch.setattr(st, "user", FakeUser(...)).
    monkeypatch.setattr(st, "user", FakeUser(False))


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

def _run_auth_wall(session_state: dict | None = None, query_params: dict | None = None) -> AppTest:
    script = """
import streamlit as st
from uvalu import authgate
authgate.auth_wall()
st.text("past the wall")
"""
    at = AppTest.from_string(script, default_timeout=60)
    for k, v in (session_state or {}).items():
        at.session_state[k] = v
    for k, v in (query_params or {}).items():
        at.query_params[k] = v
    at.run()
    return at


class TestAuthWall:
    def test_valid_token_and_cached_email_still_passes_through(self):
        # No session_state-only fast-path bypass anymore (see the "similar
        # issues" sweep note below) -- but a genuinely valid, active
        # session's token is re-verified successfully on every rerun and
        # still passes straight through.
        auth.register("first@example.com", "password123")
        _, token = auth.login("first@example.com", "password123")
        at = _run_auth_wall({"jwt_token": token, "user_email": "first@example.com",
                             "user_role": "Admin"})
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.text[0].value == "past the wall"

    def test_suspended_account_is_kicked_back_to_login(self):
        # Real bug fixed: auth_wall() used to trust session_state's cached
        # jwt_token/user_email indefinitely once set, never re-checking the
        # live user store -- an Admin suspending this account had no effect
        # on an already-open tab until the JWT happened to expire (up to
        # 24h, and in practice session_state can outlive that). Now the
        # live status is re-checked on every rerun.
        auth.register("first@example.com", "password123")
        auth.register("second@example.com", "password12345", role="Viewer")
        _, token = auth.login("second@example.com", "password12345")
        auth.set_status("second@example.com", "Suspended")
        at = _run_auth_wall({"jwt_token": token, "user_email": "second@example.com",
                             "user_role": "Viewer"})
        assert not at.exception, [str(e.value) for e in at.exception]
        assert len(at.text) == 0
        assert "jwt_token" not in at.session_state
        assert "suspended" in "".join(m.value for m in at.markdown).lower()

    def test_deleted_account_is_kicked_back_to_login(self):
        auth.register("first@example.com", "password123")
        auth.register("second@example.com", "password12345", role="Viewer")
        _, token = auth.login("second@example.com", "password12345")
        auth.delete_user("second@example.com")
        at = _run_auth_wall({"jwt_token": token, "user_email": "second@example.com",
                             "user_role": "Viewer"})
        assert not at.exception, [str(e.value) for e in at.exception]
        assert len(at.text) == 0
        assert "jwt_token" not in at.session_state
        assert "no longer exists" in "".join(m.value for m in at.markdown).lower()

    def test_role_change_takes_effect_on_next_rerun(self):
        auth.register("first@example.com", "password123")
        auth.register("second@example.com", "password12345", role="Analyst")
        _, token = auth.login("second@example.com", "password12345")
        auth.set_role("second@example.com", "Admin")
        at = _run_auth_wall({"jwt_token": token, "user_email": "second@example.com",
                             "user_role": "Analyst"})  # stale cached role
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.text[0].value == "past the wall"
        assert at.session_state["user_role"] == "Admin"  # live role, not the stale cache

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

    def test_provider_buttons_are_disabled_when_unconfigured(self):
        # No secrets.toml [auth] section exists in the test environment, so
        # both providers render disabled (see tests/test_oauth.py for the
        # is_configured() logic itself).
        at = _run_auth_wall()
        google = [b for b in at.button if b.label == "Continue with Google"][0]
        microsoft = [b for b in at.button if b.label == "Continue with Microsoft Entra ID"][0]
        assert google.disabled
        assert microsoft.disabled


class TestAuthWallLockout:
    def test_locked_out_card_replaces_form_after_attempts_exhausted(self):
        settings.save_shared_settings({**settings.load_shared_settings(),
                                       "login_attempts_before_lock": 1, "lock_minutes": 10})
        auth.register("first@example.com", "password123")
        at = _run_auth_wall()
        at.text_input[0].set_value("first@example.com")
        at.text_input[1].set_value("wrong-password")
        submit = [b for b in at.button if b.label == "Sign in"][0]
        submit.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        html = "".join(m.value for m in at.markdown)
        assert "Sign in temporarily locked" in html
        assert len(at.text_input) == 0  # form is hidden, not just an inline error

    def test_reload_while_locked_shows_card_without_resubmitting(self):
        settings.save_shared_settings({**settings.load_shared_settings(),
                                       "login_attempts_before_lock": 1})
        auth.register("first@example.com", "password123")
        at = _run_auth_wall({"uv_login_attempted_email": "first@example.com"})
        auth.login("first@example.com", "wrong-password")  # trip the lock directly
        at2 = _run_auth_wall({"uv_login_attempted_email": "first@example.com"})
        assert not at2.exception, [str(e.value) for e in at2.exception]
        html = "".join(m.value for m in at2.markdown)
        assert "Sign in temporarily locked" in html
        assert len(at2.text_input) == 0

    def test_correct_password_still_blocked_while_locked(self):
        settings.save_shared_settings({**settings.load_shared_settings(),
                                       "login_attempts_before_lock": 1})
        auth.register("first@example.com", "password123")
        auth.login("first@example.com", "wrong-password")  # trip the lock
        at = _run_auth_wall({"uv_login_attempted_email": "first@example.com"})
        assert not at.exception, [str(e.value) for e in at.exception]
        assert len(at.text_input) == 0
        assert "jwt_token" not in at.session_state

    def test_switch_account_button_reveals_form_again(self):
        settings.save_shared_settings({**settings.load_shared_settings(),
                                       "login_attempts_before_lock": 1})
        auth.register("first@example.com", "password123")
        auth.login("first@example.com", "wrong-password")  # trip the lock
        at = _run_auth_wall({"uv_login_attempted_email": "first@example.com"})
        switch = [b for b in at.button if b.label == "Not you? Use a different account"][0]
        switch.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert len(at.text_input) == 2  # form is back, even though the account is still locked
        assert "uv_login_attempted_email" not in at.session_state


# ── logging (logkit Phase 1) ─────────────────────────────────────────────

import logging as _logging  # noqa: E402

from uvalu import logkit  # noqa: E402


def _events(caplog, slug):
    return [r for r in caplog.records if getattr(r, "event", None) == slug]


class TestAuthgateLogging:
    def test_cookie_recovery_logs_session_restored(self, monkeypatch, caplog):
        caplog.set_level(_logging.DEBUG, logger="uvalu")
        auth.register("first@example.com", "password123")
        _, token = auth.login("first@example.com", "password123")
        _with_cookie(monkeypatch, {"uv_jwt": token})
        script = """
import streamlit as st
from uvalu import authgate
authgate.recover_session_from_cookie()
"""
        AppTest.from_string(script, default_timeout=60).run()
        (rec,) = _events(caplog, "auth.session.restored")
        assert rec.user_id == logkit.user_hash("first@example.com")

    def test_logout_logs_auth_logout(self, caplog):
        caplog.set_level(_logging.DEBUG, logger="uvalu")
        script = """
import streamlit as st
st.session_state["jwt_token"] = "tok"
st.session_state["user_email"] = "first@example.com"
from uvalu import authgate
authgate.handle_logout()
"""
        at = AppTest.from_string(script, default_timeout=60)
        at.query_params["logout"] = "1"
        at.run()
        (rec,) = _events(caplog, "auth.logout")
        assert rec.user_id == logkit.user_hash("first@example.com")

    @pytest.mark.parametrize("scenario,reason", [
        ("suspended", "suspended"),
        ("deleted", "account_deleted"),
        ("garbage", "invalid_token"),
    ])
    def test_auth_wall_logs_session_revoked(self, caplog, scenario, reason):
        caplog.set_level(_logging.DEBUG, logger="uvalu")
        if scenario == "garbage":
            state = {"jwt_token": "garbage"}
        else:
            auth.register("first@example.com", "password123")
            auth.register("second@example.com", "password12345", role="Viewer")
            _, token = auth.login("second@example.com", "password12345")
            if scenario == "suspended":
                auth.set_status("second@example.com", "Suspended")
            else:
                auth.delete_user("second@example.com")
            state = {"jwt_token": token, "user_email": "second@example.com",
                     "user_role": "Viewer"}
        _run_auth_wall(state)
        revoked = _events(caplog, "auth.session.revoked")
        assert any(r.reason == reason for r in revoked)


# ── Invite acceptance screen ─────────────────────────────────────────────

class TestInviteAcceptanceScreen:
    def test_invalid_token_shows_invalid_link_message(self):
        at = _run_auth_wall(query_params={"invite": "garbage-token"})
        assert not at.exception, [str(e.value) for e in at.exception]
        html = "".join(m.value for m in at.markdown)
        assert "Invite link invalid" in html
        assert len(at.text_input) == 0

    def test_valid_invite_shows_create_account_form(self):
        _, _, token = auth.invite_user("new@example.com", role="Viewer", invited_by="admin@example.com")
        at = _run_auth_wall(query_params={"invite": token})
        assert not at.exception, [str(e.value) for e in at.exception]
        html = "".join(m.value for m in at.markdown)
        assert "Create your account" in html
        assert "new@example.com" in html
        assert "Viewer" in html
        assert len(at.text_input) == 1  # just Password -- email is fixed, shown as text

    def test_accepting_with_a_valid_password_signs_in(self):
        _, _, token = auth.invite_user("new@example.com", role="Analyst")
        at = _run_auth_wall(query_params={"invite": token})
        at.text_input[0].set_value("a-real-password")
        submit = [b for b in at.button if b.label == "Create account"][0]
        submit.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.session_state["user_email"] == "new@example.com"
        assert at.session_state["user_role"] == "Analyst"
        assert "jwt_token" in at.session_state

    def test_accepting_with_a_short_password_shows_error(self):
        _, _, token = auth.invite_user("new@example.com")
        at = _run_auth_wall(query_params={"invite": token})
        at.text_input[0].set_value("short")
        submit = [b for b in at.button if b.label == "Create account"][0]
        submit.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert "8 characters" in "".join(m.value for m in at.markdown)
        assert "jwt_token" not in at.session_state

    def test_provider_buttons_present_on_acceptance_screen(self):
        _, _, token = auth.invite_user("new@example.com")
        at = _run_auth_wall(query_params={"invite": token})
        assert any(b.label == "Continue with Google" for b in at.button)


class TestForgotPasswordScreen:
    def test_shows_ask_an_admin_message(self):
        at = _run_auth_wall(query_params={"forgot": "1"})
        assert not at.exception, [str(e.value) for e in at.exception]
        html = "".join(m.value for m in at.markdown)
        assert "Forgot your password" in html
        assert "ask an admin" in html.lower()

    def test_back_to_sign_in_clears_query_param(self):
        at = _run_auth_wall(query_params={"forgot": "1"})
        back = [b for b in at.button if b.label == "Back to sign in"][0]
        back.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.query_params.get("forgot") is None


class TestPasswordResetScreen:
    def test_invalid_token_shows_invalid_link_message(self):
        at = _run_auth_wall(query_params={"reset": "garbage-token"})
        assert not at.exception, [str(e.value) for e in at.exception]
        html = "".join(m.value for m in at.markdown)
        assert "Reset link invalid" in html
        assert len(at.text_input) == 0

    def test_valid_reset_token_shows_reset_form(self):
        auth.register("first@example.com", "password123")
        _, _, token = auth.admin_request_password_reset("first@example.com")
        at = _run_auth_wall(query_params={"reset": token})
        assert not at.exception, [str(e.value) for e in at.exception]
        html = "".join(m.value for m in at.markdown)
        assert "Choose a new password" in html
        assert "first@example.com" in html
        assert len(at.text_input) == 2  # New password + Confirm

    def test_resetting_with_matching_password_signs_in(self):
        auth.register("first@example.com", "password123")
        _, _, token = auth.admin_request_password_reset("first@example.com")
        at = _run_auth_wall(query_params={"reset": token})
        at.text_input[0].set_value("brand-new-password")
        at.text_input[1].set_value("brand-new-password")
        submit = [b for b in at.button if b.label == "Reset password"][0]
        submit.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.session_state["user_email"] == "first@example.com"
        assert "jwt_token" in at.session_state

    def test_mismatched_confirmation_shows_error(self):
        auth.register("first@example.com", "password123")
        _, _, token = auth.admin_request_password_reset("first@example.com")
        at = _run_auth_wall(query_params={"reset": token})
        at.text_input[0].set_value("brand-new-password")
        at.text_input[1].set_value("something-else")
        submit = [b for b in at.button if b.label == "Reset password"][0]
        submit.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert "don't match" in "".join(m.value for m in at.markdown)
        assert "jwt_token" not in at.session_state

    def test_short_password_shows_error(self):
        auth.register("first@example.com", "password123")
        _, _, token = auth.admin_request_password_reset("first@example.com")
        at = _run_auth_wall(query_params={"reset": token})
        at.text_input[0].set_value("short")
        at.text_input[1].set_value("short")
        submit = [b for b in at.button if b.label == "Reset password"][0]
        submit.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert "characters" in "".join(m.value for m in at.markdown)
        assert "jwt_token" not in at.session_state


# ── OAuth resolution ─────────────────────────────────────────────────────

class TestOAuthResolution:
    def test_existing_linked_identity_signs_in(self, monkeypatch):
        auth.register("admin@example.com", "password123")
        _, _, token = auth.invite_user("new@example.com", role="Analyst")
        auth.accept_invite_with_oauth(token, "https://accounts.google.com", "sub-123", "new@example.com")
        monkeypatch.setattr(st, "user", FakeUser(
            True, iss="https://accounts.google.com", sub="sub-123", email="new@example.com"))
        at = _run_auth_wall()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.session_state["user_email"] == "new@example.com"
        assert at.session_state["user_role"] == "Analyst"
        assert "jwt_token" in at.session_state

    def test_unknown_identity_with_no_pending_invite_shows_refusal(self, monkeypatch):
        monkeypatch.setattr(st, "user", FakeUser(
            True, iss="https://accounts.google.com", sub="sub-999", email="stranger@example.com"))
        at = _run_auth_wall()
        assert not at.exception, [str(e.value) for e in at.exception]
        html = "".join(m.value for m in at.markdown)
        assert "No Uvalu account for this Google identity" in html
        assert "stranger@example.com" in html
        assert "jwt_token" not in at.session_state

    def test_pending_invite_by_email_completes_via_oauth(self, monkeypatch):
        auth.invite_user("new@example.com", role="Viewer")
        monkeypatch.setattr(st, "user", FakeUser(
            True, iss="https://accounts.google.com", sub="sub-123", email="new@example.com"))
        at = _run_auth_wall()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.session_state["user_email"] == "new@example.com"
        assert at.session_state["user_role"] == "Viewer"
        users = auth._load_users()
        assert users["new@example.com"]["status"] == "Active"
        assert users["new@example.com"]["linked_identities"][0]["subject"] == "sub-123"

    def test_suspended_linked_account_shows_refusal(self, monkeypatch):
        _, _, token = auth.invite_user("new@example.com")
        auth.accept_invite_with_oauth(token, "https://accounts.google.com", "sub-123", "new@example.com")
        auth.set_status("new@example.com", "Suspended")
        monkeypatch.setattr(st, "user", FakeUser(
            True, iss="https://accounts.google.com", sub="sub-123", email="new@example.com"))
        at = _run_auth_wall()
        assert not at.exception, [str(e.value) for e in at.exception]
        html = "".join(m.value for m in at.markdown)
        assert "suspended" in html.lower()
        assert "jwt_token" not in at.session_state

    def test_already_handled_flag_prevents_reprocessing(self, monkeypatch):
        # Simulates a later rerun in the same browser OIDC session -- the
        # identity is still there (st.user persists) but oauth_login()
        # shouldn't fire a second time and mint a redundant session.
        monkeypatch.setattr(st, "user", FakeUser(
            True, iss="https://accounts.google.com", sub="sub-999", email="stranger@example.com"))
        at = _run_auth_wall({"uv_oauth_handled": True})
        assert not at.exception, [str(e.value) for e in at.exception]
        assert "uv_oauth_refused" not in at.session_state
        # Falls through to the plain sign-in form since nothing else applies.
        assert len(at.text_input) == 2


class TestOAuthRefusalScreen:
    def test_back_to_sign_in_clears_refusal_and_shows_form_again(self, monkeypatch):
        signed_out = {"called": False}
        monkeypatch.setattr(oauth, "sign_out", lambda: signed_out.__setitem__("called", True))
        at = _run_auth_wall({"uv_oauth_refused": {"email": "stranger@example.com", "label": "Google",
                                                  "reason": "not_invited"},
                            "uv_oauth_handled": True})
        back_btn = [b for b in at.button if b.label == "Back to sign in"][0]
        back_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert signed_out["called"]
        assert "uv_oauth_refused" not in at.session_state
        assert "uv_oauth_handled" not in at.session_state
        assert len(at.text_input) == 2
