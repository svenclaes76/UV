"""
Stock valuation screener — implements the 6-stage algorithm from docs/stock_valuation_algorithm.md

Stage 1  — Data collection (yfinance, cached)
Stage 2  — Fair value: Graham Number · PE Fair Value · EPV · DDM (single + multi-stage) · Analyst
Stage 3  — Margin of Safety + Total Expected Return (TER) + Dividend Sustainability Flag
Stage 4  — Risk scoring: financial health · earnings quality · market risk · dividend risk · liquidity
Stage 5  — Composite Score = α×MoS + β×(100−Risk) + γ×Quality + δ×Momentum + ε×DividendScore
Stage 6  — Decision: Strong Buy (>70) | Monitor (40–70) | Avoid (<40) + hard veto rules

Caching: fundamentals stored in .cache/fundamentals.json, re-fetched after CACHE_TTL_HOURS.
"""

import contextlib
import io
import json
import logging
import math
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Python 3.14 on Windows: asyncio ProactorEventLoop logs ConnectionResetError noise when
# Yahoo Finance drops a connection mid-flight. Suppress at the logger level — less fragile
# than patching private CPython internals.
logging.getLogger("asyncio").setLevel(logging.CRITICAL)

import numpy as np
import pandas as pd
import yfinance as yf

import marketdata
from scoring import (  # re-exported for existing `from screener import …` call sites
    _clamp, _get_num, _finite,
    _financial_health_score, _earnings_quality_score, _dividend_sustainability_flag,
)

# ── Constants ─────────────────────────────────────────────────────────────────

RISK_FREE_RATE      = 0.03    # Euro area approximation
EQUITY_RISK_PREMIUM = 0.05
DEFAULT_TAX_RATE    = 0.25    # EPV fallback when `country` is missing or unmapped below
DEFAULT_BETA        = 1.0
# Blume (1971): a stock's next-period beta is well approximated by shrinking its
# trailing regression beta two-thirds of the way from the raw estimate toward the
# market beta of 1.0. yfinance's `beta` is a noisy, backward-looking single
# estimate, so both WACC and the market-risk score run it through this shrink
# (screener._adjust_beta) rather than trusting the raw number.
BLUME_WEIGHT        = 0.67
DDM_STABLE_GROWTH   = 0.02    # Terminal growth rate for multi-stage DDM
DDM_HIGH_GROWTH_YRS = 5       # Number of high-growth years in 2-stage DDM

# Statutory corporate tax rates by country, for EPV's EBIT×(1-t) step. Static headline
# rates (approx. 2024/2025), not a live feed — a known simplification like RISK_FREE_RATE
# and EQUITY_RISK_PREMIUM above. Keyed on yfinance's `country` field (full country name).
# Countries not listed here fall back to DEFAULT_TAX_RATE.
COUNTRY_TAX_RATES = {
    "United States":       0.21,
    "Belgium":             0.25,
    "Germany":             0.30,
    "France":              0.25,
    "Netherlands":         0.258,
    "United Kingdom":      0.25,
    "Switzerland":         0.149,
    "Ireland":             0.125,
    "Luxembourg":          0.2494,
    "Spain":               0.25,
    "Italy":               0.279,
    "Sweden":              0.206,
    "Norway":              0.22,
    "Denmark":             0.22,
    "Finland":             0.20,
    "Austria":             0.23,
    "Poland":              0.19,
    "Portugal":            0.21,
    "Greece":              0.22,
    "Canada":              0.265,
    "Japan":               0.2974,
    "China":               0.25,
    "South Korea":         0.24,
    "India":               0.2517,
    "Australia":           0.30,
    "New Zealand":         0.28,
    "Singapore":           0.17,
    "Hong Kong":           0.165,
    "Taiwan":              0.20,
    "Brazil":              0.34,
    "Mexico":              0.30,
    "Israel":              0.23,
    "South Africa":        0.27,
    "United Arab Emirates": 0.09,
    "Saudi Arabia":        0.20,
}

# Sell-side analyst target prices are well-documented to run optimistically biased on
# average — a flat haircut on the raw target discounts that bias before it feeds the
# fair-value composite. Fixed constant, not derived from live analyst-accuracy data.
ANALYST_TARGET_HAIRCUT = 0.10

# The analyst target also carries the lowest *base* weight of the six models and is
# scaled down further (_analyst_weight_factor) when the sell-side estimates disagree
# (wide high–low spread vs the mean) or are thin (few contributing analysts).
_ANALYST_SPREAD_TIGHT     = 0.20   # (high−low)/mean at/below which dispersion doesn't bite
_ANALYST_SPREAD_WIDE      = 0.80   # ...and at/above which the dispersion factor bottoms out
_ANALYST_DISPERSION_FLOOR = 0.30
_ANALYST_COVERAGE_FULL    = 8      # analyst count at/above which coverage doesn't bite
_ANALYST_COVERAGE_FLOOR   = 0.30

# Stage 2 fair-value model base weights — must sum to 1.00. Originally
# 0.18/0.18/0.19/0.20/0.20/0.25 (a stale sum of 1.20), rescaled to
# 0.150/0.150/0.158/0.167/0.167/0.208, then (WS-13) the analyst weight was cut
# from 0.208 to 0.130 — sell-side targets are optimism-biased and slow to react
# — and the freed ~0.078 handed to the two most fundamentals-anchored models,
# EPV and Graham. The DDM weights are the *base* rate for eligible payers;
# _fair_value_models scales them by the payout ramp (_ddm_weight_factor).
W_GRAHAM     = 0.178
W_PE         = 0.150
W_EPV        = 0.208
W_DDM_SINGLE = 0.167
W_DDM_MULTI  = 0.167
W_ANALYST    = 0.130

# PE Fair Value multiple. Instead of a flat 15x for every stock, the multiple is
# the median trailing P/E of the stock's own *sector* across the screened universe
# (screener._sector_pe_medians), winsorized to PE_MULTIPLE_BAND and given a bounded
# PEG tilt on earningsGrowth (clamp(1 + g, *PEG_TILT_BAND)). PE_MULTIPLE_FALLBACK —
# a round heuristic near the long-run market-average P/E, and the value used
# unconditionally before this — applies when the sector has fewer than
# MIN_SECTOR_SAMPLE priced peers, or when the frame carries no trailingPE/sector
# columns at all (direct _fair_value_models callers, pre-WS-10 caches).
PE_MULTIPLE_FALLBACK = 15.0
PE_MULTIPLE_BAND     = (6.0, 30.0)
PEG_TILT_BAND        = (0.7, 1.5)
MIN_SECTOR_SAMPLE    = 5

# Composite score weights — must sum to 1.0. Rebalanced away from the original
# 0.30/0.18/0.22/0.15/0.15: MoS no longer dominates outright (it co-leads with
# quality), and risk carries more weight, so a wide margin of safety can't by
# itself outvote weak fundamentals or a poor risk profile. The "value" screening
# style (settings._SCORE_STYLES) restores the MoS-led weighting for users who
# want it.
W_MOS      = 0.24   # α — margin of safety
W_RISK     = 0.22   # β — risk sub-score (already oriented so safer = higher)
W_QUALITY  = 0.24   # γ — quality
W_MOMENTUM = 0.15   # δ — momentum
W_DIVIDEND = 0.15   # ε — dividend score

# Each composite sub-score is a blend of its cross-sectional percentile rank
# (_pct_rank — a stock's standing *within the current universe*) and an absolute
# 0–100 band (_abs_band — the same value judged against a fixed bar). Pure
# percentile ranking inflates a mediocre stock in a weak universe and makes
# MoS_rank meaningless when every stock is overvalued; the absolute anchor keeps
# the score honest in that case. BLEND_PCT is the percentile weight (0 = purely
# absolute, 1 = purely relative, today's behaviour).
BLEND_PCT = 0.5

# Absolute-band breakpoints, (x, y) with x ascending; _abs_band interpolates
# linearly and clamps outside the range. y is always 0–100, higher = better.
_BAND_MOS   = [(0.0, 0.0), (0.10, 40.0), (0.25, 70.0), (0.50, 100.0)]  # margin of safety
_BAND_0_10  = [(0.0, 0.0), (10.0, 100.0)]                              # raw 0–10 score, ×10
_BAND_RISK  = [(0.0, 100.0), (10.0, 0.0)]                              # risk raw (higher = riskier)

