"""scoring.py holds the shared fundamental scorers; screener.py re-exports them
so `from screener import _financial_health_score` (etc.) keeps working and
risk.py imports them from scoring, not screener's private namespace."""
import pandas as pd
import pytest

import risk
import scoring
import screener


def test_screener_reexports_are_the_scoring_objects():
    for name in ("_clamp", "_get_num", "_financial_health_score",
                 "_earnings_quality_score", "_dividend_sustainability_flag"):
        assert getattr(screener, name) is getattr(scoring, name)


def test_risk_imports_scorers_from_scoring_not_screener():
    assert risk._financial_health_score is scoring._financial_health_score
    assert risk._earnings_quality_score is scoring._earnings_quality_score
    assert risk._dividend_sustainability_flag is scoring._dividend_sustainability_flag


def test_scorers_still_produce_neutral_on_empty_row():
    assert scoring._financial_health_score(pd.Series({})) == 5.0
    assert scoring._earnings_quality_score(pd.Series({})) == 5.0
    assert scoring._dividend_sustainability_flag(pd.Series({})) == ""


def test_latest_from_history():
    f = scoring._latest_from_history
    assert f(pd.Series({"h": [3.0, 2.0, 1.0]}), "h") == 3.0
    assert f(pd.Series({"h": [float("nan"), 2.0]}), "h") == 2.0   # skips leading NaN
    assert f(pd.Series({"h": []}), "h") is None
    assert f(pd.Series({"h": float("nan")}), "h") is None         # reindexed scalar, not a list
    assert f(pd.Series({}), "h") is None                          # column absent


def test_earnings_quality_accrual_uses_cfo_history_then_fcf():
    # CFO from the statement history is preferred
    with_cfo = scoring._earnings_quality_score(pd.Series({
        "freeCashflow": 100.0, "netIncome": 100.0,
        "cfoHistory": [40.0], "totalAssetsHistory": [1000.0]}))
    # accr = (100-40)/1000 = 0.06 -> 10 - (0.06/0.15)*10 = 6.0; mean(8.0, 6.0) = 7.0
    assert with_cfo == pytest.approx(7.0)

    # no CFO history -> freeCashflow stands in for CFO
    with_fcf = scoring._earnings_quality_score(pd.Series({
        "freeCashflow": 40.0, "netIncome": 100.0,
        "totalAssetsHistory": [1000.0]}))
    # conversion: 5 + (40/100)*3 = 6.2 ; accr = (100-40)/1000 = 0.06 -> 6.0 ; mean 6.1
    assert with_fcf == pytest.approx(6.1)
