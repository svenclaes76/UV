"""
Portfolio persistence and data helpers.

The 'beleggingen' sheet has two main sections:
  - Open positions  (header row 1):  Aandeel / google.com / Aantal / Prijs / Doel / ... / in / uit
  - Sold positions  (header row 92): Aandeel / google.com / Aantal / Prijs / Waarde / ... / Verkoop / ... / Datum in / Datum uit

Both sections share the same column indices for the data we need.
"""

import hashlib
import json
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from crypto import read_encrypted, write_encrypted  # noqa: E402

_BASE_DIR  = Path(__file__).parent / "data" / "portfolio"
_CACHE_DIR = Path(__file__).parent / ".cache"
_BASE_DIR.mkdir(parents=True, exist_ok=True)

# Active user set once per session via set_user()
_active_email: str = ""


def set_user(email: str) -> None:
    global _active_email
    _active_email = email.strip().lower()


def _user_dir(email: str = "") -> Path:
    e = (email or _active_email).strip().lower()
    slug = hashlib.sha256(e.encode()).hexdigest()[:16] if e else "default"
    d = _BASE_DIR / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def user_data_dir(email: str = "") -> Path:
    """Public accessor used by backup."""
    return _user_dir(email)


# ── Persistence ───────────────────────────────────────────────────────────────

def _save(df: pd.DataFrame, path: Path) -> None:
    write_encrypted(path, df.to_json(orient="records", date_format="iso", indent=2))


