"""
Portfolio persistence and data helpers.

The 'beleggingen' sheet has two main sections:
  - Open positions  (header row 1):  Aandeel / google.com / Aantal / Prijs / Doel / ... / in / uit
  - Sold positions  (header row 92): Aandeel / google.com / Aantal / Prijs / Waarde / ... / Verkoop / ... / Datum in / Datum uit

Both sections share the same column indices for the data we need.
"""

import hashlib
import json
import threading
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from crypto import read_encrypted, write_encrypted  # noqa: E402
from uvalu import logkit  # noqa: E402

_BASE_DIR  = Path(__file__).parent / "data" / "portfolio"
_CACHE_DIR = Path(__file__).parent / ".cache"
_BASE_DIR.mkdir(parents=True, exist_ok=True)

# Active user, set at the top of every script run via set_user(). Streamlit
# serves every connected session from the same process, dispatching each
# session's reruns onto threads that share process memory -- a plain module
# global here would let one session's set_user() clobber another's mid-run,
# corrupting which user's encrypted directory a concurrent save/load lands
# in. threading.local() gives each executing thread its own private value;
# since app.py calls set_user() unconditionally at the start of every rerun,
# this is correct even if Streamlit reuses pooled threads across sessions.
_local = threading.local()


def set_user(email: str) -> None:
    _local.active_email = email.strip().lower()


def _user_dir(email: str = "") -> Path:
    e = (email or getattr(_local, "active_email", "")).strip().lower()
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
        # File exists but couldn't be decrypted/parsed — a silent None here
        # reads downstream as "no portfolio", so make the failure visible.
        logkit.get_logger("uvalu.portfolio").warning(
            "could not read %s", path.name, exc_info=True,
            extra={"event": "storage.read_failed", "file": path.name})
        return None


def save_portfolio(df: pd.DataFrame) -> None:  _save(df, _user_dir() / "portfolio.json")
def save_sold(df: pd.DataFrame) -> None:       _save(df, _user_dir() / "sold.json")
def save_div_hist(df: pd.DataFrame) -> None:   _save(df, _user_dir() / "dividends_history.json")
def load_portfolio() -> pd.DataFrame | None:   return _load(_user_dir() / "portfolio.json")
def load_sold() -> pd.DataFrame | None:        return _load(_user_dir() / "sold.json")
def portfolio_exists() -> bool:                return (_user_dir() / "portfolio.json").exists()


# Dividend-event fields added for the fuller Dividend Management surface
# (declaration/ex/record dates, per-share gross, special/one-off type,
# auto-vs-manual source). Records saved before this shipped only have the
# original `date` (payment date), `amount` (gross total), `shares`,
# `tax_rate`/`tax_amount` — every new field defaults so old rows never crash
# code that reads them. `ex_date` is nominally "required" going forward (the
# Add-dividend dialog enforces it), but a pre-existing record without one
# falls back to its payment date rather than being left blank.
_DIV_HIST_DEFAULTS: dict = {
    "declaration_date": None,
    "ex_date":          None,
    "record_date":      None,
    "amount_per_share": None,
    "div_type":         "Cash",   # "Cash" | "Stock" | "Special"
    "source":           "manual",  # "manual" | "auto" (fetched from market data, WP-DIV8)
}


def _migrate_div_hist(df: pd.DataFrame | None) -> pd.DataFrame | None:
    """Backfill the new dividend-event columns onto rows saved by an older
    version of this app — see _DIV_HIST_DEFAULTS. Never mutates values a
    record already has."""
    if df is None or df.empty:
        return df
    df = df.copy()
    for col, default in _DIV_HIST_DEFAULTS.items():
        if col not in df.columns:
            df[col] = default
    if "date" not in df.columns:
        df["date"] = None
    _ex_blank = df["ex_date"].isna() | (df["ex_date"].astype(str).str.strip().isin(["", "None", "NaT"]))
    df.loc[_ex_blank, "ex_date"] = df.loc[_ex_blank, "date"]
    if "shares" in df.columns and "amount" in df.columns:
        _aps = pd.to_numeric(df["amount_per_share"], errors="coerce")
        _shares = pd.to_numeric(df["shares"], errors="coerce")
        _amount = pd.to_numeric(df["amount"], errors="coerce")
        _derive = _aps.isna() & _shares.notna() & (_shares > 0) & _amount.notna()
        df.loc[_derive, "amount_per_share"] = (_amount[_derive] / _shares[_derive]).round(4)
    df["div_type"] = df["div_type"].fillna("Cash").replace("", "Cash")
    df["source"]   = df["source"].fillna("manual").replace("", "manual")
    return df


