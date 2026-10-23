"""The demo snapshot on disk (demo-mode plan DM-3, demo spec "Data pipeline").

Layout under ``demo-data/`` (generated files: kept out of ``master`` by
.gitignore, committed only on ``deploy/demo`` by the demo-data workflow):

- ``eod/<ticker>.csv``        date, open, high, low, close, adjusted_close, volume
- ``dividends/<ticker>.csv``  date, value, unadjusted_value, currency, payment_date
- ``fx.csv``                  date + one column per currency: EUR per 1 unit (ECB)
- ``refresh.json``            last run: time, last bar per ticker, calls, errors
- ``budget.json``             the call counter (uvalu/demo/budget.py)

Tickers are the stored (Yahoo-form) keys. Prices are in the quote unit EODHD
gives, so London stays in pence (GBX); the app divides on display (spec F-03).

The one rule for writes: **never lose history.** An empty or unusable
response leaves the file as it is; a fresh response replaces the bars it
covers and keeps every older bar.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

EOD_COLUMNS = ["date", "open", "high", "low", "close", "adjusted_close", "volume"]
DIV_COLUMNS = ["date", "value", "unadjusted_value", "currency", "payment_date"]


def _safe(ticker: str) -> str:
    return ticker.replace("/", "_").replace("\\", "_")


def eod_path(root: Path, ticker: str) -> Path:
    return Path(root) / "eod" / f"{_safe(ticker)}.csv"


def div_path(root: Path, ticker: str) -> Path:
    return Path(root) / "dividends" / f"{_safe(ticker)}.csv"


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    frame.to_csv(tmp, index=False)
    tmp.replace(path)


def _read_csv(path: Path, columns: list[str]) -> pd.DataFrame | None:
    if not Path(path).exists():
        return None
    try:
        df = pd.read_csv(path, dtype={"date": str})
    except Exception:
        return None
    if df.empty or not set(columns) <= set(df.columns):
        return None
    return df[columns]


# ── End-of-day prices ────────────────────────────────────────────────────────

def clean_eod(rows: object) -> pd.DataFrame:
    """EODHD bars → frame with EOD_COLUMNS, one row per date, sorted. Rows
    without a date or a positive close are dropped; a missing adjusted close
    falls back to the close."""
    out = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        d, close = str(r.get("date") or "")[:10], _num(r.get("close"))
        if len(d) != 10 or close is None or close <= 0:
            continue
        adj = _num(r.get("adjusted_close"))
        out.append({"date": d, "open": _num(r.get("open")), "high": _num(r.get("high")),
                    "low": _num(r.get("low")), "close": close,
                    "adjusted_close": adj if adj and adj > 0 else close,
                    "volume": _num(r.get("volume"))})
    df = pd.DataFrame(out, columns=EOD_COLUMNS)
    return df.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)


def read_eod(root: Path, ticker: str) -> pd.DataFrame | None:
    return _read_csv(eod_path(root, ticker), EOD_COLUMNS)


def merge_eod(existing: "pd.DataFrame | None", fresh: pd.DataFrame) -> pd.DataFrame:
    """Fresh bars win on the dates they cover; older bars are kept. Bars older
    than the fresh window get their adjusted close rescaled by the ratio at the
    first overlapping date, so the series stays continuous after a dividend."""
    if existing is None or existing.empty:
        return fresh.copy()
    if fresh.empty:
        return existing.copy()
    old = existing.copy()
    overlap = old.merge(fresh[["date", "adjusted_close"]], on="date", suffixes=("", "_new"))
    if not overlap.empty:
        first = overlap.sort_values("date").iloc[0]
        if first["adjusted_close"] > 0:
            factor = first["adjusted_close_new"] / first["adjusted_close"]
            older = old["date"] < fresh["date"].min()
            old.loc[older, "adjusted_close"] = old.loc[older, "adjusted_close"] * factor
    kept = old[~old["date"].isin(set(fresh["date"]))]
    return pd.concat([kept, fresh], ignore_index=True).sort_values("date").reset_index(drop=True)


def write_eod(root: Path, ticker: str, rows: object) -> "tuple[int, str | None]":
    """Merge EODHD bars into the ticker's file. Returns (new bar count, last
    bar date). Writes nothing when the response has no usable bar."""
    fresh = clean_eod(rows)
    existing = read_eod(root, ticker)
    if fresh.empty:
        last = existing["date"].iloc[-1] if existing is not None and not existing.empty else None
        return 0, last
    before = set(existing["date"]) if existing is not None else set()
    merged = merge_eod(existing, fresh)
    _write_csv(eod_path(root, ticker), merged)
    return len(set(merged["date"]) - before), merged["date"].iloc[-1]


# ── Dividends ────────────────────────────────────────────────────────────────

def clean_dividends(rows: object) -> pd.DataFrame:
    out = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        d, value = str(r.get("date") or "")[:10], _num(r.get("value"))
        if len(d) != 10 or value is None or value <= 0:
            continue
        out.append({"date": d, "value": value,
                    "unadjusted_value": _num(r.get("unadjustedValue")) or value,
                    "currency": str(r.get("currency") or ""),
                    "payment_date": str(r.get("paymentDate") or "")[:10]})
    df = pd.DataFrame(out, columns=DIV_COLUMNS)
    return df.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)


def write_dividends(root: Path, ticker: str, rows: object) -> int:
    """Merge dividends into the ticker's file; returns how many are new."""
    fresh = clean_dividends(rows)
    if fresh.empty:
        return 0
    existing = _read_csv(div_path(root, ticker), DIV_COLUMNS)
    before = set(existing["date"]) if existing is not None else set()
    if existing is not None:
        fresh = pd.concat([existing[~existing["date"].isin(set(fresh["date"]))], fresh],
                          ignore_index=True).sort_values("date").reset_index(drop=True)
    _write_csv(div_path(root, ticker), fresh)
    return len(set(fresh["date"]) - before)


# ── FX and run status ────────────────────────────────────────────────────────

def write_fx(root: Path, rates: pd.DataFrame) -> int:
    """Merge ECB rates (DatetimeIndex × currency, EUR per 1 unit) into fx.csv;
    returns the number of rows. Nothing is written for an empty frame."""
    if rates is None or rates.empty:
        return 0
    fresh = rates.copy()
    fresh.index = pd.DatetimeIndex(fresh.index).strftime("%Y-%m-%d")
    path = Path(root) / "fx.csv"
    if path.exists():
        try:
            old = pd.read_csv(path, dtype={"date": str}).set_index("date")
            fresh = fresh.combine_first(old)
        except Exception:
            pass
    fresh = fresh.sort_index()
    fresh.index.name = "date"
    _write_csv(path, fresh.reset_index())
    return len(fresh)


def read_refresh(root: Path) -> dict:
    try:
        return json.loads((Path(root) / "refresh.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_refresh(root: Path, status: dict) -> None:
    path = Path(root) / "refresh.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
