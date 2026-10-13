"""Q1 (model M2): a partial or failed fetch doesn't change a signal
(docs/quant-review.md Q1)."""

from datetime import datetime, timedelta, timezone

import screener as sc


def _iso(days_ago=0):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


GOOD = {"Ticker": "T.BR", "Price": 10.0, "fetched_at": _iso(1),
        "revenueHistory": [3.0, 2.0, 1.0], "ebitHistory": [1.0, 1.0, 1.0], "country": "Belgium"}


def test_a_missing_history_is_carried_forward_and_marked():
    new = {"Ticker": "T.BR", "Price": 11.0, "fetched_at": _iso(), "revenueHistory": None,
           "ebitHistory": [2.0, 1.0, 1.0], "country": "Belgium"}
    out = sc._carry_forward(new, GOOD)
    assert out["revenueHistory"] == [3.0, 2.0, 1.0]
    assert out["ebitHistory"] == [2.0, 1.0, 1.0]         # a fresh value wins
    assert out["carried_forward"] == ["revenueHistory"]
    assert out["Price"] == 11.0


def test_a_failed_fetch_keeps_the_last_good_row_for_a_week():
    stub = {"Ticker": "T.BR", "fetched_at": ""}
    out = sc._carry_forward(stub, GOOD)
    assert out["Price"] == 10.0 and out["revenueHistory"] == [3.0, 2.0, 1.0]
    old = dict(GOOD, fetched_at=_iso(8))
    assert sc._carry_forward(stub, old) is stub


def test_carried_values_expire_even_through_a_chain_of_partial_fetches():
    prev = dict(GOOD, fetched_at=_iso(1), carried_forward=["revenueHistory"],
                carried_since={"revenueHistory": _iso(91)})
    new = {"Ticker": "T.BR", "Price": 11.0, "fetched_at": _iso(), "revenueHistory": None}
    assert sc._carry_forward(new, prev).get("revenueHistory") is None


def test_nothing_to_carry_returns_the_row_unchanged():
    new = dict(GOOD, fetched_at=_iso())
    assert sc._carry_forward(new, GOOD) is new
    assert sc._carry_forward(new, None) is new


def test_a_signal_change_record_names_the_inputs_that_moved(tmp_path):
    from uvalu.compliance import signal_history
    path = tmp_path / "history.jsonl"
    base = {"Ticker": "T.BR", "signal_code": "neutral", "Value Score": 41.0, "Price": 10.0,
            "veto_rules": [], "model_version": "M2", "model_settings_id": "x", "public_universe": True}
    signal_history.record_changes([base], path)
    signal_history.record_changes([dict(base, signal_code="fails_screen",
                                        veto_rules=["revenue_decline"], **{"Value Score": 0.0})], path)
    last = signal_history._read(path)[-1]
    assert last["log_reason"] == "signal_change"
    assert last["changed_inputs"] == ["Value Score", "veto_rules"]
