"""
Stock valuation screener — implements the 6-stage algorithm from docs/stock_valuation_algorithm.md

Stage 1  — Data collection (yfinance, cached)
Stage 2  — Fair value: Graham Number · PE Fair Value · EPV · DDM (single + multi-stage)
           · Analyst only when ANALYST_INPUTS_ENABLED (licensed data, DATA-6)
Stage 3  — Margin of Safety + model-implied return (estimate) + Dividend Sustainability Flag
Stage 4  — Risk scoring: financial health · earnings quality · market risk · dividend risk · liquidity
Stage 5  — Composite Score = α×MoS + β×(100−Risk) + γ×Quality + δ×Momentum + ε×DividendScore
Stage 6  — Model signal (descriptive): Undervalued | Mid score | Low score |
           Screened out | No signal

Caching: fundamentals stored in .cache/fundamentals.json, re-fetched after CACHE_TTL_HOURS.

Legal design rules (docs/legal/compliance-implementation-plan.md,
docs/legal/algorithm-compliance-review.md), by requirement ID of
"Uvalu — Legal Requirements for Launch":
  PER-1/2  Peer reference (sector medians, percentile ranks) is built from the
           public universe only (``peer_mask``); a user-selected set (holdings,
           watchlist) scored without one gets no signal (``user_selected``), and
           its P/E and P/B fair values use the fixed fallback multiples, not
           medians of the user's own holdings.
  BDG-1/3  Descriptive signal labels; a failed quality screen is its own state.
  REC-2    Model outputs are named as estimates ("Implied Return % (est.)");
           ``signal_reason`` states the rule applied, including which quality
           rules failed (``veto_rules``).
  REC-3    ``data_source`` and ``data_flags`` (stale price, thin basis, derived
           EPS, clamped fair value, small peer group) on every row.
  REC-4    ``signal_computed_at`` and ``price_as_of`` on every row.
  REC-5/6  ``methodology()`` and ``SIGNAL_DEFINITIONS`` read the live constants,
           so the methodology page cannot drift from the code.
  REC-8    ``founder_holds`` flag + FOUNDER_HOLDS_NOTICE for any founder position.
  REC-10   ``signal_distribution()``.
  REC-11   ``model_version`` + ``model_settings_id`` per row; ``signal_records()``.
  DATA-6   Analyst price targets and recommendation means are off by default:
           not fetched, not used, not in the output (``strip_analyst_fields``).
"""

import contextlib
import io
import json
import logging
import math
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
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
MODEL_VERSION = "M4"   # D12: independent of the app version; shown in the UI and the methodology change log

# D1: "Undervalued" needs at least this margin of safety, whatever the shared
# `min_mos` setting says. At 0% a price 0.5% below the model fair value would
# carry a valuation label the model can't support (REC-2, WER VI.97).
MIN_MOS_FLOOR = 0.10

# REC-3 / DATA-4: where the inputs come from, as shown to users. The free beta
# runs on Yahoo Finance, which is not licensed for a commercial service
# (decision B2: free, invite-only beta with mitigations). Replace with the
# licensed provider's name and required attribution wording once DATA-2 is
# signed (M2).
DATA_SOURCE = "Yahoo Finance (delayed quotes, via yfinance)"

# DATA-6: analyst price targets (targetMeanPrice/High/Low, numberOfAnalystOpinions)
# and the consensus recommendation mean are sell-side content licensed separately
# from prices and fundamentals. Off until a licence covers them; with it off the
# analyst model drops out of the fair-value blend (its weight renormalises across
# the remaining models) and momentum uses earnings + revenue growth only.
ANALYST_INPUTS_ENABLED = False

# The sell-side fields covered by that switch. With it off, compute_scores
# drops them from its output so no table, drawer or export can show them, and
# strip_analyst_fields() removes them from raw fundamentals rows. Stage 1
# (screener.py) still fetches and caches them until the wiring step removes
# them from its field lists (docs/legal/algorithm-compliance-review.md §4).
ANALYST_FIELDS = ("targetMeanPrice", "targetHighPrice", "targetLowPrice",
                  "numberOfAnalystOpinions", "recommendationMean")

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
# the score. The middle band was "Neutral" until 12 Oct 2026: that reads like a
# sell-side rating (Overweight / Neutral / Underweight), so it became "Mid score"
# (L12, docs/legal/signal-label-review.md). Likewise "Fails quality screen"
# became "Screened out" ("quality" is an evaluative word). The codes stay
# "neutral" / "fails_screen" so the signal history keeps one key per band.
SIGNAL_UNDERVALUED = "undervalued"
SIGNAL_NEUTRAL     = "neutral"
SIGNAL_LOW_SCORE   = "low_score"
SIGNAL_FAILS       = "fails_screen"
SIGNAL_PENDING     = "pending"

SIGNAL_LABELS = {
    SIGNAL_UNDERVALUED: N_("Undervalued"),
    # Translators: model signal badge for the middle band of the composite score (40 to below 70). Describes the score, not the stock; pairs with "Low score". Avoid words that read like an analyst rating (Neutral, Hold).
    SIGNAL_NEUTRAL:     N_("Mid score"),
    SIGNAL_LOW_SCORE:   N_("Low score"),
    # Translators: model signal badge for a stock excluded by one of the quality-screen rules (debt, cash flow, dividend cover, multi-year decline, no trading). Neutral, factual wording.
    SIGNAL_FAILS:       N_("Screened out"),
    SIGNAL_PENDING:     N_("No signal"),
}

# BDG-2: tooltip on every badge, plus the methodology link (the page renders it).
SIGNAL_TOOLTIP = N_("Model output based on public data and the settings shown. "
                    "Not a recommendation tailored to you.")

# REC-6: what each state means, the horizon the model assumes, and the risk
# warning. Thresholds are filled in from the live settings by methodology().
SIGNAL_HORIZON = N_("The models value a business on its current fundamentals and "
                    "assume a holding horizon of 3 to 5 years; they say nothing "
                    "about short-term price moves.")
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

# REC-2 / BDG-3: which quality rule a "Screened out" row tripped. The
# code is stored in `veto_rules` and logged (REC-11); the label is shown.
VETO_RULE_DEBT_EQUITY      = "debt_to_equity"
VETO_RULE_NEGATIVE_FCF     = "negative_fcf"
VETO_RULE_DIVIDEND_AT_RISK = "dividend_at_risk"
VETO_RULE_REVENUE_DECLINE  = "revenue_decline"
VETO_RULE_NEGATIVE_EBIT    = "negative_operating_income"
VETO_RULE_RETAINED_EROSION = "retained_earnings_erosion"
VETO_RULE_DIVIDEND_CUT     = "dividend_cut_thin_cover"
VETO_RULE_NO_VOLUME        = "no_trading_volume"

VETO_RULE_LABELS = {
    VETO_RULE_DEBT_EQUITY:      N_("debt-to-equity above the maximum"),
    VETO_RULE_NEGATIVE_FCF:     N_("negative free cash flow"),
    VETO_RULE_DIVIDEND_AT_RISK: N_("dividend flagged at risk with earnings cover below 1.0"),
    VETO_RULE_REVENUE_DECLINE:  N_("multi-year revenue decline"),
    VETO_RULE_NEGATIVE_EBIT:    N_("operating income negative for several years"),
    VETO_RULE_RETAINED_EROSION: N_("negative and eroding retained earnings"),
    VETO_RULE_DIVIDEND_CUT:     N_("recent dividend cut with thin cover"),
    VETO_RULE_NO_VOLUME:        N_("no trading volume"),
}

# REC-8 / MAR Delegated Regulation 2016/958 art. 5: shown on the stock page,
# and with the badge, whenever the founder holds a position in the stock, at
# any size. Positions come from FOUNDER_HOLDINGS_FILE (load_founder_holdings).
FOUNDER_HOLDS_NOTICE = N_("Disclosure: the founder of Uvalu holds a position in this stock. "
                          "Its signal is calculated exactly like every other stock's.")
FOUNDER_HOLDINGS_FILE = Path(__file__).parent / "data" / "compliance" / "founder_holdings.json"

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

MAX_WORKERS      = 4    # parallel yfinance requests
REQUEST_DELAY    = 0.5  # seconds between requests per worker
MAX_RETRIES      = 4    # retries on rate-limit (429), with exponential backoff
CACHE_TTL_HOURS  = 24   # base TTL; actual refresh is jittered ±4h per ticker
CACHE_TTL_JITTER = 4    # hours of random jitter added to each ticker's TTL

# WP-A: a row that fetched with a price but came back too thin to value (see
# _row_is_scorable — a partial Yahoo payload that raised no exception) is still
# cached so the holding keeps a price and a score, but on this much shorter TTL,
# so it heals on the next fetch cycle instead of being trusted for a full day.
# A couple of immediate in-loop retries come first, since such payloads are
# usually transient. FV-5 widens the "too thin" test a little: a row that is
# technically scorable but only via a *reconstructed* EPS (Graham + PE off one
# guessed number, < MIN_FV_MODELS models total) is a degraded payload too, and
# gets the same short-TTL heal. `fv_model_count` / `fv_basis_thin` (a superset —
# also flags a lone analyst target) are surfaced for the UI but do NOT force the
# short TTL, so a genuinely data-poor small-cap isn't re-fetched forever.
CACHE_TTL_SHORT_HOURS = 3
_THIN_ROW_RETRIES     = 2
MIN_FV_MODELS         = 2