# Decision thresholds
SCORE_STRONG_BUY = 70
SCORE_AVOID      = 40

# Composite score sub-ranks are cross-sectional percentiles (screener._pct_rank), so
# they measure a stock's standing *within the current screened universe*, not against
# any absolute bar. Below this many rows, percentile granularity gets coarse enough
# (e.g. 10 stocks = 10-point steps) that a handful of mediocre stocks can land in the
# top percentile purely for lack of competition — a "Strong Buy" needs more context at
# that point. Heuristic threshold, not statistically derived.
MIN_UNIVERSE_SIZE = 20

# Sectors where high leverage is a normal feature of the business model (banks and
# insurers hold customer deposits/float as liabilities, REITs debt-finance long-lived
# property, regulated utilities finance capex with debt) rather than a distress signal.
# The flat D/E hard veto can't tell healthy sector leverage from financial distress, so
# these sectors are exempt from it — other vetoes (negative FCF, at-risk dividend +
# low coverage) still apply.
LEVERAGE_EXEMPT_SECTORS = {"Financial Services", "Real Estate", "Utilities"}

MAX_WORKERS      = 4    # parallel yfinance requests
REQUEST_DELAY    = 0.5  # seconds between requests per worker
MAX_RETRIES      = 4    # retries on rate-limit (429), with exponential backoff
CACHE_TTL_HOURS  = 24   # base TTL; actual refresh is jittered ±4h per ticker
CACHE_TTL_JITTER = 4    # hours of random jitter added to each ticker's TTL


class _Fetcher:
    """All background-fetch state for one fundamentals cache file, shared
    across every Streamlit session in this process.

    Two instances exist: SCREENER_FETCH for the exchange universe (~1500
    tickers, refreshed slowly) and PORTFOLIO_FETCH for the user's held + sold
    positions (a few dozen, refreshed with priority). Each has its own daemon
    thread, cancel event, locks and .cache/*.json file, so a long screener
    refresh never blocks the portfolio's, and clearing one cache (see
    uvalu/data.py's _bust_cache) leaves the other intact.
    """

    def __init__(self, cache_file: Path):
        self.cache_file = cache_file
        self.live_cache: dict = {}                    # in-process mirror of the JSON file
        self.bg_thread: "threading.Thread | None" = None
        self.cancelled  = threading.Event()          # set by cancel_background_fetch()
        self.file_lock  = threading.Lock()           # guards all cache_file writes
        self.row_lock   = threading.Lock()           # guards live_cache dict + done counter
        self.state: dict = {"done": 0, "total": 0, "running": False}
        self.state_lock = threading.Lock()


SCREENER_FETCH  = _Fetcher(Path(__file__).parent / ".cache" / "fundamentals.json")
PORTFOLIO_FETCH = _Fetcher(Path(__file__).parent / ".cache" / "portfolio_fundamentals.json")

# ── Fields fetched from yfinance ──────────────────────────────────────────────

VALUATION_FIELDS = [
    "trailingEps",                  # Graham Number, PE fair value
    "bookValue",                    # Graham Number (BVPS)
    "trailingAnnualDividendRate",   # DDM single-stage
    "dividendRate",                 # Forward DPS (multi-stage DDM)
    "fiveYearAvgDividendYield",     # Yield vs historical average
    "targetMeanPrice",              # Analyst target
    "targetHighPrice",              # Analyst target — dispersion (high–low)/mean
    "targetLowPrice",               # Analyst target — dispersion (high–low)/mean
    "numberOfAnalystOpinions",      # Analyst target — coverage depth
    "ebit",                         # EPV
    "enterpriseValue",              # EPV: EV → per-share scaling
    "sharesOutstanding",            # Cash payout ratio
]

RISK_FIELDS = [
    "debtToEquity",       # Financial health
    "currentRatio",       # Financial health
    "interestCoverage",   # Financial health
    "freeCashflow",       # Earnings quality + cash payout ratio
    "netIncome",          # Earnings quality
    "beta",               # Market risk
    "averageVolume",      # Liquidity
    "payoutRatio",        # Dividend risk
]

QUALITY_FIELDS = [
    "returnOnEquity",    # ROE
    "returnOnAssets",    # ROA
    "operatingMargins",  # Operating margin
    "profitMargins",     # Net margin
    "currentRatio",      # Liquidity
    "freeCashflow",      # FCF (for yield)
]

MOMENTUM_FIELDS = [
    "earningsGrowth",     # EPS trend / proxy for DGR
    "revenueGrowth",      # Revenue CAGR proxy
    "recommendationMean", # Analyst revisions (1=strong buy, 5=strong sell)
]

ALL_EXTRA_FIELDS = list({
    *VALUATION_FIELDS, *RISK_FIELDS, *QUALITY_FIELDS, *MOMENTUM_FIELDS
})

# ── Cache helpers ─────────────────────────────────────────────────────────────

