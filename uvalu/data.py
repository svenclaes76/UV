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
from fetch_tickers import FETCHERS, fetch_exchange_tickers, list_status
from screener import (SCREENER_FETCH, PORTFOLIO_FETCH, CACHE_TTL_HOURS, _load_cache,
                      load_fundamentals_cache, backfill_thin_rows_from_screener_lane,
                      run_screener_from_df, fetch_fundamentals_nowait,
                      cancel_background_fetch, clear_live_cache, get_fetch_progress,
                      peer_mask_for, load_founder_holdings, prune_cache)
from settings import ALL_EXCHANGES, get_veto_thresholds, get_score_weights
from uvalu import datamode, logkit, universe
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


def _previous_signals() -> dict:
    """{ticker: signal_code} last logged in the shared signal history, for
    the score hysteresis at band edges (Q1, screener._apply_signal_hysteresis).
    The same for every user and screen. Empty when the history can't be read:
    signals then follow the plain thresholds."""
    try:
        from uvalu.compliance import signal_history
        return signal_history.last_signals()
    except Exception:
        logkit.get_logger("uvalu.data").warning("signal history unreadable; no hysteresis",
                                                exc_info=True, extra={"event": "signal.history_unreadable"})
        return {}


def _founder_holdings() -> frozenset:
    """REC-8: tickers the founder holds, for the `founder_holds` disclosure.
    An unreadable file is logged as an error and treated as empty rather than
    taking the screens down; fix it, because the disclosure is then missing."""
    try:
        # P1 (EX-W4): every line of a held company, so a position held on
        # AIR.DE still discloses on the AIR.PA line the Screener shows.
        return frozenset(universe.company_lines(load_founder_holdings()))
    except Exception:
        logkit.get_logger("uvalu.data").error("founder holdings file unreadable", exc_info=True,
                                              extra={"event": "compliance.founder_holdings_failed"})
        return frozenset()


