"""
Portfolio Risk Assessment — 8-stage algorithm.
docs/portfolio_risk_assessment_algorithm.md

Entry point:
    report = assess_portfolio(pf_df, cache, income_portfolio=False)

pf_df   — enriched portfolio DataFrame (columns: ticker, name, shares,
           purchase_value, current_value, live_price, sector, country,
           expected_annual, fair_value)
cache   — fundamentals cache dict[ticker -> dict] from screener._load_cache()
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf

from screener import (
    _financial_health_score,
    _earnings_quality_score,
    _dividend_sustainability_flag,
)

# ── Constants ─────────────────────────────────────────────────────────────────

RISK_FREE_RATE   = 0.03     # Euro area risk-free proxy (matches screener.py)
MARKET_DAILY_VOL = 0.012    # ~1.2% daily vol proxy for market
TRADING_DAYS     = 252
MONTE_CARLO_PATHS = 10_000
MONTE_CARLO_SEED  = 42

# Stage 7 composite weights
_W_DEFAULT = {
    "concentration": 0.25,
    "volatility":    0.20,
    "tail":          0.20,
    "factor":        0.15,
    "fundamental":   0.15,
    "income":        0.05,
}
_W_INCOME = {   # elevated income risk weight for income portfolios
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

HISTORICAL_SCENARIOS = [
    ("Dot-com crash",        "2000–2002",    -0.49),
    ("Financial crisis",     "2007–2009",    -0.57),
    ("COVID crash",          "Feb–Mar 2020", -0.34),
    ("2022 rate hike cycle", "Jan–Oct 2022", -0.25),
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
    mos: float | None               # margin of safety (fraction)
    valuation_flag: str             # "Overvalued" | "Fairly Valued" | "Undervalued" | "N/A"
    div_sustainability: str         # "OK" | "At Risk" | ""
    financial_health: float         # 0–10
    earnings_quality: float         # 0–10
    rating: str                     # "Low" | "Medium" | "High" | "Critical"


@dataclass
class ConcentrationMetrics:
    hhi: float
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


@dataclass
class QuantMetrics:
    portfolio_beta: float
    beta_label: str
    volatility_annual: float | None     # fraction, e.g. 0.15 = 15%
    volatility_label: str
    var_95_1d_eur: float | None
    var_99_1d_eur: float | None
    cvar_95_1d_eur: float | None
    mdd_1y: float | None
    mdd_3y: float | None
    mdd_5y: float | None
    mdd_label: str
    sharpe: float | None
    sortino: float | None
    ratio_label: str
    corr_matrix: pd.DataFrame | None
    high_corr_pairs: list[tuple[str, str, float]]
    effective_diversification: float | None
    returns_available: bool


@dataclass
class FactorExposure:
    available: bool
    loadings: dict[str, float]
    r_squared: float | None
    alpha_annualised: float | None
    flags: list[str]


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


@dataclass
class ScenarioResult:
    name: str
    period: str
    index_drawdown: float | None
    portfolio_drawdown: float | None    # estimated (fraction)
    portfolio_value_loss: float | None  # €


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
    action: str
    sub_scores: dict[str, float]    # component name → 0–100


@dataclass
class RebalanceSignals:
    hard_triggers: list[str]
    soft_triggers: list[str]
    actions: list[dict]     # keys: ticker, issue, action


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
    rebalance: RebalanceSignals


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
    """Download adjusted daily closes; returns DataFrame (date × ticker)."""
    if not tickers:
        return pd.DataFrame()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = yf.download(
            tickers, period=period, interval="1d",
            auto_adjust=True, progress=False, threads=True,
        )
    if raw.empty:
        return pd.DataFrame()
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    if len(tickers) == 1 and not isinstance(closes, pd.DataFrame):
        closes = closes.to_frame(name=tickers[0])
    elif len(tickers) == 1 and isinstance(closes, pd.DataFrame) and closes.shape[1] == 1:
        closes.columns = tickers
    return closes.dropna(how="all")


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
    if pts >= 5:  return "Critical"
    if pts >= 3:  return "High"
    if pts >= 1:  return "Medium"
    return "Low"


def _stage1_position_profiles(pf: pd.DataFrame, cache: dict,
                               total_value: float) -> list[PositionRisk]:
    profiles = []
    for _, row in pf.iterrows():
        ticker  = row["ticker"]
        fd      = cache.get(ticker, {})
        fd_ser  = pd.Series(fd)

        weight    = _safe(row.get("current_value"), 0) / total_value if total_value > 0 else 0.0
        beta      = _safe(fd.get("beta"))
        pos_value = _safe(row.get("current_value"), 0)

        # Parametric VaR(95%) proxy — uses beta × market daily vol
        stock_daily_vol = abs(beta if beta is not None else 1.0) * MARKET_DAILY_VOL
        var_95 = pos_value * stock_daily_vol * 1.645

        # Valuation flag from fair value vs live price
        price = _safe(row.get("live_price"))
        fv    = _safe(row.get("fair_value"))
        if price and fv and fv > 0:
            mos = (fv - price) / fv
            val_flag = ("Overvalued" if mos < -0.05 else
                        "Fairly Valued" if mos < 0.10 else "Undervalued")
        else:
            mos      = None
            val_flag = "N/A"

        fh     = _financial_health_score(fd_ser)
        eq     = _earnings_quality_score(fd_ser)
        ds     = _dividend_sustainability_flag(fd_ser)
        rating = _position_rating(weight, beta, mos, fh, eq)

        profiles.append(PositionRisk(
            ticker=ticker,
            name=str(row.get("name", ticker)),
            weight=weight,
            beta=beta,
            var_95_1d_eur=round(var_95, 2) if var_95 else None,
            mos=round(mos, 4) if mos is not None else None,
            valuation_flag=val_flag,
            div_sustainability=ds,
            financial_health=round(fh, 1),
            earnings_quality=round(eq, 1),
            rating=rating,
        ))
    return profiles


# ── Stage 2 — Concentration & diversification ─────────────────────────────────

def _hhi_label(hhi: float) -> str:
    if hhi < 0.10:  return "Well diversified"
    if hhi < 0.18:  return "Moderately concentrated"
    return "Highly concentrated"


def _stage2_concentration(pf: pd.DataFrame, total_value: float) -> ConcentrationMetrics:
    _empty = ConcentrationMetrics(
        hhi=0.0, hhi_label="N/A", top1_weight=0.0, top1_ticker="",
        top3_weight=0.0, top5_weight=0.0, top1_flag=False, top3_flag=False,
        top5_flag=False, sector_weights={}, largest_sector=None, sector_flag=False,
        geo_weights={}, largest_geo=None, geo_flag=False,
        div_hhi=None, div_top3_pct=None, income_concentration_flag=False,
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
        sec = str(row.get("sector") or "Unknown")
        val = _safe(row.get("current_value"), 0)
        sec_map[sec] = sec_map.get(sec, 0.0) + val / total_value
    sec_map = {k: round(v, 4) for k, v in sorted(sec_map.items(), key=lambda x: -x[1])}
    largest_sector = next(iter(sec_map), None)
    sec_vals = list(sec_map.values())
    sector_flag = bool(
        (largest_sector and sec_map.get(largest_sector, 0) > 0.30)
        or (len(sec_vals) >= 2 and sec_vals[0] + sec_vals[1] > 0.50)
    )

    # Geographic weights
    geo_map: dict[str, float] = {}
    for _, row in pf.iterrows():
        geo = str(row.get("country") or "Unknown")
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
    )


# ── Stage 3 — Portfolio-level quantitative metrics ────────────────────────────

def _beta_label(b: float) -> str:
    if b < 0.8:  return "Defensive"
    if b < 1.2:  return "Market-like"
    return "Aggressive"

def _vol_label(v: float) -> str:
    if v < 0.10:  return "Low"
    if v < 0.20:  return "Moderate"
    return "High"

def _mdd_label(mdd: float | None) -> str:
    if mdd is None:  return "N/A"
    v = abs(mdd)
    if v < 0.10:  return "Low"
    if v < 0.25:  return "Moderate"
    return "High"

def _ratio_label(sharpe: float | None, sortino: float | None) -> str:
    r = sortino if sortino is not None else sharpe
    if r is None:  return "N/A"
    if r > 1.5:    return "Strong"
    if r > 1.0:    return "Acceptable"
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
                  closes: pd.DataFrame) -> QuantMetrics:
    tickers = pf["ticker"].tolist()
    betas   = np.array([_safe(cache.get(t, {}).get("beta"), 1.0) for t in tickers])
    weights = _weights_for_tickers(pf, tickers, total_value)
    port_beta = float(np.dot(weights, betas))

    _no_history = QuantMetrics(
        portfolio_beta=round(port_beta, 2), beta_label=_beta_label(port_beta),
        volatility_annual=None, volatility_label="N/A",
        var_95_1d_eur=None, var_99_1d_eur=None, cvar_95_1d_eur=None,
        mdd_1y=None, mdd_3y=None, mdd_5y=None, mdd_label="N/A",
        sharpe=None, sortino=None, ratio_label="N/A",
        corr_matrix=None, high_corr_pairs=[], effective_diversification=None,
        returns_available=False,
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

    eff_div: float | None = None
    if corr is not None and len(corr) > 1:
        upper = corr.values[np.triu_indices_from(corr.values, k=1)]
        fin   = upper[np.isfinite(upper)]
        if len(fin) > 0:
            eff_div = round(1.0 - float(np.mean(fin)), 3)

    return QuantMetrics(
        portfolio_beta=round(port_beta, 2),
        beta_label=_beta_label(port_beta),
        volatility_annual=round(float(vol_ann), 4),
        volatility_label=_vol_label(float(vol_ann)),
        var_95_1d_eur=round(abs(var_95_pct) * total_value, 2),
        var_99_1d_eur=round(abs(var_99_pct) * total_value, 2),
        cvar_95_1d_eur=round(abs(cvar_95_pct) * total_value, 2),
        mdd_1y=round(float(mdd_1y), 4) if mdd_1y is not None else None,
        mdd_3y=round(float(mdd_3y), 4) if mdd_3y is not None else None,
        mdd_5y=round(float(mdd_5y), 4) if mdd_5y is not None else None,
        mdd_label=_mdd_label(mdd_5y if mdd_5y is not None else mdd_1y),
        sharpe=round(float(sharpe), 2) if sharpe is not None else None,
        sortino=round(float(sortino), 2) if sortino is not None else None,
        ratio_label=_ratio_label(sharpe, sortino),
        corr_matrix=corr,
        high_corr_pairs=high_corr,
        effective_diversification=eff_div,
        returns_available=True,
    )


# ── Stage 4 — Factor exposure (Fama-French 5-factor) ─────────────────────────

_FF5_URL = ("https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
            "F-F_Research_Data_5_Factors_2x3_Daily_CSV.zip")
_MOM_URL = ("https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
            "F-F_Momentum_Factor_Daily_CSV.zip")

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


def _stage4_factor(port_rets: pd.Series | None) -> FactorExposure:
    _unavail = FactorExposure(available=False, loadings={}, r_squared=None,
                              alpha_annualised=None, flags=[])

    if port_rets is None or len(port_rets) < 60:
        _unavail.flags = ["Insufficient price history for factor analysis (need ≥60 days)"]
        return _unavail

    try:
        ff = _fetch_ff_csv(_FF5_URL)
        ff = ff.loc[port_rets.index[0]:port_rets.index[-1]]
    except Exception as e:
        _unavail.flags = [f"Fama-French data unavailable: {e}"]
        return _unavail

    # Optionally add momentum factor
    try:
        mom = _fetch_ff_csv(_MOM_URL)
        mom = mom.loc[port_rets.index[0]:port_rets.index[-1]]
        mom_col = mom.iloc[:, 0].rename("WML")
        ff = ff.join(mom_col, how="left")
    except Exception:
        pass

    merged = ff.join(port_rets.rename("port"), how="inner").dropna()
    if len(merged) < 30:
        _unavail.flags = ["Insufficient overlapping data after alignment"]
        return _unavail

    factor_cols = [c for c in merged.columns if c not in ("RF", "port")]
    Y = (merged["port"] - merged["RF"]).values
    X = np.column_stack([np.ones(len(Y)), merged[factor_cols].values])

    coeffs, _, _, _ = np.linalg.lstsq(X, Y, rcond=None)
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
            flags.append(f"High {name} loading ({b:+.2f}) — concentrated factor bet")

    f_stds = merged[factor_cols].std().values
    contributions = np.abs(betas_) * f_stds
    if contributions.sum() > 0:
        dom_share = contributions.max() / contributions.sum()
        if dom_share > 0.60 and r2 > 0.40:
            dom_name = factor_cols[int(np.argmax(contributions))]
            flags.append(f"{dom_name} explains >{dom_share:.0%} of return variance")

    return FactorExposure(
        available=True,
        loadings=loadings,
        r_squared=round(float(r2), 3),
        alpha_annualised=round(alpha * TRADING_DAYS, 4),
        flags=flags,
    )


# ── Stage 5 — Dividend & income risk ─────────────────────────────────────────

def _stage5_income(pf: pd.DataFrame, cache: dict, total_value: float) -> IncomeRisk:
    income_col   = pf["expected_annual"].fillna(0) if "expected_annual" in pf.columns else pd.Series(0.0, index=pf.index)
    total_income = float(income_col.sum())
    port_yield   = total_income / total_value if total_value > 0 else 0.0

    # Weighted DGR (earnings growth as proxy)
    dgr_parts: list[float] = []
    for _, row in pf.iterrows():
        inc = _safe(income_col.loc[row.name], 0.0)
        eg  = _safe(cache.get(row["ticker"], {}).get("earningsGrowth"))
        if eg is not None and total_income > 0 and inc > 0:
            dgr_parts.append(inc / total_income * eg)
    weighted_dgr = float(sum(dgr_parts)) if dgr_parts else None

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
                    or (payout is not None and payout > 0.80)
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
    )


# ── Stage 6 — Stress testing & scenario analysis ──────────────────────────────

def _stage6_stress(pf: pd.DataFrame, cache: dict, portfolio_beta: float,
                   total_value: float, port_rets: pd.Series | None,
                   concentration: ConcentrationMetrics) -> StressResults:

    # 6a. Historical scenarios — beta-adjusted drawdown approximation
    historical = [
        ScenarioResult(
            name=name, period=period,
            index_drawdown=idx_dd,
            portfolio_drawdown=round(portfolio_beta * idx_dd, 4),
            portfolio_value_loss=round(abs(portfolio_beta * idx_dd) * total_value, 2),
        )
        for name, period, idx_dd in HISTORICAL_SCENARIOS
    ]

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
        "name": "Rate rise +200 bps",
        "description": "High P/E stocks repriced via discount rate expansion (duration proxy)",
        "estimated_portfolio_impact": round(rate_impact, 4),
        "estimated_loss_eur": round(abs(rate_impact) * total_value, 2),
    })

    # Recession — cyclical sectors cut 25%, defensives 10%
    rec_impact = 0.0
    for _, row in pf.iterrows():
        sec = str(row.get("sector") or "")
        w   = _safe(row.get("current_value"), 0.0) / total_value if total_value > 0 else 0.0
        rec_impact += w * (-0.25 if sec in CYCLICAL_SECTORS else -0.10)
    factor_scenarios.append({
        "name": "Recession (earnings cut 20–30%)",
        "description": "25% EPS hit in cyclicals, 10% in defensives; P/E multiples compressed",
        "estimated_portfolio_impact": round(rec_impact, 4),
        "estimated_loss_eur": round(abs(rec_impact) * total_value, 2),
    })

    # Largest sector −40% crash
    sec_w      = concentration.sector_weights.get(concentration.largest_sector or "", 0.0)
    sec_impact = sec_w * (-0.40)
    factor_scenarios.append({
        "name": f"Sector crash −40% ({concentration.largest_sector or 'N/A'})",
        "description": f"40% drawdown applied to {concentration.largest_sector or 'largest'} sector",
        "estimated_portfolio_impact": round(sec_impact, 4),
        "estimated_loss_eur": round(abs(sec_impact) * total_value, 2),
    })

    # Credit crunch — penalise high-leverage positions
    credit_impact = 0.0
    for _, row in pf.iterrows():
        t  = row["ticker"]
        de = _safe(cache.get(t, {}).get("debtToEquity"))
        w  = _safe(row.get("current_value"), 0.0) / total_value if total_value > 0 else 0.0
        if de is not None:
            de_ratio = de / 100.0   # yfinance stores as ×100
            credit_impact += w * (-min(de_ratio * 0.05, 0.30))
    factor_scenarios.append({
        "name": "Credit crunch",
        "description": "Leveraged positions repriced — high D/E stocks penalised",
        "estimated_portfolio_impact": round(credit_impact, 4),
        "estimated_loss_eur": round(abs(credit_impact) * total_value, 2),
    })

    # Dividend freeze — total income loss
    income_col   = pf["expected_annual"].fillna(0) if "expected_annual" in pf.columns else pd.Series(0.0, index=pf.index)
    total_income = float(income_col.sum())
    factor_scenarios.append({
        "name": "Dividend freeze",
        "description": "All dividend payments suspended",
        "estimated_portfolio_impact": 0.0,
        "estimated_loss_eur": round(total_income, 2),
        "note": f"Annual income impact: €{total_income:,.0f}",
    })

    # 6c. Monte Carlo simulation
    def _mc(years: int) -> MonteCarloResult:
        rng = np.random.default_rng(MONTE_CARLO_SEED)
        if port_rets is not None and len(port_rets) >= 30:
            mu    = float(port_rets.mean())
            sigma = float(port_rets.std(ddof=1))
        else:
            mu    = (RISK_FREE_RATE + portfolio_beta * 0.05) / TRADING_DAYS
            sigma = portfolio_beta * MARKET_DAILY_VOL
        days  = years * TRADING_DAYS
        paths = rng.normal(mu, sigma, size=(MONTE_CARLO_PATHS, days))
        cum   = np.prod(1.0 + np.clip(paths, -0.5, 1.0), axis=1) - 1.0
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
    worst = min((r.portfolio_drawdown or 0.0) for r in stress.historical)
    if worst < -0.40:    s += 10
    elif worst < -0.25:  s += 5
    return _clamp(s, 0, 100)


def _score_factor(f: FactorExposure) -> float:
    if not f.available:
        return 50.0
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
    return _clamp(s, 0, 100)


def _risk_label_action(score: float) -> tuple[str, str]:
    if score <= SCORE_LOW:       return "Low risk",       "Hold — monitor quarterly"
    if score <= SCORE_MODERATE:  return "Moderate risk",  "Review annually; consider minor rebalancing"
    if score <= SCORE_ELEVATED:  return "Elevated risk",  "Active monitoring; targeted rebalancing"
    if score <= SCORE_HIGH:      return "High risk",      "Immediate rebalancing required"
    return "Critical risk", "Defensive repositioning — reduce exposure immediately"


def _stage7_composite(profiles: list[PositionRisk], c: ConcentrationMetrics,
                      q: QuantMetrics, f: FactorExposure, income: IncomeRisk,
                      stress: StressResults, income_portfolio: bool) -> CompositeScore:
    W  = _W_INCOME if income_portfolio else _W_DEFAULT
    sc = _score_concentration(c)
    sv = _score_volatility(q)
    st = _score_tail(q, stress)
    sf = _score_factor(f)
    su = _score_fundamental(profiles)
    si = _score_income(income)

    score = (W["concentration"] * sc + W["volatility"] * sv + W["tail"] * st
             + W["factor"] * sf + W["fundamental"] * su + W["income"] * si)
    label, action = _risk_label_action(score)
    return CompositeScore(
        score=round(score, 1),
        label=label,
        action=action,
        sub_scores={
            "Concentration": round(sc, 1),
            "Volatility":    round(sv, 1),
            "Tail Risk":     round(st, 1),
            "Factor":        round(sf, 1),
            "Fundamental":   round(su, 1),
            "Income":        round(si, 1),
        },
    )


# ── Stage 8 — Rebalancing signals ────────────────────────────────────────────

def _stage8_rebalance(profiles: list[PositionRisk], concentration: ConcentrationMetrics,
                      quant: QuantMetrics, income: IncomeRisk,
                      stress: StressResults, total_value: float) -> RebalanceSignals:
    hard: list[str] = []
    soft: list[str] = []
    actions: list[dict] = []

    # Hard triggers
    for p in profiles:
        if p.weight > 0.20:
            hard.append(f"{p.ticker}: position weight {p.weight:.1%} exceeds 20% hard limit")
            actions.append({"ticker": p.ticker, "issue": "Overweight position (>20%)",
                            "action": "Trim to ≤15%; redeploy to underweights"})

    if quant.portfolio_beta > 1.5:
        hard.append(f"Portfolio beta {quant.portfolio_beta:.2f} exceeds 1.5 — amplified drawdown risk")
        actions.append({"ticker": "Portfolio", "issue": "Excessive beta (>1.5)",
                        "action": "Rotate into low-beta / defensive stocks"})

    if quant.var_99_1d_eur is not None and total_value > 0:
        var_pct = quant.var_99_1d_eur / total_value
        if var_pct > 0.03:
            hard.append(f"1-day 99% VaR = €{quant.var_99_1d_eur:,.0f} ({var_pct:.1%}) — exceeds 3% loss tolerance")

    if income.top3_cut_pct is not None and income.top3_cut_pct > 0.40:
        top3_tickers = ", ".join(t for t, _ in income.top3_income_shares[:3])
        hard.append(f"Top-3 dividend cut scenario removes {income.top3_cut_pct:.0%} of annual income")
        actions.append({"ticker": top3_tickers, "issue": "Income concentration (top-3 >40% at risk)",
                        "action": "Diversify income across more dividend payers"})

    worst_dd = min((r.portfolio_drawdown or 0.0) for r in stress.historical)
    if worst_dd < -0.40:
        hard.append(f"Worst-case historical scenario implies {worst_dd:.0%} portfolio drawdown")

    for p in profiles:
        if p.rating == "Critical":
            hard.append(f"{p.ticker}: Critical risk rating — review immediately")
            actions.append({"ticker": p.ticker, "issue": "Critical position risk",
                            "action": "Review fundamentals; consider reducing or exiting"})

    # Soft triggers
    if concentration.hhi > 0.15:
        soft.append(f"HHI {concentration.hhi:.3f} — concentration has drifted well above 0.10 diversified threshold")
        actions.append({"ticker": "Portfolio", "issue": "HHI elevated (>0.15)",
                        "action": "Add uncorrelated positions or sectors to reduce concentration"})
    elif concentration.hhi > 0.10:
        soft.append(f"HHI {concentration.hhi:.3f} — moderately concentrated, monitor drift")

    if concentration.sector_flag and concentration.largest_sector:
        w = concentration.sector_weights.get(concentration.largest_sector, 0.0)
        soft.append(f"{concentration.largest_sector} sector at {w:.0%} — exceeds 30% guideline")
        actions.append({"ticker": concentration.largest_sector, "issue": "Sector overconcentration (>30%)",
                        "action": "Reduce largest sector; add exposure to lagging sectors"})

    if income.weighted_dgr is not None and income.weighted_dgr < 0.025:
        soft.append(f"Weighted portfolio DGR {income.weighted_dgr:.1%} may trail inflation (~2.5%) — real income erosion risk")

    if quant.sharpe is not None and quant.sharpe < 1.0:
        soft.append(f"Sharpe ratio {quant.sharpe:.2f} below 1.0 — risk-adjusted return suboptimal")

    for p in profiles:
        if p.rating == "High":
            soft.append(f"{p.ticker}: High risk rating — monitor closely")

    if quant.high_corr_pairs:
        pairs_str = ", ".join(f"{a}/{b}" for a, b, _ in quant.high_corr_pairs[:3])
        soft.append(f"High correlation pairs (>0.80): {pairs_str} — limited diversification benefit")
        actions.append({"ticker": pairs_str, "issue": "Highly correlated holdings",
                        "action": "Replace one position per pair with uncorrelated exposure"})

    return RebalanceSignals(
        hard_triggers=hard,
        soft_triggers=soft,
        actions=actions,
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def assess_portfolio(pf_df: pd.DataFrame, cache: dict,
                     income_portfolio: bool = False) -> RiskReport:
    """
    Run the 8-stage risk assessment pipeline and return a RiskReport.

    pf_df            — enriched portfolio DataFrame; must have live_price,
                       current_value, sector, country, expected_annual, fair_value.
    cache            — fundamentals cache dict from screener._load_cache().
    income_portfolio — if True, income risk weight is elevated in Stage 7.
    """
    if pf_df is None or pf_df.empty:
        raise ValueError("Portfolio is empty — nothing to assess")

    pf = pf_df.copy()

    if "current_value" not in pf.columns:
        pf["current_value"] = (
            pf.get("live_price", pf.get("purchase_value", 0)) * pf.get("shares", 1)
        )
    if "expected_annual" not in pf.columns:
        pf["expected_annual"] = 0.0

    total_value = float(pf["current_value"].fillna(0).sum())
    tickers     = pf["ticker"].tolist()

    # Fetch 5-year price history for all positions in one batch call
    closes = _fetch_history(tickers, period="5y")

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

    s1 = _stage1_position_profiles(pf, cache, total_value)
    s2 = _stage2_concentration(pf, total_value)
    s3 = _stage3_quant(pf, cache, total_value, closes)
    s4 = _stage4_factor(port_rets)
    s5 = _stage5_income(pf, cache, total_value)
    s6 = _stage6_stress(pf, cache, s3.portfolio_beta, total_value, port_rets, s2)
    s7 = _stage7_composite(s1, s2, s3, s4, s5, s6, income_portfolio)
    s8 = _stage8_rebalance(s1, s2, s3, s5, s6, total_value)

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
        rebalance=s8,
    )
