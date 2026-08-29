"""Tests for uvalu/drawer.py — the shared stock-detail slide-in panel.

Building on tests/test_dialogs.py's finding that AppTest's dialog-button
interactions ARE reliable here (contrary to this project's earlier, more
general caution about dialog testing) as long as the test script mirrors
the real call site's own guards (e.g. checking `pf is not None and not
pf.empty` before invoking a dialog against a portfolio DataFrame).
"""
import math

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import portfolio
from uvalu import drawer, nav as nav_registry
from tests.conftest import make_scored_row, USER_SETUP_SRC


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", "unit-test-key-123")
    monkeypatch.setattr(portfolio, "_BASE_DIR", tmp_path / "portfolio")
    portfolio.set_user("test@example.com")
    yield
    portfolio.set_user("")


@pytest.fixture(autouse=True)
def _clean_nav_registry():
    # Must clear BEFORE the test too, not just restore after — test_app_smoke.py
    # runs the real app.py, which populates uvalu.nav.pages with every real
    # page and never clears it, so later tests can't assume it starts empty
    # (see tests/test_pages_help.py's identical fixture).
    saved = dict(nav_registry.pages)
    nav_registry.pages.clear()
    yield
    nav_registry.pages.clear()
    nav_registry.pages.update(saved)


# ── pure helpers ──────────────────────────────────────────────────────────

class TestFv:
    def test_returns_dash_for_none(self):
        assert drawer._fv({"x": None}, "x") == "—"

    def test_returns_dash_for_nan(self):
        assert drawer._fv({"x": float("nan")}, "x") == "—"

    def test_formats_with_fmt_function(self):
        assert drawer._fv({"x": 5}, "x", lambda v: f"{v}!") == "5!"

    def test_str_without_fmt(self):
        assert drawer._fv({"x": "hello"}, "x") == "hello"


class TestSafeFloat:
    def test_none_returns_default(self):
        assert drawer._safe_float(None) == 0.0
        assert drawer._safe_float(None, default=5.0) == 5.0

    def test_nan_returns_default(self):
        assert drawer._safe_float(float("nan")) == 0.0

    def test_real_value_is_converted(self):
        assert drawer._safe_float("3.5") == 3.5
        assert drawer._safe_float(3) == 3.0


