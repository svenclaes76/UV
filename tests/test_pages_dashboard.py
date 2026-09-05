"""AppTest coverage for uvalu/pages_/dashboard.py.

Like tests/test_pages_risk.py, risk.assess_portfolio() runs for real with
only its network-touching _fetch_history() mocked out — dashboard.py wraps
the whole risk-card computation in a bare try/except, so this also exercises
that real integration instead of silently passing through the except branch.
"""
import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import portfolio
import risk as risk_module
import uvalu.data as uv_data
from uvalu import nav as nav_registry
from uvalu.pages_ import dashboard as dashboard_page
from tests.conftest import (make_scored_row, make_scored_df, make_portfolio_df,
                            fake_portfolio_scored, USER_SETUP_SRC, settle_background_risk)


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


def _fake_ff_csv(url):
    # See tests/test_pages_risk.py's identical helper: _stage4_factor
    # otherwise makes a REAL network call to Dartmouth's Fama-French data
    # library whenever assess_portfolio() runs with >=60 days of history
    # (true here, with the 260-day _fake_history above).
    dates = pd.bdate_range("2020-01-01", periods=1500)
    rng = np.random.default_rng(42)
    cols = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"] if "5_Factors" in url else ["WML"]
    return pd.DataFrame({c: rng.normal(0, 0.005, len(dates)) for c in cols}, index=dates)


NAV_SETUP = """
import streamlit as st
from uvalu import nav as nav_registry
nav_registry.pages["screener"] = st.Page(lambda: None, title="Screener")
nav_registry.pages["settings"] = st.Page(lambda: None, title="Settings")
nav_registry.pages["risk"] = st.Page(lambda: None, title="Risk")
"""


def _run(monkeypatch, scored=None, with_risk_cache=False, prices=None, history_backfill_running=False) -> AppTest:
    _fake_scored = fake_portfolio_scored(override=scored)
    _fake_cache = lambda: ({"AAA.BR": {"Price": 100.0}} if with_risk_cache else {})
    _fake_prices = lambda tickers: prices or {
        t: {"price": 110.0, "prev_close": 108.0, "day_change_pct": 1.8, "volume": 1000} for t in tickers
    }
    monkeypatch.setattr(dashboard_page, "_load_portfolio_scored", _fake_scored)
    # A non-empty cache is required to even ENTER the risk-assessment try
    # block (`if ... and _db_risk_cache:`) — most tests leave this empty to
    # skip that path entirely and keep runs fast; the dedicated risk-card
    # tests below turn it on.
    monkeypatch.setattr(dashboard_page, "load_fundamentals_cache", _fake_cache)
    monkeypatch.setattr(dashboard_page, "_fetch_prices_cached", _fake_prices)
    # The risk-card path now goes through uvalu.data.load_portfolio_risk (the
    # shared builder the Risk page also uses, WP-DQ4), which reads these names
    # from the uvalu.data module namespace rather than the page's.
    monkeypatch.setattr(uv_data, "_load_portfolio_scored", _fake_scored)
    monkeypatch.setattr(uv_data, "load_fundamentals_cache", _fake_cache)
    monkeypatch.setattr(uv_data, "_fetch_prices_cached", _fake_prices)
    monkeypatch.setattr(risk_module, "_fetch_history", _fake_history)
    monkeypatch.setattr(risk_module, "_fetch_ff_csv", _fake_ff_csv)
    # Defaults to "nothing to backfill" so tests that don't care about the
    # value-history chart never spawn a real background thread (which would
    # make real yfinance calls). Tests exercising that path pass
    # history_backfill_running=True instead of monkeypatching this themselves
    # — this call runs last, so a test-level monkeypatch.setattr() made
    # before calling _run() would just get clobbered by the line below.
    monkeypatch.setattr(dashboard_page, "ensure_value_history_fresh",
                        lambda *a: history_backfill_running)

    script_src = USER_SETUP_SRC + NAV_SETUP + """
from uvalu.pages_ import dashboard as dashboard_page
dashboard_page.render()
"""
    at = AppTest.from_string(script_src, default_timeout=60)
    at.run()
    settle_background_risk(at)
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


