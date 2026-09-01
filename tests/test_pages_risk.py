"""AppTest coverage for uvalu/pages_/risk.py.

risk.assess_portfolio() runs for real (it's already unit-tested in
tests/test_algorithms.py) — only its network-touching _fetch_history() is
mocked, with a small synthetic 2-ticker/1-year price history, so the whole
8-stage pipeline exercises real code instead of a stubbed-out RiskReport.
"""
import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import portfolio
import risk as risk_module
import uvalu.data as uv_data
from uvalu.pages_ import risk as risk_page
from tests.conftest import (make_scored_row, make_scored_df,
                            make_portfolio_df, fake_portfolio_scored)


def _fake_history(tickers, period="5y"):
    dates = pd.bdate_range("2023-01-01", periods=260)
    data = {t: (100 + i * 5) + pd.Series(range(260)).values * 0.05 for i, t in enumerate(tickers)}
    return pd.DataFrame(data, index=dates)


def _fake_ff_csv(url):
    # risk.py's _stage4_factor otherwise makes a REAL network call to
    # Dartmouth's Fama-French data library — stub it with synthetic daily
    # factor returns spanning a wide enough range to overlap _fake_history's
    # dates (2023, ~1 trading year) with plenty of margin.
    dates = pd.bdate_range("2020-01-01", periods=1500)
    rng = np.random.default_rng(42)
    cols = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"] if "5_Factors" in url else ["WML"]
    return pd.DataFrame({c: rng.normal(0, 0.005, len(dates)) for c in cols}, index=dates)


