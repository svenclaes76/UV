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


def currencies() -> list[str]:
    """The non-euro currencies the demo needs FX for, sorted."""
    return sorted({t.currency for t in DEMO_UNIVERSE} - {"EUR"})
