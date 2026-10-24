"""AppTest coverage for uvalu/pages_/screener.py."""
import pandas as pd
from streamlit.testing.v1 import AppTest

import portfolio
from uvalu.pages_ import screener as screener_page
from tests.conftest import make_screener_data_tuple, make_scored_row, make_scored_df, USER_SETUP_SRC


def _run(monkeypatch, screener_tuple=None, fetch_progress=None) -> AppTest:
    monkeypatch.setattr(screener_page, "_load_all_screener_data",
                        lambda *a, **k: screener_tuple or make_screener_data_tuple())
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


def test_renders_skeleton_when_no_data(isolated_data, monkeypatch):
    empty = make_scored_df([])
    at = _run(monkeypatch, screener_tuple=make_screener_data_tuple(exchange_df=empty))
    html = "".join(m.value for m in at.markdown)
    assert "Loading the screening universe" in html
    # Layout-matching skeleton: filter-bar and column-header shapes render
    # too, not just a generic shimmer card (uvalu/pages_/screener.py).
    assert "uv-skel-bar" in html
    assert "Company" in html and "Margin of safety" in html


def test_skeleton_shows_fetch_progress_when_running(isolated_data, monkeypatch):
    empty = make_scored_df([])
    at = _run(monkeypatch, screener_tuple=make_screener_data_tuple(exchange_df=empty),
              fetch_progress={"running": True, "total": 40, "done": 12})
    html = "".join(m.value for m in at.markdown)
    assert "12/40 companies scored" in html
    assert "uv-skel-bar" in html


def test_shows_ticker_row_at_the_default_filters(isolated_data, monkeypatch):
    at = _run(monkeypatch)
    html = "".join(m.value for m in at.markdown)
    assert "AAA.BR" in html
    assert "Alpha Corp" in html
    # AC2: the rows are registered as a table, sorted by composite score.
    (table,) = [t for t in at.session_state["_uv_tables"] if t["key"] == "scr_table_card"]
    assert table["header"] == "scr_col_header" and any("AAA-BR" in r for r in table["rows"])
    assert table["sort"] == ["scr_sort_score", "descending"] and table["names"] == {"0": "Watchlist"}


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


def test_renders_with_saved_portfolio_present(isolated_data, monkeypatch):
    # A saved portfolio used to trigger a per-render _load_cache() +
    # portfolio-fit-context computation whose result open_drawer never read
    # (WP-2 removed it). Kept as a smoke test that a non-empty portfolio on
    # disk still renders the screener cleanly.
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


def test_bust_cache_triggered_when_some_rows_are_stale(isolated_data, monkeypatch):
    # Each ticker's cache entry refreshes independently, so a schema
    # migration can leave some rows missing a new column while others
    # already have it. In the single universe frame (EX-W2) a column missing
    # on part of the rows comes back as NaN; a frame without the column at
    # all must trigger the reset.
    calls = []

    def _bust_cache_stub():
        import streamlit as st
        calls.append(True)
        st.stop()

    monkeypatch.setattr(screener_page, "_bust_cache", _bust_cache_stub)
    stale_row = make_scored_row(Ticker="BBB.AS")
    del stale_row["fair_value"]
    stale_df = make_scored_df([stale_row])
    _run(monkeypatch, screener_tuple=make_screener_data_tuple(exchange_df=stale_df))
    assert calls == [True]


def test_fetch_in_progress_shows_refresh_sweep(isolated_data, monkeypatch):
    # With rows already on screen, a running fetch shows the same
    # non-disruptive top-of-page sweep used elsewhere (Dashboard/Portfolio/
    # Risk's timed refresh) instead of a persistent "Updating data… N/M
    # tickers" text caption.
    at = _run(monkeypatch, fetch_progress={"running": True, "total": 10, "done": 3})
    caption_html = "".join(c.value for c in at.caption)
    markdown_html = "".join(m.value for m in at.markdown)
    assert "Updating data" not in caption_html
    assert "uvBar" in markdown_html


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
    # Two rows on different exchanges (EX-W2: one frame, keyed per row); the
    # Market filter shows the registry's official names (D10).
    df = make_scored_df([make_scored_row(),
                         make_scored_row(Ticker="BBB.AS", Name="Beta Corp")])
    at = _run(monkeypatch, screener_tuple=make_screener_data_tuple(exchange_df=df))
    market_sel = at.selectbox(key="scr_market")
    market_sel.set_value("Euronext Amsterdam")
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
    assert "Model fair values" in "".join(m.value for m in at.markdown)


def test_reset_filters_is_always_shown(isolated_data, monkeypatch):
    at = _run(monkeypatch)
    assert any(b.key == "scr_reset" for b in at.button)           # default filters too (SC-11)


def test_rank_column_numbers_rows_in_the_current_sort(isolated_data, monkeypatch):
    df = make_scored_df([make_scored_row(Ticker="LOW.BR", Name="Low NV", **{"Value Score": 40.0}),
                         make_scored_row(Ticker="TOP.PA", Name="Top SA", **{"Value Score": 90.0})])
    at = _run(monkeypatch, screener_tuple=make_screener_data_tuple(exchange_df=df))
    html = "".join(m.value for m in at.markdown)
    # Score descending: TOP.PA first. Exchange short codes, not city names.
    assert html.index("TOP.PA") < html.index("LOW.BR")
    assert ">PAR</span>" in html and ">BRU</span>" in html
    assert "font-size:12px;color:var(--muted);'>1</div>" in html