def test_wires_price_autorefresh(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    calls: list[str] = []
    monkeypatch.setattr(dashboard_page, "price_autorefresh", lambda key: calls.append(key))
    at = _run(monkeypatch)
    assert not at.exception, [str(e.value) for e in at.exception]
    assert calls == ["dashboard_refresh"]


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
    caption_html = "".join(c.value for c in at.caption)
    assert "No history yet" in caption_html
    # The old copy pointed at a "Rebuild history" button that no longer
    # exists anywhere in the app — backfill is automatic now.
    assert "Rebuild history" not in caption_html


def test_shows_chart_skeleton_while_backfill_runs(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    at = _run(monkeypatch, history_backfill_running=True)
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "No history yet" not in "".join(c.value for c in at.caption)
    assert "uv-skel-bar" in "".join(m.value for m in at.markdown)


def test_shows_value_chart_when_history_present(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    portfolio.save_value_history(pd.DataFrame([
        {"date": "2024-01-01", "invested": 1000.0, "value": 1000.0},
        {"date": "2024-01-02", "invested": 1000.0, "value": 1050.0},
    ]))
    at = _run(monkeypatch)
    assert not at.exception, [str(e.value) for e in at.exception]
    assert len(at.get("plotly_chart")) >= 1


def test_refresh_button_clears_cache_and_reruns(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    calls = []
    monkeypatch.setattr(dashboard_page.st, "cache_data",
                        type("C", (), {"clear": staticmethod(lambda: calls.append(True))})())
    at = _run(monkeypatch)
    refresh_btn = [b for b in at.button if b.key == "db_refresh"][0]
    refresh_btn.click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert calls == [True]


def test_shows_dividends_received_kpi_when_no_dividend_yield(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    empty_scr = make_scored_df([])
    at = _run(monkeypatch, scored=empty_scr)
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "Dividends received" in "".join(m.value for m in at.markdown)


def test_date_range_filter_narrows_chart_view(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    dates = pd.bdate_range("2024-01-01", periods=100)
    portfolio.save_value_history(pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "invested": [1000.0] * 100,
        "value": [1000.0 + i for i in range(100)],
    }))
    at = _run(monkeypatch)
    range_sel = at.segmented_control(key="db_range")
    range_sel.set_value("1M")
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]


def test_benchmark_columns_add_chart_traces_and_legend_pills(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    portfolio.save_value_history(pd.DataFrame([
        {"date": "2024-01-01", "invested": 1000.0, "value": 1000.0,
         "benchmark_spx": 1000.0, "benchmark_stoxx": 1000.0},
        {"date": "2024-01-02", "invested": 1000.0, "value": 1050.0,
         "benchmark_spx": 1010.0, "benchmark_stoxx": 1005.0},
    ]))
    at = _run(monkeypatch)
    assert not at.exception, [str(e.value) for e in at.exception]
    assert len(at.pills) == 1
    assert set(at.pills[0].options) == {"S&P 500", "Euro Stoxx 50"}


def test_full_analysis_button_navigates_to_risk_page(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    at = _run(monkeypatch)
    full_analysis_btn = [b for b in at.button if b.key == "db_conv_full_analysis"][0]
    full_analysis_btn.click().run()
    assert not at.exception, [str(e.value) for e in at.exception]


def test_risk_card_renders_when_cache_and_history_available(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    at = _run(monkeypatch, with_risk_cache=True)
    assert not at.exception, [str(e.value) for e in at.exception]
    html = "".join(m.value for m in at.markdown)
    assert "Portfolio risk score" in html
    assert "Max drawdown" in html


def test_multi_lot_same_ticker_does_not_crash(isolated_data, monkeypatch):
    # add_position() appends rather than merging, so the same ticker can
    # appear in two portfolio rows (separate lots). Several calculations
    # (fwd income, conviction score, upcoming-dividends shares) used to
    # build a ticker-indexed Series via set_index("ticker") and then
    # .reindex()/.map() from it -- pandas raises when the source index has
    # duplicate labels, so a two-lot holding crashed the whole page.
    two_lots = [
        dict(ticker="AAA.BR", name="Alpha Corp", google_ticker="EBR:AAA",
             shares=10, purchase_value=1000.0, purchase_price=100.0,
             target_price=130.0, dividends=20.0, date_in="2023-01-01", date_out=""),
        dict(ticker="AAA.BR", name="Alpha Corp", google_ticker="EBR:AAA",
             shares=5, purchase_value=550.0, purchase_price=110.0,
             target_price=130.0, dividends=0.0, date_in="2024-01-01", date_out=""),
    ]
    portfolio.save_portfolio(make_portfolio_df(rows=two_lots))
    future_row = make_scored_row(exDividendDate="15-01-2099", dividendRate=3.2, dividendYield=0.03)
    at = _run(monkeypatch, scored=make_scored_df([future_row]))
    assert not at.exception, [str(e.value) for e in at.exception]
    html = "".join(m.value for m in at.markdown)
    assert "Composite conviction" in html


def test_risk_label_never_disagrees_with_risk_page_bands(isolated_data, monkeypatch):
    # The dashboard's simplified 3-tier gauge must never contradict
    # risk.py's own SCORE_LOW/SCORE_MODERATE bands for the same score --
    # it used to use unrelated hand-picked 35/65 boundaries.
    portfolio.save_portfolio(make_portfolio_df())
    at = _run(monkeypatch, with_risk_cache=True)
    assert not at.exception, [str(e.value) for e in at.exception]
    html = "".join(m.value for m in at.markdown)
    assert f"#1DD6A4 {risk_module.SCORE_LOW}%" in html
    assert f"#C98A3A {risk_module.SCORE_MODERATE}%" in html


def test_conviction_score_renders_from_scored_holdings(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    at = _run(monkeypatch)
    assert not at.exception, [str(e.value) for e in at.exception]
    html = "".join(m.value for m in at.markdown)
    assert "Composite conviction" in html


def test_holdings_view_details_opens_drawer(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    at = _run(monkeypatch)
    view_btn = [b for b in at.button if b.label == "View details"][0]
    view_btn.click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "Six-model fair value" in "".join(m.value for m in at.markdown)


def test_holdings_no_screener_data_shows_caption(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    empty_scr = make_scored_df([])
    at = _run(monkeypatch, scored=empty_scr)
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "No screener data available for your holdings" in "".join(c.value for c in at.caption)


def test_upcoming_dividend_row_renders_for_future_ex_date(isolated_data, monkeypatch):
    from tests.conftest import make_scored_row
    portfolio.save_portfolio(make_portfolio_df())
    future_row = make_scored_row(exDividendDate="15-01-2099", dividendRate=3.2, dividendYield=0.03)
    at = _run(monkeypatch, scored=make_scored_df([future_row]))
    assert not at.exception, [str(e.value) for e in at.exception]
    html = "".join(m.value for m in at.markdown)
    assert "Alpha Corp" in html


def test_upcoming_dividends_no_cached_dates_shows_caption(isolated_data, monkeypatch):
    from tests.conftest import make_scored_row
    portfolio.save_portfolio(make_portfolio_df())
    no_date_row = make_scored_row(exDividendDate=None)
    at = _run(monkeypatch, scored=make_scored_df([no_date_row]))
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "Ex-dividend dates not yet in cache" in "".join(c.value for c in at.caption)


def test_top_movers_no_price_data_shows_caption(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    at = _run(monkeypatch, prices={"AAA.BR": {"price": 110.0, "prev_close": 108.0,
                                              "day_change_pct": None, "volume": 1000}})
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "No daily price data available" in "".join(c.value for c in at.caption)
