"""The exchange registry: every fact about a covered exchange, in one place.

Exchange expansion plan EX-3 / EX-W2. Before this module the same facts
(key, label, Yahoo suffix, MIC, currency, country, list URL) were copied into
about ten files that had to agree. Everything else now reads them from here:
settings (keys, labels), fetch_tickers (list URLs), universe (home country),
portfolio (currency), formatting (names, badge codes) and the pages.

Names are the exchanges' official names (decision D10, 17 Oct 2026), shown
untranslated in every language (D11): they're proper names, and a filter
value that doesn't change with the language survives a language switch
(spec L-06). Keys never change, so saved settings keep working when a name
does (Athens Exchange became Euronext Athens in April 2026).

The ticker suffix is Yahoo's (EX-40): ticker formats belong to the data
vendor, and this module is the one place that knows them.

No Streamlit import; unit-tested in tests/test_exchanges.py.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Exchange:
    key: str          # stable internal key, stored in settings ("brussels")
    name: str         # official name, shown untranslated ("Euronext Brussels")
    country: str      # English country name, as the data provider writes it
    suffix: str       # Yahoo ticker suffix (".BR")
    mic: str          # ISO 10383 market identifier ("XBRU")
    currency: str     # quote currency (ISO 4217)
    badge: str        # 3-letter venue code shown next to a ticker ("BRU")
    list_url: str     # stockanalysis.com list page
    list_label: str   # name of the cached list and its log endpoint ("Brussels")


EXCHANGES: tuple[Exchange, ...] = (
    Exchange("brussels", "Euronext Brussels", "Belgium", ".BR", "XBRU", "EUR", "BRU",
             "https://stockanalysis.com/list/euronext-brussels/", "Brussels"),
    Exchange("amsterdam", "Euronext Amsterdam", "Netherlands", ".AS", "XAMS", "EUR", "AMS",
             "https://stockanalysis.com/list/euronext-amsterdam/", "Amsterdam"),
    Exchange("paris", "Euronext Paris", "France", ".PA", "XPAR", "EUR", "PAR",
             "https://stockanalysis.com/list/euronext-paris/", "Paris"),
    Exchange("milan", "Euronext Milan", "Italy", ".MI", "XMIL", "EUR", "MIL",
             "https://stockanalysis.com/list/borsa-italiana/", "Milan"),
    # Yahoo's .DE prices are Xetra's, not the Frankfurt floor's (D10).
    Exchange("frankfurt", "Xetra", "Germany", ".DE", "XETR", "EUR", "XET",
             "https://stockanalysis.com/list/frankfurt-stock-exchange/", "Frankfurt"),
    Exchange("swiss", "SIX Swiss Exchange", "Switzerland", ".SW", "XSWX", "CHF", "SWX",
             "https://stockanalysis.com/list/six-swiss-exchange/", "Swiss"),
)

BY_KEY: dict[str, Exchange] = {e.key: e for e in EXCHANGES}
BY_SUFFIX: dict[str, Exchange] = {e.suffix: e for e in EXCHANGES}


def keys() -> list[str]:
    """Every exchange key, in registry order."""
    return [e.key for e in EXCHANGES]


def for_ticker(ticker: object) -> "Exchange | None":
    """The covered exchange of a Yahoo ticker, by its suffix; None for a
    ticker without one or on an exchange that isn't covered."""
    t = str(ticker or "")
    dot = t.rfind(".")
    return BY_SUFFIX.get(t[dot:].upper()) if dot > 0 else None


def name(key: str) -> str:
    """The official name of an exchange key; the key itself if unknown."""
    e = BY_KEY.get(key)
    return e.name if e else key