# EX-W1 (exchange expansion plan, D29 / EX-19 / EX-20): rows that stay thin or
# dead are fetched less and less often, and a rate limit pauses every worker.
# On 16 Oct 2026 992 of 4,059 priced rows sat on the 3-hour short TTL (about 8
# fetches a day each, for companies that are simply data-poor) and about 4,100
# rows with no price and no country (symbols Yahoo doesn't know, mostly
# Frankfurt) were fetched every day.
THIN_TTL_STEPS_HOURS = (3, 12)          # 1st and 2nd thin result in a row; then the normal TTL
DEAD_BACKOFF_DAYS    = (1, 2, 4, 8, 16, 30)   # no price and no country, n times in a row
CACHE_PRUNE_DAYS     = 30               # a row in no list and no portfolio this long is removed


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
        self.warm_lock  = threading.Lock()           # serialises the cold-start disk parse
        self.row_lock   = threading.Lock()           # guards live_cache dict + done counter
        self.state: dict = {"done": 0, "total": 0, "running": False}
        self.state_lock = threading.Lock()


# EX-20: one cool-down shared by every fetch worker in both lanes. When any
# worker is rate-limited, all of them pause until it ends, instead of the
# other workers carrying on hitting Yahoo. In memory: it coordinates the
# threads of this one process (one Streamlit process per deployment).
_cooldown_lock  = threading.Lock()
_cooldown_until = 0.0     # time.monotonic() deadline


def _start_cooldown(seconds: float) -> None:
    global _cooldown_until
    with _cooldown_lock:
        until = time.monotonic() + seconds
        if until > _cooldown_until:
            _cooldown_until = until
            _log.info("rate limited: pausing all fetch workers for %.0f s", seconds,
                            extra={"event": "fetch.cooldown", "seconds": round(seconds, 1)})


def _wait_for_cooldown(cancelled: "threading.Event | None" = None) -> None:
    """Block until the shared cool-down is over (or the fetch is cancelled)."""
    while True:
        with _cooldown_lock:
            left = _cooldown_until - time.monotonic()
        if left <= 0 or (cancelled is not None and cancelled.is_set()):
            return
        time.sleep(min(left, 1.0))


SCREENER_FETCH  = _Fetcher(Path(__file__).parent / ".cache" / "fundamentals.json")
PORTFOLIO_FETCH = _Fetcher(Path(__file__).parent / ".cache" / "portfolio_fundamentals.json")

# ── Fields fetched from yfinance ──────────────────────────────────────────────

VALUATION_FIELDS = [
    "trailingEps",                  # Graham Number, PE fair value
    "bookValue",                    # Graham Number (BVPS)
    "trailingAnnualDividendRate",   # DDM single-stage
    "dividendRate",                 # Forward DPS (multi-stage DDM)
    "fiveYearAvgDividendYield",     # Yield vs historical average
    "ebit",                         # EPV
    "enterpriseValue",              # EPV: EV → per-share scaling
    "totalDebt",                    # EPV: EV reconstruction when enterpriseValue is dropped (FV-4)
    "totalCash",                    # EPV: EV reconstruction (FV-4)
    "marketCap",                    # EPV: EV reconstruction — equity leg (FV-4)
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
]

# DATA-6: the sell-side ANALYST_FIELDS (price targets, analyst count,
# consensus rating) are fetched only while a licence covers them.
ALL_EXTRA_FIELDS = list({
    *VALUATION_FIELDS, *RISK_FIELDS, *QUALITY_FIELDS, *MOMENTUM_FIELDS,
    *(ANALYST_FIELDS if ANALYST_INPUTS_ENABLED else ()),
})

# ── Cache helpers ─────────────────────────────────────────────────────────────

def _load_cache(fetcher: "_Fetcher | None" = None) -> dict:
    f = fetcher or SCREENER_FETCH
    if f.cache_file.exists():
        try:
            # strip_analyst_fields: rows cached before DATA-6 still carry the
            # analyst fields; they leave the cache on its next save.
            return strip_analyst_fields(json.loads(f.cache_file.read_text(encoding="utf-8")))
        except Exception:
            pass
    return {}


def _save_cache(cache: dict, fetcher: "_Fetcher | None" = None) -> None:
    """Atomic write (EX-W1, D28): written to a temporary file and moved into
    place, so a crash or restart mid-write can't leave a truncated file, which
    _load_cache would read as empty and trigger a refetch of everything. No
    indent: a third smaller and faster to parse."""
    f = fetcher or SCREENER_FETCH
    f.cache_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.cache_file.with_name(f.cache_file.name + ".tmp")
    tmp.write_text(json.dumps(cache), encoding="utf-8")
    for attempt in range(5):
        try:
            os.replace(tmp, f.cache_file)
            return
        except PermissionError:      # Windows: a reader has the file open for a moment
            if attempt == 4:
                raise
            time.sleep(0.2)


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


def _row_fetch_time(row: "dict | pd.Series"):
    """A fundamentals row's ``fetched_at`` as a datetime, or None if absent/bad."""
    ts = row.get("fetched_at")
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return None


def backfill_thin_rows_from_screener_lane(fund: "pd.DataFrame") -> "pd.DataFrame":
    """WP-C: swap in the SCREENER_FETCH lane's row for any PORTFOLIO_FETCH-lane
    row that can't be valued, *or* whose fair value would rest on fewer than
    MIN_FV_MODELS independent sub-models (review: a book-value-only degraded
    payload is now technically ``_row_is_scorable`` but still thin, and would
    otherwise show a lone ``bookValue × PB_MULTIPLE_FALLBACK`` composite on the
    portfolio screens while the Screener page shows a full one).

    A degraded provider payload cached in the portfolio lane is otherwise sticky
    until its (WP-A short) TTL expires, even when the screener lane already holds
    a complete row for the same ticker. Both lanes run the identical scorer on
    the identical row schema, so borrowing a not-older row with *more* live
    models is a no-op for correctness and an immediate heal. Tickers the screener
    lane doesn't have (held on a disabled exchange) are left untouched.
    """
    if fund is None or getattr(fund, "empty", True) or "Ticker" not in getattr(fund, "columns", []):
        return fund
    records = fund.to_dict("records")
    thin = [i for i, r in enumerate(records)
            if not _row_is_scorable(r) or _fair_value_model_count(r) < MIN_FV_MODELS]
    if not thin:
        return fund
    _warm_live_cache(SCREENER_FETCH)
    alt_cache = SCREENER_FETCH.live_cache
    changed = False
    for i in thin:
        r = records[i]
        alt = alt_cache.get(str(r.get("Ticker")))
        if not alt or not _row_is_scorable(alt):
            continue
        if _fair_value_model_count(alt) <= _fair_value_model_count(r):
            continue   # the other lane isn't actually richer — don't churn the row
        _rt, _at = _row_fetch_time(r), _row_fetch_time(alt)
        if _rt is not None and _at is not None and _at < _rt:
            continue   # don't trade a newer-but-thin row for a stale one
        records[i] = {**r, **alt}   # alt wins on shared keys; portfolio-only keys survive
        changed = True
    return pd.DataFrame(records) if changed else fund


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


# Q1 (model M2): a partial or failed fetch must not change a signal. The
# statement histories behind the trend vetoes are sometimes missing from one
# fetch and back in the next, which toggled vetoes within minutes
# (docs/quant-review.md Q1); a failed fetch replaced a good row with an empty
# stub, dropping the stock until the next success.
_CARRY_FORWARD_FIELDS = ("fcfHistory", "revenueHistory", "ebitHistory", "netIncomeHistory",
                         "cfoHistory", "retainedEarningsHistory", "totalAssetsHistory",
                         "dividend_last_cut_year", "financialCurrency", "country", "sector")
_CARRY_FORWARD_MAX_DAYS = 90   # annual statement data; older than this isn't trusted
_KEEP_ON_FAILURE_DAYS = 7      # a failed fetch keeps the last good row this long