def _load_cache(fetcher: "_Fetcher | None" = None) -> dict:
    f = fetcher or SCREENER_FETCH
    if f.cache_file.exists():
        try:
            return json.loads(f.cache_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_cache(cache: dict, fetcher: "_Fetcher | None" = None) -> None:
    f = fetcher or SCREENER_FETCH
    f.cache_file.parent.mkdir(parents=True, exist_ok=True)
    f.cache_file.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def load_fundamentals_cache() -> dict:
    """Merged fundamentals from both fetch lanes — the screener's exchange
    universe plus the portfolio's own lane. Consumers that need fundamentals
    for arbitrary held tickers (the dashboard / risk risk-card, which feed
    risk.assess_portfolio) must use this rather than _load_cache(), which is
    the screener file alone and omits holdings on disabled exchanges. The
    portfolio lane wins on any ticker present in both.
    """
    _warm_live_cache(SCREENER_FETCH)
    _warm_live_cache(PORTFOLIO_FETCH)
    return {**SCREENER_FETCH.live_cache, **PORTFOLIO_FETCH.live_cache}


def _is_fresh(entry: dict) -> bool:
    try:
        # Prefer explicit next_fetch_at (set with jitter); fall back to legacy age check
        if "next_fetch_at" in entry:
            return datetime.now(timezone.utc) < datetime.fromisoformat(entry["next_fetch_at"])
        fetched_at = datetime.fromisoformat(entry["fetched_at"])
        age_hours  = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 3600
        return age_hours < CACHE_TTL_HOURS
    except Exception:
        return False


def _next_fetch_at() -> str:
    """Random refresh time: base TTL ± jitter, so fetches spread across the day."""
    jitter_hours = random.uniform(-CACHE_TTL_JITTER, CACHE_TTL_JITTER)
    delta_hours  = CACHE_TTL_HOURS + jitter_hours
    return (datetime.now(timezone.utc) + timedelta(hours=delta_hours)).isoformat()


# ── Data fetching ─────────────────────────────────────────────────────────────

def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _fcf_history(tkr: "yf.Ticker") -> list[float] | None:
    """Annual Free Cash Flow, most recent fiscal year first, from the cash flow
    statement (up to ~4-5 years as yfinance exposes it). Returns None on fetch
    failure or if the statement doesn't expose the row (e.g. some ADRs, recent
    IPOs) — callers fall back to the single most-recent-period FCF in that case.
    Isolated in its own try/except so a failure here doesn't trigger the whole-
    ticker retry/backoff in _fetch_and_store.
    """
    try:
        cf = tkr.cashflow
        if cf is None or cf.empty or "Free Cash Flow" not in cf.index:
            return None
        vals = [_safe_float(v) for v in cf.loc["Free Cash Flow"].tolist()]
        vals = [v for v in vals if v is not None and not math.isnan(v)]
        return vals or None
    except Exception:
        return None


# Income-statement / balance-sheet lines we keep a multi-year history for, each
# stored newest-first as a plain list on the cached row (yfinance exposes ~4
# fiscal years). Every tuple is a fallback chain — yfinance's row labels vary by
# ticker/filing. Feeds the trend hard-vetoes (revenue decline, EBIT collapse,
# retained-earnings erosion), the accrual term in earnings quality, and a
# normalised EPV. Same nan-not-None gotcha as _fcf_history: ragged statements are
# padded with NaN, so trailing NaN years are dropped, not kept.
_STATEMENT_HISTORY_KEYS = (
    "revenueHistory", "ebitHistory", "netIncomeHistory",
    "cfoHistory", "retainedEarningsHistory", "totalAssetsHistory",
)


def _statement_row(stmt, names: tuple[str, ...]) -> list[float] | None:
    """First matching row of `stmt` (a yfinance statement DataFrame) as a
    newest-first float list with NaN/None entries dropped; None if `stmt` is
    empty, exposes none of `names`, or can't be read. Self-contained try/except
    so one malformed row (e.g. a duplicated index label) degrades to None for
    just that key rather than sinking the whole _statement_history dict."""
    try:
        if stmt is None or getattr(stmt, "empty", True):
            return None
        for name in names:
            if name not in stmt.index:
                continue
            series = stmt.loc[name]
            if isinstance(series, pd.DataFrame):        # duplicated index label
                series = series.iloc[0]
            vals = [_safe_float(v) for v in series.tolist()]
            vals = [v for v in vals if v is not None and not math.isnan(v)]
            return vals or None
        return None
    except Exception:
        return None


def _statement_history(tkr: "yf.Ticker") -> dict:
    """Multi-year annual history for a handful of income-statement, balance-sheet
    and cash-flow lines, most recent fiscal year first.

    Returns a dict keyed by _STATEMENT_HISTORY_KEYS, every value None on fetch
    failure or when the statement doesn't expose the row (some ADRs, recent
    IPOs) — callers fall back to the point-in-time field. Isolated in its own
    try/except like _fcf_history so a failure here doesn't trigger the whole-
    ticker retry/backoff in _fetch_and_store. `.income_stmt` / `.balance_sheet`
    / `.cashflow` are memoised on the Ticker object, so re-reading `.cashflow`
    here (also used by _fcf_history) costs no extra network call.
    """
    empty = dict.fromkeys(_STATEMENT_HISTORY_KEYS)
    try:
        income  = tkr.income_stmt
        balance = tkr.balance_sheet
        cash    = tkr.cashflow
        return {
            "revenueHistory":          _statement_row(income,  ("Total Revenue",)),
            "ebitHistory":             _statement_row(income,  ("EBIT", "Operating Income")),
            "netIncomeHistory":        _statement_row(income,  ("Net Income", "Net Income Common Stockholders")),
            "cfoHistory":              _statement_row(cash,    ("Operating Cash Flow", "Total Cash From Operating Activities")),
            "retainedEarningsHistory": _statement_row(balance, ("Retained Earnings",)),
            "totalAssetsHistory":      _statement_row(balance, ("Total Assets",)),
        }
    except Exception:
        return empty


# Number of complete calendar years of dividend history to score DGR / streaks
# over. yfinance's dividend series usually reaches much further back, but a ~6y
# window keeps "growth" and "cut" judgements about the current regime rather
# than dragging in a decade-old policy change.
_DIV_WINDOW_YEARS  = 6
_DIV_MIN_YEARS     = 2       # need at least this many complete years for a true DGR
_DIV_CUT_TOLERANCE = 0.99    # a year counts as a cut only below 99% of the prior year


def _dividend_stats(ticker: str, *, now_year: int | None = None) -> dict:
    """Annual-DPS statistics from the full payment history (marketdata.dividends).

    Returns keys, all None/0 for a non-payer or on fetch failure:
      true_dgr                — CAGR of annual DPS across the complete years in
                                the window (>= _DIV_MIN_YEARS, first year > 0)
      dividend_growth_streak  — trailing consecutive complete years of
                                non-decreasing annual DPS
      dividend_payment_years  — count of complete years with a payment in-window
      dividend_last_cut_year  — most recent complete year whose annual DPS fell
                                below _DIV_CUT_TOLERANCE x the prior year, else None
    Isolated try/except like _fcf_history so a failure here never trips the
    whole-ticker retry/backoff.
    """
    empty = {"true_dgr": None, "dividend_growth_streak": 0,
             "dividend_payment_years": 0, "dividend_last_cut_year": None}
    try:
        divs = marketdata.dividends(ticker)
        if divs is None or divs.empty:
            return empty

        this_year = now_year if now_year is not None else datetime.now(timezone.utc).year
        annual = divs.groupby(divs.index.year).sum()
        annual = annual[annual.index < this_year]          # drop the incomplete current year
        annual = annual.iloc[-_DIV_WINDOW_YEARS:]
        annual = annual[annual > 0]
        if annual.empty:
            return empty

        years = list(annual.index)
        vals  = [float(v) for v in annual.to_numpy()]

        true_dgr = None
        if len(vals) >= _DIV_MIN_YEARS and vals[0] > 0:
            true_dgr = (vals[-1] / vals[0]) ** (1.0 / (len(vals) - 1)) - 1.0

        streak = 0
        for i in range(len(vals) - 1, 0, -1):
            if vals[i] >= vals[i - 1]:
                streak += 1
            else:
                break

        last_cut_year = None
        for i in range(1, len(vals)):
            if vals[i] < vals[i - 1] * _DIV_CUT_TOLERANCE:
                last_cut_year = int(years[i])

        return {
            "true_dgr": round(true_dgr, 4) if true_dgr is not None else None,
            "dividend_growth_streak": streak,
            "dividend_payment_years": len(vals),
            "dividend_last_cut_year": last_cut_year,
        }
    except Exception:
        return empty


def _fetch_one(ticker: str, stock: dict) -> dict:
    tkr   = yf.Ticker(ticker)
    info  = tkr.info
    mcap  = info.get("marketCap")
    price = info.get("currentPrice") or info.get("regularMarketPrice")

    def _unix_to_date(ts) -> str | None:
        """Convert a Unix timestamp (int) from yfinance to an ISO date string."""
        try:
            return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%d/%m/%Y") if ts else None
        except Exception:
            return None

    row = {
        "Name":       info.get("shortName") or stock["name"],
        "Ticker":     ticker,
        "ISIN":       stock["isin"],
        "Price":      _safe_float(price),
        "Currency":   info.get("currency", "EUR"),
        "Market Cap": _safe_float(mcap),
        "sector":              info.get("sector") or None,
        "country":             info.get("country") or None,
        "exDividendDate":      _unix_to_date(info.get("exDividendDate")),
        "dividendDate":        _unix_to_date(info.get("dividendDate")),
        "fetched_at":    datetime.now(timezone.utc).isoformat(),
        "next_fetch_at": _next_fetch_at(),
    }

    # Display multiples — sanity-bounded
    for key in ("trailingPE", "priceToBook", "enterpriseToEbitda"):
        v = _safe_float(info.get(key))
        row[key] = v if (v is not None and 0 < v < 10_000) else None

    # Dividend yield — Yahoo's own "dividendYield" field mixes unit conventions
    # across tickers/exchanges (plain percent like 6.65 for most primary US
    # listings, but old-style decimal fraction like 0.006 for some secondary
    # listings), so no single scale heuristic can recover the right number for
    # every ticker. Compute it ourselves instead from two unambiguous absolute
    # values we already have — dividend rate and price — which sidesteps the
    # convention entirely and is also more precise (uses live price, not a
    # possibly-stale precomputed ratio).
    div_rate_raw = _safe_float(info.get("dividendRate") or info.get("trailingAnnualDividendRate"))
    px = _safe_float(price)
    if div_rate_raw is not None and px and px > 0:
        row["dividendYield"] = div_rate_raw / px
    else:
        dy = _safe_float(info.get("dividendYield"))
        row["dividendYield"] = (dy / 100) if (dy is not None and dy > 1.0) else dy

    # 5yr avg dividend yield — no absolute-value fallback exists (no 5yr avg
    # price/rate available), so this one is stuck with Yahoo's raw field and
    # the same magnitude heuristic; known to be unreliable for sub-1%-yield
    # stocks on affected tickers.
    avg_dy = _safe_float(info.get("fiveYearAvgDividendYield"))
    row["fiveYearAvgDividendYield"] = (avg_dy / 100) if (avg_dy is not None and avg_dy > 1.0) else avg_dy

    # Debt/Equity — reject extreme outliers
    de = _safe_float(info.get("debtToEquity"))
    row["debtToEquity"] = de if (de is not None and de < 1000) else None

    # All remaining extra fields — stored raw
    for key in ALL_EXTRA_FIELDS:
        if key not in row:   # don't overwrite already-processed fields
            row[key] = _safe_float(info.get(key))

    # Multi-year FCF history for the hard veto's "3+ consecutive negative years"
    # check; falls back to the single most-recent-period check when unavailable.
    row["fcfHistory"] = _fcf_history(tkr)

    # Multi-year revenue / EBIT / net income / CFO / retained earnings / total
    # assets — feeds the trend hard-vetoes, the accrual term in earnings quality,
    # and a normalised EPV. Every key None when the statements can't be fetched.
    row.update(_statement_history(tkr))

    # Multi-year DPS history → true dividend growth rate, growth streak, and a
    # past-cut year. `true_dgr` supersedes the earningsGrowth DGR proxy in TER
    # and the dividend scores; the rest feed the risk engine's income-stability
    # and sustainability checks.
    row.update(_dividend_stats(ticker))

    # Derived: FCF yield
    fcf  = row.get("freeCashflow")
    row["fcfYield"] = (fcf / mcap) if (fcf and mcap and mcap > 0) else None

    # Derived: cash payout ratio = (DPS × shares) / FCF
    dps    = row.get("trailingAnnualDividendRate") or row.get("dividendRate")
    shares = row.get("sharesOutstanding")
    if dps and dps > 0 and shares and shares > 0 and fcf and fcf > 0:
        row["cashPayoutRatio"] = (dps * shares) / fcf
    else:
        row["cashPayoutRatio"] = None

    # Derived: dividend coverage ratio = EPS / DPS
    eps = row.get("trailingEps")
    if eps and eps > 0 and dps and dps > 0:
        row["dividendCoverage"] = eps / dps
    else:
        row["dividendCoverage"] = None

    return row


# ── Background fetch (per-fetcher, shared across all Streamlit sessions) ──────

def get_fetch_progress(fetcher: "_Fetcher | None" = None) -> dict:
    """Thread-safe snapshot of background fetch progress."""
    f = fetcher or SCREENER_FETCH
    with f.state_lock:
        return f.state.copy()


def cancel_background_fetch(fetcher: "_Fetcher | None" = None) -> None:
    """Signal any running background fetch to stop and mark it as not running."""
    f = fetcher or SCREENER_FETCH
    f.cancelled.set()
    with f.state_lock:
        f.state["running"] = False


def clear_live_cache(fetcher: "_Fetcher | None" = None) -> None:
    """Clear the in-process cache (call before wiping the cache file)."""
    f = fetcher or SCREENER_FETCH
    f.live_cache.clear()


def _df_from_cache(stocks: list[dict], cache: dict) -> pd.DataFrame:
    rows = [cache[s["ticker"]] for s in stocks if s["ticker"] in cache]
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["Ticker"])


