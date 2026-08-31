"""AppTest coverage for uvalu/pages_/portfolio.py.

The three inline per-row edit dialogs here (_dlg_edit_open_position/
_dlg_edit_closed_position/_dlg_edit_dividend) are nested closures defined
INSIDE render() itself, not importable module-level functions like
uvalu/dialogs.py's — and each is only invoked via a one-shot trigger (a
specific row's edit-pencil button being clicked on THAT run, or a popped
session_state ticket). Per tests/test_pages_admin.py's finding, such
one-shot-gated dialogs do NOT persist across separate AppTest.run() calls
the way unconditionally-invoked ones do — so testing a full open-dialog
Save/Delete flow means RE-CLICKING the same triggering row's edit button
in the SAME staged batch as the dialog's own Save/Delete button before
each .run(), keeping the trigger condition true on every run that needs
the dialog's body to actually execute.
"""
import pandas as pd
import yfinance as yf
from streamlit.testing.v1 import AppTest

import portfolio
from uvalu.pages_ import portfolio as portfolio_page
from tests.conftest import (make_portfolio_df, fake_portfolio_scored, USER_SETUP_SRC)


def _run(monkeypatch, section=None) -> AppTest:
    monkeypatch.setattr(portfolio_page, "_load_portfolio_scored", fake_portfolio_scored())
    monkeypatch.setattr(portfolio_page, "_fetch_prices_cached", lambda tickers: {
        t: {"price": 110.0} for t in tickers
    })
    # A populated portfolio with no/stale value history triggers a real
    # backfill_value_history() -> yf.download() network call otherwise
    # (caught internally, so it doesn't fail the test, just slow and
    # network-dependent) — stub it out like tests/test_portfolio.py does.
    monkeypatch.setattr(yf, "download", lambda *a, **k: pd.DataFrame())

    # setdefault, not a plain assignment: this line re-executes on EVERY
    # script rerun (it's part of the persistent script text), so a plain
    # `st.session_state["port_section"] = ...` would silently clobber any
    # in-app navigation (e.g. a "Back to Positions" button click setting it
    # to "overview") back to this initial value on the very next run.
    section_line = (f'st.session_state.setdefault("port_section", {section!r})' if section else "")
    script_src = USER_SETUP_SRC + f"""
import streamlit as st
st.session_state["user_email"] = "test@example.com"
st.session_state["user_role"] = "Analyst"
{section_line}
from uvalu.pages_ import portfolio as portfolio_page
portfolio_page.render()
"""
    at = AppTest.from_string(script_src, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def test_shows_add_prompt_when_portfolio_empty(isolated_data, monkeypatch):
    at = _run(monkeypatch)
    assert "Your portfolio is empty" in "".join(i.value for i in at.info)


def test_overview_shows_kpi_cards_for_populated_portfolio(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    at = _run(monkeypatch)
    html = "".join(m.value for m in at.markdown)
    assert "Invested" in html
    assert "Market value" in html
    assert "AAA.BR" in html


def test_wires_price_autorefresh(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    calls: list[str] = []
    monkeypatch.setattr(portfolio_page, "price_autorefresh", lambda key: calls.append(key))
    _run(monkeypatch)
    assert calls == ["portfolio_refresh"]


def test_overview_shows_no_closed_positions_message(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    at = _run(monkeypatch)
    assert "No closed positions yet" in "".join(c.value for c in at.caption)


def test_overview_shows_closed_position_when_sold_exists(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    portfolio.save_sold(pd.DataFrame([{
        "ticker": "BBB.BR", "name": "Beta Corp", "shares": 5,
        "purchase_value": 500.0, "sale_value": 600.0,
        "date_in": "2023-01-01", "date_out": "2023-06-01",
    }]))
    at = _run(monkeypatch)
    html = "".join(m.value for m in at.markdown)
    assert "BBB.BR" in html


def test_open_positions_full_page(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    at = _run(monkeypatch, section="open")
    html = "".join(m.value for m in at.markdown)
    assert "Open positions" in html
    assert "AAA.BR" in html
    assert any(b.label == "← Back to Positions" for b in at.button)


def test_closed_positions_full_page_empty(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    at = _run(monkeypatch, section="closed")
    assert "No sold positions found" in "".join(i.value for i in at.info)


def test_closed_positions_full_page_with_data(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    portfolio.save_sold(pd.DataFrame([{
        "ticker": "BBB.BR", "name": "Beta Corp", "shares": 5,
        "purchase_value": 500.0, "sale_value": 600.0,
        "date_in": "2023-01-01", "date_out": "2023-06-01",
    }]))
    at = _run(monkeypatch, section="closed")
    html = "".join(m.value for m in at.markdown)
    assert "BBB.BR" in html


def test_dividends_full_page_empty(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    at = _run(monkeypatch, section="dividends")
    assert "Re-upload your Excel file" in "".join(i.value for i in at.info)


def test_dividends_full_page_with_data(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    portfolio.save_div_hist(pd.DataFrame([
        {"ticker": "AAA.BR", "name": "Alpha Corp", "amount": 12.5, "date": "2024-03-01", "shares": 10},
    ]))
    at = _run(monkeypatch, section="dividends")
    html = "".join(m.value for m in at.markdown)
    assert "Alpha Corp" in html


def test_migrates_legacy_portfolio_missing_account_and_purchase_price(isolated_data, monkeypatch):
    # Old portfolio.json files predate the "account"/"purchase_price"
    # columns — render() should backfill both and persist the migration.
    portfolio.save_portfolio(pd.DataFrame([{
        "ticker": "AAA.BR", "name": "Alpha Corp", "shares": 10,
        "purchase_value": 1000.0, "dividends": 0.0, "date_in": "2023-01-01",
    }]))
    _run(monkeypatch)
    migrated = portfolio.load_portfolio().iloc[0]
    assert migrated["account"] == ""
    assert migrated["purchase_price"] == 100.0


def test_drops_rows_with_blank_ticker(isolated_data, monkeypatch):
    portfolio.save_portfolio(pd.DataFrame([
        {"ticker": "AAA.BR", "name": "Alpha Corp", "shares": 10, "purchase_value": 1000.0,
         "purchase_price": 100.0, "dividends": 0.0, "date_in": "2023-01-01", "account": ""},
        {"ticker": "  ", "name": "Ghost", "shares": 1, "purchase_value": 1.0,
         "purchase_price": 1.0, "dividends": 0.0, "date_in": "2023-01-01", "account": ""},
    ]))
    at = _run(monkeypatch)
    html = "".join(m.value for m in at.markdown)
    assert "Ghost" not in html


class TestOverviewSectionNavigation:
    def test_expand_open_positions_navigates(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        at = _run(monkeypatch)
        expand_btn = [b for b in at.button if b.key == "ov_open_expand"][0]
        expand_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert "Open positions" in "".join(m.value for m in at.markdown)

    def test_expand_closed_positions_navigates(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        at = _run(monkeypatch)
        expand_btn = [b for b in at.button if b.key == "ov_closed_expand"][0]
        expand_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        html = "".join(m.value for m in at.markdown)
        assert "realised" in html.lower()

    def test_expand_dividends_navigates(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        at = _run(monkeypatch)
        expand_btn = [b for b in at.button if b.key == "ov_div_expand"][0]
        expand_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert "Dividends received" in "".join(m.value for m in at.markdown)

    def test_back_to_positions_returns_to_overview(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        at = _run(monkeypatch, section="open")
        back_btn = [b for b in at.button if b.label == "← Back to Positions"][0]
        back_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert "Portfolio" in "".join(m.value for m in at.markdown)
        assert at.session_state["port_section"] == "overview"


def test_viewer_role_disables_add_buttons(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    monkeypatch.setattr(portfolio_page, "_load_portfolio_scored", fake_portfolio_scored())
    monkeypatch.setattr(portfolio_page, "_fetch_prices_cached", lambda tickers: {
        t: {"price": 110.0} for t in tickers
    })
    script_src = USER_SETUP_SRC + """
import streamlit as st
st.session_state["user_email"] = "test@example.com"
st.session_state["user_role"] = "Viewer"
from uvalu.pages_ import portfolio as portfolio_page
portfolio_page.render()
"""
    at = AppTest.from_string(script_src, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    add_buttons = [b for b in at.button if b.label == "Add"]
    assert add_buttons
    assert all(b.disabled for b in add_buttons)


# ── Edit open position dialog ────────────────────────────────────────────

class TestEditOpenPositionDialog:
    _EDIT_KEY = "pf_open_row_0_AAA.BR_edit"

    def test_edit_button_opens_dialog_with_prefilled_values(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        at = _run(monkeypatch, section="open")
        edit_btn = [b for b in at.button if b.key == self._EDIT_KEY][0]
        edit_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.number_input(key="dlg_eop_shares").value == 10
        assert at.number_input(key="dlg_eop_invested").value == 1000.0

    def test_save_updates_position(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        at = _run(monkeypatch, section="open")
        edit_btn = [b for b in at.button if b.key == self._EDIT_KEY][0]
        edit_btn.click().run()

        # Re-click the SAME row's edit button in the same staged batch as
        # the dialog's own widgets/Save button — needed so the dialog's
        # gating condition (_res["edit"]) is true again on this next run
        # too, see the module docstring.
        edit_btn = [b for b in at.button if b.key == self._EDIT_KEY][0]
        edit_btn.click()
        at.number_input(key="dlg_eop_shares").set_value(20)
        at.number_input(key="dlg_eop_invested").set_value(2500.0)
        save_btn = [b for b in at.button if b.label == "Save"][0]
        save_btn.click()
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]

        updated = portfolio.load_portfolio().iloc[0]
        assert updated["shares"] == 20
        assert updated["purchase_value"] == 2500.0
        assert updated["purchase_price"] == 125.0

    def test_delete_removes_position(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        at = _run(monkeypatch, section="open")
        edit_btn = [b for b in at.button if b.key == self._EDIT_KEY][0]
        edit_btn.click().run()

        edit_btn = [b for b in at.button if b.key == self._EDIT_KEY][0]
        edit_btn.click()
        delete_btn = [b for b in at.button if b.label == "Delete position"][0]
        delete_btn.click()
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert portfolio.load_portfolio().empty


# ── Edit closed position dialog ──────────────────────────────────────────

class TestEditClosedPositionDialog:
    _EDIT_KEY = "pf_closed_row_0_BBB.BR_edit"

    def _seed(self):
        portfolio.save_portfolio(make_portfolio_df())
        portfolio.save_sold(pd.DataFrame([{
            "ticker": "BBB.BR", "name": "Beta Corp", "shares": 5,
            "purchase_value": 500.0, "sale_value": 600.0,
            "date_in": "2023-01-01", "date_out": "2023-06-01",
        }]))

    def test_save_updates_sold_record(self, isolated_data, monkeypatch):
        self._seed()
        at = _run(monkeypatch, section="closed")
        edit_btn = [b for b in at.button if b.key == self._EDIT_KEY][0]
        edit_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.number_input(key="dlg_ecp_shares").value == 5
        assert at.number_input(key="dlg_ecp_proceeds").value == 600.0

        edit_btn = [b for b in at.button if b.key == self._EDIT_KEY][0]
        edit_btn.click()
        at.number_input(key="dlg_ecp_shares").set_value(8)
        at.number_input(key="dlg_ecp_proceeds").set_value(750.0)
        save_btn = [b for b in at.button if b.label == "Save"][0]
        save_btn.click()
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]

        sold = portfolio.load_sold().iloc[0]
        assert sold["shares"] == 8
        assert sold["sale_value"] == 750.0

    def test_delete_removes_sold_record(self, isolated_data, monkeypatch):
        self._seed()
        at = _run(monkeypatch, section="closed")
        edit_btn = [b for b in at.button if b.key == self._EDIT_KEY][0]
        edit_btn.click().run()

        edit_btn = [b for b in at.button if b.key == self._EDIT_KEY][0]
        edit_btn.click()
        delete_btn = [b for b in at.button if b.label == "Delete trade"][0]
        delete_btn.click()
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert portfolio.load_sold().empty


# ── Edit dividend dialog ──────────────────────────────────────────────────

class TestEditDividendDialog:
    _EDIT_KEY = "pf_div_row_0_edit"

    def _seed(self):
        portfolio.save_portfolio(make_portfolio_df())
        portfolio.save_div_hist(pd.DataFrame([
            {"ticker": "AAA.BR", "name": "Alpha Corp", "amount": 12.5, "date": "2024-03-01", "shares": 10},
        ]))

    def test_save_updates_dividend(self, isolated_data, monkeypatch):
        self._seed()
        at = _run(monkeypatch, section="dividends")
        edit_btn = [b for b in at.button if b.key == self._EDIT_KEY][0]
        edit_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.number_input(key="dlg_ed_shares").value == 10

        edit_btn = [b for b in at.button if b.key == self._EDIT_KEY][0]
        edit_btn.click()
        at.number_input(key="dlg_ed_dps").set_value(2.0)
        save_btn = [b for b in at.button if b.label == "Save"][0]
        save_btn.click()
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]

        div_hist = portfolio.load_div_hist().iloc[0]
        assert div_hist["amount"] == 20.0  # 10 shares * 2.0/share

    def test_delete_removes_dividend(self, isolated_data, monkeypatch):
        self._seed()
        at = _run(monkeypatch, section="dividends")
        edit_btn = [b for b in at.button if b.key == self._EDIT_KEY][0]
        edit_btn.click().run()

        edit_btn = [b for b in at.button if b.key == self._EDIT_KEY][0]
        edit_btn.click()
        delete_btn = [b for b in at.button if b.label == "Delete dividend"][0]
        delete_btn.click()
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert portfolio.load_div_hist().empty


# ── Drawer edit handoff (_pf_edit_ticker) ─────────────────────────────────

class TestDrawerEditHandoff:
    def test_pending_edit_ticker_opens_dialog(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        monkeypatch.setattr(portfolio_page, "_load_portfolio_scored", fake_portfolio_scored())
        monkeypatch.setattr(portfolio_page, "_fetch_prices_cached", lambda tickers: {
            t: {"price": 110.0} for t in tickers
        })
        script_src = USER_SETUP_SRC + """
import streamlit as st
st.session_state["user_email"] = "test@example.com"
st.session_state["user_role"] = "Analyst"
st.session_state["port_section"] = "open"
st.session_state["_pf_edit_ticker"] = "AAA.BR"
from uvalu.pages_ import portfolio as portfolio_page
portfolio_page.render()
"""
        at = AppTest.from_string(script_src, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.number_input(key="dlg_eop_shares").value == 10
        # One-shot: the ticket must not survive the render.
        assert "_pf_edit_ticker" not in at.session_state


class TestValueHistoryDebounce:
    """PR4: the value-history backfill + daily snapshot must not ride along on
    every 60s timed price refresh (uvalu/ui.py's price_autorefresh), and on a
    genuine render the snapshot is throttled to ~once per 10 min."""

    _SRC_HEAD = USER_SETUP_SRC + """
import streamlit as st
st.session_state["user_email"] = "test@example.com"
st.session_state["user_role"] = "Analyst"
"""
    _SRC_TAIL = """
from uvalu.pages_ import portfolio as portfolio_page
portfolio_page.render()
"""

    def _patch(self, monkeypatch, snap, backfill):
        monkeypatch.setattr(portfolio_page, "_load_portfolio_scored", fake_portfolio_scored())
        monkeypatch.setattr(portfolio_page, "_fetch_prices_cached",
                            lambda tickers: {t: {"price": 110.0} for t in tickers})
        monkeypatch.setattr(portfolio_page, "record_value_snapshot", lambda *a: snap.append(a))
        monkeypatch.setattr(portfolio_page, "backfill_value_history", lambda *a: backfill.append(a))

    def test_timed_refresh_skips_snapshot_and_backfill(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        snap, backfill = [], []
        self._patch(monkeypatch, snap, backfill)
        src = self._SRC_HEAD + 'st.session_state["_tick_portfolio_refresh"] = True\n' + self._SRC_TAIL
        at = AppTest.from_string(src, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert snap == []
        assert backfill == []

    def test_genuine_render_snapshots_once_then_throttles(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        snap, backfill = [], []
        self._patch(monkeypatch, snap, backfill)
        at = AppTest.from_string(self._SRC_HEAD + self._SRC_TAIL, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert len(snap) == 1          # first genuine render records
        assert len(backfill) == 1      # no history yet → backfill runs once
        at.run()                       # immediate re-render, inside the 10-min guard
        assert not at.exception, [str(e.value) for e in at.exception]
        assert len(snap) == 1          # throttled — not called again
