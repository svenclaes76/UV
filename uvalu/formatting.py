"""Pure value formatters shared across pages."""
import re

from uvalu import exchanges
from uvalu.i18n import _, fmt_money, tr


def fmt_eur(v) -> str:
    """Format a value as a Euro price in the region format, or '—' if missing."""
    return fmt_money(v, "EUR")


def row_currency(row) -> str:
    """The quote currency of a scored row or holding: its own ``Currency``
    field, else the currency of its ticker's exchange, else EUR. Per-share
    figures (price, fair value, EPS, DPS) are in this currency, never in a
    fixed one (exchange expansion plan EX-39)."""
    get = row.get if hasattr(row, "get") else (lambda _k, _d=None: _d)
    ccy = get("Currency")
    if isinstance(ccy, str) and len(ccy.strip()) == 3 and ccy.strip().isalpha():
        return ccy.strip().upper()
    ex = exchanges.for_ticker(get("Ticker") or get("ticker"))
    return ex.currency if ex else "EUR"


def share_class(row) -> "str | None":
    """The row's share class ("B") when its company has several classes on
    one exchange (EX-W3, D20); None otherwise."""
    get = row.get if hasattr(row, "get") else (lambda _k, _d=None: _d)
    cls = get("share_class")
    return cls.strip() if isinstance(cls, str) and cls.strip() else None


def safe_pct(numerator: float, denominator: float) -> float:
    """Return numerator/denominator*100, or 0 if denominator is zero."""
    return numerator / denominator * 100 if denominator else 0


def exchange_label(ticker, exchange=None) -> str:
    """The row's own exchange name when it has one, else the official name of
    its ticker's exchange (uvalu/exchanges.py, never translated: D11); "—"
    when neither is known."""
    if isinstance(exchange, str) and exchange.strip():
        return tr(exchange)
    ex = exchanges.for_ticker(ticker)
    return ex.name if ex else "—"


# Legal forms and acronyms that stay upper case when an ALL-CAPS name is
# title-cased; small connecting words go lower case (except as the first word).
_KEEP_UPPER = {"AB", "AG", "AS", "ASA", "BV", "NV", "SA", "SE", "SPA", "PLC", "OYJ", "KGAA", "SCA", "SAS",
               "A/S", "ABP", "HF",              # Nordic legal forms (EX-W3, plan §10 P5)
               "NV/SA", "SA/NV", "ETF", "REIT", "SICAV", "SIIQ", "SOCIMI"}
_TITLE_SHORT = {"INC", "LTD", "CO", "CORP", "GRP", "HLD", "NEW", "ONE", "TWO", "BIO"}
_SMALL_WORDS = {"ET", "DE", "DI", "DU", "DES", "LA", "LE", "LES", "AND", "OF", "THE", "DEL", "DA",
                "VAN", "DER", "EN", "UND", "Y", "E"}
_CLASS_WORDS = {"CLASS", "CL", "SERIES", "SERIE", "CAT", "KLASSE"}


def _title_token(tok: str, first: bool) -> str:
    core = tok.strip(".,()")
    up = core.upper()
    if not core or "&" in core or up in _KEEP_UPPER:
        return tok
    if up in _SMALL_WORDS and not first:
        return tok.lower()
    if len(core) <= 3 and core.isalpha() and up not in _TITLE_SHORT and up not in _SMALL_WORDS:
        return tok                                     # an acronym: EOG, TUI, SBM
    return tok.title()


def display_name(name, share_class: "str | None" = None) -> str:
    """A company name as shown in the UI — the provider's own spelling,
    tidied for reading; stored data is never changed (visual review G5).

    - drops a trailing one-letter share-class code ("MBB SE I", "TUI AG N",
      "Kinross Gold Corp. R") but keeps "Class B";
    - "Cigna Group, The" → "The Cigna Group";
    - an ALL-CAPS name is title-cased, keeping legal forms (AG, NV, SE, …),
      short acronyms and "&" names (B&C) upper case: "CEOTRONICS AG I" →
      "Ceotronics AG", "MAUREL ET PROM" → "Maurel et Prom".
    A ticker standing in for a missing name ("1CF.MI") is left alone.
    Anything that isn't a non-empty string comes back as ''.

    ``share_class`` ("B"), set when a company has several classes on one
    exchange, is added after the name: "Investor AB · B shares" (D20)."""
    if not isinstance(name, str) or not name.strip():
        return ""
    toks = name.split()
    if len(toks) == 1 and (re.fullmatch(r"[A-Z0-9-]+\.[A-Z]{1,3}", toks[0]) or any(c.isdigit() for c in toks[0])):
        return toks[0]                                 # a ticker standing in for a missing name
    if len(toks) > 1 and re.fullmatch(r"[A-Z]", toks[-1]) and toks[-2].upper().strip(".") not in _CLASS_WORDS:
        toks = toks[:-1]
    out = " ".join(toks)
    m = re.fullmatch(r"(.+?),\s*the", out, flags=re.IGNORECASE)
    if m:
        out = f"The {m.group(1)}"
    letters = [c for c in out if c.isalpha()]
    if len(letters) > 3 and all(c.isupper() for c in letters):
        out = " ".join(_title_token(t, i == 0) for i, t in enumerate(out.split()))
    if isinstance(share_class, str) and share_class.strip():
        # Translators: Screener, Watchlist and stock details › a company name followed by its share class, shown only when a company has several share classes on one exchange, e.g. "Volvo AB · B shares". {share_class} is a single letter (A, B, P …).
        out = _("{name} · {share_class} shares", name=out, share_class=share_class.strip())
    return out


# Exchange short codes shown next to a ticker (Screener, Watchlist): the
# venue's own abbreviation, never translated (glossary: exchange names stay).
# Covered and planned exchanges from the registry, so a holding on a planned
# venue (London, Madrid …) gets a readable code too.
EXCHANGE_CODES = {e.suffix.lstrip("."): e.badge for e in (*exchanges.EXCHANGES, *exchanges.PLANNED)}


def exchange_code(ticker) -> "str | None":
    """"PAR" for "TTE.PA"; the raw suffix for another venue; None without one."""
    if not isinstance(ticker, str) or "." not in ticker:
        return None
    suffix = ticker.rsplit(".", 1)[1].upper()
    return EXCHANGE_CODES.get(suffix, suffix) or None
