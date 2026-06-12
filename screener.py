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

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

# ── Constants ─────────────────────────────────────────────────────────────────

RISK_FREE_RATE      = 0.03    # Euro area approximation
EQUITY_RISK_PREMIUM = 0.05
DEFAULT_TAX_RATE    = 0.25
DEFAULT_BETA        = 1.0
DDM_STABLE_GROWTH   = 0.02    # Terminal growth rate for multi-stage DDM
DDM_HIGH_GROWTH_YRS = 5       # Number of high-growth years in 2-stage DDM

# Composite score weights — must sum to 1.0
W_MOS      = 0.30   # α — margin of safety
W_RISK     = 0.18   # β — risk (inverted: 100 - risk_pctrank)
W_QUALITY  = 0.22   # γ — quality
W_MOMENTUM = 0.15   # δ — momentum
W_DIVIDEND = 0.15   # ε — dividend score

# Decision thresholds
SCORE_STRONG_BUY = 70
SCORE_AVOID      = 40

MAX_WORKERS      = 4    # parallel yfinance requests
REQUEST_DELAY    = 0.3  # seconds between requests per worker
MAX_RETRIES      = 4    # retries on rate-limit (429), with exponential backoff
CACHE_TTL_HOURS  = 24
CACHE_FILE       = Path(__file__).parent / ".cache" / "fundamentals.json"

# ── Fields fetched from yfinance ──────────────────────────────────────────────

