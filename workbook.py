"""
Workbooks — the portfolio export/import and the full copy of a user's data.

Two exports share one format:
  - **Portfolio workbook** (Settings › Import & export): Positions, Sold,
    Dividends, Cash and Watchlist — only what the user entered, ready to re-import
    (docs/import-export-plan.md). Derived values (purchase price, dividend
    totals, annual return, tax amounts) and internal ids are left out and
    rebuilt on import.
  - **All my data** (Settings › Privacy › Export my data): the same four
    sheets plus Account (the account record, never a secret), Settings (every
    setting, one row each: section · setting · value) and Automatic cash (the
    cash entries Uvalu posted for trades and dividends).

Column headers are fixed English keys, so a file exported in one language
imports in another; sheet names are translated, so import recognises a sheet
by its headers, never by its name. A hidden ``_meta`` sheet records the file
format version. Import reads the portfolio sheets and skips the rest.

Import has two modes (IE2):
  - ``replace``: restore. A backup is saved, the account's portfolio data
    (positions, sales, dividends, cash, watchlist) is deleted, then the file
    is loaded. Settings are left as they are.
  - ``add``: bulk import. Rows are appended; rows that match an existing one
    are skipped.
Every imported trade posts its cash (Buy/Sell with automatic top-ups), like a
trade entered by hand; dividend cash follows from the dividend log.

No Streamlit import — unit-tested in tests/test_workbook.py.
"""
from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

import pandas as pd

import portfolio
from uvalu.i18n import _, pgettext

FORMAT = "uvalu-workbook"
FORMAT_VERSION = 1
META_SHEET = "_meta"

DIV_TYPES = ("Cash", "Stock", "Special")

# Sheet key → columns, in export order. Required columns are checked on import.
COLUMNS: dict[str, tuple[str, ...]] = {
    "positions":   ("name", "ticker", "shares", "purchase_value", "fee", "date_in"),
    "sold":        ("name", "ticker", "shares", "purchase_value", "sale_value", "fee", "sector",
                    "date_in", "date_out"),
    "dividends":   ("name", "ticker", "shares", "amount", "currency", "tax_rate", "div_type",
                    "ex_date", "date"),
    "cash":        ("date", "type", "amount", "currency", "fx_rate", "note"),
    "watchlist":   ("ticker", "name"),
    # Only in "All my data" (privacy copy); import recognises and skips them.
    "account":     ("field", "value"),
    "settings":    ("section", "setting", "value"),
    "ledger":      ("date", "type", "amount", "currency", "fx_rate", "amount_eur", "linked_to", "note"),
}
PORTFOLIO_SHEETS = ("positions", "sold", "dividends", "cash", "watchlist")
ALL_SHEETS = ("account", "settings", "positions", "sold", "dividends", "cash", "watchlist", "ledger")
INFO_SHEETS = ("account", "settings", "ledger")
SHEET_ORDER = PORTFOLIO_SHEETS

_DATE_COLS = {"date_in", "date_out", "ex_date", "date"}
_MONEY_COLS = {"purchase_value", "sale_value", "fee", "amount", "amount_eur"}


def sheet_names() -> dict[str, str]:
    """Translated worksheet tab names."""
    # Translators: Settings › Export: worksheet tab names in the downloaded
    # workbook. Excel allows at most 31 characters and none of : \ / ? * [ ]
    return {
        "positions":   pgettext("sheet_name", "Positions"),
        "sold":        pgettext("sheet_name", "Sold"),
        "dividends":   pgettext("sheet_name", "Dividends"),
        "cash":        pgettext("sheet_name", "Cash"),
        "watchlist":   pgettext("sheet_name", "Watchlist"),
        "account":     pgettext("sheet_name", "Account"),
        "settings":    pgettext("sheet_name", "Settings"),
        "ledger":      pgettext("sheet_name", "Automatic cash"),
    }


def column_notes() -> dict[str, str]:
    """Header comments: what each column holds and which ones are required."""
    return {
        "name":           _("Company name. Optional: the ticker is shown when empty."),
        "ticker":         _("Yahoo Finance ticker, e.g. ABI.BR, ASML.AS, ROG.SW. Required."),
        "shares":         _("Number of shares. Required."),
        "purchase_value": _("Total cost in euro, without fees. Required."),
        "sale_value":     _("Total proceeds in euro, without fees. Required."),
        "fee":            _("Broker fee in euro. Optional."),
        "sector":         _("Sector. Optional."),
        "date_in":        _("Buy date. Required."),
        "date_out":       _("Sale date. Required."),
        "amount":         _("Gross dividend for all shares, in the dividend currency. Required."),
        "currency":       _("Three-letter currency code, e.g. EUR or CHF. Empty: the exchange's currency."),
        "tax_rate":       _("Foreign withholding tax in %. Optional; Belgian withholding is added automatically."),
        "div_type":       _("Cash, Stock or Special. Empty: Cash."),
        "ex_date":        _("Ex-dividend date. Empty: the payment date."),
        "date":           _("Date. Required (for a dividend: the payment date)."),
        "type":           _("Deposit, Withdrawal, Fee, Interest or Adjustment. Required."),
        "fx_rate":        _("Rate to euro for another currency. Empty: the ECB rate of that day."),
        "note":           _("Description. Optional."),
        "field":          _("Account detail. For your information: not imported."),
        "section":        _("Settings section. For your information: not imported."),
        "setting":        _("Setting. For your information: not imported."),
        "value":          _("Value. For your information: not imported."),
        "amount_eur":     _("Amount in euro."),
        "linked_to":      _("The trade or dividend this entry belongs to. Rebuilt on import, not imported."),
    }


