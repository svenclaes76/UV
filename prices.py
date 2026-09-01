"""
Real-time and EOD price feed via yfinance.

Two batch HTTP calls per refresh, regardless of ticker count:
  1. yf.download(period="5d", interval="1d")  → prev_close, volume, and a
     price fallback (a daily bar, which lags intraday).
  2. yf.download(period="1d", interval="1m")  → the true intraday last price,
     overlaid on top of (1). Best-effort: a ticker with no 1-minute bar
     (illiquid, or market closed) keeps its daily close.

Falls back to yf.Ticker.fast_info per ticker when the daily batch download
fails entirely.

Returns per-ticker: price, prev_close, day_change_pct, volume, as_of, stale,
quote_source.
`as_of` is the ISO-8601 UTC timestamp the value was fetched; `stale` is True
when the fetch returned nothing this round and a previous known-good value is
being served instead. `quote_source` is how *this* ticker's price was
obtained: "intraday" (a fresh 1-minute bar), "eod" (fell back to the most
recent daily close — lags during a live session), or "stale" (served from the
last-known-good cache because the fetch returned nothing).
"""

from __future__ import annotations

from datetime import datetime, timezone

import yfinance as yf
import pandas as pd


_EMPTY = {
    "price":          None,
    "prev_close":     None,
    "day_change_pct": None,
    "volume":         None,
    "as_of":          None,
    "stale":          False,
    "quote_source":   None,
}

# Process-global cache of the last successful per-ticker result, shared across
# all Streamlit sessions (prices are not user-scoped). When a later fetch
# returns nothing for a ticker, its last known-good value is served with
# stale=True instead of a bare None that would blank the position in the UI.
# Empty on restart; self-heals on the next successful fetch.
_last_good: dict[str, dict] = {}


def _day_change(price, prev_close) -> float | None:
    if price and prev_close:
        return round((price - prev_close) / prev_close * 100, 2)
    return None


def _intraday_last_prices(tickers: tuple[str, ...]) -> dict[str, float]:
    """Best-effort true intraday last price per ticker, via a 1-minute-interval
    download. Returns only the tickers we got a fresh number for; callers keep
    the daily close for the rest. Any failure (network, empty frame, market
    closed) returns {} so the daily-close path in fetch_prices() stands alone.
    """
    try:
        raw = yf.download(
            list(tickers),
            period="1d",
            interval="1m",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        if raw.empty:
            return {}

        out: dict[str, float] = {}
        for t in tickers:
            try:
                closes = raw["Close"][t].dropna()
                if not closes.empty:
                    out[t] = round(float(closes.iloc[-1]), 4)
            except Exception:
                pass
        return out
    except Exception:
        return {}


def fetch_prices(tickers: tuple[str, ...]) -> dict[str, dict]:
    """
    Batch-fetch latest price data for all tickers.
    Returns a dict keyed by ticker with price, prev_close, day_change_pct,
    volume, as_of, stale.
    """
    if not tickers:
        return {}

    now_iso = datetime.now(timezone.utc).isoformat()
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
                volume     = int(volumes.iloc[-1]) if not volumes.empty else None

                result[t] = {
                    "price":          round(price, 4),
                    "prev_close":     round(prev_close, 4) if prev_close else None,
                    "day_change_pct": _day_change(price, prev_close),
                    "volume":         volume,
                    "as_of":          now_iso,
                    "stale":          False,
                    "quote_source":   "eod",
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
                result[t] = {
                    "price":          round(price, 4) if price else None,
                    "prev_close":     round(prev_close, 4) if prev_close else None,
                    "day_change_pct": _day_change(price, prev_close),
                    "volume":         fi.get("three_month_average_volume"),
                    "as_of":          now_iso,
                    "stale":          False,
                    "quote_source":   "eod",
                }
            except Exception:
                pass

    # ── Intraday overlay ─────────────────────────────────────────────────────
    # Replace the daily close with a true 1-minute last price wherever we can
    # get one, and recompute the day change against the daily prev_close.
    for t, px in _intraday_last_prices(tickers).items():
        entry = result.get(t)
        if entry is None:
            continue
        entry["price"] = px
        entry["as_of"] = now_iso
        entry["stale"] = False
        entry["quote_source"] = "intraday"
        if entry.get("prev_close"):
            entry["day_change_pct"] = _day_change(px, entry["prev_close"])

    # ── Stale fallback ───────────────────────────────────────────────────────
    # A ticker we got no price for this round is served its last known-good
    # value, flagged stale. A ticker we did get is recorded as the new
    # known-good.
    for t in tickers:
        entry = result[t]
        if entry.get("price") is None:
            if t in _last_good:
                result[t] = {**_last_good[t], "stale": True, "quote_source": "stale"}
        else:
            _last_good[t] = dict(entry)

    return result
