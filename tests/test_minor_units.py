"""EX-14 / EX-15 (exchange expansion plan, EX-W5): prices quoted in pence.

Yahoo quotes London lines in pence ("GBp") while EPS, book value and market
cap are in pounds (checked on BT-A.L, 16 Oct 2026). Every price is converted
to pounds where it enters the app.
"""
import pandas as pd
import pytest
import yfinance as yf

import marketdata
import prices
import screener

# BT-A.L as Yahoo returned it on 16 Oct 2026.
BT_INFO = {
    "shortName": "BT Group plc", "currency": "GBp", "financialCurrency": "GBP",
    "currentPrice": 209.7, "trailingEps": 0.11, "bookValue": 1.275,
    "trailingPE": 19.063635, "priceToBook": 1.644706, "marketCap": 20663044096,
    "dividendRate": 0.08, "trailingAnnualDividendRate": 0.083, "dividendYield": 4.02,
    "country": "United Kingdom",
}


def _fake_ticker(info, dividends=None):
    return lambda t: type("T", (), {"info": info,
                                    "dividends": dividends if dividends is not None else pd.Series(dtype=float)})()


@pytest.mark.parametrize("raw, expected", [
    ("GBp", ("GBP", 100)), ("GBX", ("GBP", 100)), ("EUR", ("EUR", 1)),
    ("chf", ("CHF", 1)), (None, ("EUR", 1)),
])
def test_major_currency(raw, expected):
    assert marketdata.major_currency(raw) == expected


class TestFundamentals:
    def test_pence_price_is_stored_in_pounds(self, monkeypatch):
        monkeypatch.setattr(yf, "Ticker", _fake_ticker(dict(BT_INFO)))
        row = screener._fetch_one("BT-A.L", {"name": "BT", "isin": ""})
        assert row["Price"] == pytest.approx(2.097)
        assert row["Currency"] == "GBP"
        # P/E and yield now compare pounds with pounds
        assert row["Price"] / row["trailingEps"] == pytest.approx(19.06, abs=0.05)
        assert row["dividendYield"] == pytest.approx(0.08 / 2.097)
        assert "dividendRate_unit_fixed" not in row
        assert marketdata.price_divisor("BT-A.L") == 100       # recorded for history / live prices

    def test_dividend_rate_in_pence_is_scaled(self, monkeypatch):
        info = dict(BT_INFO, dividendRate=8.0, trailingAnnualDividendRate=8.3)
        monkeypatch.setattr(yf, "Ticker", _fake_ticker(info))
        row = screener._fetch_one("BT-A.L", {"name": "BT", "isin": ""})
        assert row["dividendRate"] == pytest.approx(0.08)
        assert row["trailingAnnualDividendRate"] == pytest.approx(0.083)
        assert row["dividendRate_unit_fixed"] is True

    def test_a_euro_line_is_untouched(self, monkeypatch):
        monkeypatch.setattr(yf, "Ticker", _fake_ticker({"currentPrice": 100.0, "currency": "EUR",
                                                        "dividendRate": 4.0}))
        row = screener._fetch_one("AAA.BR", {"name": "X", "isin": ""})
        assert row["Price"] == 100.0 and row["Currency"] == "EUR"
        assert marketdata.price_divisor("AAA.BR") == 1


class TestDivisor:
    def test_unknown_line_uses_the_exchange_default(self, monkeypatch):
        from uvalu import exchanges
        london = exchanges.Exchange("london", "London Stock Exchange", "United Kingdom", ".L", "XLON",
                                    "GBP", "LON", "https://stockanalysis.com/list/london-stock-exchange/",
                                    "London", price_divisor=100)
        monkeypatch.setitem(exchanges.BY_SUFFIX, ".L", london)
        assert marketdata.price_divisor("SHEL.L") == 100
        marketdata.record_quote_currency("SHEL.L", "USD")    # a London line quoted in dollars
        assert marketdata.price_divisor("SHEL.L") == 1

    def test_covered_exchanges_have_no_divisor_today(self):
        from uvalu import exchanges
        assert all(e.price_divisor == 1 for e in exchanges.EXCHANGES)


class TestHistoryDividendsLivePrices:
    @pytest.fixture(autouse=True)
    def _bt_in_pence(self):
        marketdata.record_quote_currency("BT-A.L", "GBp")

    def test_history_closes_in_pounds(self, monkeypatch):
        dates = pd.date_range("2026-10-12", periods=3)
        raw = pd.concat({"Close": pd.DataFrame({"BT-A.L": [200.0, 205.0, 209.7],
                                                "AAA.BR": [10.0, 11.0, 12.0]}, index=dates)}, axis=1)
        monkeypatch.setattr(yf, "download", lambda *a, **k: raw)
        closes = marketdata._download_closes(["BT-A.L", "AAA.BR"], None, "5d")
        assert closes["BT-A.L"].tolist() == pytest.approx([2.0, 2.05, 2.097])
        assert closes["AAA.BR"].tolist() == [10.0, 11.0, 12.0]

    def test_dividends_in_pounds(self, monkeypatch, tmp_path):
        monkeypatch.setattr(marketdata, "_DIVIDEND_DIR", tmp_path / "dividends")
        divs = pd.Series([2.45, 5.87], index=pd.to_datetime(["2025-12-29", "2026-08-06"]))
        monkeypatch.setattr(yf, "Ticker", _fake_ticker({}, dividends=divs))
        out = marketdata.dividends("BT-A.L")
        assert out.tolist() == pytest.approx([0.0245, 0.0587])

    def test_live_price_in_pounds(self, monkeypatch):
        dates = pd.date_range("2026-10-15", periods=2)
        raw = pd.concat({"Close": pd.DataFrame({"BT-A.L": [206.9, 209.7]}, index=dates),
                         "Volume": pd.DataFrame({"BT-A.L": [1000, 1200]}, index=dates)}, axis=1)
        monkeypatch.setattr(yf, "download", lambda *a, **k: raw if k.get("interval") != "1m" else pd.DataFrame())
        prices._last_good.clear()
        out = prices.fetch_prices(("BT-A.L",))["BT-A.L"]
        assert out["price"] == pytest.approx(2.097)
        assert out["prev_close"] == pytest.approx(2.069)
        assert out["day_change_pct"] == pytest.approx((209.7 - 206.9) / 206.9 * 100, abs=0.01)
        prices._last_good.clear()