def _run(monkeypatch, prices=None, risk_cache=None, portfolio_scored=None) -> AppTest:
    monkeypatch.setattr(uv_data, "_load_portfolio_scored",
                        fake_portfolio_scored(override=portfolio_scored))
    monkeypatch.setattr(uv_data, "load_fundamentals_cache", lambda: risk_cache or {})
    # fair_value/sector/country/div_rate now come from the scored screener
    # DataFrame (screener_tuple) instead of a separate fetch — only the live
    # price is fetched independently, matching what risk.py's render() does.
    monkeypatch.setattr(uv_data, "_fetch_prices_cached", lambda tickers: prices or {
        t: {"price": 110.0} for t in tickers
    })
    monkeypatch.setattr(risk_module, "_fetch_history", _fake_history)
    monkeypatch.setattr(risk_module, "_fetch_ff_csv", _fake_ff_csv)

    def _script():
        import portfolio
        portfolio.set_user("test@example.com")
        from uvalu.pages_ import risk as risk_page
        risk_page.render()

    at = AppTest.from_function(_script, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def test_shows_info_when_no_portfolio(isolated_data, monkeypatch):
    at = _run(monkeypatch)
    assert "No portfolio loaded" in "".join(i.value for i in at.info)


def test_renders_full_report_for_portfolio(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    at = _run(monkeypatch)
    html = "".join(m.value for m in at.markdown)
    assert "Risk assessment" in html
    assert "Risk factor breakdown" in html
    assert "Concentration" in html


def test_wires_price_autorefresh(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    calls: list[str] = []
    monkeypatch.setattr(risk_page, "price_autorefresh", lambda key: calls.append(key))
    _run(monkeypatch)
    assert calls == ["risk_refresh"]


def test_shows_holdings_contribution_rows(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    at = _run(monkeypatch)
    html = "".join(m.value for m in at.markdown)
    assert "AAA.BR" in html


def test_uses_cached_risk_report_within_ttl(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    calls = {"n": 0}

    def _counting_fetch(tickers, period="5y"):
        calls["n"] += 1
        return _fake_history(tickers, period)

    monkeypatch.setattr(risk_module, "_fetch_history", _counting_fetch)
    monkeypatch.setattr(risk_module, "_fetch_ff_csv", _fake_ff_csv)

    def _script():
        import portfolio
        portfolio.set_user("test@example.com")
        from uvalu.pages_ import risk as risk_page
        risk_page.render()

    monkeypatch.setattr(uv_data, "_load_portfolio_scored", fake_portfolio_scored())
    monkeypatch.setattr(uv_data, "load_fundamentals_cache", lambda: {})
    monkeypatch.setattr(uv_data, "_fetch_prices_cached", lambda tickers: {
        t: {"price": 110.0} for t in tickers
    })

    at = AppTest.from_function(_script, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert calls["n"] == 1

    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert calls["n"] == 1  # second render reuses the cached report


def test_risk_assessment_failure_shows_error(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    monkeypatch.setattr(uv_data, "_load_portfolio_scored", fake_portfolio_scored())
    monkeypatch.setattr(uv_data, "load_fundamentals_cache", lambda: {})
    monkeypatch.setattr(uv_data, "_fetch_prices_cached", lambda tickers: {
        t: {"price": 110.0} for t in tickers
    })

    def _boom(*_a, **_k):
        raise RuntimeError("boom")
    monkeypatch.setattr(risk_module, "assess_portfolio", _boom)

    def _script():
        import portfolio
        portfolio.set_user("test@example.com")
        from uvalu.pages_ import risk as risk_page
        risk_page.render()

    at = AppTest.from_function(_script, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "Risk assessment failed" in "".join(e.value for e in at.error)


def test_factor_analysis_unavailable_with_short_history(isolated_data, monkeypatch):
    # <60 days of price history -> _stage4_factor's own short-circuit,
    # never reaching (the otherwise real-network) _fetch_ff_csv at all.
    def _short_history(tickers, period="5y"):
        dates = pd.bdate_range("2024-01-01", periods=10)
        return pd.DataFrame({t: [100.0 + i for i in range(10)] for t in tickers}, index=dates)

    monkeypatch.setattr(risk_module, "_fetch_history", _short_history)
    monkeypatch.setattr(uv_data, "_load_portfolio_scored", fake_portfolio_scored())
    monkeypatch.setattr(uv_data, "load_fundamentals_cache", lambda: {})
    monkeypatch.setattr(uv_data, "_fetch_prices_cached", lambda tickers: {
        t: {"price": 110.0} for t in tickers
    })
    portfolio.save_portfolio(make_portfolio_df())

    def _script():
        import portfolio
        portfolio.set_user("test@example.com")
        from uvalu.pages_ import risk as risk_page
        risk_page.render()

    at = AppTest.from_function(_script, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "Factor analysis unavailable" in "".join(c.value for c in at.caption)


def test_vetoed_holding_shows_veto_flag(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    # Held ticker → its scored row comes from the portfolio lane now.
    at = _run(monkeypatch, portfolio_scored=make_scored_df([make_scored_row(veto=True)]))
    html = "".join(m.value for m in at.markdown)
    assert "remain(s) under a hard veto" in html
    assert ">Veto<" in html


def test_critical_risk_position_shows_flag(isolated_data, monkeypatch):
    # weight=100% (+2), beta>1.5 (+2), overvalued >10% (+2), poor financial
    # health (+2) -> 8 pts, comfortably over the >=5 "Critical" threshold —
    # see risk.py's _position_rating scoring.
    portfolio.save_portfolio(make_portfolio_df())
    at = _run(
        monkeypatch,
        portfolio_scored=make_scored_df([make_scored_row(fair_value=100.0)]),
        prices={"AAA.BR": {"price": 150.0}},
        risk_cache={"AAA.BR": {"beta": 2.0, "debtToEquity": 900.0, "currentRatio": 0.1,
                               "interestCoverage": 0.1, "freeCashflow": -1e9, "netIncome": 1e6}},
    )
    html = "".join(m.value for m in at.markdown)
    assert ">Critical<" in html


def test_view_button_opens_drawer(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    at = _run(monkeypatch)
    view_btn = [b for b in at.button if b.label == "View"][0]
    view_btn.click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "Six-model fair value" in "".join(m.value for m in at.markdown)


class TestLoadingTier:
    def test_low_at_boundary(self):
        assert risk_page._loading_tier(0.75) == ("Low", "var(--uv-mint)")

    def test_moderate(self):
        assert risk_page._loading_tier(1.0) == ("Moderate", "#C98A3A")

    def test_elevated(self):
        assert risk_page._loading_tier(2.0) == ("Elevated", "var(--down-txt)")


class _P:
    def __init__(self, ticker, weight, beta, vol_annual):
        self.ticker, self.weight, self.beta, self.vol_annual = ticker, weight, beta, vol_annual


class TestRiskContributions:
    def test_falls_back_to_weight_times_abs_beta_without_corr(self):
        profs = [_P("A", 0.6, 1.2, 0.30), _P("B", 0.4, 0.5, 0.20)]
        raw, method = risk_page._risk_contributions(profs, None)
        assert method == "beta"
        assert raw == pytest.approx([0.6 * 1.2, 0.4 * 0.5])

    def test_empty_profiles(self):
        assert risk_page._risk_contributions([], None) == ([], "beta")

    def test_variance_basis_lifts_a_high_vol_low_beta_name(self):
        # B: half the beta of A but ~2x the vol. Under weight x |beta| its
        # share is tiny; under the variance decomposition its own vol makes it
        # a real contributor (the CEK.DE case from the review).
        profs = [_P("A", 0.5, 1.2, 0.20), _P("B", 0.5, 0.4, 0.55)]
        corr = pd.DataFrame([[1.0, 0.1], [0.1, 1.0]], index=["A", "B"], columns=["A", "B"])
        raw, method = risk_page._risk_contributions(profs, corr)
        assert method == "variance"
        beta_share_B = (0.5 * 0.4) / (0.5 * 1.2 + 0.5 * 0.4)
        var_share_B = raw[1] / sum(raw)
        assert var_share_B > beta_share_B
        assert var_share_B > 0.5          # the higher-vol name now dominates

    def test_profile_missing_from_corr_matrix_still_contributes(self):
        profs = [_P("A", 0.5, 1.0, 0.25), _P("ZZZ", 0.5, 1.0, 0.25)]
        corr = pd.DataFrame([[1.0]], index=["A"], columns=["A"])   # ZZZ absent
        raw, method = risk_page._risk_contributions(profs, corr)
        assert method == "variance"
        assert all(x >= 0 for x in raw) and sum(raw) > 0