def _run_fetch(stale: list[dict], cache: dict, fetcher: "_Fetcher | None" = None) -> None:
    """Blocking fetch of stale tickers; updates the fetcher's cache file
    incrementally. `stale` is processed in the order given — callers put
    priority tickers first (see fetch_fundamentals_nowait)."""
    f = fetcher or SCREENER_FETCH
    done = 0

    def _refresh_crumb():
        try:
            yf.Ticker("AAPL").fast_info
        except Exception:
            pass

    def _fetch_and_store(stock):
        nonlocal done
        if f.cancelled.is_set():
            return
        ticker = stock["ticker"]
        row = None
        for attempt in range(MAX_RETRIES + 1):
            if f.cancelled.is_set():
                return
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    row = _fetch_one(ticker, stock)
                break
            except Exception as e:
                msg = str(e)
                is_not_found  = "404" in msg or "Not Found" in msg or "Quote not found" in msg
                is_crumb      = "401" in msg or "Invalid Crumb" in msg or "Unauthorized" in msg
                is_rate_limit = ("429" in msg or "Too Many Requests" in msg or "Rate limited" in msg
                                 or "ConnectionResetError" in msg or "10054" in msg or "RemoteDisconnected" in msg)
                if is_not_found:
                    break
                if is_crumb:
                    _refresh_crumb()
                    time.sleep(3)
                    if attempt < MAX_RETRIES:
                        continue
                elif is_rate_limit:
                    wait = 2 ** attempt * 5
                    if attempt < MAX_RETRIES:
                        time.sleep(wait)
                        continue
                print(f"\n  Warning: could not fetch {ticker}: {e}")
                break
        if f.cancelled.is_set():
            return
        if row is None:
            row = {"Name": stock["name"], "Ticker": ticker,
                   "ISIN": stock["isin"], "fetched_at": ""}
        time.sleep(REQUEST_DELAY)
        # Narrow critical section: only dict write + counter; save check happens outside
        with f.row_lock:
            cache[ticker] = row
            done += 1
            current = done
        with f.state_lock:
            f.state["done"] = current
        if not f.cancelled.is_set() and (current % 25 == 0 or current == len(stale)):
            with f.file_lock:
                _save_cache(cache, f)
        print(f"  Fetching [{current}/{len(stale)}] {ticker}          ", end="\r")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        list(executor.map(_fetch_and_store, stale))

    if not f.cancelled.is_set():
        with f.file_lock:
            _save_cache(cache, f)
    print()
    with f.state_lock:
        f.state["running"] = False


def _warm_live_cache(fetcher: "_Fetcher | None" = None) -> None:
    """Populate the fetcher's live cache from disk on first call (cold start only)."""
    f = fetcher or SCREENER_FETCH
    if not f.live_cache:
        f.live_cache.update(_load_cache(f))


def fetch_fundamentals_nowait(stocks: list[dict], fetcher: "_Fetcher | None" = None,
                              priority=()) -> pd.DataFrame:
    """
    Return cached data immediately.
    Stale tickers are refreshed in a background thread — both the JSON file and
    the fetcher's live cache are updated incrementally, so UI reruns pick up new
    data without a full disk read on every rerun.

    `priority` is an iterable of stock dicts (held positions, watchlist) whose
    tickers are fetched *before* the rest: they keep their given order at the
    front of the queue while the remaining stale tickers are shuffled behind
    them, so a portfolio name is never buried behind the exchange universe.
    """
    f = fetcher or SCREENER_FETCH
    _warm_live_cache(f)

    _priority_tickers = {s["ticker"] for s in priority}
    stale = [s for s in stocks if not _is_fresh(f.live_cache.get(s["ticker"], {}))]
    fresh_count = len(stocks) - len(stale)

    if stale and (not f.bg_thread or not f.bg_thread.is_alive()):
        print(f"  {fresh_count} cached  |  {len(stale)} stale — starting background fetch")
        f.cancelled.clear()
        with f.state_lock:
            f.state.update({"done": 0, "total": len(stale), "running": True})
        _prio = [s for s in stale if s["ticker"] in _priority_tickers]
        _rest = [s for s in stale if s["ticker"] not in _priority_tickers]
        random.shuffle(_rest)
        f.bg_thread = threading.Thread(
            target=_run_fetch, args=(_prio + _rest, f.live_cache, f), daemon=True)
        f.bg_thread.start()
    elif not stale:
        print(f"  All {fresh_count} tickers served from cache (max age {CACHE_TTL_HOURS}h)")

    return _df_from_cache(stocks, f.live_cache)


# ── Stage 2: Fair value estimation ───────────────────────────────────────────

def _adjust_beta(beta) -> float | None:
    """Shrink a raw beta toward the market beta of 1.0 by the Blume weight
    (0.67·raw + 0.33·1.0). Returns None when `beta` is missing, NaN, or outside
    the plausible [0.1, 5.0] band (rejected, not clamped to the edge) — callers
    substitute DEFAULT_BETA (WACC) or a neutral score (market risk)."""
    try:
        b = float(beta)
    except (TypeError, ValueError):
        return None
    if math.isnan(b) or not (0.1 <= b <= 5.0):
        return None
    return BLUME_WEIGHT * b + (1.0 - BLUME_WEIGHT) * DEFAULT_BETA


