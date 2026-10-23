"""The demo universe: 9 European stocks and 1 benchmark ETF (demo spec,
"Demo stock universe").

Chosen to exercise four currencies (EUR, CHF, DKK, GBP quoted in pence), five
sectors, dividend payers, a volatile stock and a benchmark. Keys are the
app's own stored form (Yahoo's, decision D12); the EODHD code comes from the
exchange registry (``exchanges.eodhd_ticker``), never from this file.

Sectors use the names the app already groups by (Yahoo's sector names), so
the sector reference file (DM-D3) and the Risk page's sector HHI line up.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DemoTicker:
    ticker: str       # stored key, Yahoo form ("SHEL.L")
    name: str
    currency: str     # ISO 4217 of the price as displayed (GBP for London)
    sector: str
    benchmark: bool = False


DEMO_UNIVERSE: tuple[DemoTicker, ...] = (
    DemoTicker("ABI.BR",    "AB InBev",                "EUR", "Consumer Defensive"),
    DemoTicker("KBC.BR",    "KBC Group",               "EUR", "Financial Services"),
    DemoTicker("ASML.AS",   "ASML Holding",            "EUR", "Technology"),
    DemoTicker("SAP.DE",    "SAP",                     "EUR", "Technology"),
    DemoTicker("MC.PA",     "LVMH",                    "EUR", "Consumer Cyclical"),
    DemoTicker("TTE.PA",    "TotalEnergies",           "EUR", "Energy"),
    DemoTicker("NESN.SW",   "Nestlé",                  "CHF", "Consumer Defensive"),
    DemoTicker("NOVO-B.CO", "Novo Nordisk",            "DKK", "Healthcare"),
    DemoTicker("SHEL.L",    "Shell",                   "GBP", "Energy"),
    DemoTicker("VWCE.DE",   "Vanguard FTSE All-World", "EUR", "ETF", benchmark=True),
)

TICKERS: tuple[str, ...] = tuple(t.ticker for t in DEMO_UNIVERSE)
STOCKS: tuple[str, ...] = tuple(t.ticker for t in DEMO_UNIVERSE if not t.benchmark)
BENCHMARK: str = next(t.ticker for t in DEMO_UNIVERSE if t.benchmark)
BY_TICKER: dict[str, DemoTicker] = {t.ticker: t for t in DEMO_UNIVERSE}


# Index series the demo needs besides the tickers: the risk benchmark the app
# uses (risk.BENCHMARK_TICKER, DM-D16). Stored under the app's own key; the
# EODHD code is fixed here because indices have no exchange in the registry.
INDEX_SERIES: dict[str, str] = {"^STOXX50E": "STOXX50E.INDX"}

SERIES: tuple[str, ...] = TICKERS + tuple(INDEX_SERIES)


def eodhd_code(key: str) -> str:
    """The EODHD code of a demo series: an index from INDEX_SERIES, otherwise
    the registry's conversion of a stored ticker."""
    if key in INDEX_SERIES:
        return INDEX_SERIES[key]
    from uvalu import exchanges
    return exchanges.eodhd_ticker(key)


# Currencies the companies report or declare dividends in besides their quote
# currency (AB InBev, TotalEnergies and Shell report in USD).
_EXTRA_FX = frozenset({"USD"})


def currencies() -> list[str]:
    """The non-euro currencies the demo needs FX for, sorted: every quote
    currency plus the reporting and dividend currencies (USD)."""
    return sorted(({t.currency for t in DEMO_UNIVERSE} | _EXTRA_FX) - {"EUR"})
