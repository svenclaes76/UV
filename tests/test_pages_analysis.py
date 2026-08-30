"""AppTest coverage for uvalu/pages_/analysis.py."""
import pandas as pd
import yfinance as yf
from streamlit.testing.v1 import AppTest

import portfolio
from uvalu.pages_ import analysis as analysis_page
from tests.conftest import make_screener_data_tuple, make_scored_row, make_scored_df, make_portfolio_df, USER_SETUP_SRC


def _run(monkeypatch, ticker="AAA.BR", screener_tuple=None) -> AppTest:
    monkeypatch.setattr(analysis_page, "_load_all_screener_data",
                        lambda *a, **k: screener_tuple or make_screener_data_tuple())

    class FakeTicker:
        def __init__(self, t):
            pass

        def history(self, period="1y"):
            return pd.DataFrame()

    monkeypatch.setattr(yf, "Ticker", FakeTicker)

    # AppTest.from_function re-executes a function's SOURCE TEXT with no
    # closure over enclosing variables (see tests/test_pages_admin.py), so
    # the ticker is baked into the script text via from_string instead.
    ticker_line = f'st.session_state["_analysis_ticker"] = {ticker!r}' if ticker is not None else ""
    script_src = USER_SETUP_SRC + f"""
import streamlit as st
from uvalu.pages_ import analysis as analysis_page
{ticker_line}
analysis_page.render()
"""
    at = AppTest.from_string(script_src, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def test_shows_info_when_no_ticker_selected(isolated_data, monkeypatch):
    at = _run(monkeypatch, ticker=None)
    assert "No stock selected" in "".join(i.value for i in at.info)


def test_shows_warning_when_ticker_not_found(isolated_data, monkeypatch):
    empty = make_scored_df([])
    at = _run(monkeypatch, ticker="ZZZ.BR", screener_tuple=make_screener_data_tuple(exchange_df=empty))
    assert "No data found" in "".join(w.value for w in at.warning)


def test_renders_full_analysis_for_matched_ticker(isolated_data, monkeypatch):
    at = _run(monkeypatch, ticker="AAA.BR")
    html = "".join(m.value for m in at.markdown)
    assert "AAA.BR" in html
    assert "Composite fair value" in html
    assert "Signal sub-scores" in html
    assert "Financials" in html
    assert "Hard-veto checks" in html


def test_shows_veto_banner_when_row_is_vetoed(isolated_data, monkeypatch):
    df = make_scored_df([make_scored_row(veto=True)])
    at = _run(monkeypatch, ticker="AAA.BR", screener_tuple=make_screener_data_tuple(exchange_df=df))
    html = "".join(m.value for m in at.markdown)
    assert "Hard veto active" in html


def test_leverage_exempt_sector_debt_check_passes_despite_high_de(isolated_data, monkeypatch):
    # A Financial Services stock with D/E over the veto threshold is exempt
    # from that specific check (screener.py's LEVERAGE_EXEMPT_SECTORS) --
    # the "Debt / equity below X×" row must show as passing, not a red ✕,
    # since the real _hard_veto formula doesn't count this against it.
    df = make_scored_df([make_scored_row(sector="Financial Services", debtToEquity=900.0, veto=False)])
    at = _run(monkeypatch, ticker="AAA.BR", screener_tuple=make_screener_data_tuple(exchange_df=df))
    html = "".join(m.value for m in at.markdown)
    assert "sector-exempt" in html


def test_single_bad_fcf_year_passes_the_positive_fcf_check(isolated_data, monkeypatch):
    # A single negative FCF year no longer vetoes once 3-year history
    # exists -- the "Positive free cash flow" check must agree and show a
    # pass, not re-derive a stricter single-period check that disagrees
    # with the real _fcf_hard_veto formula.
    df = make_scored_df([make_scored_row(
        freeCashflow=-1.0, fcfHistory=[-1.0, 50.0, 80.0], veto=False)])
    at = _run(monkeypatch, ticker="AAA.BR", screener_tuple=make_screener_data_tuple(exchange_df=df))
    html = "".join(m.value for m in at.markdown)
    assert "Positive free cash flow" in html
    # Same row must not show the veto banner (it isn't actually vetoed).
    assert "Hard veto active" not in html


def test_dividend_flag_alone_does_not_fail_the_veto_check_when_coverage_is_fine(isolated_data, monkeypatch):
    # Div Flag == "At Risk" AND coverage < 1.0x is a single combined
    # sub-condition in the real _hard_veto formula (see components.py's
    # veto_reason_str) -- flagged-but-adequately-covered must still show
    # as PASSING here, not a red X for a factor that isn't actually
    # contributing to a veto in this state.
    df = make_scored_df([make_scored_row(**{"Div Flag": "At Risk"}, dividendCoverage=1.5, veto=False)])
    at = _run(monkeypatch, ticker="AAA.BR", screener_tuple=make_screener_data_tuple(exchange_df=df))
    _rows = [m.value for m in at.markdown if "Dividend coverage adequate" in m.value]
    assert len(_rows) == 1
    assert "✓" in _rows[0]
    assert "✕" not in _rows[0]


def test_dividend_check_fails_only_when_both_flag_and_coverage_are_bad(isolated_data, monkeypatch):
    df = make_scored_df([make_scored_row(**{"Div Flag": "At Risk"}, dividendCoverage=0.5, veto=False)])
    at = _run(monkeypatch, ticker="AAA.BR", screener_tuple=make_screener_data_tuple(exchange_df=df))
    _rows = [m.value for m in at.markdown if "Dividend coverage adequate" in m.value]
    assert len(_rows) == 1
    assert "✕" in _rows[0]


def test_trend_check_passes_with_no_multi_year_history(isolated_data, monkeypatch):
    # The default fake row carries no statement history → _trend_veto is empty
    # → the "No adverse multi-year trend" row must render as passing.
    df = make_scored_df([make_scored_row(veto=False)])
    at = _run(monkeypatch, ticker="AAA.BR", screener_tuple=make_screener_data_tuple(exchange_df=df))
    _rows = [m.value for m in at.markdown if "No adverse multi-year trend" in m.value]
    assert len(_rows) == 1
    assert "✓" in _rows[0] and "✕" not in _rows[0]


def test_trend_check_fails_on_multi_year_revenue_decline(isolated_data, monkeypatch):
    df = make_scored_df([make_scored_row(revenueHistory=[60.0, 80.0, 95.0, 110.0], veto=True)])
    at = _run(monkeypatch, ticker="AAA.BR", screener_tuple=make_screener_data_tuple(exchange_df=df))
    _rows = [m.value for m in at.markdown if "No adverse multi-year trend" in m.value]
    assert len(_rows) == 1
    assert "✕" in _rows[0]
    assert "revenue fell" in _rows[0]


def test_shows_held_position_when_ticker_in_portfolio(isolated_data, monkeypatch):
    portfolio.save_portfolio(make_portfolio_df())
    at = _run(monkeypatch, ticker="AAA.BR")
    html = "".join(m.value for m in at.markdown)
    assert "shares" in html.lower()


def test_shows_not_held_when_ticker_not_in_portfolio(isolated_data, monkeypatch):
    at = _run(monkeypatch, ticker="AAA.BR")
    html = "".join(m.value for m in at.markdown)
    assert "Not held" in html


def test_renders_price_chart_when_history_available(isolated_data, monkeypatch):
    monkeypatch.setattr(analysis_page, "_load_all_screener_data",
                        lambda *a, **k: make_screener_data_tuple())

    class FakeTicker:
        def __init__(self, t):
            pass

        def history(self, period="1y"):
            dates = pd.bdate_range("2023-01-01", periods=30, tz="UTC")
            return pd.DataFrame({"Close": [100.0 + i for i in range(30)]}, index=dates)

    monkeypatch.setattr(yf, "Ticker", FakeTicker)

    at = AppTest.from_string(
        USER_SETUP_SRC + """
import streamlit as st
from uvalu.pages_ import analysis as analysis_page
st.session_state["_analysis_ticker"] = "AAA.BR"
analysis_page.render()
""",
        default_timeout=60,
    )
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert len(at.get("plotly_chart")) == 1