def _cache_age_str() -> str:
    from uvalu.i18n import _, fmt_num
    cache = _load_cache()
    if not cache:
        return _("No cache yet")
    timestamps = [
        datetime.fromisoformat(v["fetched_at"])
        for v in cache.values()
        if v.get("fetched_at")
    ]
    if not timestamps:
        return _("No cache yet")
    oldest = min(timestamps)
    age_min = (datetime.now(timezone.utc) - oldest).total_seconds() / 60
    if age_min < 60:
        return _("Cache age: {age} min (TTL {ttl}h)", age=fmt_num(age_min, 0), ttl=CACHE_TTL_HOURS)
    return _("Cache age: {age} h (TTL {ttl}h)", age=fmt_num(age_min / 60, 1), ttl=CACHE_TTL_HOURS)


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
    enabled_set = set(enabled)
    empty = pd.DataFrame(columns=["Ticker"])

    # EX-W4: the public universe is one line per company, its primary listing
    # (uvalu/universe.py). Listings whose cached country is already known to be
    # outside Europe aren't fetched at all; the rest are fetched, then chosen
    # between once their country is known.
    _cached_country = {t: r.get("country") for t, r in _load_cache().items()}
    stock_lists: dict[str, list[dict]] = {}
    _all_listed: set[str] = set()      # every listed ticker, foreign or not: kept by prune_cache
    _demo = not datamode.current().live_fetch
    if _demo:
        # Demo mode: the fixed demo universe instead of the exchanges' lists
        # (demo-mode plan DM-5), whatever the enabled exchanges say.
        stock_lists = _demo_stock_lists()
        _all_listed = {s["ticker"] for stocks in stock_lists.values() for s in stocks}
    else:
        for key in FETCHERS:
            if key in enabled_set:
                # The exchange's list, filtered and with share classes marked (EX-W3).
                _raw = fetch_exchange_tickers(key, FETCHERS)
                _all_listed.update(s["ticker"] for s in _raw)
                stock_lists[key] = [s for s in _raw
                                    if not universe.known_foreign(s["ticker"], _cached_country.get(s["ticker"]))]
        # Lineage (EX-W1a): which cached list, of which date, this build used.
        logkit.get_logger("uvalu.data").info(
            "ticker lists used by this build", extra={"event": "universe.ticker_lists", "lists": list_status()})
    _listed = [s for stocks in stock_lists.values() for s in stocks]
    _listed_tickers = {s["ticker"] for s in _listed}
    _fetch_extra = [
        {"ticker": t, "name": n, "isin": ""}
        for t, n in zip(extra_tickers, extra_names)
        if t not in _listed_tickers
    ]

    logkit.get_logger("uvalu.data").debug(
        "building scored universe for %d stocks", len(_listed) + len(_fetch_extra),
        extra={"event": "universe.build", "stocks": len(_listed) + len(_fetch_extra)})
    all_fund = fetch_fundamentals_nowait(_listed + _fetch_extra)
    # EX-22: drop rows of lines that left every list (and no user holds) a
    # month ago. Only when every exchange is enabled, so switching one off in
    # Admin doesn't throw away its rows.
    if enabled_set >= set(ALL_EXCHANGES) and not _demo:
        prune_cache(_all_listed | set(extra_tickers))

    if all_fund.empty:
        return (empty, empty)

    _country = (dict(zip(all_fund["Ticker"], all_fund["country"]))
                if "country" in all_fund.columns else {})
    _volume = (dict(zip(all_fund["Ticker"], all_fund["averageVolume"]))
               if "averageVolume" in all_fund.columns else {})
    _switches: list = []
    _exclusions: dict = {}
    if not _demo:   # the demo list is hand-picked home listings, on planned exchanges too
        _choice = _choose_primary_lines(stock_lists, all_fund, enabled_set)
        _kept = {s["ticker"] for s in _choice.kept}
        stock_lists = {key: [s for s in stocks if s["ticker"] in _kept]
                       for key, stocks in stock_lists.items()}
        _switches, _exclusions = _choice.switches, _choice.counts()
    all_stocks: list[dict] = [s for stocks in stock_lists.values() for s in stocks]
    _exchange_ticker_set = {s["ticker"] for s in all_stocks}
    # A user's holding that isn't a home listing is scored as an extra ticker,
    # against the public peers, never part of them (PER-2).
    _extra_stocks = [
        {"ticker": t, "name": n, "isin": ""}
        for t, n in zip(extra_tickers, extra_names)
        if t not in _exchange_ticker_set
    ]
    all_stocks.extend(_extra_stocks)
    logkit.get_logger("uvalu.data").info(
        "public universe: %d primary listings", len(_exchange_ticker_set),
        extra={"event": "universe.primary_listings", "stocks": len(_exchange_ticker_set),
               "listed": len(_listed), "extra": len(_extra_stocks), "excluded": _exclusions})

    # One scoring pass over every enabled exchange plus the extra portfolio
    # tickers: the sector medians and percentile ranks are taken across the
    # whole enabled universe (one European peer group), not per exchange. Its
    # ScoreReference is kept so the portfolio lane can score holdings against
    # the same peers (universe_reference_for).
    # PER-2: only the enabled exchanges' tickers (a shared setting) set the
    # sector medians and percentile ranks. The extra tickers (a user's manual
    # additions) are scored against those peers without moving them, so every
    # user sees the same signal for the same stock.
    _ref_out: dict = {}
    _prev_signals = _previous_signals()
    # A3: a company whose primary line switched keeps its signal history for
    # the stability rule on the new line.
    for _old, _new in _switches:
        if _old in _prev_signals and _new not in _prev_signals:
            _prev_signals[_new] = _prev_signals[_old]
    _universe_fund = all_fund[all_fund["Ticker"].isin({s["ticker"] for s in all_stocks})]
    scored = run_screener_from_df(_universe_fund,
                                  max_debt_equity=_max_de, max_payout=_max_payout,
                                  min_mos=_min_mos, buy_threshold=_buy_threshold,
                                  weights=score_weights, reference_out=_ref_out,
                                  peer_mask=peer_mask_for(_universe_fund, _exchange_ticker_set),
                                  founder_holdings=_founder_holdings(),
                                  previous_signals=_prev_signals,
                                  sector_multiples=_demo_sector_multiples() if _demo else None)
    if _ref_out.get("ref") is not None:
        _UNIVERSE_REFS[(tuple(enabled), tuple(extra_tickers), tuple(extra_names), tuple(thresholds),
                        tuple(score_weights))] = _ref_out["ref"]

    # EX-26: index memberships by company, on the scored rows (the Index
    # filter and the drawer's tags read this column); members that match no
    # row are logged, so a stale snapshot shows up.
    _index_unmatched: dict = {}
    _hidden: dict = {}
    if not scored.empty and "Ticker" in scored.columns:
        from uvalu import indices
        from uvalu import exchanges as _exchanges
        _names = {s["ticker"]: s.get("name") for stocks in stock_lists.values() for s in stocks}
        _names.update({t: n for t, n in zip(scored["Ticker"], scored.get("Name", [None] * len(scored)))
                       if t not in _names and isinstance(n, str)})
        _match = indices.match_universe(
            set(scored["Ticker"]), names=_names,
            enabled_suffixes={e.suffix for e in _exchanges.KNOWN_BY_SUFFIX.values() if e.key in enabled_set})
        _index_unmatched = _match.unmatched
        scored = scored.assign(indices=[_match.by_ticker.get(t, []) for t in scored["Ticker"]])
        _hidden = {k: c.reason for k, c in _match.checks.items() if not c.visible and c.expected}
        if not _demo and (_index_unmatched or _hidden):
            logkit.get_logger("uvalu.data").info(
                "index members without a row: %d; indices hidden: %d",
                sum(map(len, _index_unmatched.values())), len(_hidden),
                extra={"event": "index.unmatched",
                       "counts": {k: len(v) for k, v in _index_unmatched.items()},
                       "hidden": _hidden})

    # EX-35: the universe's fingerprint on every record, so the first build
    # after a coverage or exchange change marks its changes `universe_change`.
    if not scored.empty:
        scored = scored.assign(universe_id=universe.fingerprint(enabled_set))
    _changes, _shift = _record_signals(scored)
    # A demo process starts with an empty signal history, so its first build
    # logs every signal as new: not a change worth an alert.
    _log_data_quality(_universe_fund, scored, _exchange_ticker_set, _changes,
                      first_build=_demo and not _prev_signals, exclusions=_exclusions, shift=_shift,
                      index_unmatched={k: len(v) for k, v in _index_unmatched.items()},
                      index_hidden=_hidden)

    def _subset(stock_list):
        if scored.empty or "Ticker" not in scored.columns:
            return empty
        tickers = {s["ticker"] for s in stock_list}
        return scored[scored["Ticker"].isin(tickers)].reset_index(drop=True)

    # EX-W2: one frame for the whole public universe with an exchange_key
    # column (pages map it to the registry's name), instead of one frame per
    # exchange matched to its key by position.
    _key_of = {s["ticker"]: key for key, stocks in stock_lists.items() for s in stocks}
    universe_df = _subset(all_stocks[:len(all_stocks) - len(_extra_stocks)])
    if not universe_df.empty:
        universe_df = universe_df.assign(exchange_key=universe_df["Ticker"].map(_key_of))
    _extra_df = _subset(_extra_stocks) if _extra_stocks else empty
    return (universe_df, _extra_df)