# ── Export ────────────────────────────────────────────────────────────────────

def _blank(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    if v is pd.NaT:
        return True
    return isinstance(v, str) and v.strip() in ("", "None", "nan", "NaT")


def _cell(v):
    return None if _blank(v) else v


def _xl_date(v):
    if _blank(v):
        return None
    ts = pd.to_datetime(v, errors="coerce", format="ISO8601")
    return None if pd.isna(ts) else ts.to_pydatetime().replace(tzinfo=None)


def _xl_num(v):
    n = pd.to_numeric(v, errors="coerce")
    if pd.isna(n):
        return None
    n = float(n)
    return int(n) if n.is_integer() else n


def _records(df: "pd.DataFrame | None") -> list[dict]:
    return [] if df is None or df.empty else df.to_dict("records")


def collect(email: str, *, full: bool = False) -> dict[str, list[dict]]:
    """Export rows per sheet key: the portfolio sheets, and with ``full`` the
    rest of the user's data too."""
    import cash
    from settings import load_settings

    out: dict[str, list[dict]] = {k: [] for k in ALL_SHEETS}
    for r in _records(portfolio.load_portfolio()):
        out["positions"].append({
            "name": _cell(r.get("name")), "ticker": _cell(r.get("ticker")),
            "shares": _xl_num(r.get("shares")), "purchase_value": _xl_num(r.get("purchase_value")),
            "fee": _xl_num(r.get("fee")) or None, "date_in": _xl_date(r.get("date_in")),
        })
    for r in _records(portfolio.load_sold()):
        out["sold"].append({
            "name": _cell(r.get("name")), "ticker": _cell(r.get("ticker")),
            "shares": _xl_num(r.get("shares")), "purchase_value": _xl_num(r.get("purchase_value")),
            "sale_value": _xl_num(r.get("sale_value")), "fee": _xl_num(r.get("fee")) or None,
            "sector": _cell(r.get("sector")),
            "date_in": _xl_date(r.get("date_in")), "date_out": _xl_date(r.get("date_out")),
        })
    for r in _records(portfolio.load_div_hist()):
        ticker = _cell(r.get("ticker"))
        out["dividends"].append({
            "name": _cell(r.get("name")), "ticker": ticker, "shares": _xl_num(r.get("shares")),
            "amount": _xl_num(r.get("amount")),
            "currency": _cell(r.get("currency")) or portfolio.currency_for_ticker(ticker or ""),
            "tax_rate": _xl_num(r.get("tax_rate")), "div_type": _cell(r.get("div_type")) or "Cash",
            "ex_date": _xl_date(r.get("ex_date")), "date": _xl_date(r.get("date")),
        })
    base = portfolio.base_currency()
    _default_notes = {"Opening balance", "Manual balance correction", *cash.MANUAL_TYPES}
    for e in cash.manual_entries():
        adj = e.get("type") == "Adjustment"
        ccy = str(e.get("currency") or base).upper()
        note = str(e.get("note") or "")
        out["cash"].append({
            "date": _xl_date(e.get("date")), "type": e.get("type"),
            "amount": _xl_num(e.get("target_balance") if adj else abs(float(e.get("amount") or 0.0))),
            "currency": ccy,
            "fx_rate": None if adj or ccy == base else _xl_num(e.get("fx_rate")),
            "note": None if note in _default_notes else note,
        })
    custom = portfolio.load_manual_tickers()
    out["watchlist"] = [{"ticker": t, "name": custom.get(t)} for t in sorted(portfolio.load_watchlist())]
    if not full:
        return out
    out["account"] = _account_rows(email)
    out["settings"] = _settings_rows(load_settings(email))
    for e in cash.load_ledger():
        if not (e.get("ref_kind") or e.get("auto")):
            continue
        out["ledger"].append({
            "date": _xl_date(e.get("date")), "type": e.get("type"), "amount": _xl_num(e.get("amount")),
            "currency": e.get("currency"), "fx_rate": _xl_num(e.get("fx_rate")),
            "amount_eur": _xl_num(e.get("amount_base")), "linked_to": e.get("ref_label"),
            "note": cash.note_text(e),
        })
    return out


def _text_value(v) -> str:
    if v is None or v == "":
        return "—"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (list, tuple, set)):
        return ", ".join(str(x) for x in v) or "—"
    if isinstance(v, dict):
        return ", ".join(f"{k}: {x}" for k, x in v.items()) or "—"
    return str(v)


