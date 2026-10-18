"""Read-only access to the demo snapshot in ``demo-data/`` (demo-mode plan DM-5).

Everything the demo app shows comes from here: the EODHD end-of-day bars and
dividends and the ECB rates written by tools/demo_refresh.py, the hand-entered
fundamentals (DM-4) and the sector reference (DM-D13). Missing pieces read as
empty, so the app still starts on a partial snapshot (spec N-03).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from uvalu.demo import fundamentals, store, universe


@dataclass
class Snapshot:
    root: Path
    eod: dict[str, pd.DataFrame] = field(default_factory=dict)        # key -> EOD frame, DatetimeIndex
    dividends: dict[str, pd.DataFrame] = field(default_factory=dict)  # ticker -> dividend frame
    fx: pd.DataFrame = field(default_factory=pd.DataFrame)            # EUR per 1 unit, DatetimeIndex
    fundamentals: dict[str, dict] = field(default_factory=dict)       # ticker -> document
    sector_ref: dict = field(default_factory=dict)
    refresh: dict = field(default_factory=dict)

    # ── prices ───────────────────────────────────────────────────────────────
    def closes(self, key: str, adjusted: bool = True) -> pd.Series:
        """Daily closes in the quote unit EODHD gives (pence for London)."""
        df = self.eod.get(key)
        if df is None or df.empty:
            return pd.Series(dtype=float)
        return df["adjusted_close" if adjusted else "close"].astype(float)

    def last_bar(self) -> "date | None":
        """The newest bar date across the demo tickers: the demo's 'as of'."""
        dates = [df.index.max().date() for k, df in self.eod.items()
                 if k in universe.TICKERS and df is not None and not df.empty]
        return max(dates) if dates else None

    # ── FX ───────────────────────────────────────────────────────────────────
    def eur_per(self, ccy: str, on: "date | None" = None) -> "float | None":
        """EUR per 1 unit of ``ccy`` on ``on`` (default: latest), ECB rates,
        carried forward over weekends and holidays."""
        ccy = (ccy or "").upper()
        if ccy == "EUR":
            return 1.0
        if self.fx.empty or ccy not in self.fx.columns:
            return None
        s = self.fx[ccy].dropna()
        if on is not None:
            s = s[s.index <= pd.Timestamp(on)]
        return float(s.iloc[-1]) if not s.empty else None

    def rate(self, frm: str, to: str, on: "date | None" = None) -> "float | None":
        """Units of ``to`` per 1 ``frm``."""
        a, b = self.eur_per(frm, on), self.eur_per(to, on)
        return a / b if a and b else None

    # ── sector reference ─────────────────────────────────────────────────────
    def sector_multiples(self) -> "tuple[dict, dict]":
        """({sector: P/E}, {sector: P/B}) from the reference file."""
        sectors = (self.sector_ref or {}).get("sectors") or {}
        return ({s: float(v["pe"]) for s, v in sectors.items() if v.get("pe")},
                {s: float(v["pb"]) for s, v in sectors.items() if v.get("pb")})


def _read_eod(path: Path) -> "pd.DataFrame | None":
    try:
        df = pd.read_csv(path, dtype={"date": str})
    except Exception:
        return None
    if df.empty or not set(store.EOD_COLUMNS) <= set(df.columns):
        return None
    df.index = pd.to_datetime(df.pop("date"))
    return df.sort_index()


def load(root: Path) -> Snapshot:
    root = Path(root)
    snap = Snapshot(root=root)
    for key in universe.SERIES:
        df = _read_eod(store.eod_path(root, key))
        if df is not None:
            snap.eod[key] = df
    for t in universe.TICKERS:
        p = store.div_path(root, t)
        if p.exists():
            try:
                d = pd.read_csv(p, dtype={"date": str, "payment_date": str, "currency": str})
                d.index = pd.to_datetime(d.pop("date"))
                snap.dividends[t] = d.sort_index()
            except Exception:
                pass
    fx_path = root / "fx.csv"
    if fx_path.exists():
        try:
            fx = pd.read_csv(fx_path, dtype={"date": str})
            fx.index = pd.to_datetime(fx.pop("date"))
            snap.fx = fx.sort_index()
        except Exception:
            pass
    for t in universe.STOCKS:
        p = fundamentals.path_for(root, t)
        if p.exists():
            try:
                snap.fundamentals[t] = fundamentals.load(p)
            except Exception:
                pass
    ref = root / "reference" / "sector_multiples.json"
    if ref.exists():
        try:
            snap.sector_ref = json.loads(ref.read_text(encoding="utf-8"))
        except Exception:
            pass
    snap.refresh = store.read_refresh(root)
    return snap