def _carry_forward(row: dict, previous: "dict | None") -> dict:
    """`row` with what a partial or failed fetch lost taken from `previous`,
    the ticker's last cached row.

    - A failed fetch (no ``fetched_at``) keeps the previous good row if it's
      at most _KEEP_ON_FAILURE_DAYS old, with a short retry.
    - A successful fetch missing a field in _CARRY_FORWARD_FIELDS takes the
      previous value if that row is at most _CARRY_FORWARD_MAX_DAYS old.
      The fields taken are listed in ``carried_forward``."""
    if not previous or not previous.get("fetched_at"):
        return row
    prev_at = _row_fetch_time(previous)
    if prev_at is None:
        return row
    if prev_at.tzinfo is None:
        prev_at = prev_at.replace(tzinfo=timezone.utc)
    if not row.get("fetched_at"):
        if datetime.now(timezone.utc) - prev_at <= timedelta(days=_KEEP_ON_FAILURE_DAYS):
            return {**previous, "next_fetch_at": _next_fetch_at(short=True)}
        return row
    # Each carried value remembers when it was last really fetched, so a
    # chain of partial fetches can't keep it alive past the limit.
    prev_since = previous.get("carried_since") or {}
    now = datetime.now(timezone.utc)
    carried, since = [], {}
    for f in _CARRY_FORWARD_FIELDS:
        if row.get(f) not in (None, [], "") or previous.get(f) in (None, [], ""):
            continue
        origin = prev_since.get(f) or previous["fetched_at"]
        try:
            origin_dt = datetime.fromisoformat(str(origin))
        except (TypeError, ValueError):
            continue
        if origin_dt.tzinfo is None:
            origin_dt = origin_dt.replace(tzinfo=timezone.utc)
        if now - origin_dt > timedelta(days=_CARRY_FORWARD_MAX_DAYS):
            continue
        carried.append(f)
        since[f] = origin_dt.isoformat()
    if not carried:
        return row
    return {**row, **{f: previous[f] for f in carried},
            "carried_forward": carried, "carried_since": since}


def _next_fetch_at(short: bool = False) -> str:
    """Random refresh time: base TTL ± jitter, so fetches spread across the day.

    ``short=True`` uses ``CACHE_TTL_SHORT_HOURS`` with a proportionally smaller
    jitter — for a row that fetched but came back unscorable, so it is retried
    soon rather than trusted for a day (WP-A).
    """
    if short:
        base, jitter = CACHE_TTL_SHORT_HOURS, random.uniform(-1.0, 1.0)
    else:
        base, jitter = CACHE_TTL_HOURS, random.uniform(-CACHE_TTL_JITTER, CACHE_TTL_JITTER)
    return (datetime.now(timezone.utc) + timedelta(hours=base + jitter)).isoformat()


def _apply_refetch_schedule(row: dict, previous: "dict | None") -> dict:
    """When a row is fetched next, by what it came back as (EX-W1):

    - **Dead** (no price and no country: a symbol Yahoo doesn't know, or a
      not-found): retried after 1, 2, 4, 8, 16, then every 30 days
      (`dead_streak`). Back to the normal TTL as soon as a fetch returns a price.
    - **Thin** (priced but too thin to value, flagged `_thin` by the fetch
      loop): 3 h, then 12 h, then the normal TTL while it stays thin
      (`thin_streak`). A full row resets it.
    """
    previous = previous or {}
    row = dict(row)
    is_thin = bool(row.pop("_thin", False))
    if row.get("Price") is None and not row.get("country"):
        streak = int(previous.get("dead_streak") or 0) + 1
        days = DEAD_BACKOFF_DAYS[min(streak, len(DEAD_BACKOFF_DAYS)) - 1]
        row["dead_streak"] = streak
        row["next_fetch_at"] = (datetime.now(timezone.utc)
                                + timedelta(days=days, hours=random.uniform(0, 4))).isoformat()
        row.pop("thin_streak", None)
        return row
    row.pop("dead_streak", None)
    if is_thin:
        streak = int(previous.get("thin_streak") or 0) + 1
        row["thin_streak"] = streak
        if streak <= len(THIN_TTL_STEPS_HOURS):
            hours = THIN_TTL_STEPS_HOURS[streak - 1]
            row["next_fetch_at"] = (datetime.now(timezone.utc)
                                    + timedelta(hours=hours * random.uniform(0.8, 1.2))).isoformat()
        else:
            row["next_fetch_at"] = _next_fetch_at()
        return row
    row.pop("thin_streak", None)
    return row


def prune_cache(keep: "set[str]", fetcher: "_Fetcher | None" = None,
                max_age_days: int = CACHE_PRUNE_DAYS) -> int:
    """Remove rows for tickers in no current list and no portfolio (`keep`)
    whose last fetch is older than `max_age_days` (EX-22): delisted lines
    otherwise stay in the file forever. Skipped while a fetch is running.
    Returns the number of rows removed."""
    f = fetcher or SCREENER_FETCH
    if f.bg_thread is not None and f.bg_thread.is_alive():
        return 0
    _warm_live_cache(f)
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    with f.row_lock:
        drop = []
        for t, r in f.live_cache.items():
            if t in keep:
                continue
            when = _row_fetch_time(r) if isinstance(r, dict) else None
            if when is not None and when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            if when is None or when < cutoff:
                drop.append(t)
        for t in drop:
            del f.live_cache[t]
    if drop:
        with f.file_lock:
            _save_cache(f.live_cache, f)
        _log.info("pruned %d cached rows no longer listed", len(drop),
                  extra={"event": "cache.pruned", "rows": len(drop), "sample": drop[:10]})
    return len(drop)


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
_DIV_RAISE_TOLERANCE = 1.01  # a year counts as a raise only above 101% of the prior year


def _cagr_n(vals: list[float], n: int) -> float | None:
    """CAGR from vals[-(n+1)] to vals[-1] — i.e. over the most recent `n`
    complete years — or None without at least n+1 data points or a
    non-positive base year (a 0/negative DPS n years back makes the ratio
    meaningless, same guard true_dgr already applies to its own window)."""
    if len(vals) < n + 1:
        return None
    base = vals[-(n + 1)]
    if base <= 0:
        return None
    return (vals[-1] / base) ** (1.0 / n) - 1.0


def _dividend_stats(ticker: str, *, now_year: int | None = None) -> dict:
    """Annual-DPS statistics from the full payment history (marketdata.dividends).

    Returns keys, all None/0 for a non-payer or on fetch failure:
      true_dgr                — CAGR of annual DPS across the complete years in
                                the window (>= _DIV_MIN_YEARS, first year > 0)
      dgr_1y / dgr_3y / dgr_5y — CAGR over exactly the most recent 1/3/5
                                complete years (None without enough history),
                                for the per-holding growth panel (WP-DIV5)
      dividend_growth_streak  — trailing consecutive complete years of
                                non-decreasing annual DPS
      dividend_payment_years  — count of complete years with a payment in-window
      dividend_last_cut_year  — most recent complete year whose annual DPS fell
                                below _DIV_CUT_TOLERANCE x the prior year, else None
      dividend_last_increase_year — most recent complete year whose annual DPS
                                rose above _DIV_RAISE_TOLERANCE x the prior
                                year, else None
    Isolated try/except like _fcf_history so a failure here never trips the
    whole-ticker retry/backoff.
    """
    empty = {"true_dgr": None, "dgr_1y": None, "dgr_3y": None, "dgr_5y": None,
             "dividend_growth_streak": 0, "dividend_payment_years": 0,
             "dividend_last_cut_year": None, "dividend_last_increase_year": None}
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
        last_increase_year = None
        for i in range(1, len(vals)):
            if vals[i] < vals[i - 1] * _DIV_CUT_TOLERANCE:
                last_cut_year = int(years[i])
            if vals[i] > vals[i - 1] * _DIV_RAISE_TOLERANCE:
                last_increase_year = int(years[i])

        return {
            "true_dgr": round(true_dgr, 4) if true_dgr is not None else None,
            "dgr_1y": round(v, 4) if (v := _cagr_n(vals, 1)) is not None else None,
            "dgr_3y": round(v, 4) if (v := _cagr_n(vals, 3)) is not None else None,
            "dgr_5y": round(v, 4) if (v := _cagr_n(vals, 5)) is not None else None,
            "dividend_growth_streak": streak,
            "dividend_payment_years": len(vals),
            "dividend_last_cut_year": last_cut_year,
            "dividend_last_increase_year": last_increase_year,
        }
    except Exception:
        return empty


_NEXT_DIV_LOOKBACK = 8    # up to ~2 years of quarterly payments


