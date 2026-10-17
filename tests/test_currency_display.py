"""EX-W11b: currency codes (D14), small codes and price decimals (D22), the
user's-own-currency second line (D25) and the price sort (D16)."""
import pandas as pd
import pytest

import fx
from uvalu import formatting, i18n
from uvalu.formatting import (converted, converted_line_html, converted_text, money_html, price_decimals,
                              price_html, price_in_eur, text_width_chars)

NBSP = " "


@pytest.fixture
def chf_and_dkk(monkeypatch):
    rates = {"CHF": 1.06, "DKK": 0.134}

    def _rate(ccy, base="EUR", on=None):
        ccy = (ccy or "").upper()
        if ccy == base:
            return fx.FxQuote(1.0, None, "base")
        if ccy in rates:
            return fx.FxQuote(rates[ccy], None, "ecb")
        raise fx.FxUnavailable("no rate")
    monkeypatch.setattr(fx, "get_rate", _rate)
    formatting._EUR_RATES.clear()
    yield
    formatting._EUR_RATES.clear()


@pytest.mark.parametrize("region, expected", [
    ("en-GB", f"EUR{NBSP}55.86"), ("nl-BE", f"EUR{NBSP}55,86"), ("de-DE", f"55,86{NBSP}EUR"),
    ("fr-BE", f"55,86{NBSP}EUR"),
])
def test_codes_never_symbols(region, expected):
    assert i18n.fmt_money(55.86, "EUR", locale=region) == expected
    assert "€" not in i18n.fmt_money(1234.5, "EUR", locale=region)
    assert "£" not in i18n.fmt_money(2.1, "GBP", locale=region)


def test_code_is_set_small_and_the_number_keeps_its_weight():
    html = money_html(8.8, "CHF")
    assert ">CHF</span>" in html and html.endswith(f"{NBSP}8.80</span>") and "white-space:nowrap" in html
    assert "0.55em" in html


@pytest.mark.parametrize("value, decimals", [(999.99, 2), (1000, 0), (24270, 0), (-1500, 0), (None, 2)])
def test_no_decimals_from_a_thousand(value, decimals):
    assert price_decimals(value) == decimals
    if value is not None:
        assert price_html(24270, "DKK").endswith(f"{NBSP}24,270</span>")


def test_width_counts_the_small_code_at_its_size():
    assert text_width_chars(f"EUR{NBSP}12.24") < len(f"EUR{NBSP}12.24")
    assert text_width_chars("+48.0%") == len("+48.0%")


class TestConvertedLine:
    def test_foreign_amount_gets_the_euro_line(self, chf_and_dkk):
        assert converted(100, "CHF") == (pytest.approx(106.0), "EUR")
        assert converted_text(100, "CHF") == f"≈{NBSP}EUR{NBSP}106.00"
        line = converted_line_html(100, "CHF")
        assert f"≈{NBSP}EUR" in line and "font-size:10px" in line and "var(--muted)" in line

    def test_no_line_for_the_users_own_currency(self, chf_and_dkk):
        assert converted(100, "EUR") is None
        assert converted_line_html(100, "EUR") == ""

    def test_no_line_without_a_rate(self, chf_and_dkk):
        assert converted(100, "ISK") is None             # never a guessed figure
        assert converted_line_html(float("nan"), "CHF") == ""

    def test_line_follows_the_display_currency(self, chf_and_dkk, monkeypatch):
        """A user whose own currency is CHF sees a EUR stock converted to CHF."""
        import dataclasses
        ctx = dataclasses.replace(i18n.current(), currency="CHF")
        monkeypatch.setattr(i18n, "current", lambda: ctx)
        monkeypatch.setattr(i18n, "display_rate", lambda: (1.06, "2026-10-17"))
        assert converted(106, "EUR") == (pytest.approx(100.0), "CHF")
        assert converted(100, "CHF") is None


def test_price_sorts_on_its_euro_value(chf_and_dkk):
    df = pd.DataFrame({"Ticker": ["MAERSK-B.CO", "UCB.BR", "NESN.SW"], "Price": [24270.0, 180.0, 80.0]})
    eur = price_in_eur(df)
    assert eur.tolist() == pytest.approx([24270 * 0.134, 180.0, 80 * 1.06])
    assert list(df.assign(e=eur).sort_values("e", ascending=False)["Ticker"]) == ["MAERSK-B.CO", "UCB.BR", "NESN.SW"]


def test_converted_line_follows_the_price_rule(chf_and_dkk):
    """D22 for the second line too: DKK 24,270 → '≈ EUR 3,252', no decimals."""
    assert converted_line_html(24270, "DKK").endswith(f"≈{NBSP}EUR{NBSP}3,252</div>")
    assert f"EUR{NBSP}9.33" in converted_line_html(8.8, "CHF")
