"""
Fetches fundamentals for each ticker via yfinance and computes a value score.

Metrics used (all lower = better value, except dividend yield):
  - P/E ratio          (trailingPE)
  - P/B ratio          (priceToBook)
  - EV/EBITDA          (enterpriseToEbitda)
  - Debt/Equity        (debtToEquity)
  - Dividend yield     (dividendYield)  — higher is better

Scoring: each metric is percentile-ranked across the universe.
Final score = average percentile (0–100, higher = more undervalued).

Caching: fundamentals are stored in .cache/fundamentals.json.
Each ticker entry records a fetched_at timestamp; entries older than
CACHE_TTL_HOURS are re-fetched on the next run.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

METRICS = {
    "trailingPE":          {"label": "P/E",         "lower_is_better": True},
    "priceToBook":         {"label": "P/B",          "lower_is_better": True},
    "enterpriseToEbitda":  {"label": "EV/EBITDA",    "lower_is_better": True},
    "debtToEquity":        {"label": "Debt/Equity",  "lower_is_better": True},
    "dividendYield":       {"label": "Div. Yield",   "lower_is_better": False},
}

RATE_LIMIT_DELAY = 0.3       # seconds between yfinance calls
CACHE_TTL_HOURS   = 1       # re-fetch after this many hours
CACHE_FILE        = Path(__file__).parent / ".cache" / "fundamentals.json"


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
        age_hours = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 3600
        return age_hours < CACHE_TTL_HOURS
    except Exception:
        return False


# ── Fundamentals fetching ─────────────────────────────────────────────────────

def _sanitize(key: str, val) -> float | None:
    if val is None:
        return None
    try:
        val = float(val)
    except (TypeError, ValueError):
        return None
    if val < 0:
        return None
    if key == "trailingPE" and val > 200:
        return None
    if key == "debtToEquity" and val > 1000:
        return None
    # yfinance sometimes returns dividendYield as a percentage (e.g. 8.98)
    # instead of a decimal (0.0898) — normalize anything implausibly > 1.0
    if key == "dividendYield" and val > 1.0:
        val = val / 100
    return val


def _fetch_one(ticker: str, stock: dict) -> dict:
    info = yf.Ticker(ticker).info
    row = {
        "Name":       info.get("shortName") or stock["name"],
        "Ticker":     ticker,
        "ISIN":       stock["isin"],
        "Price":      info.get("currentPrice") or info.get("regularMarketPrice"),
        "Currency":   info.get("currency", "EUR"),
        "Market Cap": info.get("marketCap"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    for key in METRICS:
        row[key] = _sanitize(key, info.get(key))
    return row


def fetch_fundamentals(stocks: list[dict]) -> pd.DataFrame:
    cache = _load_cache()
    rows = []
    stale = [s for s in stocks if not _is_fresh(cache.get(s["ticker"], {}))]
    fresh = [s for s in stocks if _is_fresh(cache.get(s["ticker"], {}))]

    if stale:
        print(f"  {len(fresh)} cached  |  {len(stale)} to fetch")
    else:
        print(f"  All {len(fresh)} tickers served from cache (max age {CACHE_TTL_HOURS}h)")

    for i, stock in enumerate(stale, 1):
        ticker = stock["ticker"]
        print(f"  Fetching [{i}/{len(stale)}] {ticker}          ", end="\r")
        try:
            row = _fetch_one(ticker, stock)
            cache[ticker] = row
        except Exception as e:
            print(f"\n  Warning: could not fetch {ticker}: {e}")
            # Keep stale entry if available rather than dropping the ticker
            if ticker not in cache:
                cache[ticker] = {"Name": stock["name"], "Ticker": ticker,
                                 "ISIN": stock["isin"], "fetched_at": ""}
        time.sleep(RATE_LIMIT_DELAY)

    if stale:
        _save_cache(cache)
        print()  # newline after progress

    # Build rows from cache in original ticker order
    for stock in stocks:
        entry = cache.get(stock["ticker"])
        if entry:
            rows.append(entry)

    return pd.DataFrame(rows)


# ── Scoring ───────────────────────────────────────────────────────────────────

def compute_scores(df: pd.DataFrame) -> pd.DataFrame:
    score_cols = []
    for key, meta in METRICS.items():
        col = f"_score_{key}"
        valid = df[key].notna()
        if valid.sum() < 2:
            df[col] = 50.0
        else:
            ranked = df[key].rank(pct=True, na_option="keep") * 100
            df[col] = ranked if not meta["lower_is_better"] else (100 - ranked)
        score_cols.append(col)

    df["Value Score"] = df[score_cols].mean(axis=1).round(1)
    df = df.drop(columns=score_cols)
    df = df.sort_values("Value Score", ascending=False).reset_index(drop=True)
    df.index += 1
    return df


def run_screener(stocks: list[dict]) -> pd.DataFrame:
    print(f"Fetching fundamentals for {len(stocks)} stocks...")
    df = fetch_fundamentals(stocks)
    before = len(df)
    df = df[df["Price"].notna()].reset_index(drop=True)
    dropped = before - len(df)
    if dropped:
        print(f"  Dropped {dropped} ticker(s) with no price (likely delisted/inactive)")
    print("Computing value scores...")
    df = compute_scores(df)
    return df
