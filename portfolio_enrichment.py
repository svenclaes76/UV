"""
Turn a raw portfolio DataFrame into the enriched frame
``risk.assess_portfolio`` expects — live price, current value, fair value,
sector, country and forward dividend income.

The fundamentals-derived fields are pulled from the screener's own scored
DataFrame rather than re-derived, so the Risk page's numbers match the
Screener / Analysis pages for the same ticker. Kept out of the page body so
the contract sits next to the engine that consumes it and can be unit-tested
on its own.
"""
from __future__ import annotations

import pandas as pd

from screener import sector_for


def enrich_for_risk(pf: pd.DataFrame, scored_by_ticker: pd.DataFrame | None,
                    live_prices: dict) -> pd.DataFrame:
    """Return a copy of ``pf`` with the columns ``assess_portfolio`` reads.

    pf               — portfolio rows: ticker, shares, name, …
    scored_by_ticker — screener.run_screener_from_df output, indexed by Ticker
                       (may be None / missing columns — those fields come back
                       as NaN and assess_portfolio falls back).
    live_prices      — {ticker: {"price": float, …}} from the shared feed.
    """
    out = pf.copy()

    out["live_price"]    = out["ticker"].map(lambda t: (live_prices.get(t) or {}).get("price"))
    out["current_value"] = out["live_price"] * out["shares"]

    def _scr(field, default=None) -> pd.Series:
        if scored_by_ticker is None or field not in getattr(scored_by_ticker, "columns", []):
            return pd.Series(default, index=out.index)
        return out["ticker"].map(scored_by_ticker[field])

    out["fair_value"]      = _scr("fair_value")
    # Curated fallback for tickers the provider leaves unclassified, so the
    # Risk page's sector concentration / HHI don't dump a quarter of the book
    # into an "Unknown" bucket (WP-DQ7). Same helper the Dashboard donut and
    # Holdings tags use, so the three never disagree.
    _raw_sector            = _scr("sector")
    out["sector"]          = [sector_for(t, s) for t, s in zip(out["ticker"], _raw_sector)]
    out["country"]         = _scr("country")
    out["div_rate"]        = _scr("trailingAnnualDividendRate").fillna(_scr("dividendRate")).fillna(0)
    out["expected_annual"] = (out["div_rate"] * out["shares"]).round(2)
    return out