def load_div_hist() -> pd.DataFrame | None:
    return _migrate_div_hist(_load(_user_dir() / "dividends_history.json"))


# ── CRUD helpers ──────────────────────────────────────────────────────────────

def add_position(row: dict) -> None:
    """Append a new open position and persist."""
    df = load_portfolio()
    new_row = pd.DataFrame([row])
    df = pd.concat([df, new_row], ignore_index=True) if df is not None else new_row
    save_portfolio(df)
    logkit.data_mutation(actor=logkit.user_id(), action="position.add",
                         entity_type="ticker", entity_id=str(row.get("ticker") or ""),
                         shares=row.get("shares"))


def remove_positions(indices: list[int]) -> None:
    """Drop rows by integer index and persist."""
    df = load_portfolio()
    if df is None:
        return
    save_portfolio(df.drop(index=indices).reset_index(drop=True))
    logkit.data_mutation(actor=logkit.user_id(), action="position.remove",
                         entity_type="ticker", removed=len(indices))


def update_positions(df: pd.DataFrame) -> None:
    """Persist a fully-updated positions DataFrame."""
    save_portfolio(df)
    logkit.data_mutation(actor=logkit.user_id(), action="position.bulk_update",
                         entity_type="ticker", rows=(0 if df is None else len(df)))


def _annual_return_pct(purchase_value: float, proceeds: float, dividends: float,
                       date_in: str, date_out: str) -> float | None:
    """CAGR-style annualised return over the holding period, or None if the
    holding period or purchase value can't support the calculation."""
    try:
        _date_in   = pd.to_datetime(date_in,  errors="coerce")
        _date_out  = pd.to_datetime(date_out, errors="coerce")
        _held_days = (_date_out - _date_in).days
        if _held_days > 0 and purchase_value > 0:
            _total_value = proceeds + dividends
            return round(((_total_value / purchase_value) ** (365 / _held_days) - 1) * 100, 2)
        return None
    except Exception:
        return None


def sell_position(ticker: str, shares: int, proceeds: float, sell_date: str) -> None:
    """Move a position from portfolio to sold, persist both files."""
    pf = load_portfolio()
    if pf is None:
        return
    mask = pf["ticker"] == ticker
    if not mask.any():
        return
    row = pf[mask].iloc[0].copy()
    # `... or 0` doesn't catch NaN (bool(nan) is True in Python), so a
    # missing/NaN field here would silently persist NaN into the sold
    # record instead of falling back to 0 — use pd.notna instead.
    _pv = row.get("purchase_value")
    _dv = row.get("dividends")
    purchase_value = float(_pv) if pd.notna(_pv) else 0.0
    dividends      = float(_dv) if pd.notna(_dv) else 0.0
    annual_return_pct = _annual_return_pct(purchase_value, proceeds, dividends,
                                           row.get("date_in", ""), sell_date)
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
    logkit.data_mutation(actor=logkit.user_id(), action="position.sell",
                         entity_type="ticker", entity_id=ticker,
                         shares=shares, sell_date=sell_date)


def add_closed_trade(row: dict) -> None:
    """Append a directly-entered closed/realised trade — one that was opened
    and closed outside this app's normal Buy/Sell flow, so it never existed
    as an open position here. Matches Uvalu.dc.html's "Add/Edit closed trade"
    modal, which has no counterpart in sell_position() (that always moves an
    *existing* open position into sold.json)."""
    df = load_sold()
    new_row = pd.DataFrame([row])
    df = pd.concat([df, new_row], ignore_index=True) if df is not None else new_row
    save_sold(df)
    logkit.data_mutation(actor=logkit.user_id(), action="trade.add_closed",
                         entity_type="ticker", entity_id=str(row.get("ticker") or ""))


