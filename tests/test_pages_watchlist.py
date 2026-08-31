"""AppTest coverage for uvalu/pages_/watchlist.py."""
import yfinance as yf
from streamlit.testing.v1 import AppTest

import portfolio
import settings
from uvalu.pages_ import watchlist as watchlist_page
from tests.conftest import make_screener_data_tuple, make_scored_row, USER_SETUP_SRC


def _run(monkeypatch, screener_tuple=None, fetch_progress=None) -> AppTest:
    monkeypatch.setattr(watchlist_page, "_load_all_screener_data",
                        lambda *a, **k: screener_tuple or make_screener_data_tuple())
    monkeypatch.setattr(watchlist_page, "poll_while_fetching",
                        lambda *a, **k: fetch_progress or {"running": False, "total": 0, "done": 0})

    def _script():
        import portfolio
        portfolio.set_user("test@example.com")
        from uvalu.pages_ import watchlist as watchlist_page
        watchlist_page.render()

    at = AppTest.from_function(_script, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def test_renders_with_empty_watchlist(isolated_data, monkeypatch):
    at = _run(monkeypatch)
    assert "Your watchlist is empty" in "".join(m.value for m in at.markdown)


def test_shows_row_for_watchlisted_ticker(isolated_data, monkeypatch):
    portfolio.save_watchlist({"AAA.BR"})
    at = _run(monkeypatch)
    html = "".join(m.value for m in at.markdown)
    assert "AAA.BR" in html
    assert "Alpha Corp" in html


def test_watchlisted_ticker_with_no_scored_row_shows_loading_state(isolated_data, monkeypatch):
    # ZZZ.BR has no matching row in the fake screener data -> wl_df is empty
    # even though the watchlist isn't. That's the cold-cache case now: a
    # loading skeleton, not the "your watchlist is empty" message.
    portfolio.save_watchlist({"ZZZ.BR"})
    at = _run(monkeypatch)
    html = "".join(m.value for m in at.markdown)
    assert "Your watchlist is empty" not in html
    assert "No screener data yet for your watchlisted ticker" in html
    assert "uv-skel-bar" in html


def test_watchlist_loading_state_shows_fetch_progress(isolated_data, monkeypatch):
    portfolio.save_watchlist({"ZZZ.BR"})
    at = _run(monkeypatch, fetch_progress={"running": True, "total": 8, "done": 2})
    html = "".join(m.value for m in at.markdown)
    assert "Fetching data for your 1 watchlisted ticker" in html
    assert "2/8 companies scored" in html


def test_add_ticker_form_present(isolated_data, monkeypatch):
    at = _run(monkeypatch)
    assert len(at.text_input) == 2
    assert any(b.label == "Add ticker" for b in at.button)


def test_add_ticker_success_saves_to_watchlist(isolated_data, monkeypatch):
    class FakeTicker:
        def __init__(self, symbol):
            self.info = {"shortName": "New Corp", "regularMarketPrice": 50.0}

    monkeypatch.setattr(yf, "Ticker", FakeTicker)
    at = _run(monkeypatch)

    ticker_input = at.text_input[0]
    ticker_input.set_value("NEW.BR")
    submit_buttons = [b for b in at.button if b.label == "Add ticker"]
    submit_buttons[0].click().run()

    assert not at.exception, [str(e.value) for e in at.exception]
    assert portfolio.load_watchlist() == {"NEW.BR"}
    assert portfolio.load_manual_tickers() == {"NEW.BR": "New Corp"}


def test_add_ticker_not_found_shows_error(isolated_data, monkeypatch):
    class FakeTicker:
        def __init__(self, symbol):
            self.info = {}

    monkeypatch.setattr(yf, "Ticker", FakeTicker)
    at = _run(monkeypatch)

    ticker_input = at.text_input[0]
    ticker_input.set_value("BAD.BR")
    submit_buttons = [b for b in at.button if b.label == "Add ticker"]
    submit_buttons[0].click().run()

    assert not at.exception, [str(e.value) for e in at.exception]
    assert "not found" in "".join(m.value for m in at.markdown)
    assert portfolio.load_watchlist() == set()


def test_add_ticker_blank_symbol_shows_error(isolated_data, monkeypatch):
    at = _run(monkeypatch)
    submit_buttons = [b for b in at.button if b.label == "Add ticker"]
    submit_buttons[0].click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "Enter a ticker symbol" in "".join(m.value for m in at.markdown)


def test_add_ticker_lookup_exception_shows_error(isolated_data, monkeypatch):
    def _boom(symbol):
        raise RuntimeError("network down")
    monkeypatch.setattr(yf, "Ticker", _boom)
    at = _run(monkeypatch)

    ticker_input = at.text_input[0]
    ticker_input.set_value("BAD.BR")
    submit_buttons = [b for b in at.button if b.label == "Add ticker"]
    submit_buttons[0].click().run()

    assert not at.exception, [str(e.value) for e in at.exception]
    assert "not found" in "".join(m.value for m in at.markdown)


def test_star_button_removes_ticker_from_watchlist(isolated_data, monkeypatch):
    portfolio.save_watchlist({"AAA.BR"})
    at = _run(monkeypatch)
    star_btn = [b for b in at.button if b.key == "wl_row_0_AAA.BR_action"][0]
    star_btn.click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert portfolio.load_watchlist() == set()


def test_star_button_removes_manually_added_ticker_from_manual_tickers(isolated_data, monkeypatch):
    # A manually-added ticker never appears on the Screener page (it excludes
    # extra_df from its own ranked list) -- this star is the only place it
    # can ever be removed, so it has to clean up manual_tickers too or the
    # entry leaks in there permanently (still fetched/scored on every page
    # load app-wide) even after the user "removed" it from the watchlist.
    portfolio.save_watchlist({"AAA.BR"})
    portfolio.save_manual_tickers({"AAA.BR": "Alpha Corp"})
    at = _run(monkeypatch)
    star_btn = [b for b in at.button if b.key == "wl_row_0_AAA.BR_action"][0]
    star_btn.click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert portfolio.load_watchlist() == set()
    assert portfolio.load_manual_tickers() == {}


def test_star_button_disabled_for_viewer_role(isolated_data, monkeypatch):
    # Removing a watchlist entry (and, for a manually-added ticker, its
    # manual_tickers.json entry too) is a real write -- needs the same
    # Viewer-role gate as every other write action in the app.
    portfolio.save_watchlist({"AAA.BR"})
    monkeypatch.setattr(watchlist_page, "_load_all_screener_data",
                        lambda *a, **k: make_screener_data_tuple())
    script = USER_SETUP_SRC + """
import streamlit as st
st.session_state["user_role"] = "Viewer"
from uvalu.pages_ import watchlist as watchlist_page
watchlist_page.render()
"""
    at = AppTest.from_string(script, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    star_btn = [b for b in at.button if b.key == "wl_row_0_AAA.BR_action"][0]
    assert star_btn.disabled
    assert portfolio.load_watchlist() == {"AAA.BR"}


def test_add_ticker_form_disabled_for_viewer_role(isolated_data, monkeypatch):
    monkeypatch.setattr(watchlist_page, "_load_all_screener_data",
                        lambda *a, **k: make_screener_data_tuple())
    script = USER_SETUP_SRC + """
import streamlit as st
st.session_state["user_role"] = "Viewer"
from uvalu.pages_ import watchlist as watchlist_page
watchlist_page.render()
"""
    at = AppTest.from_string(script, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    add_btn = [b for b in at.button if b.label == "Add ticker"][0]
    assert add_btn.disabled


def test_view_button_opens_drawer(isolated_data, monkeypatch):
    portfolio.save_watchlist({"AAA.BR"})
    at = _run(monkeypatch)
    view_btn = [b for b in at.button if b.key == "wl_row_0_AAA.BR_view"][0]
    view_btn.click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "Six-model fair value" in "".join(m.value for m in at.markdown)