def _load(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.DataFrame(json.loads(read_encrypted(path)))
    except Exception:
        return None


def save_portfolio(df: pd.DataFrame) -> None:  _save(df, _user_dir() / "portfolio.json")
def save_sold(df: pd.DataFrame) -> None:       _save(df, _user_dir() / "sold.json")
def save_div_hist(df: pd.DataFrame) -> None:   _save(df, _user_dir() / "dividends_history.json")
def load_portfolio() -> pd.DataFrame | None:   return _load(_user_dir() / "portfolio.json")
def load_sold() -> pd.DataFrame | None:        return _load(_user_dir() / "sold.json")
def load_div_hist() -> pd.DataFrame | None:    return _load(_user_dir() / "dividends_history.json")
def portfolio_exists() -> bool:                return (_user_dir() / "portfolio.json").exists()


# ── CRUD helpers ──────────────────────────────────────────────────────────────

def add_position(row: dict) -> None:
    """Append a new open position and persist."""
    df = load_portfolio()
    new_row = pd.DataFrame([row])
    df = pd.concat([df, new_row], ignore_index=True) if df is not None else new_row
    save_portfolio(df)


def remove_positions(indices: list[int]) -> None:
    """Drop rows by integer index and persist."""
    df = load_portfolio()
    if df is None:
        return
    save_portfolio(df.drop(index=indices).reset_index(drop=True))


def update_positions(df: pd.DataFrame) -> None:
    """Persist a fully-updated positions DataFrame."""
    save_portfolio(df)


def sell_position(ticker: str, shares: int, proceeds: float, sell_date: str) -> None:
    """Move a position from portfolio to sold, persist both files."""
    pf = load_portfolio()
    if pf is None:
        return
    mask = pf["ticker"] == ticker
    if not mask.any():
        return
    row = pf[mask].iloc[0].copy()
    purchase_value = float(row.get("purchase_value") or 0)
    dividends      = float(row.get("dividends") or 0)
    # Compute annual return
    try:
        _date_in  = pd.to_datetime(row.get("date_in"),  errors="coerce")
        _date_out = pd.to_datetime(sell_date,            errors="coerce")
        _held_days = (_date_out - _date_in).days
        if _held_days > 0 and purchase_value > 0:
            _total_value = proceeds + dividends
            annual_return_pct = round(
                ((_total_value / purchase_value) ** (365 / _held_days) - 1) * 100, 2
            )
        else:
            annual_return_pct = None
    except Exception:
        annual_return_pct = None
    # Build sold record
    sold_row = {
        "name":              row.get("name", ""),
        "google_ticker":     row.get("google_ticker", ""),
        "ticker":            ticker,
        "shares":            shares,
        "purchase_value":    purchase_value,
        "sale_value":        round(proceeds, 2),
        "dividends":         dividends,
        "date_in":           row.get("date_in", ""),
        "date_out":          sell_date,
        "annual_return_pct": annual_return_pct,
    }
    sold_df = load_sold()
    new_row = pd.DataFrame([sold_row])
    sold_df = pd.concat([sold_df, new_row], ignore_index=True) if sold_df is not None else new_row
    save_sold(sold_df)
    # Remove from portfolio
    pf = pf[~mask].reset_index(drop=True)
    save_portfolio(pf)


def add_dividend(row: dict) -> None:
    """Append a dividend record and update portfolio totals."""
    df = load_div_hist()
    new_row = pd.DataFrame([row])
    df = pd.concat([df, new_row], ignore_index=True) if df is not None else new_row
    save_div_hist(df)
    _sync_portfolio_dividends(df)


def update_div_hist(df: pd.DataFrame) -> None:
    """Persist updated dividend history and sync portfolio totals."""
    save_div_hist(df)
    _sync_portfolio_dividends(df)


def _sync_portfolio_dividends(div_df: "pd.DataFrame") -> None:
    """Recompute portfolio.dividends from div_hist totals per ticker."""
    pf = load_portfolio()
    if pf is None:
        return
    div_df["amount"] = pd.to_numeric(div_df["amount"], errors="coerce").fillna(0)
    totals = div_df.groupby("ticker")["amount"].sum()
    pf["dividends"] = pf["ticker"].map(totals).fillna(pf["dividends"].fillna(0))
    save_portfolio(pf)


def save_cash(df: pd.DataFrame) -> None:    _save(df, _user_dir() / "cash.json")
def load_cash() -> pd.DataFrame | None:    return _load(_user_dir() / "cash.json")


# ── Value history ─────────────────────────────────────────────────────────────

def load_value_history() -> pd.DataFrame | None:
    return _load(_user_dir() / "value_history.json")


def save_value_history(df: pd.DataFrame) -> None:
    _save(df, _user_dir() / "value_history.json")


def record_value_snapshot(invested: float, value: float) -> None:
    """Upsert today's portfolio value snapshot (one row per calendar day)."""
    import datetime
    today = datetime.date.today().isoformat()
    hist = load_value_history()
    if hist is None or hist.empty:
        hist = pd.DataFrame(columns=["date", "invested", "value"])
    # Replace today's entry if it exists, otherwise append
    hist = hist[hist["date"] != today]
    new_row = pd.DataFrame([{"date": today, "invested": round(invested, 2), "value": round(value, 2)}])
    hist = pd.concat([hist, new_row], ignore_index=True)
    hist = hist.sort_values("date").reset_index(drop=True)
    save_value_history(hist)

def backfill_value_history(open_df: pd.DataFrame, sold_df: pd.DataFrame | None = None) -> int:
    """
    Rebuild full portfolio value history from yfinance price data.
    Combines open + sold positions, fetches daily OHLC, and saves one row per trading day.
    Returns the number of data points written.
    """
    import datetime
    import yfinance as yf

    # Build a unified list of (ticker, shares, date_in, date_out)
    segments: list[dict] = []

    for _, row in open_df.iterrows():
        ticker = str(row.get("ticker", "") or "").strip()
        shares = pd.to_numeric(row.get("shares"), errors="coerce")
        date_in = pd.to_datetime(row.get("date_in"), errors="coerce")
        purchase_value = pd.to_numeric(row.get("purchase_value"), errors="coerce")
        if not ticker or pd.isna(shares) or pd.isna(date_in):
            continue
        segments.append({
            "ticker": ticker,
            "shares": shares,
            "date_in": date_in,
            "date_out": pd.Timestamp(datetime.date.today()),
            "purchase_value": float(purchase_value) if pd.notna(purchase_value) else 0.0,
        })

    if sold_df is not None and not sold_df.empty:
        for _, row in sold_df.iterrows():
            ticker = str(row.get("ticker", "") or "").strip()
            shares = pd.to_numeric(row.get("shares"), errors="coerce")
            date_in = pd.to_datetime(row.get("date_in"), errors="coerce")
            date_out = pd.to_datetime(row.get("date_out"), errors="coerce")
            purchase_value = pd.to_numeric(row.get("purchase_value"), errors="coerce")
            if not ticker or pd.isna(shares) or pd.isna(date_in) or pd.isna(date_out):
                continue
            segments.append({
                "ticker": ticker,
                "shares": shares,
                "date_in": date_in,
                "date_out": date_out,
                "purchase_value": float(purchase_value) if pd.notna(purchase_value) else 0.0,
            })

    if not segments:
        return 0

    # Date range covering all positions
    earliest = min(s["date_in"] for s in segments)
    latest   = pd.Timestamp(datetime.date.today())

    # Fetch daily close prices for all unique tickers + benchmark indices
    _BENCHMARKS = {"^GSPC": "benchmark_spx", "^STOXX50E": "benchmark_stoxx"}
    tickers = list({s["ticker"] for s in segments})
    fetch_tickers = tickers + list(_BENCHMARKS)
    raw = yf.download(
        fetch_tickers,
        start=earliest.strftime("%Y-%m-%d"),
        end=(latest + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
    )

    if raw.empty:
        return 0

    # Extract Close prices; handle single-ticker (flat) vs multi-ticker (MultiIndex)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw["Close"]
    else:
        close = raw[["Close"]].rename(columns={"Close": fetch_tickers[0]})

    close = close.ffill()

    # Pre-compute tranches for each benchmark index:
    # simulate investing each position's purchase_value into the index on date_in.
    def _build_tranches(index_series: "pd.Series") -> list[dict]:
        tranches = []
        for seg in segments:
            available = index_series[index_series.index >= seg["date_in"]]
            if not available.empty and pd.notna(available.iloc[0]):
                units = seg["purchase_value"] / float(available.iloc[0])
                tranches.append({"date_in": seg["date_in"], "units": units})
        return tranches

    benchmark_tranches = {
        col: _build_tranches(close[ticker])
        for ticker, col in _BENCHMARKS.items()
        if ticker in close.columns
    }

    # Build a daily date index (trading days present in data)
    all_dates = close.index

    # For each date sum value of all positions active on that day
    rows = []
    for date in all_dates:
        total_value    = 0.0
        total_invested = 0.0
        for seg in segments:
            if seg["date_in"] <= date <= seg["date_out"]:
                ticker = seg["ticker"]
                if ticker in close.columns:
                    price = close.at[date, ticker]
                    if pd.notna(price):
                        total_value += seg["shares"] * float(price)
                        total_invested += seg["purchase_value"]

        if total_value > 0:
            row: dict = {
                "date":     date.date().isoformat(),
                "invested": round(total_invested, 2),
                "value":    round(total_value, 2),
            }
            for ticker, col in _BENCHMARKS.items():
                if col in benchmark_tranches and ticker in close.columns:
                    idx_price = close.at[date, ticker]
                    if pd.notna(idx_price):
                        bv = sum(
                            t["units"] * float(idx_price)
                            for t in benchmark_tranches[col]
                            if t["date_in"] <= date
                        )
                        row[col] = round(bv, 2) if bv > 0 else None
                    else:
                        row[col] = None
                else:
                    row[col] = None
            rows.append(row)

    if not rows:
        return 0

    new_hist = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    save_value_history(new_hist)
    return len(new_hist)


def save_watchlist(tickers: set[str]) -> None:
    write_encrypted(_user_dir() / "watchlist.json", json.dumps(sorted(tickers), indent=2))


def load_watchlist() -> set[str]:
    path = _user_dir() / "watchlist.json"
    if not path.exists():
        return set()
    try:
        return set(json.loads(read_encrypted(path)))
    except Exception:
        return set()


def save_manual_tickers(tickers: dict[str, str]) -> None:
    """Persist manually added foreign-market tickers as {ticker: name}."""
    write_encrypted(_user_dir() / "manual_tickers.json", json.dumps(tickers, indent=2))


def load_manual_tickers() -> dict[str, str]:
    """Return manually added foreign-market tickers as {ticker: name}."""
    path = _user_dir() / "manual_tickers.json"
    if not path.exists():
        return {}
    try:
        return json.loads(read_encrypted(path))
    except Exception:
        return {}


# ── Excel parsing ─────────────────────────────────────────────────────────────

_COL_NAMES = {
    0:  "name",
    1:  "google_ticker",
    2:  "shares",
    4:  "target_price",
    6:  "purchase_value",
    7:  "sale_value",
    10: "dividends",
    16: "date_in",
    17: "date_out",
}

_SUFFIX_MAP = {"EBR": ".BR", "AMS": ".AS", "EPA": ".PA", "BIT": ".MI", "ETR": ".DE", "SWX": ".SW"}

# Fixed row ranges (1-indexed as in Excel, converted to 0-indexed iloc below)
# Row 1 = header, rows 2-19 = positions, rows 20-91 = dividends, rows 95-110 = sold
_ROWS_POSITIONS = slice(1, 19)    # Excel rows 2–19
_ROWS_DIVIDENDS = slice(19, 91)   # Excel rows 20–91
_ROWS_SOLD      = slice(94, 110)  # Excel rows 95–110


def _prep_section(raw: "pd.DataFrame", rows: slice) -> "pd.DataFrame":
    """Slice raw sheet, rename columns, add ticker, drop rows without a valid ticker."""
    section = raw.iloc[rows].copy()
    section.columns = range(len(section.columns))
    section = section.rename(columns=_COL_NAMES)
    mask = section["google_ticker"].astype(str).str.startswith(tuple(f"{k}:" for k in _SUFFIX_MAP))
    section = section[mask].copy()
    section["ticker"] = section["google_ticker"].apply(
        lambda v: v.split(":")[1] + _SUFFIX_MAP.get(v.split(":")[0], ".BR")
        if isinstance(v, str) and ":" in v else None
    )
    return section


def parse_excel(file) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Parse the portfolio Excel file using fixed row ranges.
    Returns (open_positions, sold_positions, dividend_history).
    """
    raw = pd.read_excel(file, sheet_name="beleggingen", header=None)

    open_df = _prep_section(raw, _ROWS_POSITIONS)
    div_raw = _prep_section(raw, _ROWS_DIVIDENDS)
    sold_df = _prep_section(raw, _ROWS_SOLD)

    # Clean numeric/date columns
    for df in [open_df, sold_df]:
        for col in ["shares", "purchase_value", "sale_value", "dividends", "target_price"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["date_in"]  = pd.to_datetime(df["date_in"],  errors="coerce")
        df["date_out"] = pd.to_datetime(df["date_out"], errors="coerce")

    for col in ["shares", "purchase_value"]:
        div_raw[col] = pd.to_numeric(div_raw[col], errors="coerce")
    div_raw["date_in"] = pd.to_datetime(div_raw["date_in"], errors="coerce")

    div_df = div_raw[div_raw["date_in"].notna()].copy()
    div_df = div_df.rename(columns={"purchase_value": "amount", "date_in": "date"})

    open_cols = ["name", "google_ticker", "ticker", "shares",
                 "purchase_value", "target_price", "dividends", "date_in"]
    sold_cols = ["name", "google_ticker", "ticker", "shares",
                 "purchase_value", "sale_value", "dividends", "date_in", "date_out"]
    div_cols  = ["name", "google_ticker", "ticker", "shares", "amount", "date"]

    return (
        open_df[open_cols].reset_index(drop=True),
        sold_df[sold_cols].reset_index(drop=True),
        div_df[div_cols].reset_index(drop=True),
    )