def add_dividend(row: dict) -> None:
    """Append a dividend record and update portfolio totals. If the record
    is marked reinvested (DRIP), also folds the reinvested shares/cash into
    the matching open position — see apply_drip_reinvestment()."""
    df = load_div_hist()
    new_row = pd.DataFrame([row])
    df = pd.concat([df, new_row], ignore_index=True) if df is not None else new_row
    save_div_hist(df)
    _sync_portfolio_dividends(df)
    if row.get("reinvested") and pd.notna(pd.to_numeric(row.get("reinvested_shares"), errors="coerce")):
        apply_drip_reinvestment(str(row.get("ticker") or ""),
                                float(row["reinvested_shares"]), float(row.get("amount") or 0))
    logkit.data_mutation(actor=logkit.user_id(), action="dividend.add",
                         entity_type="ticker", entity_id=str(row.get("ticker") or ""))


def update_div_hist(df: pd.DataFrame) -> None:
    """Persist updated dividend history and sync portfolio totals. Does NOT
    retroactively re-apply DRIP math for edited records — reinvestment is
    folded into the position once, at add_dividend() time; editing a past
    record's amount/shares afterwards only affects the history display and
    the (non-reinvested) cash totals it feeds."""
    save_div_hist(df)
    _sync_portfolio_dividends(df)
    logkit.data_mutation(actor=logkit.user_id(), action="dividend.bulk_update",
                         entity_type="ticker", rows=(0 if df is None else len(df)))


def _sync_portfolio_dividends(div_df: "pd.DataFrame") -> None:
    """Recompute portfolio.dividends (net cash received, open positions
    only) from div_hist totals per ticker.

    Uses dividends_in_eur()'s net_after_be_amount_eur — EUR-converted and
    net of both foreign withholding and the Belgian 30% roerende
    voorheffing (WP-DIV3) — rather than the raw native-currency `amount`
    this used to sum directly; that previously mixed non-EUR gross amounts
    (e.g. a Swiss CHF dividend) straight into `purchase_value`, which is
    always EUR.

    Two filters: dates in the future are excluded (a dividend recorded
    ahead of its payment date shouldn't count as "received" yet), and
    reinvested (DRIP) records are excluded (that cash never left the
    position — it's already reflected in the position's larger share count
    instead, via apply_drip_reinvestment())."""
    pf = load_portfolio()
    if pf is None:
        return
    eur = dividends_in_eur(div_df)
    div_dates = pd.to_datetime(eur.get("date"), errors="coerce")
    if "reinvested" in eur.columns:
        reinvested = eur["reinvested"].fillna(False).astype(bool)
    else:
        reinvested = pd.Series(False, index=eur.index)
    received = eur[(div_dates <= pd.Timestamp.now()) & (~reinvested)]
    totals = received.groupby("ticker")["net_after_be_amount_eur"].sum()
    pf["dividends"] = pf["ticker"].map(totals).fillna(pf["dividends"].fillna(0))
    save_portfolio(pf)


def apply_drip_reinvestment(ticker: str, shares_added: float, cash_reinvested: float) -> None:
    """Fold a DRIP (dividend reinvestment) into the matching open position:
    shares grow by `shares_added`, and `cash_reinvested` is added to the
    position's cost basis — the same accounting as any other additional
    purchase, so purchase_price (= purchase_value / shares) stays correctly
    blended. A no-op if the position isn't open (e.g. already sold)."""
    if not ticker or shares_added <= 0:
        return
    pf = load_portfolio()
    if pf is None:
        return
    mask = pf["ticker"] == ticker
    if not mask.any():
        return
    idx = pf[mask].index[0]
    pf.at[idx, "shares"] = float(_num_or(pf.at[idx, "shares"], 0)) + shares_added
    pf.at[idx, "purchase_value"] = float(_num_or(pf.at[idx, "purchase_value"], 0)) + cash_reinvested
    save_portfolio(pf)
    logkit.data_mutation(actor=logkit.user_id(), action="position.drip_reinvest",
                         entity_type="ticker", entity_id=ticker, shares_added=shares_added)


def _num_or(value, default):
    """pd.to_numeric-coerced value, or `default` if missing/unparseable/NaN
    (NaN is truthy in Python, so a bare `value or default` wouldn't catch
    it) — same helper uvalu/dialogs.py keeps its own copy of."""
    v = pd.to_numeric(value, errors="coerce")
    return v if pd.notna(v) else default


