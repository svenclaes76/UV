"""Which listings make up the public coverage universe (V2, model M2).

Uvalu covers companies from the six covered countries on their own home
exchange. The stockanalysis.com exchange lists (fetch_tickers.py) also carry
every secondary listing: about a third of the old universe was US and other
non-European companies cross-listed in Milan and Frankfurt, often dormant
and with fundamentals in another currency than the quote
(docs/valuation-model-review.md V2, decided 13 Oct 2026: home listings only).

A listing is a home listing when the company's country, from the data
provider, is the country of the exchange. A listing whose country isn't known
yet is left out until it is. A line with a confirmed zero average volume is
left out too: it doesn't trade, so a signal on it means nothing. A user's own
holding on any listing is still scored, as one of their extra tickers,
against this universe (PER-2).

No Streamlit import; unit-tested in tests/test_universe.py.
"""
from __future__ import annotations

from uvalu import exchanges

EXCHANGE_COUNTRY: dict[str, str] = {e.suffix: e.country for e in exchanges.EXCHANGES}


def exchange_country(ticker: str) -> str | None:
    """The covered country of the ticker's exchange suffix, or None."""
    ex = exchanges.for_ticker(ticker)
    return ex.country if ex else None


def is_home_listing(ticker: str, country: object) -> bool:
    """True when `country` (the company's, from the provider) is the country
    of the ticker's exchange. Unknown country → False."""
    home = exchange_country(ticker)
    return bool(home) and isinstance(country, str) and country.strip() == home


def known_foreign(ticker: str, country: object) -> bool:
    """True when the company's country is known and isn't the exchange's:
    such a listing never enters the universe, so it needn't be fetched for it.
    An unknown country is not "known foreign" — it still gets fetched."""
    return isinstance(country, str) and bool(country.strip()) and not is_home_listing(ticker, country)


def is_dormant(average_volume: object) -> bool:
    """A confirmed zero average volume: the line doesn't trade (treasury
    shares, a dormant second line). A missing volume is not evidence of
    that and doesn't count."""
    try:
        return float(average_volume) == 0.0
    except (TypeError, ValueError):
        return False


def home_listings(stocks: list[dict], country_by_ticker: dict[str, object],
                  volume_by_ticker: dict[str, object] | None = None) -> list[dict]:
    """The stocks from an exchange list that are home listings and trade."""
    volume_by_ticker = volume_by_ticker or {}
    return [s for s in stocks
            if is_home_listing(s["ticker"], country_by_ticker.get(s["ticker"]))
            and not is_dormant(volume_by_ticker.get(s["ticker"]))]
