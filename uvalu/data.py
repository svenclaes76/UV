"""Screener/price/fundamentals data layer — cache-backed, no UI.

Functions keep their original private names so app.py and page modules can
import them unchanged. All @st.cache_data identity is preserved.
"""
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from prices import fetch_prices
from fetch_tickers import (fetch_brussels_tickers, fetch_amsterdam_tickers,
                            fetch_paris_tickers, fetch_milan_tickers,
                            fetch_frankfurt_tickers, fetch_swiss_tickers)
from screener import (CACHE_FILE, CACHE_TTL_HOURS, _load_cache,
                      run_screener_from_df, fetch_fundamentals_nowait,
                      cancel_background_fetch, clear_live_cache, _file_lock)
from settings import ALL_EXCHANGES


def _bust_cache() -> None:
    """Cancel any background fetch, wipe the screener disk cache, and rerun."""
    cancel_background_fetch()
    clear_live_cache()
    with _file_lock:   # prevents a concurrent background save from landing after our wipe
        try:
            CACHE_FILE.write_text("{}", encoding="utf-8")
        except OSError:
            pass
    _load_all_screener_data.clear()
    st.rerun()


def _cache_age_str() -> str:
    cache = _load_cache()
    if not cache:
        return "No cache yet"
    timestamps = [
        datetime.fromisoformat(v["fetched_at"])
        for v in cache.values()
        if v.get("fetched_at")
    ]
    if not timestamps:
        return "No cache yet"
    oldest = min(timestamps)
    age_min = (datetime.now(timezone.utc) - oldest).total_seconds() / 60
    if age_min < 60:
        return f"Cache age: {age_min:.0f} min  (TTL {CACHE_TTL_HOURS}h)"
    return f"Cache age: {age_min/60:.1f} h  (TTL {CACHE_TTL_HOURS}h)"


def _cache_version() -> str:
    """Changes whenever the fundamentals JSON file is updated on disk."""
    try:
        return str(int(CACHE_FILE.stat().st_mtime))
    except OSError:
        return "0"


@st.cache_data(show_spinner=False)
def _load_all_screener_data(cache_version: str, enabled: tuple,
                            extra_tickers: tuple = (), extra_names: tuple = (),
                            thresholds: tuple = (500.0, 0.90, 0.0, 70.0)) -> tuple:  # noqa: ARG001
    """
    Build screener DataFrames from whatever is in the cache right now.
    cache_version (file mtime), enabled exchanges, extra_tickers (portfolio
    stocks from disabled exchanges), and thresholds (max_debt_equity,
    max_payout, min_mos, buy_threshold — see settings.get_veto_thresholds())
    all bust the Streamlit cache when they change.

    extra_tickers are folded into the single fetch_fundamentals_nowait call so
    they share the same background-fetch thread, cache file, and refresh cadence
    as the screener.  A scored DataFrame for those tickers is returned as the
    last element of the tuple (after the per-exchange DataFrames).
    """
    _max_de, _max_payout, _min_mos, _buy_threshold = thresholds
    _fetch_map = {
        "brussels":  (fetch_brussels_tickers,  ".BR"),
        "amsterdam": (fetch_amsterdam_tickers, ".AS"),
        "paris":     (fetch_paris_tickers,     ".PA"),
        "milan":     (fetch_milan_tickers,     ".MI"),
        "frankfurt": (fetch_frankfurt_tickers, ".DE"),
        "swiss":     (fetch_swiss_tickers,     ".SW"),
    }
    enabled_set = set(enabled)
    empty = pd.DataFrame(columns=["Ticker"])

    stock_lists: dict[str, list[dict]] = {}
    all_stocks: list[dict] = []
    for key, (fetch_fn, _) in _fetch_map.items():
        if key in enabled_set:
            stocks = fetch_fn()
            stock_lists[key] = stocks
            all_stocks.extend(stocks)

    # Add extra (portfolio) tickers not already covered by enabled exchanges
    _exchange_ticker_set = {s["ticker"] for s in all_stocks}
    _extra_stocks = [
        {"ticker": t, "name": n, "isin": ""}
        for t, n in zip(extra_tickers, extra_names)
        if t not in _exchange_ticker_set
    ]
    all_stocks.extend(_extra_stocks)

    print(f"Loading screener data for {len(all_stocks)} stocks…")
    all_fund = fetch_fundamentals_nowait(all_stocks)

    if all_fund.empty:
        return tuple(empty for _ in ALL_EXCHANGES) + (empty,)

    def _exchange_df(stock_list):
        tickers = {s["ticker"] for s in stock_list}
        return run_screener_from_df(all_fund[all_fund["Ticker"].isin(tickers)],
                                    max_debt_equity=_max_de, max_payout=_max_payout,
                                    min_mos=_min_mos, buy_threshold=_buy_threshold)

    exchange_dfs = tuple(
        _exchange_df(stock_lists[key]) if key in stock_lists else empty
        for key in ALL_EXCHANGES
    )

    # Scored df for the extra portfolio tickers
    if _extra_stocks:
        _extra_tset = {s["ticker"] for s in _extra_stocks}
        _extra_df   = run_screener_from_df(all_fund[all_fund["Ticker"].isin(_extra_tset)],
                                           max_debt_equity=_max_de, max_payout=_max_payout,
                                           min_mos=_min_mos, buy_threshold=_buy_threshold)
    else:
        _extra_df = empty

    return exchange_dfs + (_extra_df,)


@st.cache_data(show_spinner=False, ttl=60)
def _fetch_prices_cached(tickers: tuple) -> dict:
    """Batch price feed — one HTTP call for all tickers, refreshed every 60s.

    Fair value, sector, country, and dividend fields are NOT fetched here —
    they come from the screener's own scored DataFrame (_load_all_screener_data),
    which runs the full multi-model pipeline (screener.py's _fair_value_models).
    A page that needs those alongside a live price should look them up from its
    already-loaded scored DataFrame by ticker (see uvalu/pages_/risk.py) rather
    than re-deriving them here — that used to be a second, simpler fair-value
    formula that could disagree with the screener's for the same ticker.
    """
    return fetch_prices(tickers)
