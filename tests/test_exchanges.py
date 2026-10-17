"""Tests for uvalu/exchanges.py, the exchange registry (EX-3 / EX-W2)."""
import re
from pathlib import Path

import pytest

import fetch_tickers
import settings
from uvalu import exchanges, universe
from uvalu.formatting import EXCHANGE_CODES, exchange_label, row_currency

ROOT = Path(__file__).resolve().parent.parent


def test_registry_entries_are_complete_and_unique():
    for field in ("key", "name", "suffix", "mic", "badge", "list_url", "list_label"):
        values = [getattr(e, field) for e in exchanges.EXCHANGES]
        assert len(values) == len(set(values)), field
    for e in exchanges.EXCHANGES:
        assert e.suffix.startswith(".") and e.suffix.upper() == e.suffix
        assert len(e.currency) == 3 and e.currency.isupper()
        assert len(e.mic) == 4 and len(e.badge) == 3
        assert e.list_url.startswith("https://stockanalysis.com/list/")


def test_official_names_decided_17_oct():
    """D10: official names, .DE is Xetra; keys stay as they were."""
    assert [e.name for e in exchanges.EXCHANGES] == [
        "Euronext Brussels", "Euronext Amsterdam", "Euronext Paris",
        "Euronext Milan", "Xetra", "SIX Swiss Exchange"]
    assert exchanges.keys() == ["brussels", "amsterdam", "paris", "milan", "frankfurt", "swiss"]


@pytest.mark.parametrize("ticker, key", [
    ("UCB.BR", "brussels"), ("ASML.AS", "amsterdam"), ("TTE.PA", "paris"),
    ("ENI.MI", "milan"), ("SAP.DE", "frankfurt"), ("NESN.SW", "swiss"),
    ("nesn.sw", "swiss"),
])
def test_for_ticker(ticker, key):
    assert exchanges.for_ticker(ticker).key == key


@pytest.mark.parametrize("ticker", ["AAPL", "X.NYSE", "", None, ".BR"])
def test_for_ticker_unknown(ticker):
    assert exchanges.for_ticker(ticker) is None


def test_planned_exchanges_are_known_but_not_covered():
    """EX-W3: the 15 planned exchanges are recognised (a user's holding gets
    its currency and badge) but stay out of everything that defines coverage."""
    assert len(exchanges.PLANNED) == 15
    bp = exchanges.for_ticker("BP.L")
    assert bp.key == "london" and bp.currency == "GBP" and bp.price_divisor == 100
    assert "london" not in exchanges.BY_KEY and "london" not in settings.ALL_EXCHANGES
    assert "london" not in fetch_tickers.FETCHERS
    assert universe.exchange_country("BP.L") is None          # never a home listing yet
    all_known = (*exchanges.EXCHANGES, *exchanges.PLANNED)
    for field in ("key", "name", "suffix", "mic", "badge", "list_url", "list_label"):
        values = [getattr(e, field) for e in all_known]
        assert len(values) == len(set(values)), field


def test_every_consumer_reads_the_registry():
    assert settings.ALL_EXCHANGES == exchanges.keys()
    assert settings.EXCHANGE_LABELS == {e.key: e.name for e in exchanges.EXCHANGES}
    assert set(fetch_tickers.FETCHERS) == set(exchanges.keys())
    for e in exchanges.EXCHANGES:
        assert universe.exchange_country(f"X{e.suffix}") == e.country
        assert exchange_label(f"X{e.suffix}") == e.name
        assert row_currency({"Ticker": f"X{e.suffix}"}) == e.currency
        assert EXCHANGE_CODES[e.suffix.lstrip(".")] == e.badge


def test_no_exchange_map_outside_the_registry():
    """F7 / EX-3: the facts about an exchange live only in uvalu/exchanges.py.
    A dict keyed by an exchange suffix or key anywhere else in the app is a
    copy that can drift (fetch_tickers.FETCHERS, the key → list function
    map, is the one allowed exception)."""
    pattern = re.compile(r'"\.(%s)"\s*:|"(%s)"\s*:' % (
        "|".join(e.suffix.lstrip(".") for e in exchanges.EXCHANGES),
        "|".join(exchanges.keys())))
    offenders = []
    files = [*ROOT.glob("*.py"), *(ROOT / "uvalu").rglob("*.py")]
    for path in files:
        if path.name == "exchanges.py":
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line) and not (path.name == "fetch_tickers.py" and "_tickers," in line):
                offenders.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()}")
    assert offenders == []
