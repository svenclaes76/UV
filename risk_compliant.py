"""
Portfolio Risk Assessment — 8-stage algorithm. LEGAL-COMPLIANCE COPY of risk.py.

Same computations as risk.py (docs/portfolio_risk_assessment_algorithm.md);
only what the output says changes, per "Uvalu — Legal Requirements for Launch"
(Oct 2 2026). risk.py itself is untouched; this module is a candidate
replacement, not yet wired into the app. Review:
docs/legal/algorithm-compliance-review.md.

What changed versus risk.py, by requirement ID:
  PER-4  Describe, never prescribe. The composite band carries a description,
         not an action ("Immediate rebalancing required" is gone), and Stage 8
         produces RiskObservations (what the figures show) instead of
         RebalanceSignals with "Trim to ≤15%", "Rotate into…", "Replace one
         position per pair…".
  PER-5  The Stage 8 trigger that paired a held stock's screener veto with
         "consider reducing or exiting" is removed: it combined a signal with
         the user's own portfolio. Checks against targets the user set are kept
         and marked basis="user_target".
  PER-1  "Loss tolerance" / "hard limit" wording that implied a personal risk
         tolerance is replaced by the model's reference levels.
  PER-3  `income_portfolio` (a user objective) becomes `weighting`, a model
         setting the user chooses on the Risk page, never derived from a
         questionnaire.
  DIS-3  RiskReport.disclosures: VaR, CVaR, Monte Carlo and stress results are
         statistical estimates; real losses can exceed them.
  REC-2  Per-position valuation flags are named after the comparison they make.

Entry point:
    report = assess_portfolio(pf_df, cache, weighting="standard")

pf_df   — enriched portfolio DataFrame (columns: ticker, name, shares,
           purchase_value, current_value, live_price, sector, country,
           expected_annual, fair_value)
cache   — fundamentals cache dict[ticker -> dict] from screener._load_cache()
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import marketdata
from uvalu.i18n import N_, Fmt, lazy_
from screener import (
    RISK_FREE_RATE,          # single euro-area risk-free source (screener.py)
    EQUITY_RISK_PREMIUM,     # ...and the ERP, for the Monte-Carlo drift assumption
)
from scoring import (
    _financial_health_score,
    _earnings_quality_score,
    _dividend_sustainability_flag,
)

# ── Constants ─────────────────────────────────────────────────────────────────

MARKET_DAILY_VOL = 0.012    # ~1.2% daily vol proxy for market
TRADING_DAYS     = 252
MONTE_CARLO_PATHS = 10_000
MONTE_CARLO_SEED  = 42
_MC_BLOCK    = 20    # block length (days) for the bootstrap — keeps vol clustering
_MC_MIN_OBS  = 60    # min history to block-bootstrap; below this fall back to Normal

# History window for Stage-6 scenario replay. The rest of the engine still runs
# on the trailing 5y (STRESS_HISTORY_PERIOD's frame is sliced down for Stages
# 3/4), but replaying the 2022 drawdown — and, as the cache accrues, older
# crises — needs a longer series.
STRESS_HISTORY_PERIOD = "10y"
QUANT_HISTORY_DAYS    = 5 * 366

# Market proxy for per-holding beta. EURO STOXX 50 is euro-denominated (no FX
# step) and is already the app's European benchmark elsewhere
# (portfolio.backfill_value_history). A euro-based investor's market beta is
# best measured against their home market even for the odd US-listed holding.
BENCHMARK_TICKER = "^STOXX50E"
_BETA_MIN_OBS    = 60       # aligned trading days needed to trust a regression beta
_VOL_MIN_OBS     = 60       # ...and to use a holding's own realised vol over the beta proxy

_LIQ_PARTICIPATION = 0.20   # assume you can trade 20% of a day's average volume
_LIQ_DAYS_FLAG     = 10     # > this many days to exit the position → liquidity flag

# Stage 7 composite weights
_W_DEFAULT = {
    "concentration": 0.25,
    "volatility":    0.20,
    "tail":          0.20,
    "factor":        0.15,
    "fundamental":   0.15,
    "income":        0.05,
}
_W_INCOME = {   # "income_weighted": elevated income-risk weight (a model setting, PER-3)
    "concentration": 0.20,
    "volatility":    0.15,
    "tail":          0.15,
    "factor":        0.10,
    "fundamental":   0.20,
    "income":        0.20,
}

SCORE_LOW      = 25
SCORE_MODERATE = 50
SCORE_ELEVATED = 70
SCORE_HIGH     = 85

# Canonical composite-risk bands — the single source of truth for the 0-100
# score's label, description, and semantic colour tone. `_risk_label_description`
# and the UI colour mappers (`uvalu.components.score_color` /
# `.risk_score_meter_html`) all derive from this table. Each row's first field
# is the band's inclusive upper bound; `tone` keys
# `uvalu.components._RISK_TONE_COLORS`. The green→amber break is SCORE_LOW (25)
# and amber→red is SCORE_ELEVATED (70).
# Legal copy (PER-4): the third field was a recommended action ("Hold —
# monitor quarterly" … "reduce exposure immediately"). It is now a description
# of what the band measures; nothing tells the user what to do.
# Labels and descriptions stay English (they are compared and stored); pages
# show them through uvalu.i18n.tr().
RISK_BANDS: list[tuple[float, str, str, str]] = [
    (SCORE_LOW,      N_("Low risk"),
     N_("Composite risk score 0–25: the lowest band of the model's scale."), "low"),
    (SCORE_MODERATE, N_("Moderate risk"),
     N_("Composite risk score 25–50: below the scale's midpoint."), "moderate"),
    (SCORE_ELEVATED, N_("Elevated risk"),
     N_("Composite risk score 50–70: above the scale's midpoint."), "elevated"),
    (SCORE_HIGH,     N_("High risk"),
     N_("Composite risk score 70–85: the upper band of the model's scale."), "high"),
    (100.0,          N_("Critical risk"),
     N_("Composite risk score above 85: the highest band of the model's scale."), "critical"),
]


def risk_band(score: float) -> tuple[str, str, str]:
    """(label, description, tone) for a 0-100 composite risk score, from `RISK_BANDS`."""
    for upper, label, description, tone in RISK_BANDS:
        if score <= upper:
            return label, description, tone
    _, label, description, tone = RISK_BANDS[-1]
    return label, description, tone


# DIS-3: shown with every risk report. Statistical estimates, not limits.
RISK_DISCLOSURES: list[str] = [
    N_("VaR, CVaR, Monte Carlo and stress-test figures are statistical estimates "
       "based on historical data and model assumptions. Real losses can exceed them."),
    N_("Historical scenarios replay past market moves; future crises can be larger, "
       "longer or different in kind."),
    N_("The composite risk score and its bands describe this portfolio's figures on "
       "the model's scale. They are not a personal risk assessment and do not say "
       "what you should do."),
    N_("Factor data: Kenneth R. French Data Library (Tuck School of Business, Dartmouth)."),
]

# Stage 7 weighting presets, chosen by the user as a model setting (PER-3/PER-8).
WEIGHTINGS = ("standard", "income_weighted")


# The Stage-1/3 quant band words (`_beta_label` / `_vol_label` / `_mdd_label` /
# `_sharpe_label` / `_sortino_label`) mapped onto the same three visual tones the
# composite gauge uses, so "High" volatility reads red and "Low" reads green on
# the Risk page's metric grid instead of flat grey.
_QUANT_LABEL_TONE = {
    "Low": "low", "Moderate": "moderate", "High": "high",
    "Defensive": "low", "Market-like": "moderate", "Aggressive": "high",
    "Strong": "low", "Acceptable": "moderate", "Suboptimal": "high",
}


def band_tone(label: str) -> str:
    """Visual tone (``low`` | ``moderate`` | ``high``) for a quant band word;
    ``""`` when unknown (e.g. ``"N/A"``) so callers fall back to a neutral colour."""
    return _QUANT_LABEL_TONE.get(label, "")

# name, label, benchmark drawdown, window start, window end. The window dates
# gate the "replay the held basket's own drawdown" path in _stage6_stress —
# when port_rets covers a window, that scenario's portfolio_drawdown is the
# basket's real peak-to-trough over it rather than beta × benchmark.
HISTORICAL_SCENARIOS = [
    (N_("Dot-com crash"),        "2000–2002",        -0.49, "2000-03-10", "2002-10-09"),
    (N_("Financial crisis"),     "2007–2009",        -0.57, "2007-10-09", "2009-03-09"),
    (N_("COVID crash"),          N_("Feb–Mar 2020"), -0.34, "2020-02-19", "2020-03-23"),
    (N_("2022 rate hike cycle"), N_("Jan–Oct 2022"), -0.25, "2022-01-03", "2022-10-12"),
]

CYCLICAL_SECTORS = {
    "Consumer Cyclical", "Energy", "Basic Materials",
    "Financial Services", "Industrials", "Real Estate",
}


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class PositionRisk:
    ticker: str
    name: str
    weight: float
    beta: float | None
    var_95_1d_eur: float | None
    vol_annual: float | None        # annualised vol (fraction) — realised from the holding's own EUR series, or |beta| × market vol × √252 as a fallback
    mos: float | None               # margin of safety (fraction)
    valuation_flag: str             # "Above model fair value" | "Near model fair value" | "Below model fair value" | "N/A"
    div_sustainability: str         # "OK" | "At Risk" | ""
    financial_health: float         # 0–10
    earnings_quality: float         # 0–10
    rating: str                     # "Low" | "Medium" | "High" | "Critical"
    veto: bool = False              # real hard veto from the stock valuation algorithm (screener's `veto` column)
    beta_source: str = "yfinance"   # "regression" (own EUR series vs benchmark) | "yfinance" | "default"
    days_to_liquidate: float | None = None   # trading days to exit at LIQ_PARTICIPATION of ADV
    liquidity_flag: bool = False    # True when days_to_liquidate exceeds _LIQ_DAYS_FLAG


@dataclass
class ConcentrationMetrics:
    hhi: float                      # position-level Herfindahl (Σ wᵢ²) — feeds the composite score
    hhi_label: str
    top1_weight: float
    top1_ticker: str
    top3_weight: float
    top5_weight: float
    top1_flag: bool
    top3_flag: bool
    top5_flag: bool
    sector_weights: dict[str, float]
    largest_sector: str | None
    sector_flag: bool
    geo_weights: dict[str, float]
    largest_geo: str | None
    geo_flag: bool
    div_hhi: float | None
    div_top3_pct: float | None
    income_concentration_flag: bool
    sector_hhi: float = 0.0         # sector-level Herfindahl (Σ sector_weight²) — what the Risk page's "Sector HHI" tile shows
    sector_hhi_label: str = "N/A"


@dataclass
class QuantMetrics:
    portfolio_beta: float
    beta_label: str
    volatility_annual: float | None     # fraction, e.g. 0.15 = 15%
    volatility_label: str
    var_95_1d_pct: float | None         # fraction, e.g. -0.03 = -3% (same 1-day 95% VaR as var_95_1d_eur, as a return)
    var_95_1d_eur: float | None
    var_99_1d_eur: float | None
    cvar_95_1d_eur: float | None
    mdd_1y: float | None
    mdd_3y: float | None
    mdd_5y: float | None
    mdd_label: str
    sharpe: float | None
    sortino: float | None
    ratio_label: str                    # describes `sharpe` (the value shown alongside it in the UI)
    corr_matrix: pd.DataFrame | None
    high_corr_pairs: list[tuple[str, str, float]]
    effective_diversification: float | None
    returns_available: bool
    sortino_label: str = "N/A"          # separate, higher-bar label for `sortino`
    # Direct OLS beta of the portfolio return series on the benchmark, when
    # both are available — a cross-check on the weighted-sum `portfolio_beta`.
    portfolio_beta_regression: float | None = None


@dataclass
class FactorExposure:
    available: bool
    loadings: dict[str, float]
    r_squared: float | None
    alpha_annualised: float | None
    flags: list[str]
    factor_set: str | None = None    # "developed" | "us" — which universe was regressed against
    as_of: str | None = None         # ISO date of the newest factor observation used
    stale: bool = False              # True when served from a cached copy, source unreachable
    n_obs: int | None = None         # overlapping days in the regression


@dataclass
class IncomeRisk:
    portfolio_yield: float
    total_annual_income: float
    weighted_dgr: float | None
    top3_income_shares: list[tuple[str, float]]     # (ticker, fraction of total income)
    top3_cut_eur: float | None
    top3_cut_pct: float | None                      # fraction of total income at risk
    income_concentration_flag: bool
    flagged_payers: list[str]
    flagged_income_pct: float
    # Income-share-weighted 0–10 stability over payers with DPS history
    # (payment years + growth streak + no recent cut). None when no payer in
    # the portfolio has usable dividend history yet.
    income_stability: float | None = None


@dataclass
class ScenarioResult:
    name: str
    period: str
    index_drawdown: float | None
    portfolio_drawdown: float | None    # fraction
    portfolio_value_loss: float | None  # €
    method: str = "beta-estimated"      # "replayed" when the held basket's own history covered the window


@dataclass
class MonteCarloResult:
    horizon_years: int
    p05: float
    p25: float
    p50: float
    p75: float
    p95: float
    prob_loss: float


@dataclass
class StressResults:
    historical: list[ScenarioResult]
    factor_scenarios: list[dict]
    mc_1y: MonteCarloResult
    mc_3y: MonteCarloResult
    mc_5y: MonteCarloResult


@dataclass
class CompositeScore:
    score: float
    label: str      # "Low risk" | "Moderate risk" | etc.
    description: str    # what the band means (PER-4: was `action`)
    sub_scores: dict[str, float]    # component name → 0–100
    weighting: str = "standard"     # Stage 7 preset used (see WEIGHTINGS)


# Legal copy (PER-4/PER-5): replaces RebalanceItem / RebalanceSignals. An
# observation states a figure and the reference it was compared with; there is
# no `action` field, so no code path can attach advice to it.
@dataclass
class RiskObservation:
    level: str              # "high" | "notice" (was "hard" | "soft")
    scope: str              # a ticker, sector/pair name, or "Portfolio"
    message: str            # the observation shown in the UI
    basis: str              # "model_reference" | "user_target" | "since_snapshot"
    mode: str = "absolute"  # "absolute" (level check) | "drift" (vs target/prior) | "transition"


@dataclass
class RiskObservations:
    items: list[RiskObservation]


@dataclass
class RiskReport:
    generated_at: str
    portfolio_value: float
    n_positions: int
    position_profiles: list[PositionRisk]
    concentration: ConcentrationMetrics
    quant: QuantMetrics
    factor: FactorExposure
    income: IncomeRisk
    stress: StressResults
    composite: CompositeScore
    observations: RiskObservations
    disclosures: list[str]      # DIS-3 — render with the report


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _safe(val, default=None):
    try:
        f = float(val)
        return f if np.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def _fetch_history(tickers: list[str], period: str = "5y") -> pd.DataFrame:
    """Adjusted daily closes as a DataFrame (date × ticker).

    Thin seam over marketdata.price_history, which serves these from a
    per-ticker disk cache and only refetches each ticker's missing tail.
    Kept as a function here because tests monkeypatch it directly.
    """
    return marketdata.price_history(tickers, period=period)


def _to_eur(closes: pd.DataFrame, cache: dict) -> pd.DataFrame:
    """Restate each ticker's native-currency close series in EUR.

    Without this the portfolio return series is a blend of currencies — a
    USD-quoted holding's daily "return" silently carries the day's USD/EUR
    move, distorting volatility, VaR and cross-holding correlations. Rates are
    ECB reference fixings from frankfurter.dev (fx.py, via the
    marketdata.fx_to_eur_frame shim) — the app's single FX source. A ticker
    whose currency is missing, already EUR, or has no FX history is left as-is
    (better than dropping it from the risk picture entirely).
    """
    if closes is None or closes.empty:
        return closes
    ccy = {
        t: str((cache.get(t) or {}).get("Currency") or "EUR").strip().upper()
        for t in closes.columns
    }
    foreign = sorted({c for c in ccy.values() if c and c != "EUR"})
    if not foreign:
        return closes
    fx = marketdata.fx_to_eur_frame(foreign)
    if fx is None or fx.empty:
        return closes
    out = closes.copy()
    for ticker, code in ccy.items():
        if code in fx.columns:
            rate = fx[code].reindex(out.index).ffill().bfill()
            out[ticker] = out[ticker] * rate
    return out


def _daily_returns(closes: pd.DataFrame) -> pd.DataFrame:
    return closes.pct_change().iloc[1:]


def _mdd(series: pd.Series) -> float | None:
    if series.empty or len(series) < 2:
        return None
    cum = (1 + series).cumprod()
    peak = cum.cummax()
    dd = (cum - peak) / peak
    v = dd.min()
    return float(v) if np.isfinite(v) else None


def _replay_drawdown(port_rets: "pd.Series | None", start: str, end: str,
                     min_coverage: float = 0.6) -> float | None:
    """Worst peak-to-trough drawdown of `port_rets` over [start, end], or None
    when the series doesn't substantially cover that window (starts after it,
    or has < `min_coverage` of its business days)."""
    if port_rets is None or port_rets.empty:
        return None
    w_start, w_end = pd.Timestamp(start), pd.Timestamp(end)
    if port_rets.index.min() > w_start or port_rets.index.max() < w_start:
        return None
    seg = port_rets.loc[w_start:w_end]
    expected = int(np.busday_count(w_start.date(), w_end.date()))
    if expected <= 0 or len(seg) < min_coverage * expected:
        return None
    dd = _mdd(seg)
    return round(float(dd), 4) if dd is not None else None


def _ols_beta(y: np.ndarray, x: np.ndarray) -> float | None:
    """Slope of a simple OLS of y on x (1-D, equal length). None when x has
    essentially no variance (nothing to regress against)."""
    if len(y) < 2:
        return None
    vx = float(np.var(x, ddof=1))
    if not np.isfinite(vx) or vx <= 0:
        return None
    b = float(np.cov(y, x, ddof=1)[0, 1] / vx)
    return b if np.isfinite(b) else None


def _resolve_betas(tickers: list[str], stock_rets: pd.DataFrame,
                   bench_rets: pd.Series | None,
                   cache: dict) -> tuple[dict[str, float], dict[str, str]]:
    """Per-ticker beta with provenance. Preference order:

    1. "regression" — OLS of the holding's own EUR daily returns on the
       benchmark, given ≥ _BETA_MIN_OBS aligned observations.
    2. "yfinance"   — the cached `beta` field (US-market, often stale).
    3. "default"    — 1.0.
    """
    betas: dict[str, float] = {}
    sources: dict[str, str] = {}
    have_bench = bench_rets is not None and not stock_rets.empty
    for t in tickers:
        b = None
        if have_bench and t in stock_rets.columns:
            joined = pd.concat(
                [stock_rets[t].rename("s"), bench_rets.rename("m")], axis=1
            ).dropna()
            if len(joined) >= _BETA_MIN_OBS:
                b = _ols_beta(joined["s"].to_numpy(), joined["m"].to_numpy())
        if b is not None:
            betas[t], sources[t] = round(b, 3), "regression"
            continue
        yb = _safe(cache.get(t, {}).get("beta"))
        if yb is not None:
            betas[t], sources[t] = yb, "yfinance"
        else:
            betas[t], sources[t] = 1.0, "default"
    return betas, sources


# ── Stage 1 — Position-level risk profiling ───────────────────────────────────

def _position_rating(weight: float, beta: float | None, mos: float | None,
                     fin_health: float, earn_quality: float) -> str:
    pts = 0
    if weight > 0.15:     pts += 2
    elif weight > 0.10:   pts += 1
    if beta is not None:
        if beta > 1.5:    pts += 2
        elif beta > 1.3:  pts += 1
    if mos is not None:
        if mos < -0.10:   pts += 2     # overvalued > 10%
        elif mos < 0:     pts += 1
    if fin_health < 3:    pts += 2
    elif fin_health < 5:  pts += 1
    if earn_quality < 3:  pts += 1
    if pts >= 5:  return N_("Critical")
    if pts >= 3:  return N_("High")
    if pts >= 1:  return N_("Medium")
    return N_("Low")


def _stage1_position_profiles(pf: pd.DataFrame, cache: dict,
                               total_value: float,
                               veto_lookup: dict[str, bool] | None = None,
                               *,
                               betas: dict[str, float] | None = None,
                               beta_sources: dict[str, str] | None = None,
                               closes: pd.DataFrame | None = None) -> list[PositionRisk]:
    veto_lookup  = veto_lookup or {}
    beta_sources = beta_sources or {}
    profiles = []
    for _, row in pf.iterrows():
        ticker  = row["ticker"]
        fd      = cache.get(ticker, {})
        fd_ser  = pd.Series(fd)

        weight    = _safe(row.get("current_value"), 0) / total_value if total_value > 0 else 0.0
        pos_value = _safe(row.get("current_value"), 0)

        # Beta: resolved (regression on the holding's own EUR series) when the
        # caller supplied one, else the cached yfinance field.
        if betas is not None and ticker in betas:
            beta     = _safe(betas.get(ticker))
            beta_src = beta_sources.get(ticker, "regression")
        else:
            beta     = _safe(fd.get("beta"))
            beta_src = "yfinance" if beta is not None else "default"

        # Realised annualised vol from the holding's own EUR return series when
        # there's enough history; otherwise the beta × market-vol proxy.
        realised_vol = None
        if closes is not None and not closes.empty and ticker in closes.columns:
            s = closes[ticker].dropna()
            if len(s) >= _VOL_MIN_OBS + 1:
                rv = float(s.pct_change().dropna().std(ddof=1)) * np.sqrt(TRADING_DAYS)
                if np.isfinite(rv) and rv > 0:
                    realised_vol = rv

        if realised_vol is not None:
            vol_annual      = realised_vol
            stock_daily_vol = realised_vol / np.sqrt(TRADING_DAYS)
        else:
            stock_daily_vol = abs(beta if beta is not None else 1.0) * MARKET_DAILY_VOL
            vol_annual      = stock_daily_vol * np.sqrt(TRADING_DAYS)
        var_95 = pos_value * stock_daily_vol * 1.645

        # Valuation flag from fair value vs live price
        price = _safe(row.get("live_price"))
        fv    = _safe(row.get("fair_value"))
        if price and fv and fv > 0:
            mos = (fv - price) / fv
            # Legal copy: named after the comparison it makes. "Undervalued"
            # here (MoS ≥ 10%) would clash with the screener's model signal of
            # the same name, which also needs a high composite score — the same
            # stock could read "Undervalued" on one screen and "Neutral" on the
            # other (REC-2).
            val_flag = (N_("Above model fair value") if mos < -0.05 else
                        N_("Near model fair value") if mos < 0.10 else N_("Below model fair value"))
        else:
            mos      = None
            val_flag = N_("N/A")

        fh     = _financial_health_score(fd_ser)
        eq     = _earnings_quality_score(fd_ser)
        ds     = _dividend_sustainability_flag(fd_ser)
        rating = _position_rating(weight, beta, mos, fh, eq)

        # Days to exit this position at _LIQ_PARTICIPATION of average daily
        # volume — position-size aware, unlike the screener's volume-only score.
        adv    = _safe(fd.get("averageVolume"))
        px_now = _safe(row.get("live_price"))
        dtl    = None
        if adv and adv > 0 and px_now and px_now > 0 and pos_value > 0:
            shares_held = pos_value / px_now
            dtl = round(shares_held / (adv * _LIQ_PARTICIPATION), 2)

        profiles.append(PositionRisk(
            ticker=ticker,
            name=str(row.get("name", ticker)),
            weight=weight,
            beta=beta,
            var_95_1d_eur=round(var_95, 2) if var_95 else None,
            vol_annual=round(vol_annual, 4) if vol_annual else None,
            mos=round(mos, 4) if mos is not None else None,
            valuation_flag=val_flag,
            div_sustainability=ds,
            financial_health=round(fh, 1),
            earnings_quality=round(eq, 1),
            rating=rating,
            veto=bool(veto_lookup.get(ticker, False)),
            beta_source=beta_src,
            days_to_liquidate=dtl,
            liquidity_flag=bool(dtl is not None and dtl > _LIQ_DAYS_FLAG),
        ))
    return profiles


# ── Stage 2 — Concentration & diversification ─────────────────────────────────

def _hhi_label(hhi: float) -> str:
    if hhi < 0.10:  return N_("Well diversified")
    if hhi < 0.18:  return N_("Moderately concentrated")
    return N_("Highly concentrated")


def _category_label(v: object) -> str:
    """Sector / country bucket name — NaN-safe. A DataFrame cell with no value
    arrives as a float NaN, which is truthy in Python, so `v or "Unknown"`
    let the literal string "nan" leak into the labels and flag text (the
    recurring gotcha noted across this codebase). Empty strings collapse to
    "Unknown" too."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return N_("Unknown")
    return str(v).strip() or N_("Unknown")


