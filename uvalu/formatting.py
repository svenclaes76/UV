"""Pure value formatters shared across pages."""
import re

from uvalu.i18n import N_, fmt_money, tr


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
    from portfolio import currency_for_ticker
    return currency_for_ticker(str(get("Ticker") or get("ticker") or ""))


def safe_pct(numerator: float, denominator: float) -> float:
    """Return numerator/denominator*100, or 0 if denominator is zero."""
    return numerator / denominator * 100 if denominator else 0


# Ticker suffix → exchange, for rows that carry no "Exchange" field (the
# portfolio lane, the risk table) — one map instead of a copy per page.
TICKER_SUFFIX_EXCHANGE = {
    ".BR": N_("Brussels"), ".AS": N_("Amsterdam"), ".PA": N_("Paris"),
    ".MI": N_("Milan"), ".DE": N_("Frankfurt"), ".SW": N_("Swiss"),
}


def exchange_label(ticker, exchange=None) -> str:
    """The row's own exchange name when it has one, else the one its ticker
    suffix implies, translated; "—" when neither is known."""
    if isinstance(exchange, str) and exchange.strip():
        return tr(exchange)
    for suffix, label in TICKER_SUFFIX_EXCHANGE.items():
        if str(ticker or "").endswith(suffix):
            return tr(label)
    return "—"


# Legal forms and acronyms that stay upper case when an ALL-CAPS name is
# title-cased; small connecting words go lower case (except as the first word).
_KEEP_UPPER = {"AB", "AG", "AS", "ASA", "BV", "NV", "SA", "SE", "SPA", "PLC", "OYJ", "KGAA", "SCA", "SAS",
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


def display_name(name) -> str:
    """A company name as shown in the UI — the provider's own spelling,
    tidied for reading; stored data is never changed (visual review G5).

    - drops a trailing one-letter share-class code ("MBB SE I", "TUI AG N",
      "Kinross Gold Corp. R") but keeps "Class B";
    - "Cigna Group, The" → "The Cigna Group";
    - an ALL-CAPS name is title-cased, keeping legal forms (AG, NV, SE, …),
      short acronyms and "&" names (B&C) upper case: "CEOTRONICS AG I" →
      "Ceotronics AG", "MAUREL ET PROM" → "Maurel et Prom".
    A ticker standing in for a missing name ("1CF.MI") is left alone.
    Anything that isn't a non-empty string comes back as ''."""
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
    return out


# Exchange short codes shown next to a ticker (Screener, Watchlist): the
# venue's own abbreviation, never translated (glossary: exchange names stay).
EXCHANGE_CODES = {"BR": "BRU", "PA": "PAR", "AS": "AMS", "MI": "MIL", "DE": "XET", "SW": "SWX",
                  "L": "LON", "MC": "MAD", "HE": "HEL", "ST": "STO"}


def exchange_code(ticker) -> "str | None":
    """"PAR" for "TTE.PA"; the raw suffix for another venue; None without one."""
    if not isinstance(ticker, str) or "." not in ticker:
        return None
    suffix = ticker.rsplit(".", 1)[1].upper()
    return EXCHANGE_CODES.get(suffix, suffix) or None
