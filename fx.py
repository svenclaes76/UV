"""
FX rates — frankfurter.dev (ECB reference rates), Uvalu's single FX source.

Every currency conversion in the app goes through here: the cash ledger's
per-entry rate (``get_rate``), the dividend log's EUR restatement and the risk
engine's EUR restatement of price history (both via ``rates_frame``, the latter
through the ``marketdata.fx_to_eur_frame`` shim). Using one source means a CHF
dividend converts at the same rate on the Dividends page, the Dashboard and in
the cash ledger.

frankfurter publishes the ECB's daily reference rates (~16:00 CET, business
days only). Weekends and holidays resolve to the previous business day — the
same "last known rate" behaviour the forward-filled series gives.

Rates are cached in ``.cache/fx_frankfurter.json`` (public data, so not
encrypted): historical days never change and are kept forever; the last few
days are re-checked at most hourly so today's fixing lands once published.
Each (base, currency) pair tracks the contiguous date range it has fetched, so
later calls only request the missing head/tail.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from uvalu import logkit

_log = logkit.get_logger("uvalu.fx")

API_BASE = os.environ.get("UVALU_FX_API", "https://api.frankfurter.dev/v1").rstrip("/")
TIMEOUT_S = 4.0
ECB_FIRST_DATE = date(1999, 1, 4)          # first ECB reference-rate fixing
FALLBACK_CURRENCIES = ["EUR", "USD", "GBP", "CHF", "SEK", "DKK", "NOK"]

# Module-level so tests can redirect it into tmp_path, like portfolio._BASE_DIR.
_CACHE_FILE = Path(__file__).parent / ".cache" / "fx_frankfurter.json"

_RECENT_DAYS = 4           # trailing window re-checked for a newly published fixing
_RECENT_TTL_S = 3600       # ... at most this often
_LOOKBACK_DAYS = 10        # get_rate: how far back a "previous business day" may be
_CHUNK_DAYS = 366          # max span per time-series request
_CURRENCIES_TTL_S = 86400

_lock = threading.RLock()
_cache: dict | None = None
_currencies: tuple[float, list[str]] | None = None


class FxUnavailable(Exception):
    """frankfurter.dev is unreachable or has no rate for this currency/date."""


@dataclass(frozen=True)
class FxQuote:
    rate: float          # base-currency units per 1 unit of the quoted currency
    rate_date: date      # the ECB fixing date actually used
    source: str = "ecb"  # "ecb" | "base" (currency == base, rate 1.0)


# ── HTTP seam ────────────────────────────────────────────────────────────────

def _http_get(path: str, params: dict | None = None) -> dict:
    """GET ``{API_BASE}/{path}`` and return the JSON body. Raises FxUnavailable
    on any network error or non-200 response. Tests monkeypatch this."""
    url = f"{API_BASE}/{path.lstrip('/')}"
    body = None
    try:
        with logkit.external_call("frankfurter", params={"path": path, **(params or {})},
                                  logger="uvalu.fx") as call:
            r = requests.get(url, params=params, timeout=TIMEOUT_S)
            if r.status_code != 200:
                call.note(status=str(r.status_code))
            else:
                body = r.json()
    except Exception as exc:  # already logged by external_call
        raise FxUnavailable(f"frankfurter unreachable: {exc}") from exc
    if body is None:
        raise FxUnavailable(f"frankfurter returned no data for {path}")
    return body


# ── Cache ────────────────────────────────────────────────────────────────────

def _load_cache() -> dict:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
            if not isinstance(_cache, dict):
                _cache = {}
        except Exception:
            _cache = {}
    return _cache


def _save_cache() -> None:
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _CACHE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(_cache or {}), encoding="utf-8")
        os.replace(tmp, _CACHE_FILE)
    except Exception:
        _log.warning("could not write FX cache", exc_info=True,
                     extra={"event": "fx.cache_write_failed"})


def _reset_for_tests() -> None:
    global _cache, _currencies
    with _lock:
        _cache = None
        _currencies = None


def _entry(base: str, ccy: str) -> dict:
    series = _load_cache().setdefault("series", {})
    return series.setdefault(base, {}).setdefault(ccy, {"rates": {}})


def _fetch_range(base: str, ccy: str, start: date, end: date) -> dict[str, float]:
    """Base-currency units per 1 ``ccy`` for every ECB fixing in [start, end],
    chunked so no single request spans more than _CHUNK_DAYS."""
    out: dict[str, float] = {}
    s = start
    while s <= end:
        e = min(end, s + timedelta(days=_CHUNK_DAYS - 1))
        body = _http_get(f"{s.isoformat()}..{e.isoformat()}", {"base": ccy, "symbols": base})
        rates = body.get("rates") or {}
        for day, row in rates.items():
            v = (row or {}).get(base) if isinstance(row, dict) else None
            if v:
                out[str(day)[:10]] = float(v)
        s = e + timedelta(days=1)
    return out


def _ensure(base: str, ccy: str, start: date, end: date) -> tuple[dict[str, float], Exception | None]:
    """Make sure [start, end] is cached for (base, ccy); fetch only the gaps.
    Returns (all cached rates for the pair, last fetch error or None) — a
    failed fetch never discards what's already cached."""
    today = date.today()
    start = max(start, ECB_FIRST_DATE)
    end = min(end, today)
    with _lock:
        ent = _entry(base, ccy)
        if start > end:
            return ent["rates"], None
        lo = date.fromisoformat(ent["lo"]) if ent.get("lo") else None
        hi = date.fromisoformat(ent["hi"]) if ent.get("hi") else None
        gaps: list[tuple[date, date]] = []
        if lo is None or hi is None:
            gaps.append((start, end))
        else:
            if start < lo:
                gaps.append((start, lo - timedelta(days=1)))
            if end > hi:
                gaps.append((hi + timedelta(days=1), end))
            recent = today - timedelta(days=_RECENT_DAYS)
            stale = time.time() - float(ent.get("fetched_at") or 0) > _RECENT_TTL_S
            if end >= recent and hi >= recent and stale:
                gaps.append((max(lo, recent), min(hi, end)))
        err: Exception | None = None
        changed = False
        for g_start, g_end in gaps:
            try:
                fetched = _fetch_range(base, ccy, g_start, g_end)
            except FxUnavailable as exc:
                err = exc
                continue
            ent["rates"].update(fetched)
            lo = g_start if lo is None else min(lo, g_start)
            hi = g_end if hi is None else max(hi, g_end)
            ent["lo"], ent["hi"] = lo.isoformat(), hi.isoformat()
            ent["fetched_at"] = time.time()
            changed = True
        if changed:
            _save_cache()
        if err is not None:
            _log.warning("FX lookup failed for %s", ccy,
                         extra={"event": "fx.unavailable", "currency": ccy, "base": base})
        return ent["rates"], err


