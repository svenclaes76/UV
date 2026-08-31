"""Off-thread scored-universe store (WP-5 of the instant-paint plan).

``uvalu.data._load_all_screener_data`` used to run the full per-exchange
``compute_scores`` pass (~a dozen ``df.apply(axis=1)`` sweeps over ~2000 rows)
*plus* 1-6 live stockanalysis.com ticker-list scrapes on the Streamlit render
thread — every time ``_cache_version()`` advanced (WP-1 debounces that to ~once
per 3 min during a background fetch, plus on fetch completion / exchange toggle
/ threshold change). That was the last big blocking cost on the Screener /
Watchlist / Analysis render path.

This module moves the work to a background daemon thread. Pages read the last
successfully computed 7-tuple instantly (empty frames on a cold start); a
recompute is kicked when the underlying fundamentals-cache token has moved.
One entry per ``(enabled, extra_tickers, extra_names, thresholds, weights)``
key — the same parameters ``_build_all_screener_data`` takes.
"""
import threading
import time

import pandas as pd

from settings import ALL_EXCHANGES

_EMPTY = pd.DataFrame(columns=["Ticker"])
_EMPTY_TUPLE = tuple(_EMPTY for _ in ALL_EXCHANGES) + (_EMPTY,)

# Don't respawn a worker for the same key within this many seconds of the last
# attempt: throttles the cold-start / fetch-complete / manual-refresh bursts
# (where the token can move a few times in quick succession) and caps the retry
# rate if a build keeps failing.
_MIN_RECOMPUTE_INTERVAL_S = 10.0


class _UniverseStore:
    """Process-global, shared across every Streamlit session in this process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[tuple, dict] = {}

    def _entry(self, key: tuple) -> dict:
        e = self._entries.get(key)
        if e is None:
            e = self._entries[key] = {
                "frame": _EMPTY_TUPLE, "version": 0, "token": None,
                "computed_at": 0.0, "attempt_at": 0.0, "thread": None,
            }
        return e

    def get(self, key: tuple, token: str, builder) -> tuple:
        """Return ``(frame_tuple, version, is_stale)``.

        Never computes on the caller's thread. Spawns a background recompute
        when ``token`` differs from the stored frame's token, no worker is
        already running for this key, and the last attempt was long enough ago.
        """
        now = time.time()
        with self._lock:
            e = self._entry(key)
            frame, version = e["frame"], e["version"]
            is_stale = e["token"] != token
            alive = e["thread"] is not None and e["thread"].is_alive()
            if is_stale and not alive and (now - e["attempt_at"]) >= _MIN_RECOMPUTE_INTERVAL_S:
                e["attempt_at"] = now
                e["thread"] = threading.Thread(
                    target=self._recompute, args=(key, token, builder), daemon=True)
                e["thread"].start()
        return frame, version, is_stale

    def _recompute(self, key: tuple, token: str, builder) -> None:
        try:
            new_frame = tuple(builder())
        except Exception:
            return  # leave the previous frame in place; get() retries after the interval
        with self._lock:
            e = self._entry(key)
            e["frame"] = new_frame
            e["token"] = token
            e["version"] += 1
            e["computed_at"] = time.time()

    def recomputing(self) -> bool:
        with self._lock:
            return any(e["thread"] is not None and e["thread"].is_alive()
                       for e in self._entries.values())

    def version(self) -> int:
        """Sum of per-key frame versions — a single 'something recomputed'
        counter for version-diffing auto-reruns (WP-6). With the one screener
        key in play this is just that key's version."""
        with self._lock:
            return sum(e["version"] for e in self._entries.values())

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_STORE = _UniverseStore()


def get_scored_universe(enabled, extra_tickers=(), extra_names=(),
                        thresholds=(500.0, 0.90, 0.0, 70.0),
                        score_weights=(0.30, 0.18, 0.22, 0.15, 0.15),
                        *, token: "str | None" = None) -> tuple:
    """``(frame_tuple, version, is_stale)`` for the scored exchange universe.

    Served from the process-global store: the per-exchange ``compute_scores``
    pass and the ticker-list scrapes run on a background thread, never the
    caller's. ``token`` is the staleness marker (default:
    ``uvalu.data._cache_version()``). ``frame_tuple`` is the 7-tuple
    ``_build_all_screener_data`` returns; its DataFrames are copied so a caller
    may mutate them freely.
    """
    from uvalu.data import _cache_version, _build_all_screener_data
    enabled       = tuple(enabled)
    extra_tickers = tuple(extra_tickers)
    extra_names   = tuple(extra_names)
    thresholds    = tuple(thresholds)
    score_weights = tuple(score_weights)
    key = (enabled, extra_tickers, extra_names, thresholds, score_weights)
    tok = token if token is not None else _cache_version()

    def _builder():
        return _build_all_screener_data(enabled, extra_tickers, extra_names,
                                        thresholds, score_weights)

    frame, version, is_stale = _STORE.get(key, tok, _builder)
    return tuple(d.copy() for d in frame), version, is_stale


def universe_recomputing() -> bool:
    """True while a background scored-universe recompute is in flight — pages
    use this to keep a loading skeleton polling (see
    ``uvalu.ui.poll_while_fetching``)."""
    return _STORE.recomputing()


def universe_version() -> int:
    """Monotonic-ish counter that advances every time the store finishes a
    recompute — the version-diff signal for the Screener/Watchlist auto-refresh
    fragments (WP-6, via ``uvalu.data.screener_refresh_signature``)."""
    return _STORE.version()


def clear_scored_universe() -> None:
    """Drop every stored frame so the next ``get_scored_universe`` rebuilds.
    Wired to ``uvalu.data._load_all_screener_data.clear`` for the existing
    admin / settings / ``_bust_cache`` call sites."""
    _STORE.clear()
