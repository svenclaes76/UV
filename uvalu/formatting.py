"""Pure value formatters shared across pages."""
import re

from uvalu.i18n import fmt_money


def fmt_eur(v) -> str:
    """Format a value as a Euro price in the region format, or '—' if missing."""
    return fmt_money(v, "EUR")


def safe_pct(numerator: float, denominator: float) -> float:
    """Return numerator/denominator*100, or 0 if denominator is zero."""
    return numerator / denominator * 100 if denominator else 0


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