def _approx_wacc(beta) -> float:
    b = _adjust_beta(beta)
    return RISK_FREE_RATE + (b if b is not None else DEFAULT_BETA) * EQUITY_RISK_PREMIUM


def _ddm_single(div_rate, wacc, g) -> float | None:
    """Gordon growth single-stage DDM."""
    if not div_rate or div_rate <= 0:
        return None
    g = max(0.0, min(0.05, g if g is not None else 0.02))
    if wacc <= g:
        return None
    d1  = div_rate * (1 + g)
    val = d1 / (wacc - g)
    return val if 0 < val < 1e6 else None


def _ddm_multistage(div_rate, wacc, g_high, g_stable=DDM_STABLE_GROWTH,
                    years=DDM_HIGH_GROWTH_YRS) -> float | None:
    """2-stage DDM: explicit high-growth phase + Gordon terminal value."""
    if not div_rate or div_rate <= 0:
        return None
    if wacc <= g_stable:
        return None
    g_high = max(0.0, min(0.15, g_high if g_high is not None else 0.05))
    pv  = 0.0
    dps = div_rate
    for t in range(1, years + 1):
        dps = dps * (1 + g_high)
        pv += dps / (1 + wacc) ** t
    terminal_dps = dps * (1 + g_stable)
    tv  = terminal_dps / (wacc - g_stable)
    pv += tv / (1 + wacc) ** years
    return pv if 0 < pv < 1e6 else None


# DDM weight ramps continuously with the payout ratio instead of switching the
# whole ~0.33 DDM block in or out at hard 5%/90% edges — an 89% vs 91% payer
# shouldn't see the fair value lurch. Knots: zero below 5% and above 95%, full
# weight across the 30–70% "comfortable" band, linear on each shoulder between.
_DDM_PAYOUT_KNOTS = (0.05, 0.30, 0.70, 0.95)


def _ddm_weight_factor(div_rate, payout) -> float:
    """Multiplier in [0, 1] applied to BOTH DDM base weights (W_DDM_SINGLE /
    W_DDM_MULTI). 0 for a non-payer or a payout outside _DDM_PAYOUT_KNOTS[0]..[3];
    1.0 across the [1]..[2] band; a linear ramp on each shoulder. Continuous at
    every knot, so there's no cliff anywhere in the payout range."""
    if not div_rate or div_rate <= 0 or payout is None or pd.isna(payout):
        return 0.0
    lo0, lo1, hi1, hi0 = _DDM_PAYOUT_KNOTS
    if payout <= lo0 or payout >= hi0:
        return 0.0
    if payout < lo1:
        return (payout - lo0) / (lo1 - lo0)
    if payout <= hi1:
        return 1.0
    return (hi0 - payout) / (hi0 - hi1)


def _analyst_weight_factor(row: pd.Series) -> float:
    """Multiplier in [~0.09, 1.0] applied to W_ANALYST. Scales the analyst
    target's pull down when the sell-side estimates disagree (wide high–low
    spread relative to the mean) or are thinly covered (few contributing
    analysts). 1.0 when neither signal is available — an absent field never
    penalizes, it just doesn't discount.
    """
    hi, lo, mean = (_get_num(row, "targetHighPrice"),
                    _get_num(row, "targetLowPrice"),
                    _get_num(row, "targetMeanPrice"))
    dispersion = 1.0
    if None not in (hi, lo, mean) and mean > 0 and hi >= lo:
        spread = (hi - lo) / mean
        if spread > _ANALYST_SPREAD_TIGHT:
            t = ((spread - _ANALYST_SPREAD_TIGHT)
                 / (_ANALYST_SPREAD_WIDE - _ANALYST_SPREAD_TIGHT))
            dispersion = _clamp(1.0 - t * (1.0 - _ANALYST_DISPERSION_FLOOR),
                                _ANALYST_DISPERSION_FLOOR, 1.0)

    n = _get_num(row, "numberOfAnalystOpinions")
    coverage = (_clamp(n / _ANALYST_COVERAGE_FULL, _ANALYST_COVERAGE_FLOOR, 1.0)
                if n else 1.0)

    return dispersion * coverage


def _sector_pe_medians(df: pd.DataFrame) -> dict:
    """{sector: winsorized median trailing P/E} across `df`, for the PE fair-value
    model. Only sectors with at least MIN_SECTOR_SAMPLE positive P/E readings get
    an entry — callers fall back to PE_MULTIPLE_FALLBACK for every other sector.
    Returns {} when the frame carries no `trailingPE`/`sector` columns at all
    (e.g. a hand-built test frame), so `_fair_value_models` stays usable stand-alone.
    """
    if "trailingPE" not in df.columns or "sector" not in df.columns:
        return {}
    pe    = pd.to_numeric(df["trailingPE"], errors="coerce")
    valid = pd.DataFrame({"sector": df["sector"], "pe": pe})
    valid = valid[(valid["pe"] > 0) & (valid["pe"] < 10_000) & valid["sector"].notna()]
    if valid.empty:
        return {}
    lo, hi = PE_MULTIPLE_BAND
    return {
        sector: float(np.clip(grp["pe"].median(), lo, hi))
        for sector, grp in valid.groupby("sector")
        if len(grp) >= MIN_SECTOR_SAMPLE
    }


def _normalised_ebit(row: pd.Series):
    """Mean EBIT across the available multi-year window (`ebitHistory`, newest
    first) when at least 3 finite years exist — EPV capitalises a
    through-the-cycle *earnings power*, so a single peak or trough year
    shouldn't set the whole valuation. Falls back to the point-in-time `ebit`
    otherwise (recent IPOs, tickers whose statement fetch failed)."""
    hist = row.get("ebitHistory")
    vals = ([f for f in (_finite(v) for v in hist) if f is not None]
            if isinstance(hist, list) else [])
    if len(vals) >= 3:
        return sum(vals) / len(vals)
    return _get_num(row, "ebit")