# Ticker-suffix -> (native currency, settings.py exchange key), for
# defaulting a dividend record's currency and its withholding-tax lookup.
# Same six exchanges as settings.ALL_EXCHANGES / uvalu/pages_/portfolio.py's
# _TICKER_SUFFIX_EXCHANGE; every listed exchange quotes in EUR except Swiss.
_EXCHANGE_SUFFIX = {
    ".BR": ("EUR", "brussels"), ".AS": ("EUR", "amsterdam"), ".PA": ("EUR", "paris"),
    ".MI": ("EUR", "milan"),    ".DE": ("EUR", "frankfurt"), ".SW": ("CHF", "swiss"),
}


def currency_for_ticker(ticker: str) -> str:
    for suffix, (ccy, _key) in _EXCHANGE_SUFFIX.items():
        if str(ticker).endswith(suffix):
            return ccy
    return "EUR"


def exchange_key_for_ticker(ticker: str) -> str | None:
    for suffix, (_ccy, key) in _EXCHANGE_SUFFIX.items():
        if str(ticker).endswith(suffix):
            return key
    return None


# Belgian "roerende voorheffing" — a fixed statutory rate on investment
# income, not a guess about a foreign treaty rate (unlike the per-exchange
# `dividend_withholding` table in settings.py, which stays 0%-by-default
# because the app has no way to know a user's actual treaty rate). Applied
# after any foreign withholding already deducted, on every Cash/Special
# dividend — not on Stock (scrip) dividends, where no cash changes hands to
# withhold from.
BE_WITHHOLDING_RATE = 0.30


def dividends_in_eur(div_df: "pd.DataFrame") -> "pd.DataFrame":
    """div_hist rows with `amount_eur`/`tax_amount_eur`/`net_amount_eur`
    (foreign-withholding-only net, kept for backward compat) plus
    `be_tax_amount(_eur)` and `net_after_be_amount(_eur)` (net of foreign
    withholding AND the Belgian 30% layer — the figure that should drive
    yield-on-cost/income reporting) — all converted from each row's native
    `currency` to EUR at its payment `date`, via marketdata.fx_to_eur_frame
    (the same historical-FX helper risk.py already uses to EUR-normalise
    price history). EUR rows convert at 1.0; a currency with no fetchable
    FX history falls back to its native amount unconverted."""
    import marketdata

    out = div_df.copy()
    if "tax_amount" not in out.columns:
        out["tax_amount"] = 0.0
    if "tax_rate" not in out.columns:
        out["tax_rate"] = 0.0
    if "currency" not in out.columns:
        out["currency"] = "EUR"
    if "div_type" not in out.columns:
        out["div_type"] = "Cash"
    out["amount"]     = pd.to_numeric(out["amount"], errors="coerce").fillna(0)
    out["tax_amount"] = pd.to_numeric(out["tax_amount"], errors="coerce").fillna(0)
    out["tax_rate"]   = pd.to_numeric(out["tax_rate"], errors="coerce").fillna(0)
    out["currency"]   = out["currency"].fillna("EUR").astype(str).str.upper()
    out["div_type"]   = out["div_type"].fillna("Cash").replace("", "Cash")
    out["net_amount"] = out["amount"] - out["tax_amount"]
    _be_eligible = out["div_type"] != "Stock"
    out["be_tax_amount"] = 0.0
    out.loc[_be_eligible, "be_tax_amount"] = (
        (out.loc[_be_eligible, "amount"] - out.loc[_be_eligible, "tax_amount"]).clip(lower=0)
        * BE_WITHHOLDING_RATE
    ).round(2)
    out["net_after_be_amount"] = out["amount"] - out["tax_amount"] - out["be_tax_amount"]
    dates = pd.to_datetime(out["date"], errors="coerce")

    foreign = sorted({c for c in out["currency"].unique() if c and c != "EUR"})
    fx = marketdata.fx_to_eur_frame(foreign) if foreign else pd.DataFrame()

    def _rate(ccy: str, dt) -> float:
        if ccy == "EUR" or fx.empty or ccy not in fx.columns or pd.isna(dt):
            return 1.0
        s = fx[ccy].reindex(fx.index.union([dt])).sort_index().ffill().bfill()
        r = s.get(dt)
        return float(r) if pd.notna(r) else 1.0

    rates = [
        _rate(ccy, dt) if ccy != "EUR" else 1.0
        for ccy, dt in zip(out["currency"], dates)
    ]
    out["_fx_rate"]              = rates
    out["amount_eur"]            = out["amount"] * out["_fx_rate"]
    out["tax_amount_eur"]        = out["tax_amount"] * out["_fx_rate"]
    out["net_amount_eur"]        = out["net_amount"] * out["_fx_rate"]
    out["be_tax_amount_eur"]     = out["be_tax_amount"] * out["_fx_rate"]
    out["net_after_be_amount_eur"] = out["net_after_be_amount"] * out["_fx_rate"]
    return out.drop(columns=["_fx_rate"])


