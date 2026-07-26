"""AppTest coverage for uvalu/pages_/admin.py."""
import pandas as pd
from streamlit.testing.v1 import AppTest

import auth
import backup
import portfolio
import settings
from uvalu.pages_ import admin as admin_page
from tests.conftest import TEST_EMAIL, fake_cached_fn


def _run(monkeypatch, role="Admin", section=None) -> AppTest:
    # AppTest.from_function re-executes a function's SOURCE TEXT as a fresh
    # script (no closure over enclosing variables — confirmed via
    # inspect.getsourcelines in streamlit's own app_test.py), so role/section
    # can't be passed as real Python values here. AppTest.from_string takes
    # the already-interpolated script text directly instead.
    monkeypatch.setattr(admin_page, "_load_all_screener_data", fake_cached_fn(None))

    section_line = f'st.session_state["admin_section"] = {section!r}' if section else ""
    script_src = f"""
import streamlit as st
from uvalu.pages_ import admin as admin_page
st.session_state["user_email"] = "test@example.com"
st.session_state["user_role"] = {role!r}
{section_line}
admin_page.render()
"""
    at = AppTest.from_string(script_src, default_timeout=60)
    at.run()
    return at


def test_non_admin_sees_access_denied(isolated_data, monkeypatch):
    at = _run(monkeypatch, role="Analyst")
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "Admin access required" in "".join(e.value for e in at.error)


def test_admin_renders_users_section_by_default(isolated_data, monkeypatch):
    auth.register("test@example.com", "password123")
    at = _run(monkeypatch, role="Admin")
    assert not at.exception, [str(e.value) for e in at.exception]
    html = "".join(m.value for m in at.markdown)
    assert "test@example.com" in html


def test_admin_stat_tiles_reflect_user_counts(isolated_data, monkeypatch):
    auth.register("admin@example.com", "password123")
    auth.register("second@example.com", "password12345", role="Viewer")
    auth.invite_user("invited@example.com")
    at = _run(monkeypatch, role="Admin")
    assert not at.exception, [str(e.value) for e in at.exception]
    html = "".join(m.value for m in at.markdown)
    assert "Total users" in html


def test_feeds_section_shows_all_exchanges(isolated_data, monkeypatch):
    at = _run(monkeypatch, role="Admin", section="feeds")
    assert not at.exception, [str(e.value) for e in at.exception]
    html = "".join(m.value for m in at.markdown)
    for label in settings.EXCHANGE_LABELS.values():
        assert label in html


def test_backups_section_shows_no_backups_message(isolated_data, monkeypatch):
    at = _run(monkeypatch, role="Admin", section="backups")
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "No backups yet" in "".join(i.value for i in at.info)


def test_backups_section_lists_existing_backup(isolated_data, monkeypatch):
    portfolio.save_portfolio(pd.DataFrame([{"ticker": "AAA.BR"}]))
    backup.create_backup(TEST_EMAIL)
    at = _run(monkeypatch, role="Admin", section="backups")
    assert not at.exception, [str(e.value) for e in at.exception]
    html = "".join(m.value for m in at.markdown)
    assert "Manual snapshot" in html


# ── Users: role change / suspend / delete ────────────────────────────────