def _choose_primary_lines(stock_lists: dict[str, list[dict]], all_fund: pd.DataFrame,
                          enabled_set: set) -> "universe.Choice":
    """EX-W4: one line per company among the enabled exchanges' lists, the
    saved choices updated (.cache/listing_choice.json), and the left-out
    lines counted per reason and exchange (EX-8)."""
    from screener import _traded_value_eur
    from uvalu import exchanges
    fund = all_fund.copy()
    fund["traded_value_eur"] = _traded_value_eur(fund)
    cols = [c for c in ("country", "averageVolume", "traded_value_eur", "sharesOutstanding",
                        "quoteType", "Name") if c in fund.columns]
    info = {t: dict(zip(cols, vals)) for t, *vals in zip(fund["Ticker"], *(fund[c] for c in cols))}
    # A national index member without a country from the provider takes its
    # exchange's country (indices.home_country_hints): Michelin, Linde.
    from uvalu import indices
    for t, country in indices.home_country_hints().items():
        row = info.get(t)
        if row is not None and not (isinstance(row.get("country"), str) and row["country"].strip()):
            row["country"] = country
    stocks = [s for key in stock_lists for s in stock_lists[key]]
    suffixes = {e.suffix for e in exchanges.EXCHANGES if e.key in enabled_set}
    choice = universe.choose_primary_lines(stocks, info, enabled_suffixes=suffixes)
    try:
        universe.save_choices(choice.choices)
    except OSError:
        logkit.get_logger("uvalu.data").warning("listing choices not saved", exc_info=True,
                                                extra={"event": "universe.choices_unsaved"})
    logkit.get_logger("uvalu.data").info(
        "left out of the universe: %d lines", len(choice.excluded),
        extra={"event": "universe.exclusions", "counts": choice.counts(),
               "switches": len(choice.switches)})
    return choice