def _stage2_concentration(pf: pd.DataFrame, total_value: float) -> ConcentrationMetrics:
    _empty = ConcentrationMetrics(
        hhi=0.0, hhi_label="N/A", top1_weight=0.0, top1_ticker="",
        top3_weight=0.0, top5_weight=0.0, top1_flag=False, top3_flag=False,
        top5_flag=False, sector_weights={}, largest_sector=None, sector_flag=False,
        geo_weights={}, largest_geo=None, geo_flag=False,
        div_hhi=None, div_top3_pct=None, income_concentration_flag=False,
        sector_hhi=0.0, sector_hhi_label="N/A",
    )
    if total_value <= 0:
        return _empty

    values  = pf["current_value"].fillna(0).values
    tickers = pf["ticker"].values
    weights = values / total_value
    order   = np.argsort(weights)[::-1]
    ws, ts  = weights[order], tickers[order]

    hhi  = float(np.sum(ws ** 2))
    top1 = float(ws[0]) if len(ws) >= 1 else 0.0
    top3 = float(np.sum(ws[:3]))
    top5 = float(np.sum(ws[:5]))

    # Sector weights
    sec_map: dict[str, float] = {}
    for _, row in pf.iterrows():
        sec = _category_label(row.get("sector"))
        val = _safe(row.get("current_value"), 0)
        sec_map[sec] = sec_map.get(sec, 0.0) + val / total_value
    sec_map = {k: round(v, 4) for k, v in sorted(sec_map.items(), key=lambda x: -x[1])}
    largest_sector = next(iter(sec_map), None)
    sec_vals = list(sec_map.values())
    # Sector-level Herfindahl (Σ sector_weight²) — the real "how concentrated
    # across sectors" number, distinct from `hhi` above which is the
    # position-count Herfindahl. The Risk page's "Sector HHI" tile shows this.
    sector_hhi = float(sum(v ** 2 for v in sec_vals))
    sector_flag = bool(
        (largest_sector and sec_map.get(largest_sector, 0) > 0.30)
        or (len(sec_vals) >= 2 and sec_vals[0] + sec_vals[1] > 0.50)
    )

    # Geographic weights
    geo_map: dict[str, float] = {}
    for _, row in pf.iterrows():
        geo = _category_label(row.get("country"))
        val = _safe(row.get("current_value"), 0)
        geo_map[geo] = geo_map.get(geo, 0.0) + val / total_value
    geo_map = {k: round(v, 4) for k, v in sorted(geo_map.items(), key=lambda x: -x[1])}
    largest_geo = next(iter(geo_map), None)
    geo_flag    = bool(largest_geo and geo_map.get(largest_geo, 0) > 0.60)

    # Dividend income concentration
    income_col  = pf["expected_annual"].fillna(0) if "expected_annual" in pf.columns else pd.Series(0.0, index=pf.index)
    total_income = float(income_col.sum())
    if total_income > 0:
        inc_shares = income_col / total_income
        div_hhi    = float((inc_shares ** 2).sum())
        top3_inc   = float(inc_shares.nlargest(3).sum())
    else:
        div_hhi  = None
        top3_inc = None

    return ConcentrationMetrics(
        hhi=round(hhi, 4),
        hhi_label=_hhi_label(hhi),
        top1_weight=round(top1, 4),
        top1_ticker=str(ts[0]) if len(ts) >= 1 else "",
        top3_weight=round(top3, 4),
        top5_weight=round(top5, 4),
        top1_flag=top1 > 0.15,
        top3_flag=top3 > 0.35,
        top5_flag=top5 > 0.50,
        sector_weights=sec_map,
        largest_sector=largest_sector,
        sector_flag=sector_flag,
        geo_weights=geo_map,
        largest_geo=largest_geo,
        geo_flag=geo_flag,
        div_hhi=round(div_hhi, 4) if div_hhi is not None else None,
        div_top3_pct=round(top3_inc, 4) if top3_inc is not None else None,
        income_concentration_flag=bool(top3_inc and top3_inc > 0.50),
        sector_hhi=round(sector_hhi, 4),
        sector_hhi_label=_hhi_label(sector_hhi),
    )


