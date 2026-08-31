"""Screener/price/fundamentals data layer — cache-backed, no UI.

Functions keep their original private names so app.py and page modules can
import them unchanged. All @st.cache_data identity is preserved.
"""
import threading
import time
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from prices import fetch_prices
from uvalu.market_hours import is_market_hours
from fetch_tickers import (fetch_brussels_tickers, fetch_amsterdam_tickers,
                            fetch_paris_tickers, fetch_milan_tickers,
                            fetch_frankfurt_tickers, fetch_swiss_tickers)
from screener import (SCREENER_FETCH, PORTFOLIO_FETCH, CACHE_TTL_HOURS, _load_cache,
                      run_screener_from_df, fetch_fundamentals_nowait,
                      cancel_background_fetch, clear_live_cache, get_fetch_progress)
from settings import ALL_EXCHANGES, get_veto_thresholds, get_score_weights


def _bust_cache() -> None:
    """Cancel any background fetch, wipe the screener disk cache, and rerun.

    Only the SCREENER_FETCH lane is touched — the portfolio's own fundamentals
    cache (PORTFOLIO_FETCH) is deliberately left intact so held positions don't
    have to be re-fetched every time the screener universe is refreshed.
    """
    cancel_background_fetch(SCREENER_FETCH)
    clear_live_cache(SCREENER_FETCH)
    with SCREENER_FETCH.file_lock:   # prevents a concurrent background save landing after our wipe
        try:
            SCREENER_FETCH.cache_file.write_text("{}", encoding="utf-8")
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


_CACHE_VERSION_BUCKET_S = 30   # coarsen the mtime token — see _mtime_bucket


