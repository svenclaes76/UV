"""AppTest coverage for Cash Management v1's UI: the Portfolio cash strip,
the Cash activity full page (uvalu/pages_/cash.py, routed from
uvalu/pages_/portfolio.py), the Add cash transaction dialog, the Buy/Sell
dialogs' fee + "Cash after trade" row, the Dashboard Cash tile and the Risk
page's "invested portion only" banner."""
from datetime import date

import pandas as pd
import yfinance as yf
from streamlit.testing.v1 import AppTest

import cash
import fx
import portfolio
from uvalu.pages_ import portfolio as portfolio_page
from tests.conftest import make_portfolio_df, fake_portfolio_scored, USER_SETUP_SRC, portfolio_page_src

D = date(2026, 3, 2)


def _run_portfolio(monkeypatch, section=None, role="Analyst") -> AppTest:
    monkeypatch.setattr(portfolio_page, "_load_portfolio_scored", fake_portfolio_scored())
    monkeypatch.setattr(portfolio_page, "_fetch_prices_cached", lambda tickers: {
        t: {"price": 110.0} for t in tickers})
    monkeypatch.setattr(portfolio_page, "ensure_value_history_fresh", lambda *a: False)
    monkeypatch.setattr(portfolio_page, "import_dividends_from_market_data", lambda *a, **k: 0)
    at = AppTest.from_string(portfolio_page_src(section, role), default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def _html(at) -> str:
    return "".join(m.value for m in at.markdown)


# ── Portfolio overview strip ─────────────────────────────────────────────────

class TestCashStrip:
    def test_strip_shows_balance_and_split(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())          # 10 × €110 = €1,100 invested
        cash.post_manual("Deposit", D, 900)
        at = _run_portfolio(monkeypatch)
        html = _html(at)
        assert "Cash balance" in html and "EUR base" in html
        assert "€900.00" in html
        assert "45.0%" in html and "55.0%" in html              # cash / invested
        assert "Total portfolio value €2,000" in html
        assert {"ov_cash_deposit", "ov_cash_withdraw"} <= {b.key for b in at.button}

    def test_empty_ledger_hint(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        at = _run_portfolio(monkeypatch)
        assert "No entries yet · buys top up automatically" in _html(at)

    def test_viewer_sees_deposit_withdraw_disabled(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        at = _run_portfolio(monkeypatch, role="Viewer")
        btns = [b for b in at.button if b.key in ("ov_cash_deposit", "ov_cash_withdraw")]
        assert len(btns) == 2 and all(b.disabled for b in btns)

    def test_expand_opens_cash_page(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        at = _run_portfolio(monkeypatch)
        [b for b in at.button if b.key == "ov_cash_expand"][0].click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.session_state["port_section"] == "cash"
        assert "Cash activity" in _html(at)

    def test_strip_shown_for_empty_portfolio(self, isolated_data, monkeypatch):
        at = _run_portfolio(monkeypatch)
        assert "Cash balance" in _html(at)

    def test_reconcile_runs_once_per_session(self, isolated_data, monkeypatch):
        calls = []
        monkeypatch.setattr(cash, "reconcile_dividend_postings", lambda *a, **k: calls.append(1) or 0)
        portfolio.save_portfolio(make_portfolio_df())
        at = _run_portfolio(monkeypatch)
        at.run()
        assert len(calls) == 1


# ── Cash activity page ───────────────────────────────────────────────────────

class TestCashPage:
    def _seed(self):
        cash.post_adjustment(D, 1000, "Opening balance")
        cash.post_manual("Withdrawal", "2026-03-05", 200, note="To savings")
        cash.post_manual("Deposit", "2026-03-06", 100, "USD", manual_rate=0.85)
        cash.post_trade("Buy", trade_id="TRD-0001", ticker="AAA.BR", shares=10, gross=2000,
                        on="2026-03-10")

    def test_tiles_table_and_export(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        self._seed()
        at = _run_portfolio(monkeypatch, section="cash")
        html = _html(at)
        assert "Net deposits" in html and "Trade flow" in html
        # ledger rows: newest first, top-up labelled, manual FX flagged
        assert html.index("TRD-0001 · AAA.BR") < html.index("To savings")
        assert "top-up" in html and "manual" in html and "set to €1,000.00" in html
        assert "5 of 5 entries" in html
        assert any(b.label == "Export" for b in at.get("download_button"))
        assert any(b.key == "btn_add_cash" and not b.disabled for b in at.button)
        # one pencil per row: manual entries edit, automatic ones open the linked view
        pencils = {b.key: b.help for b in at.button if b.key and b.key.startswith("pf_cash_row_")}
        assert len(pencils) == 5
        assert sorted(pencils.values()).count("View linked entry") == 2   # buy + its top-up

    def test_filter_pills(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        self._seed()
        at = _run_portfolio(monkeypatch, section="cash")
        at.button_group(key="cash_filter").set_value("Trades").run()
        assert not at.exception, [str(e.value) for e in at.exception]
        html = _html(at)
        assert "1 of 5 entries" in html and "To savings" not in html

    def test_viewer_is_read_only_but_can_export(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        self._seed()
        at = _run_portfolio(monkeypatch, section="cash", role="Viewer")
        assert all(b.disabled for b in at.button if b.key == "btn_add_cash" or
                   (b.key or "").startswith("pf_cash_row_"))
        assert any(b.label == "Export" for b in at.get("download_button"))

    def test_empty_ledger_message(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        at = _run_portfolio(monkeypatch, section="cash")
        assert any("No cash entries yet" in i.value for i in at.info)

    def test_deep_link_query_param(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        monkeypatch.setattr(portfolio_page, "_load_portfolio_scored", fake_portfolio_scored())
        monkeypatch.setattr(portfolio_page, "_fetch_prices_cached", lambda t: {x: {"price": 1.0} for x in t})
        monkeypatch.setattr(portfolio_page, "ensure_value_history_fresh", lambda *a: False)
        at = AppTest.from_string(USER_SETUP_SRC + """
import streamlit as st
st.session_state["user_email"] = "test@example.com"
st.session_state["user_role"] = "Analyst"
from uvalu.pages_ import portfolio as portfolio_page
portfolio_page.render()
""", default_timeout=60)
        at.query_params["section"] = "cash"
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.session_state["port_section"] == "cash"


# ── Add cash transaction dialog ──────────────────────────────────────────────

def _run_dialog(preset="Deposit", role="Analyst") -> AppTest:
    at = AppTest.from_string(USER_SETUP_SRC + f"""
import streamlit as st
st.session_state["user_role"] = {role!r}
from uvalu.dialogs import cash_transaction_dialog
cash_transaction_dialog({preset!r})
""", default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def _save(at, label):
    [b for b in at.button if b.label == label][0].click().run()
    assert not at.exception, [str(e.value) for e in at.exception]


class TestCashDialog:
    def test_deposit_in_base_currency(self, isolated_data):
        at = _run_dialog()
        at.number_input(key="dlg_cash_amt").set_value(2500.0)
        at.text_input(key="dlg_cash_note").set_value("Monthly savings plan")
        at.run()
        assert "+€2,500.00" in _html(at)
        _save(at, "Save")
        e = cash.load_ledger()[0]
        assert (e["type"], e["amount"], e["note"]) == ("Deposit", 2500.0, "Monthly savings plan")

    def test_withdrawal_preset_and_block(self, isolated_data):
        cash.post_manual("Deposit", date.today(), 100)
        at = _run_dialog("Withdrawal")
        at.number_input(key="dlg_cash_amt").set_value(150.0)
        at.run()
        assert "· blocked" in _html(at)
        _save(at, "Save")
        assert any("Balance cannot go negative" in x.value for x in at.error)
        assert len(cash.load_ledger()) == 1

    def test_foreign_currency_uses_ecb_rate(self, isolated_data, monkeypatch):
        monkeypatch.setattr(fx, "get_rate", lambda c, b="EUR", on=None: fx.FxQuote(0.85, date(2026, 3, 2), "ecb"))
        at = _run_dialog()
        at.selectbox(key="dlg_cash_ccy").set_value("USD")
        at.number_input(key="dlg_cash_amt").set_value(1000.0)
        at.run()
        html = _html(at)
        assert "1 USD = €0.8500" in html and "frankfurter.dev" in html and "+€850.00" in html
        _save(at, "Save")
        e = cash.load_ledger()[0]
        assert (e["currency"], e["fx_rate"], e["fx_source"], e["amount_base"]) == ("USD", 0.85, "ecb", 850.0)

    def test_outage_forces_manual_flagged_rate(self, isolated_data):
        at = _run_dialog()                                    # conftest: frankfurter is "down"
        at.selectbox(key="dlg_cash_ccy").set_value("GBP")
        at.number_input(key="dlg_cash_amt").set_value(100.0)
        at.run()
        assert "frankfurter.dev is unreachable" in _html(at)
        _save(at, "Save")
        assert any("Enter the FX rate to convert GBP to EUR." in x.value for x in at.error)
        at.number_input(key="dlg_cash_rate").set_value(1.16)
        _save(at, "Save")
        e = cash.load_ledger()[0]
        assert (e["fx_source"], e["amount_base"]) == ("manual", 116.0)

    def test_adjustment_sets_balance(self, isolated_data):
        cash.post_manual("Deposit", D, 1000)
        at = _run_dialog("Adjustment")
        at.number_input(key="dlg_cash_target").set_value(987.6)
        at.run()
        assert "−€12.40" in _html(at)
        _save(at, "Save")
        assert cash.balance() == 987.6

    def test_viewer_cannot_post(self, isolated_data):
        at = _run_dialog(role="Viewer")
        assert not [b for b in at.button if b.label == "Save"]
        assert any("Viewer role is read-only" in c.value for c in at.caption)


# ── Edit cash transaction / linked entry dialogs ─────────────────────────────

def _run_edit(entry_id: str) -> AppTest:
    at = AppTest.from_string(USER_SETUP_SRC + f"""
import streamlit as st
st.session_state["user_role"] = "Analyst"
from uvalu.dialogs import edit_cash_dialog
edit_cash_dialog({entry_id!r})
""", default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


class TestEditCashDialog:
    def test_prefilled_and_saves_in_place(self, isolated_data):
        e = cash.post_manual("Deposit", D, 500, note="Savings")
        at = _run_edit(e["id"])
        assert at.number_input(key="dlg_cash_amt").value == 500.0
        assert at.text_input(key="dlg_cash_note").value == "Savings"
        assert at.selectbox(key="dlg_cash_type").disabled
        at.number_input(key="dlg_cash_amt").set_value(750.0)
        at.run()
        assert "+€250.00" in _html(at)          # the change
        _save(at, "Save")
        led = cash.load_ledger()
        assert len(led) == 1 and led[0]["id"] == e["id"] and led[0]["amount_base"] == 750.0

    def test_lowering_a_deposit_below_spent_cash_is_blocked(self, isolated_data):
        e = cash.post_manual("Deposit", D, 500)
        cash.post_manual("Withdrawal", "2026-03-05", 400)
        at = _run_edit(e["id"])
        at.number_input(key="dlg_cash_amt").set_value(300.0)
        at.run()
        assert "· blocked" in _html(at)
        _save(at, "Save")
        assert any("Balance cannot go negative" in x.value for x in at.error)
        assert cash.balance() == 100.0

    def test_foreign_entry_keeps_its_stored_rate(self, isolated_data):
        e = cash.post_manual("Deposit", D, 100, "USD", manual_rate=0.9)
        at = _run_edit(e["id"])
        assert at.number_input(key="dlg_cash_rate").value == 0.9      # manual panel, prefilled
        at.number_input(key="dlg_cash_amt").set_value(200.0)
        _save(at, "Save")
        led = cash.load_ledger()[0]
        assert (led["fx_rate"], led["fx_source"], led["amount_base"]) == (0.9, "manual", 180.0)

    def test_delete_asks_for_confirmation(self, isolated_data, dialog_fragment_runs):
        cash.post_manual("Deposit", D, 500)
        e = cash.post_manual("Interest", "2026-03-04", 3)
        at = _run_edit(e["id"])
        _save(at, "Delete")
        at.run()                                  # the dialog's fragment rerun (no-op under AppTest)
        assert "Balance after: €500.00" in _html(at)
        _save(at, "Delete permanently")
        assert [x["type"] for x in cash.load_ledger()] == ["Deposit"]

    def test_automatic_entries_are_refused(self, isolated_data):
        posted = cash.post_trade("Buy", trade_id="TRD-0001", ticker="AAA.BR", shares=1, gross=10, on=D)
        at = _run_edit(posted[-1]["id"])
        assert any("Automatic entries" in x.value for x in at.error)


class TestLinkedCashDialog:
    def test_shows_source_and_jumps_there(self, isolated_data):
        posted = cash.post_trade("Sell", trade_id="TRD-0009", ticker="AAA.BR", shares=2, gross=50, on=D)
        at = AppTest.from_string(USER_SETUP_SRC + f"""
from uvalu.dialogs import linked_cash_dialog
linked_cash_dialog({posted[-1]["id"]!r})
""", default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        html = _html(at)
        assert "TRD-0009 · AAA.BR" in html and "+€50.00" in html
        _save(at, "Open closed positions")
        assert at.session_state["port_section"] == "closed"


def test_ledger_shows_50_rows_then_more(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    for i in range(60):
        cash.post_manual("Deposit", D, 1 + i)
    at = _run_portfolio(monkeypatch, section="cash")
    rows = [b for b in at.button if (b.key or "").startswith("pf_cash_row_")]
    assert len(rows) == 50
    [b for b in at.button if b.key == "cash_show_more"][0].click().run()
    assert len([b for b in at.button if (b.key or "").startswith("pf_cash_row_")]) == 60


# ── Buy / Sell dialogs ───────────────────────────────────────────────────────

class TestTradeDialogs:
    def test_buy_shows_top_up_and_posts_it(self, isolated_data, monkeypatch):
        monkeypatch.setattr(yf, "Ticker", lambda sym: type(
            "T", (), {"info": {"regularMarketPrice": 50.0, "shortName": "Alpha"}})())
        cash.post_manual("Deposit", date.today(), 400)
        at = AppTest.from_string(USER_SETUP_SRC + """
from uvalu.dialogs import add_position_dialog
add_position_dialog(preset_ticker="AAA.BR")
""", default_timeout=60)
        at.run()
        at.number_input(key="dlg_ap_shares").set_value(10)
        at.number_input(key="dlg_ap_cost").set_value(500.0)
        at.number_input(key="dlg_ap_fee").set_value(9.9)
        at.run()
        html = _html(at)
        assert "Cash after trade" in html and "Auto top-up from outside cash" in html and "+€109.90" in html
        _save(at, "Save")
        led = cash.replay(cash.load_ledger())
        assert [r["type"] for r in led] == ["Deposit", "Deposit", "Buy"]
        assert led[1]["topup"] and led[-1]["bal"] == 0.0
        assert portfolio.load_portfolio().iloc[0]["trade_id"] == led[-1]["ref_id"]

    def test_sell_with_fee_posts_net_proceeds(self, isolated_data):
        portfolio.save_portfolio(pd.DataFrame([{
            "ticker": "AAA.BR", "name": "Alpha Corp", "shares": 10, "live_price": 100.0,
            "purchase_value": 800.0, "dividends": 0.0, "date_in": "2023-01-01"}]))
        at = AppTest.from_string(USER_SETUP_SRC + """
from portfolio import load_portfolio
from uvalu.dialogs import sell_position_dialog
pf = load_portfolio()
if pf is not None and not pf.empty:
    sell_position_dialog(pf, "AAA.BR", preset_price=110.0)
""", default_timeout=60)
        at.run()
        at.number_input(key="dlg_sell_shares").set_value(4)
        at.number_input(key="dlg_sell_fee").set_value(5.0)
        at.run()
        assert "€435.00" in _html(at)
        _save(at, "Confirm sale")
        assert cash.balance() == 435.0
        assert portfolio.load_portfolio().iloc[0]["shares"] == 6


# ── Dashboard + Risk ─────────────────────────────────────────────────────────

def test_dashboard_cash_tile_and_current_value(isolated_data, monkeypatch):
    from tests.test_pages_dashboard import _run as run_dashboard
    portfolio.save_portfolio(make_portfolio_df())          # 10 × €110 = €1,100
    cash.post_manual("Deposit", D, 900)
    html = _html(run_dashboard(monkeypatch))
    assert "of total value · not in risk" in html
    assert "incl. €900 cash" in html and "€2,000" in html


def test_risk_banner_only_with_cash(isolated_data, monkeypatch):
    from tests.test_pages_risk import _run as run_risk
    portfolio.save_portfolio(make_portfolio_df())
    at = run_risk(monkeypatch)
    assert "Risk metrics cover the invested portion only" not in _html(at)
    cash.post_manual("Deposit", D, 900)
    at.run()
    html = _html(at)
    assert "Risk metrics cover the invested portion only (€1,100)" in html
    assert "Cash of €900, 45.0% of total value" in html
    assert any(b.key == "risk_view_cash" for b in at.button)