# ── Stage 3 — Portfolio-level quantitative metrics ────────────────────────────

def _beta_label(b: float) -> str:
    if b < 0.8:  return N_("Defensive")
    if b < 1.2:  return N_("Market-like")
    return N_("Aggressive")

def _vol_label(v: float) -> str:
    if v < 0.10:  return N_("Low")
    if v < 0.20:  return N_("Moderate")
    return N_("High")

def _mdd_label(mdd: float | None) -> str:
    if mdd is None:  return N_("N/A")
    v = abs(mdd)
    if v < 0.10:  return N_("Low")
    if v < 0.25:  return N_("Moderate")
    return N_("High")

def _sharpe_label(sharpe: float | None) -> str:
    if sharpe is None:  return N_("N/A")
    if sharpe > 1.5:    return N_("Strong")
    if sharpe > 1.0:    return N_("Acceptable")
    return N_("Suboptimal")


def _sortino_label(sortino: float | None) -> str:
    # Sortino uses downside deviation only, which is ≤ total volatility by
    # construction, so it runs structurally higher than Sharpe for the same
    # portfolio — reusing Sharpe's bands would make "Strong" too easy to clear.
    if sortino is None:  return "N/A"
    if sortino > 2.0:    return "Strong"
    if sortino > 1.5:    return "Acceptable"
    return "Suboptimal"


