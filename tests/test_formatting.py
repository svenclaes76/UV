"""Tests for uvalu/formatting.py's pure value formatters."""
import pytest

from uvalu.formatting import display_name, fmt_eur, row_currency, safe_pct


class TestFmtEur:
    def test_formats_value(self):
        assert fmt_eur(12.5) == "€12.50"

    def test_missing_value_is_dash(self):
        assert fmt_eur(None) == "—"
        assert fmt_eur(float("nan")) == "—"


class TestSafePct:
    def test_computes_percentage(self):
        assert safe_pct(25.0, 100.0) == 25.0

    def test_zero_denominator_returns_zero(self):
        assert safe_pct(25.0, 0) == 0


# ── display_name (visual review G5) ─────────────────────────────────────────

@pytest.mark.parametrize("raw, shown", [
    ("MBB SE I", "MBB SE"),                          # trailing share-class letter
    ("Deutsche Rohstoff AG N", "Deutsche Rohstoff AG"),
    ("Cigna Group, The R", "The Cigna Group"),
    ("INVESTOR AB CLASS B", "Investor AB Class B"),  # "Class B" is kept
    ("CEOTRONICS AG I", "Ceotronics AG"),
    ("MAUREL ET PROM", "Maurel et Prom"),
    ("B&C SPEAKERS", "B&C Speakers"),
    ("EOG RESOURCES INC. R", "EOG Resources Inc."),
    ("LAURENT-PERRIER", "Laurent-Perrier"),
    ("TUI AG N", "TUI AG"),
    ("bpost NV/SA", "bpost NV/SA"),                  # mixed case: left as written
    ("Montea Comm. VA", "Montea Comm. VA"),
    ("1CF.MI", "1CF.MI"),                            # a ticker standing in for a name
    ("CPINV.BR", "CPINV.BR"),
    ("", ""),
    (None, ""),
])
def test_display_name(raw, shown):
    assert display_name(raw) == shown


# ── exchange_label (visual review DR3) ──────────────────────────────────────

@pytest.mark.parametrize("ticker, exchange, shown", [
    ("SYENS.BR", None, "Brussels"),          # the portfolio lane has no Exchange field
    ("SYENS.BR", "", "Brussels"),
    ("CEK.DE", None, "Frankfurt"),
    ("AAA.PA", "Paris", "Paris"),            # the row's own field wins
    ("BDC", None, "—"),
    (None, None, "—"),
])
def test_exchange_label(ticker, exchange, shown):
    from uvalu.formatting import exchange_label
    assert exchange_label(ticker, exchange) == shown


def test_exchange_codes_match_the_design_reference():
    """Venue codes as in Uvalu.dc.html's _exch (Portfolio, Risk, Screener rows)."""
    from uvalu.formatting import exchange_code
    assert [exchange_code(t) for t in ("ULVR.L", "TEF.MC", "NDA-FI.HE", "VOLV-B.ST", "AED.BR")] == \
        ["LON", "MAD", "HEL", "STO", "BRU"]
    assert exchange_code("AAPL") is None


class TestRowCurrency:
    """EX-W0: per-share figures use the row's own currency."""

    def test_row_currency_field_wins(self):
        assert row_currency({"Ticker": "ALPN.SW", "Currency": "chf"}) == "CHF"

    def test_falls_back_to_the_exchange_currency(self):
        assert row_currency({"Ticker": "ALPN.SW"}) == "CHF"
        assert row_currency({"ticker": "UCB.BR", "Currency": None}) == "EUR"

    def test_unknown_suffix_is_eur(self):
        assert row_currency({"Ticker": "AAPL"}) == "EUR"

    def test_works_on_a_series(self):
        import pandas as pd
        assert row_currency(pd.Series({"Ticker": "NESN.SW", "Currency": float("nan")})) == "CHF"
