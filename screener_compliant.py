"""
Stock valuation screener — LEGAL-COMPLIANCE COPY of screener.py.

Same 6-stage algorithm as screener.py (docs/stock_valuation_algorithm.md), with
the changes required by "Uvalu — Legal Requirements for Launch" (Oct 2 2026).
screener.py itself is untouched; this module is a candidate replacement, not
yet wired into the app. Review: docs/legal/algorithm-compliance-review.md.

Stage 1  — Data collection: imported from screener.py (shared fetcher + cache)
Stage 2  — Fair value: Graham Number · PE Fair Value · EPV · DDM (single + multi-stage)
           · Analyst only when ANALYST_INPUTS_ENABLED (licensed data, DATA-6)
Stage 3  — Margin of Safety + model-implied return (estimate) + Dividend Sustainability Flag
Stage 4  — Risk scoring: financial health · earnings quality · market risk · dividend risk · liquidity
Stage 5  — Composite Score = α×MoS + β×(100−Risk) + γ×Quality + δ×Momentum + ε×DividendScore
Stage 6  — Model signal (descriptive, BDG-1): Undervalued | Neutral | Low score |
           Fails quality screen | Pending — replaces Strong Buy / Monitor / Avoid

What changed versus screener.py, by requirement ID:
  PER-1/2  Peer reference (sector medians, percentile ranks) is built from the
           public universe only (``peer_mask``); a user-selected set (holdings,
           watchlist) scored without one gets no signal (``user_selected``).
  BDG-1/3  Descriptive signal labels; veto is its own state, not folded into Avoid.
  REC-2    Model outputs carry ``is_estimate`` semantics in their names
           ("Implied Return % (est.)"); ``signal_reason`` states the rule applied.
  REC-3    ``data_source`` and ``data_flags`` (stale price, thin basis, derived
           EPS, clamped fair value, small peer group) on every row.
  REC-4    ``signal_computed_at`` and ``price_as_of`` on every row.
  REC-5/6  ``methodology()`` and ``SIGNAL_DEFINITIONS`` read the live constants,
           so the methodology page cannot drift from the code.
  REC-10   ``signal_distribution()``.
  REC-11   ``model_version`` + ``model_settings_id`` per row; ``signal_records()``.
  DATA-6   Analyst price targets and recommendation means are off by default.
"""

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from uvalu import logkit
from uvalu.i18n import N_, Fmt, lazy_
from scoring import (  # re-exported for existing `from screener import …` call sites
    _clamp, _get_num, _finite,
    _financial_health_score, _earnings_quality_score, _dividend_sustainability_flag,
)

# ── Constants ─────────────────────────────────────────────────────────────────

_log = logkit.get_logger("uvalu.screener")
_fetch_log = logkit.get_logger("uvalu.screener.fetch")  # per-ticker; sampled (see logging.config.json)

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
# Gordon-growth models blow up as the discount rate approaches the growth rate:
# the whole valuation collapses onto a near-zero denominator. Below this spread
# between WACC and g the DDM output is dominated by that instability rather than
# by the cash flows, so the variant is dropped instead of returned. Feeding the
# real dividend CAGR into the DDM (FV-7) makes low-beta / high-DGR names hit this
# regime far more often, so the guard is load-bearing, not cosmetic.
DDM_MIN_SPREAD      = 0.03

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

# FV-3: book-value and FCF fair-value *fallbacks*. Both are crude — a
# sector-median P/B misprices high-ROE compounders, a flat FCF multiple misprices
# growth — so they enter the blend ONLY when *none* of the fundamentals trio
# (Graham / PE / EPV) produced a value, i.e. for genuine loss-makers where any
# fundamentals anchor beats a lone haircut analyst target. Their weights sit
# *outside* the six-model sum above (like the DDM payout ramp and the analyst
# dispersion factor, they're conditionally applied, not part of the base rate).
W_PB  = 0.10
W_FCF = 0.10
PB_MULTIPLE_FALLBACK = 1.5          # sector has < MIN_SECTOR_SAMPLE priced peers / no priceToBook
PB_MULTIPLE_BAND     = (0.5, 4.0)   # winsor bounds on a sector-median P/B
FCF_MULTIPLE         = 15.0         # ≈ 6.7% FCF yield; fixed, not 1/(WACC−g) (Gordon instability)

# Composite fair-value sanity guard. A blended fair value above this multiple of
# the current price is only trusted when at least two of the individual models
# independently land that high — otherwise it's a single runaway model (a DDM
# with WACC barely above g, a stale REIT NAV) dragging the weighted mean up, and
# the composite is clamped to the models' median (never below the current
# price). REIT / NAV-style names are the usual offenders; a proper P/B-anchored
# model for that cohort is the real fix, this is the guardrail.
FV_SANITY_MULT = 2.0

# Per-share input sanity floor. `bookValue` / `trailingEps` are both scaled by
# the same `sharesOutstanding` figure for a given row, so when Price/bookValue
# (the implied P/B) falls below this floor, that scaling is suspect for the
# whole row — either a genuine data defect (a secondary listing whose reported
# per-share fundamentals were computed off a different share count/class than
# the one actually priced, e.g. a foreign megacap's illiquid depositary line)
# or a real but structural mismatch (a central-bank-style issuer whose legally
# capped dividend breaks the standard proportional-equity-claim assumption
# these models rely on). Either way, book-value- and earnings-anchored models
# built on that basis (Graham, PE fair value, the P/B fallback/NAV-primary
# model) aren't trustworthy for this row and are held dark rather than
# contributing a number the market's own pricing already contradicts by orders
# of magnitude. Deliberately P/B-only, not a symmetric P/E floor: trailingEps
# is a flow figure that legitimately swings on ordinary earnings volatility (a
# real one-off gain can push implied P/E below 1 with nothing wrong), while
# bookValue is comparatively stable — an implausible P/B is a much cleaner
# signal on its own than an implausible P/E, which produced real false
# positives (genuinely cheap, legitimately low-P/E small caps) when tried.
# Calibrated against the full scored universe: the lowest P/B among live
# Strong Buy rows outside this failure mode sits at ~0.11, a 5×+ margin above
# this floor.
PTB_SANITY_FLOOR = 0.02

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

# WP-B: when a fetched row is missing trailingEps but carries a trailingPE (a
# common shape for a partial Yahoo payload — summaryDetail lands, the
# defaultKeyStatistics module doesn't), _fetch_one recovers EPS as
# Price / trailingPE. Yahoo only publishes a positive trailingPE, so this only
# ever yields the eps > 0 that Graham Number and PE fair value need. The band
# rejects a nonsense ratio: the raw 0 < pe < 10_000 guard in _fetch_one is a
# display sanity bound, far too wide to divide a price by.
_PE_DERIVE_BAND = (2.0, 200.0)

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

# ── Legal-compliance constants (see module docstring) ─────────────────────────

# REC-11: bump on any change that can move a fair value, score or signal, so a
# logged signal can be reproduced against the code that produced it.
MODEL_VERSION = "2.0.1-legal.1"

# REC-3 / DATA-4: where the inputs come from. Replace with the licensed
# provider's name and required attribution wording once DATA-2 is signed.
DATA_SOURCE = "Yahoo Finance (via yfinance), unlicensed for commercial use"

# DATA-6: analyst price targets (targetMeanPrice/High/Low, numberOfAnalystOpinions)
# and the consensus recommendation mean are sell-side content licensed separately
# from prices and fundamentals. Off until a licence covers them; with it off the
# analyst model drops out of the fair-value blend (its weight renormalises across
# the remaining models) and momentum uses earnings + revenue growth only.
ANALYST_INPUTS_ENABLED = False

# REC-3: a price older than this is flagged as stale in `data_flags`.
PRICE_STALE_HOURS = 72

# BDG-1: descriptive signal states. `signal_code` is the stable machine value
# (store/compare this); `Signal` is the English display label (show via tr()).
# Deviation from BDG-1's literal mapping, deliberately: MONITOR → "Near fair
# value" and AVOID → "Overvalued" would be false for many rows, because the
# bands come from the composite score (MoS + risk + quality + momentum +
# dividend), not from valuation alone — a stock 30% below fair value with weak
# quality sits in the lowest band. Labels must describe what the model measured
# (REC-2; WER VI.97 misleading practices), so the lower bands are named after
# the score.
SIGNAL_UNDERVALUED = "undervalued"
SIGNAL_NEUTRAL     = "neutral"
SIGNAL_LOW_SCORE   = "low_score"
SIGNAL_FAILS       = "fails_screen"
SIGNAL_PENDING     = "pending"

SIGNAL_LABELS = {
    SIGNAL_UNDERVALUED: N_("Undervalued"),
    SIGNAL_NEUTRAL:     N_("Neutral"),
    SIGNAL_LOW_SCORE:   N_("Low score"),
    SIGNAL_FAILS:       N_("Fails quality screen"),
    SIGNAL_PENDING:     N_("No signal"),
}

# BDG-2: tooltip on every badge, plus the methodology link (the page renders it).
SIGNAL_TOOLTIP = N_("Model output based on public data and the settings shown. "
                    "Not a recommendation tailored to you.")