def _next_expected_ex_div(ticker: str) -> dict:
    """Forecast the next ex-dividend date and payment frequency from the
    full per-payment history (marketdata.dividends) — Dashboard's "Upcoming
    dividends" card used to filter yfinance's own `exDividendDate` field
    `>= today`, but that field is normally the *last* ex-div date Yahoo
    recorded, not a forecast, so the filter mostly came up empty. This
    derives the typical gap between recent payments and projects forward
    from the most recent one (repeatedly, in case that payment was itself
    already a while ago) instead.

    Returns {"nextExDividendDate": "DD/MM/YYYY" | None, "dividendFrequency":
    str | None} — both None for a non-payer, too little history to derive a
    reliable cadence, or on fetch failure (isolated try/except, same pattern
    as _dividend_stats above).
    """
    empty = {"nextExDividendDate": None, "dividendFrequency": None}
    try:
        divs = marketdata.dividends(ticker)
        if divs is None or len(divs) < 2:
            return empty
        recent = divs.iloc[-_NEXT_DIV_LOOKBACK:]
        gap_days = recent.index.to_series().diff().dropna().dt.days
        gap_days = gap_days[gap_days > 0]
        if gap_days.empty:
            return empty
        median_gap = float(gap_days.median())

        if median_gap <= 45:
            freq = N_("Monthly")
        elif median_gap <= 135:
            freq = N_("Quarterly")
        elif median_gap <= 225:
            freq = N_("Semi-annual")
        else:
            freq = N_("Annual")

        today = pd.Timestamp.now().normalize()
        next_date = recent.index[-1]
        # The last payment may already be older than one full cadence —
        # project forward until the forecast is actually in the future.
        guard = 0
        while next_date < today and guard < 12:
            next_date += pd.Timedelta(days=median_gap)
            guard += 1

        return {"nextExDividendDate": next_date.strftime("%d/%m/%Y"), "dividendFrequency": freq}
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
        # V1 (model M2): the currency the fundamentals are reported in, which
        # can differ from the quote currency (a Swiss company reporting in
        # USD). _convert_reporting_currency() reconciles the two.
        "financialCurrency": info.get("financialCurrency") or None,
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

    # WP-B: recover a missing trailing EPS from the P/E multiple. A degraded
    # Yahoo payload often drops trailingEps (defaultKeyStatistics) while keeping
    # trailingPE (summaryDetail); Price / trailingPE is the same figure to within
    # the price snapshot, and only ever positive (Yahoo suppresses P/E for
    # loss-makers). Fires only for a sane P/E in _PE_DERIVE_BAND. Flagged so
    # downstream — the fair-value models, dividend-coverage derivation below, and
    # the UI's thin-data hint — can see the input was reconstructed, not fetched.
    row["trailingEps_derived"] = False
    if row.get("trailingEps") is None:
        _pe = row.get("trailingPE")
        _px = _safe_float(price)
        if _pe is not None and _PE_DERIVE_BAND[0] < _pe < _PE_DERIVE_BAND[1] and _px and _px > 0:
            row["trailingEps"] = round(_px / _pe, 4)
            row["trailingEps_derived"] = True

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

    # Forecast next ex-div date + payment frequency from the same payment
    # history — feeds Dashboard's "Upcoming dividends" card (uvalu/pages_/
    # dashboard.py), which otherwise has to rely on the raw exDividendDate
    # field above (usually the *last* ex-div date, not a forecast).
    row.update(_next_expected_ex_div(ticker))

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
    _lane = "screener" if f is SCREENER_FETCH else "portfolio"
    done = 0
    failed = 0

    def _refresh_crumb():
        try:
            yf.Ticker("AAPL").fast_info
        except Exception:
            pass

    def _fetch_and_store(stock):
        nonlocal done, failed
        if f.cancelled.is_set():
            return
        ticker = stock["ticker"]
        row = None
        thin_tries = 0
        for attempt in range(MAX_RETRIES + 1):
            _wait_for_cooldown(f.cancelled)
            if f.cancelled.is_set():
                return
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    row = _fetch_one(ticker, stock)
                _scorable = _row_is_scorable(row)
                # FV-5: a row that IS scorable but whose fair value would rest on
                # fewer than MIN_FV_MODELS independent sub-models is a thin fetch
                # — almost always a partial Yahoo payload (some quoteSummary
                # modules missing) rather than a genuinely data-poor company.
                # Heal it like an unscorable one so it doesn't stick for a day
                # (review: gating this on `trailingEps_derived` missed the
                # book-value-only shape and let it diverge from the other lane).
                _thin = (_scorable and _fair_value_model_count(row) < MIN_FV_MODELS)
                if (_scorable and not _thin) or row.get("Price") is None:
                    break   # good row, or a dead/blocked symbol retrying can't improve
                # Priced but too thin to value: not scorable at all, or scorable
                # only via a single sub-model. Retry a couple of times; if it
                # stays thin, keep the row but flag it for a short-TTL refetch so
                # it self-heals next cycle rather than being trusted a full day (WP-A).
                thin_tries += 1
                if thin_tries <= _THIN_ROW_RETRIES:
                    row = None
                    time.sleep(min(2 ** thin_tries * 3, 20))
                    continue
                row["next_fetch_at"] = _next_fetch_at(short=True)
                row["_thin"] = True
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
                    if attempt < MAX_RETRIES:
                        _start_cooldown(2 ** attempt * 5)   # EX-20: every worker waits, not just this one
                        continue
                _fetch_log.warning(
                    "fundamentals fetch failed for %s", ticker,
                    extra={"event": "external_call.failed", "endpoint": "yfinance.quoteSummary",
                           "ticker": ticker, "reason": type(e).__name__, "lane": _lane})
                break
        if f.cancelled.is_set():
            return
        if row is None:
            row = {"Name": stock["name"], "Ticker": ticker,
                   "ISIN": stock["isin"], "fetched_at": ""}
        row = _carry_forward(row, cache.get(ticker))
        row = _apply_refetch_schedule(row, cache.get(ticker))
        time.sleep(REQUEST_DELAY)
        # Narrow critical section: only dict write + counter; save check happens outside
        with f.row_lock:
            cache[ticker] = row
            done += 1
            if not row.get("fetched_at"):
                failed += 1
            current = done
        with f.state_lock:
            f.state["done"] = current
        if not f.cancelled.is_set() and (current % 25 == 0 or current == len(stale)):
            with f.file_lock:
                _save_cache(cache, f)
        # Per-ticker progress — sampled to ~5% by logging.config.json so a
        # 1500-ticker refresh doesn't flood the log.
        _fetch_log.info("fetched %s (%d/%d)", ticker, current, len(stale),
                        extra={"event": "external_call.ok", "endpoint": "yfinance.quoteSummary",
                               "ticker": ticker, "lane": _lane})

    with logkit.job("fundamentals_fetch", reraise=False, trigger="stale_tickers",
                    lane=_lane, items=len(stale)) as _j:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            list(executor.map(_fetch_and_store, stale))
        _j.note(done=done, failed=failed, cancelled=f.cancelled.is_set())

    if not f.cancelled.is_set():
        with f.file_lock:
            _save_cache(cache, f)
    with f.state_lock:
        f.state["running"] = False


def _warm_live_cache(fetcher: "_Fetcher | None" = None) -> None:
    """Populate the fetcher's live cache from disk on first call (cold start only).

    Double-checked lock: the screener file is ~14 MB, so if two Streamlit
    script threads hit a cold cache in the same instant (fresh process, two
    sessions) an unguarded ``if not f.live_cache`` lets both run the full
    json.loads. The lock lets the first parse win and the second see a
    populated cache and skip straight through.
    """
    f = fetcher or SCREENER_FETCH
    if f.live_cache:
        return
    with f.warm_lock:
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

    _lane = "screener" if f is SCREENER_FETCH else "portfolio"
    if stale and (not f.bg_thread or not f.bg_thread.is_alive()):
        _log.info("background fundamentals fetch queued",
                  extra={"event": "job.queued", "job": "fundamentals_fetch",
                         "lane": _lane, "stale": len(stale), "cached": fresh_count})
        f.cancelled.clear()
        with f.state_lock:
            f.state.update({"done": 0, "total": len(stale), "running": True})
        _prio = [s for s in stale if s["ticker"] in _priority_tickers]
        _rest = [s for s in stale if s["ticker"] not in _priority_tickers]
        random.shuffle(_rest)
        f.bg_thread = logkit.spawn(_run_fetch, _prio + _rest, f.live_cache, f,
                                   name=f"fundamentals_fetch:{_lane}")
    elif not stale:
        _log.debug("all %d tickers served from fundamentals cache", fresh_count,
                   extra={"event": "cache.hit", "lane": _lane})

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


# V3 (model M3): the P/E fair value and the Graham Number used trailing EPS,
# so a one-off gain (a disposal, a revaluation) inflated both, and the PEG
# tilt on the trailing earningsGrowth counted the same gain a second time
# (docs/valuation-model-review.md V3: 11 Undervalued stocks had a trailing P/E
# under 5). Both now use normalised EPS, the same robust central value EPV
# uses for EBIT, and the tilt uses the multi-year growth.
_EPS_MIN_YEARS = 3
_TRAILING_GROWTH_MAX = 0.50        # without history, a bigger trailing jump is ignored
EPS_ONE_OFF_PE = 4.0               # a trailing P/E below this on trailing EPS is suspect

# V4 (model M4): a weighted average of model values far apart isn't an
# estimate of anything, and a margin of safety above 50% on a listed share is
# more often a data error than a bargain (docs/valuation-model-review.md V4:
# median highest/lowest model 3.3×, 328 stocks above 10×; TPG0.DE at 95% on
# a broken price). Both keep a stock out of Undervalued and are flagged.
FV_DISPERSION_MAX = 3.0            # highest / lowest model value
MOS_PLAUSIBLE_MAX = 0.50           # margin of safety above this: check the data