def _demo_stock_lists() -> dict[str, list[dict]]:
    """The demo's 9 stocks (not the ETF), grouped by exchange key like the
    exchanges' own lists."""
    from uvalu import exchanges
    from uvalu.demo import universe as demo_universe
    lists: dict[str, list[dict]] = {}
    for t in demo_universe.STOCKS:
        ex = exchanges.for_ticker(t)
        lists.setdefault(ex.key if ex else "", []).append(
            {"ticker": t, "name": demo_universe.BY_TICKER[t].name, "isin": ""})
    return lists


def _demo_sector_multiples():
    from uvalu.demo import workspace
    ws = workspace.current()
    return ws.sector_multiples if ws else None


def _log_data_quality(fund: pd.DataFrame, scored: pd.DataFrame, public: set, changes: int,
                      first_build: bool = False, exclusions: "dict | None" = None,
                      index_unmatched: "dict | None" = None, shift: "dict | None" = None,
                      index_hidden: "dict | None" = None) -> None:
    """Q2: log the build's data-quality summary, and a warning per threshold
    crossed (uvalu/data_quality.py), except on a first build against an empty
    signal history. Never fails a build."""
    _log = logkit.get_logger("uvalu.data")
    try:
        from uvalu import data_quality
        pub_fund = fund[fund["Ticker"].isin(public)] if "Ticker" in fund.columns else fund
        pub_scored = scored[scored["Ticker"].isin(public)] if "Ticker" in scored.columns else scored
        summary = data_quality.build_summary(pub_fund, pub_scored, changes=changes, shift=shift)
        summary["excluded"] = exclusions or {}   # EX-8: per exchange, per reason
        summary["index_unmatched"] = index_unmatched or {}   # EX-26
        summary["index_hidden"] = index_hidden or {}         # quality gate: index -> reason
        _log.info("build data quality: %d rows, %d signal changes", summary["rows"], summary["signal_changes"],
                  extra={"event": "data_quality.summary", "first_build": first_build, **summary})
        for text in ([] if first_build else data_quality.alerts(summary)):
            _log.warning("data quality alert: %s", text, extra={"event": "data_quality.alert", "alert": text})
    except Exception:
        _log.error("data-quality summary failed", exc_info=True, extra={"event": "data_quality.failed"})


def _record_signals(scored: pd.DataFrame) -> "tuple[int, dict]":
    """REC-7 / REC-11: log signal changes and the day's snapshot of every
    public signal, and the model version the build used. Returns the number
    of changes logged and signal_history.shift() (a new universe or model).
    Never fails a build: an error is logged and the screens carry on."""
    shift = {"universe": False, "model": False}
    if scored is None or scored.empty:
        return 0, shift
    changes = 0
    try:
        from screener import model_version, signal_records
        from uvalu.compliance import settings_audit, signal_history
        recs = signal_records(scored)
        shift = signal_history.shift(recs)
        changes = signal_history.record_changes(recs)
        signal_history.write_daily_snapshot(recs)
        _ids = scored["model_settings_id"].dropna().unique() if "model_settings_id" in scored.columns else []
        if len(_ids):
            settings_audit.record_model_version(model_version(), str(_ids[0]))
    except Exception:
        logkit.get_logger("uvalu.data").error("signal log write failed", exc_info=True,
                                              extra={"event": "compliance.signal_log_failed"})
    return changes, shift


# ScoreReference of the last scored universe per get_scored_universe key
# (enabled, extra_tickers, extra_names, thresholds, score_weights).
_UNIVERSE_REFS: dict = {}