def _account_rows(email: str) -> list[dict]:
    """What the account record holds about the user — never a secret (no
    password hash, codes, tokens or authenticator key)."""
    import auth

    user = auth._load_users().get((email or "").strip().lower()) or {}
    rows = [("email", email), ("role", user.get("role")), ("status", user.get("status")),
            ("created_at", user.get("created_at")), ("invited_by", user.get("invited_by")),
            ("last_active", user.get("last_active")), ("password_changed_at", user.get("password_changed_at")),
            ("two_step_verification", bool(user.get("totp_enabled"))),
            ("trusted_devices", len(user.get("trusted_devices") or [])),
            ("linked_sign_in", [i.get("provider") for i in (user.get("linked_identities") or [])
                                if isinstance(i, dict)])]
    for sess in user.get("sessions") or []:
        if isinstance(sess, dict):
            parts = (sess.get("created_at"), sess.get("user_agent"), "revoked" if sess.get("revoked") else "active")
            rows.append(("session", " · ".join(str(x) for x in parts if x)))
    return [{"field": k, "value": _text_value(v)} for k, v in rows]


def _pct(v) -> str:
    try:
        return f"{float(v) * 100:g}%"
    except (TypeError, ValueError):
        return _text_value(v)


def _settings_rows(user_settings: dict) -> list[dict]:
    """Every setting of the user, one row each, grouped by the Settings
    section it lives in: section · setting · value."""

    not_set = _("Not set (default)")

    def val(v):
        return not_set if v is None or v == "" else _text_value(v)

    rows: list[tuple[str, str, str]] = []
    lr = _("Language & region")
    for key, label in (("language", _("Language")), ("region", _("Region format")),
                       ("display_currency", _("Display currency")), ("date_format", _("Date format")),
                       ("time_zone", _("Time zone")), ("week_start", _("First day of week"))):
        rows.append((lr, label, val(user_settings.get(key))))
    rows.append((_("Display"), _("Table density"), val(user_settings.get("density"))))
    from uvalu import withholding
    own = user_settings.get(withholding.SETTING_KEY) or {}
    for country in withholding.countries():     # by country of the company (D13)
        rows.append((_("Dividend withholding"), withholding.country_name(country),
                     f"{withholding.rate_for(country, own):g}%"))
    targets = portfolio.load_targets()
    ta = _("Target allocation")
    for name, w in sorted((targets.get("sectors") or {}).items()):
        rows.append((ta, _("Sector · {name}", name=name), _pct(w)))
    for ticker, w in sorted((targets.get("tickers") or {}).items()):
        rows.append((ta, _("Ticker · {ticker}", ticker=ticker), _pct(w)))
    rows.append((ta, _("Concentration ceiling (HHI)"),
                 _pct(targets["hhi_max"]) if targets.get("hhi_max") else not_set))
    dv = _("Dividends")
    for ticker, meta in sorted(portfolio.load_dividend_meta().items()):
        if not isinstance(meta, dict):
            continue
        if meta.get("frequency"):
            rows.append((dv, _("Payment frequency · {ticker}", ticker=ticker), str(meta["frequency"])))
        if meta.get("dismissed_auto_ex"):
            rows.append((dv, _("Dismissed automatic dividends · {ticker}", ticker=ticker),
                         _text_value(meta["dismissed_auto_ex"])))
    rows.append((_("Portfolio"), _("Base currency"), portfolio.base_currency()))
    rows.append((_("Notices"), _("Last “What’s new” seen"), val(user_settings.get("last_seen_version"))))
    return [{"section": a, "setting": b, "value": c} for a, b, c in rows]