class TestGoAnalysis:
    # The "page registered -> actually calls st.switch_page()" branch is
    # covered indirectly by TestOpenDrawer.test_view_full_analysis_button_navigates
    # below (calling _go_analysis from a real button click inside the open
    # dialog) — calling st.switch_page() directly at a bare script's
    # top level, outside any click/dialog context, hangs AppTest's script
    # runner indefinitely (confirmed: 60s timeout, unlike the button-click
    # path which completes normally), so it isn't tested standalone here.

    def test_noop_switch_when_page_not_registered(self):
        def _script():
            import streamlit as st
            from uvalu import drawer
            drawer._go_analysis("AAA.BR")
            st.text(st.session_state.get("_analysis_ticker"))

        at = AppTest.from_function(_script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.text[0].value == "AAA.BR"


class TestGoPortfolioEdit:
    def test_sets_section_and_ticker(self):
        def _script():
            import streamlit as st
            from uvalu import drawer
            drawer._go_portfolio_edit("AAA.BR")
            st.text(st.session_state.get("port_section"))
            st.text(st.session_state.get("_pf_edit_ticker"))

        at = AppTest.from_function(_script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.text[0].value == "open"
        assert at.text[1].value == "AAA.BR"


# ── dispatch_pending_drawer_action ────────────────────────────────────────

class TestDispatchPendingDrawerAction:
    def test_noop_when_no_pending_action(self):
        def _script():
            import streamlit as st
            from uvalu.drawer import dispatch_pending_drawer_action
            dispatch_pending_drawer_action()
            st.text("done")

        at = AppTest.from_function(_script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.text[0].value == "done"

    def test_buy_action_opens_add_position_dialog_with_presets(self):
        def _script():
            import streamlit as st
            from uvalu.drawer import dispatch_pending_drawer_action
            st.session_state["_drw_action"] = {"kind": "buy", "ticker": "AAA.BR", "name": "Alpha Corp", "price": 42.0}
            dispatch_pending_drawer_action()

        at = AppTest.from_function(_script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.text_input(key="dlg_ap_ticker").value == "AAA.BR"
        assert at.text_input(key="dlg_ap_name").value == "Alpha Corp"
        assert at.number_input(key="dlg_ap_price").value == 42.0
        # A one-shot pop — the pending action must not survive the call.
        assert "_drw_action" not in at.session_state

    def test_sell_action_opens_sell_dialog_when_portfolio_has_position(self):
        portfolio.save_portfolio(pd.DataFrame([{
            "ticker": "AAA.BR", "name": "Alpha Corp", "shares": 10, "live_price": 100.0,
        }]))

        def _script():
            import portfolio
            portfolio.set_user("test@example.com")
            import streamlit as st
            from uvalu.drawer import dispatch_pending_drawer_action
            st.session_state["_drw_action"] = {"kind": "sell", "ticker": "AAA.BR", "price": 105.0}
            dispatch_pending_drawer_action()

        at = AppTest.from_function(_script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert any(b.label == "Confirm close" for b in at.button)

    def test_sell_action_noop_when_portfolio_empty(self):
        def _script():
            import streamlit as st
            from uvalu.drawer import dispatch_pending_drawer_action
            st.session_state["_drw_action"] = {"kind": "sell", "ticker": "AAA.BR", "price": 105.0}
            dispatch_pending_drawer_action()
            st.text("done")

        at = AppTest.from_function(_script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.text[0].value == "done"


# ── open_drawer ───────────────────────────────────────────────────────────

def _open_drawer_script(veto=False) -> str:
    return USER_SETUP_SRC + f"""
import pandas as pd
from uvalu.drawer import open_drawer
row = pd.Series({make_scored_row(veto=veto)!r})
open_drawer(row, None)
"""


class TestOpenDrawer:
    def test_renders_not_held_state(self):
        at = AppTest.from_string(_open_drawer_script(), default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        html = "".join(m.value for m in at.markdown)
        assert "AAA.BR" in html
        assert "Not held" in html
        assert any(b.label == "Add" for b in at.button)

    def test_renders_veto_banner(self):
        at = AppTest.from_string(_open_drawer_script(veto=True), default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert "Hard veto triggered" in "".join(m.value for m in at.markdown)

    def test_renders_held_state_with_position_metrics(self):
        portfolio.save_portfolio(pd.DataFrame([{
            "ticker": "AAA.BR", "name": "Alpha Corp", "shares": 10,
            "purchase_value": 900.0, "purchase_price": 90.0,
        }]))
        at = AppTest.from_string(_open_drawer_script(), default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        html = "".join(m.value for m in at.markdown)
        assert "Shares held" in html
        assert "Unrealised P&L" in html
        assert any(b.label == "Edit" for b in at.button)
        assert any(b.label == "Close" for b in at.button)

    def test_prefers_live_price_over_stale_screener_price(self):
        # dashboard.py's holdings table merges a 60s-fresh live_price
        # alongside the screener's own up-to-24h-cached Price -- the drawer
        # must use the fresher one for the hero tile and Position value/P&L
        # when it's present, not silently fall back to the stale figure.
        portfolio.save_portfolio(pd.DataFrame([{
            "ticker": "AAA.BR", "name": "Alpha Corp", "shares": 10,
            "purchase_value": 900.0, "purchase_price": 90.0,
        }]))
        script = USER_SETUP_SRC + f"""
import pandas as pd
from uvalu.drawer import open_drawer
row = pd.Series({make_scored_row(Price=100.0, live_price=150.0)!r})
open_drawer(row, None)
"""
        at = AppTest.from_string(script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        html = "".join(m.value for m in at.markdown)
        assert "€150.00" in html   # hero Price tile, from live_price
        assert "€100.00" not in html
        assert "€1,500" in html    # Position value = 10 shares * live_price
        assert "€1,000" not in html

    def test_watchlisted_not_held_shows_status(self):
        portfolio.save_watchlist({"AAA.BR"})
        at = AppTest.from_string(_open_drawer_script(), default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert "Not held" in "".join(m.value for m in at.markdown)

    def test_view_full_analysis_button_navigates(self):
        script = f"""
import pandas as pd
import streamlit as st
from uvalu import nav as nav_registry
from uvalu.drawer import open_drawer
nav_registry.pages["analysis"] = st.Page(lambda: None, title="Analysis")
row = pd.Series({make_scored_row()!r})
open_drawer(row, None)
"""
        at = AppTest.from_string(script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        view_btn = [b for b in at.button if b.label == "View full analysis"][0]
        view_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.session_state["_analysis_ticker"] == "AAA.BR"

    def test_add_button_stashes_buy_action_and_reruns(self):
        at = AppTest.from_string(_open_drawer_script(), default_timeout=60)
        at.run()
        add_btn = [b for b in at.button if b.label == "Add"][0]
        add_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        # After st.rerun(), the drawer dialog is not re-invoked by this bare
        # script (no dispatch_pending_drawer_action call here — that's the
        # caller's job), so the stashed action should still be sitting in
        # session_state for the next real page render to pick up.
        assert at.session_state["_drw_action"]["kind"] == "buy"
        assert at.session_state["_drw_action"]["ticker"] == "AAA.BR"

    def test_viewer_role_disables_edit_and_sell_buttons(self):
        portfolio.save_portfolio(pd.DataFrame([{
            "ticker": "AAA.BR", "name": "Alpha Corp", "shares": 10,
            "purchase_value": 900.0, "purchase_price": 90.0,
        }]))
        script = USER_SETUP_SRC + f"""
import pandas as pd
import streamlit as st
from uvalu.drawer import open_drawer
st.session_state["user_role"] = "Viewer"
row = pd.Series({make_scored_row()!r})
open_drawer(row, None)
"""
        at = AppTest.from_string(script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        edit_btn = [b for b in at.button if b.label == "Edit"][0]
        close_btn = [b for b in at.button if b.label == "Close"][0]
        assert edit_btn.disabled
        assert close_btn.disabled
