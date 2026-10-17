"""EX-W3 (exchange expansion plan): symbol mapping, per-exchange filters,
share classes, and tickers typed by hand. Symbols are real ones from the
stockanalysis.com lists on 16 Oct 2026."""
import pandas as pd
import pytest
import requests
import yfinance as yf

import fetch_tickers
import screener
from uvalu import exchanges
from uvalu.formatting import display_name, share_class


@pytest.mark.parametrize("symbol, suffix, ticker", [
    ("INVE.B", ".ST", "INVE-B.ST"),      # Stockholm share class
    ("NOVO.B", ".CO", "NOVO-B.CO"),      # Copenhagen
    ("NOVO B", ".CO", "NOVO-B.CO"),      # space instead of a dot
    ("BT.A", ".L", "BT-A.L"),            # London
    ("GRF.P", ".MC", "GRF-P.MC"),        # Madrid
    ("SFS.B", ".IC", "SFS-B.IC"),        # Iceland
    ("NDA.FI", ".HE", "NDA-FI.HE"),      # Nordea's line in Helsinki
    ("NOKIA.SEK", ".ST", "NOKIA-SEK.ST"),
    ("TAL1T", ".TL", "TAL1T.TL"),        # digits inside a Baltic ticker stay
    ("UCB", ".BR", "UCB.BR"),            # today's exchanges: unchanged
    ("1COV", ".DE", "1COV.DE"),
])
def test_yahoo_ticker(symbol, suffix, ticker):
    assert fetch_tickers.yahoo_ticker(symbol, suffix) == ticker


class TestFilters:
    def test_london_drops_the_international_order_book(self):
        keep = fetch_tickers.LIST_FILTERS["london"]
        assert [s for s in ["0R1I", "0HD6", "SHEL", "BT.A", "III"] if keep(s)] == ["SHEL", "BT.A", "III"]

    def test_madrid_drops_latibex(self):
        keep = fetch_tickers.LIST_FILTERS["madrid"]
        assert [s for s in ["ITX", "SAN", "XPBR", "XVALO", "GRF.P"] if keep(s)] == ["ITX", "SAN", "GRF.P"]

    def test_frankfurt_keeps_its_own_filter_only(self):
        assert "frankfurt" not in fetch_tickers.LIST_FILTERS
        assert "tallinn" not in fetch_tickers.LIST_FILTERS   # TAL1T would fail the Frankfurt shape rule
        assert not fetch_tickers._is_equity_symbol("TAL1T")


class TestShareClasses:
    def _stocks(self, *tickers):
        return [{"ticker": t, "name": t, "isin": "", "mic": "X"} for t in tickers]

    def test_classes_of_one_company_are_marked(self):
        out = fetch_tickers.mark_share_classes(self._stocks("VOLV-A.ST", "VOLV-B.ST", "ERIC-B.ST"))
        classes = {s["ticker"]: s.get("share_class") for s in out}
        assert classes == {"VOLV-A.ST": "A", "VOLV-B.ST": "B", "ERIC-B.ST": None}

    def test_a_class_line_next_to_the_plain_line(self):
        out = fetch_tickers.mark_share_classes(self._stocks("GRF.MC", "GRF-P.MC"))
        assert [s.get("share_class") for s in out] == [None, "P"]

    def test_a_single_class_line_and_second_lines_are_not_classes(self):
        out = fetch_tickers.mark_share_classes(self._stocks("BT-A.L", "NDA-SE.ST", "NDA-FI.ST"))
        assert all("share_class" not in s for s in out)

    def test_display_name_adds_the_class(self):
        assert display_name("Volvo AB", "B") == "Volvo AB · B shares"
        assert display_name("Volvo AB") == "Volvo AB"
        assert share_class({"share_class": "B"}) == "B"
        assert share_class(pd.Series({"share_class": float("nan")})) is None

    def test_fetched_row_keeps_the_class(self, monkeypatch):
        monkeypatch.setattr(yf, "Ticker", lambda t: type("T", (), {"info": {"currentPrice": 200.0,
                                                                           "currency": "SEK"}})())
        row = screener._fetch_one("VOLV-B.ST", {"name": "Volvo", "isin": "", "share_class": "B"})
        assert row["share_class"] == "B"


class TestPlannedExchangeList:
    def test_london_list_is_mapped_filtered_and_marked(self, monkeypatch):
        html = pd.DataFrame({"Symbol": ["0R1I", "SHEL", "BT.A", "RDS.A", "RDS.B"],
                             "Company Name": ["Foreign", "Shell", "BT", "Royal A", "Royal B"]}).to_html(index=False)
        monkeypatch.setattr(requests, "get", lambda *a, **k: type("R", (), {
            "text": html, "raise_for_status": lambda self: None})())
        out = fetch_tickers.fetch_exchange_tickers("london")
        assert [s["ticker"] for s in out] == ["SHEL.L", "BT-A.L", "RDS-A.L", "RDS-B.L"]
        assert [s.get("share_class") for s in out] == [None, None, "A", "B"]
        assert all(s["mic"] == "XLON" for s in out)

    def test_a_planned_list_without_data_is_empty_not_an_error(self, monkeypatch):
        def _down(*a, **k):
            raise requests.ConnectionError("offline")
        monkeypatch.setattr(requests, "get", _down)
        assert fetch_tickers.fetch_exchange_tickers("riga") == []


@pytest.mark.parametrize("typed, ticker", [
    ("novo b.co", "NOVO-B.CO"), ("NOVO.B.CO", "NOVO-B.CO"), ("  inve b.st ", "INVE-B.ST"),
    ("TTE.PA", "TTE.PA"), ("ttE.pa", "TTE.PA"), ("BRK.B", "BRK.B"), ("AAPL", "AAPL"), ("", ""),
])
def test_normalize_ticker(typed, ticker):
    """Plan §10 P3: a ticker typed by hand, as the exchange writes it."""
    assert exchanges.normalize_ticker(typed) == ticker
