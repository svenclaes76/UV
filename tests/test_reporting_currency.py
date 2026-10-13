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