def _weights_for_tickers(pf: pd.DataFrame, tickers: list[str],
                         total_value: float) -> np.ndarray:
    w = np.array([
        _safe(pf.loc[pf["ticker"] == t, "current_value"].values[0], 0.0)
        for t in tickers
    ], dtype=float)
    s = w.sum()
    return w / s if s > 0 else np.ones(len(tickers)) / max(len(tickers), 1)


def _stage3_quant(pf: pd.DataFrame, cache: dict, total_value: float,
                  closes: pd.DataFrame, *,
                  betas: dict[str, float] | None = None,
                  portfolio_beta_regression: float | None = None) -> QuantMetrics:
    tickers = pf["ticker"].tolist()
    if betas is not None:
        beta_arr = np.array([_safe(betas.get(t), 1.0) for t in tickers])
    else:
        beta_arr = np.array([_safe(cache.get(t, {}).get("beta"), 1.0) for t in tickers])
    weights = _weights_for_tickers(pf, tickers, total_value)
    port_beta = float(np.dot(weights, beta_arr))

    _no_history = QuantMetrics(
        portfolio_beta=round(port_beta, 2), beta_label=_beta_label(port_beta),
        volatility_annual=None, volatility_label="N/A",
        var_95_1d_pct=None, var_95_1d_eur=None, var_99_1d_eur=None, cvar_95_1d_eur=None,
        mdd_1y=None, mdd_3y=None, mdd_5y=None, mdd_label="N/A",
        sharpe=None, sortino=None, ratio_label="N/A", sortino_label="N/A",
        corr_matrix=None, high_corr_pairs=[], effective_diversification=None,
        returns_available=False,
        portfolio_beta_regression=portfolio_beta_regression,
    )

    if closes.empty:
        return _no_history

    avail = [t for t in tickers if t in closes.columns]
    if not avail:
        return _no_history

    aw = _weights_for_tickers(pf, avail, total_value)
    dr = _daily_returns(closes[avail].dropna(how="all")).dropna(how="all")
    if len(dr) < 20:
        return _no_history

    port_rets = (dr.fillna(0).values @ aw)

    sigma_d  = float(np.std(port_rets, ddof=1))
    vol_ann  = sigma_d * np.sqrt(TRADING_DAYS)

    var_95_pct  = float(np.percentile(port_rets, 5))
    var_99_pct  = float(np.percentile(port_rets, 1))
    tail_mask   = port_rets <= var_95_pct
    cvar_95_pct = float(port_rets[tail_mask].mean()) if tail_mask.any() else var_95_pct

    s = pd.Series(port_rets, index=dr.index)
    mdd_1y = _mdd(s.iloc[-252:])
    mdd_3y = _mdd(s.iloc[-756:])
    mdd_5y = _mdd(s)

    rf_d          = RISK_FREE_RATE / TRADING_DAYS
    excess        = port_rets - rf_d
    mean_excess_a = float(np.mean(excess)) * TRADING_DAYS
    sharpe        = mean_excess_a / vol_ann if vol_ann > 0 else None

    down = port_rets[port_rets < rf_d]
    sortino = (mean_excess_a / (float(np.std(down, ddof=1)) * np.sqrt(TRADING_DAYS))
               if len(down) > 1 else None)

    corr = dr.iloc[-252:].fillna(0).corr() if len(dr) >= 20 else None

    high_corr: list[tuple[str, str, float]] = []
    if corr is not None:
        cols = list(corr.columns)
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                c = corr.iloc[i, j]
                if np.isfinite(c) and c > 0.80:
                    high_corr.append((cols[i], cols[j], round(float(c), 3)))

    # Weight-weighted average pairwise correlation — weights each pair by
    # w_i × w_j so a correlation between two large positions counts more
    # than one between two negligible ones, reflecting the portfolio actually
    # held rather than just the list of tickers in it.
    eff_div: float | None = None
    if corr is not None and len(corr) > 1:
        i_idx, j_idx = np.triu_indices_from(corr.values, k=1)
        pair_corr = corr.values[i_idx, j_idx]
        pair_w    = aw[i_idx] * aw[j_idx]
        mask      = np.isfinite(pair_corr) & (pair_w > 0)
        if mask.any():
            weighted_corr = float(np.average(pair_corr[mask], weights=pair_w[mask]))
            eff_div = round(1.0 - weighted_corr, 3)

    return QuantMetrics(
        portfolio_beta=round(port_beta, 2),
        beta_label=_beta_label(port_beta),
        volatility_annual=round(float(vol_ann), 4),
        volatility_label=_vol_label(float(vol_ann)),
        var_95_1d_pct=round(min(0.0, var_95_pct), 4),
        var_95_1d_eur=round(max(0.0, -var_95_pct) * total_value, 2),
        var_99_1d_eur=round(max(0.0, -var_99_pct) * total_value, 2),
        cvar_95_1d_eur=round(max(0.0, -cvar_95_pct) * total_value, 2),
        mdd_1y=round(float(mdd_1y), 4) if mdd_1y is not None else None,
        mdd_3y=round(float(mdd_3y), 4) if mdd_3y is not None else None,
        mdd_5y=round(float(mdd_5y), 4) if mdd_5y is not None else None,
        # Tier word must describe the same window as the number shown next to
        # it — the Risk page renders `mdd_1y` under a "(1Y)" heading, so the
        # label is derived from the 1Y drawdown (falling back to 5Y only when
        # there isn't a full year of history). The composite score still uses
        # the deeper 5Y figure independently (see _stage7_composite).
        mdd_label=_mdd_label(mdd_1y if mdd_1y is not None else mdd_5y),
        sharpe=round(float(sharpe), 2) if sharpe is not None else None,
        sortino=round(float(sortino), 2) if sortino is not None else None,
        ratio_label=_sharpe_label(sharpe),
        sortino_label=_sortino_label(sortino),
        corr_matrix=corr,
        high_corr_pairs=high_corr,
        effective_diversification=eff_div,
        returns_available=True,
        portfolio_beta_regression=portfolio_beta_regression,
    )


# ── Stage 4 — Factor exposure (Fama-French 5-factor + momentum) ──────────────

_FF_BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"

# Factor universes, tried in order. "developed" is the better match for a
# euro-based portfolio of multinationals; "us" is the long-standing fallback
# used if the Developed files are unreachable. (Both are USD-constructed with a
# US risk-free; the regression subtracts the file's own RF and stays internally
# consistent — see the risk-engine plan, WS-2/WS-5.)
_FACTOR_SETS = [
    ("developed", _FF_BASE + "Developed_5_Factors_Daily_CSV.zip",
                  _FF_BASE + "Developed_Mom_Factor_Daily_CSV.zip"),
    ("us",        _FF_BASE + "F-F_Research_Data_5_Factors_2x3_Daily_CSV.zip",
                  _FF_BASE + "F-F_Momentum_Factor_Daily_CSV.zip"),
]

_FACTORS_DIR         = Path(__file__).parent / ".cache" / "factors"
_FACTOR_MAX_AGE_DAYS = 7

# In-process cache so we only download once per session
_ff_cache: dict[str, pd.DataFrame] = {}


def _fetch_ff_csv(url: str) -> pd.DataFrame:
    """Download a Ken French CSV zip and return a daily-return DataFrame."""
    if url in _ff_cache:
        return _ff_cache[url]
    import io, zipfile, urllib.request
    with urllib.request.urlopen(url, timeout=15) as resp:
        data = resp.read()
    zf   = zipfile.ZipFile(io.BytesIO(data))
    name = zf.namelist()[0]
    raw  = zf.read(name).decode("latin-1")
    # FF CSV files have a header block of text lines before the data;
    # the data section starts where lines match "YYYYMMDD,..." pattern.
    lines = raw.splitlines()
    start = next(i for i, l in enumerate(lines) if l and l[0].isdigit())
    # Find end of the daily section (blank line or line starting with non-digit marks next section)
    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i].strip()
        if not stripped:
            end = i
            break
        if stripped and not stripped[0].isdigit():
            end = i
            break
    csv_text = "\n".join(lines[start:end])
    df = pd.read_csv(io.StringIO(csv_text), header=None)
    df.columns = ["Date"] + [c.strip() for c in
                              pd.read_csv(io.StringIO("\n".join(lines[start-1:start])),
                                          header=None).iloc[0, 1:].tolist()]
    df["Date"] = pd.to_datetime(df["Date"].astype(str), format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["Date"]).set_index("Date")
    df = df.apply(pd.to_numeric, errors="coerce") / 100.0
    _ff_cache[url] = df
    return df


def _factor_cache_path(kind: str, setname: str) -> Path:
    return _FACTORS_DIR / f"{setname}_{kind}.csv"


def _read_factor_cache(kind: str, *, max_age_days: float | None):
    """Newest on-disk factor frame for `kind` ('5f'|'mom'), preferring the
    earlier _FACTOR_SETS entries. Returns (df, setname) or None. `max_age_days`
    None accepts any age (the stale-fallback path)."""
    for setname, *_ in _FACTOR_SETS:
        p = _factor_cache_path(kind, setname)
        if not p.exists():
            continue
        if max_age_days is not None:
            try:
                if (time.time() - p.stat().st_mtime) / 86400 >= max_age_days:
                    continue
            except OSError:
                continue
        try:
            df = pd.read_csv(p, index_col=0, parse_dates=True)
            if not df.empty:
                return df, setname
        except Exception:
            continue
    return None


def _write_factor_cache(kind: str, setname: str, df: pd.DataFrame) -> None:
    try:
        _FACTORS_DIR.mkdir(parents=True, exist_ok=True)
        p   = _factor_cache_path(kind, setname)
        tmp = p.with_suffix(".csv.tmp")
        df.to_csv(tmp)
        tmp.replace(p)
    except Exception:
        pass


