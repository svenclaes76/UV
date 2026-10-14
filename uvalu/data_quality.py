"""Data-quality summary of each universe build (Q2, model M2).

Every build logs what it saw: how complete the key fields were, how many
signals changed, how many rows had a currency converted or left unverified,
and how many leaned on carried-forward values. A threshold crossed is logged
as a warning, so a partial-payload day or a provider change shows up in the
logs instead of silently moving signals (docs/quant-review.md Q2).

No Streamlit import; unit-tested in tests/test_data_quality.py.
"""
from __future__ import annotations

import pandas as pd

# Fields whose absence moves a fair value or a veto.
KEY_FIELDS = ("Price", "trailingEps", "bookValue", "sharesOutstanding", "beta",
              "sector", "country", "financialCurrency", "fcfHistory", "ebitHistory",
              "revenueHistory")

# Alert thresholds. Missing rates above these mean the provider sent partial
# data for many stocks at once; a signal-change share above the limit means
# a build moved far more signals than ordinary price moves do.
MAX_MISSING_SHARE = {"Price": 0.02, "country": 0.05, "sector": 0.15}
DEFAULT_MAX_MISSING_SHARE = 0.25
MAX_CHANGED_SHARE = 0.05


def _missing(series: pd.Series) -> pd.Series:
    return series.map(lambda v: v is None or v == [] or v == "" or (isinstance(v, float) and v != v))


def build_summary(fund: pd.DataFrame, scored: pd.DataFrame, *, changes: int) -> dict:
    """What one build saw. `fund`: the public universe's fundamentals rows;
    `scored`: the scored public universe; `changes`: signal changes logged."""
    n = len(fund)
    missing = {}
    for field in KEY_FIELDS:
        if field in fund.columns and n:
            missing[field] = round(float(_missing(fund[field]).mean()), 4)
        elif n:
            missing[field] = 1.0
    flags = scored["data_flags"] if "data_flags" in scored.columns else pd.Series([], dtype=object)
    carried = (fund["carried_forward"].map(lambda v: bool(v) if isinstance(v, list) else False).sum()
               if "carried_forward" in fund.columns else 0)
    signals = (scored["signal_code"].value_counts().to_dict()
               if "signal_code" in scored.columns else {})
    return {
        "rows": n,
        "scored": len(scored),
        "missing_share": missing,
        "signal_changes": int(changes),
        "changed_share": round(changes / len(scored), 4) if len(scored) else 0.0,
        "currency_unverified": int(sum("currency_unverified" in f for f in flags if isinstance(f, list))),
        "carried_forward_rows": int(carried),
        "signals": {str(k): int(v) for k, v in signals.items()},
    }


def alerts(summary: dict) -> list[str]:
    """Plain-language alerts for the thresholds `summary` crosses."""
    out = []
    for field, share in summary.get("missing_share", {}).items():
        limit = MAX_MISSING_SHARE.get(field, DEFAULT_MAX_MISSING_SHARE)
        if share > limit:
            out.append(f"{field} missing for {share:.0%} of rows (limit {limit:.0%})")
    if summary.get("changed_share", 0.0) > MAX_CHANGED_SHARE:
        out.append(f"{summary['signal_changes']} signal changes in one build, "
                   f"{summary['changed_share']:.0%} of stocks (limit {MAX_CHANGED_SHARE:.0%})")
    return out
