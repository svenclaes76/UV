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

_SUFFIX_MAP = {"EBR": ".BR", "AMS": ".AS"}

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
    mask = section["google_ticker"].astype(str).str.startswith(("EBR:", "AMS:"))
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
