"""Tests for uvalu/dialogs.py — shared Add/Sell/Dividend/Closed-trade CRUD
modals.

Every public entry point here is an @st.dialog-decorated function. Project
memory (see uvalu-drawer-dialog-gotchas) flags AppTest's dialog-button
interaction as previously unreliable in one specific case (a nested
@st.dialog + st.switch_page combination) — these tests probe plain
Save/Cancel button clicks directly to see whether that holds here too,
rather than assuming either way.
"""
import pandas as pd
import pytest
import yfinance as yf
from streamlit.testing.v1 import AppTest

import portfolio
from uvalu import dialogs
from tests.conftest import make_portfolio_df, USER_SETUP_SRC


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", "unit-test-key-123")
    monkeypatch.setattr(portfolio, "_BASE_DIR", tmp_path / "portfolio")
    portfolio.set_user("test@example.com")
    yield
    portfolio.set_user("")


# ── _lookup_ticker (pure-ish, network via yfinance) ──────────────────────

class TestLookupTicker:
    def test_returns_name_and_price_when_found(self, monkeypatch):
        class FakeTicker:
            def __init__(self, sym):
                self.info = {"regularMarketPrice": 42.5, "shortName": "Alpha Corp"}
        monkeypatch.setattr(yf, "Ticker", FakeTicker)
        assert dialogs._lookup_ticker("AAA.BR") == ("Alpha Corp", 42.5)

    def test_falls_back_to_current_price(self, monkeypatch):
        class FakeTicker:
            def __init__(self, sym):
                self.info = {"currentPrice": 10.0, "longName": "Beta Corp"}
        monkeypatch.setattr(yf, "Ticker", FakeTicker)
        assert dialogs._lookup_ticker("BBB.BR") == ("Beta Corp", 10.0)

    def test_uses_symbol_as_name_when_no_name_fields(self, monkeypatch):
        class FakeTicker:
            def __init__(self, sym):
                self.info = {"regularMarketPrice": 5.0}
        monkeypatch.setattr(yf, "Ticker", FakeTicker)
        assert dialogs._lookup_ticker("ZZZ.BR") == ("ZZZ.BR", 5.0)

    def test_returns_none_when_no_price(self, monkeypatch):
        class FakeTicker:
            def __init__(self, sym):
                self.info = {}
        monkeypatch.setattr(yf, "Ticker", FakeTicker)
        assert dialogs._lookup_ticker("BAD.BR") is None

    def test_returns_none_on_exception(self, monkeypatch):
        def boom(sym):
            raise RuntimeError("network down")
        monkeypatch.setattr(yf, "Ticker", boom)
        assert dialogs._lookup_ticker("AAA.BR") is None


