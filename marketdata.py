"""
Market-data provider — one wrapper around yfinance for the whole app.

Today it owns a single job: batch daily price history, disk-cached per ticker
under ``.cache/history/{ticker}.csv`` and extended incrementally so only each
ticker's missing tail is refetched. ``risk._fetch_history`` delegates here;
``prices.py`` and ``screener.py`` keep their own yfinance access for now and
migrate later (they don't need this for correctness).

The retry/backoff for Yahoo's 429s and dropped connections mirrors
``screener._run_fetch``'s per-ticker loop, adapted for ``yf.download``'s
single batch call.

Everything returned here is in each ticker's native quote currency — FX
normalisation to EUR is a separate concern (see the risk-engine plan, WS-2).
"""

from __future__ import annotations

import time
import warnings
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

# Module-level so tests can redirect them into tmp_path, like portfolio._BASE_DIR.
_HISTORY_DIR  = Path(__file__).parent / ".cache" / "history"
_DIVIDEND_DIR = Path(__file__).parent / ".cache" / "dividends"

_DIVIDEND_MAX_AGE_DAYS = 7    # dividends move a few times a year — a weekly refresh is plenty

_MAX_RETRIES     = 4
_RETRY_BASE_WAIT = 5          # seconds; doubled each attempt

# Calendar-day span for the yfinance ``period`` strings this app actually uses.
_PERIOD_DAYS = {
    "1y": 366, "2y": 731, "3y": 1096, "5y": 1827, "10y": 3653, "max": 36525,
}

_TRANSIENT_MARKERS = (
    "429", "Too Many Requests", "Rate limited", "ConnectionResetError",
    "10054", "RemoteDisconnected", "Connection aborted", "Connection reset",
)


# ── Calendar helpers ─────────────────────────────────────────────────────────

def _period_start(period: str, today: date | None = None) -> date:
    today = today or date.today()
    return today - timedelta(days=_PERIOD_DAYS.get(period, _PERIOD_DAYS["5y"]))


def _prev_business_day(d: date | None = None) -> date:
    """Most recent weekday strictly before ``d`` (today by default).

    The risk engine is end-of-day, so a cache whose newest row reaches this
    date is treated as complete and triggers no network call. Weekday-only —
    it doesn't know exchange holidays, which at worst costs one tiny, empty
    tail fetch the morning after a holiday.
    """
    d = (d or date.today()) - timedelta(days=1)
    while d.weekday() >= 5:                       # Sat = 5, Sun = 6
        d -= timedelta(days=1)
    return d


# ── Per-ticker CSV cache ─────────────────────────────────────────────────────

def _safe_name(ticker: str) -> str:
    return ticker.replace("/", "_").replace("\\", "_")


def _cache_path(ticker: str) -> Path:
    return _HISTORY_DIR / f"{_safe_name(ticker)}.csv"


def _read_series_csv(path: Path, value_col: str) -> pd.Series | None:
    """Load a two-column (date, `value_col`) CSV back into a sorted, deduped
    float Series. None on any problem."""
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, parse_dates=["date"])
        if df.empty or value_col not in df.columns:
            return None
        s = df.set_index("date")[value_col].astype(float).sort_index()
        return s[~s.index.duplicated(keep="last")]
    except Exception:
        return None


