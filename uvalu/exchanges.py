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
    # Yahoo quotes some exchanges' lines in the currency's minor unit (London:
    # pence, "GBp"). The default divisor for a line whose own quote currency
    # isn't known yet; marketdata.price_divisor() prefers the line's own.
    price_divisor: int = 1


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

# Planned (exchange expansion plan §4): defined and tested here, but not yet
# covered — not in settings, the ticker lists, the Market filter or Admin
# until a later work package moves them into EXCHANGES. They are known to
# for_ticker(), so a user's own holding on one of them gets the right
# currency, name and badge already.
PLANNED: tuple[Exchange, ...] = (
    Exchange("madrid", "Bolsa de Madrid", "Spain", ".MC", "XMAD", "EUR", "MAD",
             "https://stockanalysis.com/list/madrid-stock-exchange/", "Madrid"),
    Exchange("stockholm", "Nasdaq Stockholm", "Sweden", ".ST", "XSTO", "SEK", "STO",
             "https://stockanalysis.com/list/nasdaq-stockholm/", "Stockholm"),
    Exchange("copenhagen", "Nasdaq Copenhagen", "Denmark", ".CO", "XCSE", "DKK", "CPH",
             "https://stockanalysis.com/list/copenhagen-stock-exchange/", "Copenhagen"),
    Exchange("helsinki", "Nasdaq Helsinki", "Finland", ".HE", "XHEL", "EUR", "HEL",
             "https://stockanalysis.com/list/nasdaq-helsinki/", "Helsinki"),
    # Part of Euronext; the official branding to show is still to be
    # confirmed (open item EX4).
    Exchange("oslo", "Oslo Børs", "Norway", ".OL", "XOSL", "NOK", "OSL",
             "https://stockanalysis.com/list/oslo-bors/", "Oslo"),
    Exchange("lisbon", "Euronext Lisbon", "Portugal", ".LS", "XLIS", "EUR", "LIS",
             "https://stockanalysis.com/list/euronext-lisbon/", "Lisbon"),
    Exchange("dublin", "Euronext Dublin", "Ireland", ".IR", "XMSM", "EUR", "DUB",
             "https://stockanalysis.com/list/euronext-dublin/", "Dublin"),
    Exchange("vienna", "Wiener Börse", "Austria", ".VI", "XWBO", "EUR", "VIE",
             "https://stockanalysis.com/list/vienna-stock-exchange/", "Vienna"),
    # Yahoo quotes London lines in pence (EX-14): price_divisor 100.
    Exchange("london", "London Stock Exchange", "United Kingdom", ".L", "XLON", "GBP", "LON",
             "https://stockanalysis.com/list/london-stock-exchange/", "London", price_divisor=100),
    # Renamed from Athens Exchange in April 2026.
    Exchange("athens", "Euronext Athens", "Greece", ".AT", "XATH", "EUR", "ATH",
             "https://stockanalysis.com/list/athens-stock-exchange/", "Athens"),
    Exchange("iceland", "Nasdaq Iceland", "Iceland", ".IC", "XICE", "ISK", "ICE",
             "https://stockanalysis.com/list/nasdaq-iceland/", "Iceland"),
    Exchange("tallinn", "Nasdaq Tallinn", "Estonia", ".TL", "XTAL", "EUR", "TAL",
             "https://stockanalysis.com/list/nasdaq-tallinn/", "Tallinn"),
    Exchange("riga", "Nasdaq Riga", "Latvia", ".RG", "XRIS", "EUR", "RIG",
             "https://stockanalysis.com/list/nasdaq-riga/", "Riga"),
    Exchange("vilnius", "Nasdaq Vilnius", "Lithuania", ".VS", "XLIT", "EUR", "VIL",
             "https://stockanalysis.com/list/nasdaq-vilnius/", "Vilnius"),
    Exchange("warsaw", "Warsaw Stock Exchange", "Poland", ".WA", "XWAR", "PLN", "WAR",
             "https://stockanalysis.com/list/warsaw-stock-exchange/", "Warsaw"),
)

BY_KEY: dict[str, Exchange] = {e.key: e for e in EXCHANGES}
BY_SUFFIX: dict[str, Exchange] = {e.suffix: e for e in EXCHANGES}
# Covered and planned, for recognising any ticker a user may hold.
KNOWN_BY_KEY: dict[str, Exchange] = {e.key: e for e in (*EXCHANGES, *PLANNED)}
KNOWN_BY_SUFFIX: dict[str, Exchange] = {e.suffix: e for e in (*EXCHANGES, *PLANNED)}


def keys() -> list[str]:
    """Every exchange key, in registry order."""
    return [e.key for e in EXCHANGES]


def for_ticker(ticker: object) -> "Exchange | None":
    """The exchange of a Yahoo ticker, by its suffix: a covered or a planned
    one (check ``.key in BY_KEY`` for covered); None for a ticker without a
    suffix or on an exchange the registry doesn't know."""
    t = str(ticker or "")
    dot = t.rfind(".")
    return KNOWN_BY_SUFFIX.get(t[dot:].upper()) if dot > 0 else None


def yahoo_symbol(symbol: str) -> str:
    """An exchange symbol in Yahoo's form, without the suffix: class and line
    separators (dot, space) become a dash ("INVE.B", "NOVO B" → "INVE-B",
    "NOVO-B"). EX-11 / EX-40."""
    return "-".join(str(symbol).strip().replace(".", " ").split())


def normalize_ticker(text: object) -> str:
    """A ticker typed by a user, in Yahoo's form: "novo b.co", "NOVO.B.CO" →
    "NOVO-B.CO" (plan §10 P3). Only when it ends in a known exchange suffix;
    anything else is just trimmed and upper-cased."""
    t = " ".join(str(text or "").strip().upper().split())
    for suffix in sorted(KNOWN_BY_SUFFIX, key=len, reverse=True):
        if t.endswith(suffix) and len(t) > len(suffix):
            return f"{yahoo_symbol(t[: -len(suffix)])}{suffix}"
    return t


def name(key: str) -> str:
    """The official name of an exchange key; the key itself if unknown."""
    e = KNOWN_BY_KEY.get(key)
    return e.name if e else key


# ── EODHD codes (EX-40, demo-mode plan DM-3) ─────────────────────────────────
# EODHD writes a ticker as SYMBOL.EXCHANGE with its own exchange codes. The
# stored key stays Yahoo's (D12); this table is the one conversion. Only the
# exchanges whose EODHD code is confirmed are listed: an unlisted one raises
# rather than guess a code and waste a call on a 404.
_EODHD_EXCHANGE: dict[str, str] = {
    "brussels": "BR",
    "amsterdam": "AS",
    "paris": "PA",
    "frankfurt": "XETRA",   # Yahoo .DE is Xetra (D10)
    "swiss": "SW",
    "copenhagen": "CO",
    "london": "LSE",
}


def eodhd_ticker(ticker: str) -> str:
    """The EODHD code of a stored (Yahoo-form) ticker: "SAP.DE" →
    "SAP.XETRA", "SHEL.L" → "SHEL.LSE". The symbol part is unchanged (EODHD
    also writes share classes with a dash, "NOVO-B.CO"). Raises ValueError
    for an exchange without a confirmed EODHD code."""
    e = for_ticker(ticker)
    code = _EODHD_EXCHANGE.get(e.key) if e else None
    if not code:
        raise ValueError(f"no EODHD exchange code for {ticker!r}")
    return f"{str(ticker)[: str(ticker).rfind('.')]}.{code}"