class TestDialogWidthCss:
    def test_renders_expected_style_block(self):
        def _script():
            from uvalu import dialogs
            dialogs._dialog_width_css(420)
        at = AppTest.from_function(_script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert "420px" in at.markdown[0].value


# ── add_position_dialog ──────────────────────────────────────────────────

def _run_add_position(monkeypatch, preset_ticker="", preset_name="", preset_price=0.0) -> AppTest:
    script = USER_SETUP_SRC + f"""
from uvalu.dialogs import add_position_dialog
add_position_dialog(preset_ticker={preset_ticker!r}, preset_name={preset_name!r}, preset_price={preset_price!r})
"""
    at = AppTest.from_string(script, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


class TestAddPositionDialog:
    def test_renders_with_presets(self, monkeypatch):
        at = _run_add_position(monkeypatch, preset_ticker="AAA.BR", preset_name="Alpha Corp", preset_price=12.5)
        assert at.text_input(key="dlg_ap_ticker").value == "AAA.BR"
        assert at.text_input(key="dlg_ap_name").value == "Alpha Corp"
        assert at.number_input(key="dlg_ap_price").value == 12.5

    def test_save_without_ticker_shows_error(self, monkeypatch):
        at = _run_add_position(monkeypatch)
        save = [b for b in at.button if b.label == "Save"][0]
        save.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert "Enter a ticker symbol" in "".join(e.value for e in at.error)

    def test_save_with_unknown_ticker_shows_error(self, monkeypatch):
        monkeypatch.setattr(yf, "Ticker", lambda sym: type("T", (), {"info": {}})())
        at = _run_add_position(monkeypatch, preset_ticker="ZZZ.BR")
        save = [b for b in at.button if b.label == "Save"][0]
        save.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert "not found" in "".join(e.value for e in at.error)

    def test_save_with_valid_ticker_and_total_cost_adds_position(self, monkeypatch):
        monkeypatch.setattr(yf, "Ticker", lambda sym: type(
            "T", (), {"info": {"regularMarketPrice": 50.0, "shortName": "Alpha Corp"}})())
        at = _run_add_position(monkeypatch, preset_ticker="AAA.BR")
        at.number_input(key="dlg_ap_shares").set_value(10)
        at.number_input(key="dlg_ap_cost").set_value(1000.0)
        save = [b for b in at.button if b.label == "Save"][0]
        save.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        saved = portfolio.load_portfolio()
        assert saved.iloc[0]["ticker"] == "AAA.BR"
        assert saved.iloc[0]["shares"] == 10
        assert saved.iloc[0]["purchase_value"] == 1000.0

    def test_cancel_does_not_save(self, monkeypatch):
        at = _run_add_position(monkeypatch, preset_ticker="AAA.BR")
        cancel = [b for b in at.button if b.label == "Cancel"][0]
        cancel.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert portfolio.load_portfolio() is None


# ── sell_position_dialog ──────────────────────────────────────────────────

class TestSellPositionDialog:
    def test_renders_ticker_selector_when_no_ticker_given(self, monkeypatch):
        script = USER_SETUP_SRC + """
from portfolio import load_portfolio
from uvalu.dialogs import sell_position_dialog
import pandas as pd
pf = pd.DataFrame([{"ticker": "AAA.BR", "name": "Alpha Corp", "shares": 10, "live_price": 100.0}])
sell_position_dialog(pf)
"""
        at = AppTest.from_string(script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert len(at.selectbox) == 1

    def test_nan_shares_and_live_price_do_not_crash(self, monkeypatch):
        # `pd.to_numeric(...) or default` doesn't catch NaN (bool(nan) is
        # True in Python), so a position with an unparseable/blank shares or
        # live_price field (e.g. an Excel-imported row with a blank cell)
        # used to crash int(nan) outright when opening this dialog.
        script = USER_SETUP_SRC + """
from uvalu.dialogs import sell_position_dialog
import pandas as pd
pf = pd.DataFrame([{"ticker": "AAA.BR", "name": "Alpha Corp",
                    "shares": float("nan"), "live_price": float("nan")}])
sell_position_dialog(pf, "AAA.BR")
"""
        at = AppTest.from_string(script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.number_input(key="dlg_sell_shares").value == 1
        assert at.number_input(key="dlg_sell_price").value == 0.0

    def test_confirm_close_sells_position(self, monkeypatch):
        portfolio.save_portfolio(pd.DataFrame([{
            "ticker": "AAA.BR", "name": "Alpha Corp", "shares": 10,
            "live_price": 100.0, "purchase_value": 800.0, "dividends": 0.0, "date_in": "2023-01-01",
        }]))
        # `if pf is not None and not pf.empty:` mirrors the guard the real
        # call site uses (uvalu/drawer.py's dispatch_pending_drawer_action)
        # before invoking this dialog. Without it, AppTest's st.rerun()
        # (fired by "Confirm close" itself) re-executes this whole script,
        # reloading a NOW-empty portfolio and unconditionally reopening the
        # dialog against it — and portfolio.py's JSON round-trip turns a
        # truly-empty DataFrame column-less, so `pf["ticker"]` KeyErrors.
        # That's a test-script-structure artifact, not a real app bug —
        # confirmed by this guard alone fixing it, matching production.
        script = USER_SETUP_SRC + """
from portfolio import load_portfolio
from uvalu.dialogs import sell_position_dialog
pf = load_portfolio()
if pf is not None and not pf.empty:
    sell_position_dialog(pf, "AAA.BR", preset_price=110.0)
"""
        at = AppTest.from_string(script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]

        confirm = [b for b in at.button if b.label == "Confirm close"][0]
        confirm.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert portfolio.load_portfolio().empty
        sold = portfolio.load_sold()
        assert sold.iloc[0]["ticker"] == "AAA.BR"
        assert sold.iloc[0]["sale_value"] == 1100.0


# ── add_dividend_dialog ───────────────────────────────────────────────────

class TestAddDividendDialog:
    def _run(self):
        portfolio.save_portfolio(pd.DataFrame([{
            "ticker": "AAA.BR", "name": "Alpha Corp", "shares": 10, "dividends": 0.0,
        }]))
        script = USER_SETUP_SRC + """
from portfolio import load_portfolio
from uvalu.dialogs import add_dividend_dialog
pf = load_portfolio()
add_dividend_dialog(pf)
"""
        at = AppTest.from_string(script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        return at

    def test_nan_shares_does_not_crash_on_save(self):
        # Same NaN-truthy bug as sell_position_dialog's shares lookup --
        # int(pd.to_numeric(...) or 0) raises ValueError on a NaN shares
        # field instead of falling back to 0.
        portfolio.save_portfolio(pd.DataFrame([{
            "ticker": "AAA.BR", "name": "Alpha Corp", "shares": float("nan"), "dividends": 0.0,
        }]))
        script = USER_SETUP_SRC + """
from portfolio import load_portfolio
from uvalu.dialogs import add_dividend_dialog
pf = load_portfolio()
add_dividend_dialog(pf)
"""
        at = AppTest.from_string(script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        at.text_input(key="dlg_dv_ticker").set_value("AAA.BR")
        at.number_input(key="dlg_dv_amount").set_value(15.0)
        save = [b for b in at.button if b.label == "Save"][0]
        save.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert portfolio.load_div_hist().iloc[0]["shares"] == 0

    def test_save_without_amount_shows_error(self):
        at = self._run()
        at.text_input(key="dlg_dv_ticker").set_value("AAA.BR")
        save = [b for b in at.button if b.label == "Save"][0]
        save.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert "Enter a ticker and an amount" in "".join(e.value for e in at.error)

    def test_save_with_valid_data_records_dividend(self):
        at = self._run()
        at.text_input(key="dlg_dv_ticker").set_value("AAA.BR")
        at.number_input(key="dlg_dv_amount").set_value(15.0)
        save = [b for b in at.button if b.label == "Save"][0]
        save.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        div_hist = portfolio.load_div_hist()
        assert div_hist.iloc[0]["ticker"] == "AAA.BR"
        assert div_hist.iloc[0]["amount"] == 15.0


# ── add_closed_trade_dialog ────────────────────────────────────────────────

class TestAddClosedTradeDialog:
    def _run(self):
        script = USER_SETUP_SRC + """
from uvalu.dialogs import add_closed_trade_dialog
add_closed_trade_dialog()
"""
        at = AppTest.from_string(script, default_timeout=60)
        at.run()
        assert not at.exception, [str(e.value) for e in at.exception]
        return at

    def test_save_without_prices_shows_error(self):
        at = self._run()
        at.text_input(key="dlg_ct_ticker").set_value("AAA.BR")
        save = [b for b in at.button if b.label == "Save"][0]
        save.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert "Enter a ticker, shares" in "".join(e.value for e in at.error)

    def test_save_with_valid_data_records_closed_trade(self):
        at = self._run()
        at.text_input(key="dlg_ct_ticker").set_value("SAP.DE")
        at.number_input(key="dlg_ct_shares").set_value(5)
        at.number_input(key="dlg_ct_buy").set_value(100.0)
        at.number_input(key="dlg_ct_sell").set_value(120.0)
        save = [b for b in at.button if b.label == "Save"][0]
        save.click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        sold = portfolio.load_sold()
        assert sold.iloc[0]["ticker"] == "SAP.DE"
        assert sold.iloc[0]["purchase_value"] == 500.0
        assert sold.iloc[0]["sale_value"] == 600.0
