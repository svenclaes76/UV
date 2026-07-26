"""AppTest coverage for uvalu/pages_/watchlist.py."""
import yfinance as yf
from streamlit.testing.v1 import AppTest

import portfolio
import settings
from uvalu.pages_ import watchlist as watchlist_page
from tests.conftest import make_screener_data_tuple, make_scored_row


def _run(monkeypatch, screener_tuple=None) -> AppTest:
    monkeypatch.setattr(watchlist_page, "_load_all_screener_data",
                        lambda *a, **k: screener_tuple or make_screener_data_tuple())

    def _script():
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


def test_ticker_not_in_screener_data_falls_back_to_empty_state(isolated_data, monkeypatch):
    # ZZZ.BR has no matching row in the fake screener data -> filtered out
    # of wl_df, same empty-results branch as an actually-empty watchlist.
    portfolio.save_watchlist({"ZZZ.BR"})
    at = _run(monkeypatch)
    assert "Your watchlist is empty" in "".join(m.value for m in at.markdown)


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
