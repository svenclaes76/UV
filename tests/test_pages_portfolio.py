"""AppTest coverage for uvalu/pages_/portfolio.py.

The per-row Edit dialogs (uvalu/dialogs.py's edit_position_dialog /
edit_closed_trade_dialog / edit_dividend_dialog) are each only invoked via a
one-shot trigger (a specific row's edit-pencil button being clicked on THAT
run, or a popped session_state ticket). Per tests/test_pages_admin.py's finding, such
one-shot-gated dialogs do NOT persist across separate AppTest.run() calls
the way unconditionally-invoked ones do — so testing a full open-dialog
Save/Delete flow means RE-CLICKING the same triggering row's edit button
in the SAME staged batch as the dialog's own Save/Delete button before
each .run(), keeping the trigger condition true on every run that needs
the dialog's body to actually execute.
"""
import pandas as pd
from streamlit.testing.v1 import AppTest

import portfolio
from uvalu.pages_ import portfolio as portfolio_page
from tests.conftest import (make_portfolio_df, fake_portfolio_scored, USER_SETUP_SRC,
                            portfolio_page_src)


def _run(monkeypatch, section=None) -> AppTest:
    monkeypatch.setattr(portfolio_page, "_load_portfolio_scored", fake_portfolio_scored())
    monkeypatch.setattr(portfolio_page, "_fetch_prices_cached", lambda tickers: {
        t: {"price": 110.0} for t in tickers
    })
    # A populated portfolio with no/stale value history would otherwise spawn
    # a real background ensure_value_history_fresh() -> backfill_value_history()
    # -> yf.download() thread. It's non-blocking so it wouldn't fail/slow this
    # test directly, but a stray daemon thread outliving this test's tmp_path
    # and monkeypatches (torn down as soon as the test function returns) is
    # exactly the kind of cross-test leak isolated_data exists to prevent —
    # stub the whole call out, like tests/test_pages_dashboard.py does.
    monkeypatch.setattr(portfolio_page, "ensure_value_history_fresh", lambda *a: False)
    # The Dividend log auto-imports from market data (yfinance) once per
    # session — stub it so no test hits the network.
    monkeypatch.setattr(portfolio_page, "import_dividends_from_market_data", lambda *a, **k: 0)

    script_src = portfolio_page_src(section)
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
    assert "No closed positions yet" in "".join(i.value for i in at.info)


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
    assert "No dividend events yet" in "".join(i.value for i in at.info)


