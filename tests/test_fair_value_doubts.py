"""V4 (model M4): model disagreement and implausible margins keep a stock
out of Undervalued (docs/valuation-model-review.md V4)."""

import pandas as pd

import screener as sc


def test_the_range_and_dispersion_of_the_models_are_reported():
    row = pd.Series({"Price": 10.0, "trailingEps": 1.0, "bookValue": 8.0})
    out = sc._fair_value_models(row)
    vals = [v for v in (out["graham_number"], out["pe_fair_value"]) if v]
    assert out["fv_low"] == round(min(vals), 2) and out["fv_high"] == round(max(vals), 2)
    assert out["fv_dispersion"] == round(max(vals) / min(vals), 3)


def test_doubt_flags():
    df = pd.DataFrame([
        {"fv_dispersion": 3.5, "margin_of_safety": 0.20},
        {"fv_dispersion": 2.0, "margin_of_safety": 0.95},   # TPG0.DE-like
        {"fv_dispersion": 2.0, "margin_of_safety": 0.30},
        {"fv_dispersion": None, "margin_of_safety": None},
    ])
    disagree, implausible = sc._fair_value_doubts(df)
    assert list(disagree) == [True, False, False, False]
    assert list(implausible) == [False, True, False, False]


def _universe(extra):
    rows = [{"Ticker": f"P{i}.PA", "Price": 10.0, "trailingEps": 1.0 + i / 20, "bookValue": 8.0,
             "trailingPE": 9.0, "sector": "Industrials"} for i in range(25)]
    return pd.DataFrame(rows + [extra])


def test_an_implausible_margin_is_never_undervalued_and_says_why():
    # A broken price far below every model value.
    extra = {"Ticker": "TPG0.DE", "Price": 0.88, "trailingEps": 1.83, "bookValue": 8.47,
             "trailingPE": 9.0, "sector": "Industrials", "beta": 1.0}
    out = sc.run_screener_from_df(_universe(extra), min_mos=0.10)
    r = out[out["Ticker"] == "TPG0.DE"].iloc[0]
    assert r["signal_code"] != sc.SIGNAL_UNDERVALUED
    assert "margin_implausible" in r["data_flags"]
    if r["signal_code"] == sc.SIGNAL_NEUTRAL:
        assert "data error" in sc.signal_reason(r, buy_threshold=70.0, min_mos=0.10)


def test_the_reason_for_disagreeing_models_shows_the_range():
    row = pd.Series({"signal_code": sc.SIGNAL_NEUTRAL, "Value Score": 80.0, "margin_of_safety": 0.30,
                     "fv_models_disagree": True, "fv_low": 5.0, "fv_high": 20.0})
    text = sc.signal_reason(row, buy_threshold=70.0, min_mos=0.10)
    assert "disagree" in text and "5.00" in text and "20.00" in text


def test_a_signal_kept_by_the_stability_rule_says_so():
    row = pd.Series({"signal_code": sc.SIGNAL_UNDERVALUED, "Value Score": 69.0, "margin_of_safety": 0.20})
    text = sc.signal_reason(row, buy_threshold=70.0, min_mos=0.10)
    assert "stability rule" in text and "at or above" not in text


def test_hysteresis_does_not_keep_a_doubtful_undervalued():
    df = pd.DataFrame([{"Ticker": "T.BR", "signal_code": sc.SIGNAL_NEUTRAL, "Value Score": 69.0,
                        "margin_of_safety": 0.20, "fv_basis_thin": False, "fv_models_disagree": True}])
    out = sc._apply_signal_hysteresis(df, {"T.BR": sc.SIGNAL_UNDERVALUED}, buy_threshold=70.0, min_mos=0.10)
    assert out.iloc[0] == sc.SIGNAL_NEUTRAL
