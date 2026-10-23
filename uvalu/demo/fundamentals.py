"""Hand-entered fundamentals for the demo (demo-mode plan DM-4, spec F-09).

The EODHD free plan has no European fundamentals, so each demo stock gets one
JSON file, ``demo-data/fundamentals/<ticker>.json``, typed in from the
company's own published reports. The file holds **only figures as reported**,
by fiscal year: no ratios. Ratios (margins, ROE, P/E, payout, ...) are derived
from these when the snapshot is fed into the app (DM-5), so every number the
demo shows traces back to a report and a page.

File shape (``template()`` writes an empty one):

    {
      "ticker": "ABI.BR",                 stored key, a demo stock
      "company": "...",
      "reporting_currency": "USD",        currency of the statements
      "dividend_currency": "EUR",         currency the dividend is declared in
      "fiscal_year_end": "12-31",         MM-DD
      "statement_type": "bank",           optional; "industrial" when left out
      "entered_on": "2026-10-18",         when this file was last checked
      "sources": {"fy25": {"title": ..., "url": ..., "published": "2026-02-12"}},
      "years": [                          newest first, 3 or more
        {"fiscal_year": 2025,
         "revenue": {"value": 59320, "source": "fy25", "page": "11"}, ...}
      ]
    }

Amounts are in **millions** of the reporting currency; per-share amounts in
units (``eps_basic`` in the reporting currency, ``dps`` in the dividend
currency); ``shares_weighted`` in millions. Each figure carries the source id
and page; ``note`` explains anything computed from two report lines.

``validate()`` returns a list of problems; tools/demo_fundamentals.py runs it
on every file and CI fails on an error. No Streamlit import.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from uvalu.demo import universe

MIN_YEARS = 3          # the trend vetoes and normalised EPS need three years

# name: (required, description)
FIELDS: dict[str, tuple[bool, str]] = {
    "revenue":             (True,  "Revenue"),
    "ebit":                (True,  "Profit from operations (EBIT) as reported"),
    "ebit_normalized":     (False, "Normalized / underlying EBIT, if the company reports one"),
    "net_income":          (True,  "Profit attributable to equity holders of the parent"),
    "eps_basic":           (True,  "Basic EPS, per share, reporting currency"),
    "shares_weighted":     (True,  "Weighted average number of shares, millions"),
    "cfo":                 (True,  "Cash flow from operating activities"),
    "capex":               (True,  "Purchases of PP&E and intangibles, as a positive number"),
    "total_assets":        (True,  "Total assets"),
    "equity":              (True,  "Equity attributable to equity holders of the parent"),
    "retained_earnings":   (False, "Retained earnings"),
    "total_debt":          (True,  "Interest-bearing loans and borrowings, current + non-current"),
    "cash":                (True,  "Cash and cash equivalents"),
    "current_assets":      (True,  "Total current assets"),
    "current_liabilities": (True,  "Total current liabilities"),
    "interest_expense":    (False, "Net interest expense, as a positive number"),
    "dps":                 (False, "Dividend per share for the fiscal year, dividend currency"),
}

TOP_KEYS = ("ticker", "company", "reporting_currency", "dividend_currency",
            "fiscal_year_end", "entered_on", "sources", "years")
OPTIONAL_TOP_KEYS = ("statement_type",)

# A bank's statements have no operating profit, current assets or liabilities,
# capex or meaningful operating cash flow; with "statement_type": "bank" these
# become optional. Revenue is the bank's total income.
STATEMENT_TYPES = ("industrial", "bank")
BANK_OPTIONAL = frozenset({"ebit", "cfo", "capex", "total_debt", "cash",
                           "current_assets", "current_liabilities", "interest_expense"})

_ISO_CCY = re.compile(r"^[A-Z]{3}$")
_MMDD = re.compile(r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")


@dataclass(frozen=True)
class Problem:
    level: str          # "error" or "warning"
    where: str          # "years[0].revenue"
    message: str

    def __str__(self) -> str:
        return f"{self.level}: {self.where}: {self.message}"


def path_for(root: Path, ticker: str) -> Path:
    return Path(root) / "fundamentals" / f"{ticker}.json"


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _num(v) -> "float | None":
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if math.isfinite(v) else None


def _iso_date(s) -> bool:
    try:
        date.fromisoformat(str(s))
        return True
    except ValueError:
        return False


def value(year: dict, field: str) -> "float | None":
    """A field's number from one year entry, or None."""
    entry = year.get(field)
    return _num(entry.get("value")) if isinstance(entry, dict) else None


