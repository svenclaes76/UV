"""AppTest coverage for uvalu/pages_/dashboard.py.

Like tests/test_pages_risk.py, risk.assess_portfolio() runs for real with
only its network-touching _fetch_history() mocked out — dashboard.py wraps
the whole risk-card computation in a bare try/except, so this also exercises
that real integration instead of silently passing through the except branch.
"""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import portfolio
import risk as risk_module
from uvalu import nav as nav_registry
from uvalu.pages_ import dashboard as dashboard_page
from tests.conftest import make_screener_data_tuple, make_scored_row, make_scored_df, make_portfolio_df


@pytest.fixture(autouse=True)
def _clean_nav_registry():
    # uvalu.nav.pages is process-global mutable state shared across every
    # test file (see tests/test_pages_help.py's identical fixture) — clear
    # before AND restore after, since leaked real entries from an earlier
    # test file (e.g. test_app_smoke.py running the real app.py) could
    # otherwise still be present during this test too, not just afterward.
    saved = dict(nav_registry.pages)
    nav_registry.pages.clear()
    yield
    nav_registry.pages.clear()
    nav_registry.pages.update(saved)


def _fake_history(tickers, period="5y"):
    dates = pd.bdate_range("2023-01-01", periods=260)
    data = {t: (100 + i * 5) + pd.Series(range(260)).values * 0.05 for i, t in enumerate(tickers)}
    return pd.DataFrame(data, index=dates)


NAV_SETUP = """
import streamlit as st
from uvalu import nav as nav_registry
nav_registry.pages["screener"] = st.Page(lambda: None, title="Screener")
nav_registry.pages["settings"] = st.Page(lambda: None, title="Settings")
nav_registry.pages["risk"] = st.Page(lambda: None, title="Risk")
"""


def _run(monkeypatch, screener_tuple=None) -> AppTest:
    monkeypatch.setattr(dashboard_page, "_load_all_screener_data",
                        lambda *a, **k: screener_tuple or make_screener_data_tuple())
    monkeypatch.setattr(dashboard_page, "_load_cache", lambda: {})
    monkeypatch.setattr(dashboard_page, "_fetch_prices_cached", lambda tickers: {
        t: {"price": 110.0, "prev_close": 108.0, "day_change_pct": 1.8, "volume": 1000} for t in tickers
    })
    monkeypatch.setattr(risk_module, "_fetch_history", _fake_history)

    script_src = NAV_SETUP + """
from uvalu.pages_ import dashboard as dashboard_page
dashboard_page.render()
"""
    at = AppTest.from_string(script_src, default_timeout=60)
    at.run()
    return at


def test_shows_empty_state_when_no_portfolio(isolated_data, monkeypatch):
    at = _run(monkeypatch)
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "No portfolio yet" in "".join(s.value for s in at.subheader)


def test_shows_info_when_portfolio_empty_dataframe(isolated_data, monkeypatch):
    portfolio.save_portfolio(pd.DataFrame())
    at = _run(monkeypatch)
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "Your portfolio is empty" in "".join(i.value for i in at.info)


def test_renders_full_dashboard_for_populated_portfolio(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    at = _run(monkeypatch)
    assert not at.exception, [str(e.value) for e in at.exception]
    html = "".join(m.value for m in at.markdown)
    assert "Portfolio overview" in html
    assert "Current value" in html or "current value" in html.lower()


def test_shows_holdings_ladder_row(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    at = _run(monkeypatch)
    assert not at.exception, [str(e.value) for e in at.exception]
    html = "".join(m.value for m in at.markdown)
    assert "AAA.BR" in html
    assert "Holdings" in html


def test_shows_no_history_caption_when_value_history_missing(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    at = _run(monkeypatch)
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "No history yet" in "".join(c.value for c in at.caption)


def test_shows_value_chart_when_history_present(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    portfolio.save_value_history(pd.DataFrame([
        {"date": "2024-01-01", "invested": 1000.0, "value": 1000.0},
        {"date": "2024-01-02", "invested": 1000.0, "value": 1050.0},
    ]))
    at = _run(monkeypatch)
    assert not at.exception, [str(e.value) for e in at.exception]
    assert len(at.get("plotly_chart")) >= 1