class TestUserRowActions:
    def test_changing_role_persists(self, isolated_data, monkeypatch):
        auth.register("admin@example.com", "password123")
        auth.register("second@example.com", "password12345", role="Viewer")
        at = _run(monkeypatch, role="Admin")
        role_select = at.selectbox(key="admin_role_second@example.com")
        role_select.set_value("Analyst")
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        users = {u["email"]: u for u in auth.list_users()}
        assert users["second@example.com"]["role"] == "Analyst"

    def test_current_users_own_role_select_is_disabled(self, isolated_data, monkeypatch):
        # _run() hardcodes user_email to test@example.com — the "own row"
        # comparison is against that exact address.
        auth.register("test@example.com", "password123")
        at = _run(monkeypatch, role="Admin")
        role_select = at.selectbox(key="admin_role_test@example.com")
        assert role_select.disabled

    def test_suspend_then_reactivate(self, isolated_data, monkeypatch):
        auth.register("admin@example.com", "password123")
        auth.register("second@example.com", "password12345")
        at = _run(monkeypatch, role="Admin")
        suspend_btn = [b for b in at.button if b.key == "admin_toggle_second@example.com"][0]
        suspend_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        users = {u["email"]: u for u in auth.list_users()}
        assert users["second@example.com"]["status"] == "Suspended"

        reactivate_btn = [b for b in at.button if b.key == "admin_toggle_second@example.com"][0]
        assert reactivate_btn.label == "Reactivate"
        reactivate_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        users = {u["email"]: u for u in auth.list_users()}
        assert users["second@example.com"]["status"] == "Active"

    def test_delete_via_overflow_popover(self, isolated_data, monkeypatch):
        auth.register("admin@example.com", "password123")
        auth.register("second@example.com", "password12345")
        at = _run(monkeypatch, role="Admin")
        delete_btn = [b for b in at.button if b.key == "admin_delete_second@example.com"][0]
        delete_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        emails = {u["email"] for u in auth.list_users()}
        assert "second@example.com" not in emails

    def test_search_filters_user_list(self, isolated_data, monkeypatch):
        auth.register("admin@example.com", "password123")
        auth.register("second@example.com", "password12345")
        at = _run(monkeypatch, role="Admin")
        search = at.text_input(key="admin_user_search")
        search.set_value("second")
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        html = "".join(m.value for m in at.markdown)
        assert "second@example.com" in html
        assert "admin@example.com" not in html


# ── Invite user dialog ─────────────────────────────────────────────────────
#
# _dlg_invite()/_dlg_restore() are only invoked via `if st.button("..."):
# _dlg_X()` — a ONE-SHOT gate tied to that specific click. Unlike
# tests/test_dialogs.py's dialogs (called unconditionally at a script's top
# level on every run, so a follow-up AppTest.run() re-enters the same
# dialog function fresh) or tests/test_drawer.py's open_drawer, clicking a
# SECOND widget inside one of these two dialogs on a SEPARATE .run() call
# does nothing silently: the "Invite user"/"Restore" button isn't re-clicked
# on that later run, so the `if st.button(...):` gate is False, the dialog
# function never re-executes, and the staged value-set/click on its
# (stale) inner widgets has nothing to land on. Confirmed directly — this
# is a real behavioral difference from the other two dialog modules, not a
# fluke. So: verify the button-click WIRING (single run) separately from
# the dialog's OWN internal Save/Cancel logic (call the @st.dialog function
# directly and unconditionally, exactly like test_dialogs.py does).

class TestInviteUserButtonWiring:
    def test_click_opens_dialog(self, isolated_data, monkeypatch):
        auth.register("admin@example.com", "password123")
        at = _run(monkeypatch, role="Admin")
        open_btn = [b for b in at.button if b.label == "Invite user"][0]
        open_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert any(w.key == "admin_invite_email" for w in at.text_input)


def _run_dlg_invite(monkeypatch) -> AppTest:
    script = """
from uvalu.pages_.admin import _dlg_invite
_dlg_invite()
"""
    at = AppTest.from_string(script, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


class TestDlgInvite:
    def test_send_invite_creates_user(self, isolated_data, monkeypatch):
        at = _run_dlg_invite(monkeypatch)
        at.text_input(key="admin_invite_email").set_value("new@example.com")
        send_btn = [b for b in at.button if b.label == "Send invite"][0]
        send_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]

        users = {u["email"]: u for u in auth.list_users()}
        assert "new@example.com" in users
        assert users["new@example.com"]["status"] == "Invited"
        # Temp password is shown once, copyable via st.code.
        assert len(at.code) == 1

    def test_cancel_reruns_without_inviting(self, isolated_data, monkeypatch):
        at = _run_dlg_invite(monkeypatch)
        cancel_btn = [b for b in at.button if b.label == "Cancel"][0]
        cancel_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert len(auth.list_users()) == 0

    def test_invalid_email_shows_error(self, isolated_data, monkeypatch):
        at = _run_dlg_invite(monkeypatch)
        at.text_input(key="admin_invite_email").set_value("not-an-email")
        send_btn = [b for b in at.button if b.label == "Send invite"][0]
        send_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert "valid email" in "".join(e.value for e in at.error)
        assert len(auth.list_users()) == 0