_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _write(rows: dict[str, list[dict]], keys: tuple[str, ...]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    from uvalu import buildinfo

    names = sheet_names()
    notes = column_notes()
    wb = Workbook()
    wb.remove(wb.active)
    for key in keys:
        ws = wb.create_sheet(names[key])
        cols = COLUMNS[key]
        ws.append(list(cols))
        for i, col in enumerate(cols, start=1):
            c = ws.cell(row=1, column=i)
            c.font = Font(bold=True)
            c.comment = Comment(notes[col], "Uvalu", width=260, height=90)
        for r in rows.get(key, []):
            ws.append([r.get(c) for c in cols])
            # SR7: openpyxl stores a string starting with "=" as a formula.
            # Text starting with a formula character (a note, a ticker typed
            # as "=HYPERLINK(...)") is written as plain text, so opening the
            # export can't run it; the value itself is unchanged for re-import.
            for cell in ws[ws.max_row]:
                if isinstance(cell.value, str) and cell.value[:1] in _FORMULA_START:
                    cell.data_type = "s"
        ws.freeze_panes = "A2"
        for i, col in enumerate(cols, start=1):
            letter = get_column_letter(i)
            width = len(col)
            for (cell,) in ws.iter_rows(min_row=2, min_col=i, max_col=i):
                if col in _DATE_COLS and cell.value is not None:
                    cell.number_format = "yyyy-mm-dd"
                    width = max(width, 10)
                elif col in _MONEY_COLS and isinstance(cell.value, (int, float)):
                    cell.number_format = "0.00"
                    width = max(width, len(f"{cell.value:.2f}"))
                elif cell.value is not None:
                    width = max(width, len(str(cell.value)))
            ws.column_dimensions[letter].width = min(width + 2, 48)
    meta = wb.create_sheet(META_SHEET)
    info = buildinfo.current()
    for k, v in (("format", FORMAT), ("format_version", FORMAT_VERSION),
                 ("app_version", info.display_version),
                 ("exported_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))):
        meta.append([k, v])
    meta.sheet_state = "hidden"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_workbook(email: str) -> bytes:
    """The portfolio workbook (Positions, Sold, Dividends, Cash). It doubles
    as the template for a bulk import: an empty account gets the headers
    only, and rows added to a full export import in Add mode without the
    existing ones being duplicated."""
    return _write(collect(email), PORTFOLIO_SHEETS)


def export_all(email: str) -> bytes:
    """Everything Uvalu holds about the user (Settings › Privacy › Export my
    data): account, settings, the portfolio sheets, automatic cash entries
    and the watchlist."""
    return _write(collect(email, full=True), ALL_SHEETS)


# ── Import: parsing and validation ────────────────────────────────────────────

@dataclass
class Issue:
    sheet: str      # sheet key
    row: int        # Excel row number (1 = header)
    message: str


@dataclass
class ParsedWorkbook:
    positions: list[dict] = field(default_factory=list)
    sold: list[dict] = field(default_factory=list)
    dividends: list[dict] = field(default_factory=list)
    cash: list[dict] = field(default_factory=list)
    watchlist: dict[str, str] = field(default_factory=dict)   # ticker → name ("" = none given)
    sheets: list[str] = field(default_factory=list)   # sheet keys found, in file order
    issues: list[Issue] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def counts(self) -> dict[str, int]:
        return {"positions": len(self.positions), "sold": len(self.sold),
                "dividends": len(self.dividends), "cash": len(self.cash), "watchlist": len(self.watchlist)}

    @property
    def empty(self) -> bool:
        return not any(self.counts().values())


def _norm_header(h) -> str:
    return re.sub(r"\s+", "_", str(h or "").strip().lower())


def _identify(headers: set[str]) -> str | None:
    """Sheet key from its headers. Also reads exports made before format 1
    (extra columns are ignored, the old watchlist header was "Ticker")."""
    if headers == {"field", "value"}:
        return "account"
    if {"setting", "value"} <= headers:
        return "settings"
    if "linked_to" in headers:
        return "ledger"
    if "ticker" in headers and "sale_value" in headers:
        return "sold"
    if "ticker" in headers and "purchase_value" in headers:
        return "positions"
    if "ticker" in headers and ({"amount", "amount_per_share"} & headers):
        return "dividends"
    if "type" in headers and "amount" in headers:
        return "cash"
    if "ticker" in headers and headers <= {"ticker", "name"}:
        return "watchlist"
    return None


def _num(v) -> float | None:
    """A number from a cell: Excel numbers, or text with a decimal comma or
    point and thousands separators ("1.974,36", "1,974.36", "1974,36")."""
    if _blank(v):
        return None
    if isinstance(v, bool):
        raise ValueError
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(" ", "").replace(" ", "").replace(" ", "").replace("%", "")
    s = s.replace("€", "").replace("'", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    return float(s)


def _date(v) -> date | None:
    if _blank(v):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        ts = pd.to_datetime(s, errors="coerce", format="ISO8601")
    else:
        ts = pd.to_datetime(s, errors="coerce", dayfirst=True)
    if pd.isna(ts):
        raise ValueError
    return ts.date()


def _text(v) -> str:
    return "" if _blank(v) else str(v).strip()


class _Row:
    """One data row with per-column parsing that records issues."""

    def __init__(self, sheet: str, rownum: int, values: dict, issues: list[Issue]):
        self.sheet, self.rownum, self.values, self.issues = sheet, rownum, values, issues
        self.ok = True

    def _issue(self, msg: str) -> None:
        self.ok = False
        self.issues.append(Issue(self.sheet, self.rownum, msg))

    def text(self, col: str, required: bool = False) -> str:
        s = _text(self.values.get(col))
        if required and not s:
            self._issue(_("{column} is empty.", column=col))
        return s

    def ticker(self, col: str = "ticker") -> str:
        s = self.text(col, required=True).upper()
        if s and not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-^=]*", s):
            self._issue(_("{value} is not a ticker.", value=s))
        return s

    def number(self, col: str, *, required: bool = False, positive: bool = False,
               min_value: float | None = None, max_value: float | None = None) -> float | None:
        raw = self.values.get(col)
        try:
            n = _num(raw)
        except (TypeError, ValueError):
            self._issue(_("{column}: {value} is not a number.", column=col, value=_text(raw)))
            return None
        if n is None:
            if required:
                self._issue(_("{column} is empty.", column=col))
            return None
        if math.isnan(n) or math.isinf(n):
            self._issue(_("{column}: {value} is not a number.", column=col, value=_text(raw)))
            return None
        if positive and n <= 0:
            self._issue(_("{column} must be greater than zero.", column=col))
        elif min_value is not None and n < min_value:
            self._issue(_("{column} must be at least {minimum}.", column=col, minimum=f"{min_value:g}"))
        elif max_value is not None and n > max_value:
            self._issue(_("{column} must be at most {maximum}.", column=col, maximum=f"{max_value:g}"))
        return n

    def day(self, col: str, required: bool = False) -> date | None:
        raw = self.values.get(col)
        try:
            d = _date(raw)
        except (TypeError, ValueError):
            self._issue(_("{column}: {value} is not a date.", column=col, value=_text(raw)))
            return None
        if d is None and required:
            self._issue(_("{column} is empty.", column=col))
        return d

    def choice(self, col: str, options: tuple[str, ...], default: str | None = None) -> str | None:
        s = self.text(col)
        if not s:
            if default is None:
                self._issue(_("{column} is empty.", column=col))
            return default
        match = next((o for o in options if o.lower() == s.lower()), None)
        if match is None:
            self._issue(_("{column}: {value} is not one of {options}.", column=col, value=s,
                          options=", ".join(options)))
        return match


def _shares(n: float | None):
    if n is None:
        return None
    return int(n) if float(n).is_integer() else round(float(n), 6)


def _parse_rows(key: str, rows: list[tuple[int, dict]], wb: ParsedWorkbook) -> None:
    import cash

    today = date.today()
    for rownum, values in rows:
        r = _Row(key, rownum, values, wb.issues)
        if key in ("positions", "sold"):
            rec = {"name": r.text("name"), "ticker": r.ticker(),
                   "shares": _shares(r.number("shares", required=True, positive=True)),
                   "purchase_value": r.number("purchase_value", required=True, positive=True),
                   "fee": r.number("fee", min_value=0) or 0.0,
                   "date_in": r.day("date_in", required=True)}
            if rec["date_in"] and rec["date_in"] > today:
                r._issue(_("{column} is in the future.", column="date_in"))
            if key == "sold":
                rec["sale_value"] = r.number("sale_value", required=True, min_value=0)
                rec["sector"] = r.text("sector")
                rec["date_out"] = r.day("date_out", required=True)
                if rec["date_in"] and rec["date_out"] and rec["date_out"] < rec["date_in"]:
                    r._issue(_("date_out is before date_in."))
                if rec["date_out"] and rec["date_out"] > today:
                    r._issue(_("{column} is in the future.", column="date_out"))
            if r.ok:
                (wb.sold if key == "sold" else wb.positions).append(rec)
        elif key == "dividends":
            ticker = r.ticker()
            shares = r.number("shares", min_value=0)
            amount = r.number("amount", positive=True) if "amount" in values and not _blank(values.get("amount")) else None
            per_share = r.number("amount_per_share", positive=True) if amount is None else None
            if amount is None and per_share is None and r.ok:
                r._issue(_("{column} is empty.", column="amount"))
            elif amount is None and per_share is not None:
                if not shares:
                    r._issue(_("shares is needed to compute the amount from amount_per_share."))
                else:
                    amount = round(per_share * shares, 2)
            ccy = r.text("currency").upper() or (portfolio.currency_for_ticker(ticker) if ticker else "EUR")
            if not re.fullmatch(r"[A-Z]{3}", ccy):
                r._issue(_("{column}: {value} is not a currency code.", column="currency", value=ccy))
            pay = r.day("date", required=True)
            ex = r.day("ex_date") or pay
            if ex and pay and ex > pay:
                r._issue(_("ex_date is after the payment date."))
            rec = {"name": r.text("name"), "ticker": ticker, "shares": _shares(shares) or 0,
                   "amount": amount, "currency": ccy,
                   "tax_rate": r.number("tax_rate", min_value=0, max_value=100) or 0.0,
                   "div_type": r.choice("div_type", DIV_TYPES, default="Cash"),
                   "ex_date": ex, "date": pay}
            if r.ok:
                wb.dividends.append(rec)
        elif key == "cash":
            type_ = r.choice("type", cash.MANUAL_TYPES)
            amount = r.number("amount", required=True, min_value=0)
            if type_ and type_ != "Adjustment" and amount is not None and amount <= 0:
                r._issue(_("{column} must be greater than zero.", column="amount"))
            ccy = r.text("currency").upper()
            if ccy and not re.fullmatch(r"[A-Z]{3}", ccy):
                r._issue(_("{column}: {value} is not a currency code.", column="currency", value=ccy))
            rec = {"date": r.day("date", required=True), "type": type_, "amount": amount,
                   "currency": ccy or None, "fx_rate": r.number("fx_rate", positive=True),
                   "note": r.text("note")}
            if type_ == "Adjustment" and ccy and ccy != portfolio.base_currency():
                r._issue(_("An Adjustment is always in {currency}.", currency=portfolio.base_currency()))
            if rec["date"] and rec["date"] > today:
                r._issue(_("{column} is in the future.", column="date"))
            if r.ok:
                wb.cash.append(rec)
        elif key == "watchlist":
            t = r.ticker()
            if r.ok:
                wb.watchlist[t] = r.text("name") or wb.watchlist.get(t, "")


def parse_workbook(data: bytes) -> ParsedWorkbook:
    """Read an uploaded workbook. Never raises for bad content: problems are
    returned as ``issues`` (a file with issues must not be imported)."""
    from openpyxl import load_workbook

    wb = ParsedWorkbook()
    try:
        book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        wb.issues.append(Issue("", 0, _("This is not an Excel workbook (.xlsx).")))
        return wb
    try:
        for ws in book.worksheets:
            raw = list(ws.iter_rows(values_only=True))
            if ws.title == META_SHEET:
                wb.meta = {str(r[0]): r[1] for r in raw if r and len(r) > 1 and r[0] is not None}
                continue
            if not raw:
                continue
            headers = [_norm_header(h) for h in raw[0]]
            key = _identify({h for h in headers if h})
            if key not in PORTFOLIO_SHEETS or key in wb.sheets:
                continue
            wb.sheets.append(key)
            rows = []
            for i, values in enumerate(raw[1:], start=2):
                rec = {h: v for h, v in zip(headers, values) if h}
                if all(_blank(v) for v in rec.values()):
                    continue
                rows.append((i, rec))
            _parse_rows(key, rows, wb)
    finally:
        book.close()
    version = wb.meta.get("format_version")
    try:
        if version is not None and int(version) > FORMAT_VERSION:
            wb.issues.append(Issue("", 0, _("This file was made by a newer version of Uvalu. Update the app first.")))
    except (TypeError, ValueError):
        pass
    if not wb.sheets and not wb.issues:
        wb.issues.append(Issue("", 0, _("No Uvalu sheets found. Start from an Uvalu export.")))
    return wb


# ── Import: plan and apply ────────────────────────────────────────────────────

def _iso(d: date | None) -> str:
    return "" if d is None else pd.Timestamp(d).isoformat()


def _day(v) -> date | None:
    ts = pd.to_datetime(v, errors="coerce", format="ISO8601")
    return None if pd.isna(ts) else ts.date()


def _close(a, b) -> bool:
    try:
        return abs(float(a) - float(b)) < 0.005
    except (TypeError, ValueError):
        return False


def _trade_key(ticker, date_in, shares) -> tuple:
    return (str(ticker or "").upper(), _day(date_in), round(float(pd.to_numeric(shares, errors="coerce") or 0), 6))


@dataclass
class ImportPlan:
    mode: str
    new: dict[str, int]            # rows that would be written, per sheet key
    skipped: dict[str, int]        # duplicates skipped (add mode)
    positions: list[dict] = field(default_factory=list)
    sold: list[dict] = field(default_factory=list)
    dividends: list[dict] = field(default_factory=list)
    cash: list[dict] = field(default_factory=list)
    watchlist: dict[str, str] = field(default_factory=dict)


def plan_import(wb: ParsedWorkbook, mode: str) -> ImportPlan:
    """Which rows an import writes. ``replace`` takes the whole file; ``add``
    leaves out rows that match existing data (positions: ticker + buy date +
    shares; sold: the same + sale date; dividends: ticker + ex-date or
    payment date; cash: date + type + amount + currency)."""
    import cash as cash_mod

    if mode not in ("replace", "add"):
        raise ValueError(mode)
    pos, sold, divs, cash_rows = list(wb.positions), list(wb.sold), list(wb.dividends), list(wb.cash)
    watch = dict(wb.watchlist)
    if mode == "add":
        have_pos = {_trade_key(r.get("ticker"), r.get("date_in"), r.get("shares"))
                    for r in _records(portfolio.load_portfolio())}
        pos = [r for r in pos if _trade_key(r["ticker"], r["date_in"], r["shares"]) not in have_pos]
        have_sold = {(_trade_key(r.get("ticker"), r.get("date_in"), r.get("shares")), _day(r.get("date_out")))
                     for r in _records(portfolio.load_sold())}
        sold = [r for r in sold
                if (_trade_key(r["ticker"], r["date_in"], r["shares"]), r["date_out"]) not in have_sold]
        have_div = _records(portfolio.load_div_hist())
        by_ticker: dict[str, list[tuple]] = {}
        for r in have_div:
            by_ticker.setdefault(str(r.get("ticker") or "").upper(), []).append(
                (_day(r.get("ex_date")), _day(r.get("date"))))
        divs = [r for r in divs
                if not any(r["ex_date"] in pair or r["date"] in pair for pair in by_ticker.get(r["ticker"], []))]
        base = portfolio.base_currency()
        have_cash = []
        for e in cash_mod.manual_entries():
            adj = e.get("type") == "Adjustment"
            have_cash.append((_day(e.get("date")), e.get("type"),
                              e.get("target_balance") if adj else abs(float(e.get("amount") or 0.0)),
                              str(e.get("currency") or base).upper()))
        cash_rows = [r for r in cash_rows
                     if not any(d == r["date"] and t == r["type"] and _close(a, r["amount"])
                                and c == (r["currency"] or base) for d, t, a, c in have_cash)]
    if mode == "add":
        have_watch = portfolio.load_watchlist()
        watch = {t: n for t, n in watch.items() if t not in have_watch}
    new = wb.counts()
    new.update(positions=len(pos), sold=len(sold), dividends=len(divs), cash=len(cash_rows),
               watchlist=len(watch))
    full = wb.counts()
    skipped = {k: full[k] - new[k] for k in PORTFOLIO_SHEETS}
    return ImportPlan(mode, new, skipped, pos, sold, divs, cash_rows, watch)


class ImportError_(ValueError):
    """The import cannot run; the message is user-facing. Nothing was written."""


def _resolve_cash_rates(rows: list[dict]) -> list[dict]:
    """Cash rows with fx_rate/fx_source/fx_date filled — done before any
    write, so a missing ECB rate stops the import with the data intact."""
    import cash
    import fx

    base = portfolio.base_currency()
    out = []
    for r in rows:
        ccy = (r.get("currency") or base).upper()
        if r["type"] == "Adjustment" or ccy == base:
            out.append({**r, "currency": base if r["type"] == "Adjustment" else ccy,
                        "fx_rate": 1.0, "fx_source": "base", "fx_date": None})
            continue
        if r.get("fx_rate"):
            out.append({**r, "currency": ccy, "fx_source": "manual", "fx_date": None})
            continue
        try:
            rate, src, fx_date = cash.resolve_rate(ccy, r["date"])
        except fx.FxUnavailable:
            raise ImportError_(_("No exchange rate for {currency} on {date}. Add it in the fx_rate column.",
                                 currency=ccy, date=r["date"].isoformat()))
        out.append({**r, "currency": ccy, "fx_rate": rate, "fx_source": src, "fx_date": fx_date})
    return out


def _sold_dividends(sold: list[dict], lots: list[dict], div_df: "pd.DataFrame | None") -> list[float]:
    """Net dividends (EUR, after foreign and Belgian withholding — the figure
    the app keeps on positions) received by each sold lot: every dividend of
    the ticker with an ex-date inside the holding period, split by share
    count over all lots (open and sold) held on that day. IE3."""
    totals = [0.0] * len(sold)
    if div_df is None or div_df.empty or not sold:
        return totals
    eur = portfolio.dividends_in_eur(div_df)
    today = pd.Timestamp(date.today())
    for _, d in eur.iterrows():
        ex = _day(d.get("ex_date")) or _day(d.get("date"))
        pay = pd.to_datetime(d.get("date"), errors="coerce")
        if ex is None or pd.isna(pay) or pay > today:
            continue
        ticker = str(d.get("ticker") or "").upper()
        holders = []
        for lot in lots:
            if str(lot.get("ticker") or "").upper() != ticker:
                continue
            d_in, d_out = _day(lot.get("date_in")), _day(lot.get("date_out"))
            if d_in is None or d_in > ex or (d_out is not None and d_out <= ex):
                continue
            holders.append(lot)
        total_sh = sum(float(pd.to_numeric(h.get("shares"), errors="coerce") or 0) for h in holders)
        if total_sh <= 0:
            continue
        net = float(pd.to_numeric(d.get("net_after_be_amount_eur"), errors="coerce") or 0.0)
        for h in holders:
            idx = h.get("_sold_idx")
            if idx is not None:
                totals[idx] += net * float(pd.to_numeric(h.get("shares"), errors="coerce") or 0) / total_sh
    return [round(t, 2) for t in totals]


# Replace restores the portfolio and watchlist; settings stay. The watchlist
# (and its hand-added tickers' names) is rewritten from the file below.
_REPLACED_FILES = ("portfolio.json", "sold.json", "dividends_history.json", "cash.json")


def apply_import(wb: ParsedWorkbook, mode: str, email: str) -> ImportPlan:
    """Write an import to the active user's data. Returns the plan it
    applied. Raises ImportError_ before writing anything when it can't run."""
    import cash
    from uvalu import logkit

    if wb.issues:
        raise ImportError_(_("Fix the problems in the file first."))
    plan = plan_import(wb, mode)
    cash_rows = _resolve_cash_rates(plan.cash)

    if mode == "replace":
        import backup
        backup.create_backup(email)
        udir = portfolio.user_data_dir(email)
        for fname in _REPLACED_FILES:
            (udir / fname).unlink(missing_ok=True)

    names: dict[str, str] = dict(portfolio.load_manual_tickers())
    for r in [*plan.positions, *plan.sold, *_records(portfolio.load_portfolio()), *_records(portfolio.load_sold())]:
        if r.get("name") and str(r.get("ticker") or ""):
            names.setdefault(str(r["ticker"]).upper(), str(r["name"]))

    ids = iter(portfolio.reserve_ids("trade", len(plan.positions) + len(plan.sold)))
    pos_rows, trades = [], []
    for r in plan.positions:
        tid = next(ids)
        pv = round(float(r["purchase_value"]), 2)
        pos_rows.append({
            "name": r["name"] or names.get(r["ticker"], r["ticker"]), "ticker": r["ticker"],
            "shares": r["shares"], "purchase_price": round(pv / float(r["shares"]), 4),
            "purchase_value": pv, "dividends": 0.0, "date_in": _iso(r["date_in"]),
            "trade_id": tid, "fee": round(float(r["fee"] or 0.0), 2),
        })
        trades.append({"kind": "Buy", "trade_id": tid, "ticker": r["ticker"], "shares": r["shares"],
                       "gross": pv, "fee": r["fee"] or 0.0, "date": r["date_in"]})
    sold_rows = []
    for r in plan.sold:
        tid = next(ids)
        row = {
            "name": r["name"] or names.get(r["ticker"], r["ticker"]), "ticker": r["ticker"],
            "shares": r["shares"], "purchase_value": round(float(r["purchase_value"]), 2),
            "sale_value": round(float(r["sale_value"]), 2), "dividends": 0.0,
            "date_in": _iso(r["date_in"]), "date_out": _iso(r["date_out"]), "trade_id": tid,
        }
        if r["fee"]:
            row["fee"] = round(float(r["fee"]), 2)
        if r.get("sector"):
            row["sector"] = r["sector"]
        sold_rows.append(row)
        trades.append({"kind": "Buy", "trade_id": tid, "ticker": r["ticker"], "shares": r["shares"],
                       "gross": row["purchase_value"], "fee": 0.0, "date": r["date_in"]})
        trades.append({"kind": "Sell", "trade_id": tid, "ticker": r["ticker"], "shares": r["shares"],
                       "gross": row["sale_value"], "fee": r["fee"] or 0.0, "date": r["date_out"]})

    div_ids = iter(portfolio.reserve_ids("dividend", len(plan.dividends)))
    div_rows = []
    for r in plan.dividends:
        amount = round(float(r["amount"]), 2)
        fwh, _be, _net = portfolio.dividend_tax_breakdown(amount, float(r["tax_rate"] or 0.0), r["div_type"])
        div_rows.append({
            "name": r["name"] or names.get(r["ticker"], r["ticker"]), "ticker": r["ticker"],
            "shares": r["shares"], "amount": amount,
            "amount_per_share": round(amount / float(r["shares"]), 4) if r["shares"] else None,
            "currency": r["currency"], "tax_rate": round(float(r["tax_rate"] or 0.0), 2),
            "tax_amount": fwh, "div_type": r["div_type"], "source": "manual",
            "ex_date": _iso(r["ex_date"]), "date": _iso(r["date"]), "div_id": next(div_ids),
        })

    def _concat(old, new_rows):
        new_df = pd.DataFrame(new_rows)
        if old is None or old.empty:
            return new_df
        return pd.concat([old, new_df], ignore_index=True) if new_rows else old

    div_df = _concat(portfolio.load_div_hist(), div_rows)
    if div_rows:
        portfolio.save_div_hist(div_df)

    # Sold dividends need every lot of the ticker (existing and new).
    existing_pf, existing_sold = _records(portfolio.load_portfolio()), _records(portfolio.load_sold())
    lots = [*existing_pf, *existing_sold, *pos_rows,
            *({**s, "_sold_idx": i} for i, s in enumerate(sold_rows))]
    for row, total in zip(sold_rows, _sold_dividends(sold_rows, lots, div_df)):
        row["dividends"] = total
        ar = portfolio._annual_return_pct(row["purchase_value"], row["sale_value"], total,
                                          row["date_in"], row["date_out"])
        row["annual_return_pct"] = float("nan") if ar is None else ar

    if pos_rows:
        portfolio.save_portfolio(_concat(portfolio.load_portfolio(), pos_rows))
    if sold_rows:
        portfolio.save_sold(_concat(portfolio.load_sold(), sold_rows))
    if not div_df.empty:
        portfolio._sync_portfolio_dividends(div_df)

    # Dividend cash first, so trades only top up what the dividends don't cover.
    try:
        cash.reconcile_dividend_postings()
    except Exception:
        logkit.get_logger("uvalu.workbook").warning(
            "dividend cash reconcile after import failed", exc_info=True,
            extra={"event": "cash.reconcile_failed"})
    if cash_rows or trades:
        cash.import_entries(cash_rows, trades)

    # Watchlist: a name in the file marks a hand-added ticker (manual_tickers).
    named = {t: n for t, n in plan.watchlist.items() if n}
    if mode == "replace":
        portfolio.save_watchlist(set(wb.watchlist))
        portfolio.save_manual_tickers({t: n for t, n in wb.watchlist.items() if n})
    elif plan.watchlist:
        portfolio.save_watchlist(portfolio.load_watchlist() | set(plan.watchlist))
        if named:
            portfolio.save_manual_tickers({**portfolio.load_manual_tickers(), **named})

    logkit.data_mutation(actor=logkit.user_id(), action="workbook.import", entity_type="portfolio",
                         mode=mode, **{k: v for k, v in plan.new.items()})
    return plan
