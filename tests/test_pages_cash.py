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
from tests.conftest import make_portfolio_df, fake_portfolio_scored, USER_SETUP_SRC

D = date(2026, 3, 2)


def _run_portfolio(monkeypatch, section=None, role="Analyst") -> AppTest:
    monkeypatch.setattr(portfolio_page, "_load_portfolio_scored", fake_portfolio_scored())
    monkeypatch.setattr(portfolio_page, "_fetch_prices_cached", lambda tickers: {
        t: {"price": 110.0} for t in tickers})
    monkeypatch.setattr(portfolio_page, "ensure_value_history_fresh", lambda *a: False)
    monkeypatch.setattr(portfolio_page, "import_dividends_from_market_data", lambda *a, **k: 0)
    section_line = (f'st.session_state.setdefault("port_section", {section!r})' if section else "")
    at = AppTest.from_string(USER_SETUP_SRC + f"""
import streamlit as st
st.session_state["user_email"] = "test@example.com"
st.session_state["user_role"] = {role!r}
{section_line}
from uvalu.pages_ import portfolio as portfolio_page
portfolio_page.render()
""", default_timeout=60)
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

    def test_viewer_has_no_deposit_withdraw(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        at = _run_portfolio(monkeypatch, role="Viewer")
        keys = {b.key for b in at.button}
        assert "ov_cash_deposit" not in keys and "ov_cash_withdraw" not in keys

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
        assert any(b.label == "Export CSV" for b in at.get("download_button"))
        assert any(b.key == "btn_add_cash" for b in at.button)

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
        assert "Viewer · read-only" in _html(at)
        assert not any(b.key == "btn_add_cash" for b in at.button)
        assert any(b.label == "Export CSV" for b in at.get("download_button"))

    def test_empty_ledger_message(self, isolated_data, monkeypatch):
        portfolio.save_portfolio(make_portfolio_df())
        at = _run_portfolio(monkeypatch, section="cash")
        assert any("No cash entries yet" in c.value for c in at.caption)

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
        _save(at, "Add deposit")
        e = cash.load_ledger()[0]
        assert (e["type"], e["amount"], e["note"]) == ("Deposit", 2500.0, "Monthly savings plan")

    def test_withdrawal_preset_and_block(self, isolated_data):
        cash.post_manual("Deposit", date.today(), 100)
        at = _run_dialog("Withdrawal")
        at.number_input(key="dlg_cash_amt").set_value(150.0)
        at.run()
        assert "· blocked" in _html(at)
        _save(at, "Add withdrawal")
        assert "Balance cannot go negative" in _html(at)
        assert len(cash.load_ledger()) == 1

    def test_foreign_currency_uses_ecb_rate(self, isolated_data, monkeypatch):
        monkeypatch.setattr(fx, "get_rate", lambda c, b="EUR", on=None: fx.FxQuote(0.85, date(2026, 3, 2), "ecb"))
        at = _run_dialog()
        at.selectbox(key="dlg_cash_ccy").set_value("USD")
        at.number_input(key="dlg_cash_amt").set_value(1000.0)
        at.run()
        html = _html(at)
        assert "1 USD = €0.8500" in html and "frankfurter.dev" in html and "+€850.00" in html
        _save(at, "Add deposit")
        e = cash.load_ledger()[0]
        assert (e["currency"], e["fx_rate"], e["fx_source"], e["amount_base"]) == ("USD", 0.85, "ecb", 850.0)

    def test_outage_forces_manual_flagged_rate(self, isolated_data):
        at = _run_dialog()                                    # conftest: frankfurter is "down"
        at.selectbox(key="dlg_cash_ccy").set_value("GBP")
        at.number_input(key="dlg_cash_amt").set_value(100.0)
        at.run()
        assert "frankfurter.dev is unreachable" in _html(at)
        _save(at, "Add deposit")
        assert "Enter the FX rate to convert GBP to EUR." in _html(at)
        at.number_input(key="dlg_cash_rate").set_value(1.16)
        _save(at, "Add deposit")
        e = cash.load_ledger()[0]
        assert (e["fx_source"], e["amount_base"]) == ("manual", 116.0)

    def test_adjustment_sets_balance(self, isolated_data):
        cash.post_manual("Deposit", D, 1000)
        at = _run_dialog("Adjustment")
        at.number_input(key="dlg_cash_target").set_value(987.6)
        at.run()
        assert "−€12.40" in _html(at)
        _save(at, "Log correction")
        assert cash.balance() == 987.6

    def test_viewer_cannot_post(self, isolated_data):
        at = _run_dialog(role="Viewer")
        assert not [b for b in at.button if b.label == "Add deposit"]


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
        assert "Cash after trade" in html and "+€109.90 auto top-up" in html
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