def _robust_central(values: list) -> "float | None":
    """Median of 3, trimmed mean (one extreme dropped per end) of 4+, else None."""
    vals = sorted(f for f in (_finite(v) for v in values) if f is not None)
    if len(vals) < _EPS_MIN_YEARS:
        return None
    if len(vals) == 3:
        return vals[1]
    trimmed = vals[1:-1]
    return sum(trimmed) / len(trimmed)


def _normalised_eps(row: "dict | pd.Series") -> "tuple[float | None, str]":
    """(EPS, basis) for the P/E and Graham models. With at least
    _EPS_MIN_YEARS finite years of `netIncomeHistory` and a share count, the
    robust central net income divided by today's shares (basis
    "normalised"); otherwise trailing EPS (basis "trailing"). Today's share
    count is an approximation where buybacks or new shares changed it."""
    hist = row.get("netIncomeHistory")
    central = _robust_central(hist) if isinstance(hist, list) else None
    shares = _eps_share_count(row)
    if central is not None and shares and shares > 0:
        return central / shares, "normalised"
    return _get_num(row, "trailingEps"), "trailing"


def _eps_share_count(row: "dict | pd.Series") -> "float | None":
    """The share count to divide company net income by. The provider's
    `sharesOutstanding` can cover one share class only (Robertet's investment
    certificates, CBE.PA: 122,792 shares, €76M at the price, against a €1.3bn
    market cap for the whole company). When price × shares and the market cap
    differ by more than a factor 2, the count implied by market cap ÷ price is
    used. (Not the count implied by net income ÷ trailing EPS: that differs
    exactly when trailing EPS holds a one-off, the case V3 is about.)"""
    shares = _finite(row.get("sharesOutstanding"))
    mcap = _finite(row.get("marketCap")) or _finite(row.get("Market Cap"))
    price = _finite(row.get("Price"))
    if mcap and mcap > 0 and price and price > 0:
        implied = mcap / price
        if not shares or shares <= 0 or not (0.5 <= implied / shares <= 2.0):
            return implied
    return shares


def _tilt_growth(row: "dict | pd.Series") -> "float | None":
    """Earnings growth for the P/E model's PEG tilt: the compound growth of
    `netIncomeHistory` (oldest to newest, at least _EPS_MIN_YEARS finite
    positive years); without that, the trailing `earningsGrowth` only when
    its size is at most _TRAILING_GROWTH_MAX; else None (no tilt)."""
    hist = row.get("netIncomeHistory")
    vals = [f for f in ((_finite(v) for v in hist) if isinstance(hist, list) else ()) if f is not None]
    if len(vals) >= _EPS_MIN_YEARS and vals[0] > 0 and vals[-1] > 0:
        return (vals[0] / vals[-1]) ** (1.0 / (len(vals) - 1)) - 1.0   # newest first
    eg = _get_num(row, "earningsGrowth")
    if eg is not None and abs(eg) <= _TRAILING_GROWTH_MAX:
        return eg
    return None


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
                       sector_pb: "dict | None" = None, *, discount_shift: float = 0.0) -> dict:
    price    = row.get("Price")
    eps, eps_basis = _normalised_eps(row)   # V3: multi-year EPS, else trailing
    bvps     = row.get("bookValue")
    div_rate = row.get("trailingAnnualDividendRate") or row.get("dividendRate")
    payout, payout_source = _payout_signal(row)   # FV-1: reported / cash / 1-over-coverage
    analyst  = row.get("targetMeanPrice")
    ebit     = _normalised_ebit(row)   # robust mean of ebitHistory (≥3yr) else point-in-time
    ev, ev_source = _enterprise_value(row)   # FV-4: provider EV, else reconstructed from mcap+debt−cash
    beta     = row.get("beta")
    eg       = _tilt_growth(row)                    # V3: PEG tilt on multi-year growth
    ddm_g    = _dgr_estimate(row)                   # FV-7: true DPS CAGR, else earningsGrowth
    country  = row.get("country")
    # FV-8 keys off the *resolved* sector (SECTOR_OVERRIDES fills provider gaps for
    # the exact REITs the guard is for — e.g. RET.BR, whose raw sector is often
    # null); `compute_scores` also resolves `df["sector"]` before Stage 2 so the
    # sector-median buckets and this agree (review).
    sector   = sector_for(row.get("Ticker"), row.get("sector"))
    shares   = row.get("sharesOutstanding")
    tax_rate = COUNTRY_TAX_RATES.get(country, DEFAULT_TAX_RATE)

    # discount_shift: added to the discount rate for the sensitivity table
    # (fair_value_sensitivity, REC-6); 0 for every scored row.
    wacc = _approx_wacc(beta) + discount_shift

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
    if eg is not None and pd.notna(eg):
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
                "ev_source": ev_source, "fv_model_count": 0, "eps_basis": eps_basis,
                "fv_low": None, "fv_high": None, "fv_dispersion": None,
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
    if (eps_basis == "trailing" and bool(row.get("trailingEps_derived"))
            and gn is not None and gn > 0 and pe_fv is not None and pe_fv > 0):
        fv_model_count -= 1
    fv_model_count = max(fv_model_count, 1)

    total_w = sum(w for _, w in avail)
    iv      = sum(v * w / total_w for v, w in avail)
    # V4: the spread of the models behind the composite.
    _vals = [v for v, _ in avail]
    fv_low, fv_high = min(_vals), max(_vals)
    fv_dispersion = fv_high / fv_low if fv_low > 0 else None

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
        "eps_basis":      eps_basis,
        "fv_low":         round(fv_low, 2),
        "fv_high":        round(fv_high, 2),
        "fv_dispersion":  round(fv_dispersion, 3) if fv_dispersion else None,
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
    ``signal_code`` (REC-2, REC-5). Replaces the former decision_reason: it
    reports the rule and the figures, in descriptive terms only — no "BUY",
    no "avoid", nothing addressed to the reader (DIS-6). Mirrors
    ``compute_scores`` Stage 6 exactly. ``min_mos`` is a fraction."""
    code = str(row.get("signal_code") or "")
    _s = row.get("Value Score")
    _m = row.get("margin_of_safety")
    score = None if _s is None or (isinstance(_s, float) and pd.isna(_s)) else float(_s)
    mos   = None if _m is None or (isinstance(_m, float) and pd.isna(_m)) else float(_m)
    thin  = bool(row.get("fv_basis_thin"))
    min_mos = effective_min_mos(min_mos)
    from uvalu.i18n import _, fmt_num, fmt_pct
    _score_txt = "—" if score is None else fmt_num(score, 0)
    _thr = fmt_num(buy_threshold, 0)

    def _pct(v):
        return fmt_pct(v, 0, fraction=True, signed=True)

    if code == SIGNAL_PENDING:
        return _("No signal: the peer group needed to rank this stock is not available yet.")

    if code == SIGNAL_FAILS:
        rules = row.get("veto_rules")
        names = [_(VETO_RULE_LABELS[r]) for r in (rules if isinstance(rules, list) else [])
                 if r in VETO_RULE_LABELS]
        if names:
            return _("Fails the model's quality screen ({rules}), so its composite score is set to 0.",
                     rules="; ".join(names))
        return _("Fails the model's quality screen, so its composite score is set to 0.")

    if code == SIGNAL_UNDERVALUED:
        if score is not None and score < buy_threshold and mos is not None:
            # Q1: kept by the stability rule, within SIGNAL_HYSTERESIS of the edge.
            return _("Model score {score} is within {band} points of {threshold}, so the stock keeps its "
                     "signal (stability rule), and the price is {mos} below the model fair value "
                     "(minimum {min_mos}).",
                     score=_score_txt, band=fmt_num(SIGNAL_HYSTERESIS, 0), threshold=_thr,
                     mos=_pct(mos), min_mos=_pct(min_mos))
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
    if bool(row.get("currency_unverified")):
        gates.append(_("the company's figures couldn't be converted to the share's currency"))
    if bool(row.get("eps_one_off_suspect")):
        gates.append(_("the earnings may include a one-off gain"))
    if bool(row.get("fv_models_disagree")):
        _lo, _hi = row.get("fv_low"), row.get("fv_high")
        if _lo is not None and _hi is not None and pd.notna(_lo) and pd.notna(_hi):
            gates.append(_("the models disagree: their values range from {low} to {high}",
                           low=fmt_num(float(_lo), 2), high=fmt_num(float(_hi), 2)))
        else:
            gates.append(_("the models disagree"))
    if bool(row.get("mos_implausible")):
        gates.append(_("a margin of safety above {limit} is more often a data error than a real discount",
                       limit=fmt_pct(MOS_PLAUSIBLE_MAX, 0, fraction=True)))
    # Translators: signal explanation for a "Mid score" badge; {reasons} is a list of lowercase reasons joined by "; ".
    return (_("Mid score: {reasons}.", reasons="; ".join(gates)) if gates
            else _("Model score is between the lower and upper thresholds."))


def _total_expected_return(price, fair_value, div_yield, dgr, ddm_contributed=False) -> float | None:
    """Model-implied return estimate = gap to model fair value % + forward
    dividend yield + assumed DGR (all as %). Formerly "TER %" (Total Expected
    Return); published as "Implied Return % (est.)" because it is a model estimate, not
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


