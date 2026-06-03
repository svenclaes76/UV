"""
Real-time and EOD price feed via yfinance.

Uses yf.download() for batch price fetching — a single HTTP request for any
number of tickers, instead of one request per ticker. Falls back to
yf.Ticker.fast_info for individual tickers when download fails.

Returns per-ticker: price, prev_close, day_change_pct, volume.
"""

from __future__ import annotations

import yfinance as yf
import pandas as pd


_EMPTY = {
    "price":          None,
    "prev_close":     None,
    "day_change_pct": None,
    "volume":         None,
}


def fetch_prices(tickers: tuple[str, ...]) -> dict[str, dict]:
    """
    Batch-fetch latest price data for all tickers in a single HTTP call.
    Returns a dict keyed by ticker with price, prev_close, day_change_pct, volume.
    """
    if not tickers:
        return {}

    result = {t: dict(_EMPTY) for t in tickers}

    try:
        raw = yf.download(
            list(tickers),
            period="5d",       # last 5 trading days → guaranteed two closing prices
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )

        if raw.empty:
            raise ValueError("Empty download response")

        # yf.download always returns MultiIndex columns (Field, Ticker) when
        # given a list — even a single-element list.
        for t in tickers:
            try:
                closes  = raw["Close"][t].dropna()
                volumes = raw["Volume"][t].dropna()

                if len(closes) < 1:
                    continue

                price      = float(closes.iloc[-1])
                prev_close = float(closes.iloc[-2]) if len(closes) >= 2 else None
                day_chg    = ((price - prev_close) / prev_close * 100) if prev_close else None
                volume     = int(volumes.iloc[-1]) if not volumes.empty else None

                result[t] = {
                    "price":          round(price, 4),
                    "prev_close":     round(prev_close, 4) if prev_close else None,
                    "day_change_pct": round(day_chg, 2) if day_chg is not None else None,
                    "volume":         volume,
                }
            except Exception:
                pass

    except Exception:
        # Fallback: fast_info per ticker (lighter than .info)
        for t in tickers:
            try:
                fi = yf.Ticker(t).fast_info
                price      = fi.get("last_price") or fi.get("regular_market_price")
                prev_close = fi.get("previous_close") or fi.get("regular_market_previous_close")
                day_chg    = ((price - prev_close) / prev_close * 100
                              if price and prev_close else None)
                result[t] = {
                    "price":          round(price, 4) if price else None,
                    "prev_close":     round(prev_close, 4) if prev_close else None,
                    "day_change_pct": round(day_chg, 2) if day_chg is not None else None,
                    "volume":         fi.get("three_month_average_volume"),
                }
            except Exception:
                pass

    return result
