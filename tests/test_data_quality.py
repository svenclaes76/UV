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


# ── EX-W11: universe change, per-exchange mix ──────────────────────────────

def test_a_universe_or_model_shift_explains_a_burst_of_changes():
    import pandas as pd
    from uvalu import data_quality
    scored = pd.DataFrame({"Ticker": [f"T{i}.PA" for i in range(20)], "signal_code": ["neutral"] * 20})
    plain = data_quality.build_summary(scored, scored, changes=10)
    assert any("signal changes" in a for a in data_quality.alerts(plain))
    shifted = data_quality.build_summary(scored, scored, changes=10, shift={"universe": True, "model": False})
    assert shifted["universe_changed"] and not any("signal changes" in a for a in data_quality.alerts(shifted))


def test_per_exchange_undervalued_alert_needs_five_stocks():
    import pandas as pd
    from uvalu import data_quality
    rows = ([("A%d.PA" % i, "neutral") for i in range(95)] + [("U%d.PA" % i, "undervalued") for i in range(1)]
            + [("W%d.WA" % i, "neutral") for i in range(15)] + [("V%d.WA" % i, "undervalued") for i in range(5)]
            + [("D0.IR", "undervalued")] + [("D%d.IR" % i, "neutral") for i in range(1, 20)])
    scored = pd.DataFrame(rows, columns=["Ticker", "signal_code"])
    s = data_quality.build_summary(scored, scored, changes=0)
    assert s["by_exchange"][".WA"] == {"rows": 20, "undervalued": 5, "median_pe": None}
    alerts = data_quality.alerts(s)
    assert any(a.startswith(".WA:") for a in alerts)          # 25% vs 5.0%, 5 stocks
    assert not any(a.startswith(".IR:") for a in alerts)      # 1 stock only


def test_universe_change_is_a_changed_input(tmp_path):
    from uvalu.compliance import signal_history as sh
    path = tmp_path / "h.jsonl"
    base = {"Ticker": "AIR.PA", "signal_code": "neutral", "public_universe": True,
            "model_version": "M5", "model_settings_id": "x", "universe_id": "old"}
    sh.record_changes([base], path)
    moved = dict(base, signal_code="undervalued", universe_id="new")
    assert sh.shift([moved], path) == {"universe": True, "model": False}
    sh.record_changes([moved], path)
    last = sh._last_records(path)["AIR.PA"]
    assert "universe_change" in last["changed_inputs"]
    assert sh.shift([moved], path) == {"universe": False, "model": False}


def test_fingerprint_follows_exchanges_and_rule():
    from uvalu import universe
    assert universe.fingerprint(["paris", "milan"]) == universe.fingerprint(["milan", "paris"])
    assert universe.fingerprint(["paris"]) != universe.fingerprint(["paris", "oslo"])
