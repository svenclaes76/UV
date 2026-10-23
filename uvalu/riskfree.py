"""Risk-free rate per currency, from the committed snapshot uvalu/risk_free_rates.json.

Exchange expansion plan EX-W5b (decision D33, model review M2, EX2): the
10-year government bond yield of each quote currency, from the OECD's
"Long-term interest rates" series; EUR uses Germany's (the Bund). The snapshot
is drafted by tools/refresh_risk_free.py each quarter and committed with its
date (open item EX10); nothing here fetches at run time, so signals don't move
with every yield change.

A currency without a rate (Iceland: no OECD series) returns None; the scorer
then discounts at the EUR rate and keeps the row out of Undervalued.

No Streamlit import; unit-tested in tests/test_riskfree.py.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

SNAPSHOT = Path(__file__).parent / "risk_free_rates.json"

# Quote units in a currency's minor unit share the major unit's rate.
_MINOR_UNITS = {"GBX": "GBP", "GBp": "GBP", "ZAC": "ZAR", "ILA": "ILS"}


@lru_cache(maxsize=1)
def _data() -> dict:
    try:
        return json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _key(currency) -> "str | None":
    if not isinstance(currency, str) or not currency.strip():
        return None
    c = currency.strip()
    return _MINOR_UNITS.get(c, c.upper())


def rate(currency) -> "float | None":
    """The yield as a fraction (0.0347), or None when the snapshot has none."""
    entry = _data().get("rates", {}).get(_key(currency) or "")
    try:
        value = float(entry["rate"])
    except (TypeError, KeyError, ValueError):
        return None
    return value


def eur_rate() -> "float | None":
    return rate("EUR")


def period(currency) -> "str | None":
    """The month the yield is for ("2026-09")."""
    entry = _data().get("rates", {}).get(_key(currency) or "")
    return entry.get("period") if isinstance(entry, dict) else None


def as_of() -> "str | None":
    """The date the snapshot was drafted."""
    return _data().get("as_of")


def rates() -> dict[str, float]:
    """{currency: yield} for every currency in the snapshot."""
    return {c: r for c in _data().get("rates", {}) if (r := rate(c)) is not None}
