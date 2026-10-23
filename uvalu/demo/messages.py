"""User-facing demo texts shared by several pages (demo-mode plan DM-5)."""
from __future__ import annotations

from uvalu import datamode
from uvalu.demo import universe
from uvalu.i18n import _


def outside_demo(ticker: str) -> bool:
    """True in demo mode for a ticker the snapshot doesn't hold (spec F-10)."""
    return not datamode.current().live_fetch and ticker not in universe.TICKERS


def not_in_demo(ticker: str) -> str:
    # Translators: Shown in demo mode when someone types a ticker outside the demo's fixed list. {tickers} is that list.
    return _("{ticker} isn't in the demo. The demo covers {tickers}.",
             ticker=ticker, tickers=", ".join(universe.TICKERS))