def _fair_value_models(row: pd.Series, sector_pe: "dict | None" = None) -> dict:
    price    = row.get("Price")
    eps      = row.get("trailingEps")
    bvps     = row.get("bookValue")
    div_rate = row.get("trailingAnnualDividendRate") or row.get("dividendRate")
    payout   = row.get("payoutRatio")
    analyst  = row.get("targetMeanPrice")
    ebit     = _normalised_ebit(row)   # mean of ebitHistory (≥3yr) else point-in-time
    ev       = row.get("enterpriseValue")
    beta     = row.get("beta")
    eg       = row.get("earningsGrowth")
    country  = row.get("country")
    sector   = row.get("sector")
    shares   = row.get("sharesOutstanding")
    tax_rate = COUNTRY_TAX_RATES.get(country, DEFAULT_TAX_RATE)

    wacc = _approx_wacc(beta)

    # Graham Number
    gn = None
    if eps and bvps and eps > 0 and bvps > 0:
        gn = (22.5 * eps * bvps) ** 0.5

    # PE Fair Value: sector-median trailing P/E (winsorized to PE_MULTIPLE_BAND)
    # with a bounded PEG tilt on earningsGrowth; PE_MULTIPLE_FALLBACK when the
    # sector has too few priced peers or no sector P/E data was supplied.
    pe_multiple = (sector_pe or {}).get(sector, PE_MULTIPLE_FALLBACK)
    if pd.notna(eg):
        pe_multiple *= float(np.clip(1.0 + eg, *PEG_TILT_BAND))
    pe_fv = (eps * pe_multiple) if (eps and eps > 0) else None

    # Earnings Power Value (EPV_EV = EBIT×(1-t)/WACC). EBIT is the multi-year mean
    # (_normalised_ebit) when history allows, so a peak/trough year doesn't set the
    # valuation; t is the country's statutory rate (COUNTRY_TAX_RATES), else DEFAULT_TAX_RATE.
    epv = None
    if ebit and ebit > 0 and ev and ev > 0 and price and price > 0:
        epv_ev = ebit * (1 - tax_rate) / wacc
        if shares and shares > 0:
            # Exact: subtract net debt (EV − market cap) from EPV_EV, then divide
            # by shares — avoids assuming EPV_EV's implied capital structure mirrors
            # the actual EV/market-cap ratio, which the EV-ratio shortcut below does.
            net_debt = ev - (price * shares)
            epv = (epv_ev - net_debt) / shares
        else:
            # Fallback when shares outstanding is unavailable: EV-ratio approximation.
            epv = price * (epv_ev / ev)

    # DDM weight ramps with the payout ratio (_ddm_weight_factor) rather than a
    # hard 5–90% in/out gate — full base weight in the 30–70% band, tapering to 0
    # by 5% / 95%, so an 89%→91% payer shifts by a sliver, not the whole block.
    ddm_factor  = _ddm_weight_factor(div_rate, payout)
    ddm_usable  = ddm_factor > 0
    w_ddm1 = W_DDM_SINGLE * ddm_factor
    w_ddm2 = W_DDM_MULTI  * ddm_factor

    ddm1 = _ddm_single(div_rate, wacc, eg)     if ddm_usable else None
    ddm2 = _ddm_multistage(div_rate, wacc, eg) if ddm_usable else None

    # Discount the raw analyst target for its well-documented optimism bias before it
    # feeds the composite (the undiscounted target is still shown elsewhere in the UI),
    # then scale its already-low base weight down further when the sell-side estimates
    # are widely dispersed or thinly covered (_analyst_weight_factor).
    analyst_fv = analyst * (1 - ANALYST_TARGET_HAIRCUT) if analyst else None
    w_analyst  = W_ANALYST * _analyst_weight_factor(row)

    # Base weights (DDM scaled by the payout ramp, analyst by dispersion/coverage)
    candidates = [
        (gn,         W_GRAHAM),
        (pe_fv,      W_PE),
        (epv,        W_EPV),
        (ddm1,       w_ddm1),
        (ddm2,       w_ddm2),
        (analyst_fv, w_analyst),
    ]
    avail = [(v, w) for v, w in candidates if v is not None and v > 0 and w > 0]
    if not avail:
        return {"graham_number": gn, "pe_fair_value": pe_fv, "epv": epv,
                "ddm": ddm1, "ddm_multistage": ddm2, "fair_value": None,
                "ddm_contributed": False}

    total_w = sum(w for _, w in avail)
    iv      = sum(v * w / total_w for v, w in avail)

    # Did either DDM variant actually feed the composite? (a positive ramp factor
    # alone isn't enough — the variant can still be None, e.g. the WACC<=g guard
    # in _ddm_single, or filtered by the v > 0 / w > 0 test above.)
    ddm_contributed = (ddm1, w_ddm1) in avail or (ddm2, w_ddm2) in avail

    return {
        "graham_number":  gn,
        "pe_fair_value":  pe_fv,
        "epv":            epv,
        "ddm":            round(ddm1, 2) if ddm1 else None,
        "ddm_multistage": round(ddm2, 2) if ddm2 else None,
        "fair_value":     round(iv, 2),
        "ddm_contributed": ddm_contributed,
    }


# ── Stage 3: MoS, TER, Dividend Sustainability Flag ──────────────────────────

def _margin_of_safety(price, fair_value) -> float | None:
    if price and fair_value and fair_value > 0 and price > 0:
        return (fair_value - price) / fair_value
    return None


def _total_expected_return(price, fair_value, div_yield, dgr, ddm_contributed=False) -> float | None:
    """TER = capital gain % + forward dividend yield + expected DGR (all as %).

    When DDM contributed to this stock's fair value, the growth assumption is
    already embedded in the capital-gain term via the fair value itself — adding
    the full DGR proxy on top would double-count it, so it's halved in that case.
    """
    if not price or price <= 0:
        return None
    cap_gain = ((fair_value - price) / price * 100) if fair_value else 0.0
    dy       = (div_yield * 100) if div_yield else 0.0
    dg       = (max(0.0, min(0.10, dgr)) * 100) if dgr else 0.0
    if ddm_contributed:
        dg *= 0.5
    return round(cap_gain + dy + dg, 1)


# ── Stage 4: Risk scoring ─────────────────────────────────────────────────────
# _clamp, _get_num, _financial_health_score, _earnings_quality_score and
# _dividend_sustainability_flag now live in scoring.py (shared with risk.py) and
# are re-exported at the top of this module.

def _dgr_estimate(row: pd.Series):
    """Best available dividend growth rate for a row: the true 5-6yr DPS CAGR
    (`true_dgr`, from _dividend_stats) when we have enough history, otherwise
    the `earningsGrowth` proxy. A real 0.0 (flat DPS) still wins over the
    proxy — the None check is deliberate, not truthiness."""
    v = _get_num(row, "true_dgr")
    return v if v is not None else _get_num(row, "earningsGrowth")


def _market_risk_score(row: pd.Series) -> float:
    """0–10, higher = lower beta risk. Beta is Blume-adjusted (shrunk toward
    1.0) before scoring — see _adjust_beta — so a noisy trailing estimate can't
    swing this dimension as hard."""
    beta = _adjust_beta(_get_num(row, "beta"))
    if beta is None:
        return 5.0
    return float(_clamp(10 - abs(beta) * 3.5, 0, 10))


def _dividend_risk_score(row: pd.Series) -> float:
    """
    0–10, higher = lower dividend risk.
    For non-payers: neutral 5.0.
    """
    div_rate = _get_num(row, "trailingAnnualDividendRate") or _get_num(row, "dividendRate")
    if not div_rate or div_rate <= 0:
        return 5.0  # neutral for non-payers

    scores = []
    payout = _get_num(row, "payoutRatio")
    if payout is not None and payout > 0:
        if 0.30 <= payout <= 0.70:
            scores.append(10.0)
        elif payout < 0.30:
            scores.append(7.0)
        elif payout <= 0.85:
            scores.append(4.0)
        else:
            scores.append(0.0)   # > 85% at risk

    cpr = _get_num(row, "cashPayoutRatio")
    if cpr is not None:
        scores.append(_clamp(10 - cpr * 10, 0, 10))  # 0% = 10, 100% = 0

    coverage = _get_num(row, "dividendCoverage")
    if coverage is not None:
        scores.append(_clamp(coverage * 2, 0, 10))    # 1.5× = 3, 5× = 10

    dgr = _dgr_estimate(row)                           # true DPS CAGR, else earningsGrowth
    if dgr is not None:
        scores.append(_clamp(5 + dgr * 25, 0, 10))

    return float(np.mean(scores)) if scores else 5.0


def _liquidity_score(row: pd.Series) -> float:
    """0–10, higher = more liquid."""
    vol = _get_num(row, "averageVolume")
    if vol is None or vol <= 0:
        return 5.0
    if vol >= 500_000: return 10.0
    if vol >= 100_000: return 7.5
    if vol >= 25_000:  return 5.0
    return 2.5


def _composite_risk_raw(row: pd.Series) -> float:
    """
    0–10 risk level (higher = riskier).
    Averages dimension safety scores then inverts.
    """
    h = _financial_health_score(row)
    e = _earnings_quality_score(row)
    m = _market_risk_score(row)
    d = _dividend_risk_score(row)
    l = _liquidity_score(row)
    return float(10 - np.mean([h, e, m, d, l]))


# ── Quality and Momentum raw scores ──────────────────────────────────────────

def _quality_raw(row: pd.Series) -> float:
    """0–10 composite of profitability / efficiency metrics."""
    scores = []
    roe = _get_num(row, "returnOnEquity")
    if roe is not None: scores.append(_clamp(roe * 50, 0, 10))
    roa = _get_num(row, "returnOnAssets")
    if roa is not None: scores.append(_clamp(roa * 100, 0, 10))
    om  = _get_num(row, "operatingMargins")
    if om  is not None: scores.append(_clamp(om * 50, 0, 10))
    fcy = _get_num(row, "fcfYield")
    if fcy is not None: scores.append(_clamp(fcy * 100, 0, 10))
    cr  = _get_num(row, "currentRatio")
    if cr  is not None: scores.append(_clamp((cr - 0.5) / 0.15, 0, 10))
    return float(np.mean(scores)) if scores else 5.0


