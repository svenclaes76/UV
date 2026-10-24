"""V1 (model M2): figures reported in another currency than the quote are
converted before scoring (docs/valuation-model-review.md V1)."""

import math

import numpy as np
import pandas as pd

import screener


def _row(**kw):
    base = {"Ticker": "1INVEB.MI", "Price": 36.0, "Currency": "EUR", "financialCurrency": "SEK",
            "trailingEps": 7.84, "bookValue": 293.6, "ebit": 1.0e9, "totalDebt": 2.0e9,
            "totalCash": 5.0e8, "freeCashflow": 4.0e8, "netIncome": 6.0e8,
            "enterpriseValue": 9.9e9, "trailingPE": 4.6, "priceToBook": 0.12,
            "ebitHistory": [1.0e9, 9.0e8, None, float("nan")]}
    base.update(kw)
    return base


def _sek_eur(rep, quote):
    assert (rep, quote) == ("SEK", "EUR")
    return 0.09


def test_reporting_currency_figures_are_converted_to_the_quote_currency():
    # M4 behaviour (V7 switched off): every figure is taken as reporting currency.
    screener._m5_state["m5_per_share_currency"] = False
    df, _ = screener._convert_reporting_currency(pd.DataFrame([_row()]), rate_fn=_sek_eur)
    r = df.iloc[0]
    assert math.isclose(r["bookValue"], 293.6 * 0.09)
    assert math.isclose(r["trailingEps"], 7.84 * 0.09)
    assert math.isclose(r["ebit"], 1.0e9 * 0.09)
    assert r["ebitHistory"][:2] == [1.0e9 * 0.09, 9.0e8 * 0.09]
    assert r["ebitHistory"][2] is None and math.isnan(r["ebitHistory"][3])
    # The sector-median inputs are recomputed from the converted figures.
    assert math.isclose(r["priceToBook"], 36.0 / (293.6 * 0.09))
    assert math.isclose(r["trailingPE"], 36.0 / (7.84 * 0.09))
    assert np.isnan(r["enterpriseValue"])          # rebuilt from its parts (FV-4)
    assert not r["currency_unverified"]


def test_same_currency_and_unknown_reporting_currency_are_left_alone():
    rows = [_row(Ticker="SOLB.BR", financialCurrency="EUR"), _row(Ticker="OLD.BR", financialCurrency=None)]
    df, _ = screener._convert_reporting_currency(
        pd.DataFrame(rows), rate_fn=lambda *a: (_ for _ in ()).throw(AssertionError("no rate needed")))
    assert list(df["bookValue"]) == [293.6, 293.6]
    assert not df["currency_unverified"].any()


def test_without_a_rate_the_row_is_flagged_and_leaves_the_peer_group():
    def _no_rate(*_):
        raise RuntimeError("ECB unavailable")
    df = pd.DataFrame([_row(), _row(Ticker="SOLB.BR", financialCurrency="EUR")])
    out, mask = screener._convert_reporting_currency(df, pd.Series([True, True]), rate_fn=_no_rate)
    assert list(out["currency_unverified"]) == [True, False]
    assert list(mask) == [False, True]
    assert out.iloc[0]["bookValue"] == 293.6        # not converted, not trusted either


def test_an_unverified_row_is_never_undervalued_and_carries_the_flag(monkeypatch):
    monkeypatch.setattr(screener, "_fx_rate", lambda *a: (_ for _ in ()).throw(RuntimeError("no rate")))
    rows = [_row(Ticker=f"P{i}.MI", financialCurrency="EUR", bookValue=20.0 + i, trailingEps=3.0 + i / 10)
            for i in range(25)]
    rows.append(_row())   # SEK reporter, unconvertible: a huge apparent discount
    out = screener.run_screener_from_df(pd.DataFrame(rows), min_mos=0.10)
    inv = out[out["Ticker"] == "1INVEB.MI"].iloc[0]
    assert inv["signal_code"] != screener.SIGNAL_UNDERVALUED
    assert "currency_unverified" in inv["data_flags"]


# ── V7 (M5): the per-share figures' currency is decided per row ────────────

def _usd_gbp(rep, quote):
    return {("USD", "GBP"): 0.75, ("EUR", "GBP"): 0.86, ("USD", "NOK"): 10.0}[(rep, quote)]


def test_eps_in_the_reporting_currency_is_converted():
    # Shell: EPS 3.38 USD, net income USD 17.8bn on 5.68bn shares.
    row = _row(Ticker="SHEL.L", Currency="GBP", financialCurrency="USD", Price=40.33, trailingEps=3.38,
               bookValue=31.0, sharesOutstanding=5.684e9, netIncomeHistory=[17.84e9, 16.1e9])
    df, _ = screener._convert_reporting_currency(pd.DataFrame([row]), rate_fn=_usd_gbp)
    r = df.iloc[0]
    assert r["per_share_ccy"] == "reporting" and not r["currency_unverified"]
    assert math.isclose(r["trailingEps"], 3.38 * 0.75) and math.isclose(r["bookValue"], 31.0 * 0.75)
    assert math.isclose(r["netIncomeHistory"][0], 17.84e9 * 0.75)    # statements as before


def test_eps_already_in_the_quote_currency_is_left_alone():
    # Equinor: EPS NOK 36 against USD net income of USD 8.5bn on 2.37bn shares.
    row = _row(Ticker="EQNR.OL", Currency="NOK", financialCurrency="USD", Price=453.8, trailingEps=36.04,
               bookValue=165.9, sharesOutstanding=2.368e9, netIncomeHistory=[8.5e9], ebit=2.0e10)
    df, _ = screener._convert_reporting_currency(pd.DataFrame([row]), rate_fn=_usd_gbp)
    r = df.iloc[0]
    assert r["per_share_ccy"] == "quote" and not r["currency_unverified"]
    assert r["trailingEps"] == 36.04 and r["bookValue"] == 165.9
    assert math.isclose(r["ebit"], 2.0e10 * 10.0)                   # statements are still converted
    assert math.isclose(r["trailingPE"], 453.8 / 36.04)


def test_close_currencies_stay_unconverted():
    row = _row(Ticker="ULVR.L", Currency="GBP", financialCurrency="EUR", trailingEps=3.69, bookValue=6.3,
               sharesOutstanding=2.15e9, netIncomeHistory=[6.0e9])
    df, _ = screener._convert_reporting_currency(pd.DataFrame([row]), rate_fn=_usd_gbp)
    r = df.iloc[0]
    assert r["per_share_ccy"] == "close" and r["trailingEps"] == 3.69 and not r["currency_unverified"]


def test_no_fit_or_no_anchor_is_unverified():
    no_anchor = _row(Ticker="X.OL", Currency="NOK", financialCurrency="USD", sharesOutstanding=None)
    misfit = _row(Ticker="Y.OL", Currency="NOK", financialCurrency="USD", trailingEps=6.32,
                  sharesOutstanding=1e9, netIncomeHistory=[2.0e9])     # halfway between USD 2bn and NOK 20bn
    df, _ = screener._convert_reporting_currency(pd.DataFrame([no_anchor, misfit]), rate_fn=_usd_gbp)
    assert list(df["per_share_ccy"]) == ["unverified", "unverified"]
    assert df["currency_unverified"].all()