# REC-6: what each state means, the horizon the model assumes, and the risk
# warning. Thresholds are filled in from the live settings by methodology().
SIGNAL_HORIZON = N_("The models value a business on its current fundamentals and "
                    "assume a multi-year holding horizon; they say nothing about "
                    "short-term price moves.")
SIGNAL_RISK_WARNING = N_("Model signals can be wrong. They depend on third-party data "
                         "that may be delayed or incorrect and on assumptions that may "
                         "not hold. Investing involves risk, including loss of capital.")
SIGNAL_SENSITIVITY = N_("Fair values are sensitive to the discount rate, growth and "
                        "sector multiples: with a 2% growth rate, raising the discount "
                        "rate from 8% to 9% lowers a dividend-model fair value by about 14%.")
SIGNAL_DEFINITIONS = {
    SIGNAL_UNDERVALUED: N_("Composite model score at or above the upper threshold, the "
                           "price at least the minimum margin below the model fair value, "
                           "and the fair value backed by two or more independent models."),
    SIGNAL_NEUTRAL:     N_("Composite model score between the lower and upper thresholds, "
                           "or above the upper threshold without a confirmed margin of safety."),
    SIGNAL_LOW_SCORE:   N_("Composite model score below the lower threshold."),
    SIGNAL_FAILS:       N_("Fails at least one quality rule (debt, cash flow, dividend "
                           "cover, multi-year decline or no trading volume); its composite "
                           "score is set to 0."),
    SIGNAL_PENDING:     N_("Not enough peer data to rank this stock yet."),
}

# Sectors where high leverage is a normal feature of the business model (banks and
# insurers hold customer deposits/float as liabilities, REITs debt-finance long-lived
# property, regulated utilities finance capex with debt) rather than a distress signal.
# The flat D/E hard veto can't tell healthy sector leverage from financial distress, so
# these sectors are exempt from it — other vetoes (negative FCF, at-risk dividend +
# low coverage) still apply.
# Sector names are market-data values: they stay English here and are shown
# through uvalu.i18n.tr(). N_() only marks them for translation.
LEVERAGE_EXEMPT_SECTORS = {N_("Financial Services"), N_("Real Estate"), N_("Utilities")}

# FV-8: sectors whose value is driven by the balance sheet, not an income
# statement, so the earnings-anchored models (Graham √(EPS·BVPS), a Greenwald
# EPV on EBIT) are noise. Real estate books IFRS fair-value revaluation gains in
# EPS — so EPS, and any P/E built on it, swings ±50% year to year; banks and
# insurers have no "EBIT" in the industrial sense.
#   • Real estate → Graham + P/E + EPV all skipped → `_trio` is 0 → valued off
#     the FV-3 book-value model (a NAV proxy) + DDM + analyst.
#   • Financial Services → Graham + EPV skipped, **P/E kept** (the standard bank
#     metric, on real not-revaluation-distorted EPS). The book-value model still
#     fires for them (see `pb_eligible` — it's a primary anchor for this cohort,
#     not just a loss-maker fallback), so a bank is valued off P/E + P/B + DDM +
#     analyst.
# Utilities are NOT here — regulated, stable EPS, a real operating EBIT.
_GRAHAM_EPV_SKIP_SECTORS = {"Real Estate", "Financial Services"}
_PE_SKIP_SECTORS         = {"Real Estate"}   # + revaluation-distorted P/E; banks keep P/E

# Sector fallback for tickers the fundamentals provider classifies as null — a
# gap that otherwise leaves a held name in the "Unknown" bucket on every screen
# (sector allocation donut, Risk-page sector HHI/concentration) and with no
# sector tag on the Holdings row. Keyed by exact ticker; only consulted when the
# provider's own `sector` is missing. Extend as gaps surface — these are stable
# GICS-style classifications, not judgement calls.
SECTOR_OVERRIDES = {
    "RET.BR":   N_("Real Estate"),            # Retail Estates NV — Belgian retail REIT
    "SYENS.BR": N_("Basic Materials"),        # Syensqo SA/NV — specialty chemicals
    "MELE.BR":  N_("Technology"),             # Melexis NV — automotive semiconductors
    "PROX.BR":  N_("Communication Services"), # Proximus PLC — telecom
}


def sector_for(ticker: object, raw_sector: object = None) -> "str | None":
    """The sector to display/aggregate for ``ticker``: the provider's own value
    when it has one, else a curated ``SECTOR_OVERRIDES`` fallback, else None.
    Shared by every screen that reads a sector so the Holdings tag, the
    allocation donut and the Risk-page concentration never disagree (WP-DQ7)."""
    if raw_sector is not None and not (isinstance(raw_sector, float) and pd.isna(raw_sector)):
        s = str(raw_sector).strip()
        if s and s.lower() != "nan":
            return s
    return SECTOR_OVERRIDES.get(str(ticker).strip())

# ── Stage 1: data collection — shared with screener.py, not copied ──────────
# The fetch/cache layer (yfinance workers, the two _Fetcher lanes and their
# cache files, dividend/statement history) is not a legal-compliance concern
# and holds process-wide state (background threads, cache paths), so this copy
# imports it rather than duplicating it: one fetcher, one cache, whichever
# scoring module is in use.
from screener import (  # noqa: E402
    MIN_FV_MODELS, CACHE_TTL_HOURS, CACHE_TTL_JITTER,
    VALUATION_FIELDS, RISK_FIELDS, QUALITY_FIELDS, MOMENTUM_FIELDS,
    _STATEMENT_HISTORY_KEYS, _row_fetch_time,
)
# Re-exported so uvalu/data.py can switch its `from screener import …` line to
# this module unchanged.
from screener import (  # noqa: E402, F401
    SCREENER_FETCH, PORTFOLIO_FETCH, load_fundamentals_cache, fetch_fundamentals_nowait,
    backfill_thin_rows_from_screener_lane, get_fetch_progress,
)



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
    # Keep the Gordon denominator sane by *clamping* g down to `wacc − DDM_MIN_SPREAD`
    # rather than dropping the model outright — a low-beta payer (wacc ≈ 5–7%) whose
    # dividend really compounds ~5% would otherwise silently lose single-stage DDM
    # (review). Only give up when WACC itself is below the minimum spread.
    g_cap = wacc - DDM_MIN_SPREAD
    if g_cap <= 0:
        return None
    g = _clamp(g if g is not None else 0.02, 0.0, min(0.05, g_cap))
    d1  = div_rate * (1 + g)
    val = d1 / (wacc - g)
    return val if 0 < val < 1e6 else None


def _ddm_multistage(div_rate, wacc, g_high, g_stable=DDM_STABLE_GROWTH,
                    years=DDM_HIGH_GROWTH_YRS) -> float | None:
    """2-stage DDM: explicit high-growth phase + Gordon terminal value."""
    if not div_rate or div_rate <= 0:
        return None
    if wacc - g_stable < DDM_MIN_SPREAD:
        return None
    # Cap g_high at `wacc − DDM_MIN_SPREAD` too: with g_high near/above wacc the
    # explicit-phase terms grow with t and inflate the PV before the terminal
    # value is even reached, and the terminal-leg guard above never sees it (review).
    g_high = _clamp(g_high if g_high is not None else 0.05,
                    0.0, min(0.15, wacc - DDM_MIN_SPREAD))
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


# FV-1: the payout ramp above needs a payout ratio, but yfinance's reported
# `payoutRatio` divides by trailing GAAP net income — it comes back absurd
# (1.4×, 7.7×), negative, or null for a loss-making, trough-earnings or
# freshly-demerged payer, and any value outside the ramp's own contributing band
# silently zero-weights BOTH DDM variants. `_payout_signal` trusts the reported
# ratio only while it is inside `[0, _DDM_PAYOUT_KNOTS[3]]` (0–95%) — the regime
# where the GAAP denominator is sound — and otherwise falls back to the cash
# payout (`cashPayoutRatio` = DPS·shares / FCF, derived in `_fetch_one`), then to
# the reciprocal of the EPS/DPS coverage ratio. Only when no proxy at all is
# available does it surface the extreme reported value (so the ramp still zeroes
# it). Returns (value | None, source); `source` is persisted on the scored row
# as `payout_source` for the UI.
_PAYOUT_CASH_MAX = 1.5   # accept the cash payout ratio as a signal up to here


def _payout_signal(row: "dict | pd.Series") -> "tuple[float | None, str]":
    pr = _finite(row.get("payoutRatio"))
    # `> 0`, not `>= 0`: a real payer's payout is never exactly zero, so a
    # provider `0.0` is missing-as-zero — fall through to the cash / coverage
    # proxies instead of trusting it (review).
    if pr is not None and 0.0 < pr <= _DDM_PAYOUT_KNOTS[3]:
        return pr, "reported"
    cpr = _finite(row.get("cashPayoutRatio"))
    if cpr is not None and 0.0 < cpr <= _PAYOUT_CASH_MAX:
        return cpr, "cash"
    cov = _finite(row.get("dividendCoverage"))
    if cov is not None and cov > 0:
        return min(1.0 / cov, 10.0), "coverage"
    if pr is not None and pr > 0:
        return pr, "reported"   # extreme (>0.95) and no better proxy — ramp zeroes it
    return None, "none"


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