VALUATION_FIELDS = [
    "trailingEps",                  # Graham Number, PE fair value
    "bookValue",                    # Graham Number (BVPS)
    "trailingAnnualDividendRate",   # DDM single-stage
    "dividendRate",                 # Forward DPS (multi-stage DDM)
    "fiveYearAvgDividendYield",     # Yield vs historical average
    "targetMeanPrice",              # Analyst target
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

def _load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_FILE.parent.mkdir(exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _is_fresh(entry: dict) -> bool:
    try:
        fetched_at = datetime.fromisoformat(entry["fetched_at"])
        age_hours  = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 3600
        return age_hours < CACHE_TTL_HOURS
    except Exception:
        return False


# ── Data fetching ─────────────────────────────────────────────────────────────

def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _fetch_one(ticker: str, stock: dict) -> dict:
    info  = yf.Ticker(ticker).info
    mcap  = info.get("marketCap")
    price = info.get("currentPrice") or info.get("regularMarketPrice")

    row = {
        "Name":       info.get("shortName") or stock["name"],
        "Ticker":     ticker,
        "ISIN":       stock["isin"],
        "Price":      _safe_float(price),
        "Currency":   info.get("currency", "EUR"),
        "Market Cap": _safe_float(mcap),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

    # Display multiples — sanity-bounded
    for key in ("trailingPE", "priceToBook", "enterpriseToEbitda"):
        v = _safe_float(info.get(key))
        row[key] = v if (v is not None and 0 < v < 10_000) else None

    # Dividend yield — normalise pct vs decimal
    dy = _safe_float(info.get("dividendYield"))
    if dy is not None and dy > 1.0:
        dy /= 100
    row["dividendYield"] = dy

    # 5yr avg dividend yield — normalise
    avg_dy = _safe_float(info.get("fiveYearAvgDividendYield"))
    if avg_dy is not None and avg_dy > 1.0:
        avg_dy /= 100
    row["fiveYearAvgDividendYield"] = avg_dy

    # Debt/Equity — reject extreme outliers
    de = _safe_float(info.get("debtToEquity"))
    row["debtToEquity"] = de if (de is not None and de < 1000) else None

    # All remaining extra fields — stored raw
    for key in ALL_EXTRA_FIELDS:
        if key not in row:   # don't overwrite already-processed fields
            row[key] = _safe_float(info.get(key))

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


def fetch_fundamentals(stocks: list[dict]) -> pd.DataFrame:
    cache      = _load_cache()
    stale      = [s for s in stocks if not _is_fresh(cache.get(s["ticker"], {}))]
    fresh      = [s for s in stocks if _is_fresh(cache.get(s["ticker"], {}))]
    _lock      = threading.Lock()
    _done      = [0]

    if stale:
        print(f"  {len(fresh)} cached  |  {len(stale)} to fetch")
    else:
        print(f"  All {len(fresh)} tickers served from cache (max age {CACHE_TTL_HOURS}h)")

    def _fetch_and_store(stock):
        ticker = stock["ticker"]
        row = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                row = _fetch_one(ticker, stock)
                break
            except Exception as e:
                msg = str(e)
                if ("429" in msg or "Too Many Requests" in msg or "Rate limited" in msg
                        or "ConnectionResetError" in msg or "10054" in msg or "RemoteDisconnected" in msg):
                    wait = 2 ** attempt * 5   # 5s, 10s, 20s, 40s
                    if attempt < MAX_RETRIES:
                        time.sleep(wait)
                        continue
                print(f"\n  Warning: could not fetch {ticker}: {e}")
                break
        if row is None:
            row = {"Name": stock["name"], "Ticker": ticker,
                   "ISIN": stock["isin"], "fetched_at": ""}
        time.sleep(REQUEST_DELAY)
        with _lock:
            cache[ticker] = row
            _done[0] += 1
            print(f"  Fetching [{_done[0]}/{len(stale)}] {ticker}          ", end="\r")

    if stale:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            list(executor.map(_fetch_and_store, stale))
        _save_cache(cache)
        print()

    rows = [cache[s["ticker"]] for s in stocks if s["ticker"] in cache]
    return pd.DataFrame(rows)


# ── Stage 2: Fair value estimation ───────────────────────────────────────────

def _approx_wacc(beta) -> float:
    b = beta if (beta is not None and 0.1 <= beta <= 5.0) else DEFAULT_BETA
    return RISK_FREE_RATE + b * EQUITY_RISK_PREMIUM


def _ddm_single(div_rate, wacc, g) -> float | None:
    """Gordon growth single-stage DDM."""
    if not div_rate or div_rate <= 0:
        return None
    g = max(0.0, min(0.05, g or 0.02))
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
    g_high = max(0.0, min(0.15, g_high or 0.05))
    pv  = 0.0
    dps = div_rate
    for t in range(1, years + 1):
        dps = dps * (1 + g_high)
        pv += dps / (1 + wacc) ** t
    terminal_dps = dps * (1 + g_stable)
    tv  = terminal_dps / (wacc - g_stable)
    pv += tv / (1 + wacc) ** years
    return pv if 0 < pv < 1e6 else None


def _fair_value_models(row: pd.Series) -> dict:
    price    = row.get("Price")
    eps      = row.get("trailingEps")
    bvps     = row.get("bookValue")
    div_rate = row.get("trailingAnnualDividendRate") or row.get("dividendRate")
    payout   = row.get("payoutRatio")
    analyst  = row.get("targetMeanPrice")
    ebit     = row.get("ebit")
    ev       = row.get("enterpriseValue")
    beta     = row.get("beta")
    eg       = row.get("earningsGrowth")

    wacc = _approx_wacc(beta)

    # Graham Number
    gn = None
    if eps and bvps and eps > 0 and bvps > 0:
        gn = (22.5 * eps * bvps) ** 0.5

    # PE Fair Value (Graham conservative: EPS × 15)
    pe_fv = (eps * 15) if (eps and eps > 0) else None

    # Earnings Power Value (EPV = EBIT×(1-t)/WACC, scaled to per-share via EV ratio)
    epv = None
    if ebit and ebit > 0 and ev and ev > 0 and price and price > 0:
        epv_ev = ebit * (1 - DEFAULT_TAX_RATE) / wacc
        epv    = price * (epv_ev / ev)

    # DDM weight guidance:
    # — zero weight if no dividend, payout > 90%, or payout < 5%
    # — higher weight (up to 0.40 combined) for established payers with 30–70% payout
    is_dividend_payer = bool(div_rate and div_rate > 0)
    payout_ok = payout and 0.05 <= payout <= 0.90
    ddm_eligible = is_dividend_payer and payout_ok

    ddm1 = _ddm_single(div_rate, wacc, eg)     if ddm_eligible else None
    ddm2 = _ddm_multistage(div_rate, wacc, eg) if ddm_eligible else None

    # Base weights
    candidates = [
        (gn,      0.18),
        (pe_fv,   0.18),
        (epv,     0.19),
        (ddm1,    0.20 if ddm_eligible else 0.0),
        (ddm2,    0.20 if ddm_eligible else 0.0),
        (analyst, 0.25),
    ]
    avail = [(v, w) for v, w in candidates if v is not None and v > 0 and w > 0]
    if not avail:
        return {"graham_number": gn, "pe_fair_value": pe_fv, "epv": epv,
                "ddm": ddm1, "ddm_multistage": ddm2, "fair_value": None}

    total_w = sum(w for _, w in avail)
    iv      = sum(v * w / total_w for v, w in avail)

    return {
        "graham_number":  gn,
        "pe_fair_value":  pe_fv,
        "epv":            epv,
        "ddm":            round(ddm1, 2) if ddm1 else None,
        "ddm_multistage": round(ddm2, 2) if ddm2 else None,
        "fair_value":     round(iv, 2),
    }


# ── Stage 3: MoS, TER, Dividend Sustainability Flag ──────────────────────────

def _margin_of_safety(price, fair_value) -> float | None:
    if price and fair_value and fair_value > 0 and price > 0:
        return (fair_value - price) / fair_value
    return None


def _total_expected_return(price, fair_value, div_yield, dgr) -> float | None:
    """TER = capital gain % + forward dividend yield + expected DGR (all as %)."""
    if not price or price <= 0:
        return None
    cap_gain = ((fair_value - price) / price * 100) if fair_value else 0.0
    dy       = (div_yield * 100) if div_yield else 0.0
    dg       = (max(0.0, min(0.10, dgr)) * 100) if dgr else 0.0
    return round(cap_gain + dy + dg, 1)


def _dividend_sustainability_flag(row: pd.Series) -> str:
    """
    Returns 'At Risk', 'OK', or '' (non-payer).
    Checks: payout ratio, cash payout ratio, dividend coverage ratio.
    """
    div_rate = row.get("trailingAnnualDividendRate") or row.get("dividendRate")
    if not div_rate or div_rate <= 0:
        return ""  # non-payer, no flag

    payout   = row.get("payoutRatio")
    cpr      = row.get("cashPayoutRatio")
    coverage = row.get("dividendCoverage")

    if (payout   and payout   > 0.90) or \
       (cpr      and cpr      > 0.80) or \
       (coverage and coverage < 1.20):
        return "At Risk"
    return "OK"


# ── Stage 4: Risk scoring ─────────────────────────────────────────────────────

def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _financial_health_score(row: pd.Series) -> float:
    """0–10, higher = healthier."""
    scores = []
    de = row.get("debtToEquity")
    if de is not None:
        de_ratio = de / 100   # yfinance: 100 = 1.0×
        scores.append(_clamp(10 - de_ratio * 2.5, 0, 10))
    cr = row.get("currentRatio")
    if cr is not None:
        scores.append(_clamp((cr - 0.5) / 0.15, 0, 10))
    ic = row.get("interestCoverage")
    if ic is not None and ic > 0:
        scores.append(_clamp(ic / 2, 0, 10))
    return float(np.mean(scores)) if scores else 5.0


def _earnings_quality_score(row: pd.Series) -> float:
    """0–10, higher = better quality."""
    fcf = row.get("freeCashflow")
    ni  = row.get("netIncome")
    if fcf is None or ni is None or ni == 0:
        return 5.0
    return float(_clamp(5 + (fcf / abs(ni)) * 3, 0, 10))


def _market_risk_score(row: pd.Series) -> float:
    """0–10, higher = lower beta risk."""
    beta = row.get("beta")
    if beta is None:
        return 5.0
    return float(_clamp(10 - abs(beta) * 3.5, 0, 10))


def _dividend_risk_score(row: pd.Series) -> float:
    """
    0–10, higher = lower dividend risk.
    For non-payers: neutral 5.0.
    """
    div_rate = row.get("trailingAnnualDividendRate") or row.get("dividendRate")
    if not div_rate or div_rate <= 0:
        return 5.0  # neutral for non-payers

    scores = []
    payout = row.get("payoutRatio")
    if payout is not None and payout > 0:
        if 0.30 <= payout <= 0.70:
            scores.append(10.0)
        elif payout < 0.30:
            scores.append(7.0)
        elif payout <= 0.85:
            scores.append(4.0)
        else:
            scores.append(0.0)   # > 85% at risk

    cpr = row.get("cashPayoutRatio")
    if cpr is not None:
        scores.append(_clamp(10 - cpr * 10, 0, 10))  # 0% = 10, 100% = 0

    coverage = row.get("dividendCoverage")
    if coverage is not None:
        scores.append(_clamp(coverage * 2, 0, 10))    # 1.5× = 3, 5× = 10

    eg = row.get("earningsGrowth")
    if eg is not None:
        scores.append(_clamp(5 + eg * 25, 0, 10))     # DGR proxy

    return float(np.mean(scores)) if scores else 5.0


def _liquidity_score(row: pd.Series) -> float:
    """0–10, higher = more liquid."""
    vol = row.get("averageVolume")
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
    roe = row.get("returnOnEquity")
    if roe is not None: scores.append(_clamp(roe * 50, 0, 10))
    roa = row.get("returnOnAssets")
    if roa is not None: scores.append(_clamp(roa * 100, 0, 10))
    om  = row.get("operatingMargins")
    if om  is not None: scores.append(_clamp(om * 50, 0, 10))
    fcy = row.get("fcfYield")
    if fcy is not None: scores.append(_clamp(fcy * 100, 0, 10))
    cr  = row.get("currentRatio")
    if cr  is not None: scores.append(_clamp((cr - 0.5) / 0.15, 0, 10))
    return float(np.mean(scores)) if scores else 5.0


def _momentum_raw(row: pd.Series) -> float:
    """0–10 composite of growth and analyst sentiment."""
    scores = []
    eg = row.get("earningsGrowth")
    if eg is not None: scores.append(_clamp(5 + eg * 25, 0, 10))
    rg = row.get("revenueGrowth")
    if rg is not None: scores.append(_clamp(5 + rg * 25, 0, 10))
    rm = row.get("recommendationMean")
    if rm is not None: scores.append(_clamp((5 - rm) / 4 * 10, 0, 10))
    return float(np.mean(scores)) if scores else 5.0


def _dividend_score_raw(row: pd.Series) -> float:
    """
    0–10 composite dividend attractiveness score.
    Combines: yield vs 5-yr average, payout safety, cash coverage, DGR proxy.
    Non-payers get neutral 5.0 so they are not penalised.
    """
    div_rate = row.get("trailingAnnualDividendRate") or row.get("dividendRate")
    if not div_rate or div_rate <= 0:
        return 5.0   # neutral — non-payer is neither rewarded nor penalised

    scores = []

    # 1. Current yield vs 5-year average yield
    dy      = row.get("dividendYield")
    avg_dy  = row.get("fiveYearAvgDividendYield")
    if dy and avg_dy and avg_dy > 0:
        ratio = dy / avg_dy
        scores.append(_clamp(ratio * 5, 0, 10))  # at avg = 5, 2× avg = 10

    # 2. Payout ratio sustainability
    payout = row.get("payoutRatio")
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
    cpr = row.get("cashPayoutRatio")
    if cpr is not None:
        scores.append(_clamp(10 - cpr * 10, 0, 10))

    # 4. Dividend coverage ratio
    coverage = row.get("dividendCoverage")
    if coverage is not None:
        scores.append(_clamp(coverage * 2, 0, 10))

    # 5. DGR proxy (earnings growth as best available approximation)
    eg = row.get("earningsGrowth")
    if eg is not None:
        scores.append(_clamp(5 + eg * 25, 0, 10))

    return float(np.mean(scores)) if scores else 5.0


# ── Stage 5: Composite score ──────────────────────────────────────────────────

def _pct_rank(series: pd.Series, ascending=True) -> pd.Series:
    """Percentile rank 0–100. NaN rows receive 50 (neutral)."""
    ranked = series.rank(pct=True, na_option="keep") * 100
    if not ascending:
        ranked = 100 - ranked
    return ranked.fillna(50.0)


def compute_scores(df: pd.DataFrame) -> pd.DataFrame:
    # Ensure all expected columns exist (older cache may be missing new fields)
    all_fields = [
        *VALUATION_FIELDS, *RISK_FIELDS, *QUALITY_FIELDS, *MOMENTUM_FIELDS,
        "fcfYield", "cashPayoutRatio", "dividendCoverage",
    ]
    df = df.reindex(columns=[*df.columns, *[f for f in all_fields if f not in df.columns]])

    # ── Stage 2: fair values ──────────────────────────────────────────────────
    fv_cols = df.apply(_fair_value_models, axis=1, result_type="expand")
    for col in fv_cols.columns:
        df[col] = fv_cols[col]

    # ── Stage 3: MoS · TER · Dividend Sustainability ─────────────────────────
    df["margin_of_safety"] = df.apply(
        lambda r: _margin_of_safety(r["Price"], r["fair_value"]), axis=1
    )
    df["TER %"] = df.apply(
        lambda r: _total_expected_return(
            r["Price"], r["fair_value"],
            r.get("dividendYield"), r.get("earningsGrowth")
        ), axis=1
    )
    df["Div Flag"] = df.apply(_dividend_sustainability_flag, axis=1)

    # ── Stage 4: raw dimension scores (0–10) ─────────────────────────────────
    df["_risk_raw"]     = df.apply(_composite_risk_raw, axis=1)
    df["_quality_raw"]  = df.apply(_quality_raw,        axis=1)
    df["_momentum_raw"] = df.apply(_momentum_raw,       axis=1)
    df["_dividend_raw"] = df.apply(_dividend_score_raw, axis=1)

    # Hard veto: D/E > 500 (≈5×) OR FCF negative OR dividend flagged at risk
    # with coverage < 1.0 (imminent cut risk)
    de       = df["debtToEquity"].fillna(0)
    fcf      = df["freeCashflow"].fillna(0)
    coverage = df["dividendCoverage"].fillna(999)
    df["_hard_veto"] = (de > 500) | (fcf < 0) | (
        (df["Div Flag"] == "At Risk") & (coverage < 1.0)
    )

    # ── Stage 5: percentile ranks → 0–100 ────────────────────────────────────
    mos_rank      = _pct_rank(df["margin_of_safety"], ascending=True)
    risk_rank     = _pct_rank(df["_risk_raw"],         ascending=False)  # lower = better
    quality_rank  = _pct_rank(df["_quality_raw"],      ascending=True)
    momentum_rank = _pct_rank(df["_momentum_raw"],     ascending=True)
    dividend_rank = _pct_rank(df["_dividend_raw"],     ascending=True)

    score = (
        W_MOS      * mos_rank
        + W_RISK   * risk_rank
        + W_QUALITY   * quality_rank
        + W_MOMENTUM  * momentum_rank
        + W_DIVIDEND  * dividend_rank
    ).round(1)

    score[df["_hard_veto"]] = 0.0
    df["Value Score"] = score

    # ── Stage 6: decision ────────────────────────────────────────────────────
    def _decision(row):
        if row["_hard_veto"]:
            return "Avoid"
        s = row["Value Score"]
        if s >= SCORE_STRONG_BUY:
            return "Strong Buy"
        if s >= SCORE_AVOID:
            return "Monitor"
        return "Avoid"

    df["Decision"]   = df.apply(_decision, axis=1)
    df["Risk Score"] = df["_risk_raw"].round(1)
    df["MoS %"]      = (df["margin_of_safety"] * 100).round(1)

    # Drop internal columns
    df = df.drop(columns=[c for c in df.columns if c.startswith("_")])
    df = df.sort_values("Value Score", ascending=False).reset_index(drop=True)
    df.index += 1
    return df


def run_screener(stocks: list[dict]) -> pd.DataFrame:
    print(f"Fetching fundamentals for {len(stocks)} stocks...")
    df = fetch_fundamentals(stocks)
    return _score_and_clean(df)


def run_screener_from_df(df: pd.DataFrame) -> pd.DataFrame:
    """Score and clean a DataFrame that was already fetched (avoids re-fetching)."""
    return _score_and_clean(df.copy())


def _score_and_clean(df: pd.DataFrame) -> pd.DataFrame:
    before  = len(df)
    df      = df[df["Price"].notna()].reset_index(drop=True)
    dropped = before - len(df)
    if dropped:
        print(f"  Dropped {dropped} ticker(s) with no price (likely delisted/inactive)")
    print("Computing valuation scores...")
    return compute_scores(df)