def import_dividends_from_market_data(pf: "pd.DataFrame", email: str = "") -> int:
    """Pull each held ticker's per-share dividend-payment history from
    market data (marketdata.dividends — yfinance) and insert any ex-dates
    missing from the user's own ledger, marked source="auto".

    yfinance's dividend feed exposes ex-date + per-share amount only, never
    an actual payment date — so the payment `date` field is defaulted to
    the ex-date rather than guessed at a settlement lag, matching this
    app's existing "never guess a number and silently apply it" stance
    (see settings.py's dividend_withholding comment, same principle applied
    to dates instead of a tax rate). uvalu/pages_/portfolio.py's dividend
    log flags these rows "confirm" until the user edits the payment date.

    Returns the number of rows imported."""
    import marketdata
    from settings import get_dividend_withholding

    existing = load_div_hist()
    _existing_ex: set[tuple[str, "pd.Timestamp"]] = set()
    if existing is not None and not existing.empty:
        _ex_dates = pd.to_datetime(existing["ex_date"], errors="coerce").dt.normalize()
        _existing_ex = set(zip(existing["ticker"].astype(str), _ex_dates))

    new_rows: list[dict] = []
    for _, prow in pf.iterrows():
        ticker = str(prow.get("ticker") or "").strip()
        shares = _num_or(prow.get("shares"), 0)
        if not ticker or shares <= 0:
            continue
        try:
            divs = marketdata.dividends(ticker)
        except Exception:
            continue
        if divs is None or divs.empty:
            continue
        tax_rate = get_dividend_withholding(exchange_key_for_ticker(ticker), email)
        currency = currency_for_ticker(ticker)
        for ex_ts, ps in divs.items():
            ex_norm = pd.Timestamp(ex_ts).normalize()
            if (ticker, ex_norm) in _existing_ex:
                continue
            ps = float(ps)
            if ps <= 0:
                continue
            gross = round(ps * float(shares), 2)
            new_rows.append({
                "name": prow.get("name", ticker), "google_ticker": prow.get("google_ticker", ""),
                "ticker": ticker, "shares": int(shares), "amount": gross,
                "amount_per_share": round(ps, 4), "currency": currency,
                "tax_rate": round(tax_rate, 2), "tax_amount": round(gross * tax_rate / 100, 2),
                "div_type": "Cash", "source": "auto",
                "declaration_date": None, "ex_date": pd.Timestamp(ex_ts).isoformat(),
                "record_date": None, "date": pd.Timestamp(ex_ts).isoformat(),
                "reinvested": False, "reinvested_shares": None,
            })
            _existing_ex.add((ticker, ex_norm))

    if not new_rows:
        return 0
    new_df = pd.DataFrame(new_rows)
    df = pd.concat([existing, new_df], ignore_index=True) if existing is not None and not existing.empty else new_df
    save_div_hist(df)
    _sync_portfolio_dividends(df)
    logkit.data_mutation(actor=logkit.user_id(), action="dividend.import_auto",
                         entity_type="ticker", rows=len(new_rows))
    return len(new_rows)


def dividend_income_summary(div_df: "pd.DataFrame | None", *, months: int = 12) -> "pd.DataFrame":
    """Per-ticker trailing-`months` dividend income, from dividends_in_eur()
    output, for events already paid (payment date in [now-months, now]).

    Columns: gross_eur, foreign_tax_eur, be_tax_eur, net_eur (net of both
    foreign withholding and the Belgian 30% layer — the figure yield-on-cost
    and income roll-ups should read), and regular_gross_eur (gross excluding
    Special/one-off events — the basis trailing yield uses, so a special
    dividend doesn't distort it). Empty (zero rows, same columns) for no
    history or nothing in the window."""
    _cols = ["gross_eur", "foreign_tax_eur", "be_tax_eur", "net_eur", "regular_gross_eur"]
    if div_df is None or div_df.empty:
        return pd.DataFrame(columns=_cols)
    out = dividends_in_eur(div_df)
    dates = pd.to_datetime(out["date"], errors="coerce")
    now = pd.Timestamp.now()
    cutoff = now - pd.DateOffset(months=months)
    win = out[(dates <= now) & (dates > cutoff)].copy()
    if win.empty:
        return pd.DataFrame(columns=_cols)
    win["_regular_gross"] = win["amount_eur"].where(win["div_type"] != "Special", 0.0)
    g = win.groupby("ticker").agg(
        gross_eur=("amount_eur", "sum"),
        foreign_tax_eur=("tax_amount_eur", "sum"),
        be_tax_eur=("be_tax_amount_eur", "sum"),
        net_eur=("net_after_be_amount_eur", "sum"),
        regular_gross_eur=("_regular_gross", "sum"),
    )
    return g


