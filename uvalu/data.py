"""Screener/price/fundamentals data layer — cache-backed, no UI.

Functions keep their original private names so app.py and page modules can
import them unchanged. All @st.cache_data identity is preserved.
"""
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf
import streamlit as st

from prices import fetch_prices
from fetch_tickers import (fetch_brussels_tickers, fetch_amsterdam_tickers,
                            fetch_paris_tickers, fetch_milan_tickers,
                            fetch_frankfurt_tickers, fetch_swiss_tickers)
from screener import (CACHE_FILE, CACHE_TTL_HOURS, _load_cache,
                      run_screener_from_df, fetch_fundamentals_nowait,
                      cancel_background_fetch, clear_live_cache, _file_lock)
from settings import ALL_EXCHANGES
import risk as _risk_module


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


def _compute_fair_values(info: dict) -> dict:
    eps  = info.get("trailingEps")
    bvps = info.get("bookValue")

    # Graham Number: √(22.5 × EPS × BVPS) — requires positive EPS and BVPS
    graham_number = None
    if eps and bvps and eps > 0 and bvps > 0:
        graham_number = round((22.5 * eps * bvps) ** 0.5, 2)

    # PE Fair Value: EPS × 15 (Graham's assumed fair P/E for a no-growth company)
    pe_fair_value = None
    if eps and eps > 0:
        pe_fair_value = round(eps * 15, 2)

    # Graham Growth: EPS × (8.5 + 2g) where g is expected annual earnings growth (%)
    # Uses earningsGrowth (TTM) as a proxy; clamped to [-5%, 25%] to avoid extremes.
    graham_growth = None
    raw_growth = info.get("earningsGrowth") or info.get("revenueGrowth")
    if eps and eps > 0 and raw_growth is not None:
        g = max(-5.0, min(25.0, raw_growth * 100))
        graham_growth = round(eps * (8.5 + 2 * g), 2)
        if graham_growth <= 0:
            graham_growth = None

    analyst_target = info.get("targetMeanPrice")

    # Composite: average of all available positive estimates
    estimates = [v for v in [graham_number, pe_fair_value, graham_growth, analyst_target]
                 if v is not None and v > 0]
    composite = round(sum(estimates) / len(estimates), 2) if estimates else None

    return {
        "graham_number": graham_number,
        "pe_fair_value": pe_fair_value,
        "graham_growth": graham_growth,
        "fair_value":    composite,
    }


@st.cache_data(show_spinner=False, ttl=60)
def _fetch_prices_cached(tickers: tuple) -> dict:
    """Batch price feed — one HTTP call for all tickers, refreshed every 60s."""
    return fetch_prices(tickers)


@st.cache_data(show_spinner=False, ttl=21_600)
def _fetch_fundamentals(tickers: tuple) -> dict:
    """
    Per-ticker fundamentals (EPS, BVPS, analyst targets, div rate) via yf.info.
    Cached for 6 h — these change quarterly, not by the minute.
    """
    result = {}
    _empty = {
        "analyst_target": None, "div_rate": 0,
        "graham_number": None, "pe_fair_value": None,
        "graham_growth": None, "fair_value": None,
        "sector": None, "country": None,
    }
    for t in tickers:
        if not t or not isinstance(t, str):
            result[t] = dict(_empty)
            continue
        try:
            info = yf.Ticker(t).info
            fv   = _compute_fair_values(info)
            result[t] = {
                "analyst_target": info.get("targetMeanPrice"),
                "div_rate":       info.get("trailingAnnualDividendRate") or 0,
                "sector":         info.get("sector") or None,
                "country":        info.get("country") or None,
                **fv,
            }
        except Exception:
            result[t] = dict(_empty)
    return result


def _fetch_live_data(tickers: tuple) -> dict:
    """Merge fast batch prices with slower-moving fundamentals."""
    prices = _fetch_prices_cached(tickers)
    fundas = _fetch_fundamentals(tickers)
    return {
        t: {**fundas.get(t, {}), **prices.get(t, {})}
        for t in tickers
    }


def get_cached_risk_report(session_key: str, pf: pd.DataFrame, risk_cache: dict,
                           income_portfolio: bool = False):
    """1-hour session_state-cached wrapper around risk.assess_portfolio() —
    it fetches 5y of price history per holding and runs a factor regression,
    expensive enough that recomputing it on every Streamlit rerun (a widget
    toggle elsewhere on the same page, not just a genuine data refresh) is
    wasteful. `session_key` scopes the cache slot — pass a DIFFERENT key per
    call site whose `pf` enrichment differs (e.g. uvalu/pages_/dashboard.py's
    Conviction & risk card doesn't enrich `pf` with sector/country/fair_value/
    expected_annual the way uvalu/pages_/risk.py's own report does — see that
    function's docstring), so a lighter computation from one page never gets
    served as if it were the other's full report."""
    _key = str((tuple(sorted(pf["ticker"].tolist())), income_portfolio))
    _cached = st.session_state.get(session_key, {})
    if _cached.get("key") == _key and "report" in _cached:
        _gen_at = datetime.fromisoformat(_cached["report"].generated_at)
        if (datetime.now(timezone.utc) - _gen_at).total_seconds() < 3600:
            return _cached["report"]
    report = _risk_module.assess_portfolio(pf, risk_cache, income_portfolio)
    st.session_state[session_key] = {"key": _key, "report": report}
    return report
