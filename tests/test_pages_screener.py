"""AppTest coverage for uvalu/pages_/screener.py."""
import pandas as pd
from streamlit.testing.v1 import AppTest

import portfolio
from uvalu.pages_ import screener as screener_page
from tests.conftest import make_screener_data_tuple, make_scored_row, make_scored_df, USER_SETUP_SRC


def _run(monkeypatch, screener_tuple=None, fetch_progress=None) -> AppTest:
    monkeypatch.setattr(screener_page, "_load_all_screener_data",
                        lambda *a, **k: screener_tuple or make_screener_data_tuple())
    monkeypatch.setattr(screener_page, "_load_cache", lambda: {})
    monkeypatch.setattr(screener_page, "get_fetch_progress",
                        lambda: fetch_progress or {"running": False, "total": 0, "done": 0})

    def _script():
        import portfolio
        portfolio.set_user("test@example.com")
        from uvalu.pages_ import screener as screener_page
        screener_page.render()

    at = AppTest.from_function(_script, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def test_renders_with_no_data(isolated_data, monkeypatch):
    empty = make_scored_df([])
    at = _run(monkeypatch, screener_tuple=make_screener_data_tuple(exchange_df=empty))
    assert "No screener data available yet" in "".join(i.value for i in at.info)


def test_shows_ticker_row_for_default_buy_filter(isolated_data, monkeypatch):
    # Default Signal filter is ["BUY"]; the fake row's Decision="Strong Buy"
    # maps to the BUY signal, so it should survive the default filter set.
    at = _run(monkeypatch)
    html = "".join(m.value for m in at.markdown)
    assert "AAA.BR" in html
    assert "Alpha Corp" in html


def test_min_score_filter_excludes_low_scoring_row(isolated_data, monkeypatch):
    df = make_scored_df([make_scored_row(**{"Value Score": 10.0})])
    at = _run(monkeypatch, screener_tuple=make_screener_data_tuple(exchange_df=df))
    slider = at.slider(key="scr_min_score")
    slider.set_value(50)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "No stocks match these filters" in "".join(m.value for m in at.markdown)


def test_search_filters_by_ticker(isolated_data, monkeypatch):
    df = make_scored_df([make_scored_row(), make_scored_row(Ticker="BBB.BR", Name="Beta Corp")])
    at = _run(monkeypatch, screener_tuple=make_screener_data_tuple(exchange_df=df))
    search = at.text_input(key="scr_search")
    search.set_value("Beta")
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    html = "".join(m.value for m in at.markdown)
    assert "Beta Corp" in html
    assert "Alpha Corp" not in html


def test_reset_filters_button_clears_search(isolated_data, monkeypatch):
    df = make_scored_df([make_scored_row(), make_scored_row(Ticker="BBB.BR", Name="Beta Corp")])
    at = _run(monkeypatch, screener_tuple=make_screener_data_tuple(exchange_df=df))
    # "Beta" still matches one row (BBB.BR) — a search matching ZERO rows
    # crashes here instead (see test_pages_screener.py's flagged bug), which
    # isn't what this test is about.
    search = at.text_input(key="scr_search")
    search.set_value("Beta")
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "Alpha Corp" not in "".join(m.value for m in at.markdown)

    reset_buttons = [b for b in at.button if b.label == "Reset filters"]
    reset_buttons[0].click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "Alpha Corp" in "".join(m.value for m in at.markdown)


def test_portfolio_context_computed_when_holdings_present(isolated_data, monkeypatch):
    from tests.conftest import make_portfolio_df
    portfolio.save_portfolio(make_portfolio_df())
    at = _run(monkeypatch)
    assert not at.exception, [str(e.value) for e in at.exception]


def test_bust_cache_triggered_when_fair_value_column_missing(isolated_data, monkeypatch):
    # A stale-schema cache (predates a scoring-column addition) triggers a
    # cache bust. Real _bust_cache() calls st.rerun(), which halts the
    # script immediately (never reaching the code further down that
    # otherwise unconditionally accesses the now-missing "fair_value"
    # column) — the stub reproduces that halt via st.stop() instead of a
    # real rerun, avoiding the same infinite-rerun trap documented for
    # settings.py's Excel import (a bare no-op stub would let execution
    # fall through and crash on the missing column instead).
    calls = []

    def _bust_cache_stub():
        import streamlit as st
        calls.append(True)
        st.stop()

    monkeypatch.setattr(screener_page, "_bust_cache", _bust_cache_stub)
    stale_row = make_scored_row()
    del stale_row["fair_value"]
    df = make_scored_df([stale_row])
    _run(monkeypatch, screener_tuple=make_screener_data_tuple(exchange_df=df))
    assert calls == [True]


def test_bust_cache_triggered_when_a_non_first_exchange_is_stale(isolated_data, monkeypatch):
    # The staleness check used to only look at _exch_dfs[0] (brussels) --
    # since each ticker's cache entry refreshes independently, a schema
    # migration could leave a LATER exchange still missing the new column
    # while brussels already has it, and the reset would never fire. Put
    # good data in brussels (index 0) and stale data in amsterdam (index 1).
    calls = []

    def _bust_cache_stub():
        import streamlit as st
        calls.append(True)
        st.stop()

    monkeypatch.setattr(screener_page, "_bust_cache", _bust_cache_stub)
    good_df = make_scored_df([make_scored_row()])
    stale_row = make_scored_row(Ticker="BBB.AS")
    del stale_row["fair_value"]
    stale_df = make_scored_df([stale_row])
    empty = pd.DataFrame(columns=["Ticker"])
    tuple7 = (good_df, stale_df, empty, empty, empty, empty, empty)
    _run(monkeypatch, screener_tuple=tuple7)
    assert calls == [True]


def test_fetch_in_progress_shows_progress_caption(isolated_data, monkeypatch):
    at = _run(monkeypatch, fetch_progress={"running": True, "total": 10, "done": 3})
    caption_html = "".join(c.value for c in at.caption)
    assert "Updating data" in caption_html
    assert "3/10" in caption_html


def test_sector_filter_narrows_results(isolated_data, monkeypatch):
    df = make_scored_df([
        make_scored_row(sector="Technology"),
        make_scored_row(Ticker="BBB.BR", Name="Beta Corp", sector="Healthcare"),
    ])
    at = _run(monkeypatch, screener_tuple=make_screener_data_tuple(exchange_df=df))
    sector_sel = at.selectbox(key="scr_sector")
    sector_sel.set_value("Healthcare")
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    html = "".join(m.value for m in at.markdown)
    assert "Beta Corp" in html
    assert "Alpha Corp" not in html


def test_market_filter_narrows_results(isolated_data, monkeypatch):
    exch_df = make_scored_df([make_scored_row()])
    extra_df = make_scored_df([make_scored_row(Ticker="BBB.BR", Name="Beta Corp")])
    # Put BBB.BR in a DIFFERENT real exchange slot (amsterdam) so it gets a
    # different "Exchange" label than AAA.BR's "Brussels".
    tup = list(make_screener_data_tuple(exchange_df=exch_df))
    tup[1] = extra_df  # ALL_EXCHANGES[1] == "amsterdam"
    at = _run(monkeypatch, screener_tuple=tuple(tup))
    market_sel = at.selectbox(key="scr_market")
    market_sel.set_value("Amsterdam")
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    html = "".join(m.value for m in at.markdown)
    assert "Beta Corp" in html
    assert "Alpha Corp" not in html


def test_clicking_signal_header_sorts_by_signal(isolated_data, monkeypatch):
    at = _run(monkeypatch)
    signal_header = [b for b in at.button if b.key == "scr_sort_signal"][0]
    signal_header.click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert at.session_state["scr_sort_key"] == "signal"
    assert at.session_state["scr_sort_dir"] == "desc"

    # Clicking the SAME header again toggles direction instead of resetting it.
    signal_header = [b for b in at.button if b.key == "scr_sort_signal"][0]
    signal_header.click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert at.session_state["scr_sort_dir"] == "asc"


def test_star_button_adds_ticker_to_watchlist(isolated_data, monkeypatch):
    at = _run(monkeypatch)
    star_btn = [b for b in at.button if b.key == "scr_row_0_AAA.BR_action"][0]
    star_btn.click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert portfolio.load_watchlist() == {"AAA.BR"}


def test_star_button_removes_ticker_from_watchlist(isolated_data, monkeypatch):
    portfolio.save_watchlist({"AAA.BR"})
    portfolio.save_manual_tickers({"AAA.BR": "Alpha Corp"})
    at = _run(monkeypatch)
    star_btn = [b for b in at.button if b.key == "scr_row_0_AAA.BR_action"][0]
    star_btn.click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert portfolio.load_watchlist() == set()
    assert portfolio.load_manual_tickers() == {}


def test_star_button_disabled_for_viewer_role(isolated_data, monkeypatch):
    # The star toggles/persists a watchlist change (save_watchlist) -- a
    # real write, so it needs the same Viewer-role gate as every other
    # write action in the app (portfolio.py's Add/Edit/Sell, drawer.py's
    # Edit/Sell/Add).
    monkeypatch.setattr(screener_page, "_load_all_screener_data",
                        lambda *a, **k: make_screener_data_tuple())
    monkeypatch.setattr(screener_page, "_load_cache", lambda: {})
    monkeypatch.setattr(screener_page, "get_fetch_progress",
                        lambda: {"running": False, "total": 0, "done": 0})
    script = USER_SETUP_SRC + """
import streamlit as st
st.session_state["user_role"] = "Viewer"
from uvalu.pages_ import screener as screener_page
screener_page.render()
"""
    at = AppTest.from_string(script, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    star_btn = [b for b in at.button if b.key == "scr_row_0_AAA.BR_action"][0]
    assert star_btn.disabled
    assert portfolio.load_watchlist() == set()


def test_view_button_opens_drawer(isolated_data, monkeypatch):
    at = _run(monkeypatch)
    view_btn = [b for b in at.button if b.key == "scr_row_0_AAA.BR_view"][0]
    view_btn.click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "Six-model fair value" in "".join(m.value for m in at.markdown)