def _as_of(df: pd.DataFrame | None) -> str | None:
    if df is None or df.empty:
        return None
    try:
        return pd.Timestamp(df.index.max()).date().isoformat()
    except Exception:
        return None


def _factor_data(kind: str) -> tuple[pd.DataFrame | None, dict]:
    """(daily factor-return DataFrame, meta) for `kind` in {'5f','mom'}.

    Disk cache first (< _FACTOR_MAX_AGE_DAYS old), then each _FACTOR_SETS entry
    in turn via _fetch_ff_csv, writing a fresh CSV on success. If every network
    attempt fails, the newest stale CSV on disk is served. meta keys:
    set, as_of (last date in the frame), stale, source.
    """
    url_idx = 0 if kind == "5f" else 1

    fresh = _read_factor_cache(kind, max_age_days=_FACTOR_MAX_AGE_DAYS)
    if fresh is not None:
        df, setname = fresh
        return df, {"set": setname, "as_of": _as_of(df), "stale": False, "source": "disk"}

    last_err: Exception | None = None
    for setname, *urls in _FACTOR_SETS:
        try:
            df = _fetch_ff_csv(urls[url_idx])
            _write_factor_cache(kind, setname, df)
            return df, {"set": setname, "as_of": _as_of(df), "stale": False, "source": "network"}
        except Exception as e:                     # noqa: BLE001 — try the next set
            last_err = e

    stale = _read_factor_cache(kind, max_age_days=None)
    if stale is not None:
        df, setname = stale
        return df, {"set": setname, "as_of": _as_of(df), "stale": True,
                    "source": "disk", "error": str(last_err)}
    return None, {"set": None, "as_of": None, "stale": True, "source": None,
                  "error": str(last_err)}


def _stage4_factor(port_rets: pd.Series | None) -> FactorExposure:
    _unavail = FactorExposure(available=False, loadings={}, r_squared=None,
                              alpha_annualised=None, flags=[])

    if port_rets is None or len(port_rets) < 60:
        _unavail.flags = [lazy_("Insufficient price history for factor analysis (need ≥60 days)")]
        return _unavail

    ff_df, ff_meta = _factor_data("5f")
    if ff_df is None:
        _unavail.flags = [lazy_("Fama-French data unavailable: {error}", error=str(ff_meta.get('error', 'no data')))]
        return _unavail
    ff = ff_df.loc[port_rets.index[0]:port_rets.index[-1]]

    # Optionally add the momentum factor
    mom_df, _mom_meta = _factor_data("mom")
    if mom_df is not None:
        try:
            mom = mom_df.loc[port_rets.index[0]:port_rets.index[-1]]
            ff  = ff.join(mom.iloc[:, [0]].rename(columns={mom.columns[0]: "WML"}), how="left")
        except Exception:
            pass

    merged = ff.join(port_rets.rename("port"), how="inner").dropna()
    if len(merged) < 30:
        _unavail.flags = [lazy_("Insufficient overlapping data after alignment")]
        return _unavail

    factor_cols = [c for c in merged.columns if c not in ("RF", "port")]
    Y = (merged["port"] - merged["RF"]).values
    X = np.column_stack([np.ones(len(Y)), merged[factor_cols].values])

    coeffs = np.linalg.lstsq(X, Y, rcond=None)[0]
    alpha  = float(coeffs[0])
    betas_ = coeffs[1:]

    y_hat  = X @ coeffs
    ss_res = float(np.sum((Y - y_hat) ** 2))
    ss_tot = float(np.sum((Y - Y.mean()) ** 2))
    r2     = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    loadings = {name: round(float(b), 3) for name, b in zip(factor_cols, betas_)}

    flags: list[str] = []
    for name, b in loadings.items():
        if abs(b) > 1.5:
            flags.append(lazy_("High {factor} loading ({value}) — concentrated factor bet",
                               factor=name, value=Fmt("num", b, decimals=2, signed=True)))

    # Each factor's share of *return variance* (doc: ">60% of return variance
    # explained by one factor"), not just of the summed loadings — Var(β·X) =
    # β² × Var(X), normalised by the portfolio's own return variance. Ignores
    # cross-factor covariance (an uncorrelated-factors approximation), but
    # unlike a plain |β|×std proxy it's actually in variance units.
    f_vars = merged[factor_cols].var().values
    var_y  = float(np.var(Y, ddof=1))
    factor_var_contrib = (betas_ ** 2) * f_vars
    if var_y > 0:
        dom_idx   = int(np.argmax(factor_var_contrib))
        dom_share = factor_var_contrib[dom_idx] / var_y
        if dom_share > 0.60 and r2 > 0.40:
            dom_name = factor_cols[dom_idx]
            flags.append(lazy_("{factor} explains >{share} of return variance",
                               factor=dom_name, share=Fmt("pct", float(dom_share), decimals=0, fraction=True)))

    n_overlap = len(merged)
    if ff_meta.get("stale"):
        flags.append(lazy_("Factor data is a cached copy ({set} set, as of {date}) — source unreachable",
                           set=str(ff_meta.get('set')), date=Fmt("date", ff_meta.get('as_of'))))

    return FactorExposure(
        available=True,
        loadings=loadings,
        r_squared=round(float(r2), 3),
        alpha_annualised=round(alpha * TRADING_DAYS, 4),
        flags=flags,
        factor_set=ff_meta.get("set"),
        as_of=ff_meta.get("as_of"),
        stale=bool(ff_meta.get("stale")),
        n_obs=n_overlap,
    )


# ── Stage 5 — Dividend & income risk ─────────────────────────────────────────

def _stage5_income(pf: pd.DataFrame, cache: dict, total_value: float) -> IncomeRisk:
    income_col   = pf["expected_annual"].fillna(0) if "expected_annual" in pf.columns else pd.Series(0.0, index=pf.index)
    total_income = float(income_col.sum())
    port_yield   = total_income / total_value if total_value > 0 else 0.0

    # Weighted DGR — true DPS CAGR when the fundamentals cache carries it,
    # earningsGrowth proxy otherwise.
    dgr_parts: list[float] = []
    for _, row in pf.iterrows():
        inc = _safe(income_col.loc[row.name], 0.0)
        fd  = cache.get(row["ticker"], {})
        dgr = _safe(fd.get("true_dgr"))
        if dgr is None:
            dgr = _safe(fd.get("earningsGrowth"))
        if dgr is not None and total_income > 0 and inc > 0:
            dgr_parts.append(inc / total_income * dgr)
    weighted_dgr = float(sum(dgr_parts)) if dgr_parts else None

    # Income-share-weighted stability over payers with real DPS history
    # (payment years + growth streak + no cut in the last 5 complete years).
    _now_year  = datetime.now(timezone.utc).year
    stab_parts: list[float] = []
    for _, row in pf.iterrows():
        inc = _safe(income_col.loc[row.name], 0.0)
        if total_income <= 0 or inc <= 0:
            continue
        fd = cache.get(row["ticker"], {})
        py = _safe(fd.get("dividend_payment_years"))
        gs = _safe(fd.get("dividend_growth_streak"))
        if py is None and gs is None:
            continue                       # no history — don't fabricate a score
        last_cut = _safe(fd.get("dividend_last_cut_year"))
        recent_cut = last_cut is not None and last_cut >= _now_year - 5
        sc = (min(py or 0.0, 10) * 0.4
              + min(gs or 0.0, 10) * 0.4
              + (0.0 if recent_cut else 2.0))
        stab_parts.append(inc / total_income * _clamp(sc, 0, 10))
    income_stability = round(float(sum(stab_parts)), 2) if stab_parts else None

    # Top-3 dividend income contributors
    pairs = list(zip(pf["ticker"].tolist(), income_col.tolist()))
    pairs.sort(key=lambda x: -x[1])
    top3 = pairs[:3]
    top3_total = sum(inc for _, inc in top3)
    top3_shares = [(t, round(inc / total_income, 4) if total_income > 0 else 0.0)
                   for t, inc in top3]

    # Payout sustainability flags
    flagged_payers: list[str] = []
    flagged_income  = 0.0
    for _, row in pf.iterrows():
        t    = row["ticker"]
        fd   = cache.get(t, {})
        ds   = _dividend_sustainability_flag(pd.Series(fd))
        payout   = _safe(fd.get("payoutRatio"))
        cpr      = _safe(fd.get("cashPayoutRatio"))
        coverage = _safe(fd.get("dividendCoverage"))
        div_rate = _safe(fd.get("trailingAnnualDividendRate") or fd.get("dividendRate"))
        if div_rate and div_rate > 0:
            if (ds == "At Risk"
                    or (payout is not None and payout > 0.90)
                    or (cpr is not None and cpr > 0.80)
                    or (coverage is not None and coverage < 1.2)):
                flagged_payers.append(t)
                flagged_income += _safe(income_col.loc[row.name], 0.0)

    flagged_pct = flagged_income / total_income if total_income > 0 else 0.0

    return IncomeRisk(
        portfolio_yield=round(port_yield, 4),
        total_annual_income=round(total_income, 2),
        weighted_dgr=round(weighted_dgr, 4) if weighted_dgr is not None else None,
        top3_income_shares=top3_shares,
        top3_cut_eur=round(top3_total * 0.50, 2) if top3_total > 0 else None,
        top3_cut_pct=round(top3_total / total_income * 0.50, 4) if total_income > 0 else None,
        income_concentration_flag=bool(total_income > 0 and top3_total / total_income > 0.50),
        flagged_payers=flagged_payers,
        flagged_income_pct=round(flagged_pct, 4),
        income_stability=income_stability,
    )


# ── Stage 6 — Stress testing & scenario analysis ──────────────────────────────