def _mtime_bucket(path, seconds: int = _CACHE_VERSION_BUCKET_S) -> str:
    """A cache-key token that changes at most once per `seconds` as `path` is
    written. During a background fetch _save_cache() rewrites the file every
    ~25 tickers (a few seconds apart); keying _load_all_screener_data() on the
    raw mtime made it re-score the whole universe on each of those writes.
    Bucketing to 30s caps that to one re-score per bucket — new data still
    surfaces within 30s, and the screener page's own 5s auto-rerun covers the
    gap while a fetch is active.
    """
    try:
        return str(int(path.stat().st_mtime // seconds))
    except OSError:
        return "0"


# ── WP-1: debounce the full-universe re-score during a background fetch ────────
# _load_all_screener_data is @st.cache_data keyed on _cache_version(). While a
# cold SCREENER_FETCH runs it rewrites fundamentals.json every ~25 tickers, so
# the 30s mtime bucket above still rolls over every ~15-30s for the whole
# 20-40 min fetch — every roll is a cache miss that re-scores the entire
# enabled-exchange universe (~a dozen df.apply(axis=1) passes in
# screener.compute_scores) on the next rerun. That re-score storm is the bulk
# of the "screens load slowly while data is updating" symptom.
#
# So while the fetch is running, hold the version token steady and let it
# advance at most once per RECOMPUTE_DEBOUNCE_S: new data still lands, in
# ~3-minute batches instead of ~20-second ones. Two escape hatches keep a
# genuinely cold cache responsive:
#   * the first advance after a fetch starts is always allowed (data that
#     accumulated before the first page view shows up right away), and
#   * while very few tickers have been fetched (_DEBOUNCE_COLD_DONE) the
#     debounce is bypassed entirely, so an empty universe still fills on each
#     bucket for the first page views.
# Once the fetch stops, the raw bucket is used again for one final re-score
# against the complete data.
RECOMPUTE_DEBOUNCE_S = 180
_DEBOUNCE_COLD_DONE  = 40

_version_lock = threading.Lock()
_version_state: dict = {"token": None, "advanced_at": 0.0, "was_running": False}


def _debounced_bucket(raw_bucket: str, *, running: bool, cold: bool) -> str:
    """Hold `raw_bucket` steady while a background fetch churns the cache file
    (see RECOMPUTE_DEBOUNCE_S). Process-global state, guarded by _version_lock
    since Streamlit runs script threads concurrently in one process."""
    now = time.time()
    with _version_lock:
        state = _version_state
        # Fetch just transitioned idle -> running: reset the clock so the first
        # token change of this fetch lands immediately rather than being held
        # for up to RECOMPUTE_DEBOUNCE_S behind a stale timestamp from a prior
        # fetch (or from process start).
        if running and not state["was_running"]:
            state["advanced_at"] = 0.0
        state["was_running"] = running

        if state["token"] is None:
            state.update(token=raw_bucket, advanced_at=now)
            return raw_bucket
        if raw_bucket == state["token"]:
            return state["token"]
        if running and not cold and (now - state["advanced_at"]) < RECOMPUTE_DEBOUNCE_S:
            return state["token"]
        state.update(token=raw_bucket, advanced_at=now)
        return raw_bucket


def _cache_version() -> str:
    """Coarsened mtime token for the screener fundamentals file, debounced while
    a background screener fetch is running (WP-1, see _debounced_bucket)."""
    raw  = _mtime_bucket(SCREENER_FETCH.cache_file)
    prog = get_fetch_progress(SCREENER_FETCH)
    return _debounced_bucket(
        raw,
        running=bool(prog.get("running")),
        cold=int(prog.get("done", 0)) < _DEBOUNCE_COLD_DONE,
    )


def _portfolio_cache_version() -> str:
    """Coarsened mtime token for the portfolio fundamentals file. Keyed
    separately from _cache_version() so a screener refresh doesn't bust the
    portfolio's scored data and vice-versa."""
    return _mtime_bucket(PORTFOLIO_FETCH.cache_file)


@st.cache_data(show_spinner=False)
def _load_all_screener_data(cache_version: str, enabled: tuple,
                            extra_tickers: tuple = (), extra_names: tuple = (),
                            thresholds: tuple = (500.0, 0.90, 0.0, 70.0),
                            score_weights: tuple = (0.30, 0.18, 0.22, 0.15, 0.15)) -> tuple:  # noqa: ARG001
    """
    Build screener DataFrames from whatever is in the cache right now.
    cache_version (file mtime), enabled exchanges, extra_tickers (portfolio
    stocks from disabled exchanges), thresholds (max_debt_equity, max_payout,
    min_mos, buy_threshold — see settings.get_veto_thresholds()) and
    score_weights (the screening-style sub-weight vector — see
    settings.get_score_weights()) all bust the Streamlit cache when they change.

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
                                    min_mos=_min_mos, buy_threshold=_buy_threshold,
                                    weights=score_weights)

    exchange_dfs = tuple(
        _exchange_df(stock_lists[key]) if key in stock_lists else empty
        for key in ALL_EXCHANGES
    )

    # Scored df for the extra portfolio tickers
    if _extra_stocks:
        _extra_tset = {s["ticker"] for s in _extra_stocks}
        _extra_df   = run_screener_from_df(all_fund[all_fund["Ticker"].isin(_extra_tset)],
                                           max_debt_equity=_max_de, max_payout=_max_payout,
                                           min_mos=_min_mos, buy_threshold=_buy_threshold,
                                           weights=score_weights)
    else:
        _extra_df = empty

    return exchange_dfs + (_extra_df,)


@st.cache_data(show_spinner=False)
def _load_portfolio_screener_data(pf_cache_version: str, tickers: tuple, names: tuple,
                                  thresholds: tuple = (500.0, 0.90, 0.0, 70.0),
                                  score_weights: tuple = (0.30, 0.18, 0.22, 0.15, 0.15)) -> pd.DataFrame:  # noqa: ARG001
    """Scored screener rows for the portfolio's *own* tickers (held + sold),
    fetched through the dedicated PORTFOLIO_FETCH lane — its own background
    thread, cache file and priority queue — so they never wait behind the
    exchange universe and aren't wiped by _bust_cache().

    Cache key: the portfolio cache-file mtime (pf_cache_version), the ticker
    set, the veto thresholds and the screening-style weight vector. Deliberately
    NOT keyed on enabled_exchanges, so toggling an exchange in Settings leaves
    this untouched.
    """
    _max_de, _max_payout, _min_mos, _buy_threshold = thresholds
    stocks = [{"ticker": t, "name": n, "isin": ""} for t, n in zip(tickers, names)]
    if not stocks:
        return pd.DataFrame(columns=["Ticker"])
    fund = fetch_fundamentals_nowait(stocks, fetcher=PORTFOLIO_FETCH, priority=stocks)
    if fund.empty:
        return pd.DataFrame(columns=["Ticker"])
    return run_screener_from_df(fund, max_debt_equity=_max_de, max_payout=_max_payout,
                                min_mos=_min_mos, buy_threshold=_buy_threshold,
                                weights=score_weights)


def _load_portfolio_scored(held: "pd.DataFrame | None",
                           sold: "pd.DataFrame | None" = None) -> pd.DataFrame:
    """Scored screener rows for a portfolio's own tickers (held + optionally
    sold), via the PORTFOLIO_FETCH lane only — no full-universe scoring.

    Dashboard / Portfolio / Risk use this instead of filtering
    ``_load_all_screener_data()`` down to their holdings: they only ever look
    up rows for tickers they hold, so scoring the whole enabled-exchange
    universe just to discard all but ~30 rows was pure overhead on every
    render (WP-3). One row per ticker; a held ticker on a *disabled* exchange
    is covered here too, which the old path missed.

    Ticker order is held-first then sold (deduped), and a held name wins over
    a sold name on collision — matching the inline tuple construction
    Portfolio/Risk used before, so a well-formed portfolio's
    ``_load_portfolio_screener_data`` cache entry is unchanged.
    """
    seen: dict[str, str] = {}
    for df in (held, sold):
        if df is None or getattr(df, "empty", True) or "ticker" not in df.columns:
            continue
        _names = df["name"] if "name" in df.columns else df["ticker"]
        for _t, _n in zip(df["ticker"], _names):
            _t = str(_t).strip()
            if _t and _t not in seen:
                seen[_t] = str(_n)
    if not seen:
        return pd.DataFrame(columns=["Ticker"])
    return _load_portfolio_screener_data(
        _portfolio_cache_version(), tuple(seen), tuple(seen.values()),
        get_veto_thresholds(), get_score_weights(),
    )


def prefetch_portfolio_data() -> None:
    """Warm the portfolio's fundamentals + price caches at login, before the
    first page renders. Fire-and-forget: kicks the PORTFOLIO_FETCH background
    thread and primes the shared price cache, swallowing every error so a cold
    Yahoo or an empty portfolio never blocks sign-in. Safe to call on every
    rerun — app.py gates it behind a session flag anyway.
    """
    try:
        from portfolio import load_portfolio, load_sold
        frames = [
            df for df in (load_portfolio(), load_sold())
            if df is not None and not df.empty and "ticker" in df.columns
        ]
        seen: dict[str, str] = {}
        for df in frames:
            _names = df["name"] if "name" in df.columns else df["ticker"]
            for _t, _n in zip(df["ticker"], _names):
                _t = str(_t).strip()
                if _t and _t not in seen:
                    seen[_t] = str(_n)
        if not seen:
            return
        stocks = [{"ticker": t, "name": n, "isin": ""} for t, n in seen.items()]
        fetch_fundamentals_nowait(stocks, fetcher=PORTFOLIO_FETCH, priority=stocks)
        _fetch_prices_cached(tuple(seen))
    except Exception:
        pass


def _price_bucket() -> int:
    """Market-hours-aware cache-busting token for the live price feed: a new
    value every 60s during market hours, every 900s otherwise. Passed as an
    argument to the @st.cache_data-wrapped batch fetch so its effective TTL
    tracks market hours — the decorator's own ttl= is fixed at import time and
    can't vary per call.
    """
    window = 60 if is_market_hours() else 900
    return int(time.time() // window)


@st.cache_data(show_spinner=False, ttl=60)
def _fetch_prices_batch(tickers: tuple, bucket: int = 0) -> dict:  # noqa: ARG001
    """Batch price feed — one HTTP pair (daily + 1-minute) for all tickers.

    `bucket` is the market-hours-aware cache-busting token from _price_bucket();
    it is unused in the body, present only to become part of the @st.cache_data
    key.

    Fair value, sector, country, and dividend fields are NOT fetched here —
    they come from the screener's own scored DataFrame (_load_all_screener_data),
    which runs the full multi-model pipeline (screener.py's _fair_value_models).
    A page that needs those alongside a live price should look them up from its
    already-loaded scored DataFrame by ticker (see uvalu/pages_/risk.py) rather
    than re-deriving them here — that used to be a second, simpler fair-value
    formula that could disagree with the screener's for the same ticker.
    """
    return fetch_prices(tickers)


def _fetch_prices_cached(tickers: tuple) -> dict:
    """Live price feed for a set of tickers.

    Normalises the incoming tuple (strip, dedupe, sort) so every caller —
    dashboard, portfolio, risk — collapses onto a single shared cache entry
    and a single upstream fetch, regardless of the order or duplicate tickers
    in the portfolio DataFrame they happen to pass in.
    """
    norm = tuple(sorted({str(t).strip() for t in tickers if t and str(t).strip()}))
    if not norm:
        return {}
    return _fetch_prices_batch(norm, _price_bucket())