def _write_series_csv(path: Path, series: pd.Series, value_col: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = series.sort_index()
    out = out[~out.index.duplicated(keep="last")]
    frame = pd.DataFrame({
        "date":    pd.DatetimeIndex(out.index).strftime("%Y-%m-%d"),
        value_col: out.to_numpy(dtype=float),
    })
    tmp = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(tmp, index=False)
    tmp.replace(path)                             # atomic on same filesystem


def _read_cache(ticker: str) -> pd.Series | None:
    return _read_series_csv(_cache_path(ticker), "close")


def _write_cache(ticker: str, series: pd.Series) -> None:
    _write_series_csv(_cache_path(ticker), series, "close")


# ── Download ─────────────────────────────────────────────────────────────────

def _download_closes(tickers: list[str], start: date | None, period: str) -> pd.DataFrame:
    """Batch-download adjusted daily closes → DataFrame (DatetimeIndex ×
    ticker). Retries Yahoo rate-limits / dropped connections with exponential
    backoff; returns an empty frame on total failure (callers treat a missing
    column exactly as they treat a ticker Yahoo has no data for)."""
    if not tickers:
        return pd.DataFrame()

    kwargs = dict(interval="1d", auto_adjust=True, progress=False, threads=True)
    if start is not None:
        kwargs["start"] = start.strftime("%Y-%m-%d")
    else:
        kwargs["period"] = period

    raw = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                raw = yf.download(tickers, **kwargs)
            break
        except Exception as e:                    # yfinance raises bare Exception
            msg = str(e)
            transient = any(m in msg for m in _TRANSIENT_MARKERS)
            if transient and attempt < _MAX_RETRIES:
                time.sleep(_RETRY_BASE_WAIT * 2 ** attempt)
                continue
            print(f"  marketdata: price-history fetch failed ({e})")
            return pd.DataFrame()

    if raw is None or raw.empty:
        return pd.DataFrame()

    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    if not isinstance(closes, pd.DataFrame):
        closes = closes.to_frame(name=tickers[0])
    elif isinstance(closes.columns, pd.MultiIndex):
        closes = closes.copy()
        closes.columns = closes.columns.get_level_values(-1)
    if len(tickers) == 1 and closes.shape[1] == 1 and list(closes.columns) != tickers:
        closes.columns = tickers

    idx = pd.to_datetime(closes.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    closes.index = idx
    return closes.dropna(how="all")


# ── Public API ───────────────────────────────────────────────────────────────

def price_history(tickers, period: str = "5y") -> pd.DataFrame:
    """Adjusted daily closes for ``tickers`` as a DataFrame (DatetimeIndex ×
    ticker), covering roughly the trailing ``period``.

    Served from ``.cache/history/{ticker}.csv``, refetching only each ticker's
    missing tail. Called more than once the same day, later calls make no
    network request at all. A ticker whose fetch fails with no cache on disk
    is simply absent from the returned frame.
    """
    tickers = [str(t).strip() for t in dict.fromkeys(tickers) if str(t).strip()]
    if not tickers:
        return pd.DataFrame()

    today            = date.today()
    complete_through = _prev_business_day(today)
    want_start       = _period_start(period, today)

    cached: dict[str, pd.Series] = {}
    cold:  list[str] = []
    stale: list[str] = []
    for t in tickers:
        s = _read_cache(t)
        if s is None or s.empty:
            cold.append(t)
        else:
            cached[t] = s
            if s.index.max().date() < complete_through:
                stale.append(t)

    # 1. Cold tickers — one full-period batch download.
    if cold:
        fresh = _download_closes(cold, start=None, period=period)
        for t in cold:
            col = fresh[t].dropna() if t in fresh.columns else pd.Series(dtype=float)
            if not col.empty:
                cached[t] = col
                _write_cache(t, col)

    # 2. Warm-but-stale tickers — one batch download of just the missing tail.
    if stale:
        tail_start = min(cached[t].index.max().date() for t in stale) + timedelta(days=1)
        fresh = _download_closes(stale, start=tail_start, period=period)
        for t in stale:
            col = fresh[t].dropna() if t in fresh.columns else pd.Series(dtype=float)
            if col.empty:
                continue
            merged = pd.concat([cached[t], col])
            cached[t] = merged[~merged.index.duplicated(keep="last")].sort_index()
            _write_cache(t, cached[t])

    if not cached:
        return pd.DataFrame()

    out = pd.DataFrame(cached).sort_index()
    out = out[out.index >= pd.Timestamp(want_start)]
    return out.dropna(how="all")


def fx_to_eur_frame(currencies, period: str = "5y") -> pd.DataFrame:
    """Daily "EUR per 1 unit" rate for each currency, as a DataFrame
    (DatetimeIndex × ISO currency code).

    FX pairs are ordinary yfinance tickers — ``USDEUR=X`` quotes EUR per 1
    USD — so they ride the same per-ticker CSV cache as equity history.
    EUR is skipped (the caller uses 1.0); a currency with no fetchable
    history is simply absent from the frame, and the caller then leaves
    those positions in native terms.
    """
    codes = sorted({(c or "").strip().upper() for c in currencies if (c or "").strip()})
    foreign = [c for c in codes if c != "EUR"]
    if not foreign:
        return pd.DataFrame()

    pairs = {c: f"{c}EUR=X" for c in foreign}
    hist  = price_history(list(pairs.values()), period=period)
    cols: dict[str, pd.Series] = {}
    for code, pair in pairs.items():
        if pair in hist.columns:
            s = hist[pair].dropna()
            if not s.empty:
                cols[code] = s
    return pd.DataFrame(cols).sort_index() if cols else pd.DataFrame()


def dividends(ticker: str) -> pd.Series:
    """Full per-share dividend-payment history — ex-date (DatetimeIndex, tz-naive)
    → amount, oldest first.

    Disk-cached at ``.cache/dividends/{ticker}.csv`` and refetched at most
    weekly (dividends are sparse; a full re-pull of ``Ticker.dividends`` is one
    cheap call, so there's no tail-merge here). Empty Series for a non-payer, or
    on fetch failure with nothing cached.
    """
    path   = _DIVIDEND_DIR / f"{_safe_name(ticker)}.csv"
    cached = _read_series_csv(path, "amount")
    if cached is not None:
        try:
            age_days = (time.time() - path.stat().st_mtime) / 86400
        except OSError:
            age_days = _DIVIDEND_MAX_AGE_DAYS + 1
        if age_days < _DIVIDEND_MAX_AGE_DAYS:
            return cached

    try:
        raw = yf.Ticker(ticker).dividends
    except Exception:
        return cached if cached is not None else pd.Series(dtype=float, name="amount")

    if raw is None or len(raw) == 0:
        return cached if cached is not None else pd.Series(dtype=float, name="amount")

    idx = pd.to_datetime(raw.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    out = pd.Series(raw.to_numpy(dtype=float), index=idx, name="amount").sort_index()
    out = out[~out.index.duplicated(keep="last")]
    _write_series_csv(path, out, "amount")
    return out
