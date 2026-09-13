"""AppTest coverage for uvalu/pages_/settings.py."""
import io

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import auth
import portfolio
import settings
from uvalu import oauth
from uvalu.pages_ import settings as settings_page
from tests.conftest import TEST_EMAIL, fake_cached_fn, USER_SETUP_SRC


class FakeUser(dict):
    """Minimal stand-in for streamlit.user_info.UserInfoProxy — see
    tests/test_oauth.py's identical class for why this suffices."""
    def __init__(self, is_logged_in: bool, **claims):
        super().__init__(**claims)
        self.is_logged_in = is_logged_in


def _run(monkeypatch, role="Analyst", jwt_sid=None) -> AppTest:
    # AppTest.from_function re-executes a function's SOURCE TEXT as a fresh
    # script (no closure over enclosing variables — see tests/test_pages_admin.py's
    # identical note), so `role` can't be passed as a real Python value into a
    # from_function script; AppTest.from_string takes the already-interpolated
    # text directly instead.
    monkeypatch.setattr(settings_page, "_load_all_screener_data", fake_cached_fn(None))

    _sid_line = f'st.session_state["jwt_sid"] = {jwt_sid!r}\n' if jwt_sid else ""
    script_src = USER_SETUP_SRC + f"""
import streamlit as st
from uvalu.pages_ import settings as settings_page
st.session_state["user_email"] = "test@example.com"
st.session_state["user_role"] = {role!r}
{_sid_line}settings_page.render()
"""
    at = AppTest.from_string(script_src, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def test_renders_without_exceptions(isolated_data, monkeypatch):
    _run(monkeypatch)


def test_shows_default_veto_thresholds(isolated_data, monkeypatch):
    at = _run(monkeypatch)
    html = "".join(m.value for m in at.markdown)
    assert "500%" in html   # max debt/equity default
    assert "90%" in html    # max payout default
    assert "70" in html     # buy threshold default


def test_changing_max_debt_equity_slider_persists_and_reruns(isolated_data, monkeypatch):
    # Screening & veto rules are admin-only (see the non-admin tests below).
    at = _run(monkeypatch, role="Admin")
    slider = at.slider(key="scr_max_de")
    slider.set_value(300)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert settings.load_shared_settings()["max_debt_equity"] == 300.0


def test_changing_benchmark_toggle_persists(isolated_data, monkeypatch):
    at = _run(monkeypatch, role="Admin")
    toggle = at.toggle(key="scr_stoxx")
    toggle.set_value(True)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert settings.load_shared_settings()["benchmark_stoxx"] is True


@pytest.mark.parametrize("role", ["Analyst", "Viewer"])
def test_screening_sliders_disabled_for_non_admin(isolated_data, monkeypatch, role):
    # These are shared, all-user settings ("admin-controlled, apply to all
    # users" per settings.py's own docstring) — a non-admin must not be able
    # to change what every other user's BUY/AVOID decisions are based on.
    at = _run(monkeypatch, role=role)
    assert at.slider(key="scr_max_de").disabled is True
    assert at.slider(key="scr_max_payout").disabled is True
    assert at.slider(key="scr_min_mos").disabled is True
    assert at.slider(key="scr_buy_thr").disabled is True
    assert at.toggle(key="scr_stoxx").disabled is True
    assert "Admin-only" in "".join(m.value for m in at.markdown)


@pytest.mark.parametrize("role", ["Analyst", "Viewer"])
def test_non_admin_cannot_persist_veto_threshold_change(isolated_data, monkeypatch, role):
    # Server-side guard, independent of the widgets' own disabled= state --
    # even if a disabled slider's value were somehow driven, the save path
    # itself must not write shared settings for a non-admin.
    at = _run(monkeypatch, role=role)
    at.slider(key="scr_max_de").set_value(300)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert settings.load_shared_settings()["max_debt_equity"] == 500.0


def test_changing_screening_style_persists_and_reruns(isolated_data, monkeypatch):
    at = _run(monkeypatch, role="Admin")
    at.segmented_control(key="scr_style").set_value("Income")
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert settings.load_shared_settings()["screen_style"] == "income"


@pytest.mark.parametrize("role", ["Analyst", "Viewer"])
def test_screening_style_disabled_and_not_persisted_for_non_admin(isolated_data, monkeypatch, role):
    at = _run(monkeypatch, role=role)
    assert at.segmented_control(key="scr_style").disabled is True
    at.segmented_control(key="scr_style").set_value("Growth")
    at.run()
    assert settings.load_shared_settings().get("screen_style", "balanced") == "balanced"


def test_changing_refresh_interval_persists(isolated_data, monkeypatch):
    at = _run(monkeypatch)
    select_slider = at.select_slider(key="disp_refresh_interval")
    select_slider.set_value(300)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert settings.load_settings(TEST_EMAIL)["refresh_interval_s"] == 300


def test_export_shows_info_when_portfolio_empty(isolated_data, monkeypatch):
    at = _run(monkeypatch)
    assert "Your portfolio is empty" in "".join(i.value for i in at.info)
    assert len(at.download_button) == 0


def test_export_shows_download_button_when_portfolio_has_data(isolated_data, monkeypatch):
    portfolio.save_portfolio(pd.DataFrame([{"ticker": "AAA.BR", "shares": 10}]))
    at = _run(monkeypatch)
    assert len(at.download_button) == 1
    assert at.download_button[0].label == "Download backup.xlsx"


def _build_test_workbook() -> bytes:
    # Excel's "used range" (what read_excel sees back) is trimmed to the
    # last populated row/column — a sold-position row with a real date_out
    # value (col 17) is what keeps all 18 columns and 110 rows intact when
    # read back, matching tests/test_portfolio.py's TestParseExcel builder.
    n_cols = 18
    rows = [[None] * n_cols for _ in range(110)]
    rows[1][0] = "Test Corp"
    rows[1][1] = "EBR:TESTX"
    rows[1][2] = 10
    rows[1][6] = 1000.0
    rows[1][16] = "2024-01-01"
    rows[94][0] = "Sold Corp"
    rows[94][1] = "EBR:SOLDX"
    rows[94][2] = 5
    rows[94][6] = 500.0
    rows[94][7] = 600.0
    rows[94][16] = "2023-01-01"
    rows[94][17] = "2023-06-01"
    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, sheet_name="beleggingen", header=False, index=False)
    return buf.getvalue()