def validate(doc: dict, *, file_ticker: "str | None" = None) -> list[Problem]:
    """Every problem in one fundamentals document; empty means valid."""
    out: list[Problem] = []
    err = lambda w, m: out.append(Problem("error", w, m))      # noqa: E731
    warn = lambda w, m: out.append(Problem("warning", w, m))   # noqa: E731

    if not isinstance(doc, dict):
        return [Problem("error", "file", "not a JSON object")]
    for k in TOP_KEYS:
        if k not in doc:
            err(k, "missing")
    for k in doc:
        if k not in TOP_KEYS and k not in OPTIONAL_TOP_KEYS:
            warn(k, "unknown key")
    kind = doc.get("statement_type", "industrial")
    if kind not in STATEMENT_TYPES:
        err("statement_type", f"expected one of: {', '.join(STATEMENT_TYPES)}")

    ticker = doc.get("ticker")
    if ticker not in universe.STOCKS:
        err("ticker", f"{ticker!r} is not a demo stock")
    if file_ticker and ticker != file_ticker:
        err("ticker", f"{ticker!r} doesn't match the file name {file_ticker!r}")
    for k in ("reporting_currency", "dividend_currency"):
        if k in doc and not _ISO_CCY.match(str(doc[k])):
            err(k, "expected a 3-letter ISO currency code")
    if "fiscal_year_end" in doc and not _MMDD.match(str(doc["fiscal_year_end"])):
        err("fiscal_year_end", "expected MM-DD")
    if "entered_on" in doc and not _iso_date(doc["entered_on"]):
        err("entered_on", "expected an ISO date")

    sources = doc.get("sources") if isinstance(doc.get("sources"), dict) else {}
    if not sources:
        err("sources", "at least one source is needed")
    for sid, s in sources.items():
        if not isinstance(s, dict) or not s.get("title") or not s.get("url"):
            err(f"sources.{sid}", "needs a title and a url")
        elif not _iso_date(s.get("published")):
            err(f"sources.{sid}.published", "expected an ISO date")

    years = doc.get("years") if isinstance(doc.get("years"), list) else []
    if len(years) < MIN_YEARS:
        err("years", f"{len(years)} year(s); at least {MIN_YEARS} are needed")
    fys = [y.get("fiscal_year") for y in years if isinstance(y, dict)]
    if fys != sorted(fys, reverse=True) or len(set(fys)) != len(fys):
        err("years", "fiscal years must be unique and newest first")
    elif fys and any(a - b != 1 for a, b in zip(fys, fys[1:])):
        warn("years", "fiscal years are not consecutive")

    for i, y in enumerate(years):
        w = f"years[{i}]"
        if not isinstance(y, dict) or not isinstance(y.get("fiscal_year"), int):
            err(w, "needs an integer fiscal_year")
            continue
        for k in y:
            if k != "fiscal_year" and k not in FIELDS:
                warn(f"{w}.{k}", "unknown field")
        for name, (required, _desc) in FIELDS.items():
            required = required and not (kind == "bank" and name in BANK_OPTIONAL)
            entry = y.get(name)
            if entry is None:
                if required:
                    err(f"{w}.{name}", "missing")
                continue
            if not isinstance(entry, dict):
                err(f"{w}.{name}", 'expected {"value": ..., "source": ..., "page": ...}')
                continue
            v = entry.get("value")
            if v is None:
                if required:
                    err(f"{w}.{name}", "required, but the value is null")
                continue
            if _num(v) is None:
                err(f"{w}.{name}", "value is not a number")
                continue
            if entry.get("source") not in sources:
                err(f"{w}.{name}", f"source {entry.get('source')!r} is not in sources")
            if not str(entry.get("page") or "").strip():
                err(f"{w}.{name}", "page is missing")
        _check_consistency(y, w, err, warn)
    return out


def _check_consistency(y: dict, w: str, err, warn) -> None:
    v = lambda f: value(y, f)    # noqa: E731
    for f in ("revenue", "total_assets", "shares_weighted"):
        if v(f) is not None and v(f) <= 0:
            err(f"{w}.{f}", "must be positive")
    for f in ("capex", "cash", "total_debt", "current_assets", "current_liabilities",
              "interest_expense", "dps"):
        if v(f) is not None and v(f) < 0:
            err(f"{w}.{f}", "enter as a positive number")
    if v("revenue") and v("ebit") is not None and abs(v("ebit")) > v("revenue"):
        err(f"{w}.ebit", "larger than revenue: check the unit (millions)")
    if v("total_assets"):
        for f in ("current_assets", "equity", "cash"):
            if v(f) is not None and v(f) > v("total_assets"):
                err(f"{w}.{f}", "larger than total assets")
    # The strongest typo check: basic EPS × weighted shares ≈ net income.
    eps, sh, ni = v("eps_basic"), v("shares_weighted"), v("net_income")
    if eps is not None and sh and ni:
        gap = abs(eps * sh - ni) / abs(ni)
        if gap > 0.05:
            err(f"{w}.eps_basic", f"EPS × shares = {eps * sh:,.0f}, net income {ni:,.0f} "
                                  f"({gap:.0%} apart): check EPS, shares or the unit")
        elif gap > 0.02:
            warn(f"{w}.eps_basic", f"EPS × shares is {gap:.1%} off net income")
    if v("ebit_normalized") is not None and v("revenue") and abs(v("ebit_normalized")) > v("revenue"):
        err(f"{w}.ebit_normalized", "larger than revenue")


def as_of(doc: dict) -> "str | None":
    """The balance-sheet date of the newest fiscal year (ISO), the date shown
    as "Fundamentals as of ..." (spec F-09)."""
    years = doc.get("years") or []
    if not years or not _MMDD.match(str(doc.get("fiscal_year_end", ""))):
        return None
    return f"{years[0]['fiscal_year']}-{doc['fiscal_year_end']}"


def template(ticker: str, years: "tuple[int, ...]" = (2025, 2024, 2023)) -> dict:
    """An empty document for one demo stock, ready to fill in."""
    t = universe.BY_TICKER[ticker]
    blank = {"value": None, "source": "", "page": ""}
    return {
        "ticker": t.ticker,
        "company": t.name,
        "reporting_currency": t.currency,
        "dividend_currency": t.currency,
        "fiscal_year_end": "12-31",
        "entered_on": date.today().isoformat(),
        "sources": {"": {"title": "", "url": "", "published": ""}},
        "years": [{"fiscal_year": fy, **{f: dict(blank) for f in FIELDS}} for fy in years],
    }
