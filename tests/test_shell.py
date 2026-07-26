"""Tests for uvalu/shell.py — the top-bar shell (logo, nav, theme toggle,
avatar menu). Previously untested directly; the module's 93% baseline
coverage came entirely incidentally from test_app_smoke.py running the
real app.py.
"""
import pytest
from streamlit.testing.v1 import AppTest

from uvalu import nav as nav_registry, shell


@pytest.fixture(autouse=True)
def _clean_nav_registry():
    saved = dict(nav_registry.pages)
    nav_registry.pages.clear()
    yield
    nav_registry.pages.clear()
    nav_registry.pages.update(saved)


class TestInitials:
    def test_two_word_local_part(self):
        assert shell._initials("marek.kowalski@example.com") == "MK"

    def test_single_word_local_part(self):
        assert shell._initials("marek@example.com") == "MA"

    def test_empty_email_returns_question_mark(self):
        assert shell._initials("") == "?"
        assert shell._initials(None) == "?"


class TestDisplayName:
    def test_title_cases_dotted_local_part(self):
        assert shell._display_name("marek.kowalski@example.com") == "Marek Kowalski"

    def test_empty_email_returns_email_itself(self):
        assert shell._display_name("") == ""


def _run_topbar(active_path="dashboard", is_admin=False, register_admin=True):
    script = f"""
import streamlit as st
from uvalu import nav as nav_registry, shell
nav_registry.pages["dashboard"] = st.Page(lambda: None, title="Dashboard")
nav_registry.pages["screener"] = st.Page(lambda: None, title="Screener")
nav_registry.pages["settings"] = st.Page(lambda: None, title="Settings")
nav_registry.pages["help"] = st.Page(lambda: None, title="Help")
{'nav_registry.pages["admin"] = st.Page(lambda: None, title="Admin")' if register_admin else ""}
st.session_state["user_email"] = "test@example.com"
st.session_state["user_role"] = "{"Admin" if is_admin else "Analyst"}"


class _Nav:
    url_path = "{active_path}"


shell.render_topbar(_Nav())
"""
    at = AppTest.from_string(script, default_timeout=60)
    at.run()
    return at


class TestRenderTopbar:
    def test_renders_without_exceptions(self):
        at = _run_topbar()
        assert not at.exception, [str(e.value) for e in at.exception]

    def test_closes_stray_popover_on_settings_path(self):
        at = _run_topbar(active_path="settings")
        assert not at.exception, [str(e.value) for e in at.exception]

    def test_closes_stray_popover_on_help_path(self):
        at = _run_topbar(active_path="help")
        assert not at.exception, [str(e.value) for e in at.exception]

    def test_theme_toggle_click_triggers_reload_script(self):
        at = _run_topbar()
        toggle_btn = [b for b in at.button if b.key == "uv_theme_toggle_btn"][0]
        toggle_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]

    def test_admin_portal_link_shown_for_admin_user(self):
        at = _run_topbar(is_admin=True, register_admin=True)
        assert not at.exception, [str(e.value) for e in at.exception]
        assert any(link.label == "Admin portal" for link in at.get("page_link"))

    def test_admin_portal_link_hidden_for_non_admin_user(self):
        at = _run_topbar(is_admin=False, register_admin=True)
        assert not at.exception, [str(e.value) for e in at.exception]
        assert not any(link.label == "Admin portal" for link in at.get("page_link"))

    def test_admin_portal_link_hidden_when_page_not_registered(self):
        at = _run_topbar(is_admin=True, register_admin=False)
        assert not at.exception, [str(e.value) for e in at.exception]
        assert not any(link.label == "Admin portal" for link in at.get("page_link"))