def _stage6_stress(pf: pd.DataFrame, cache: dict, portfolio_beta: float,
                   total_value: float, port_rets: pd.Series | None,
                   concentration: ConcentrationMetrics) -> StressResults:

    # 6a. Historical scenarios — replay the held basket's own drawdown over any
    # window its return history covers; beta × benchmark drawdown elsewhere.
    historical: list[ScenarioResult] = []
    for name, period, idx_dd, w_start, w_end in HISTORICAL_SCENARIOS:
        replayed = _replay_drawdown(port_rets, w_start, w_end)
        if replayed is not None:
            dd, method = replayed, "replayed"
        else:
            dd, method = round(portfolio_beta * idx_dd, 4), "beta-estimated"
        historical.append(ScenarioResult(
            name=name, period=period, index_drawdown=idx_dd,
            portfolio_drawdown=dd,
            portfolio_value_loss=round(abs(dd) * total_value, 2),
            method=method,
        ))

    # 6b. Factor / hypothetical scenarios
    factor_scenarios: list[dict] = []

    # Rate rise +200 bps — high P/E = long duration = more sensitive
    rate_impacts = []
    for _, row in pf.iterrows():
        t  = row["ticker"]
        pe = _safe(cache.get(t, {}).get("trailingPE"))
        w  = _safe(row.get("current_value"), 0.0) / total_value if total_value > 0 else 0.0
        if pe and 0 < pe < 500:
            dur = min(pe / 20.0, 3.0)
            rate_impacts.append(w * dur * (-0.12))
    rate_impact = float(sum(rate_impacts)) if rate_impacts else -0.10
    factor_scenarios.append({
        "name": lazy_("Rate rise +200 bps"),
        "description": lazy_("High P/E stocks repriced via discount rate expansion (duration proxy)"),
        "estimated_portfolio_impact": round(rate_impact, 4),
        "estimated_loss_eur": round(abs(rate_impact) * total_value, 2),
    })

    # Recession — cyclical sectors cut 25%, defensives 10%
    rec_impact = 0.0
    for _idx, row in pf.iterrows():
        sec = str(row.get("sector") or "")
        w   = _safe(row.get("current_value"), 0.0) / total_value if total_value > 0 else 0.0
        rec_impact += w * (-0.25 if sec in CYCLICAL_SECTORS else -0.10)
    factor_scenarios.append({
        "name": lazy_("Recession (earnings cut 20–30%)"),
        "description": lazy_("25% EPS hit in cyclicals, 10% in defensives; P/E multiples compressed"),
        "estimated_portfolio_impact": round(rec_impact, 4),
        "estimated_loss_eur": round(abs(rec_impact) * total_value, 2),
    })

    # Largest sector −40% crash
    sec_w      = concentration.sector_weights.get(concentration.largest_sector or "", 0.0)
    sec_impact = sec_w * (-0.40)
    factor_scenarios.append({
        "name": lazy_("Sector crash −40% ({sector})",
                      sector=Fmt("tr", concentration.largest_sector or "N/A")),
        "description": lazy_("40% drawdown applied to {sector} sector",
                             sector=(Fmt("tr", concentration.largest_sector) if concentration.largest_sector
                                     else lazy_("largest"))),
        "estimated_portfolio_impact": round(sec_impact, 4),
        "estimated_loss_eur": round(abs(sec_impact) * total_value, 2),
    })

    # Credit crunch — penalise high-leverage positions
    credit_impact = 0.0
    for _idx, row in pf.iterrows():
        t  = row["ticker"]
        de = _safe(cache.get(t, {}).get("debtToEquity"))
        w  = _safe(row.get("current_value"), 0.0) / total_value if total_value > 0 else 0.0
        if de is not None:
            de_ratio = de / 100.0   # yfinance stores as ×100
            credit_impact += w * (-min(de_ratio * 0.05, 0.30))
    factor_scenarios.append({
        "name": lazy_("Credit crunch"),
        "description": lazy_("Leveraged positions repriced — high D/E stocks penalised"),
        "estimated_portfolio_impact": round(credit_impact, 4),
        "estimated_loss_eur": round(abs(credit_impact) * total_value, 2),
    })

    # Dividend freeze — total income loss
    income_col   = pf["expected_annual"].fillna(0) if "expected_annual" in pf.columns else pd.Series(0.0, index=pf.index)
    total_income = float(income_col.sum())
    factor_scenarios.append({
        "name": lazy_("Dividend freeze"),
        "description": lazy_("All dividend payments suspended"),
        "estimated_portfolio_impact": 0.0,
        "estimated_loss_eur": round(total_income, 2),
        "note": lazy_("Annual income impact: {amount}",
                      amount=Fmt("money", total_income, decimals=0, currency="EUR")),
    })

    # 6c. Monte Carlo — block-bootstrap the portfolio's own daily returns
    # (keeps the realised fat tails and volatility clustering that an iid-Normal
    # draw throws away), re-centred on a CAPM drift so the forward mean is an
    # explicit assumption rather than an extrapolation of the trailing period.
    mc_drift = (RISK_FREE_RATE + portfolio_beta * EQUITY_RISK_PREMIUM) / TRADING_DAYS

    def _mc(years: int) -> MonteCarloResult:
        rng  = np.random.default_rng(MONTE_CARLO_SEED)
        days = years * TRADING_DAYS
        if port_rets is not None and len(port_rets) >= _MC_MIN_OBS:
            r   = port_rets.to_numpy(dtype=float)
            r   = r - float(r.mean()) + mc_drift          # re-centre on CAPM drift
            blk      = min(_MC_BLOCK, len(r))
            n_starts = len(r) - blk + 1
            n_blocks = -(-days // blk)                    # ceil
            starts   = rng.integers(0, n_starts, size=MONTE_CARLO_PATHS * n_blocks)
            gathered = r[starts[:, None] + np.arange(blk)]  # (paths·n_blocks, blk)
            paths    = gathered.reshape(MONTE_CARLO_PATHS, n_blocks * blk)[:, :days]
        else:
            sigma = portfolio_beta * MARKET_DAILY_VOL
            paths = rng.normal(mc_drift, sigma, size=(MONTE_CARLO_PATHS, days))
        cum = np.prod(1.0 + np.clip(paths, -0.5, 1.0), axis=1) - 1.0
        return MonteCarloResult(
            horizon_years=years,
            p05=round(float(np.percentile(cum,  5)), 4),
            p25=round(float(np.percentile(cum, 25)), 4),
            p50=round(float(np.percentile(cum, 50)), 4),
            p75=round(float(np.percentile(cum, 75)), 4),
            p95=round(float(np.percentile(cum, 95)), 4),
            prob_loss=round(float(np.mean(cum < 0)), 4),
        )

    return StressResults(
        historical=historical,
        factor_scenarios=factor_scenarios,
        mc_1y=_mc(1), mc_3y=_mc(3), mc_5y=_mc(5),
    )


# ── Stage 7 — Composite portfolio risk score ──────────────────────────────────

def _score_concentration(c: ConcentrationMetrics) -> float:
    s = 0.0
    if c.hhi >= 0.18:     s += 35
    elif c.hhi >= 0.10:   s += 18
    if c.top1_flag:       s += 20
    if c.top3_flag:       s += 15
    if c.top5_flag:       s += 10
    if c.sector_flag:     s += 15
    if c.geo_flag:        s += 10
    if c.income_concentration_flag: s += 5
    return _clamp(s, 0, 100)


def _score_volatility(q: QuantMetrics) -> float:
    s = 0.0
    if q.portfolio_beta > 1.5:     s += 35
    elif q.portfolio_beta > 1.2:   s += 20
    elif q.portfolio_beta < 0.8:   s += 5
    if q.volatility_annual is not None:
        if q.volatility_annual > 0.25:   s += 35
        elif q.volatility_annual > 0.15: s += 20
        elif q.volatility_annual > 0.10: s += 10
    mdd = q.mdd_5y if q.mdd_5y is not None else (q.mdd_3y if q.mdd_3y is not None else q.mdd_1y)
    if mdd is not None:
        v = abs(mdd)
        if v > 0.30:    s += 30
        elif v > 0.20:  s += 15
        elif v > 0.10:  s += 5
    return _clamp(s, 0, 100)


def _score_tail(q: QuantMetrics, stress: StressResults) -> float:
    s = 0.0
    if q.cvar_95_1d_eur is not None and q.var_95_1d_eur is not None and q.var_95_1d_eur > 0:
        ratio = q.cvar_95_1d_eur / q.var_95_1d_eur
        if ratio > 1.5:    s += 20
        elif ratio > 1.2:  s += 10
    p05 = stress.mc_1y.p05
    if p05 < -0.40:    s += 40
    elif p05 < -0.25:  s += 25
    elif p05 < -0.10:  s += 10
    pl = stress.mc_1y.prob_loss
    if pl > 0.35:    s += 30
    elif pl > 0.25:  s += 15
    elif pl > 0.15:  s += 5
    worst = min((r.portfolio_drawdown for r in stress.historical
                 if r.portfolio_drawdown is not None), default=0.0)
    if worst < -0.40:    s += 10
    elif worst < -0.25:  s += 5
    return _clamp(s, 0, 100)


def _score_factor(f: FactorExposure) -> float:
    if not f.available:
        return 50.0     # placeholder for the sub-score display; _stage7 drops the slot
    s = 0.0
    s += sum(20 for b in f.loadings.values() if abs(b) > 1.5)
    if f.r_squared is not None:
        if f.r_squared > 0.80:   s += 30
        elif f.r_squared > 0.60: s += 15
    if f.alpha_annualised is not None and f.alpha_annualised < -0.05:
        s += 20
    return _clamp(s, 0, 100)


def _score_fundamental(profiles: list[PositionRisk]) -> float:
    if not profiles:
        return 50.0
    total_w = sum(p.weight for p in profiles)
    if total_w == 0:
        return 50.0
    rating_pts = {"Low": 0, "Medium": 33, "High": 67, "Critical": 100}
    return _clamp(
        sum(p.weight / total_w * rating_pts.get(p.rating, 50) for p in profiles),
        0, 100,
    )


def _score_income(income: IncomeRisk) -> float:
    s = 0.0
    if income.income_concentration_flag:        s += 35
    if income.flagged_income_pct > 0.20:        s += 30
    if income.top3_cut_pct is not None and income.top3_cut_pct > 0.20: s += 20
    if income.weighted_dgr is not None and income.weighted_dgr < 0.025: s += 15
    # Low income-stability (short/no growth streaks, recent cuts among the
    # payers weighted by income share) — None when no payer has DPS history yet.
    if income.income_stability is not None:
        if income.income_stability < 3.0:    s += 25
        elif income.income_stability < 5.0:  s += 12
    return _clamp(s, 0, 100)


def _risk_label_description(score: float) -> tuple[str, str]:
    label, description, _tone = risk_band(score)
    return label, description


def _stage7_composite(profiles: list[PositionRisk], c: ConcentrationMetrics,
                      q: QuantMetrics, f: FactorExposure, income: IncomeRisk,
                      stress: StressResults, weighting: str) -> CompositeScore:
    W  = dict(_W_INCOME if weighting == "income_weighted" else _W_DEFAULT)
    sc = _score_concentration(c)
    sv = _score_volatility(q)
    st = _score_tail(q, stress)
    sf = _score_factor(f)
    su = _score_fundamental(profiles)
    si = _score_income(income)

    comps = {"concentration": sc, "volatility": sv, "tail": st,
             "factor": sf, "fundamental": su, "income": si}
    if not f.available:
        # Drop the factor slot and renormalise the rest — a flat 50 at 15%
        # weight otherwise drags every portfolio's score toward the middle
        # whenever the Fama-French feed is unavailable.
        W.pop("factor")
        _tot = sum(W.values())
        W = {k: v / _tot for k, v in W.items()}

    score = sum(W[k] * comps[k] for k in W)
    label, description = _risk_label_description(score)
    return CompositeScore(
        score=round(score, 1),
        label=label,
        description=description,
        weighting=weighting,
        sub_scores={
            "Concentration": round(sc, 1),
            "Volatility":    round(sv, 1),
            "Tail Risk":     round(st, 1),
            "Factor":        round(sf, 1),
            "Fundamental":   round(su, 1),
            "Income":        round(si, 1),
        },
    )


# ── Stage 8 — Risk observations ──────────────────────────────────────────────
# Legal copy of risk.py's "Rebalancing signals" (PER-4, PER-5). Same checks
# and thresholds, except:
#   • every check states the figure and the reference it is compared with, and
#     nothing more — no "trim", "rotate", "replace", "reduce or exit";
#   • the model's own thresholds are called reference levels, not limits or
#     the user's tolerance (PER-1: the app knows nothing about the user's
#     tolerance);
#   • risk.py's "breaches a hard veto rule … consider reducing or exiting"
#     trigger is dropped. It paired the screener's signal with the fact that
#     the user holds the stock — the exact pattern PER-5 forbids. The veto
#     stays visible on the stock's own badge, the same for every user.
#   • checks against targets the user set themselves are kept (PER-5 allows
#     alerts on user-set thresholds) and carry basis="user_target".

_RATING_RANK = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}
_DRIFT_PP = 0.05   # 5 percentage-point drift-from-target / drift-since-snapshot threshold