# ── Public API ───────────────────────────────────────────────────────────────

def get_rate(ccy: str, base: str = "EUR", on: date | None = None) -> FxQuote:
    """ECB reference rate for 1 ``ccy`` in ``base`` on ``on`` (default today),
    or on the closest earlier business day. Raises FxUnavailable when neither
    the API nor the cache has a rate within _LOOKBACK_DAYS."""
    ccy = (ccy or "").strip().upper()
    base = (base or "EUR").strip().upper()
    on = on or date.today()
    if isinstance(on, pd.Timestamp):
        on = on.date()
    if ccy == base:
        return FxQuote(1.0, on, "base")
    on = min(on, date.today())
    if on < ECB_FIRST_DATE:
        raise FxUnavailable(f"no ECB rates before {ECB_FIRST_DATE.isoformat()}")
    window_start = on - timedelta(days=_LOOKBACK_DAYS)
    rates, err = _ensure(base, ccy, window_start, on)
    candidates = [d for d in rates if window_start.isoformat() <= d <= on.isoformat()]
    if not candidates:
        raise FxUnavailable(str(err) if err else f"no {ccy} rate near {on.isoformat()}")
    best = max(candidates)
    return FxQuote(round(float(rates[best]), 6), date.fromisoformat(best), "ecb")


def rates_frame(currencies, start, end=None, base: str = "EUR") -> pd.DataFrame:
    """Daily "``base`` per 1 unit" rate per currency — DatetimeIndex (ECB
    fixing days) × ISO code. ``base`` itself and blanks are skipped; a
    currency with no data (unknown code, outage with nothing cached) is simply
    absent, and callers leave those amounts in native terms."""
    base = (base or "EUR").strip().upper()
    codes = sorted({(c or "").strip().upper() for c in currencies if (c or "").strip()})
    codes = [c for c in codes if c != base]
    if not codes:
        return pd.DataFrame()
    s = pd.Timestamp(start).date() if start is not None else date.today() - timedelta(days=1827)
    e = pd.Timestamp(end).date() if end is not None else date.today()
    cols: dict[str, pd.Series] = {}
    for code in codes:
        rates, _err = _ensure(base, code, s, e)
        if not rates:
            continue
        ser = pd.Series({pd.Timestamp(d): v for d, v in rates.items()}, dtype=float).sort_index()
        ser = ser[(ser.index >= pd.Timestamp(s) - pd.Timedelta(days=_LOOKBACK_DAYS))
                  & (ser.index <= pd.Timestamp(e))]
        if not ser.empty:
            cols[code] = ser
    return pd.DataFrame(cols).sort_index() if cols else pd.DataFrame()


def supported_currencies() -> list[str]:
    """ISO codes frankfurter can convert — the common European set first (in
    FALLBACK_CURRENCIES order), then the rest alphabetically. Falls back to
    FALLBACK_CURRENCIES when the API can't be reached."""
    global _currencies
    with _lock:
        if _currencies and time.time() - _currencies[0] < _CURRENCIES_TTL_S:
            return list(_currencies[1])
    try:
        body = _http_get("currencies")
        codes = {str(c).upper() for c in body}
    except FxUnavailable:
        return list(FALLBACK_CURRENCIES)
    ordered = [c for c in FALLBACK_CURRENCIES if c in codes or c == "EUR"]
    ordered += sorted(codes - set(ordered))
    with _lock:
        _currencies = (time.time(), ordered)
    return list(ordered)