def test_import_valid_excel_saves_portfolio(isolated_data, monkeypatch):
    # settings.py's import branch calls st.rerun() unconditionally on success
    # without ever clearing the file_uploader's own state — since AppTest's
    # uploaded file persists across reruns exactly like a real session, that
    # st.rerun() re-enters the same "file present -> re-import -> rerun"
    # branch forever (confirmed: this hangs for the full 60s timeout without
    # this patch). Real bug in the app, out of scope here — st.rerun is
    # stubbed to a no-op so this test can still verify the save itself
    # happened before rerun() would have fired.
    import streamlit as st
    monkeypatch.setattr(st, "rerun", lambda *a, **k: None)

    at = _run(monkeypatch)
    uploader = at.file_uploader(key="imp_portfolio")
    uploader.upload(
        "portfolio.xlsx", _build_test_workbook(),
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert portfolio.load_portfolio().iloc[0]["ticker"] == "TESTX.BR"


def test_import_excel_with_no_valid_positions_shows_error(isolated_data, monkeypatch):
    at = _run(monkeypatch)
    # No row matches a valid EBR:/AMS:/etc. prefix, but a dummy value in the
    # last row/column keeps Excel's used-range at the full 110x18 shape
    # instead of collapsing to a near-empty sheet (see _build_test_workbook).
    rows = [[None] * 18 for _ in range(110)]
    rows[1][1] = "XYZ:NOTVALID"
    rows[109][17] = "placeholder"
    empty_wb = io.BytesIO()
    pd.DataFrame(rows).to_excel(empty_wb, sheet_name="beleggingen", header=False, index=False)

    uploader = at.file_uploader(key="imp_portfolio")
    uploader.upload(
        "portfolio.xlsx", empty_wb.getvalue(),
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "No open" in "".join(e.value for e in at.error)


def test_targets_section_renders(isolated_data, monkeypatch):
    at = _run(monkeypatch)
    html = "".join(m.value for m in at.markdown)
    assert "Target allocation" in html
    assert at.text_area(key="tgt_sectors").value == ""      # nothing saved yet
    assert at.number_input(key="tgt_hhi").value == 0.0


def test_save_target_allocation_persists(isolated_data, monkeypatch):
    import streamlit as st
    monkeypatch.setattr(st, "rerun", lambda *a, **k: None)   # save branch reruns

    at = _run(monkeypatch)
    at.text_area(key="tgt_sectors").set_value("Technology 25\nHealthcare 15")
    at.text_area(key="tgt_tickers").set_value("AAA.BR 10")
    at.number_input(key="tgt_hhi").set_value(0.15)
    at.run()
    at.button(key="tgt_save").click()
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]

    t = portfolio.load_targets()
    assert t["sectors"] == {"Technology": 0.25, "Healthcare": 0.15}
    assert t["tickers"] == {"AAA.BR": 0.10}
    assert t["hhi_max"] == 0.15


def test_existing_targets_prefill_the_editor(isolated_data, monkeypatch):
    portfolio.save_targets({"sectors": {"Technology": 0.30}, "hhi_max": 0.12})
    at = _run(monkeypatch)
    assert "Technology 30" in at.text_area(key="tgt_sectors").value
    assert at.number_input(key="tgt_hhi").value == 0.12


def test_parse_targets_text_drops_malformed_and_out_of_range():
    from uvalu.pages_.settings import _parse_targets_text
    parsed = _parse_targets_text("Technology 25\nBad\nHuge 250\nConsumer Cyclical 12%\n  \nZero 0")
    assert parsed == {"Technology": 0.25, "Consumer Cyclical": 0.12}


def test_account_footer_shows_email_and_role(isolated_data, monkeypatch):
    at = _run(monkeypatch)
    html = "".join(m.value for m in at.markdown)
    assert TEST_EMAIL in html
    assert "Analyst" in html
    assert "Sign out" in html


# ── logging (logkit Phase 2) ─────────────────────────────────────────────

import logging as _logging  # noqa: E402

from uvalu import logkit  # noqa: E402


def _config_changes(caplog, key=None):
    return [r for r in caplog.records
            if getattr(r, "event", None) == "config.change"
            and (key is None or getattr(r, "key", None) == key)]


class TestSettingsLogging:
    def test_shared_settings_change_logs_per_key_with_old_and_new(self, isolated_data, caplog):
        caplog.set_level(_logging.DEBUG, logger="uvalu")
        base = settings.load_shared_settings()
        settings.save_shared_settings({**base, "max_debt_equity": 400.0, "screen_style": "value"})
        changed = {r.key: (r.old, r.new, r.scope) for r in _config_changes(caplog)}
        assert changed["max_debt_equity"] == (500.0, 400.0, "shared")
        assert changed["screen_style"][1] == "value"
        assert "buy_threshold" not in changed          # unchanged keys don't log

    def test_user_settings_change_scope_is_user_hash(self, isolated_data, caplog):
        caplog.set_level(_logging.DEBUG, logger="uvalu")
        settings.save_settings({**settings.load_settings(TEST_EMAIL), "density": "compact"}, TEST_EMAIL)
        (rec,) = _config_changes(caplog, "density")
        assert rec.new == "compact"
        assert rec.scope == f"user:{logkit.user_hash(TEST_EMAIL)}"

    def test_no_op_save_logs_nothing(self, isolated_data, caplog):
        caplog.set_level(_logging.DEBUG, logger="uvalu")
        current = settings.load_shared_settings()
        settings.save_shared_settings(dict(current))
        assert _config_changes(caplog) == []

    def test_corrupt_shared_settings_file_logs_and_falls_back(self, isolated_data, caplog):
        caplog.set_level(_logging.DEBUG, logger="uvalu")
        settings._SHARED_FILE.parent.mkdir(parents=True, exist_ok=True)
        settings._SHARED_FILE.write_bytes(b"not a valid encrypted payload")
        got = settings.load_shared_settings()
        assert got["max_debt_equity"] == 500.0           # defaults, behaviour unchanged
        reads = [r for r in caplog.records if getattr(r, "event", None) == "storage.read_failed"]
        assert reads and reads[0].file == "shared.json" and reads[0].exc_info is not None


# ── Security card ─────────────────────────────────────────────────────────

class TestSecurityCard:
    def test_shows_password_last_changed(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        at = _run(monkeypatch)
        html = "".join(m.value for m in at.markdown)
        assert "Last changed" in html

    def test_no_account_shows_set_a_password(self, isolated_data, monkeypatch):
        # TEST_EMAIL isn't registered in auth's user store at all — only
        # portfolio.set_user() was called (see USER_SETUP_SRC) — has_password()
        # is False for a nonexistent account, same UI as a real provider-only
        # account with no password_hash yet.
        at = _run(monkeypatch)
        html = "".join(m.value for m in at.markdown)
        assert "NOT SET" in html
        assert any(b.label == "Set a password" for b in at.button)

    def test_change_button_opens_dialog(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        at = _run(monkeypatch)
        open_btn = [b for b in at.button if b.label == "Change"][0]
        open_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert any(w.key == "set_pw_current" for w in at.text_input)


def _run_dlg_change_password(monkeypatch, email=TEST_EMAIL) -> AppTest:
    # Same one-shot-gate limitation as admin.py's _dlg_invite (see the long
    # comment above TestInviteUserButtonWiring in test_pages_admin.py) —
    # call the @st.dialog function directly and unconditionally instead of
    # driving it through the "Change" button click.
    script = f"""
from uvalu.pages_.settings import _dlg_change_password
_dlg_change_password({email!r})
"""
    at = AppTest.from_string(script, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


class TestDlgChangePassword:
    def test_correct_current_password_changes_it(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        at = _run_dlg_change_password(monkeypatch)
        at.text_input(key="set_pw_current").set_value("password123")
        at.text_input(key="set_pw_new").set_value("newpassword456")
        at.text_input(key="set_pw_confirm").set_value("newpassword456")
        submit = [b for b in at.button if b.label == "Change password"][0]
        submit.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert len(at.success) == 1
        ok, _ = auth.login(TEST_EMAIL, "newpassword456")
        assert ok

    def test_wrong_current_password_shows_error(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        at = _run_dlg_change_password(monkeypatch)
        at.text_input(key="set_pw_current").set_value("wrong-password")
        at.text_input(key="set_pw_new").set_value("newpassword456")
        at.text_input(key="set_pw_confirm").set_value("newpassword456")
        submit = [b for b in at.button if b.label == "Change password"][0]
        submit.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert "incorrect" in "".join(e.value for e in at.error).lower()

    def test_mismatched_confirmation_shows_error(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        at = _run_dlg_change_password(monkeypatch)
        at.text_input(key="set_pw_current").set_value("password123")
        at.text_input(key="set_pw_new").set_value("newpassword456")
        at.text_input(key="set_pw_confirm").set_value("different789")
        submit = [b for b in at.button if b.label == "Change password"][0]
        submit.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert "match" in "".join(e.value for e in at.error).lower()

    def test_new_password_shows_live_strength_caption(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        at = _run_dlg_change_password(monkeypatch)
        at.text_input(key="set_pw_new").set_value("weak")
        at.run()
        html = "".join(m.value for m in at.markdown)
        assert "Password strength: Weak" in html

        at.text_input(key="set_pw_new").set_value("Str0ng!-Passphrase-99")
        at.run()
        html = "".join(m.value for m in at.markdown)
        assert "Password strength: Strong" in html


def _run_dlg_set_password(monkeypatch, email=TEST_EMAIL) -> AppTest:
    script = f"""
from uvalu.pages_.settings import _dlg_set_password
_dlg_set_password({email!r})
"""
    at = AppTest.from_string(script, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


class TestDlgSetPassword:
    def test_new_password_shows_live_strength_caption(self, isolated_data, monkeypatch):
        at = _run_dlg_set_password(monkeypatch)
        at.text_input(key="set_pw2_new").set_value("weak")
        at.run()
        html = "".join(m.value for m in at.markdown)
        assert "Password strength: Weak" in html


# ── Active sessions card ──────────────────────────────────────────────────

class TestActiveSessions:
    def test_shows_current_and_other_sessions(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        _, tok1 = auth.login(TEST_EMAIL, "password123",
                             user_agent="Mozilla/5.0 (Macintosh) AppleWebKit Chrome/120.0")
        _, _, sid1 = auth.verify_token(tok1)
        auth.login(TEST_EMAIL, "password123",
                  user_agent="Mozilla/5.0 (Windows NT 10.0) AppleWebKit Firefox/120.0")
        at = _run(monkeypatch, jwt_sid=sid1)
        html = "".join(m.value for m in at.markdown)
        assert "Current" in html
        assert "Chrome on macOS" in html
        assert "Firefox on Windows" in html
        assert any(b.label == "Sign out" for b in at.button)

    def test_current_session_has_no_sign_out_button(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        _, tok1 = auth.login(TEST_EMAIL, "password123")
        _, _, sid1 = auth.verify_token(tok1)
        at = _run(monkeypatch, jwt_sid=sid1)
        assert not any(b.key == f"set_session_signout_{sid1}" for b in at.button)

    def test_sign_out_one_session_revokes_only_that_one(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        _, tok1 = auth.login(TEST_EMAIL, "password123")
        _, _, sid1 = auth.verify_token(tok1)
        _, tok2 = auth.login(TEST_EMAIL, "password123")
        _, _, sid2 = auth.verify_token(tok2)
        at = _run(monkeypatch, jwt_sid=sid1)
        signout_btn = [b for b in at.button if b.key == f"set_session_signout_{sid2}"][0]
        signout_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert auth.is_session_active(TEST_EMAIL, sid1)
        assert not auth.is_session_active(TEST_EMAIL, sid2)

    def test_sign_out_everywhere_else_keeps_current_only(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        _, tok1 = auth.login(TEST_EMAIL, "password123")
        _, _, sid1 = auth.verify_token(tok1)
        auth.login(TEST_EMAIL, "password123")
        auth.login(TEST_EMAIL, "password123")
        at = _run(monkeypatch, jwt_sid=sid1)
        revoke_btn = [b for b in at.button if b.label == "Sign out everywhere else"][0]
        revoke_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert auth.is_session_active(TEST_EMAIL, sid1)
        assert len(auth.list_sessions(TEST_EMAIL)) == 1

    def test_single_session_hides_sign_out_everywhere_button(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        _, tok1 = auth.login(TEST_EMAIL, "password123")
        _, _, sid1 = auth.verify_token(tok1)
        at = _run(monkeypatch, jwt_sid=sid1)
        assert not any(b.label == "Sign out everywhere else" for b in at.button)


# ── Linked accounts ───────────────────────────────────────────────────────

class TestLinkedAccounts:
    def test_unlinked_configured_provider_shows_connect(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        monkeypatch.setattr(oauth, "_auth_secrets", lambda: {
            "google": {"client_id": "x", "client_secret": "y",
                      "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration"}})
        at = _run(monkeypatch)
        assert any(b.label == "Connect" for b in at.button)

    def test_unconfigured_provider_shows_unavailable(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        at = _run(monkeypatch)
        html = "".join(m.value for m in at.markdown)
        assert "Not configured for this workspace" in html
        assert "Unavailable" in html

    def test_linked_provider_shows_connected_and_disconnect(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        auth.link_identity(TEST_EMAIL, "https://accounts.google.com", "sub-123", "test@example.com")
        at = _run(monkeypatch)
        html = "".join(m.value for m in at.markdown)
        assert "CONNECTED" in html
        assert any(b.label == "Disconnect" for b in at.button)

    def test_disconnect_unlinks_provider(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        auth.link_identity(TEST_EMAIL, "https://accounts.google.com", "sub-123", "test@example.com")
        at = _run(monkeypatch)
        disconnect_btn = [b for b in at.button if b.label == "Disconnect"][0]
        disconnect_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert auth.list_linked_identities(TEST_EMAIL) == []

    def test_disconnecting_only_method_is_refused(self, isolated_data, monkeypatch):
        # Password-less account with exactly one linked identity -- refused
        # by auth.unlink_identity(), surfaced here as a toast rather than
        # silently vanishing.
        _, _, token = auth.invite_user(TEST_EMAIL)
        auth.accept_invite_with_oauth(token, "https://accounts.google.com", "sub-123", TEST_EMAIL)
        at = _run(monkeypatch)
        disconnect_btn = [b for b in at.button if b.label == "Disconnect"][0]
        disconnect_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert len(auth.list_linked_identities(TEST_EMAIL)) == 1

    def test_connect_click_starts_login(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        monkeypatch.setattr(oauth, "_auth_secrets", lambda: {
            "google": {"client_id": "x", "client_secret": "y",
                      "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration"}})
        started = {"provider": None}
        monkeypatch.setattr(oauth, "start_login", lambda pid: started.__setitem__("provider", pid))
        at = _run(monkeypatch)
        connect_btn = [b for b in at.button if b.label == "Connect"][0]
        connect_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert started["provider"] == "google"


class TestOAuthSelfLinking:
    def test_completed_identity_links_to_current_account(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        monkeypatch.setattr(st, "user", FakeUser(
            True, iss="https://accounts.google.com", sub="sub-123", email=TEST_EMAIL))
        at = _run(monkeypatch)
        assert not at.exception, [str(e.value) for e in at.exception]
        linked = auth.list_linked_identities(TEST_EMAIL)
        assert len(linked) == 1
        assert linked[0]["subject"] == "sub-123"

    def test_identity_already_linked_elsewhere_is_not_stolen(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        auth.register("other@example.com", "password123456")
        auth.link_identity("other@example.com", "https://accounts.google.com", "sub-123", "other@example.com")
        monkeypatch.setattr(st, "user", FakeUser(
            True, iss="https://accounts.google.com", sub="sub-123", email=TEST_EMAIL))
        at = _run(monkeypatch)
        assert not at.exception, [str(e.value) for e in at.exception]
        assert auth.list_linked_identities(TEST_EMAIL) == []
        assert len(auth.list_linked_identities("other@example.com")) == 1


# ── Two-factor authentication ─────────────────────────────────────────────

def _enable_totp(email=TEST_EMAIL):
    import pyotp
    secret, _ = auth.begin_totp_enrollment(email)
    auth.confirm_totp_enrollment(email, pyotp.TOTP(secret).now())


class TestTotpToggleRow:
    def test_provider_only_account_shows_not_applicable(self, isolated_data, monkeypatch):
        # TEST_EMAIL isn't registered at all -- has_password() is False, same
        # as a real provider-only account.
        at = _run(monkeypatch)
        html = "".join(m.value for m in at.markdown)
        assert "Not applicable" in html
        assert not any(w.key == "set_totp_toggle" for w in at.toggle)

    def test_toggle_off_by_default(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        at = _run(monkeypatch)
        assert not at.toggle(key="set_totp_toggle").value

    def test_turning_on_opens_enrollment_dialog(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        at = _run(monkeypatch)
        at.toggle(key="set_totp_toggle").set_value(True)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert any(w.key == "totp_enroll_code" for w in at.text_input)
        assert any(b.label == "Confirm and enable" for b in at.button)

    def test_turning_off_disables_totp(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        _enable_totp()
        at = _run(monkeypatch)
        at.toggle(key="set_totp_toggle").set_value(False)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert not auth.is_totp_enabled(TEST_EMAIL)

    def test_enabled_shows_backup_codes_and_trusted_devices_rows(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        _enable_totp()
        at = _run(monkeypatch)
        html = "".join(m.value for m in at.markdown)
        assert "Backup codes" in html
        assert "Trusted devices" in html

    def test_disabled_hides_backup_codes_and_trusted_devices_rows(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        at = _run(monkeypatch)
        html = "".join(m.value for m in at.markdown)
        assert "Backup codes" not in html
        assert "Trusted devices" not in html


def _run_dlg_totp_enroll(monkeypatch, email=TEST_EMAIL) -> AppTest:
    # Same one-shot-gate limitation as _dlg_change_password — call the
    # @st.dialog function directly and unconditionally.
    script = f"""
from uvalu.pages_.settings import _dlg_totp_enroll
_dlg_totp_enroll({email!r})
"""
    at = AppTest.from_string(script, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


class TestDlgTotpEnroll:
    def test_shows_qr_and_code_input(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        at = _run_dlg_totp_enroll(monkeypatch)
        assert len(at.image) == 1
        assert any(w.key == "totp_enroll_code" for w in at.text_input)
        assert any(b.label == "Confirm and enable" for b in at.button)

    def test_correct_code_enables_totp(self, isolated_data, monkeypatch):
        import pyotp
        auth.register(TEST_EMAIL, "password123")
        at = _run_dlg_totp_enroll(monkeypatch)
        secret = auth._load_users()[TEST_EMAIL]["totp_secret"]
        at.text_input(key="totp_enroll_code").set_value(pyotp.TOTP(secret).now())
        confirm_btn = [b for b in at.button if b.label == "Confirm and enable"][0]
        confirm_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert auth.is_totp_enabled(TEST_EMAIL)

    def test_wrong_code_shows_error(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        at = _run_dlg_totp_enroll(monkeypatch)
        at.text_input(key="totp_enroll_code").set_value("000000")
        confirm_btn = [b for b in at.button if b.label == "Confirm and enable"][0]
        confirm_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert not auth.is_totp_enabled(TEST_EMAIL)
        assert "didn't match" in "".join(e.value for e in at.error)

    def test_cancel_does_not_enable_totp(self, isolated_data, monkeypatch):
        # A cancel-click's st.session_state.pop() inside this @st.dialog
        # function doesn't reliably surface via the outer at.session_state
        # after .click().run() (confirmed via a minimal repro — a plain
        # counter increment/pop showed the same staleness), so this checks
        # the actually-observable outcome (auth.py's own persisted state)
        # instead of asserting on at.session_state directly.
        auth.register(TEST_EMAIL, "password123")
        at = _run_dlg_totp_enroll(monkeypatch)
        cancel_btn = [b for b in at.button if b.label == "Cancel"][0]
        cancel_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert not auth.is_totp_enabled(TEST_EMAIL)


def _run_with_backup_codes_flag(monkeypatch, codes) -> AppTest:
    script = f"""
import streamlit as st
st.session_state["totp_new_backup_codes"] = {codes!r}
from uvalu.pages_.settings import _dlg_backup_codes_shown
_dlg_backup_codes_shown()
"""
    at = AppTest.from_string(script, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


class TestDlgBackupCodesShown:
    def test_shows_all_codes(self, isolated_data, monkeypatch):
        at = _run_with_backup_codes_flag(monkeypatch, ["aaaa-1111", "bbbb-2222"])
        assert len(at.code) == 1
        assert "aaaa-1111" in at.code[0].value
        assert "bbbb-2222" in at.code[0].value

    def test_done_disabled_until_checked(self, isolated_data, monkeypatch):
        at = _run_with_backup_codes_flag(monkeypatch, ["aaaa-1111"])
        done_btn = [b for b in at.button if b.label == "Done"][0]
        assert done_btn.disabled

    def test_done_clickable_once_checked(self, isolated_data, monkeypatch):
        # See TestDlgTotpEnroll's cancel test for why this doesn't assert on
        # at.session_state directly across a dialog button click.
        at = _run_with_backup_codes_flag(monkeypatch, ["aaaa-1111"])
        at.checkbox(key="totp_backup_saved").set_value(True)
        at.run()
        done_btn = [b for b in at.button if b.label == "Done"][0]
        assert not done_btn.disabled
        done_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]


class TestBackupCodesCard:
    def test_shows_remaining_count(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        _enable_totp()
        at = _run(monkeypatch)
        html = "".join(m.value for m in at.markdown)
        assert "10 unused code" in html

    def test_regenerate_opens_confirm_dialog(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        _enable_totp()
        at = _run(monkeypatch)
        regen_btn = [b for b in at.button if b.label == "Regenerate"][0]
        regen_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert any(b.key == "totp_regen_confirm" for b in at.button)

    def test_confirm_regenerates_codes(self, isolated_data, monkeypatch):
        # Same AppTest dialog-session_state limitation noted on TestDlgTotpEnroll's
        # cancel test -- checks the real backup-codes-remaining count (an
        # observable, persisted side effect) rather than the staged
        # at.session_state["totp_new_backup_codes"] value.
        auth.register(TEST_EMAIL, "password123")
        _enable_totp()
        at = _run(monkeypatch)
        regen_btn = [b for b in at.button if b.label == "Regenerate"][0]
        regen_btn.click().run()
        confirm_btn = [b for b in at.button if b.key == "totp_regen_confirm"][0]
        confirm_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert auth.backup_codes_remaining(TEST_EMAIL) == 10


class TestTrustedDevicesCard:
    def test_shows_device_count(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        _enable_totp()
        auth.trust_this_device(TEST_EMAIL)
        at = _run(monkeypatch)
        html = "".join(m.value for m in at.markdown)
        assert "1 device" in html

    def test_revoke_all_clears_devices(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        _enable_totp()
        auth.trust_this_device(TEST_EMAIL)
        at = _run(monkeypatch)
        revoke_btn = [b for b in at.button if b.label == "Revoke all"][0]
        revoke_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert auth.trusted_device_count(TEST_EMAIL) == 0

    def test_revoke_all_disabled_when_no_devices(self, isolated_data, monkeypatch):
        auth.register(TEST_EMAIL, "password123")
        _enable_totp()
        at = _run(monkeypatch)
        revoke_btn = [b for b in at.button if b.label == "Revoke all"][0]
        assert revoke_btn.disabled


# ── Passkeys stub (Phase 3 — UI only, no WebAuthn) ──────────────────────────

class TestPasskeysStubRow:
    def test_shows_phase_3_badge_and_disabled_manage_button(self, isolated_data, monkeypatch):
        at = _run(monkeypatch)
        html = "".join(m.value for m in at.markdown)
        assert "Passkeys" in html
        assert "PHASE 3" in html
        manage_btn = [b for b in at.button if b.label == "Manage"][0]
        assert manage_btn.disabled

    def test_shown_regardless_of_password_or_totp_state(self, isolated_data, monkeypatch):
        # No account registered at all (provider-only) -- the row still
        # appears, unlike the TOTP-gated rows above it.
        at = _run(monkeypatch)
        assert any(b.label == "Manage" for b in at.button)