def _trend_veto_rules(row: pd.Series) -> list[tuple[str, object]]:
    """(rule code, reason text) for each *trend*-based hard veto a stock trips
    (empty list = clean). The code is a stable VETO_RULE_* value (logged with
    the signal, REC-11); the text carries the stock's own figures."""
    rules: list[tuple[str, object]] = []

    rev = _clean_history(row, "revenueHistory")
    if len(rev) >= _TREND_MIN_YEARS:
        run = _declining_run(rev)
        if run >= _TREND_DECLINE_RUN:
            rules.append((VETO_RULE_REVENUE_DECLINE,
                          lazy_("revenue fell {years} straight years", years=run + 1)))

    ebit = _clean_history(row, "ebitHistory")
    if len(ebit) >= _TREND_MIN_YEARS and all(v < 0 for v in ebit[:_TREND_MIN_YEARS]):
        rules.append((VETO_RULE_NEGATIVE_EBIT,
                      lazy_("operating income negative {years} years running", years=_TREND_MIN_YEARS)))

    ret = _clean_history(row, "retainedEarningsHistory")
    if (len(ret) >= _TREND_MIN_YEARS and ret[0] < 0
            and _declining_run(ret) >= _TREND_DECLINE_RUN):
        rules.append((VETO_RULE_RETAINED_EROSION, lazy_("retained earnings negative and still eroding")))

    last_cut = _get_num(row, "dividend_last_cut_year")
    coverage = _get_num(row, "dividendCoverage")
    if (last_cut is not None and coverage is not None
            and last_cut >= datetime.now(timezone.utc).year - _DIV_CUT_VETO_YEARS
            and coverage < _DIV_CUT_VETO_COVERAGE):
        rules.append((VETO_RULE_DIVIDEND_CUT,
                      lazy_("dividend cut in {year} with only {coverage}× cover", year=str(int(last_cut)),
                            coverage=Fmt("num", coverage, decimals=2))))

    return rules


def _trend_veto(row: pd.Series) -> list[str]:
    """Reasons a stock trips a *trend*-based hard veto (empty list = clean).

    The static, point-in-time vetoes (sector-adjusted D/E, single-period FCF,
    at-risk dividend + coverage < 1.0) live in compute_scores / veto_reason_str;
    this is the multi-year-deterioration set. One function, so compute_scores and
    both veto UIs (components.veto_reason_str, analysis.py's checks panel) read
    the exact same rule instead of re-deriving it.
    """
    return [text for _code, text in _trend_veto_rules(row)]


def compute_scores(df: pd.DataFrame, *, max_debt_equity: float = 500.0,
                   max_payout: float = 0.90, min_mos: float = 0.0,
                   buy_threshold: float = SCORE_STRONG_BUY,
                   weights: "tuple | None" = None,
                   reference: "ScoreReference | None" = None,
                   reference_out: "dict | None" = None,
                   peer_mask: "pd.Series | None" = None,
                   user_selected: bool = False,
                   founder_holdings: "set | frozenset | None" = None,
                   computed_at: "datetime | None" = None,
                   previous_signals: "dict | None" = None) -> pd.DataFrame:
    # ``reference``: score `df` against another universe's sector medians and
    # rank distributions instead of its own (the portfolio lane passes the
    # scored universe's). ``reference_out``: a dict that receives this pass's
    # own ScoreReference under "ref", for later callers to score against.
    #
    # PER-1 / PER-2:
    # ``peer_mask``: boolean Series aligned to `df` marking the rows of the
    # public universe. Only those rows set the sector medians and the rank
    # distributions; the other rows (a user's manual tickers, holdings on a
    # disabled exchange) are scored *against* the public peers without moving
    # them. Without a mask every row is a peer; before v2.1.0 that let a user's
    # manual tickers shift every other stock's percentile ranks, so two users
    # could see different signals for the same stock.
    # ``user_selected``: `df` is a set a user picked (holdings, watchlist), not
    # the public universe. Without a ``reference`` its rows are not ranked among
    # themselves (that would make the signal depend on the user's holdings);
    # they get signal_code "pending" instead. Fair values are still computed.
    # ``founder_holdings``: tickers the founder holds a position in (REC-8;
    # see load_founder_holdings). Sets only the `founder_holds` disclosure
    # flag; it never touches a score or a signal.
    # ``computed_at``: timestamp stamped on every row (REC-4); defaults to now.
    # Composite sub-score weights (W_MOS, W_RISK, W_QUALITY, W_MOMENTUM,
    # W_DIVIDEND). None → the module defaults ("balanced"); the Settings
    # screening-style picker passes a re-lensed vector via
    # settings.get_score_weights().
    min_mos = effective_min_mos(min_mos)   # D1 floor
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
        *_STATEMENT_HISTORY_KEYS, *ANALYST_FIELDS,
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
    elif _no_peer_basis:
        # PER-1: no public peer group to take sector multiples from. Medians of
        # a user-selected set would make the P/E and P/B fair values depend on
        # what the user holds, so every sector uses the fixed fallback multiples.
        sector_pe, sector_pb = {}, {}
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
    trend_rules   = df.apply(lambda r: [code for code, _t in _trend_veto_rules(r)], axis=1)
    trend_veto    = trend_rules.map(bool)
    no_trade_veto = pd.to_numeric(df["averageVolume"], errors="coerce") == 0
    de_veto       = (de > max_debt_equity) & ~leverage_exempt
    div_veto      = (df["Div Flag"] == "At Risk") & (coverage < 1.0)
    df["_hard_veto"] = de_veto | fcf_veto | trend_veto | div_veto | no_trade_veto
    # REC-2 / BDG-3: the rules each vetoed row tripped, as stable codes, in
    # the order of the methodology page's quality-screen list.
    _static_rules = ((VETO_RULE_DEBT_EQUITY, de_veto), (VETO_RULE_NEGATIVE_FCF, fcf_veto),
                     (VETO_RULE_DIVIDEND_AT_RISK, div_veto))
    df["veto_rules"] = [
        [code for code, hit in _static_rules if bool(hit.iloc[i])]
        + list(trend_rules.iloc[i])
        + ([VETO_RULE_NO_VOLUME] if bool(no_trade_veto.iloc[i]) else [])
        for i in range(len(df))
    ]

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
    # The former Strong Buy / Monitor / Avoid decision, published as a
    # descriptive state (BDG-1) — veto → fails_screen (its own state, BDG-3,
    # not folded into the lowest band); score ≥ buy_threshold + confirmed
    # MoS ≥ min_mos + corroborated fair value → undervalued; score ≥
    # SCORE_AVOID → neutral; else low_score. Rows with no public peer basis
    # (PER-1) → pending, with no score: a rank among a user's own holdings is
    # not shown.
    # Rationale for the gates:
    # Undervalued requires both the composite score AND the margin of safety
    # to clear their configured thresholds (Settings → Model settings) — a
    # high score alone doesn't override a thin MoS. A stock with no computable
    # fair value (NaN MoS — every model failed) can't have its margin of
    # safety confirmed, so it can't be Undervalued; it falls through to
    # Neutral / Low score on score alone. A `fv_basis_thin` fair value (FV-5:
    # fewer than MIN_FV_MODELS independent sub-models, e.g. a lone book-value
    # fallback) is real but weakly corroborated: it keeps the row out of
    # Undervalued rather than joining `_hard_veto`, since a thin basis isn't a
    # red flag on its own, just an unconfirmed one.
    # np.select takes the first true branch, and every non-veto branch
    # already excludes veto rows. NaN score compares False everywhere → Low
    # score.
    _dec_veto  = df["_hard_veto"].fillna(False).astype(bool)
    _dec_score = pd.to_numeric(df["Value Score"], errors="coerce")
    _dec_mos   = pd.to_numeric(df["margin_of_safety"], errors="coerce")
    _dec_thin  = df["fv_basis_thin"].fillna(False).astype(bool)
    # V1: a fair value whose currency couldn't be reconciled isn't confirmed.
    _dec_ccy   = (df["currency_unverified"].fillna(False).astype(bool)
                  if "currency_unverified" in df.columns else pd.Series(False, index=df.index))
    # V3: a fair value on trailing EPS with a trailing P/E under EPS_ONE_OFF_PE
    # most likely rests on a one-off gain; it isn't confirmed either.
    df["eps_one_off_suspect"] = _eps_one_off_suspect(df)
    _dec_oneoff = df["eps_one_off_suspect"]
    # V4: models far apart, or a margin too large to trust without a check.
    df["fv_models_disagree"], df["mos_implausible"] = _fair_value_doubts(df)
    _dec_doubt = df["fv_models_disagree"] | df["mos_implausible"]
    df["signal_code"] = np.select(
        [
            _dec_veto,
            (~_dec_veto) & (_dec_score >= buy_threshold) & _dec_mos.notna()
                & (_dec_mos >= min_mos) & ~_dec_thin & ~_dec_ccy & ~_dec_oneoff & ~_dec_doubt,
            (~_dec_veto) & (_dec_score >= SCORE_AVOID),
        ],
        [SIGNAL_FAILS, SIGNAL_UNDERVALUED, SIGNAL_NEUTRAL],
        default=SIGNAL_LOW_SCORE,
    )
    if previous_signals:
        df["signal_code"] = _apply_signal_hysteresis(
            df, previous_signals, buy_threshold=buy_threshold, min_mos=min_mos)
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
    # Whether the row belongs to the shared public universe. Only these rows go
    # into the shared signal history (signal_history.record_changes): a user's
    # own tickers, or a user-selected pass without a peer mask, never do.
    df["public_universe"] = (_peers & (peer_mask is not None or not user_selected)).astype(bool)
    # REC-8: founder position disclosure, at any size (FOUNDER_HOLDS_NOTICE).
    _founder = {str(t) for t in (founder_holdings or ())}
    df["founder_holds"] = (df["Ticker"].astype(str).isin(_founder) if "Ticker" in df.columns
                           else pd.Series(False, index=df.index))
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
        "currency_unverified": _dec_ccy.tolist(),
        "eps_one_off_suspect": _dec_oneoff.tolist(),
        "fair_value_models_disagree": df["fv_models_disagree"].tolist(),
        "margin_implausible": df["mos_implausible"].tolist(),
    }
    df["data_flags"] = [
        [name for name, vals in _flag_cols.items() if vals[i]] for i in range(len(df))
    ]

    # Drop internal columns, and the unlicensed analyst fields (DATA-6)
    df = df.drop(columns=[c for c in df.columns if c.startswith("_")])
    df = strip_analyst_fields(df)
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
                         user_selected: bool = False,
                         founder_holdings: "set | frozenset | None" = None,
                         previous_signals: "dict | None" = None) -> pd.DataFrame:
    """Score and clean a DataFrame that was already fetched (avoids re-fetching).
    ``reference`` / ``reference_out`` / ``peer_mask`` / ``user_selected`` /
    ``founder_holdings`` / ``previous_signals``: see compute_scores and
    _apply_signal_hysteresis."""
    return _score_and_clean(df.copy(), max_debt_equity=max_debt_equity,
                            max_payout=max_payout, min_mos=min_mos,
                            buy_threshold=buy_threshold, weights=weights,
                            reference=reference, reference_out=reference_out,
                            peer_mask=peer_mask, user_selected=user_selected,
                            founder_holdings=founder_holdings,
                            previous_signals=previous_signals)