def test_hide_positions_i_own_drops_held_tickers(isolated_data, monkeypatch):
    portfolio.save_portfolio(pd.DataFrame([dict(ticker="AAA.BR", name="Alpha Corp", google_ticker="EBR:AAA",
                                                shares=10, purchase_value=1000.0, purchase_price=100.0,
                                                target_price=130.0, dividends=0.0, date_in="2023-01-01",
                                                date_out="")]))
    df = make_scored_df([make_scored_row(), make_scored_row(Ticker="BBB.BR", Name="Beta NV")])
    at = _run(monkeypatch, screener_tuple=make_screener_data_tuple(exchange_df=df))
    at.pills(key="scr_hide_owned_pill").set_value("owned").run()
    assert not at.exception, [str(e.value) for e in at.exception]
    html = "".join(m.value for m in at.markdown)
    assert "BBB.BR" in html and "AAA.BR" not in html


def test_hide_positions_i_own_matches_by_company(isolated_data, monkeypatch):
    # D19: held on a secondary line (AIR.DE), shown on the primary (AIR.PA).
    from uvalu import universe
    universe.save_choices({"airbus|Netherlands|": {"chosen": "AIR.PA", "lines": ["AIR.DE", "AIR.PA"]}})
    portfolio.save_portfolio(pd.DataFrame([dict(ticker="AIR.DE", name="Airbus SE", google_ticker="ETR:AIR",
                                                shares=10, purchase_value=1000.0, purchase_price=100.0,
                                                target_price=130.0, dividends=0.0, date_in="2023-01-01",
                                                date_out="")]))
    df = make_scored_df([make_scored_row(Ticker="AIR.PA", Name="Airbus SE"),
                         make_scored_row(Ticker="BBB.BR", Name="Beta NV")])
    at = _run(monkeypatch, screener_tuple=make_screener_data_tuple(exchange_df=df))
    at.pills(key="scr_hide_owned_pill").set_value("owned").run()
    assert not at.exception, [str(e.value) for e in at.exception]
    html = "".join(m.value for m in at.markdown)
    assert "BBB.BR" in html and "AIR.PA" not in html


def _with_pending_row():
    """A valued Undervalued row plus a No signal row (no fair value, score or margin)."""
    pending = make_scored_row(Ticker="PEND.BR", Name="Pending Peer NV", signal_code="pending",
                              fair_value=float("nan"), **{"Value Score": float("nan"), "MoS %": float("nan"),
                                                           "margin_of_safety": float("nan")})
    return make_screener_data_tuple(exchange_df=make_scored_df([make_scored_row(), pending]))


def test_default_signal_filter_selects_nothing(isolated_data, monkeypatch):
    at = _run(monkeypatch)
    assert list(at.session_state["scr_signal"]) == []
    assert "pending" in screener_page._SIGNAL_CHIPS


def test_no_signal_stock_is_listed_at_the_default_filters(isolated_data, monkeypatch):
    at = _run(monkeypatch, screener_tuple=_with_pending_row())
    html = "".join(m.value for m in at.markdown)
    assert "PEND.BR" in html and "AAA.BR" in html
    assert "2 of 2 European stocks" in html


def test_no_signal_stock_drops_out_when_min_margin_is_raised(isolated_data, monkeypatch):
    at = _run(monkeypatch, screener_tuple=_with_pending_row())
    at.slider(key="scr_min_mos").set_value(-15).run()
    assert not at.exception, [str(e.value) for e in at.exception]
    html = "".join(m.value for m in at.markdown)
    assert "PEND.BR" not in html and "AAA.BR" in html


def test_no_signal_stock_drops_out_when_min_score_is_raised(isolated_data, monkeypatch):
    at = _run(monkeypatch, screener_tuple=_with_pending_row())
    at.slider(key="scr_min_score").set_value(5).run()
    assert not at.exception, [str(e.value) for e in at.exception]
    html = "".join(m.value for m in at.markdown)
    assert "PEND.BR" not in html and "AAA.BR" in html


def test_no_signal_chip_filters_to_pending_rows(isolated_data, monkeypatch):
    at = _run(monkeypatch, screener_tuple=_with_pending_row())
    at.pills(key="scr_signal").set_value(["pending"]).run()
    assert not at.exception, [str(e.value) for e in at.exception]
    html = "".join(m.value for m in at.markdown)
    assert "PEND.BR" in html and "AAA.BR" not in html


def test_index_filter_keeps_members_only(isolated_data, monkeypatch):
    # EX-24: the Index filter after Market; only indices with members are listed.
    df = make_scored_df([make_scored_row(Ticker="AIR.PA", Name="Airbus SE", indices=["euro_stoxx_50", "cac_40"]),
                         make_scored_row(Ticker="BBB.BR", Name="Beta NV", indices=[])])
    at = _run(monkeypatch, screener_tuple=make_screener_data_tuple(exchange_df=df))
    sel = at.selectbox(key="scr_index")
    assert sel.options[0] == "All indices" and "EURO STOXX 50" in sel.options and "DAX" not in sel.options
    sel.set_value("euro_stoxx_50").run()
    assert not at.exception, [str(e.value) for e in at.exception]
    html = "".join(m.value for m in at.markdown)
    assert "AIR.PA" in html and "BBB.BR" not in html
