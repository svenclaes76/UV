"""AppTest coverage for uvalu/pages_/screener.py."""
from streamlit.testing.v1 import AppTest

import portfolio
from uvalu.pages_ import screener as screener_page
from tests.conftest import make_screener_data_tuple, make_scored_row, make_scored_df


def _run(monkeypatch, screener_tuple=None) -> AppTest:
    monkeypatch.setattr(screener_page, "_load_all_screener_data",
                        lambda *a, **k: screener_tuple or make_screener_data_tuple())
    monkeypatch.setattr(screener_page, "_load_cache", lambda: {})
    monkeypatch.setattr(screener_page, "get_fetch_progress",
                        lambda: {"running": False, "total": 0, "done": 0})

    def _script():
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