# Model reference levels, named so the methodology page can publish them.
REF_POSITION_WEIGHT = 0.20
REF_PORTFOLIO_BETA  = 1.5
REF_VAR99_1D_PCT    = 0.03
REF_FLAGGED_INCOME  = 0.40
REF_WORST_SCENARIO  = -0.40
REF_HHI_HIGH        = 0.18
REF_HHI_MODERATE    = 0.10
REF_DGR_INFLATION   = 0.025
REF_SHARPE          = 1.0


def _stage8_observations(profiles: list[PositionRisk], concentration: ConcentrationMetrics,
                         quant: QuantMetrics, income: IncomeRisk,
                         stress: StressResults, total_value: float, *,
                         targets: dict | None = None,
                         prior_snapshot: dict | None = None) -> RiskObservations:
    targets        = targets or {}
    prior_snapshot = prior_snapshot or {}
    sector_targets = targets.get("sectors") or {}
    ticker_targets = targets.get("tickers") or {}
    _prior_date    = prior_snapshot.get("date") or prior_snapshot.get("as_of")
    prior_since    = Fmt("date", _prior_date) if _prior_date else lazy_("last snapshot")
    items: list[RiskObservation] = []

    def add(level, scope, message, basis="model_reference", mode="absolute"):
        items.append(RiskObservation(level, scope, message, basis, mode))

    # Level "high": figures above the model's upper reference levels
    for p in profiles:
        if p.weight > REF_POSITION_WEIGHT:
            add("high", p.ticker,
                lazy_("{ticker} is {weight} of the portfolio, above the model's {ref} single-position reference level",
                      ticker=p.ticker, weight=Fmt("pct", p.weight, fraction=True),
                      ref=Fmt("pct", REF_POSITION_WEIGHT, decimals=0, fraction=True)))

    if quant.portfolio_beta > REF_PORTFOLIO_BETA:
        add("high", "Portfolio",
            lazy_("Portfolio beta is {beta}, above {ref}: historically the portfolio moved more than the market in both directions",
                  beta=Fmt("num", quant.portfolio_beta, decimals=2), ref=Fmt("num", REF_PORTFOLIO_BETA, decimals=1)))

    if quant.var_99_1d_eur is not None and total_value > 0:
        var_pct = quant.var_99_1d_eur / total_value
        if var_pct > REF_VAR99_1D_PCT:
            add("high", "Portfolio",
                lazy_("Estimated 1-day 99% VaR is {amount} ({pct}), above the model's {ref} reference level",
                      amount=Fmt("money", quant.var_99_1d_eur, decimals=0, currency="EUR"),
                      pct=Fmt("pct", var_pct, fraction=True),
                      ref=Fmt("pct", REF_VAR99_1D_PCT, decimals=0, fraction=True)))

    if income.flagged_income_pct > REF_FLAGGED_INCOME:
        flagged_str = ", ".join(income.flagged_payers[:5])
        add("high", flagged_str,
            lazy_("{pct} of estimated portfolio income comes from positions whose dividend is flagged at risk",
                  pct=Fmt("pct", income.flagged_income_pct, decimals=0, fraction=True)))

    worst_dd = min((r.portfolio_drawdown for r in stress.historical
                   if r.portfolio_drawdown is not None), default=0.0)
    if worst_dd < REF_WORST_SCENARIO:
        add("high", "Portfolio",
            lazy_("The worst historical scenario replay gives an estimated {drawdown} portfolio drawdown",
                  drawdown=Fmt("pct", worst_dd, decimals=0, fraction=True)))

    for p in profiles:
        if p.rating == "Critical":
            add("high", p.ticker,
                lazy_("{ticker}: position risk rating Critical (from its weight, beta, valuation gap, "
                      "financial health and earnings quality)", ticker=p.ticker))

    # ── Level "notice" ──────────────────────────────────────────────────────
    # Concentration (HHI): a user-set ceiling wins over the model's reference
    # bands; a prior snapshot adds a "changed since" check on top.
    hhi_max = _safe(targets.get("hhi_max"))
    if hhi_max is not None:
        if concentration.hhi > hhi_max:
            add("notice", "Portfolio",
                lazy_("HHI {hhi} is above the {ceiling} ceiling you set",
                      hhi=Fmt("num", concentration.hhi, decimals=3), ceiling=Fmt("num", hhi_max, decimals=3)),
                basis="user_target", mode="drift")
    elif concentration.hhi > REF_HHI_HIGH:
        add("notice", "Portfolio",
            lazy_("HHI {hhi}: highly concentrated on the model's scale (above {ref})",
                  hhi=Fmt("num", concentration.hhi, decimals=3), ref=Fmt("num", REF_HHI_HIGH, decimals=2)))
    elif concentration.hhi > REF_HHI_MODERATE:
        add("notice", "Portfolio",
            lazy_("HHI {hhi}: moderately concentrated on the model's scale (above {ref})",
                  hhi=Fmt("num", concentration.hhi, decimals=3), ref=Fmt("num", REF_HHI_MODERATE, decimals=2)))

    prior_hhi = _safe(prior_snapshot.get("hhi"))
    if prior_hhi is not None and concentration.hhi - prior_hhi > _DRIFT_PP:
        add("notice", "Portfolio",
            lazy_("HHI rose by {change} since {date} (now {hhi})",
                  change=Fmt("num", concentration.hhi - prior_hhi, decimals=3), date=prior_since,
                  hhi=Fmt("num", concentration.hhi, decimals=3)),
            basis="since_snapshot", mode="drift")

    # Sector: drift vs the user's target allocation when one exists, else the
    # model's 30% reference level on the largest sector.
    if sector_targets:
        for sec in sorted(set(sector_targets) | set(concentration.sector_weights)):
            tgt = _safe(sector_targets.get(sec))
            if tgt is None:
                continue
            actual = concentration.sector_weights.get(sec, 0.0)
            drift  = actual - tgt
            if abs(drift) >= _DRIFT_PP:
                add("notice", sec,
                    lazy_("{sector} is {actual} of the portfolio against your {target} target ({drift})",
                          sector=Fmt("tr", sec), actual=Fmt("pct", actual, decimals=0, fraction=True),
                          target=Fmt("pct", tgt, decimals=0, fraction=True),
                          drift=Fmt("pct", drift, decimals=0, fraction=True, signed=True)),
                    basis="user_target", mode="drift")
    elif concentration.sector_flag and concentration.largest_sector:
        w = concentration.sector_weights.get(concentration.largest_sector, 0.0)
        add("notice", concentration.largest_sector,
            lazy_("{sector} is {weight} of the portfolio, above the model's 30% sector reference level",
                  sector=Fmt("tr", concentration.largest_sector), weight=Fmt("pct", w, decimals=0, fraction=True)))

    # Per-name drift vs the user's own target weights.
    if ticker_targets:
        for p in profiles:
            tgt = _safe(ticker_targets.get(p.ticker))
            if tgt is None:
                continue
            drift = p.weight - tgt
            if abs(drift) >= _DRIFT_PP:
                add("notice", p.ticker,
                    lazy_("{ticker} is {weight} of the portfolio against your {target} target ({drift})",
                          ticker=p.ticker, weight=Fmt("pct", p.weight, decimals=0, fraction=True),
                          target=Fmt("pct", tgt, decimals=0, fraction=True),
                          drift=Fmt("pct", drift, decimals=0, fraction=True, signed=True)),
                    basis="user_target", mode="drift")

    if income.weighted_dgr is not None and income.weighted_dgr < REF_DGR_INFLATION:
        add("notice", "Portfolio",
            lazy_("Weighted dividend growth {dgr} is below the model's {ref} inflation reference",
                  dgr=Fmt("pct", income.weighted_dgr, fraction=True),
                  ref=Fmt("pct", REF_DGR_INFLATION, decimals=1, fraction=True)))

    prior_sharpe = _safe(prior_snapshot.get("sharpe"))
    if quant.sharpe is not None and quant.sharpe < REF_SHARPE:
        if prior_sharpe is not None and prior_sharpe < REF_SHARPE:
            add("notice", "Portfolio",
                lazy_("Sharpe ratio {sharpe} is below 1.0 in two consecutive risk reports (was {previous} at {date})",
                      sharpe=Fmt("num", quant.sharpe, decimals=2), previous=Fmt("num", prior_sharpe, decimals=2),
                      date=prior_since),
                basis="since_snapshot", mode="drift")
        else:
            add("notice", "Portfolio",
                lazy_("Sharpe ratio {sharpe} is below 1.0: historical return per unit of volatility was modest",
                      sharpe=Fmt("num", quant.sharpe, decimals=2)))

    # Rating transitions vs the prior snapshot (an upgrade into High/Critical).
    prior_ratings = prior_snapshot.get("ratings") or {}
    for p in profiles:
        was = prior_ratings.get(p.ticker)
        if (was in _RATING_RANK and p.rating in ("High", "Critical")
                and _RATING_RANK[p.rating] > _RATING_RANK[was]):
            add("notice", p.ticker,
                lazy_("{ticker}: position risk rating changed from {previous} to {rating} since {date}",
                      ticker=p.ticker, previous=Fmt("tr", was), rating=Fmt("tr", p.rating), date=prior_since),
                basis="since_snapshot", mode="transition")

    for p in profiles:
        if p.rating == "High":
            add("notice", p.ticker,
                lazy_("{ticker}: position risk rating High", ticker=p.ticker))

    for p in profiles:
        if p.liquidity_flag and p.days_to_liquidate is not None:
            add("notice", p.ticker,
                lazy_("{ticker}: the full position equals about {days} trading days at {participation} of average daily volume",
                      ticker=p.ticker, days=Fmt("num", p.days_to_liquidate, decimals=0),
                      participation=Fmt("pct", _LIQ_PARTICIPATION, decimals=0, fraction=True)))

    if quant.high_corr_pairs:
        pairs_str = ", ".join(f"{a}/{b}" for a, b, _corr in quant.high_corr_pairs[:3])
        add("notice", pairs_str,
            lazy_("Highly correlated pairs (above 0.80): {pairs}. Their prices have tended to move together",
                  pairs=pairs_str))

    return RiskObservations(items=items)