def _sector_pb_medians(df: pd.DataFrame) -> dict:
    """{sector: winsorized median `priceToBook`} across `df`, for the FV-3 P/B
    fallback. Same shape and MIN_SECTOR_SAMPLE gate as `_sector_pe_medians`;
    callers fall back to PB_MULTIPLE_FALLBACK for an unlisted sector. Returns {}
    when the frame carries no `priceToBook`/`sector` columns (hand-built test
    frames) so `_fair_value_models` stays usable stand-alone."""
    if "priceToBook" not in df.columns or "sector" not in df.columns:
        return {}
    pb    = pd.to_numeric(df["priceToBook"], errors="coerce")
    valid = pd.DataFrame({"sector": df["sector"], "pb": pb})
    valid = valid[(valid["pb"] > 0) & (valid["pb"] < 100) & valid["sector"].notna()]
    if valid.empty:
        return {}
    lo, hi = PB_MULTIPLE_BAND
    return {
        sector: float(np.clip(grp["pb"].median(), lo, hi))
        for sector, grp in valid.groupby("sector")
        if len(grp) >= MIN_SECTOR_SAMPLE
    }


# FV-2: a plain mean of `ebitHistory` does *not* survive a single catastrophic
# year — one −20bn writedown drags a 4-year mean negative even when the other
# three years are solidly positive, and EPV then refuses the stock entirely.
# A MAD-based outlier test was tried but is unreliable on the 3–4 point windows
# yfinance gives: for a fast grower it flags the newest (most relevant) year as
# the outlier (review). `_normalised_ebit` now uses an order-statistic estimator
# instead — median at 3 points, a symmetric trimmed mean (drop one from each
# end) at 4+ — which is stable, has no discontinuity, and still removes a lone
# crisis/windfall year. Point-in-time `ebit` below `_EBIT_MIN_YEARS` finite years.
_EBIT_MIN_YEARS = 3


def _normalised_ebit(row: pd.Series):
    """Robust central EBIT across the multi-year window (`ebitHistory`) when at
    least `_EBIT_MIN_YEARS` finite years exist — EPV capitalises a
    through-the-cycle *earnings power*, so neither a single crisis year nor a
    single peak should set the whole valuation. Falls back to the point-in-time
    `ebit` otherwise (recent IPOs, tickers whose statement fetch failed)."""
    hist = row.get("ebitHistory")
    vals = sorted(f for f in ((_finite(v) for v in hist)
                              if isinstance(hist, list) else ()) if f is not None)
    n = len(vals)
    if n < _EBIT_MIN_YEARS:
        return _get_num(row, "ebit")
    if n == 3:
        return vals[1]                       # median of 3 — drops any lone extreme
    trimmed = vals[1:-1]                      # 4+ years: drop one extreme per end
    return sum(trimmed) / len(trimmed)


def _enterprise_value(row: "dict | pd.Series") -> "tuple[float | None, str]":
    """Enterprise value for the EPV model. FV-4: yfinance drops `enterpriseValue`
    on a partial payload while usually still carrying the balance-sheet pieces,
    so fall back to a reconstruction — ``(market cap or Price × shares) +
    totalDebt − totalCash`` — before giving up. Returns ``(ev | None, source)``
    with ``source`` in ``{"provider", "reconstructed", "none"}``; a non-positive
    result is treated as no EV."""
    ev = _finite(row.get("enterpriseValue"))
    if ev is not None and ev > 0:
        return ev, "provider"

    equity = _finite(row.get("marketCap")) or _finite(row.get("Market Cap"))
    if equity is None or equity <= 0:
        price  = _finite(row.get("Price"))
        shares = _finite(row.get("sharesOutstanding"))
        equity = (price * shares
                  if price and shares and price > 0 and shares > 0 else None)

    total_debt = _finite(row.get("totalDebt"))
    if equity is None or total_debt is None:
        return None, "none"
    total_cash = _finite(row.get("totalCash")) or 0.0
    ev = equity + total_debt - total_cash
    return (ev, "reconstructed") if ev > 0 else (None, "none")


def _row_is_scorable(row: "dict | pd.Series") -> bool:
    """True when a fundamentals row carries enough for at least one of the six
    fair-value models below to produce a value — i.e. ``compute_scores`` can give
    it a real ``fair_value`` / ``MoS`` rather than a NaN the rank layer papers
    over with a neutral 50 (``_pct_rank`` / ``_abs_band``).

    Kept deliberately in lock-step with ``_fair_value_models``' per-model input
    guards; if a model's requirements change there, mirror the change here.
    ``bookValue > 0`` alone now counts (FV-3: the P/B fallback values it when no
    trio model fired; a live trio makes the row scorable anyway, so the
    unconditional check here stays in step with the conditional blend). Positive
    ``freeCashflow`` + ``sharesOutstanding`` likewise (FV-3 FCF fallback). The
    DDM branch mirrors
    ``_payout_signal`` + ``_ddm_weight_factor`` (FV-1): a payer is scorable via
    DDM whenever *some* payout proxy — reported ratio, cash payout, or
    1/coverage — lands inside the ramp band, not only when ``payoutRatio`` is
    present. The EPV branch takes ``_enterprise_value`` (FV-4), so a row whose
    ``enterpriseValue`` was dropped but whose balance-sheet pieces survived
    still counts. FV-8's per-sector model skips are *not* mirrored here — a
    ``Real Estate`` / ``Financial Services`` row with ``eps > 0`` still reads as
    scorable (it is, via P/B + DDM + analyst); the worst case is the usual
    tolerated one below. The EBIT branch is deliberately lenient: it accepts a
    multi-year history without re-checking the mean's sign, since a false
    "scorable" only means the row keeps its normal TTL — it still renders "—"
    if the models genuinely can't value it, exactly as today.
    """
    def _num(key):
        v = row.get(key)
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        return v if v == v else None   # NaN -> None

    eps    = _num("trailingEps")
    pe     = _num("trailingPE")
    book   = _num("bookValue")
    ebit   = _num("ebit")
    target = _num("targetMeanPrice")
    div    = _num("trailingAnnualDividendRate") or _num("dividendRate")

    _hist = row.get("ebitHistory")
    have_ebit = (ebit is not None and ebit > 0) or (
        isinstance(_hist, list)
        and len([v for v in _hist if isinstance(v, (int, float)) and v == v]) >= 3
    )

    fcf    = _num("freeCashflow")
    shares = _num("sharesOutstanding")

    return any((
        eps is not None and eps > 0,                                     # Graham, PE fair value
        book is not None and book > 0
            and pe is not None and _PE_DERIVE_BAND[0] < pe < _PE_DERIVE_BAND[1],  # WP-B recovers EPS -> Graham, PE
        ANALYST_INPUTS_ENABLED and target is not None and target > 0,   # analyst target (DATA-6)
        div is not None and div > 0
            and _ddm_weight_factor(div, _payout_signal(row)[0]) > 0,     # DDM (payout ramp must be non-zero)
        have_ebit and _enterprise_value(row)[0] is not None,            # EPV (EV from provider or FV-4 reconstruction)
        book is not None and book > 0,                                  # FV-3 P/B fallback
        fcf is not None and fcf > 0 and shares is not None and shares > 0,  # FV-3 FCF fallback
    ))


