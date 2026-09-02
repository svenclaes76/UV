"""Screener/price/fundamentals data layer — cache-backed, no UI.

Functions keep their original private names so app.py and page modules can
import them unchanged. All @st.cache_data identity is preserved.
"""
import threading
import time
from datetime import date, datetime, timezone
from typing import NamedTuple

import pandas as pd
import streamlit as st

from prices import fetch_prices
from uvalu.market_hours import is_market_hours, MARKET_TZ
from fetch_tickers import (fetch_brussels_tickers, fetch_amsterdam_tickers,
                            fetch_paris_tickers, fetch_milan_tickers,
                            fetch_frankfurt_tickers, fetch_swiss_tickers)
from screener import (SCREENER_FETCH, PORTFOLIO_FETCH, CACHE_TTL_HOURS, _load_cache,
                      load_fundamentals_cache, backfill_thin_rows_from_screener_lane,
                      run_screener_from_df, fetch_fundamentals_nowait,
                      cancel_background_fetch, clear_live_cache, get_fetch_progress)
from settings import ALL_EXCHANGES, get_veto_thresholds, get_score_weights
from uvalu.store import get_scored_universe, clear_scored_universe


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


def _build_all_screener_data(enabled: tuple,
                             extra_tickers: tuple = (), extra_names: tuple = (),
                             thresholds: tuple = (500.0, 0.90, 0.0, 70.0),
                             score_weights: tuple = (0.30, 0.18, 0.22, 0.15, 0.15)) -> tuple:
    """Build the per-exchange scored DataFrames from whatever is in the
    fundamentals cache right now.

    enabled exchanges, extra_tickers (portfolio stocks from disabled
    exchanges), thresholds (max_debt_equity, max_payout, min_mos, buy_threshold
    — see settings.get_veto_thresholds()) and score_weights (the screening-style
    sub-weight vector — see settings.get_score_weights()) select what is built.
    extra_tickers are folded into the single fetch_fundamentals_nowait call so
    they share the same background-fetch thread, cache file, and refresh cadence
    as the screener; their scored DataFrame is the last element of the tuple.

    Runs on uvalu.store's background worker, never the Streamlit render thread
    (WP-5) — it does the full compute_scores pass plus up to six live
    stockanalysis.com ticker-list scrapes.
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


def _load_all_screener_data(cache_version: str, enabled: tuple,
                            extra_tickers: tuple = (), extra_names: tuple = (),
                            thresholds: tuple = (500.0, 0.90, 0.0, 70.0),
                            score_weights: tuple = (0.30, 0.18, 0.22, 0.15, 0.15)) -> tuple:
    """Non-blocking accessor for the scored exchange universe (WP-5).

    Returns uvalu.store's last successfully computed 7-tuple immediately (empty
    frames on a cold start) and kicks a background recompute when
    `cache_version` (the WP-1-debounced fundamentals-file mtime token) has
    moved past what the stored frame was built from. The heavy per-exchange
    compute_scores pass and the ticker-list scrapes never touch the render
    thread now.

    Kept as the name + signature every page / Analysis / admin already imports.
    `.clear()` drops the store so the next call rebuilds (see
    uvalu.store.clear_scored_universe — wired below).
    """
    frame, _version, _is_stale = get_scored_universe(
        enabled, extra_tickers, extra_names, thresholds, score_weights,
        token=cache_version)
    return frame


_load_all_screener_data.clear = clear_scored_universe


def screener_refresh_signature() -> tuple:
    """Version-diff key for the Screener / Watchlist auto-refresh fragments
    (WP-6, passed to uvalu.ui._auto_rerun). Changes when the off-thread store
    finishes a recompute, when the background fetch's progress advances by ~25
    tickers, or when it starts / stops — so those 5s poll fragments stop
    re-rendering the page into identical output between recomputes.

    Plain function, no st.* — it runs inside the timer fragment.
    """
    from uvalu.store import universe_version
    _p = get_fetch_progress(SCREENER_FETCH)
    return (universe_version(), bool(_p.get("running")), (_p.get("done") or 0) // 25)


def _price_refresh_signature() -> tuple:
    """Version-diff key for the live-price auto-refresh fragments (WP-6). Changes
    when the market-hours-aware price bucket rolls (a fresh upstream quote fetch
    is due), when the portfolio fetch lane advances / stops, or when its scored
    frame's mtime token moves. Plain function, no st.*."""
    _p = get_fetch_progress(PORTFOLIO_FETCH)
    return (_price_bucket(), _portfolio_cache_version(),
            bool(_p.get("running")), (_p.get("done") or 0) // 10)


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
    # WP-C: if the portfolio lane cached a row too thin to value but the screener
    # lane already holds a complete one for that ticker, borrow it — a degraded
    # payload otherwise sits until its short TTL (WP-A) expires.
    fund = backfill_thin_rows_from_screener_lane(fund)
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


# ── Live-price margin of safety overlay (WP-DQ1) ─────────────────────────────

def apply_live_mos(scored: "pd.DataFrame | None", live_prices: dict) -> "pd.DataFrame | None":
    """Refresh ``Price`` / ``live_price`` / ``MoS %`` on a scored portfolio
    frame so the Holdings ladder's three numbers reconcile.

    ``screener.compute_scores`` computes ``margin_of_safety`` / ``MoS %``
    against the fundamentals-cache ``Price`` snapshot, which can be hours or
    days stale. The portfolio screens render that percentage next to a live
    price and a fair value, so the three didn't agree — worst case a holding
    shown "at fair value" beside a deeply negative MoS because its cached
    price was weeks old (WP-DQ1).

    This recomputes ``margin_of_safety`` = ``(fair_value − live_price) /
    fair_value`` from the batch fair value and the live quote. It deliberately
    leaves ``fair_value``, the six sub-model values, ``Value Score``, the
    ``Sub *`` ranks and ``Decision`` on the universe-ranked batch basis: those
    need the whole scored universe and are not live figures. Only ``EPV``'s
    net-debt term is price-sensitive in the fair-value blend, a second-order
    effect not worth a row-wise model re-run here.

    Adds ``price_stale`` — True when there is no live quote, or the live quote
    is more than 10% off the batch price (a sign the cached fundamentals row,
    and so the fair value built from it, is old).
    """
    if scored is None or getattr(scored, "empty", True) or "Ticker" not in getattr(scored, "columns", []):
        return scored

    out = scored.copy()
    _batch_price = pd.to_numeric(out.get("Price"), errors="coerce")
    _live = pd.to_numeric(
        out["Ticker"].map(lambda t: (live_prices.get(str(t)) or {}).get("price")),
        errors="coerce",
    )
    _src = out["Ticker"].map(lambda t: (live_prices.get(str(t)) or {}).get("quote_source"))
    _price = _live.where(_live > 0, _batch_price)

    out["live_price"] = _live
    out["Price"] = _price
    # A row's price is "stale" for display purposes when there's no live
    # quote, the live quote is >10% off the cached price (old fundamentals
    # row), or — during a live session — the feed only had a daily close for
    # it, not an intraday tick (WP-DQ1 + WP-DQ8).
    out["price_stale"] = (
        _live.isna()
        | (_batch_price.notna() & _live.notna() & _batch_price.gt(0)
           & (_live / _batch_price - 1).abs().gt(0.10))
        | (is_market_hours() & _src.isin(["eod", "stale"]))
    )

    if "fair_value" in out.columns:
        _fv = pd.to_numeric(out["fair_value"], errors="coerce")
        _mos = ((_fv - _price) / _fv).where((_price > 0) & (_fv > 0))
        out["margin_of_safety"] = _mos
        out["MoS %"] = (_mos * 100).round(1)

    # WP-E: `data_thin` == "no fair value AND none of the six models can produce
    # one from this row's own fundamentals" — i.e. a partial provider payload
    # still being refetched (WP-A gives it a short TTL). The Holdings ladder
    # shows a "fv pending" hint for these instead of the bare "—" a genuinely
    # unvaluable business gets. A row that already carries a fair value (incl. a
    # WP-B EPS-derived one, or a WP-C cross-lane backfill) is never `data_thin`.
    from screener import _row_is_scorable
    _fv_missing = (pd.to_numeric(out["fair_value"], errors="coerce").isna()
                   if "fair_value" in out.columns else pd.Series(True, index=out.index))
    out["data_thin"] = _fv_missing & ~out.apply(_row_is_scorable, axis=1)

    # Curated sector fallback for provider-unclassified names (WP-DQ7) — so a
    # drawer opened from the Portfolio page shows the same sector the Dashboard
    # donut and the Risk page do.
    from screener import sector_for
    out["sector"] = [
        sector_for(t, s) for t, s in zip(out["Ticker"], out.get("sector", pd.Series(index=out.index, dtype=object)))
    ]
    return out


# ── Shared portfolio risk report (WP-DQ4) ────────────────────────────────────
# The Risk page and the Dashboard's "Conviction & risk" card both render
# risk.assess_portfolio() output. They used to build it independently with
# different arguments — the Dashboard passed neither the hard-veto lookup nor
# the sector/country/fair-value-enriched frame — so the same portfolio showed
# two different composite risk scores side by side (e.g. Risk page 29 vs
# Dashboard 32). This is the one builder both call: identical inputs, a single
# session-cached RiskReport.

class PortfolioRisk(NamedTuple):
    report: object            # risk.RiskReport
    scored: pd.DataFrame      # _load_portfolio_scored(held, sold) — one row/ticker
    veto_lookup: dict         # {ticker: bool} from the screener's own `veto` column
    pf: pd.DataFrame          # the portfolio enriched for the risk engine


_RISK_REPORT_TTL_S = 3600


def load_portfolio_risk(pf: "pd.DataFrame") -> PortfolioRisk:
    """Build (or return the session-cached) portfolio ``RiskReport`` plus the
    scored-holdings frame and hard-veto lookup the consumer pages also need.

    Enriches ``pf`` via ``portfolio_enrichment.enrich_for_risk`` (live price →
    ``current_value``, plus ``fair_value`` / ``sector`` / ``country`` /
    ``expected_annual`` from the portfolio screener lane) and calls
    ``risk.assess_portfolio`` with the hard-veto lookup, target allocation and
    prior snapshot — the full-fidelity argument set the Risk page always used.

    Cached in ``st.session_state`` keyed on the ticker set, the veto lookup and
    the target allocation, with a 1-hour TTL (day rollover covered in
    practice). Deliberately not keyed on the snapshot, which this call also
    writes — keying on it would self-invalidate the cache on the next render.
    """
    import risk as _risk
    from portfolio import (load_sold, load_targets, load_risk_snapshot,
                           save_risk_snapshot)
    from portfolio_enrichment import enrich_for_risk

    live = _fetch_prices_cached(tuple(pf["ticker"].tolist()))
    # Refresh Price / MoS on the live quote so the drawer opened from this
    # page (and the Dashboard, which shares this frame's convention) shows a
    # margin of safety that agrees with the price beside it (WP-DQ1).
    scored = apply_live_mos(_load_portfolio_scored(pf, load_sold()), live)
    veto_lookup = (scored.set_index("Ticker")["veto"].to_dict()
                   if "veto" in getattr(scored, "columns", []) else {})
    scored_by_ticker = (
        scored.drop_duplicates(subset="Ticker", keep="first").set_index("Ticker")
        if not scored.empty else scored
    )
    pf_enriched = enrich_for_risk(pf, scored_by_ticker, live)

    cache = load_fundamentals_cache()
    income_portfolio = False
    targets = load_targets()
    prior_snapshot = load_risk_snapshot()

    key = str((tuple(sorted(pf_enriched["ticker"].tolist())), income_portfolio,
               tuple(sorted(veto_lookup.items())),
               repr(sorted(targets.items()))))
    cached = st.session_state.get("_risk_report_cache", {})
    report = None
    if cached.get("key") == key and "report" in cached:
        _gen = datetime.fromisoformat(cached["report"].generated_at)
        if (datetime.now(timezone.utc) - _gen).total_seconds() < _RISK_REPORT_TTL_S:
            report = cached["report"]

    if report is None:
        report = _risk.assess_portfolio(
            pf_enriched, cache, income_portfolio, veto_lookup,
            targets=targets, prior_snapshot=prior_snapshot)
        st.session_state["_risk_report_cache"] = {"key": key, "report": report}
        # Upsert today's snapshot as the reference point for future drift
        # checks — once per day, so the diff is against a real prior run.
        if prior_snapshot.get("date") != date.today().isoformat():
            try:
                save_risk_snapshot(_risk.snapshot_from_report(report))
            except Exception:
                pass

    return PortfolioRisk(report, scored, veto_lookup, pf_enriched)


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

    Side effect: stashes a ``price_feed_status()`` summary of the result in
    ``st.session_state["_price_feed_status"]`` so the shell topbar can show a
    truthful "as of" / delayed / closed indicator (WP-DQ8).
    """
    norm = tuple(sorted({str(t).strip() for t in tickers if t and str(t).strip()}))
    if not norm:
        return {}
    _map = _fetch_prices_batch(norm, _price_bucket())
    try:
        st.session_state["_price_feed_status"] = price_feed_status(_map)
    except Exception:
        pass
    return _map


def price_feed_status(price_map: dict) -> dict:
    """Summarise a ``prices.fetch_prices`` result for the freshness indicator.

    Returns ``as_of`` (a MARKET_TZ-aware datetime, the batch fetch time — all
    tickers in one batch share it), ``market_open``, and per-``quote_source``
    counts. "delayed" = tickers still on the most recent daily close during a
    live session; "stale" = served from the last-known-good cache.
    """
    entries = [e for e in price_map.values() if isinstance(e, dict)]
    as_of = None
    for e in entries:
        raw = e.get("as_of")
        if raw:
            try:
                dt = datetime.fromisoformat(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt = dt.astimezone(MARKET_TZ)
                as_of = dt if as_of is None else max(as_of, dt)
            except ValueError:
                pass
    srcs = [e.get("quote_source") for e in entries if e.get("price") is not None]
    return {
        "as_of":       as_of,
        "market_open": is_market_hours(),
        "total":       len(srcs),
        "intraday":    sum(s == "intraday" for s in srcs),
        "delayed":     sum(s == "eod" for s in srcs),
        "stale":       sum(s == "stale" for s in srcs),
    }
