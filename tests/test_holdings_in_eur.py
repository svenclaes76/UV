"""P12 (exchange expansion plan §10): holding values are in EUR.

Position values were shares × live price with the price in the stock's own
currency, then added to EUR totals and compared with the EUR purchase value.
"""
import pandas as pd
import pytest

import fx
import portfolio
from portfolio_enrichment import enrich_for_risk

EUR_PER_CHF = 1.06


@pytest.fixture
def chf_rate(monkeypatch):
    def _rate(ccy, base="EUR", on=None):
        ccy = (ccy or "").upper()
        if ccy == base:
            return fx.FxQuote(1.0, None, "base")
        if ccy == "CHF":
            return fx.FxQuote(EUR_PER_CHF, None, "ecb")
        raise fx.FxUnavailable(f"no {ccy} rate")
    monkeypatch.setattr(fx, "get_rate", _rate)


def _pf():
    return pd.DataFrame({"ticker": ["UCB.BR", "NESN.SW"], "shares": [10, 10],
                         "live_price": [100.0, 80.0], "purchase_value": [900.0, 800.0]})


def test_position_values_convert_each_currency(chf_rate):
    values = portfolio.position_values_eur(_pf())
    assert values.tolist() == pytest.approx([1000.0, 800.0 * EUR_PER_CHF])


def test_missing_rate_leaves_the_value_unknown(monkeypatch):
    def _no_rate(ccy, base="EUR", on=None):
        if ccy.upper() == base:
            return fx.FxQuote(1.0, None, "base")
        raise fx.FxUnavailable("offline")
    monkeypatch.setattr(fx, "get_rate", _no_rate)
    values = portfolio.position_values_eur(_pf())
    assert values.iloc[0] == 1000.0
    assert pd.isna(values.iloc[1])           # never the CHF amount as if it were euros


def test_missing_price_stays_missing(chf_rate):
    pf = _pf()
    pf.loc[1, "live_price"] = None
    assert pd.isna(portfolio.position_values_eur(pf).iloc[1])


def test_risk_enrichment_values_and_income_in_eur(chf_rate):
    pf = _pf()[["ticker", "shares"]]
    scored = pd.DataFrame({"trailingAnnualDividendRate": [2.0, 3.0]},
                          index=pd.Index(["UCB.BR", "NESN.SW"], name="Ticker"))
    live = {"UCB.BR": {"price": 100.0}, "NESN.SW": {"price": 80.0}}
    out = enrich_for_risk(pf, scored, live)
    assert out["current_value"].tolist() == pytest.approx([1000.0, 848.0])
    assert out["expected_annual"].tolist() == pytest.approx([20.0, round(30.0 * EUR_PER_CHF, 2)])
    assert out["live_price"].tolist() == [100.0, 80.0]   # per-share price stays native