# ── Feeds section ─────────────────────────────────────────────────────────

class TestFeedsSection:
    def test_disabling_an_exchange_persists(self, isolated_data, monkeypatch):
        at = _run(monkeypatch, role="Admin", section="feeds")
        toggle = at.toggle(key="admin_feed_brussels")
        toggle.set_value(False)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        enabled = settings.load_shared_settings()["enabled_exchanges"]
        assert "brussels" not in enabled

    def test_disabling_last_exchange_is_reverted_via_toast(self, isolated_data, monkeypatch):
        # Previously crashed (task_45bd0152, now fixed): the revert defers
        # to a plain `_admin_feed_revert_<key>` session_state flag checked
        # BEFORE the toggle widget is instantiated on the next run, instead
        # of overwriting the widget's own key after the fact.
        shared = settings.load_shared_settings()
        shared["enabled_exchanges"] = ["brussels"]
        settings.save_shared_settings(shared)

        at = _run(monkeypatch, role="Admin", section="feeds")
        toggle = at.toggle(key="admin_feed_brussels")
        toggle.set_value(False)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert any("At least one exchange" in t.value for t in at.toast)
        assert at.toggle(key="admin_feed_brussels").value is True
        assert settings.load_shared_settings()["enabled_exchanges"] == ["brussels"]


# ── Backups section: create + restore ────────────────────────────────────

class TestBackupsSection:
    def test_create_backup_button(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(pd.DataFrame([{"ticker": "AAA.BR"}]))
        at = _run(monkeypatch, role="Admin", section="backups")
        create_btn = [b for b in at.button if b.label == "Create backup now"][0]
        create_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert len(backup.list_backups()) == 1

    def test_restore_button_opens_dialog(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(pd.DataFrame([{"ticker": "AAA.BR"}]))
        entry = backup.create_backup(TEST_EMAIL)
        at = _run(monkeypatch, role="Admin", section="backups")
        restore_btn = [b for b in at.button if b.key == f"admin_restore_{entry['id']}"][0]
        restore_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert any(w.value.startswith("This replaces all current portfolio data")
                  for w in at.warning)


class TestDlgRestore:
    # _dlg_restore is only invoked via `if st.button("Restore"): _dlg_restore(...)`
    # — same one-shot-gate limitation as _dlg_invite (see the long comment
    # above TestInviteUserButtonWiring). Call it directly and unconditionally
    # here to test its own confirm/done flow across multiple .run() calls.

    def test_confirm_restores_and_shows_done_state(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(pd.DataFrame([{"ticker": "AAA.BR"}]))
        entry = backup.create_backup(TEST_EMAIL)
        portfolio.save_portfolio(pd.DataFrame([{"ticker": "CHANGED.BR"}]))

        script = f"""
from uvalu.pages_.admin import _dlg_restore
_dlg_restore({entry['id']!r}, {entry['created_at']!r}, {TEST_EMAIL!r})
"""
        at = AppTest.from_string(script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]

        confirm_btn = [b for b in at.button if b.label == "Restore workspace"][0]
        confirm_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert portfolio.load_portfolio().iloc[0]["ticker"] == "AAA.BR"
        assert "Restore complete" in "".join(m.value for m in at.markdown)

        done_btn = [b for b in at.button if b.label == "Done"][0]
        done_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]

    def test_cancel_does_not_restore(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(pd.DataFrame([{"ticker": "AAA.BR"}]))
        entry = backup.create_backup(TEST_EMAIL)
        portfolio.save_portfolio(pd.DataFrame([{"ticker": "CHANGED.BR"}]))

        script = f"""
from uvalu.pages_.admin import _dlg_restore
_dlg_restore({entry['id']!r}, {entry['created_at']!r}, {TEST_EMAIL!r})
"""
        at = AppTest.from_string(script, default_timeout=60)
        at.run()
        cancel_btn = [b for b in at.button if b.label == "Cancel"][0]
        cancel_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert portfolio.load_portfolio().iloc[0]["ticker"] == "CHANGED.BR"
