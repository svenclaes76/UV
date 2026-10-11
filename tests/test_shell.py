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


class TestPriceIndicator:
    """WP-DQ8: the topbar pill reflects the real price feed, not a hardcoded
    'Live'."""

    @pytest.fixture(autouse=True)
    def _no_session(self, monkeypatch):
        # Force the session-state read to miss so each test controls `status`.
        monkeypatch.setattr(shell.st, "session_state", {}, raising=False)

    def test_market_closed_is_grey_and_not_live(self, monkeypatch):
        monkeypatch.setattr(shell, "is_market_hours", lambda: False)
        text, color = shell._price_indicator()
        assert text.startswith("Market closed") and color == "#8A8A8A"

    def test_all_intraday_is_live_mint(self, monkeypatch):
        monkeypatch.setattr(shell, "is_market_hours", lambda: True)
        shell.st.session_state["_price_feed_status"] = {
            "as_of": None, "total": 5, "intraday": 5, "delayed": 0, "stale": 0}
        text, color = shell._price_indicator()
        assert text.startswith("Live") and color == "#1DD6A4"

    def test_delayed_names_show_amber_count(self, monkeypatch):
        monkeypatch.setattr(shell, "is_market_hours", lambda: True)
        shell.st.session_state["_price_feed_status"] = {
            "as_of": None, "total": 8, "intraday": 5, "delayed": 3, "stale": 0}
        text, color = shell._price_indicator()
        assert "3/8" in text and color == "#C98A3A"


def _run_topbar(active_path="dashboard", is_admin=False, register_admin=True):
    script = f"""
import streamlit as st
from uvalu import nav as nav_registry, shell
nav_registry.pages["dashboard"] = st.Page(lambda: None, title="Dashboard")
nav_registry.pages["screener"] = st.Page(lambda: None, title="Screener")
nav_registry.pages["settings"] = st.Page(lambda: None, title="Settings")
nav_registry.pages["help"] = st.Page(lambda: None, title="Help")
nav_registry.pages["legal"] = st.Page(lambda: None, title="Legal", url_path="legal")
nav_registry.pages["about"] = st.Page(lambda: None, title="About", url_path="about")
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


class TestUserMenu:
    def test_menu_items_and_order(self):
        at = _run_topbar()
        assert not at.exception, [str(e.value) for e in at.exception]
        labels = [link.label for link in at.get("page_link") if link.label in
                  ("Settings", "Methodology", "About Uvalu", "Legal & policies")]
        # No "Legal & policies": the footer and Settings › Legal lead there.
        assert labels == ["Settings", "Methodology", "About Uvalu"]

    def test_header_shows_free_beta_not_the_role(self):
        at = _run_topbar()
        html = "".join(m.value for m in at.markdown)
        assert ">Free beta</span>" in html and ">Analyst</span>" not in html

    def test_sign_out_is_a_red_menu_item_with_a_symbol(self):
        at = _run_topbar()
        html = "".join(m.value for m in at.markdown)
        assert 'class="uv-menu-signout"' in html and ">logout</span>Sign out</a>" in html


class TestNotices:
    def test_beta_box_links_the_terms(self):
        at = AppTest.from_string("from uvalu import shell\nshell.render_beta_banner()\n", default_timeout=60)
        at.run()
        html = at.markdown[0].value
        assert 'href="/legal?doc=terms"' in html and "Terms →" in html
        assert "border-radius:8px" in html          # stays a rounded box (G01)
        assert "justify-content:center" in html     # text centred (design reference)

    def test_inactive_nav_links_reach_the_label(self):
        """Streamlit 1.60 gives the link label its own <span> colour; the nav
        CSS has to override it, or every link reads as active (GL-03)."""
        css = shell._topbar_css("screener")
        assert '.st-key-uv_topbar_nav a[data-testid="stPageLink-NavLink"] * { color: inherit !important; }' in css

    def test_peer_rebuild_strip_shown_only_while_pending(self, monkeypatch):
        from uvalu import data
        for pending, expected in ((True, 1), (False, 0)):
            monkeypatch.setattr(data, "peer_reference_pending", lambda p=pending: p)
            at = AppTest.from_string("from uvalu import shell\nshell.render_peer_rebuild_strip()\n",
                                     default_timeout=60)
            at.run()
            assert not at.exception, [str(e.value) for e in at.exception]
            assert len(at.markdown) == expected
            if expected:
                assert "Rebuilding the peer reference" in at.markdown[0].value

    def test_notice_order(self):
        """Top bar, update notice, reload prompt, beta box, peer strip (GL-02)."""
        from pathlib import Path
        src = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
        calls = ["shell.render_topbar(", "update_notice.render_whats_new_notice(",
                 "update_notice.render_reload_prompt(", "shell.render_beta_banner(",
                 "shell.render_peer_rebuild_strip("]
        positions = [src.index(c) for c in calls]
        assert positions == sorted(positions)

    def test_error_box_has_message_and_reference(self):
        at = AppTest.from_string("from uvalu import shell\nshell.render_error_reference()\n", default_timeout=60)
        at.run()
        html = at.markdown[0].value
        assert "Couldn’t load this page. Try again in a moment." in html
        assert "background:var(--down-bg)" in html and "Reference for support:" in html
        assert 'font-family:var(--uv-mono);' in html


def test_top_bar_shows_the_consensus_lockup():
    """Logo plan L2: the outlined lockup at a 26px mark height, colours from
    the theme tokens; no live-text wordmark."""
    at = AppTest.from_string(
        "from uvalu import shell, nav\n"
        "class _N: url_path = 'screener'\n"
        "shell.render_topbar(_N())\n", default_timeout=60)
    at.run()
    html = "".join(m.value for m in at.markdown)
    assert 'aria-label="Uvalu"' in html and 'height="26"' in html
    assert "var(--logo-ring)" in html and "uval<span" not in html