# ── Main entry point ──────────────────────────────────────────────────────────

def snapshot_from_report(report: "RiskReport") -> dict:
    """The slim reference a later run diffs against for Stage 8's drift
    triggers — persist via portfolio.save_risk_snapshot()."""
    return {
        "as_of":          report.generated_at,
        "hhi":            report.concentration.hhi,
        "sharpe":         report.quant.sharpe,
        "sector_weights": dict(report.concentration.sector_weights),
        "ratings":        {p.ticker: p.rating for p in report.position_profiles},
    }


def assess_portfolio(pf_df: pd.DataFrame, cache: dict,
                     weighting: str = "standard",
                     veto_lookup: dict[str, bool] | None = None,
                     targets: dict | None = None,
                     prior_snapshot: dict | None = None) -> RiskReport:
    """
    Run the 8-stage risk assessment pipeline and return a RiskReport.

    pf_df            — enriched portfolio DataFrame. Build it with
                       portfolio_enrichment.enrich_for_risk(); it needs
                       live_price, current_value, sector, country,
                       expected_annual and fair_value (missing columns fall
                       back — current_value / expected_annual are derived here,
                       sector / country / fair_value default to neutral).
    cache            — fundamentals cache dict from screener._load_cache().
                       Its per-ticker "Currency" field, when present, drives
                       the EUR restatement of price history (_to_eur); a
                       missing currency is treated as EUR. Its "beta" field is
                       the fallback when a holding has too little history to
                       regress a beta against BENCHMARK_TICKER.
    weighting        — Stage 7 weighting preset, one of WEIGHTINGS. A model
                       setting the user picks (PER-8); never derive it from the
                       user's goals or a questionnaire (PER-3). "income_weighted"
                       is risk.py's income_portfolio=True.
    veto_lookup      — optional {ticker: bool} from the screener's own `veto`
                       column (screener.py's df["veto"]); feeds Stage 1's
                       PositionRisk.veto only (Stage 8 no longer reads it, PER-5).
    targets          — optional target allocation
                       {"sectors": {..}, "tickers": {..}, "hhi_max": float}
                       (portfolio.load_targets()); switches Stage 8's sector /
                       name / HHI checks from absolute levels to drift-vs-target.
    prior_snapshot   — optional {"date","hhi","sharpe","sector_weights","ratings"}
                       from the last run (portfolio.load_risk_snapshot(), built
                       via snapshot_from_report()); adds drift-since / two-period
                       / rating-transition observations.
    """
    if weighting not in WEIGHTINGS:
        raise ValueError(f"unknown weighting {weighting!r}; expected one of {WEIGHTINGS}")
    if pf_df is None or pf_df.empty:
        raise ValueError(lazy_("Portfolio is empty — nothing to assess"))

    pf = pf_df.copy()

    if "current_value" not in pf.columns:
        pf["current_value"] = (
            pf.get("live_price", pf.get("purchase_value", 0)) * pf.get("shares", 1)
        )
    if "expected_annual" not in pf.columns:
        pf["expected_annual"] = 0.0

    total_value = float(pf["current_value"].fillna(0).sum())
    tickers     = pf["ticker"].tolist()

    # One batch fetch of the longer stress window for all positions + the
    # benchmark, restated in EUR. Stages 1/3/4 run on the trailing 5y slice
    # (behaviour unchanged); Stage 6 gets the full-length series for scenario
    # replay and the Monte-Carlo bootstrap.
    closes_full  = _to_eur(_fetch_history(tickers + [BENCHMARK_TICKER],
                                          period=STRESS_HISTORY_PERIOD), cache)
    _cutoff      = pd.Timestamp.now().normalize() - pd.Timedelta(days=QUANT_HISTORY_DAYS)
    closes_all   = closes_full[closes_full.index >= _cutoff] if not closes_full.empty else closes_full
    bench_closes = (closes_all[[BENCHMARK_TICKER]]
                    if BENCHMARK_TICKER in closes_all.columns else pd.DataFrame())
    closes       = closes_all.drop(columns=[BENCHMARK_TICKER], errors="ignore")
    closes_stress = closes_full.drop(columns=[BENCHMARK_TICKER], errors="ignore")

    bench_rets: pd.Series | None = None
    if not bench_closes.empty:
        _b = _daily_returns(bench_closes).dropna()
        if len(_b) >= _BETA_MIN_OBS:
            bench_rets = _b[BENCHMARK_TICKER]

    # Per-holding beta (regression on own EUR series vs benchmark, with
    # yfinance / 1.0 fallbacks) — feeds Stages 1 and 3.
    stock_rets = _daily_returns(closes) if not closes.empty else pd.DataFrame()
    betas, beta_sources = _resolve_betas(tickers, stock_rets, bench_rets, cache)

    # Build portfolio daily return series (used in Stages 3, 4, 6)
    port_rets: pd.Series | None = None
    if not closes.empty:
        avail = [t for t in tickers if t in closes.columns]
        if avail:
            aw = _weights_for_tickers(pf, avail, total_value)
            dr = _daily_returns(closes[avail].dropna(how="all")).dropna(how="all")
            if not dr.empty:
                port_rets = pd.Series(
                    dr.fillna(0).values @ aw,
                    index=dr.index,
                    name="portfolio",
                )

    # Direct OLS beta of the portfolio return series on the benchmark — a
    # cross-check on the weighted-sum portfolio beta.
    port_beta_reg: float | None = None
    if port_rets is not None and bench_rets is not None:
        j = pd.concat([port_rets.rename("p"), bench_rets.rename("m")], axis=1).dropna()
        if len(j) >= _BETA_MIN_OBS:
            _pbr = _ols_beta(j["p"].to_numpy(), j["m"].to_numpy())
            port_beta_reg = round(_pbr, 3) if _pbr is not None else None

    # Full-length portfolio return series for Stage 6 (scenario replay + MC).
    port_rets_stress: pd.Series | None = None
    if not closes_stress.empty:
        avail_s = [t for t in tickers if t in closes_stress.columns]
        if avail_s:
            aw_s = _weights_for_tickers(pf, avail_s, total_value)
            dr_s = _daily_returns(closes_stress[avail_s].dropna(how="all")).dropna(how="all")
            if not dr_s.empty:
                port_rets_stress = pd.Series(dr_s.fillna(0).values @ aw_s,
                                             index=dr_s.index, name="portfolio")

    s1 = _stage1_position_profiles(pf, cache, total_value, veto_lookup,
                                   betas=betas, beta_sources=beta_sources, closes=closes)
    s2 = _stage2_concentration(pf, total_value)
    s3 = _stage3_quant(pf, cache, total_value, closes,
                       betas=betas, portfolio_beta_regression=port_beta_reg)
    s4 = _stage4_factor(port_rets)
    s5 = _stage5_income(pf, cache, total_value)
    s6 = _stage6_stress(pf, cache, s3.portfolio_beta, total_value, port_rets_stress, s2)
    s7 = _stage7_composite(s1, s2, s3, s4, s5, s6, weighting)
    s8 = _stage8_observations(s1, s2, s3, s5, s6, total_value,
                              targets=targets, prior_snapshot=prior_snapshot)

    return RiskReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        portfolio_value=round(total_value, 2),
        n_positions=len(pf),
        position_profiles=s1,
        concentration=s2,
        quant=s3,
        factor=s4,
        income=s5,
        stress=s6,
        composite=s7,
        observations=s8,
        disclosures=list(RISK_DISCLOSURES),
    )
