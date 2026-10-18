"""An offline stand-in for the parts of ``yfinance`` the app uses, answering
from the demo snapshot (demo-mode plan DM-5, the "offline switch").

In demo mode ``workspace.activate`` puts ``download`` and ``Ticker`` from here
onto the ``yfinance`` module, so every existing call site (the price feed,
price history, the value-history backfill, the add-ticker lookups) keeps
working without a network request and without a demo branch of its own.
Anything outside the snapshot answers empty, the way Yahoo answers for an
unknown symbol, and is logged as ``demo.offline_request`` so a missed path
shows up in the log instead of reaching the network.

Quote units match Yahoo's: London closes and dividends in pence ("GBp").
Closes are EODHD's adjusted closes (``auto_adjust=True`` is the default the
app relies on); there is no intraday data.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from uvalu import logkit
from uvalu.demo import universe

_log = logkit.get_logger("uvalu.demo")
_SNAP = None          # set by workspace.activate()
_ROWS: dict = {}      # ticker -> fundamentals row (for Ticker.info)

_PERIOD_DAYS = {"1d": 1, "5d": 7, "1mo": 31, "3mo": 92, "6mo": 183, "1y": 366, "2y": 731,
                "5y": 1827, "10y": 3653, "ytd": 366, "max": 36525}


def install(snap, rows: dict) -> None:
    global _SNAP, _ROWS
    _SNAP, _ROWS = snap, dict(rows)


def _miss(kind: str, what) -> None:
    _log.info("demo: no snapshot data for %s %s", kind, what,
              extra={"event": "demo.offline_request", "kind": kind, "what": str(what)})


def _frame(key: str) -> "pd.DataFrame | None":
    return _SNAP.eod.get(key) if _SNAP is not None else None


def download(tickers, start=None, end=None, period=None, interval="1d", **_kw) -> pd.DataFrame:
    """Daily bars as yfinance returns them: (field, ticker) MultiIndex columns."""
    if isinstance(tickers, str):
        tickers = tickers.replace(",", " ").split()
    tickers = list(tickers or [])
    if interval not in ("1d", None):
        return pd.DataFrame()          # no intraday data in the demo
    lo = pd.Timestamp(start) if start else None
    hi = pd.Timestamp(end) if end else None
    if lo is None and period:
        lo = pd.Timestamp(date.today() - timedelta(days=_PERIOD_DAYS.get(str(period), 366)))
    parts = {}
    for t in tickers:
        df = _frame(t)
        if df is None or df.empty:
            _miss("prices", t)
            continue
        sel = df
        if lo is not None:
            sel = sel[sel.index >= lo]
        if hi is not None:
            sel = sel[sel.index < hi]
        if sel.empty:
            continue
        parts[t] = pd.DataFrame({
            "Open": sel["open"], "High": sel["high"], "Low": sel["low"],
            "Close": sel["adjusted_close"], "Volume": sel["volume"],
        })
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts, axis=1)                     # (ticker, field)
    out = out.swaplevel(0, 1, axis=1).sort_index(axis=1)
    out.index.name = "Date"
    return out


def _quote_unit_amount(ticker: str, amount: float, currency: str, on) -> float:
    """A dividend in the ticker's quote unit, as Yahoo gives it (pence for
    London). EODHD states each payment's currency; one declared in another
    currency (Shell declares in USD) is converted at the ECB rate of its
    ex-date."""
    t = universe.BY_TICKER.get(ticker)
    quote = t.currency if t else "EUR"
    pence = ticker.endswith(".L")
    ccy = currency.strip().upper()
    if pence and ccy in ("GBX", "GBP."):
        return amount
    if ccy and ccy != quote and _SNAP is not None:
        r = _SNAP.rate(ccy, quote, on.date() if hasattr(on, "date") else on)
        amount = amount * r if r else float("nan")
    return amount * 100 if pence else amount


class _FastInfo(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None


class Ticker:
    """``yfinance.Ticker`` look-alike: info, fast_info and dividends from the
    snapshot; empty statements (the demo's fundamentals come from the reports)."""

    def __init__(self, symbol: str, *_a, **_kw):
        self.ticker = str(symbol or "").strip().upper()
        self._known = self.ticker in universe.SERIES

    def _closes(self) -> pd.Series:
        df = _frame(self.ticker)
        return df["close"].astype(float) if df is not None and not df.empty else pd.Series(dtype=float)

    @property
    def info(self) -> dict:
        if not self._known:
            _miss("info", self.ticker)
            return {}
        t = universe.BY_TICKER.get(self.ticker)
        closes = self._closes()
        last = float(closes.iloc[-1]) if not closes.empty else None
        row = _ROWS.get(self.ticker, {})
        unit = "GBp" if self.ticker.endswith(".L") else (t.currency if t else "EUR")
        return {
            "symbol": self.ticker, "shortName": t.name if t else self.ticker,
            "longName": t.name if t else self.ticker, "currency": unit,
            "currentPrice": last, "regularMarketPrice": last,
            "previousClose": float(closes.iloc[-2]) if len(closes) > 1 else None,
            "sector": row.get("sector"), "country": row.get("country"),
            "financialCurrency": row.get("financialCurrency"),
            "quoteType": "ETF" if t and t.benchmark else "EQUITY",
        }

    @property
    def fast_info(self) -> _FastInfo:
        closes = self._closes()
        if closes.empty:
            _miss("fast_info", self.ticker)
            return _FastInfo()
        df = _frame(self.ticker)
        vol = pd.to_numeric(df["volume"], errors="coerce").dropna().tail(63)
        last, prev = float(closes.iloc[-1]), (float(closes.iloc[-2]) if len(closes) > 1 else None)
        return _FastInfo(last_price=last, regular_market_price=last, previous_close=prev,
                         regular_market_previous_close=prev,
                         three_month_average_volume=float(vol.mean()) if not vol.empty else None,
                         currency="GBp" if self.ticker.endswith(".L") else None)

    @property
    def dividends(self) -> pd.Series:
        d = _SNAP.dividends.get(self.ticker) if _SNAP is not None else None
        if d is None or d.empty:
            return pd.Series(dtype=float, name="Dividends")
        return pd.Series([_quote_unit_amount(self.ticker, float(v), str(c or ""), ts)
                          for ts, v, c in zip(d.index, pd.to_numeric(d["value"], errors="coerce"),
                                              d["currency"])],
                         index=d.index, name="Dividends", dtype=float).dropna()

    # Statements: the demo's fundamentals come from the reports, not from here.
    @property
    def financials(self) -> pd.DataFrame:
        return pd.DataFrame()

    income_stmt = cashflow = balance_sheet = financials

    def history(self, period="1y", interval="1d", start=None, end=None, **_kw) -> pd.DataFrame:
        raw = download([self.ticker], start=start, end=end, period=period, interval=interval)
        if raw.empty:
            return raw
        out = raw.xs(self.ticker, axis=1, level=1)
        return out
