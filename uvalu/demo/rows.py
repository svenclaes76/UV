"""Fundamentals rows for the demo, in the shape ``screener._fetch_one`` writes
(demo-mode plan DM-5, the "snapshot → app caches" step).

Built from the hand-entered reports (uvalu/demo/fundamentals.py) and the EODHD
prices instead of Yahoo's ``Ticker.info``. Conventions follow Yahoo's so the
engine needs no demo branch:

- per-share and statement figures stay in the **reporting currency**, with
  ``financialCurrency`` set; ``screener._convert_reporting_currency`` converts
  them to the quote currency, exactly as for a Yahoo row (V1);
- amounts in units (the reports are in millions), ratios as fractions,
  ``debtToEquity`` in percent;
- ``Price``, ``Market Cap``, ``dividendRate`` in the quote currency's major
  unit (pounds for London, EX-14);
- histories newest first.

Figures the reports don't give (EBITDA, five-year average yield, analyst
fields) stay None; the models that need them stay dark with their reason.
Beta is measured on the snapshot's daily returns against the app's benchmark
(EURO STOXX 50, DM-D16) over the snapshot's year, not Yahoo's five years.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from uvalu import exchanges
from uvalu.demo import universe
from uvalu.demo.fundamentals import value
from uvalu.demo.snapshot import Snapshot

BENCHMARK_KEY = "^STOXX50E"
_MILLION = 1e6
_MIN_BETA_DAYS = 120


def _units(v):
    return v * _MILLION if v is not None else None


def _ratio(a, b):
    return a / b if a is not None and b not in (None, 0) else None


def quote_divisor(ticker: str) -> int:
    ex = exchanges.for_ticker(ticker)
    return ex.price_divisor if ex else 1


def beta(snap: Snapshot, ticker: str) -> "float | None":
    s = snap.closes(ticker).pct_change()
    b = snap.closes(BENCHMARK_KEY).pct_change()
    df = pd.concat([s, b], axis=1, keys=["s", "b"]).dropna()
    if len(df) < _MIN_BETA_DAYS or df["b"].var() == 0:
        return None
    return float(df["s"].cov(df["b"]) / df["b"].var())


def average_volume(snap: Snapshot, ticker: str, days: int = 63) -> "float | None":
    df = snap.eod.get(ticker)
    if df is None or df.empty or "volume" not in df.columns:
        return None
    v = pd.to_numeric(df["volume"], errors="coerce").dropna().tail(days)
    return float(v.mean()) if not v.empty else None


def _history(doc: dict, field: str) -> "list[float] | None":
    vals = [value(y, field) for y in doc.get("years") or []]
    vals = [_units(v) for v in vals if v is not None]
    return vals or None


def _fcf_history(doc: dict) -> "list[float] | None":
    out = []
    for y in doc.get("years") or []:
        cfo, capex = value(y, "cfo"), value(y, "capex")
        if cfo is not None and capex is not None:
            out.append(_units(cfo - capex))
    return out or None


def _dmy(ts) -> "str | None":
    try:
        return pd.Timestamp(ts).strftime("%d/%m/%Y")
    except Exception:
        return None


def build_row(snap: Snapshot, ticker: str, now: "datetime | None" = None) -> "dict | None":
    """One fundamentals row, or None when the ticker has no price yet."""
    t = universe.BY_TICKER[ticker]
    raw = snap.closes(ticker, adjusted=False)
    if raw.empty:
        return None
    now = now or datetime.now(timezone.utc)
    div = quote_divisor(ticker)
    price = float(raw.iloc[-1]) / div                       # quote currency, major unit
    quote = t.currency
    ex = exchanges.for_ticker(ticker)
    row: dict = {
        "Name": t.name, "Ticker": ticker, "ISIN": "", "Price": price, "Currency": quote,
        "sector": t.sector, "country": ex.country if ex else None,
        "fetched_at": now.isoformat(),
        # The snapshot is the only source: never "stale" in the fetch sense.
        "next_fetch_at": (now + timedelta(days=3650)).isoformat(),
        "beta": beta(snap, ticker), "averageVolume": average_volume(snap, ticker),
        "enterpriseValue": None, "enterpriseToEbitda": None, "fiveYearAvgDividendYield": None,
        "trailingEps_derived": False,
    }
    doc = snap.fundamentals.get(ticker)
    if not doc or t.benchmark:
        row["financialCurrency"] = quote
        return row

    years = doc.get("years") or []
    y0 = years[0] if years else {}
    y1 = years[1] if len(years) > 1 else {}
    rep = doc.get("reporting_currency") or quote
    row["financialCurrency"] = rep
    v = lambda f, y=y0: value(y, f)   # noqa: E731

    shares = _units(v("shares_weighted"))
    eps, ni, equity = v("eps_basic"), v("net_income"), v("equity")
    bvps = equity / v("shares_weighted") if equity is not None and v("shares_weighted") else None
    fcf = (v("cfo") - v("capex")) if v("cfo") is not None and v("capex") is not None else None
    to_quote = 1.0 if rep == quote else snap.rate(rep, quote)

    # Dividends: the year's DPS from the report, in the quote currency.
    dps_q = None
    if v("dps") is not None:
        r = 1.0 if doc.get("dividend_currency") == quote else snap.rate(doc.get("dividend_currency"), quote)
        dps_q = v("dps") * r if r else None
    dps_rep = None
    if v("dps") is not None:
        r = 1.0 if doc.get("dividend_currency") == rep else snap.rate(doc.get("dividend_currency"), rep)
        dps_rep = v("dps") * r if r else None

    row.update({
        "Market Cap": price * shares if shares else None,
        "marketCap": price * shares if shares else None,
        "sharesOutstanding": shares,
        "trailingEps": eps,
        "bookValue": bvps,
        "ebit": _units(v("ebit")),
        "totalDebt": _units(v("total_debt")),
        "totalCash": _units(v("cash")),
        "freeCashflow": _units(fcf),
        "netIncome": _units(ni),
        "trailingPE": (price / (eps * to_quote)) if eps and eps > 0 and to_quote else None,
        "priceToBook": (price / (bvps * to_quote)) if bvps and bvps > 0 and to_quote else None,
        "debtToEquity": (_ratio(v("total_debt"), equity) * 100) if _ratio(v("total_debt"), equity) is not None else None,
        "currentRatio": _ratio(v("current_assets"), v("current_liabilities")),
        "interestCoverage": _ratio(v("ebit"), v("interest_expense")),
        "returnOnEquity": _ratio(ni, equity),
        "returnOnAssets": _ratio(ni, v("total_assets")),
        "operatingMargins": _ratio(v("ebit"), v("revenue")),
        "profitMargins": _ratio(ni, v("revenue")),
        "earningsGrowth": (_ratio(eps, value(y1, "eps_basic")) - 1) if _ratio(eps, value(y1, "eps_basic")) else None,
        "revenueGrowth": (_ratio(v("revenue"), value(y1, "revenue")) - 1) if _ratio(v("revenue"), value(y1, "revenue")) else None,
        "payoutRatio": _ratio(dps_rep, eps) if eps and eps > 0 else None,
        "dividendRate": dps_q,
        "trailingAnnualDividendRate": dps_q,
        "dividendYield": (dps_q / price) if dps_q and price else None,
        "fcfHistory": _fcf_history(doc),
        "revenueHistory": _history(doc, "revenue"),
        "ebitHistory": _history(doc, "ebit"),
        "netIncomeHistory": _history(doc, "net_income"),
        "cfoHistory": _history(doc, "cfo"),
        "retainedEarningsHistory": _history(doc, "retained_earnings"),
        "totalAssetsHistory": _history(doc, "total_assets"),
        "fundamentals_as_of": f"{y0.get('fiscal_year')}-{doc.get('fiscal_year_end', '12-31')}" if y0 else None,
    })
    # Derived like _fetch_one (in the reporting currency, before conversion).
    mcap_rep = (price / to_quote) * shares if to_quote and shares else None
    row["fcfYield"] = (row["freeCashflow"] / mcap_rep) if row["freeCashflow"] and mcap_rep else None
    row["cashPayoutRatio"] = ((dps_rep * shares) / row["freeCashflow"]
                              if dps_rep and shares and row["freeCashflow"] and row["freeCashflow"] > 0 else None)
    row["dividendCoverage"] = (eps / dps_rep) if eps and eps > 0 and dps_rep else None

    d = snap.dividends.get(ticker)
    if d is not None and not d.empty:
        row["exDividendDate"] = _dmy(d.index.max())
        pay = str(d["payment_date"].iloc[-1] or "")
        row["dividendDate"] = _dmy(pay) if len(pay) >= 10 else None
    else:
        row["exDividendDate"] = row["dividendDate"] = None
    return {k: (None if isinstance(x, float) and not math.isfinite(x) else x) for k, x in row.items()}


def build_all(snap: Snapshot, now: "datetime | None" = None) -> dict[str, dict]:
    rows = {}
    for t in universe.TICKERS:
        r = build_row(snap, t, now)
        if r is not None:
            rows[t] = r
    return rows


def sector_multiples(snap: Snapshot) -> "tuple[dict, dict]":
    """The reference file's sector multiples, clipped to the engine's own bands
    (screener.PE_MULTIPLE_BAND / PB_MULTIPLE_BAND), as its medians would be."""
    import screener
    pe, pb = snap.sector_multiples()
    lo, hi = screener.PE_MULTIPLE_BAND
    plo, phi = screener.PB_MULTIPLE_BAND
    return ({s: float(np.clip(x, lo, hi)) for s, x in pe.items()},
            {s: float(np.clip(x, plo, phi)) for s, x in pb.items()})