def _momentum_raw(row: pd.Series) -> float:
    """0–10 composite of growth and analyst sentiment."""
    scores = []
    eg = _get_num(row, "earningsGrowth")
    if eg is not None: scores.append(_clamp(5 + eg * 25, 0, 10))
    rg = _get_num(row, "revenueGrowth")
    if rg is not None: scores.append(_clamp(5 + rg * 25, 0, 10))
    rm = _get_num(row, "recommendationMean")
    if rm is not None: scores.append(_clamp((5 - rm) / 4 * 10, 0, 10))
    return float(np.mean(scores)) if scores else 5.0


def _dividend_score_raw(row: pd.Series) -> float:
    """
    0–10 composite dividend attractiveness score.
    Combines: yield vs 5-yr average, payout safety, cash coverage, DGR proxy.
    Non-payers get neutral 5.0 so they are not penalised.
    """
    div_rate = _get_num(row, "trailingAnnualDividendRate") or _get_num(row, "dividendRate")
    if not div_rate or div_rate <= 0:
        return 5.0   # neutral — non-payer is neither rewarded nor penalised

    scores = []

    # 1. Current yield vs 5-year average yield
    dy      = _get_num(row, "dividendYield")
    avg_dy  = _get_num(row, "fiveYearAvgDividendYield")
    if dy and avg_dy and avg_dy > 0:
        ratio = dy / avg_dy
        scores.append(_clamp(ratio * 5, 0, 10))  # at avg = 5, 2× avg = 10

    # 2. Payout ratio sustainability
    payout = _get_num(row, "payoutRatio")
    if payout and payout > 0:
        if 0.30 <= payout <= 0.70:
            scores.append(10.0)
        elif payout < 0.30:
            scores.append(7.0)
        elif payout <= 0.85:
            scores.append(4.0)
        else:
            scores.append(0.0)

    # 3. Cash payout ratio (lower = safer)
    cpr = _get_num(row, "cashPayoutRatio")
    if cpr is not None:
        scores.append(_clamp(10 - cpr * 10, 0, 10))

    # 4. Dividend coverage ratio
    coverage = _get_num(row, "dividendCoverage")
    if coverage is not None:
        scores.append(_clamp(coverage * 2, 0, 10))

    # 5. Dividend growth — true DPS CAGR when available, else earningsGrowth
    dgr = _dgr_estimate(row)
    if dgr is not None:
        scores.append(_clamp(5 + dgr * 25, 0, 10))

    return float(np.mean(scores)) if scores else 5.0


# ── Stage 5: Composite score ──────────────────────────────────────────────────

def _pct_rank(series: pd.Series, ascending=True) -> pd.Series:
    """Percentile rank 0–100. NaN rows receive 50 (neutral)."""
    ranked = series.rank(pct=True, na_option="keep") * 100
    if not ascending:
        ranked = 100 - ranked
    return ranked.fillna(50.0)


def _abs_band(value, points: list) -> float:
    """Map `value` through the piecewise-linear (x, y) `points` (x ascending),
    clamped to the endpoint y outside the range. None/NaN → the midpoint of the
    two endpoint y's (neutral), matching _pct_rank's NaN handling."""
    if value is None or pd.isna(value):
        return (points[0][1] + points[-1][1]) / 2.0
    if value <= points[0][0]:
        return float(points[0][1])
    if value >= points[-1][0]:
        return float(points[-1][1])
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if value <= x1:
            return float(y0 + (y1 - y0) * (value - x0) / (x1 - x0))
    return float(points[-1][1])


def _blend_ranks(series: pd.Series, band: list, ascending: bool = True) -> pd.Series:
    """BLEND_PCT × cross-sectional percentile rank + (1 − BLEND_PCT) × absolute
    band — the composite sub-score for one dimension (0–100, higher = better)."""
    pct = _pct_rank(series, ascending=ascending)
    absolute = series.apply(lambda v: _abs_band(v, band))
    return BLEND_PCT * pct + (1.0 - BLEND_PCT) * absolute


def _fcf_hard_veto(row: pd.Series) -> bool:
    """True if FCF has been negative for 3+ consecutive most-recent fiscal years
    (`fcfHistory`, newest first). Falls back to a single most-recent-period check
    (`freeCashflow`) when fewer than 3 years of history are available — e.g. recent
    IPOs, or tickers where the cash flow statement fetch failed/is unsupported.
    """
    history = row.get("fcfHistory")
    if isinstance(history, list) and len(history) >= 3:
        return all(v < 0 for v in history[:3])
    fcf = row.get("freeCashflow")
    return bool(fcf is not None and fcf < 0)


# Trend-based hard vetoes (WS-15). Each needs a minimum window of the relevant
# multi-year series (screener._statement_history / _dividend_stats); a series
# that short or absent simply doesn't trigger — recent IPOs and failed statement
# fetches never get vetoed for missing data.
_TREND_MIN_YEARS       = 3      # points a history list needs before a trend check runs
_TREND_DECLINE_RUN     = 2      # consecutive YoY declines that count as a decline trend
_DIV_CUT_VETO_YEARS    = 2      # a DPS cut this recent, plus thin cover, is a standalone veto
_DIV_CUT_VETO_COVERAGE = 1.5    # "thin" dividend cover for that standalone veto


def _clean_history(row: pd.Series, field: str) -> list[float]:
    """A newest-first history list column as finite floats (NaN/None dropped,
    order kept); [] when the column is absent or isn't a list."""
    hist = row.get(field)
    if not isinstance(hist, list):
        return []
    return [f for f in (_finite(v) for v in hist) if f is not None]


def _declining_run(vals: list[float]) -> int:
    """Consecutive year-over-year declines at the newest end of a newest-first
    series: `vals[0] < vals[1] < vals[2] …` → 2, 3, … (0 if the newest year
    didn't fall)."""
    run = 0
    for i in range(len(vals) - 1):
        if vals[i] < vals[i + 1]:
            run += 1
        else:
            break
    return run


def _trend_veto(row: pd.Series) -> list[str]:
    """Reasons a stock trips a *trend*-based hard veto (empty list = clean).

    The static, point-in-time vetoes (sector-adjusted D/E, single-period FCF,
    at-risk dividend + coverage < 1.0) live in compute_scores / veto_reason_str;
    this is the multi-year-deterioration set. One function, so compute_scores and
    both veto UIs (components.veto_reason_str, analysis.py's checks panel) read
    the exact same rule instead of re-deriving it.
    """
    reasons: list[str] = []

    rev = _clean_history(row, "revenueHistory")
    if len(rev) >= _TREND_MIN_YEARS:
        run = _declining_run(rev)
        if run >= _TREND_DECLINE_RUN:
            reasons.append(f"revenue fell {run + 1} straight years")

    ebit = _clean_history(row, "ebitHistory")
    if len(ebit) >= _TREND_MIN_YEARS and all(v < 0 for v in ebit[:_TREND_MIN_YEARS]):
        reasons.append(f"operating income negative {_TREND_MIN_YEARS} years running")

    ret = _clean_history(row, "retainedEarningsHistory")
    if (len(ret) >= _TREND_MIN_YEARS and ret[0] < 0
            and _declining_run(ret) >= _TREND_DECLINE_RUN):
        reasons.append("retained earnings negative and still eroding")

    last_cut = _get_num(row, "dividend_last_cut_year")
    coverage = _get_num(row, "dividendCoverage")
    if (last_cut is not None and coverage is not None
            and last_cut >= datetime.now(timezone.utc).year - _DIV_CUT_VETO_YEARS
            and coverage < _DIV_CUT_VETO_COVERAGE):
        reasons.append(f"dividend cut in {int(last_cut)} with only {coverage:.2f}× cover")

    return reasons