def universe_reference_for(key: tuple):
    return _UNIVERSE_REFS.get(key)


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
                                  score_weights: tuple = (0.30, 0.18, 0.22, 0.15, 0.15),
                                  ref_key: "tuple | None" = None,
                                  ref_version: int = 0) -> pd.DataFrame:  # noqa: ARG001
    """Scored screener rows for the portfolio's *own* tickers (held + sold),
    fetched through the dedicated PORTFOLIO_FETCH lane — its own background
    thread, cache file and priority queue — so they never wait behind the
    exchange universe and aren't wiped by _bust_cache().

    Cache key: the portfolio cache-file mtime (pf_cache_version), the ticker
    set, the veto thresholds and the screening-style weight vector. Deliberately
    NOT keyed on enabled_exchanges, so toggling an exchange in Settings leaves
    this untouched.

    ``ref_key`` / ``ref_version``: the scored universe whose ScoreReference the
    holdings are scored against (sector medians, percentile ranks), so their
    fair values, scores and signals match the Screener and Analysis page.
    ``ref_version`` is only a cache key. Without a reference (cold start, the
    universe not built yet) they are *not* ranked among themselves (PER-1: that
    would make a signal depend on what the user holds): they get "No signal"
    until the universe is built, while fair values and quality screens show.
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
                                weights=score_weights,
                                reference=universe_reference_for(ref_key) if ref_key else None,
                                user_selected=True, founder_holdings=_founder_holdings(),
                                previous_signals=_previous_signals())


def _universe_ref_args() -> tuple:
    """(ref_key, version) of the scored universe the Screener/Analysis/Watchlist
    pages show — same arguments they pass to _load_all_screener_data, so this
    shares their stored build (and starts it when none is running)."""
    from portfolio import load_manual_tickers
    from settings import load_shared_settings
    from uvalu.store import universe_reference
    enabled = tuple(load_shared_settings().get("enabled_exchanges", ALL_EXCHANGES))
    manual = load_manual_tickers()
    args = (enabled, tuple(manual.keys()), tuple(manual.values()),
            tuple(get_veto_thresholds()), tuple(get_score_weights()))
    ref, version = universe_reference(*args, token=_cache_version())
    return (args, version) if ref is not None else (None, 0)


def peer_reference_pending() -> bool:
    """True while the holdings can't be ranked yet because the universe's
    ScoreReference is still being built (cold start). In that window the
    portfolio lane gives every holding "No signal" (PER-1) and fair values
    without sector medians, so a page showing them — or an average over the
    few failed-screen rows that do carry a score (0) — would paint figures
    that change seconds later. Pages show their loading skeleton instead.
    False once a reference exists, or when no build is running (a failed or
    empty universe), so a skeleton never spins forever."""
    try:
        from uvalu.store import universe_recomputing
        ref_key, _version = _universe_ref_args()
        return ref_key is None and universe_recomputing()
    except Exception:
        return False


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
    try:
        _ref_key, _ref_version = _universe_ref_args()
    except Exception:   # no reference is never a reason to fail the portfolio screens
        logkit.get_logger("uvalu.data").warning("universe reference unavailable", exc_info=True,
                                                extra={"event": "score.reference_failed"})
        _ref_key, _ref_version = None, 0
    return _load_portfolio_screener_data(
        _portfolio_cache_version(), tuple(seen), tuple(seen.values()),
        get_veto_thresholds(), get_score_weights(), _ref_key, _ref_version,
    )


# ── Live-price overlay (WP-DQ1, B3) ──────────────────────────────────────────

def apply_live_prices(scored: "pd.DataFrame | None", live_prices: dict) -> "pd.DataFrame | None":
    """Add the live quote to a scored portfolio frame, next to the scored
    figures, without changing them.

    Adds ``live_price``, ``price_stale``, ``data_thin`` and the curated
    ``sector``. ``Price``, ``margin_of_safety`` and ``MoS %`` stay those of
    the scoring pass: a model signal is shown with the price and margin of
    safety it was computed from, and that price's time (``price_as_of``)
    (REC-4, BDG-3; decision B3 in docs/legal/compliance-implementation-plan.md).
    Until v2.1.0 this function (then ``apply_live_mos``) recomputed the
    margin of safety on the live quote, so a badge could sit next to a margin
    of safety it was never computed from.

    ``price_stale`` is True when there is no live quote, the live quote is
    more than 10% off the scored price (the scored fundamentals row is old),
    or, during a live session, the feed only had a daily close.
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

    out["live_price"] = _live
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

# risk.assess_portfolio() is a synchronous, network-bound call on a cold/stale
# cache (5y OHLC per holding + a Ken-French factor download, uvalu/pages_/
# dashboard.py's Conviction card and the whole Risk page both used to block on
# it with no placeholder). Keyed exactly like the session-state cache below —
# so a background computation started by one page/session is picked up by
# whichever page/session asks for that same key next — guarded by a lock so
# concurrent reruns for the same key don't spawn duplicate threads.
_risk_compute_running: dict[str, bool] = {}
_risk_compute_result: dict[str, object] = {}
_risk_compute_error: dict[str, BaseException] = {}
_risk_compute_lock = threading.Lock()