def _score_and_clean(df: pd.DataFrame, *, max_debt_equity: float = 500.0,
                     max_payout: float = 0.90, min_mos: float = 0.0,
                     buy_threshold: float = SCORE_STRONG_BUY,
                     weights: "tuple | None" = None,
                     reference: "ScoreReference | None" = None,
                     reference_out: "dict | None" = None,
                     peer_mask: "pd.Series | None" = None,
                     user_selected: bool = False,
                     founder_holdings: "set | frozenset | None" = None,
                     previous_signals: "dict | None" = None) -> pd.DataFrame:
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
    df, peer_mask = _convert_reporting_currency(df, peer_mask)
    _log.debug("computing valuation scores for %d rows", len(df),
               extra={"event": "score.compute", "rows": len(df)})
    return compute_scores(df, max_debt_equity=max_debt_equity, max_payout=max_payout,
                          min_mos=min_mos, buy_threshold=buy_threshold, weights=weights,
                          reference=reference, reference_out=reference_out,
                          peer_mask=peer_mask, user_selected=user_selected,
                          founder_holdings=founder_holdings,
                          previous_signals=previous_signals)


def _fair_value_doubts(df: pd.DataFrame) -> "tuple[pd.Series, pd.Series]":
    """V4: (models disagree, margin implausible) per row. Disagree: the
    highest model value is more than FV_DISPERSION_MAX times the lowest.
    Implausible: the margin of safety is above MOS_PLAUSIBLE_MAX."""
    disp = pd.to_numeric(df["fv_dispersion"], errors="coerce") if "fv_dispersion" in df.columns         else pd.Series(np.nan, index=df.index)
    mos = pd.to_numeric(df["margin_of_safety"], errors="coerce") if "margin_of_safety" in df.columns         else pd.Series(np.nan, index=df.index)
    return ((disp > FV_DISPERSION_MAX).fillna(False).astype(bool),
            (mos > MOS_PLAUSIBLE_MAX).fillna(False).astype(bool))


def _eps_one_off_suspect(df: pd.DataFrame) -> pd.Series:
    """V3: True where the earnings models ran on trailing EPS (no multi-year
    history) and the trailing P/E is positive but under EPS_ONE_OFF_PE."""
    basis = df["eps_basis"] if "eps_basis" in df.columns else pd.Series("trailing", index=df.index)
    pe = pd.to_numeric(df["trailingPE"], errors="coerce") if "trailingPE" in df.columns         else pd.Series(np.nan, index=df.index)
    return ((basis == "trailing") & (pe > 0) & (pe < EPS_ONE_OFF_PE)).fillna(False).astype(bool)


# ── Signal hysteresis (Q1, model M2) ─────────────────────────────────────────
# Signals are recomputed whenever data arrives, and every refresh moves the
# percentile ranks of every other stock a little, so a stock near a band edge
# flipped on noise (SRAIL.SW 21 times in 9 days at 39.9 / 40.0;
# docs/quant-review.md Q1). A stock now keeps its band until its composite
# score falls SIGNAL_HYSTERESIS points past the edge it would leave by. Entry
# into a higher band is unchanged. The score only: the margin-of-safety floor
# for Undervalued stays strict (decision D1), and vetoes are absolute rules.
# Every user gets the same previous signal (the shared history), so this
# keeps PER-1. Published on the methodology page.
SIGNAL_HYSTERESIS = 2.0


def _apply_signal_hysteresis(df: pd.DataFrame, previous: dict, *,
                             buy_threshold: float, min_mos: float) -> pd.Series:
    """`df["signal_code"]` with each downgrade that only a small score dip
    caused undone. `previous`: {ticker: signal_code} from the signal history."""
    codes = df["signal_code"].copy()
    if "Ticker" not in df.columns:
        return codes
    prev = df["Ticker"].map(previous)
    score = pd.to_numeric(df["Value Score"], errors="coerce")
    # Undervalued → Mid score on score alone: everything else Undervalued
    # needs still holds (np.select put it in Mid score only for the score).
    keep_u = ((prev == SIGNAL_UNDERVALUED) & (codes == SIGNAL_NEUTRAL)
              & (score < buy_threshold) & (score >= buy_threshold - SIGNAL_HYSTERESIS))
    if keep_u.any():
        mos = pd.to_numeric(df["margin_of_safety"], errors="coerce")
        thin = df["fv_basis_thin"].fillna(False).astype(bool)
        ccy = (df["currency_unverified"].fillna(False).astype(bool)
               if "currency_unverified" in df.columns else pd.Series(False, index=df.index))
        oneoff = (df["eps_one_off_suspect"].fillna(False).astype(bool)
                  if "eps_one_off_suspect" in df.columns else pd.Series(False, index=df.index))
        doubt = pd.Series(False, index=df.index)
        for _col in ("fv_models_disagree", "mos_implausible"):
            if _col in df.columns:
                doubt |= df[_col].fillna(False).astype(bool)
        keep_u &= mos.notna() & (mos >= min_mos) & ~thin & ~ccy & ~oneoff & ~doubt
    keep_n = ((prev == SIGNAL_NEUTRAL) & (codes == SIGNAL_LOW_SCORE)
              & (score >= SCORE_AVOID - SIGNAL_HYSTERESIS))
    codes[keep_u] = SIGNAL_UNDERVALUED
    codes[keep_n] = SIGNAL_NEUTRAL
    return codes


# ── Reporting currency (V1, model M2) ────────────────────────────────────────
# Yahoo gives the price in the listing's quote currency but per-share and
# statement figures in the company's reporting currency. Where they differ,
# a fair value came out in the wrong currency (Investor AB in Milan: book
# value in SEK against a EUR price, docs/valuation-model-review.md V1).
# These figures are converted to the quote currency before scoring.
_REPORTING_CCY_FIELDS = ("trailingEps", "bookValue", "ebit", "totalDebt", "totalCash",
                         "freeCashflow", "netIncome")
_REPORTING_CCY_HISTORIES = ("fcfHistory", "revenueHistory", "ebitHistory", "netIncomeHistory",
                            "cfoHistory", "retainedEarningsHistory", "totalAssetsHistory")


def _fx_rate(reporting: str, quote: str) -> float:
    """Units of `quote` per 1 `reporting`, from the ECB reference rates."""
    import fx
    return float(fx.get_rate(reporting, base=quote).rate)