def test_dividends_full_page_with_data(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    portfolio.save_div_hist(pd.DataFrame([
        {"ticker": "AAA.BR", "name": "Alpha Corp", "amount": 12.5, "date": "2024-03-01", "shares": 10},
    ]))
    at = _run(monkeypatch, section="dividends")
    html = "".join(m.value for m in at.markdown)
    assert "Alpha Corp" in html


def test_dividend_log_layout_matches_design(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    portfolio.set_dividend_meta("AAA.BR", frequency="Annual")
    portfolio.save_div_hist(pd.DataFrame([
        {"ticker": "AAA.BR", "name": "Alpha Corp", "amount": 12.5, "date": "2024-03-01", "shares": 10,
         "declaration_date": "2024-01-10", "record_date": "2024-02-28"},
    ]))
    at = _run(monkeypatch, section="dividends")
    labels = [b.label for b in at.button]
    assert "Import from market data" not in labels
    exports = [b for b in at.get("download_button") if b.proto.label == "Export"]
    assert len(exports) == 2  # header (log) + annual summary card
    html = "".join(m.value for m in at.markdown)
    assert "decl " not in html and "rec " not in html
    assert "Alpha Corp · Annual" not in html
    assert "Withholding by domicile" not in html
    assert "Annual dividend income summary" in html


def test_dividends_page_auto_imports_once_per_session(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    calls = []
    at = _run(monkeypatch, section="dividends")
    monkeypatch.setattr(portfolio_page, "import_dividends_from_market_data",
                        lambda *a, **k: calls.append(1) or 0)
    at.run()
    assert calls == []  # already ran on the first render of this session


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
    add_buttons = [b for b in at.button if b.label == "Add position"]
    assert add_buttons
    assert all(b.disabled for b in add_buttons)


def _redraw(at, edit_key: str) -> None:
    """The dialog's own fragment rerun (showing the new state at once) is a
    no-op under AppTest (dialog_fragment_runs) — one more run shows it."""
    [b for b in at.button if b.key == edit_key][0].click()
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]


def _confirm_delete(at, edit_key: str) -> None:
    """Delete → confirmation → Delete permanently, re-clicking the row's
    pencil each run to keep the one-shot dialog open (module docstring)."""
    [b for b in at.button if b.key == edit_key][0].click()
    [b for b in at.button if b.label == "Delete"][0].click()
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    _redraw(at, edit_key)
    assert any(b.label == "Delete permanently" for b in at.button)
    [b for b in at.button if b.key == edit_key][0].click()
    [b for b in at.button if b.label == "Delete permanently"][0].click()
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]


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
        tick = at.text_input(key="dlg_eop_id_ticker")
        assert tick.value == "AAA.BR" and tick.disabled

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

    def test_delete_removes_position(self, isolated_data, monkeypatch, dialog_fragment_runs):
        portfolio.save_portfolio(make_portfolio_df())
        at = _run(monkeypatch, section="open")
        edit_btn = [b for b in at.button if b.key == self._EDIT_KEY][0]
        edit_btn.click().run()

        _confirm_delete(at, self._EDIT_KEY)
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
        assert at.number_input(key="dlg_ecp_buy").value == 100.0
        assert at.number_input(key="dlg_ecp_sell").value == 120.0

        edit_btn = [b for b in at.button if b.key == self._EDIT_KEY][0]
        edit_btn.click()
        at.number_input(key="dlg_ecp_shares").set_value(8)
        at.number_input(key="dlg_ecp_sell").set_value(125.0)
        save_btn = [b for b in at.button if b.label == "Save"][0]
        save_btn.click()
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]

        sold = portfolio.load_sold().iloc[0]
        assert sold["shares"] == 8
        assert sold["sale_value"] == 1000.0
        # The cost basis follows the share count (it used to stay at 5
        # shares' worth, which silently raised the buy price and the P&L).
        assert sold["purchase_value"] == 800.0

    def test_untouched_save_keeps_exact_totals(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        portfolio.save_sold(pd.DataFrame([{
            "ticker": "BBB.BR", "name": "Beta Corp", "shares": 3,
            "purchase_value": 100.0, "sale_value": 200.0,
            "date_in": "2023-01-01", "date_out": "2023-06-01",
        }]))
        at = _run(monkeypatch, section="closed")
        [b for b in at.button if b.key == self._EDIT_KEY][0].click().run()
        [b for b in at.button if b.key == self._EDIT_KEY][0].click()
        [b for b in at.button if b.label == "Save"][0].click()
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        sold = portfolio.load_sold().iloc[0]
        assert (sold["purchase_value"], sold["sale_value"]) == (100.0, 200.0)

    def test_delete_removes_sold_record(self, isolated_data, monkeypatch, dialog_fragment_runs):
        self._seed()
        at = _run(monkeypatch, section="closed")
        edit_btn = [b for b in at.button if b.key == self._EDIT_KEY][0]
        edit_btn.click().run()

        _confirm_delete(at, self._EDIT_KEY)
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

    def test_dialog_has_no_declaration_record_or_frequency_fields(self, isolated_data, monkeypatch):
        self._seed()
        at = _run(monkeypatch, section="dividends")
        [b for b in at.button if b.key == self._EDIT_KEY][0].click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert {w.key for w in at.date_input} == {"dlg_ed_ex", "dlg_ed_date"}
        assert not [s for s in at.selectbox if s.key == "dlg_ed_freq"]
        # Missing currency (NaN) must not leak into the label as "(nan)".
        assert at.number_input(key="dlg_ed_dps").label == "Per share (EUR) *"

    def test_identity_row_is_first_and_locked(self, isolated_data, monkeypatch):
        self._seed()
        at = _run(monkeypatch, section="dividends")
        [b for b in at.button if b.key == self._EDIT_KEY][0].click().run()
        tick = at.text_input(key="dlg_ed_id_ticker")
        name = at.text_input(key="dlg_ed_id_name")
        assert (tick.value, name.value) == ("AAA.BR", "Alpha Corp")
        assert tick.disabled and name.disabled
        assert [b.label for b in at.button if b.key and b.key.startswith("dlg_ed_")] == ["Delete", "Cancel", "Save"]

    def test_missing_withholding_rate_is_zero_not_nan(self, isolated_data, monkeypatch):
        # _seed()'s record has no tax_rate at all (NaN after load): the field
        # must show 0 and the preview must never render "nan".
        self._seed()
        at = _run(monkeypatch, section="dividends")
        [b for b in at.button if b.key == self._EDIT_KEY][0].click().run()
        assert at.number_input(key="dlg_ed_tax").value == 0.0
        assert "nan" not in "".join(m.value for m in at.markdown)

    def test_save_keeps_existing_declaration_and_record_dates(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        portfolio.save_div_hist(pd.DataFrame([
            {"ticker": "AAA.BR", "name": "Alpha Corp", "amount": 12.5, "date": "2024-03-01", "shares": 10,
             "declaration_date": "2024-01-10", "record_date": "2024-02-28"},
        ]))
        at = _run(monkeypatch, section="dividends")
        [b for b in at.button if b.key == self._EDIT_KEY][0].click().run()
        [b for b in at.button if b.key == self._EDIT_KEY][0].click()
        at.number_input(key="dlg_ed_dps").set_value(2.0)
        [b for b in at.button if b.label == "Save"][0].click()
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        row = portfolio.load_div_hist().iloc[0]
        assert row["amount"] == 20.0
        assert str(row["declaration_date"]).startswith("2024-01-10")
        assert str(row["record_date"]).startswith("2024-02-28")

    def test_delete_removes_dividend(self, isolated_data, monkeypatch, dialog_fragment_runs):
        self._seed()
        at = _run(monkeypatch, section="dividends")
        edit_btn = [b for b in at.button if b.key == self._EDIT_KEY][0]
        edit_btn.click().run()

        _confirm_delete(at, self._EDIT_KEY)
        assert portfolio.load_div_hist().empty

    def test_editing_a_future_dated_record_does_not_crash(self, isolated_data, monkeypatch):
        """A record dated ahead of today (entered before dates were capped,
        or imported) must stay editable — st.date_input raises if its
        current `value` falls outside `min_value`/`max_value`, so the
        dialog's max_value can't be a flat `today` when the row's own date
        is already later than that."""
        portfolio.save_portfolio(make_portfolio_df())
        portfolio.save_div_hist(pd.DataFrame([
            {"ticker": "AAA.BR", "name": "Alpha Corp", "amount": 12.5,
             "date": "2099-01-15", "shares": 10},
        ]))
        at = _run(monkeypatch, section="dividends")
        edit_btn = [b for b in at.button if b.key == self._EDIT_KEY][0]
        edit_btn.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]


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
        monkeypatch.setattr(portfolio_page, "ensure_value_history_fresh",
                            lambda *a: backfill.append(a) or False)

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


# ── Section reset on arrival ──────────────────────────────────────────────

class TestSectionResetOnArrival:
    """Arriving at Portfolio from another page lands on the Overview, not on
    whichever sub-page the user left from; hand-offs and in-page reruns keep
    the sub-page."""

    def _at(self, monkeypatch, prelude: str) -> AppTest:
        monkeypatch.setattr(portfolio_page, "_load_portfolio_scored", fake_portfolio_scored())
        monkeypatch.setattr(portfolio_page, "_fetch_prices_cached", lambda t: {x: {"price": 110.0} for x in t})
        monkeypatch.setattr(portfolio_page, "ensure_value_history_fresh", lambda *a: False)
        monkeypatch.setattr(portfolio_page, "import_dividends_from_market_data", lambda *a, **k: 0)
        at = AppTest.from_string(USER_SETUP_SRC + f"""
import streamlit as st
st.session_state["user_role"] = "Analyst"
{prelude}
from uvalu.pages_ import portfolio as portfolio_page
try:
    portfolio_page.render()
finally:
    st.session_state["_uv_render_page"] = "portfolio"
""", default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        return at

    def test_coming_back_from_another_page_shows_overview(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        at = self._at(monkeypatch, 'st.session_state.setdefault("port_section", "cash")\n'
                                   'st.session_state["_uv_render_page"] = "screener"')
        assert at.session_state["port_section"] == "overview"

    def test_rerun_within_portfolio_keeps_the_sub_page(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        at = self._at(monkeypatch, 'st.session_state.setdefault("port_section", "cash")\n'
                                   'st.session_state.setdefault("_uv_render_page", "portfolio")')
        assert at.session_state["port_section"] == "cash"
        at.run()
        assert at.session_state["port_section"] == "cash"

    def test_hand_off_from_another_page_is_honoured_once(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        at = self._at(monkeypatch, 'if "port_section" not in st.session_state:\n'
                                   '    st.session_state["port_section"] = "cash"\n'
                                   '    st.session_state["_pf_section_handoff"] = True\n'
                                   '    st.session_state["_uv_render_page"] = "risk"')
        assert at.session_state["port_section"] == "cash"
        assert "_pf_section_handoff" not in at.session_state


# ── Id migration + no derived columns on disk ─────────────────────────────

def test_render_backfills_trade_ids_and_strips_live_columns(isolated_data, monkeypatch):
    df = make_portfolio_df()
    df["live_price"] = 99.0          # written by the pre-fix Edit position dialog
    df["current_value"] = 990.0
    portfolio.save_portfolio(df)
    portfolio.save_sold(pd.DataFrame([{"ticker": "BBB.BR", "name": "Beta", "shares": 1,
                                       "purchase_value": 1.0, "sale_value": 2.0,
                                       "date_in": "2023-01-01", "date_out": "2023-02-01"}]))
    _run(monkeypatch)
    pf = portfolio.load_portfolio()
    assert "live_price" not in pf.columns and "current_value" not in pf.columns
    assert str(pf.iloc[0]["trade_id"]).startswith("TRD-")
    assert str(portfolio.load_sold().iloc[0]["trade_id"]).startswith("TRD-")


# ── Edit position ↔ linked cash entry ─────────────────────────────────────

class TestEditPositionCash:
    _EDIT_KEY = "pf_open_row_0_AAA.BR_edit"

    def _buy(self):
        import cash
        cash.post_manual("Deposit", "2023-01-01", 5000)
        portfolio.record_buy({"ticker": "AAA.BR", "name": "Alpha Corp", "shares": 10,
                              "purchase_price": 100.0, "purchase_value": 1000.0, "dividends": 0.0,
                              "date_in": "2023-01-02", "account": ""}, fee=5.0)

    def test_save_can_repost_the_buy(self, isolated_data, monkeypatch):
        import cash
        self._buy()
        at = _run(monkeypatch, section="open")
        [b for b in at.button if b.key == self._EDIT_KEY][0].click().run()
        assert at.checkbox(key="dlg_eop_sync").value is True
        [b for b in at.button if b.key == self._EDIT_KEY][0].click()
        at.number_input(key="dlg_eop_invested").set_value(1200.0)
        [b for b in at.button if b.label == "Save"][0].click()
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert portfolio.load_portfolio().iloc[0]["purchase_value"] == 1200.0
        assert cash.balance() == 5000 - 1205

    def test_save_without_sync_leaves_cash(self, isolated_data, monkeypatch):
        import cash
        self._buy()
        at = _run(monkeypatch, section="open")
        [b for b in at.button if b.key == self._EDIT_KEY][0].click().run()
        [b for b in at.button if b.key == self._EDIT_KEY][0].click()
        at.checkbox(key="dlg_eop_sync").uncheck()
        at.number_input(key="dlg_eop_invested").set_value(1200.0)
        [b for b in at.button if b.label == "Save"][0].click()
        at.run()
        assert cash.balance() == 5000 - 1005

    def test_delete_can_remove_its_cash(self, isolated_data, monkeypatch, dialog_fragment_runs):
        import cash
        self._buy()
        at = _run(monkeypatch, section="open")
        [b for b in at.button if b.key == self._EDIT_KEY][0].click().run()
        [b for b in at.button if b.key == self._EDIT_KEY][0].click()
        [b for b in at.button if b.label == "Delete"][0].click()
        at.run()
        _redraw(at, self._EDIT_KEY)
        assert at.checkbox(key="dlg_eop_rm_cash").value is True
        [b for b in at.button if b.key == self._EDIT_KEY][0].click()
        [b for b in at.button if b.label == "Delete permanently"][0].click()
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert portfolio.load_portfolio().empty
        assert cash.balance() == 5000

    def test_keep_cancels_the_confirmation(self, isolated_data, monkeypatch, dialog_fragment_runs):
        self._buy()
        at = _run(monkeypatch, section="open")
        [b for b in at.button if b.key == self._EDIT_KEY][0].click().run()
        [b for b in at.button if b.key == self._EDIT_KEY][0].click()
        [b for b in at.button if b.label == "Delete"][0].click()
        at.run()
        _redraw(at, self._EDIT_KEY)
        [b for b in at.button if b.key == self._EDIT_KEY][0].click()
        [b for b in at.button if b.label == "Keep"][0].click()
        at.run()
        _redraw(at, self._EDIT_KEY)
        assert not at.exception, [str(e.value) for e in at.exception]
        assert len(portfolio.load_portfolio()) == 1
        assert any(b.label == "Delete" for b in at.button)

    def test_partly_sold_lot_offers_no_cash_sync(self, isolated_data, monkeypatch):
        self._buy()
        portfolio.record_sell("AAA.BR", 4, 110.0, 0.0, "2023-06-01")
        at = _run(monkeypatch, section="open")
        [b for b in at.button if b.key == self._EDIT_KEY][0].click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert not [c for c in at.checkbox if c.key == "dlg_eop_sync"]
        assert any("keeps this buy as recorded" in c.value for c in at.caption)



class TestAlignedDialogs:
    def test_trade_dialog_shows_result_box(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        portfolio.save_sold(pd.DataFrame([{"ticker": "BBB.BR", "name": "Beta Corp", "shares": 5,
                                           "purchase_value": 500.0, "sale_value": 600.0,
                                           "date_in": "2023-01-01", "date_out": "2023-06-01"}]))
        at = _run(monkeypatch, section="closed")
        assert any(b.label == "Add trade" for b in at.button)
        [b for b in at.button if b.key == "pf_closed_row_0_BBB.BR_edit"][0].click().run()
        html = "".join(m.value for m in at.markdown)
        assert "Realised P&amp;L" in html or "Realised P&L" in html
        assert "+€100.00 · +20.0%" in html

    def test_edit_position_price_per_share_sets_total(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        key = "pf_open_row_0_AAA.BR_edit"
        at = _run(monkeypatch, section="open")
        [b for b in at.button if b.key == key][0].click().run()
        assert at.number_input(key="dlg_eop_price").value == 100.0
        assert "no cash change" in "".join(m.value for m in at.markdown)
        [b for b in at.button if b.key == key][0].click()
        at.number_input(key="dlg_eop_price").set_value(120.0)
        [b for b in at.button if b.label == "Save"][0].click()
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert portfolio.load_portfolio().iloc[0]["purchase_value"] == 1200.0

    def test_edit_position_cash_box_previews_the_repost(self, isolated_data, monkeypatch):
        import cash
        cash.post_manual("Deposit", "2023-01-01", 5000)
        portfolio.record_buy({"ticker": "AAA.BR", "name": "Alpha Corp", "shares": 10, "purchase_price": 100.0,
                              "purchase_value": 1000.0, "dividends": 0.0, "date_in": "2023-01-02",
                              "account": ""})
        key = "pf_open_row_0_AAA.BR_edit"
        at = _run(monkeypatch, section="open")
        [b for b in at.button if b.key == key][0].click().run()
        [b for b in at.button if b.key == key][0].click()
        at.number_input(key="dlg_eop_invested").set_value(1200.0)
        at.run()
        html = "".join(m.value for m in at.markdown)
        assert "−€200.00" in html and "€3,800.00" in html

    def test_edit_dividend_cash_link_line(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        portfolio.save_div_hist(pd.DataFrame([
            {"ticker": "AAA.BR", "name": "Alpha Corp", "amount": 10.0, "date": "2024-03-01", "shares": 10,
             "ex_date": "2024-02-20", "currency": "EUR"}]))
        at = _run(monkeypatch, section="dividends")
        [b for b in at.button if b.key == "pf_div_row_0_edit"][0].click().run()
        assert any("Cash entry follows automatically (net EUR 7.00)" in c.value for c in at.caption)