def load_portfolio_risk(pf: "pd.DataFrame") -> "PortfolioRisk | None":
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

    Returns ``None`` while a fresh report is still being computed in the
    background — callers must render a loading skeleton and poll (e.g. via
    ``uvalu.ui._auto_rerun``) rather than treating ``None`` as "no risk data".
    """
    import risk as _risk
    from portfolio import (load_sold, load_targets, load_risk_snapshot,
                           save_risk_snapshot, set_user)
    from portfolio_enrichment import enrich_for_risk
    from uvalu.runtime import current_user

    # Not from pre-reference scores (G1): until the universe's peer reference
    # exists the holdings carry no signals and fair values without sector
    # medians, and a report built from them would sit in the session cache
    # for an hour (Dashboard read 35, the Risk page 36, for one portfolio).
    if peer_reference_pending():
        return None
    try:
        _ref_version = _universe_ref_args()[1]
    except Exception:
        _ref_version = 0

    live = _fetch_prices_cached(tuple(pf["ticker"].tolist()))
    # Live quote alongside the scored figures (B3: the scored Price and MoS
    # stay those the signal was computed from).
    scored = apply_live_prices(_load_portfolio_scored(pf, load_sold()), live)
    veto_lookup = (scored.set_index("Ticker")["veto"].to_dict()
                   if "veto" in getattr(scored, "columns", []) else {})
    scored_by_ticker = (
        scored.drop_duplicates(subset="Ticker", keep="first").set_index("Ticker")
        if not scored.empty else scored
    )
    pf_enriched = enrich_for_risk(pf, scored_by_ticker, live)

    cache = load_fundamentals_cache()
    weighting = "standard"   # PER-3: a model setting, never derived from a user objective
    targets = load_targets()
    prior_snapshot = load_risk_snapshot()

    key = str((tuple(sorted(pf_enriched["ticker"].tolist())), weighting,
               tuple(sorted(veto_lookup.items())),
               repr(sorted(targets.items())), _ref_version))
    cached = st.session_state.get("_risk_report_cache", {})
    report = None
    if cached.get("key") == key and "report" in cached:
        _gen = datetime.fromisoformat(cached["report"].generated_at)
        if (datetime.now(timezone.utc) - _gen).total_seconds() < _RISK_REPORT_TTL_S:
            report = cached["report"]

    if report is None:
        with _risk_compute_lock:
            report = _risk_compute_result.pop(key, None)
            _error = _risk_compute_error.pop(key, None)
            already_running = _risk_compute_running.get(key, False)
            if report is None and _error is None and not already_running:
                _risk_compute_running[key] = True
                _spawn = True
            else:
                _spawn = False

        if _error is not None:
            # Surface it on THIS (consuming) rerun exactly like the old
            # synchronous call would have — callers already wrap
            # load_portfolio_risk() in their own try/except. Re-raising
            # rather than silently retrying forever also means a
            # persistently-failing input (bad ticker, unreachable factor
            # data) fails once per rerun instead of respawning a thread that
            # would just fail again immediately.
            raise _error

        if report is not None:
            st.session_state["_risk_report_cache"] = {"key": key, "report": report}
            # Upsert today's snapshot as the reference point for future drift
            # checks — once per day, so the diff is against a real prior run.
            # Runs on this (consuming) rerun's own thread, already correctly
            # user-scoped via app.py's per-run set_user(), not inside the
            # background thread below.
            if prior_snapshot.get("date") != date.today().isoformat():
                try:
                    save_risk_snapshot(_risk.snapshot_from_report(report))
                except Exception:
                    pass
        else:
            if _spawn:
                _email = current_user().email

                _n_tickers = len(pf_enriched)

                def _run() -> None:
                    try:
                        # _user_dir() (load_targets/load_risk_snapshot above
                        # already ran on the main thread, correctly scoped —
                        # this only guards assess_portfolio itself, which
                        # doesn't touch user-scoped storage, but a freshly
                        # spawned thread still starts with no thread-local
                        # active user at all, same class of bug
                        # ensure_value_history_fresh already had to handle).
                        set_user(_email)
                        with logkit.job("risk_report", trigger="cache_miss",
                                        tickers=_n_tickers):
                            _r = _risk.assess_portfolio(
                                pf_enriched, cache, weighting=weighting, veto_lookup=veto_lookup,
                                targets=targets, prior_snapshot=prior_snapshot)
                        with _risk_compute_lock:
                            _risk_compute_result[key] = _r
                    except BaseException as _e:  # noqa: BLE001 — re-raised on the consuming rerun, see above
                        with _risk_compute_lock:
                            _risk_compute_error[key] = _e
                    finally:
                        with _risk_compute_lock:
                            _risk_compute_running[key] = False

                logkit.spawn(_run, name="risk_report")
            return None

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
        logkit.get_logger("uvalu.data").warning(
            "portfolio prefetch failed", exc_info=True,
            extra={"event": "job.failed", "job": "portfolio_prefetch"})


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