def _convert_reporting_currency(df: pd.DataFrame, peer_mask: "pd.Series | None" = None,
                                rate_fn=None) -> "tuple[pd.DataFrame, pd.Series | None]":
    """Convert the reporting-currency figures of every row whose
    financialCurrency differs from its quote Currency, and flag the rows that
    can't be converted (no rate). Returns (df, peer_mask).

    On a converted row the provider's enterpriseValue is dropped (its currency
    is unclear; the EV is rebuilt from market cap, debt and cash, FV-4), and
    trailingPE / priceToBook are recomputed from the converted figures, since
    they feed the sector medians. A `currency_unverified` row stays out of the
    peer group (sector medians and ranks) and out of Undervalued. A row with
    no financialCurrency yet (fetched before M2) is taken as reporting in its
    quote currency."""
    df = df.copy()
    df["currency_unverified"] = False
    if "financialCurrency" not in df.columns or "Currency" not in df.columns:
        return df, peer_mask
    rate_fn = rate_fn or _fx_rate
    rates: dict = {}
    converted = 0
    for i in df.index:
        rep_ccy, quote = df.at[i, "financialCurrency"], df.at[i, "Currency"]
        if not (isinstance(rep_ccy, str) and rep_ccy.strip() and isinstance(quote, str) and quote.strip()):
            continue
        rep_ccy, quote = rep_ccy.strip().upper(), quote.strip().upper()
        if rep_ccy == quote:
            continue
        if (rep_ccy, quote) not in rates:
            try:
                rates[(rep_ccy, quote)] = rate_fn(rep_ccy, quote)
            except Exception:
                rates[(rep_ccy, quote)] = None
        rate = rates[(rep_ccy, quote)]
        if not rate:
            df.at[i, "currency_unverified"] = True
            continue
        for col in _REPORTING_CCY_FIELDS:
            if col in df.columns:
                v = _safe_float(df.at[i, col])
                df.at[i, col] = v * rate if v is not None else df.at[i, col]
        for col in _REPORTING_CCY_HISTORIES:
            if col in df.columns and isinstance(df.at[i, col], (list, tuple)):
                df.at[i, col] = [x * rate if isinstance(x, (int, float)) and not isinstance(x, bool)
                                 and math.isfinite(x) else x for x in df.at[i, col]]
        if "enterpriseValue" in df.columns:
            df.at[i, "enterpriseValue"] = np.nan
        price = _safe_float(df.at[i, "Price"]) if "Price" in df.columns else None
        eps = _safe_float(df.at[i, "trailingEps"]) if "trailingEps" in df.columns else None
        bvps = _safe_float(df.at[i, "bookValue"]) if "bookValue" in df.columns else None
        if "trailingPE" in df.columns:
            df.at[i, "trailingPE"] = price / eps if price and eps and eps > 0 else np.nan
        if "priceToBook" in df.columns:
            df.at[i, "priceToBook"] = price / bvps if price and bvps and bvps > 0 else np.nan
        converted += 1
    unverified = df["currency_unverified"].astype(bool)
    if peer_mask is not None and unverified.any():
        peer_mask = peer_mask & ~unverified
    if converted or unverified.any():
        _log.info("reporting currency: %d rows converted, %d unverified", converted, int(unverified.sum()),
                  extra={"event": "score.currency", "converted": converted,
                         "unverified": int(unverified.sum())})
    return df, peer_mask


# ── Legal-compliance helpers ──────────────────────────────────────────────────

def peer_mask_for(df: pd.DataFrame, public_tickers) -> pd.Series:
    """PER-2: the ``peer_mask`` for `df` — True for rows whose Ticker is in the
    public universe (the enabled exchanges' ticker lists, a shared setting),
    False for user-added rows (manual tickers, holdings on a disabled exchange)."""
    public = set(public_tickers)
    if "Ticker" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["Ticker"].isin(public)


def effective_min_mos(min_mos: float) -> float:
    """The margin of safety "Undervalued" actually requires: the shared
    `min_mos` setting (a fraction), but never below MIN_MOS_FLOOR (D1)."""
    try:
        return max(float(min_mos), MIN_MOS_FLOOR)
    except (TypeError, ValueError):
        return MIN_MOS_FLOOR


def strip_analyst_fields(data):
    """DATA-6: `data` without the sell-side ANALYST_FIELDS while
    ANALYST_INPUTS_ENABLED is off — a DataFrame (columns dropped), a single
    fundamentals row (dict) or a {ticker: row} cache dict. Returned unchanged
    when the switch is on. Never mutates its argument."""
    if ANALYST_INPUTS_ENABLED or data is None:
        return data
    if isinstance(data, pd.DataFrame):
        return data.drop(columns=[c for c in ANALYST_FIELDS if c in data.columns])
    if isinstance(data, dict):
        if data and all(isinstance(v, dict) for v in data.values()):   # {ticker: row}
            return {k: strip_analyst_fields(v) for k, v in data.items()}
        return {k: v for k, v in data.items() if k not in ANALYST_FIELDS}
    return data


def load_founder_holdings(path: Path = FOUNDER_HOLDINGS_FILE) -> frozenset:
    """REC-8: the tickers the founder holds a position in, at any size, for the
    `founder_holds` disclosure flag. The file is kept by hand and updated with
    each personal trade in a covered stock (see the conflicts of interest
    policy): {"updated": "YYYY-MM-DD", "tickers": ["ABI.BR", ...]}.

    A missing file means "no positions". A file that exists but can't be read
    raises: silently showing no disclosure would be a false statement."""
    if not path.exists():
        return frozenset()
    data = json.loads(path.read_text(encoding="utf-8"))
    tickers = data.get("tickers") if isinstance(data, dict) else None
    if not isinstance(tickers, list):
        raise ValueError(f"{path}: expected {{\"tickers\": [...]}}")
    return frozenset(str(t).strip() for t in tickers if str(t).strip())


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
    min_mos = effective_min_mos(min_mos)   # D1 floor
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


# REC-3: what each data flag means, for the stock page's data panel.
DATA_FLAG_LABELS = {
    "price_stale": N_("The price is more than 72 hours old."),
    "price_missing_timestamp": N_("The time of the price is unknown."),
    "fair_value_missing": N_("No model could compute a fair value."),
    "fair_value_thin_basis": N_("The fair value rests on fewer than two independent models."),
    "fair_value_clamped": N_("The fair value was capped at the models' median."),
    "eps_derived_from_pe": N_("Earnings per share were derived from the P/E ratio."),
    "small_peer_group": N_("Fewer than 20 stocks were available for comparison."),
    "currency_unverified": N_("The company reports in another currency than its share price, "
                              "and no exchange rate was available to convert its figures."),
    "eps_one_off_suspect": N_("Earnings per share come from the latest year only, and the price is "
                              "under 4 times those earnings: they may include a one-off gain."),
    "fair_value_models_disagree": N_("The models disagree: the highest value is more than 3 times the "
                                     "lowest, so the fair value is shown as a range."),
    "margin_implausible": N_("The price is more than 50% below the model fair value. A gap this "
                             "large is more often a data error than a real discount: check the figures."),
}


def fair_value_sensitivity(row: "pd.Series | dict", reference: "ScoreReference | None" = None,
                           shifts: tuple = (-0.01, 0.0, 0.01)) -> list[dict]:
    """REC-6: the stock's model fair value and margin of safety with the
    discount rate shifted by each of ``shifts`` (fractions), all else equal.
    Uses the scored universe's sector multiples (``reference``) so the 0 shift
    reproduces the row's own fair value. Display only: a shifted fair value
    never changes a score or a signal (decision D2)."""
    row = pd.Series(row) if isinstance(row, dict) else row
    sector_pe = reference.sector_pe if reference is not None else {}
    sector_pb = reference.sector_pb if reference is not None else {}
    base_rate = _approx_wacc(row.get("beta"))
    price = _finite(row.get("Price"))
    out = []
    for shift in shifts:
        fv = _finite(_fair_value_models(row, sector_pe=sector_pe, sector_pb=sector_pb,
                                        discount_shift=shift).get("fair_value"))
        out.append({"shift": shift, "discount_rate": base_rate + shift, "fair_value": fv,
                    "margin_of_safety": _margin_of_safety(price, fv)})
    return out


# The inputs a signal can be reproduced from (REC-11), next to its outputs.
SIGNAL_RECORD_FIELDS = (
    "Ticker", "signal_code", "Value Score", "Price", "price_as_of", "fair_value",
    "margin_of_safety", "fv_model_count", "fv_basis_thin", "veto",
    "Sub MoS", "Sub Risk", "Sub Quality", "Sub Momentum", "Sub Dividend",
    "graham_number", "pe_fair_value", "epv", "ddm", "ddm_multistage",
    "pb_fair_value", "fcf_fair_value", "data_flags", "veto_rules",
    "public_universe", "founder_holds",
    "signal_computed_at", "model_version", "model_settings_id",
)


def signal_records(df: pd.DataFrame) -> list[dict]:
    """REC-7 / REC-11: one JSON-safe record per scored row with the signal, the
    inputs and fair values behind it, and the model version/settings — for an
    append-only signal log (see uvalu/compliance/signal_history.py). NaN becomes None."""
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
