"""AppTest coverage for uvalu/pages_/risk.py.

risk.assess_portfolio() runs for real (it's already unit-tested in
tests/test_algorithms.py) — only its network-touching _fetch_history() is
mocked, with a small synthetic 2-ticker/1-year price history, so the whole
8-stage pipeline exercises real code instead of a stubbed-out RiskReport.
"""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import portfolio
import risk as risk_module
from uvalu.pages_ import risk as risk_page
from tests.conftest import make_screener_data_tuple, make_scored_row, make_scored_df, make_portfolio_df


def _fake_history(tickers, period="5y"):
    dates = pd.bdate_range("2023-01-01", periods=260)
    data = {t: (100 + i * 5) + pd.Series(range(260)).values * 0.05 for i, t in enumerate(tickers)}
    return pd.DataFrame(data, index=dates)


def _run(monkeypatch, screener_tuple=None) -> AppTest:
    monkeypatch.setattr(risk_page, "_load_all_screener_data",
                        lambda *a, **k: screener_tuple or make_screener_data_tuple())
    monkeypatch.setattr(risk_page, "_load_cache", lambda: {})
    monkeypatch.setattr(risk_page, "_fetch_live_data", lambda tickers: {
        t: {"price": 110.0, "fair_value": 122.0, "sector": "Technology", "country": "Belgium", "div_rate": 3.2}
        for t in tickers
    })
    monkeypatch.setattr(risk_module, "_fetch_history", _fake_history)

    def _script():
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

    def _script():
        from uvalu.pages_ import risk as risk_page
        risk_page.render()

    monkeypatch.setattr(risk_page, "_load_all_screener_data", lambda *a, **k: make_screener_data_tuple())
    monkeypatch.setattr(risk_page, "_load_cache", lambda: {})
    monkeypatch.setattr(risk_page, "_fetch_live_data", lambda tickers: {
        t: {"price": 110.0, "fair_value": 122.0, "sector": "Technology", "country": "Belgium", "div_rate": 3.2}
        for t in tickers
    })

    at = AppTest.from_function(_script, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert calls["n"] == 1

    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert calls["n"] == 1  # second render reuses the cached report
