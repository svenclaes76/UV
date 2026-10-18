"""Tests for uvalu/datamode.py and the demo universe (demo-mode plan DM-1)."""
import pytest

from uvalu import datamode, exchanges
from uvalu.demo import universe


def test_default_is_personal(monkeypatch):
    monkeypatch.delenv(datamode.ENV_VAR, raising=False)
    assert datamode.current() is datamode.PERSONAL
    assert not datamode.is_demo()


@pytest.mark.parametrize("raw", ["demo", " DEMO ", "Demo"])
def test_demo_selected_case_and_space_insensitive(monkeypatch, raw):
    monkeypatch.setenv(datamode.ENV_VAR, raw)
    assert datamode.current() is datamode.DEMO
    assert datamode.is_demo()


def test_empty_value_is_personal(monkeypatch):
    monkeypatch.setenv(datamode.ENV_VAR, "")
    assert datamode.current() is datamode.PERSONAL


def test_unknown_mode_fails_loudly(monkeypatch):
    monkeypatch.setenv(datamode.ENV_VAR, "demoo")
    with pytest.raises(ValueError, match="not a data mode"):
        datamode.current()


def test_commercial_is_reserved_but_not_built(monkeypatch):
    monkeypatch.setenv(datamode.ENV_VAR, "commercial")
    with pytest.raises(RuntimeError, match="isn't built yet"):
        datamode.current()


def test_personal_profile_is_todays_app():
    p = datamode.PERSONAL
    assert p.live_fetch and p.sign_in and p.persistent_writes
    assert p.data_dir is None and p.universe is None
    assert not p.hidden_pages and not p.banner


def test_demo_profile_never_fetches_and_never_writes():
    d = datamode.DEMO
    assert not d.live_fetch and not d.sign_in and not d.persistent_writes
    assert d.banner and d.data_dir.name == "demo-data"
    assert d.universe == universe.TICKERS
    assert {"watchlist", "admin"} <= d.hidden_pages


def test_demo_universe_shape():
    assert len(universe.DEMO_UNIVERSE) == 10
    assert len(universe.STOCKS) == 9
    assert universe.BENCHMARK == "VWCE.DE"
    assert universe.currencies() == ["CHF", "DKK", "GBP"]
    assert len({t.sector for t in universe.DEMO_UNIVERSE if not t.benchmark}) == 6


def test_demo_currencies_match_the_registry():
    for t in universe.DEMO_UNIVERSE:
        ex = exchanges.for_ticker(t.ticker)
        assert ex is not None, t.ticker
        assert ex.currency == t.currency, t.ticker


@pytest.mark.parametrize("ticker, code", [
    ("ABI.BR", "ABI.BR"), ("KBC.BR", "KBC.BR"), ("ASML.AS", "ASML.AS"),
    ("SAP.DE", "SAP.XETRA"), ("MC.PA", "MC.PA"), ("TTE.PA", "TTE.PA"),
    ("NESN.SW", "NESN.SW"), ("NOVO-B.CO", "NOVO-B.CO"), ("SHEL.L", "SHEL.LSE"),
    ("VWCE.DE", "VWCE.XETRA"),
])
def test_eodhd_codes_from_the_spec(ticker, code):
    assert exchanges.eodhd_ticker(ticker) == code


def test_eodhd_code_unknown_exchange_raises():
    with pytest.raises(ValueError):
        exchanges.eodhd_ticker("PKN.WA")      # no confirmed EODHD code yet
    with pytest.raises(ValueError):
        exchanges.eodhd_ticker("AAPL")
