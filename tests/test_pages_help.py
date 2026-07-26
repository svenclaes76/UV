"""AppTest coverage for uvalu/pages_/help.py — static content page, no data
dependencies, so no isolation fixtures are needed here."""
import pytest
from streamlit.testing.v1 import AppTest

from uvalu import nav as nav_registry


@pytest.fixture(autouse=True)
def _clean_nav_registry():
    # uvalu.nav.pages is process-global mutable state — tests/test_app_smoke.py
    # runs the real app.py, which populates it with every real page and never
    # clears it, so later tests can't assume it starts empty.
    saved = dict(nav_registry.pages)
    nav_registry.pages.clear()
    yield
    nav_registry.pages.clear()
    nav_registry.pages.update(saved)


def _run() -> AppTest:
    def _script():
        from uvalu.pages_ import help as help_page
        help_page.render()

    at = AppTest.from_function(_script, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def test_renders_without_exceptions():
    _run()


def test_shows_all_four_section_headers():
    at = _run()
    html = "".join(m.value for m in at.markdown)
    for header in ("Signal legend", "The six fair-value models", "Hard-veto rules", "Frequently asked"):
        assert header in html


def test_shows_signal_badges_for_all_four_kinds():
    at = _run()
    html = "".join(m.value for m in at.markdown)
    for badge_class in ("uv-badge-buy", "uv-badge-monitor", "uv-badge-avoid", "uv-badge-veto"):
        assert badge_class in html


def test_no_back_button_when_dashboard_not_registered():
    at = _run()
    assert len(at.button) == 0


def test_back_button_present_when_dashboard_registered():
    def _script():
        import streamlit as st
        from uvalu import nav as nav_registry
        from uvalu.pages_ import help as help_page
        nav_registry.pages["dashboard"] = st.Page(lambda: None, title="Dashboard")
        help_page.render()

    at = AppTest.from_function(_script, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert len(at.button) == 1
    assert at.button[0].label == "← Back"