def save_cash(df: pd.DataFrame) -> None:
    _save(df, _user_dir() / "cash.json")
    # Rows only — never the balances (money amounts stay out of the log).
    logkit.data_mutation(actor=logkit.user_id(), action="cash.update",
                         entity_type="cash", rows=(0 if df is None else len(df)))


def load_cash() -> pd.DataFrame | None:    return _load(_user_dir() / "cash.json")


# ── Per-holding dividend profile ─────────────────────────────────────────────
# Small ticker-keyed store for the two things that are properties of a
# *holding*, not of any one dividend event: the payment frequency (only
# overridden here once a user sets it explicitly — otherwise callers fall
# back to screener._next_expected_ex_div's market-data-derived guess, so
# this file never "assumes" a frequency the requirements doc asked not to)
# and the DRIP default (pre-fills the Add-dividend dialog's reinvested
# checkbox for that ticker; the checkbox itself still decides each event).
# Shape: {ticker: {"frequency": str | None, "drip_default": bool}}.

def save_dividend_meta(meta: dict) -> None:
    _prev = load_dividend_meta()
    _save_user_json("dividend_meta.json", meta)
    _changed = sorted(t for t in set(meta) | set(_prev) if meta.get(t) != _prev.get(t))
    if _changed:
        logkit.data_mutation(actor=logkit.user_id(), action="dividend_meta.update",
                             entity_type="ticker", tickers=_changed)


def load_dividend_meta() -> dict:
    m = _load_user_json("dividend_meta.json", {})
    return m if isinstance(m, dict) else {}


