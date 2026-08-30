"""
Shared 0–10 fundamental scoring helpers used by *both* the valuation screener
(screener.py) and the portfolio risk engine (risk.py).

They live here so risk.py doesn't have to reach into screener.py's private
namespace. screener.py re-exports every name below, so existing call sites
(`from screener import _financial_health_score`, …) keep working unchanged.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

_DIV_RECENT_CUT_YEARS = 3   # a DPS cut this recent still flags the payer

# Sloan-style accrual ratio at which the accrual sub-score of earnings quality
# hits 0. accr = (net income - operating cash flow) / total assets; ~0 or
# negative is clean (score 10), >= this is heavily accrual-driven (score 0).
_ACCRUAL_SCALE = 0.15


def _clamp(v, lo, hi):
    return float(np.clip(v, lo, hi))


def _finite(v) -> float | None:
    """v as a float, or None if it isn't a number or is NaN."""
    if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v)):
        return float(v)
    return None


def _latest_from_history(row: pd.Series, field: str):
    """Most-recent (index 0) finite value of a newest-first history list column
    (screener._statement_history: `revenueHistory`, `cfoHistory`,
    `totalAssetsHistory`, …), or None. Tolerates the column being absent — a
    reindex leaves a NaN scalar, not a list — or holding NaN entries."""
    hist = row.get(field)
    if not isinstance(hist, list):
        return None
    for v in hist:
        f = _finite(v)
        if f is not None:
            return f
    return None


def _get_num(row: pd.Series, field: str):
    """row.get(field), normalizing NaN to None. compute_scores calls all the
    scoring functions below via df.apply(fn, axis=1), which hands each one a
    pandas Series where a field missing for this ticker (or a whole column
    reindexed in for schema compatibility) reads as float NaN, not a missing
    key. Every `is not None` / truthy guard below assumes plain-dict get()
    semantics (missing -> None) and doesn't catch NaN, so without this,
    NaN silently flows into arithmetic and corrupts the whole np.mean(scores)
    to NaN for that dimension -- even when the other inputs were fine.
    """
    v = row.get(field)
    return None if pd.isna(v) else v


def _financial_health_score(row: pd.Series) -> float:
    """0–10, higher = healthier."""
    scores = []
    de = _get_num(row, "debtToEquity")
    if de is not None:
        de_ratio = de / 100   # yfinance: 100 = 1.0×
        scores.append(_clamp(10 - de_ratio * 2.5, 0, 10))
    cr = _get_num(row, "currentRatio")
    if cr is not None:
        scores.append(_clamp((cr - 0.5) / 0.15, 0, 10))
    ic = _get_num(row, "interestCoverage")
    if ic is not None and ic > 0:
        scores.append(_clamp(ic / 2, 0, 10))
    return float(np.mean(scores)) if scores else 5.0


def _earnings_quality_score(row: pd.Series) -> float:
    """0–10, higher = better quality.

    Blends three signals, whichever have inputs (else a neutral 5.0):
    - **FCF-to-net-income conversion** — net income the cash flow doesn't back is
      lower quality.
    - **Multi-year FCF-history consistency** (`fcfHistory`) — the fraction of
      positive years and how stable the level is.
    - **Sloan accrual ratio** — `(net income − operating cash flow) / total
      assets` (latest year of `cfoHistory` / `totalAssetsHistory`, falling back
      to `freeCashflow` as a rougher stand-in for CFO). Large positive accruals
      (earnings running ahead of cash, scaled by the asset base) mean-revert and
      predict weaker future returns; ~0 or negative scores clean.
    """
    scores: list[float] = []

    fcf = _get_num(row, "freeCashflow")
    ni  = _get_num(row, "netIncome")
    if fcf is not None and ni is not None and ni != 0:
        scores.append(_clamp(5 + (fcf / abs(ni)) * 3, 0, 10))

    hist = row.get("fcfHistory")
    if isinstance(hist, list):
        vals = [f for f in (_finite(v) for v in hist) if f is not None]
        if len(vals) >= 3:
            pos_frac  = sum(1 for v in vals if v > 0) / len(vals)
            mean      = sum(vals) / len(vals)
            cv        = float(np.std(vals)) / abs(mean) if mean != 0 else 5.0
            stability = _clamp(10 - cv * 4, 0, 10)        # cv 0 → 10, cv 2.5 → 0
            scores.append(_clamp((pos_frac * 10 + stability) / 2, 0, 10))

    # Sloan accruals. CFO from the statement history is the textbook input; FCF
    # (CFO − capex) overstates accruals by the capex line but is a usable proxy.
    cfo    = _latest_from_history(row, "cfoHistory")
    if cfo is None:
        cfo = fcf
    assets = _latest_from_history(row, "totalAssetsHistory")
    if ni is not None and cfo is not None and assets is not None and assets > 0:
        accr = (ni - cfo) / assets
        scores.append(_clamp(10 - (accr / _ACCRUAL_SCALE) * 10, 0, 10))

    return float(np.mean(scores)) if scores else 5.0


def _dividend_sustainability_flag(row: pd.Series, max_payout: float = 0.90) -> str:
    """
    Returns 'At Risk', 'OK', or '' (non-payer).
    Checks: payout ratio (user-configurable via Settings' "Max dividend
    payout" slider — see settings.get_veto_thresholds()), cash payout
    ratio, dividend coverage ratio, and a DPS cut within the last
    _DIV_RECENT_CUT_YEARS complete years (`dividend_last_cut_year`, from
    screener._dividend_stats).
    """
    div_rate = row.get("trailingAnnualDividendRate") or row.get("dividendRate")
    if not div_rate or div_rate <= 0:
        return ""  # non-payer, no flag

    payout   = row.get("payoutRatio")
    cpr      = row.get("cashPayoutRatio")
    coverage = row.get("dividendCoverage")

    last_cut = row.get("dividend_last_cut_year")
    recent_cut = (last_cut is not None and not pd.isna(last_cut)
                  and last_cut >= datetime.now(timezone.utc).year - _DIV_RECENT_CUT_YEARS)

    if (payout   and payout   > max_payout) or \
       (cpr      and cpr      > 0.80) or \
       (coverage and coverage < 1.20) or \
       recent_cut:
        return "At Risk"
    return "OK"
