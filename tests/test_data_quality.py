"""Q2 (model M2): the per-build data-quality summary and its alerts."""

import pandas as pd

from uvalu import data_quality as dq


def _fund(n=100, missing_eps=0):
    rows = [{"Ticker": f"T{i}.BR", "Price": 10.0, "trailingEps": None if i < missing_eps else 1.0,
             "country": "Belgium", "sector": "Industrials", "fcfHistory": [1.0, 2.0],
             "carried_forward": ["revenueHistory"] if i < 3 else None} for i in range(n)]
    return pd.DataFrame(rows)


def _scored(n=100):
    return pd.DataFrame([{"Ticker": f"T{i}.BR", "signal_code": "neutral",
                          "data_flags": ["currency_unverified"] if i == 0 else []} for i in range(n)])


def test_summary_counts_missing_fields_changes_and_flags():
    s = dq.build_summary(_fund(missing_eps=10), _scored(), changes=4)
    assert s["missing_share"]["trailingEps"] == 0.10
    assert s["missing_share"]["Price"] == 0.0
    assert s["missing_share"]["financialCurrency"] == 1.0     # not in the frame at all
    assert s["signal_changes"] == 4 and s["changed_share"] == 0.04
    assert s["currency_unverified"] == 1 and s["carried_forward_rows"] == 3
    assert s["signals"] == {"neutral": 100}


def test_a_quiet_build_raises_no_alerts_except_missing_new_fields():
    s = dq.build_summary(_fund(), _scored(), changes=2)
    s["missing_share"] = {k: v for k, v in s["missing_share"].items() if v < 1.0}
    assert dq.alerts(s) == []


def test_partial_payloads_and_mass_changes_raise_alerts():
    s = dq.build_summary(_fund(missing_eps=40), _scored(), changes=12)
    texts = dq.alerts(s)
    assert any(t.startswith("trailingEps missing for 40%") for t in texts)
    assert any("12 signal changes in one build" in t for t in texts)