def set_dividend_meta(ticker: str, *, frequency: str | None = None, drip_default: bool | None = None) -> None:
    """Upsert one ticker's entry, leaving unspecified fields as they were."""
    if not ticker:
        return
    meta = load_dividend_meta()
    entry = dict(meta.get(ticker) or {})
    if frequency is not None:
        entry["frequency"] = frequency or None
    if drip_default is not None:
        entry["drip_default"] = bool(drip_default)
    meta[ticker] = entry
    save_dividend_meta(meta)


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
    with logkit.external_call("yfinance.download.backfill", logger="uvalu.portfolio",
                              params={"tickers": len(fetch_tickers)}) as _call:
        raw = yf.download(
            fetch_tickers,
            start=earliest.strftime("%Y-%m-%d"),
            end=(latest + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
            auto_adjust=True,
            progress=False,
        )
        if raw.empty:
            _call.note(status="empty")

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


# One in-flight backfill per user at a time — keyed by email so two users
# (or two tabs of the same user) never race, and so either page (Portfolio or
# Dashboard, whichever the user visits first) can trigger and poll the same
# run instead of each kicking off its own.
_backfill_state: dict[str, bool] = {}
_backfill_lock = threading.Lock()


def ensure_value_history_fresh(open_df: pd.DataFrame, sold_df: "pd.DataFrame | None", email: str) -> bool:
    """Non-blocking replacement for calling backfill_value_history() directly
    on the render path. Kicks it off in a background thread when this user's
    value_history.json is missing/stale and no backfill is already running for
    them; otherwise a no-op. Returns True while a backfill is in flight for
    this user, so a caller with somewhere to show progress (Dashboard's value
    chart) can render a skeleton and poll instead of the page just blocking.
    """
    with _backfill_lock:
        if _backfill_state.get(email):
            return True
        vh = load_value_history()
        yesterday = (pd.Timestamp.today() - pd.Timedelta(days=1)).normalize()
        last_date = (
            pd.to_datetime(vh["date"]).max()
            if vh is not None and not vh.empty
            else pd.Timestamp("1970-01-01")
        )
        needs_backfill = last_date < yesterday or vh is None or len(vh) <= 1
        if not needs_backfill:
            return False
        _backfill_state[email] = True

    def _run() -> None:
        try:
            # set_user() is required here: _user_dir() resolves the active
            # user from this thread's OWN threading.local() storage, which
            # starts unset on a freshly spawned thread — without this the
            # backfill would silently write into the anonymous default/
            # bucket instead of this user's directory (same bug class as the
            # dialog-fragment issue enter_dialog() fixes in uvalu/ui.py).
            set_user(email)
            with logkit.job("value_history_backfill", reraise=False,
                            trigger="stale_history") as _j:
                _rows = backfill_value_history(open_df, sold_df)
                _j.note(rows_written=_rows)
        finally:
            with _backfill_lock:
                _backfill_state[email] = False

    logkit.spawn(_run, name="value_history_backfill")
    return True


def _save_user_json(filename: str, data) -> None:
    write_encrypted(_user_dir() / filename, json.dumps(data, indent=2))


def _load_user_json(filename: str, default):
    path = _user_dir() / filename
    if not path.exists():
        return default
    try:
        return json.loads(read_encrypted(path))
    except Exception:
        return default


def save_watchlist(tickers: set[str]) -> None:
    _prev = load_watchlist()
    _save_user_json("watchlist.json", sorted(tickers))
    _added, _removed = sorted(set(tickers) - _prev), sorted(_prev - set(tickers))
    if _added or _removed:
        logkit.data_mutation(actor=logkit.user_id(), action="watchlist.update",
                             entity_type="watchlist", added=_added, removed=_removed)


def load_watchlist() -> set[str]:
    return set(_load_user_json("watchlist.json", []))


def save_manual_tickers(tickers: dict[str, str]) -> None:
    _prev = set(load_manual_tickers())
    _save_user_json("manual_tickers.json", tickers)
    _added, _removed = sorted(set(tickers) - _prev), sorted(_prev - set(tickers))
    if _added or _removed:
        logkit.data_mutation(actor=logkit.user_id(), action="manual_tickers.update",
                             entity_type="manual_tickers", added=_added, removed=_removed)


def load_manual_tickers() -> dict[str, str]:
    return _load_user_json("manual_tickers.json", {})


# ── Target allocation + risk snapshot (feeds risk Stage 8's drift triggers) ───

def _clean_weight_map(raw) -> dict[str, float]:
    out: dict[str, float] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            if 0.0 < f <= 1.0:
                out[str(k)] = round(f, 4)
    return out


def save_targets(targets: dict) -> None:
    """Persist the user's target allocation. Shape (all keys optional):
    {"sectors": {name: fraction}, "tickers": {ticker: fraction}, "hhi_max": fraction}
    """
    targets = targets or {}
    clean: dict = {}
    if targets.get("sectors"):
        clean["sectors"] = _clean_weight_map(targets["sectors"])
    if targets.get("tickers"):
        clean["tickers"] = _clean_weight_map(targets["tickers"])
    try:
        hhi_max = float(targets.get("hhi_max"))
        if 0.0 < hhi_max <= 1.0:
            clean["hhi_max"] = round(hhi_max, 4)
    except (TypeError, ValueError):
        pass
    _save_user_json("targets.json", clean)
    logkit.data_mutation(actor=logkit.user_id(), action="targets.update",
                         entity_type="targets",
                         sectors=len(clean.get("sectors", {})),
                         tickers=len(clean.get("tickers", {})),
                         has_hhi_max=("hhi_max" in clean))


def load_targets() -> dict:
    t = _load_user_json("targets.json", {})
    return t if isinstance(t, dict) else {}


def save_risk_snapshot(snapshot: dict) -> None:
    """Upsert a small snapshot of the current risk picture, one per calendar
    day — the reference point Stage 8 diffs against for drift triggers."""
    import datetime
    snap = dict(snapshot or {})
    snap.setdefault("date", datetime.date.today().isoformat())
    _save_user_json("risk_snapshot.json", snap)


def load_risk_snapshot() -> dict:
    s = _load_user_json("risk_snapshot.json", {})
    return s if isinstance(s, dict) else {}


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