def compute_scores(df: pd.DataFrame, *, max_debt_equity: float = 500.0,
                   max_payout: float = 0.90, min_mos: float = 0.0,
                   buy_threshold: float = SCORE_STRONG_BUY,
                   weights: "tuple | None" = None) -> pd.DataFrame:
    # Composite sub-score weights (W_MOS, W_RISK, W_QUALITY, W_MOMENTUM,
    # W_DIVIDEND). None → the module defaults ("balanced"); the Settings
    # screening-style picker passes a re-lensed vector via
    # settings.get_score_weights().
    w_mos, w_risk, w_quality, w_momentum, w_dividend = (
        weights if weights is not None
        else (W_MOS, W_RISK, W_QUALITY, W_MOMENTUM, W_DIVIDEND)
    )
    # Ensure all expected columns exist (older cache may be missing new fields)
    all_fields = [
        *VALUATION_FIELDS, *RISK_FIELDS, *QUALITY_FIELDS, *MOMENTUM_FIELDS,
        "fcfYield", "cashPayoutRatio", "dividendCoverage",
        "exDividendDate", "dividendDate", "sector", "fcfHistory",
        "true_dgr", "dividend_growth_streak", "dividend_payment_years",
        "dividend_last_cut_year",
        *_STATEMENT_HISTORY_KEYS,
    ]
    # dict.fromkeys dedupes: VALUATION/RISK/QUALITY/MOMENTUM field lists overlap
    # (e.g. currentRatio, freeCashflow appear in two of them), and reindexing with
    # a duplicated name produces a duplicate column — every later row.get(name)
    # then returns a 2-value Series and blows up the scalar guards downstream.
    _missing = [f for f in dict.fromkeys(all_fields) if f not in df.columns]
    df = df.reindex(columns=[*df.columns, *_missing])

    # ── Stage 2: fair values ──────────────────────────────────────────────────
    sector_pe = _sector_pe_medians(df)   # universe-relative PE-fair-value multiples
    fv_cols = df.apply(lambda r: _fair_value_models(r, sector_pe=sector_pe),
                       axis=1, result_type="expand")
    for col in fv_cols.columns:
        df[col] = fv_cols[col]

    # ── Stage 3: MoS · TER · Dividend Sustainability ─────────────────────────
    df["margin_of_safety"] = df.apply(
        lambda r: _margin_of_safety(r["Price"], r["fair_value"]), axis=1
    )
    df["TER %"] = df.apply(
        lambda r: _total_expected_return(
            r["Price"], r["fair_value"],
            r.get("dividendYield"), _dgr_estimate(r),
            r.get("ddm_contributed", False)
        ), axis=1
    )
    df["Div Flag"] = df.apply(lambda r: _dividend_sustainability_flag(r, max_payout=max_payout), axis=1)

    # ── Stage 4: raw dimension scores (0–10) ─────────────────────────────────
    df["_risk_raw"]     = df.apply(_composite_risk_raw, axis=1)
    df["_quality_raw"]  = df.apply(_quality_raw,        axis=1)
    df["_momentum_raw"] = df.apply(_momentum_raw,       axis=1)
    df["_dividend_raw"] = df.apply(_dividend_score_raw, axis=1)

    # Hard veto: D/E > max_debt_equity (user-configurable, default 500 ≈5×), skipped for
    # LEVERAGE_EXEMPT_SECTORS where high leverage is structural rather than distress, OR
    # FCF negative for 3+ consecutive years (single most-recent period if less history
    # is available) OR dividend flagged at risk with coverage < 1.0 (imminent cut risk)
    # OR any multi-year deterioration trend (_trend_veto: revenue decline, EBIT
    # collapse, retained-earnings erosion, a recent dividend cut on thin cover).
    de            = df["debtToEquity"].fillna(0)
    coverage      = df["dividendCoverage"].fillna(999)
    leverage_exempt = df["sector"].isin(LEVERAGE_EXEMPT_SECTORS)
    fcf_veto      = df.apply(_fcf_hard_veto, axis=1)
    trend_veto    = df.apply(lambda r: bool(_trend_veto(r)), axis=1)
    df["_hard_veto"] = ((de > max_debt_equity) & ~leverage_exempt) | fcf_veto | trend_veto | (
        (df["Div Flag"] == "At Risk") & (coverage < 1.0)
    )

    # ── Stage 5: sub-scores (blend of percentile rank + absolute band) → 0–100 ─
    mos_rank      = _blend_ranks(df["margin_of_safety"], _BAND_MOS,  ascending=True)
    risk_rank     = _blend_ranks(df["_risk_raw"],        _BAND_RISK, ascending=False)  # lower raw = safer
    quality_rank  = _blend_ranks(df["_quality_raw"],     _BAND_0_10, ascending=True)
    momentum_rank = _blend_ranks(df["_momentum_raw"],    _BAND_0_10, ascending=True)
    dividend_rank = _blend_ranks(df["_dividend_raw"],    _BAND_0_10, ascending=True)

    score = (
        w_mos       * mos_rank
        + w_risk    * risk_rank
        + w_quality  * quality_rank
        + w_momentum * momentum_rank
        + w_dividend * dividend_rank
    ).round(1)

    score[df["_hard_veto"]] = 0.0
    df["Value Score"] = score

    # Composite sub-scores (0-100 percentile ranks) — kept as named columns
    # (not "_"-prefixed, so they survive the internal-column drop below) so
    # the Analysis page's "Signal sub-scores" section can show what actually
    # drove the composite instead of just the final number.
    df["Sub MoS"]      = mos_rank.round(1)
    df["Sub Risk"]     = risk_rank.round(1)
    df["Sub Quality"]  = quality_rank.round(1)
    df["Sub Momentum"] = momentum_rank.round(1)
    df["Sub Dividend"] = dividend_rank.round(1)

    # Flag every row when the screened universe is too small for the percentile ranks
    # above to be statistically meaningful (see MIN_UNIVERSE_SIZE) — callers (e.g. the
    # Screener page) can surface this as a caveat rather than letting a "Strong Buy"
    # from a tiny universe look as confident as one from a large, competitive one.
    df["small_universe"] = len(df) < MIN_UNIVERSE_SIZE

    # ── Stage 6: decision ────────────────────────────────────────────────────
    # A BUY requires both the composite score AND the margin of safety to
    # clear their configured thresholds (Settings → Screening & veto rules) —
    # a high score alone no longer overrides an unacceptably thin MoS. A stock
    # with no computable fair value (NaN MoS — every model failed) can't have
    # its margin of safety confirmed, so it can't reach Strong Buy either; it
    # falls through to Monitor/Avoid on score alone instead of bypassing the gate.
    def _decision(row):
        if row["_hard_veto"]:
            return "Avoid"
        s   = row["Value Score"]
        mos = row["margin_of_safety"]
        if s >= buy_threshold and pd.notna(mos) and mos >= min_mos:
            return "Strong Buy"
        if s >= SCORE_AVOID:
            return "Monitor"
        return "Avoid"

    df["Decision"]   = df.apply(_decision, axis=1)
    df["Risk Score"] = df["_risk_raw"].round(1)
    df["MoS %"]      = (df["margin_of_safety"] * 100).round(1)

    # Expose the veto flag publicly before dropping internal-only columns
    df["veto"] = df["_hard_veto"]

    # Drop internal columns
    df = df.drop(columns=[c for c in df.columns if c.startswith("_")])
    df = df.sort_values("Value Score", ascending=False).reset_index(drop=True)
    df.index += 1
    return df



def run_screener_from_df(df: pd.DataFrame, *, max_debt_equity: float = 500.0,
                         max_payout: float = 0.90, min_mos: float = 0.0,
                         buy_threshold: float = SCORE_STRONG_BUY,
                         weights: "tuple | None" = None) -> pd.DataFrame:
    """Score and clean a DataFrame that was already fetched (avoids re-fetching)."""
    return _score_and_clean(df.copy(), max_debt_equity=max_debt_equity,
                            max_payout=max_payout, min_mos=min_mos,
                            buy_threshold=buy_threshold, weights=weights)


def _score_and_clean(df: pd.DataFrame, *, max_debt_equity: float = 500.0,
                     max_payout: float = 0.90, min_mos: float = 0.0,
                     buy_threshold: float = SCORE_STRONG_BUY,
                     weights: "tuple | None" = None) -> pd.DataFrame:
    if "Price" not in df.columns:
        df["Price"] = None
    before  = len(df)
    df      = df[df["Price"].notna()].reset_index(drop=True)
    dropped = before - len(df)
    if dropped:
        print(f"  Dropped {dropped} ticker(s) with no price (likely delisted/inactive)")
    if df.empty:
        return df
    print("Computing valuation scores...")
    return compute_scores(df, max_debt_equity=max_debt_equity, max_payout=max_payout,
                          min_mos=min_mos, buy_threshold=buy_threshold, weights=weights)
