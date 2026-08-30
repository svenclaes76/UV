"""scoring.py holds the shared fundamental scorers; screener.py re-exports them
so `from screener import _financial_health_score` (etc.) keeps working and
risk.py imports them from scoring, not screener's private namespace."""
import pandas as pd

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
