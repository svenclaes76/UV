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
# D37: an exchange whose Undervalued share is above this multiple of the
# universe's, with at least MIN_UNDERVALUED_FOR_RATIO such stocks (decided
# 24 October 2026, as in the shadow build's go/no-go).
MAX_UNDERVALUED_RATIO = 3.0
MIN_UNDERVALUED_FOR_RATIO = 5


def _missing(series: pd.Series) -> pd.Series:
    return series.map(lambda v: v is None or v == [] or v == "" or (isinstance(v, float) and v != v))


def _by_exchange(scored: pd.DataFrame) -> dict[str, dict]:
    """D37: per exchange suffix, rows, Undervalued count and median P/E."""
    if scored.empty or "Ticker" not in scored.columns or "signal_code" not in scored.columns:
        return {}
    suffix = scored["Ticker"].astype(str).map(lambda t: "." + t.rsplit(".", 1)[-1] if "." in t else "")
    pe = pd.to_numeric(scored["trailingPE"], errors="coerce") if "trailingPE" in scored.columns else None
    out = {}
    for sfx, idx in suffix.groupby(suffix).groups.items():
        part_pe = pe.loc[idx] if pe is not None else pd.Series(dtype=float)
        part_pe = part_pe[part_pe > 0]
        out[sfx] = {"rows": int(len(idx)),
                    "undervalued": int((scored.loc[idx, "signal_code"] == "undervalued").sum()),
                    "median_pe": round(float(part_pe.median()), 1) if len(part_pe) else None}
    return out


def build_summary(fund: pd.DataFrame, scored: pd.DataFrame, *, changes: int,
                  shift: "dict | None" = None) -> dict:
    """What one build saw. `fund`: the public universe's fundamentals rows;
    `scored`: the scored public universe; `changes`: signal changes logged;
    `shift`: signal_history.shift() — a new universe or model this build."""
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
        "by_exchange": _by_exchange(scored),
        "universe_changed": bool((shift or {}).get("universe")),
        "model_changed": bool((shift or {}).get("model")),
    }


def alerts(summary: dict) -> list[str]:
    """Plain-language alerts for the thresholds `summary` crosses."""
    out = []
    for field, share in summary.get("missing_share", {}).items():
        limit = MAX_MISSING_SHARE.get(field, DEFAULT_MAX_MISSING_SHARE)
        if share > limit:
            out.append(f"{field} missing for {share:.0%} of rows (limit {limit:.0%})")
    # EX-36: a new universe or model moves many signals at once by design;
    # that build's changes carry `universe_change` / `model_version` instead.
    explained = summary.get("universe_changed") or summary.get("model_changed")
    if summary.get("changed_share", 0.0) > MAX_CHANGED_SHARE and not explained:
        out.append(f"{summary['signal_changes']} signal changes in one build, "
                   f"{summary['changed_share']:.0%} of stocks (limit {MAX_CHANGED_SHARE:.0%})")
    by_ex = summary.get("by_exchange") or {}
    rows = sum(v["rows"] for v in by_ex.values())
    uv = sum(v["undervalued"] for v in by_ex.values())
    share = uv / rows if rows else 0.0
    for sfx, v in sorted(by_ex.items()):
        if (share > 0 and v["rows"] and v["undervalued"] >= MIN_UNDERVALUED_FOR_RATIO
                and v["undervalued"] / v["rows"] > MAX_UNDERVALUED_RATIO * share):
            out.append(f"{sfx}: Undervalued {v['undervalued'] / v['rows']:.1%} of {v['rows']} stocks, "
                       f"more than {MAX_UNDERVALUED_RATIO:g}x the universe's {share:.1%}")
    return out
