"""
Portfolio persistence and data helpers.

The 'beleggingen' sheet has two main sections:
  - Open positions  (header row 1):  Aandeel / google.com / Aantal / Prijs / Doel / ... / in / uit
  - Sold positions  (header row 92): Aandeel / google.com / Aantal / Prijs / Waarde / ... / Verkoop / ... / Datum in / Datum uit

Both sections share the same column indices for the data we need.
"""

import json
from pathlib import Path

import pandas as pd

PORTFOLIO_FILE  = Path(__file__).parent / ".cache" / "portfolio.json"
SOLD_FILE       = Path(__file__).parent / ".cache" / "sold.json"
DIV_HIST_FILE   = Path(__file__).parent / ".cache" / "dividends_history.json"
WATCHLIST_FILE  = Path(__file__).parent / ".cache" / "watchlist.json"


# ── Persistence ───────────────────────────────────────────────────────────────

def _save(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(exist_ok=True)
    path.write_text(df.to_json(orient="records", date_format="iso", indent=2), encoding="utf-8")


def _load(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.DataFrame(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return None


def save_portfolio(df: pd.DataFrame) -> None:  _save(df, PORTFOLIO_FILE)
def save_sold(df: pd.DataFrame) -> None:       _save(df, SOLD_FILE)
def save_div_hist(df: pd.DataFrame) -> None:   _save(df, DIV_HIST_FILE)
def load_portfolio() -> pd.DataFrame | None:   return _load(PORTFOLIO_FILE)
def load_sold() -> pd.DataFrame | None:        return _load(SOLD_FILE)
def load_div_hist() -> pd.DataFrame | None:    return _load(DIV_HIST_FILE)
def portfolio_exists() -> bool:                return PORTFOLIO_FILE.exists()


def save_watchlist(tickers: set[str]) -> None:
    WATCHLIST_FILE.parent.mkdir(exist_ok=True)
    WATCHLIST_FILE.write_text(json.dumps(sorted(tickers), indent=2), encoding="utf-8")


def load_watchlist() -> set[str]:
    if not WATCHLIST_FILE.exists():
        return set()
    try:
        return set(json.loads(WATCHLIST_FILE.read_text(encoding="utf-8")))
    except Exception:
        return set()


# ── Excel parsing ─────────────────────────────────────────────────────────────

def _read_sheet(file) -> pd.DataFrame:
    """Read the beleggingen sheet using positional column indices (robust across sections)."""
    raw = pd.read_excel(file, sheet_name="beleggingen", header=None)

    # The column names we care about are at fixed positions regardless of section:
    #  0: name   1: google_ticker   2: shares   4: target/sale_price
    #  6: purchase_value   7: sale_value   10: dividends   16: date_in   17: date_out
    raw.columns = range(len(raw.columns))
    raw = raw.rename(columns={
        0:  "name",
        1:  "google_ticker",
        2:  "shares",
        4:  "target_price",
        6:  "purchase_value",
        7:  "sale_value",
        10: "dividends",
        16: "date_in",
        17: "date_out",
    })

    # Keep only rows with a valid EBR: ticker
    mask = raw["google_ticker"].astype(str).str.startswith("EBR:")
    return raw[mask].copy()


def parse_excel(file) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Parse the portfolio Excel file.
    Returns (open_positions, sold_positions, dividend_history) — all EBR: only.
    """
    df = _read_sheet(file)

    # Clean shared columns
    for col in ["shares", "purchase_value", "sale_value", "dividends", "target_price"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["date_in"]  = pd.to_datetime(df["date_in"],  errors="coerce")
    df["date_out"] = pd.to_datetime(df["date_out"], errors="coerce")
    df["ticker"]   = df["google_ticker"].str.split(":").str[1] + ".BR"

    has_exit = df["date_out"].notna()

    # Open positions: no exit date, has a target price
    open_df = df[~has_exit & df["target_price"].notna()].copy()

    # Sold positions: has exit date and a meaningful purchase value
    sold_df = df[has_exit & df["purchase_value"].notna() & (df["purchase_value"] > 100)].copy()

    # Dividend history: no exit date, no target price, purchase_value is the dividend amount
    div_df = df[
        ~has_exit &
        df["target_price"].isna() &
        df["purchase_value"].notna() &
        (df["purchase_value"] < 500) &
        df["date_in"].notna()
    ].copy()
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