def _fair_value_models(row: pd.Series, sector_pe: "dict | None" = None,
                       sector_pb: "dict | None" = None) -> dict:
    price    = row.get("Price")
    eps      = row.get("trailingEps")
    bvps     = row.get("bookValue")
    div_rate = row.get("trailingAnnualDividendRate") or row.get("dividendRate")
    payout, payout_source = _payout_signal(row)   # FV-1: reported / cash / 1-over-coverage
    analyst  = row.get("targetMeanPrice")
    ebit     = _normalised_ebit(row)   # robust mean of ebitHistory (≥3yr) else point-in-time
    ev, ev_source = _enterprise_value(row)   # FV-4: provider EV, else reconstructed from mcap+debt−cash
    beta     = row.get("beta")
    eg       = row.get("earningsGrowth")            # PEG tilt on the PE model
    ddm_g    = _dgr_estimate(row)                   # FV-7: true DPS CAGR, else earningsGrowth
    country  = row.get("country")
    # FV-8 keys off the *resolved* sector (SECTOR_OVERRIDES fills provider gaps for
    # the exact REITs the guard is for — e.g. RET.BR, whose raw sector is often
    # null); `compute_scores` also resolves `df["sector"]` before Stage 2 so the
    # sector-median buckets and this agree (review).
    sector   = sector_for(row.get("Ticker"), row.get("sector"))
    shares   = row.get("sharesOutstanding")
    tax_rate = COUNTRY_TAX_RATES.get(country, DEFAULT_TAX_RATE)

    wacc = _approx_wacc(beta)

    # FV-8: for a NAV-driven sector the earnings-anchored models are skipped
    # (see _GRAHAM_EPV_SKIP_SECTORS / _PE_SKIP_SECTORS) — the row is valued off
    # P/B + DDM + analyst instead.
    _skip_graham_epv = sector in _GRAHAM_EPV_SKIP_SECTORS
    _skip_pe         = sector in _PE_SKIP_SECTORS

    # Per-share input sanity floor (PTB_SANITY_FLOOR): bookValue and trailingEps
    # share the same sharesOutstanding basis for a row, so an implied P/B this
    # far below the market's own price is evidence that basis is broken for
    # the whole row — holds Graham, PE fair value, and the P/B model dark
    # rather than building a number the market price already contradicts by
    # orders of magnitude. See the constant's own comment for the full
    # rationale, including why this is P/B-only, not a symmetric P/E floor.
    _ptb_implausible = bool(price and bvps and bvps > 0
                            and price / bvps < PTB_SANITY_FLOOR)

    # Graham Number
    gn = None
    if eps and bvps and eps > 0 and bvps > 0 and not _skip_graham_epv and not _ptb_implausible:
        gn = (22.5 * eps * bvps) ** 0.5

    # PE Fair Value: sector-median trailing P/E (winsorized to PE_MULTIPLE_BAND)
    # with a bounded PEG tilt on earningsGrowth; PE_MULTIPLE_FALLBACK when the
    # sector has too few priced peers or no sector P/E data was supplied.
    pe_multiple = (sector_pe or {}).get(sector, PE_MULTIPLE_FALLBACK)
    if pd.notna(eg):
        pe_multiple *= float(np.clip(1.0 + eg, *PEG_TILT_BAND))
    pe_fv = (eps * pe_multiple) if (eps and eps > 0 and not _skip_pe and not _ptb_implausible) else None

    # Earnings Power Value (EPV_EV = EBIT×(1-t)/WACC). EBIT is the multi-year mean
    # (_normalised_ebit) when history allows, so a peak/trough year doesn't set the
    # valuation; t is the country's statutory rate (COUNTRY_TAX_RATES), else DEFAULT_TAX_RATE.
    epv = None
    epv_negative = False
    if (ebit and ebit > 0 and ev and ev > 0 and price and price > 0
            and not _skip_graham_epv):
        epv_ev = ebit * (1 - tax_rate) / wacc
        if shares and shares > 0:
            # Exact: subtract net debt (EV − market cap) from EPV_EV, then divide
            # by shares — avoids assuming EPV_EV's implied capital structure mirrors
            # the actual EV/market-cap ratio, which the EV-ratio shortcut below does.
            if ev_source == "reconstructed":
                # `ev` was built as equity + totalDebt − totalCash; take net debt
                # straight from those legs. Using `ev − price·shares` here would
                # inject phantom debt whenever the `marketCap` leg counts share
                # classes that `sharesOutstanding` omits (review).
                net_debt = (_finite(row.get("totalDebt")) or 0.0) - (_finite(row.get("totalCash")) or 0.0)
            else:
                net_debt = ev - (price * shares)
            epv = (epv_ev - net_debt) / shares
        else:
            # Fallback when shares outstanding is unavailable: EV-ratio approximation.
            epv = price * (epv_ev / ev)
        # FV-4: a ≤0 EPV means net debt swamps the capitalised earnings power
        # (common for leveraged names / REITs). It's kept out of the blend by the
        # v > 0 filter below, but the flag lets the UI say *why* the row is dark
        # rather than showing a bare "—".
        epv_negative = bool(epv is not None and epv <= 0)

    # DDM weight ramps with the payout signal (_ddm_weight_factor) rather than a
    # hard 5–90% in/out gate — full base weight in the 30–70% band, tapering to 0
    # by 5% / 95%, so an 89%→91% payer shifts by a sliver, not the whole block.
    # `payout` is _payout_signal's best proxy (FV-1), not the raw reported ratio.
    ddm_factor  = _ddm_weight_factor(div_rate, payout)
    ddm_usable  = ddm_factor > 0
    w_ddm1 = W_DDM_SINGLE * ddm_factor
    w_ddm2 = W_DDM_MULTI  * ddm_factor

    # FV-7: DDM growth is the true DPS CAGR (`_dgr_estimate` → `true_dgr`, else
    # the `earningsGrowth` proxy) — the same figure TER and the dividend scores
    # use — not the raw `earningsGrowth` this passed before.
    ddm1 = _ddm_single(div_rate, wacc, ddm_g)     if ddm_usable else None
    ddm2 = _ddm_multistage(div_rate, wacc, ddm_g) if ddm_usable else None

    # Discount the raw analyst target for its well-documented optimism bias before it
    # feeds the composite (the undiscounted target is still shown elsewhere in the UI),
    # then scale its already-low base weight down further when the sell-side estimates
    # are widely dispersed or thinly covered (_analyst_weight_factor).
    # DATA-6: with ANALYST_INPUTS_ENABLED off the model is dark (weight 0), so the
    # blend renormalises across the remaining models and fv_model_count ignores it.
    analyst_fv = (analyst * (1 - ANALYST_TARGET_HAIRCUT)
                  if analyst and ANALYST_INPUTS_ENABLED else None)
    w_analyst  = W_ANALYST * _analyst_weight_factor(row) if ANALYST_INPUTS_ENABLED else 0.0

    # FV-3: book-value and FCF fallbacks. Eligible only when *none* of the
    # fundamentals trio (Graham / PE / EPV) produced a value — a genuine
    # loss-maker with no earnings anchor, where a crude book/cash number beats a
    # lone haircut analyst target. Even one live trio model (usually EPV) is
    # enough to leave these dark, so a normally-valued name is untouched.
    _trio = sum(1 for v in (gn, pe_fv, epv) if v is not None and v > 0)
    fallback_eligible = _trio == 0

    # FV-8: for a NAV-driven sector the book-value model is a *primary* anchor,
    # not a fallback — so it also fires when the trio is only alive via a kept
    # model (a bank's P/E). REITs still reach it via _trio == 0. (FCF stays a
    # pure loss-maker fallback — a bank's "free cash flow" is not meaningful.)
    pb_eligible = fallback_eligible or _skip_graham_epv

    pb_fv = None
    if pb_eligible and bvps and bvps > 0 and not _ptb_implausible:
        pb_multiple = (sector_pb or {}).get(sector, PB_MULTIPLE_FALLBACK)
        pb_fv = bvps * pb_multiple

    fcf_fv = None
    if fallback_eligible:
        fcf = _finite(row.get("freeCashflow"))
        if fcf and fcf > 0 and shares and shares > 0 and price and price > 0:
            # Capitalise FCF at a fixed multiple, then subtract net debt (like EPV)
            # so a cash-generative but heavily-levered name isn't overvalued.
            gross    = fcf * FCF_MULTIPLE
            net_debt = (ev - price * shares) if (ev and ev > 0) else 0.0
            _v = (gross - net_debt) / shares
            fcf_fv = _v if _v > 0 else None

    # Base weights (DDM scaled by the payout ramp, analyst by dispersion/coverage;
    # W_PB / W_FCF are 0 unless the fallback is eligible and produced a value)
    candidates = [
        (gn,         W_GRAHAM),
        (pe_fv,      W_PE),
        (epv,        W_EPV),
        (ddm1,       w_ddm1),
        (ddm2,       w_ddm2),
        (analyst_fv, w_analyst),
        (pb_fv,      W_PB),
        (fcf_fv,     W_FCF),
    ]
    avail = [(v, w) for v, w in candidates if v is not None and v > 0 and w > 0]
    if not avail:
        return {"graham_number": gn, "pe_fair_value": pe_fv, "epv": epv,
                "ddm": ddm1, "ddm_multistage": ddm2, "fair_value": None,
                "ddm_contributed": False, "fair_value_clamped": False,
                "payout_source": payout_source, "epv_negative": epv_negative,
                "ev_source": ev_source, "fv_model_count": 0,
                "pb_fair_value": pb_fv, "fcf_fair_value": fcf_fv,
                "fv_dark_reasons": _fv_dark_reasons(
                    gn, pe_fv, epv, ddm1, ddm2, analyst_fv,
                    eps=eps, ev=ev, ebit=ebit, div_rate=div_rate, payout=payout,
                    epv_negative=epv_negative, skip_graham_epv=_skip_graham_epv,
                    skip_pe=_skip_pe, ptb_implausible=_ptb_implausible)}

    # FV-5: how many *independent* sub-models back the composite.
    #  • ddm1 + ddm2 are one Gordon family fed identical inputs (the sanity clamp
    #    already collapses them) — count once.
    #  • Graham + PE both key off EPS; when that EPS was reconstructed from the
    #    P/E (trailingEps_derived, WP-B) they are one anchor — count once.
    fv_model_count = len(avail)
    if ddm1 is not None and ddm1 > 0 and ddm2 is not None and ddm2 > 0:
        fv_model_count -= 1
    if (bool(row.get("trailingEps_derived"))
            and gn is not None and gn > 0 and pe_fv is not None and pe_fv > 0):
        fv_model_count -= 1
    fv_model_count = max(fv_model_count, 1)

    total_w = sum(w for _, w in avail)
    iv      = sum(v * w / total_w for v, w in avail)

    # ── Sanity guard (WP-DQ9) ────────────────────────────────────────────────
    # If the blend implies a fair value more than FV_SANITY_MULT× the price but
    # at most one individual model agrees it's that high, one model is running
    # away with the weighted mean — clamp to the models' median, floored at the
    # current price so the clamp itself never manufactures a negative MoS.
    fv_clamped = False
    if price and price > 0 and iv > FV_SANITY_MULT * price:
        model_vals = sorted(v for v, _ in avail)
        thr = FV_SANITY_MULT * price
        # The two DDM variants are one model family fed identical inputs — when
        # they run high they run high together, so they count as a single
        # corroborating vote, not two (otherwise a Gordon-model blow-up can
        # never be caught: ddm1 + ddm2 alone would "agree").
        _ddm_vals = {v for v in (ddm1, ddm2) if v is not None}
        corroborating = sum(1 for v in model_vals
                            if v >= thr and v not in _ddm_vals)
        corroborating += 1 if any(v >= thr for v in _ddm_vals) else 0
        if corroborating <= 1:
            m = len(model_vals)
            median = (model_vals[m // 2] if m % 2
                      else 0.5 * (model_vals[m // 2 - 1] + model_vals[m // 2]))
            capped = max(median, float(price))
            if capped < iv:
                iv = capped
                fv_clamped = True

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
        "pb_fair_value":  round(pb_fv, 2) if pb_fv else None,
        "fcf_fair_value": round(fcf_fv, 2) if fcf_fv else None,
        "fair_value":     round(iv, 2),
        "fv_model_count": fv_model_count,
        "ddm_contributed": ddm_contributed,
        "fair_value_clamped": fv_clamped,
        "payout_source":  payout_source,
        "epv_negative":   epv_negative,
        "ev_source":      ev_source,
        "fv_dark_reasons": _fv_dark_reasons(
            gn, pe_fv, epv, ddm1, ddm2, analyst_fv,
            eps=eps, ev=ev, ebit=ebit, div_rate=div_rate, payout=payout,
            epv_negative=epv_negative, skip_graham_epv=_skip_graham_epv,
            skip_pe=_skip_pe, ptb_implausible=_ptb_implausible),
    }


def _fv_dark_reasons(gn, pe_fv, epv, ddm1, ddm2, analyst_fv, *, eps, ev, ebit,
                     div_rate, payout, epv_negative, skip_graham_epv, skip_pe,
                     ptb_implausible: bool = False) -> dict:
    """FV-6: authoritative {model key -> short 'why dark' code} for the models
    that did not feed the composite. Built alongside the guards in
    `_fair_value_models` so the UI only formats codes — it never re-derives a
    model's input conditions (`uvalu.components._REASON_TEXT` maps the codes)."""
    def _dead(x):
        return not (x is not None and x > 0)

    out: dict = {}
    if _dead(gn):
        out["graham_number"] = ("sector" if skip_graham_epv
                                else "implausible_book" if ptb_implausible
                                else "no_eps" if _dead(eps) else "no_book")
    if _dead(pe_fv):
        out["pe_fair_value"] = ("sector" if skip_pe
                                else "implausible_book" if ptb_implausible
                                else "no_eps")
    if _dead(epv):
        out["epv"] = ("sector" if skip_graham_epv
                      else "epv_negative" if epv_negative
                      else "no_ev" if _dead(ev)
                      else "no_ebit" if ebit is None
                      else "low_ebit")
    if ddm1 is None and ddm2 is None:
        out["ddm"] = ("non_payer" if _dead(div_rate)
                      else "payout_missing" if payout is None
                      else "payout_band" if (payout <= _DDM_PAYOUT_KNOTS[0]
                                             or payout >= _DDM_PAYOUT_KNOTS[3])
                      else "spread")
    if not ANALYST_INPUTS_ENABLED:
        out["analyst"] = "not_licensed"
    elif _dead(analyst_fv):
        out["analyst"] = "no_coverage"
    return out


def _fair_value_model_count(row: "dict | pd.Series") -> int:
    """`_fair_value_models`' own `fv_model_count` for a single row (FV-5). Run
    with no sector context — the sector P/E and P/B medians scale model *values*
    but never change which models produce one, so the count is exact. Used by
    `_fetch_and_store` (which sees a raw row, before `compute_scores`) to spot a
    degraded payload whose fair value would rest on too thin a basis."""
    r = row if isinstance(row, pd.Series) else pd.Series(row)
    return int(_fair_value_models(r).get("fv_model_count", 0))


# ── Stage 3: MoS, TER, Dividend Sustainability Flag ──────────────────────────

def _margin_of_safety(price, fair_value) -> float | None:
    if price and fair_value and fair_value > 0 and price > 0:
        return (fair_value - price) / fair_value
    return None


def signal_reason(row: "pd.Series", *, buy_threshold: float = SCORE_STRONG_BUY,
                  min_mos: float = 0.0) -> str:
    """One-line, stock-specific statement of which model rule produced a row's
    ``signal_code`` (REC-2, REC-5). Replaces screener.decision_reason: it
    reports the rule and the figures, in descriptive terms only — no "BUY",
    no "avoid", nothing addressed to the reader (DIS-6). Mirrors
    ``compute_scores`` Stage 6 exactly. ``min_mos`` is a fraction."""
    code = str(row.get("signal_code") or "")
    _s = row.get("Value Score")
    _m = row.get("margin_of_safety")
    score = None if _s is None or (isinstance(_s, float) and pd.isna(_s)) else float(_s)
    mos   = None if _m is None or (isinstance(_m, float) and pd.isna(_m)) else float(_m)
    thin  = bool(row.get("fv_basis_thin"))
    from uvalu.i18n import _, fmt_num, fmt_pct
    _score_txt = "—" if score is None else fmt_num(score, 0)
    _thr = fmt_num(buy_threshold, 0)

    def _pct(v):
        return fmt_pct(v, 0, fraction=True, signed=True)

    if code == SIGNAL_PENDING:
        return _("No signal: the peer group needed to rank this stock is not available yet.")

    if code == SIGNAL_FAILS:
        return _("Fails the model's quality screen, so its composite score is set to 0.")

    if code == SIGNAL_UNDERVALUED:
        if mos is not None:
            return _("Model score {score} is at or above {threshold}, and the price is {mos} below the "
                     "model fair value (minimum {min_mos}).",
                     score=_score_txt, threshold=_thr, mos=_pct(mos), min_mos=_pct(min_mos))
        return _("Model score {score} is at or above {threshold}.", score=_score_txt, threshold=_thr)

    if code == SIGNAL_LOW_SCORE:
        return _("Model score {score} is below the lower threshold of {floor}.", score=_score_txt,
                 floor=fmt_num(SCORE_AVOID, 0))

    gates = []
    if score is None or score < buy_threshold:
        gates.append(_("model score {score} is below the upper threshold of {threshold}",
                       score=_score_txt, threshold=_thr))
    if mos is None:
        gates.append(_("no model fair value could be computed"))
    elif mos < min_mos:
        gates.append(_("margin of safety {mos} is below the {min_mos} minimum", mos=_pct(mos), min_mos=_pct(min_mos)))
    if thin:
        gates.append(_("the fair value rests on fewer than two independent models"))
    return (_("Neutral: {reasons}.", reasons="; ".join(gates)) if gates
            else _("Model score is between the lower and upper thresholds."))


def _total_expected_return(price, fair_value, div_yield, dgr, ddm_contributed=False) -> float | None:
    """Model-implied return estimate = gap to model fair value % + forward
    dividend yield + assumed DGR (all as %). Same formula as screener.py's TER;
    published as "Implied Return % (est.)" because it is a model estimate, not
    an expected return (REC-2, DIS-5).

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
    """0–10, higher = more liquid. A *confirmed* zero (the ticker genuinely
    hasn't traded — e.g. treasury shares, a dormant secondary listing) is not
    the same as a missing field, and must not share its neutral treatment:
    scored worst-case instead. `vol < 0` shouldn't occur but is treated the
    same as missing rather than crashing the band checks below."""
    vol = _get_num(row, "averageVolume")
    if vol is None or vol < 0:
        return 5.0
    if vol == 0:
        return 0.0
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
    """0–10 composite of growth (and analyst sentiment when licensed, DATA-6)."""
    scores = []
    eg = _get_num(row, "earningsGrowth")
    if eg is not None: scores.append(_clamp(5 + eg * 25, 0, 10))
    rg = _get_num(row, "revenueGrowth")
    if rg is not None: scores.append(_clamp(5 + rg * 25, 0, 10))
    rm = _get_num(row, "recommendationMean") if ANALYST_INPUTS_ENABLED else None
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

@dataclass(frozen=True)
class ScoreReference:
    """The peer-relative inputs of one scored universe: the sector P/E and P/B
    medians behind the fair-value models and, per composite dimension, the
    sorted raw values the percentile ranks are taken against.

    A small frame (the portfolio lane's ~20 holdings) scored with the
    universe's reference gets the same fair values, sub-scores and signals as
    the same rows inside the universe pass; scored on its own it would be
    ranked against the user's holdings instead (WP-3 regression, Oct 2026)."""
    sector_pe: dict
    sector_pb: dict
    dists: dict          # {"mos" | "risk" | "quality" | "momentum" | "dividend": sorted np.ndarray}
    size: int


def _pct_rank(series: pd.Series, ascending=True, dist: "np.ndarray | None" = None) -> pd.Series:
    """Percentile rank 0–100. NaN rows receive 50 (neutral).

    With ``dist`` (a reference universe's sorted values) each value is ranked
    against that universe instead of against ``series`` itself — the same
    average-rank percentile ``Series.rank(pct=True)`` gives a value that is
    part of the universe; a value the universe doesn't hold is ranked as if
    added to it."""
    if dist is None or not len(dist):
        ranked = series.rank(pct=True, na_option="keep") * 100
    else:
        v = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
        lo = np.searchsorted(dist, v, side="left")
        eq = np.searchsorted(dist, v, side="right") - lo
        n = len(dist)
        pct = np.where(eq > 0, (lo + (eq + 1) / 2) / n, (lo + 1) / (n + 1))
        ranked = pd.Series(np.where(np.isnan(v), np.nan, pct * 100), index=series.index)
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


def _blend_ranks(series: pd.Series, band: list, ascending: bool = True,
                 dist: "np.ndarray | None" = None) -> pd.Series:
    """BLEND_PCT × cross-sectional percentile rank + (1 − BLEND_PCT) × absolute
    band — the composite sub-score for one dimension (0–100, higher = better).
    ``dist``: rank against a reference universe (see ScoreReference)."""
    pct = _pct_rank(series, ascending=ascending, dist=dist)
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
            reasons.append(lazy_("revenue fell {years} straight years", years=run + 1))

    ebit = _clean_history(row, "ebitHistory")
    if len(ebit) >= _TREND_MIN_YEARS and all(v < 0 for v in ebit[:_TREND_MIN_YEARS]):
        reasons.append(lazy_("operating income negative {years} years running", years=_TREND_MIN_YEARS))

    ret = _clean_history(row, "retainedEarningsHistory")
    if (len(ret) >= _TREND_MIN_YEARS and ret[0] < 0
            and _declining_run(ret) >= _TREND_DECLINE_RUN):
        reasons.append(lazy_("retained earnings negative and still eroding"))

    last_cut = _get_num(row, "dividend_last_cut_year")
    coverage = _get_num(row, "dividendCoverage")
    if (last_cut is not None and coverage is not None
            and last_cut >= datetime.now(timezone.utc).year - _DIV_CUT_VETO_YEARS
            and coverage < _DIV_CUT_VETO_COVERAGE):
        reasons.append(lazy_("dividend cut in {year} with only {coverage}× cover", year=str(int(last_cut)),
                             coverage=Fmt("num", coverage, decimals=2)))

    return reasons


def compute_scores(df: pd.DataFrame, *, max_debt_equity: float = 500.0,
                   max_payout: float = 0.90, min_mos: float = 0.0,
                   buy_threshold: float = SCORE_STRONG_BUY,
                   weights: "tuple | None" = None,
                   reference: "ScoreReference | None" = None,
                   reference_out: "dict | None" = None,
                   peer_mask: "pd.Series | None" = None,
                   user_selected: bool = False,
                   computed_at: "datetime | None" = None) -> pd.DataFrame:
    # ``reference``: score `df` against another universe's sector medians and
    # rank distributions instead of its own (the portfolio lane passes the
    # scored universe's). ``reference_out``: a dict that receives this pass's
    # own ScoreReference under "ref", for later callers to score against.
    #
    # PER-1 / PER-2 (legal copy):
    # ``peer_mask``: boolean Series aligned to `df` marking the rows of the
    # public universe. Only those rows set the sector medians and the rank
    # distributions; the other rows (a user's manual tickers, holdings on a
    # disabled exchange) are scored *against* the public peers without moving
    # them. screener.py builds the reference from every row it is given, so a
    # user's manual tickers shifted every other stock's percentile ranks — two
    # users could see different signals for the same stock.
    # ``user_selected``: `df` is a set a user picked (holdings, watchlist), not
    # the public universe. Without a ``reference`` its rows are not ranked among
    # themselves (that would make the signal depend on the user's holdings);
    # they get signal_code "pending" instead. Fair values are still computed.
    # ``computed_at``: timestamp stamped on every row (REC-4); defaults to now.
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
        "exDividendDate", "dividendDate", "nextExDividendDate", "dividendFrequency",
        "sector", "fcfHistory",
        "true_dgr", "dgr_1y", "dgr_3y", "dgr_5y",
        "dividend_growth_streak", "dividend_payment_years",
        "dividend_last_cut_year", "dividend_last_increase_year",
        *_STATEMENT_HISTORY_KEYS,
    ]
    # dict.fromkeys dedupes: VALUATION/RISK/QUALITY/MOMENTUM field lists overlap
    # (e.g. currentRatio, freeCashflow appear in two of them), and reindexing with
    # a duplicated name produces a duplicate column — every later row.get(name)
    # then returns a 2-value Series and blows up the scalar guards downstream.
    _missing = [f for f in dict.fromkeys(all_fields) if f not in df.columns]
    df = df.reindex(columns=[*df.columns, *_missing])

    # WP-B: recover a missing trailing EPS from the P/E multiple before the
    # fair-value models run — so a row cached before _fetch_one learned to do
    # this, or borrowed from the other fetch lane (backfill_thin_rows_*), still
    # gets Graham / PE fair value. Same _PE_DERIVE_BAND contract as _fetch_one;
    # Yahoo only publishes a positive P/E, so this only ever yields eps > 0.
    if "trailingEps_derived" not in df.columns:
        df["trailingEps_derived"] = False
    df["trailingEps_derived"] = df["trailingEps_derived"].fillna(False).astype(bool)
    if len(df) and "trailingPE" in df.columns:
        _eps = pd.to_numeric(df["trailingEps"], errors="coerce")
        _pe  = pd.to_numeric(df["trailingPE"], errors="coerce")
        _px  = pd.to_numeric(df["Price"], errors="coerce")
        _derive = _eps.isna() & _pe.gt(_PE_DERIVE_BAND[0]) & _pe.lt(_PE_DERIVE_BAND[1]) & _px.gt(0)
        if _derive.any():
            df.loc[_derive, "trailingEps"] = (_px / _pe).round(4)[_derive]
            df.loc[_derive, "trailingEps_derived"] = True

    # ── Stage 2: fair values ──────────────────────────────────────────────────
    # FV-8 / sector-median buckets key off the resolved sector (SECTOR_OVERRIDES
    # fills provider gaps) — resolve it once here so Stage 2 and the downstream
    # UI never disagree about a ticker's sector (review).
    if "Ticker" in df.columns:
        df["sector"] = [sector_for(t, s) for t, s in zip(df["Ticker"], df["sector"])]
    if peer_mask is not None:
        _peers = peer_mask.reindex(df.index).fillna(False).astype(bool)
    else:
        _peers = pd.Series(True, index=df.index)
    _no_peer_basis = reference is None and (user_selected or not _peers.any())
    if reference is not None:
        sector_pe, sector_pb = reference.sector_pe, reference.sector_pb
    else:
        # universe-relative PE / P/B multiples, from the public peers only (PER-2)
        sector_pe = _sector_pe_medians(df[_peers])
        sector_pb = _sector_pb_medians(df[_peers])
    fv_cols = df.apply(lambda r: _fair_value_models(r, sector_pe=sector_pe,
                                                    sector_pb=sector_pb),
                       axis=1, result_type="expand")
    for col in fv_cols.columns:
        df[col] = fv_cols[col]

    # FV-5: a row that has a fair value but fewer than MIN_FV_MODELS independent
    # sub-models behind it — the composite is real but weakly corroborated.
    _fv_present = pd.to_numeric(df["fair_value"], errors="coerce").notna()
    _cnt        = pd.to_numeric(df["fv_model_count"], errors="coerce")
    df["fv_basis_thin"] = _fv_present & (_cnt < MIN_FV_MODELS)

    # ── Stage 3: MoS · TER · Dividend Sustainability ─────────────────────────
    # Vectorised equivalent of `_margin_of_safety(Price, fair_value)` applied
    # row-wise (the scalar stays for its own callers/tests): (fv − price) / fv
    # where both are finite and > 0, NaN otherwise. `> 0` already excludes
    # NaN/None/≤0, matching the scalar's `price and fv and fv > 0 and price > 0`.
    _mos_price = pd.to_numeric(df["Price"], errors="coerce")
    _mos_fv    = pd.to_numeric(df["fair_value"], errors="coerce")
    df["margin_of_safety"] = (
        (_mos_fv - _mos_price) / _mos_fv
    ).where((_mos_price > 0) & (_mos_fv > 0))
    df["Implied Return % (est.)"] = df.apply(
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
    # collapse, retained-earnings erosion, a recent dividend cut on thin cover) OR a
    # confirmed zero average volume — a ticker that genuinely hasn't traded (treasury
    # shares, a dormant secondary listing) rather than one where volume is simply
    # unreported (`== 0`, not `.fillna(0)`, so a missing field never vetoes).
    de            = df["debtToEquity"].fillna(0)
    coverage      = df["dividendCoverage"].fillna(999)
    leverage_exempt = df["sector"].isin(LEVERAGE_EXEMPT_SECTORS)
    fcf_veto      = df.apply(_fcf_hard_veto, axis=1)
    trend_veto    = df.apply(lambda r: bool(_trend_veto(r)), axis=1)
    no_trade_veto = pd.to_numeric(df["averageVolume"], errors="coerce") == 0
    df["_hard_veto"] = ((de > max_debt_equity) & ~leverage_exempt) | fcf_veto | trend_veto | (
        (df["Div Flag"] == "At Risk") & (coverage < 1.0)
    ) | no_trade_veto

    # ── Stage 5: sub-scores (blend of percentile rank + absolute band) → 0–100 ─
    _raw_cols = {"mos": "margin_of_safety", "risk": "_risk_raw", "quality": "_quality_raw",
                 "momentum": "_momentum_raw", "dividend": "_dividend_raw"}
    _dists = (reference.dists if reference is not None else
              {k: np.sort(pd.to_numeric(df.loc[_peers, c], errors="coerce").dropna().to_numpy(dtype=float))
               for k, c in _raw_cols.items()})
    _peer_size = reference.size if reference is not None else int(_peers.sum())
    if reference_out is not None and not _no_peer_basis:
        reference_out["ref"] = ScoreReference(sector_pe=dict(sector_pe), sector_pb=dict(sector_pb),
                                              dists=_dists, size=_peer_size)
    # Rank against the explicit distribution whenever some rows are not peers;
    # with every row a peer, Series.rank is the same ranking (see _pct_rank).
    _use_dists = reference is not None or not bool(_peers.all())
    _ref_dist = (lambda k: _dists[k]) if _use_dists else (lambda k: None)
    mos_rank      = _blend_ranks(df["margin_of_safety"], _BAND_MOS,  ascending=True,  dist=_ref_dist("mos"))
    risk_rank     = _blend_ranks(df["_risk_raw"],        _BAND_RISK, ascending=False,  # lower raw = safer
                                 dist=_ref_dist("risk"))
    quality_rank  = _blend_ranks(df["_quality_raw"],     _BAND_0_10, ascending=True,  dist=_ref_dist("quality"))
    momentum_rank = _blend_ranks(df["_momentum_raw"],    _BAND_0_10, ascending=True,  dist=_ref_dist("momentum"))
    dividend_rank = _blend_ranks(df["_dividend_raw"],    _BAND_0_10, ascending=True,  dist=_ref_dist("dividend"))

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
    df["small_universe"] = _peer_size < MIN_UNIVERSE_SIZE

    # ── Stage 6: model signal ────────────────────────────────────────────────
    # Legal copy: same rule as screener.py's Decision, published as a
    # descriptive state (BDG-1) — veto → fails_screen (its own state, BDG-3,
    # not folded into the lowest band); score ≥ buy_threshold + confirmed
    # MoS ≥ min_mos + corroborated fair value → undervalued; score ≥
    # SCORE_AVOID → neutral; else low_score. Rows with no public peer basis
    # (PER-1) → pending, with no score: a rank among a user's own holdings is
    # not shown.
    # The screener.py rationale for the gates, unchanged:
    # A BUY requires both the composite score AND the margin of safety to
    # clear their configured thresholds (Settings → Screening & veto rules) —
    # a high score alone no longer overrides an unacceptably thin MoS. A stock
    # with no computable fair value (NaN MoS — every model failed) can't have
    # its margin of safety confirmed, so it can't reach Strong Buy either; it
    # falls through to Monitor/Avoid on score alone instead of bypassing the gate.
    # A `fv_basis_thin` fair value (FV-5: fewer than MIN_FV_MODELS independent
    # sub-models, e.g. a lone book-value fallback) is real but weakly
    # corroborated — deferred at FV-5 ship time as its own Stage 6 change; it
    # gates Strong Buy here rather than joining `_hard_veto`, since a thin basis
    # isn't a red flag on its own, just an unconfirmed one — the row still falls
    # through to Monitor on score.
    # Vectorised equivalent of the former per-row `_decision`: veto → Avoid;
    # else score ≥ buy_threshold with a confirmed MoS ≥ min_mos and a
    # corroborated fair value → Strong Buy; else score ≥ SCORE_AVOID → Monitor;
    # else Avoid. np.select takes the first true branch, and every non-veto
    # branch already excludes veto rows, so the priority matches the if/elif
    # ladder exactly. NaN score compares False everywhere → Avoid, same as the
    # scalar path.
    _dec_veto  = df["_hard_veto"].fillna(False).astype(bool)
    _dec_score = pd.to_numeric(df["Value Score"], errors="coerce")
    _dec_mos   = pd.to_numeric(df["margin_of_safety"], errors="coerce")
    _dec_thin  = df["fv_basis_thin"].fillna(False).astype(bool)
    df["signal_code"] = np.select(
        [
            _dec_veto,
            (~_dec_veto) & (_dec_score >= buy_threshold) & _dec_mos.notna()
                & (_dec_mos >= min_mos) & ~_dec_thin,
            (~_dec_veto) & (_dec_score >= SCORE_AVOID),
        ],
        [SIGNAL_FAILS, SIGNAL_UNDERVALUED, SIGNAL_NEUTRAL],
        default=SIGNAL_LOW_SCORE,
    )
    if _no_peer_basis:
        # PER-1: the vetoes are absolute rules on the stock's own data, so a
        # failed screen still shows; everything rank-based is withheld.
        _pending = ~_dec_veto
        df.loc[_pending, "signal_code"] = SIGNAL_PENDING
        for _c in ("Value Score", "Sub MoS", "Sub Risk", "Sub Quality", "Sub Momentum", "Sub Dividend"):
            df.loc[_pending, _c] = np.nan
    df["Signal"] = df["signal_code"].map(SIGNAL_LABELS)
    df["Risk Score"] = df["_risk_raw"].round(1)
    df["MoS %"]      = (df["margin_of_safety"] * 100).round(1)

    # Expose the veto flag publicly before dropping internal-only columns
    df["veto"] = df["_hard_veto"]

    # ── Provenance (REC-3, REC-4, REC-11) ────────────────────────────────────
    _now = computed_at or datetime.now(timezone.utc)
    df["signal_computed_at"] = _now.isoformat(timespec="seconds")
    # A plain list, not df.apply: apply would coerce the datetimes to
    # datetime64 and turn a missing timestamp into NaT, which `is None` misses.
    _fetched = [_row_fetch_time({"fetched_at": v})
                for v in (df["fetched_at"] if "fetched_at" in df.columns else [None] * len(df))]
    df["price_as_of"] = [
        (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).isoformat(timespec="seconds")
        if t is not None else None
        for t in _fetched
    ]
    df["data_source"]       = DATA_SOURCE
    df["model_version"]     = MODEL_VERSION
    df["model_settings_id"] = model_settings_id(
        max_debt_equity=max_debt_equity, max_payout=max_payout, min_mos=min_mos,
        buy_threshold=buy_threshold,
        weights=(w_mos, w_risk, w_quality, w_momentum, w_dividend))
    _stale_before = _now - timedelta(hours=PRICE_STALE_HOURS)
    _flag_cols = {
        "price_missing_timestamp": [t is None for t in _fetched],
        "price_stale": [t is not None and (t if t.tzinfo else t.replace(tzinfo=timezone.utc)) < _stale_before
                        for t in _fetched],
        "fair_value_missing": df["fair_value"].isna().tolist(),
        "fair_value_thin_basis": df["fv_basis_thin"].fillna(False).astype(bool).tolist(),
        "fair_value_clamped": df["fair_value_clamped"].fillna(False).astype(bool).tolist(),
        "eps_derived_from_pe": df["trailingEps_derived"].fillna(False).astype(bool).tolist(),
        "small_peer_group": df["small_universe"].astype(bool).tolist(),
    }
    df["data_flags"] = [
        [name for name, vals in _flag_cols.items() if vals[i]] for i in range(len(df))
    ]

    # Drop internal columns
    df = df.drop(columns=[c for c in df.columns if c.startswith("_")])
    df = df.sort_values("Value Score", ascending=False).reset_index(drop=True)
    df.index += 1
    return df



def run_screener_from_df(df: pd.DataFrame, *, max_debt_equity: float = 500.0,
                         max_payout: float = 0.90, min_mos: float = 0.0,
                         buy_threshold: float = SCORE_STRONG_BUY,
                         weights: "tuple | None" = None,
                         reference: "ScoreReference | None" = None,
                         reference_out: "dict | None" = None,
                         peer_mask: "pd.Series | None" = None,
                         user_selected: bool = False) -> pd.DataFrame:
    """Score and clean a DataFrame that was already fetched (avoids re-fetching).
    ``reference`` / ``reference_out`` / ``peer_mask`` / ``user_selected``: see
    compute_scores."""
    return _score_and_clean(df.copy(), max_debt_equity=max_debt_equity,
                            max_payout=max_payout, min_mos=min_mos,
                            buy_threshold=buy_threshold, weights=weights,
                            reference=reference, reference_out=reference_out,
                            peer_mask=peer_mask, user_selected=user_selected)


def _score_and_clean(df: pd.DataFrame, *, max_debt_equity: float = 500.0,
                     max_payout: float = 0.90, min_mos: float = 0.0,
                     buy_threshold: float = SCORE_STRONG_BUY,
                     weights: "tuple | None" = None,
                     reference: "ScoreReference | None" = None,
                     reference_out: "dict | None" = None,
                     peer_mask: "pd.Series | None" = None,
                     user_selected: bool = False) -> pd.DataFrame:
    if "Price" not in df.columns:
        df["Price"] = None
    before  = len(df)
    _keep   = df["Price"].notna()
    if peer_mask is not None:   # keep it aligned with the rows that survive
        peer_mask = peer_mask.reindex(df.index).fillna(False).astype(bool)[_keep].reset_index(drop=True)
    df      = df[_keep].reset_index(drop=True)
    dropped = before - len(df)
    if dropped:
        _log.debug("dropped %d ticker(s) with no price (likely delisted/inactive)", dropped,
                   extra={"event": "score.clean", "dropped": dropped})
    if df.empty:
        return df
    _log.debug("computing valuation scores for %d rows", len(df),
               extra={"event": "score.compute", "rows": len(df)})
    return compute_scores(df, max_debt_equity=max_debt_equity, max_payout=max_payout,
                          min_mos=min_mos, buy_threshold=buy_threshold, weights=weights,
                          reference=reference, reference_out=reference_out,
                          peer_mask=peer_mask, user_selected=user_selected)


# ── Legal-compliance helpers ──────────────────────────────────────────────────

def peer_mask_for(df: pd.DataFrame, public_tickers) -> pd.Series:
    """PER-2: the ``peer_mask`` for `df` — True for rows whose Ticker is in the
    public universe (the enabled exchanges' ticker lists, a shared setting),
    False for user-added rows (manual tickers, holdings on a disabled exchange)."""
    public = set(public_tickers)
    if "Ticker" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["Ticker"].isin(public)


def model_settings_id(*, max_debt_equity: float, max_payout: float, min_mos: float,
                      buy_threshold: float, weights: tuple) -> str:
    """REC-11: short stable id of the shared model settings a signal was computed
    with, so a logged signal can be matched to the exact settings behind it."""
    import hashlib
    payload = json.dumps({
        "max_debt_equity": round(float(max_debt_equity), 6),
        "max_payout": round(float(max_payout), 6),
        "min_mos": round(float(min_mos), 6),
        "buy_threshold": round(float(buy_threshold), 6),
        "weights": [round(float(w), 6) for w in weights],
        "analyst_inputs": ANALYST_INPUTS_ENABLED,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def methodology(*, max_debt_equity: float = 500.0, max_payout: float = 0.90,
                min_mos: float = 0.0, buy_threshold: float = SCORE_STRONG_BUY,
                weights: "tuple | None" = None) -> dict:
    """REC-5 / REC-6 / PER-8: everything the methodology page must publish, read
    from the live constants and the active shared settings, so the page states
    the thresholds the code actually applies. Pass the same arguments as
    compute_scores (settings.get_veto_thresholds / get_score_weights)."""
    w = weights if weights is not None else (W_MOS, W_RISK, W_QUALITY, W_MOMENTUM, W_DIVIDEND)
    models = {
        "graham_number": W_GRAHAM, "pe_fair_value": W_PE, "epv": W_EPV,
        "ddm_single": W_DDM_SINGLE, "ddm_multistage": W_DDM_MULTI,
        "book_value_fallback": W_PB, "fcf_fallback": W_FCF,
    }
    if ANALYST_INPUTS_ENABLED:
        models["analyst_target"] = W_ANALYST
    return {
        "model_version": MODEL_VERSION,
        "model_settings_id": model_settings_id(max_debt_equity=max_debt_equity, max_payout=max_payout,
                                               min_mos=min_mos, buy_threshold=buy_threshold, weights=w),
        "data_source": DATA_SOURCE,
        "update_frequency_hours": {"fundamentals": CACHE_TTL_HOURS,
                                   "fundamentals_jitter": CACHE_TTL_JITTER},
        "fair_value": {
            "model_base_weights": models,
            "min_independent_models": MIN_FV_MODELS,
            "risk_free_rate": RISK_FREE_RATE,
            "equity_risk_premium": EQUITY_RISK_PREMIUM,
            "ddm_stable_growth": DDM_STABLE_GROWTH,
            "pe_multiple_fallback": PE_MULTIPLE_FALLBACK,
            "pe_multiple_band": PE_MULTIPLE_BAND,
            "fcf_multiple": FCF_MULTIPLE,
            "sanity_multiple": FV_SANITY_MULT,
            "analyst_inputs": ANALYST_INPUTS_ENABLED,
        },
        "composite_weights": dict(zip(("margin_of_safety", "risk", "quality", "momentum", "dividend"), w)),
        "rank_blend": {"percentile_share": BLEND_PCT, "absolute_share": 1.0 - BLEND_PCT},
        "thresholds": {
            "undervalued_min_score": float(buy_threshold),
            "undervalued_min_margin_of_safety": float(min_mos),
            "low_score_below": float(SCORE_AVOID),
            "min_peer_group": MIN_UNIVERSE_SIZE,
        },
        "quality_screen": {
            "max_debt_equity_pct": float(max_debt_equity),
            "leverage_exempt_sectors": sorted(LEVERAGE_EXEMPT_SECTORS),
            "negative_fcf_years": 3,
            "dividend_at_risk_payout_above": float(max_payout),
            "dividend_at_risk_cover_below": 1.0,
            "revenue_decline_years": _TREND_DECLINE_RUN + 1,
            "negative_operating_income_years": _TREND_MIN_YEARS,
            "dividend_cut_within_years": _DIV_CUT_VETO_YEARS,
            "dividend_cut_cover_below": _DIV_CUT_VETO_COVERAGE,
            "zero_average_volume": True,
        },
        "signals": {code: {"label": SIGNAL_LABELS[code], "definition": SIGNAL_DEFINITIONS[code]}
                    for code in SIGNAL_LABELS},
        "tooltip": SIGNAL_TOOLTIP,
        "horizon": SIGNAL_HORIZON,
        "risk_warning": SIGNAL_RISK_WARNING,
        "sensitivity": SIGNAL_SENSITIVITY,
        "price_stale_after_hours": PRICE_STALE_HOURS,
    }


def signal_distribution(df: pd.DataFrame) -> dict[str, float]:
    """REC-10: share of covered stocks per signal state (fractions summing to 1
    over the rows that have a signal; "pending" rows are left out)."""
    if df is None or df.empty or "signal_code" not in df.columns:
        return {}
    codes = df.loc[df["signal_code"] != SIGNAL_PENDING, "signal_code"]
    if codes.empty:
        return {}
    shares = codes.value_counts(normalize=True)
    return {code: float(shares.get(code, 0.0))
            for code in (SIGNAL_UNDERVALUED, SIGNAL_NEUTRAL, SIGNAL_LOW_SCORE, SIGNAL_FAILS)}


# The inputs a signal can be reproduced from (REC-11), next to its outputs.
SIGNAL_RECORD_FIELDS = (
    "Ticker", "signal_code", "Value Score", "Price", "price_as_of", "fair_value",
    "margin_of_safety", "fv_model_count", "fv_basis_thin", "veto",
    "Sub MoS", "Sub Risk", "Sub Quality", "Sub Momentum", "Sub Dividend",
    "graham_number", "pe_fair_value", "epv", "ddm", "ddm_multistage",
    "pb_fair_value", "fcf_fair_value", "data_flags",
    "signal_computed_at", "model_version", "model_settings_id",
)


def signal_records(df: pd.DataFrame) -> list[dict]:
    """REC-7 / REC-11: one JSON-safe record per scored row with the signal, the
    inputs and fair values behind it, and the model version/settings — for an
    append-only signal log (see signal_history.py). NaN becomes None."""
    if df is None or df.empty:
        return []
    cols = [c for c in SIGNAL_RECORD_FIELDS if c in df.columns]
    out = []
    for rec in df[cols].to_dict(orient="records"):
        clean = {}
        for k, v in rec.items():
            if isinstance(v, (list, tuple)):
                clean[k] = list(v)
            elif v is None or (isinstance(v, float) and math.isnan(v)):
                clean[k] = None
            elif isinstance(v, (np.bool_, bool)):
                clean[k] = bool(v)
            elif isinstance(v, (np.integer, np.floating)):
                clean[k] = v.item()
            else:
                clean[k] = v
        out.append(clean)
    return out
