"""
Legal design rules of the scoring and risk algorithms (screener.py, risk.py,
uvalu/compliance/) — docs/legal/algorithm-compliance-review.md.

Two kinds of check:
  • snapshot — the scored output of a fixed synthetic universe is frozen in
    tests/snapshots/scored_universe.json, so a refactor can't move a fair
    value, score or signal unnoticed. Regenerate deliberately (and bump
    screener.MODEL_VERSION) with ``UVALU_UPDATE_SNAPSHOTS=1 pytest
    tests/test_compliance_algorithms.py``. It replaced the equivalence tests
    against the pre-v2.1.0 originals when the compliant versions were
    swapped in;
  • requirement — each requirement ID the algorithms claim to meet (PER-1/2/4/5,
    BDG-1/3, REC-2/3/4/5/7/8/9/10/11, DATA-6, DIS-3) is pinned by a test.

All offline: synthetic frames, monkeypatched price history and factor data.
"""

import inspect
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import marketdata
import risk
import screener as sc
from uvalu.compliance import settings_audit, signal_history


@pytest.fixture(autouse=True)
def _isolate_factor_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(risk, "_FACTORS_DIR", tmp_path / "factors")
    monkeypatch.setattr(risk, "_ff_cache", {})


_NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
_SECTORS = ["Technology", "Industrials", "Consumer Defensive", "Healthcare"]


def _universe(n: int = 30, seed: int = 3, prefix: str = "P") -> pd.DataFrame:
    """A synthetic scored-universe input: n rows spread across 4 sectors,
    with enough fundamentals for every model family and a fresh fetched_at."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        price = float(rng.uniform(20, 200))
        eps = float(price / rng.uniform(8, 25))
        shares = 1e8
        rows.append({
            "Ticker": f"{prefix}{i}.BR", "Name": f"{prefix}{i}", "Price": price,
            "sector": _SECTORS[i % 4], "country": "Belgium",
            "trailingEps": eps, "trailingPE": price / eps,
            "bookValue": float(price / rng.uniform(1, 4)),
            "trailingAnnualDividendRate": float(eps * rng.uniform(0.3, 0.6)),
            "dividendRate": float(eps * rng.uniform(0.3, 0.6)),
            "payoutRatio": float(rng.uniform(0.3, 0.6)),
            "dividendYield": float(rng.uniform(0.01, 0.05)),
            "targetMeanPrice": float(price * rng.uniform(0.8, 1.4)),
            "targetHighPrice": float(price * 1.5), "targetLowPrice": float(price * 0.7),
            "numberOfAnalystOpinions": 10, "recommendationMean": float(rng.uniform(1.5, 4.0)),
            "ebit": float(eps * shares * rng.uniform(1.2, 1.8)),
            "enterpriseValue": float(price * shares * rng.uniform(1.0, 1.4)),
            "marketCap": price * shares, "sharesOutstanding": shares,
            "freeCashflow": float(eps * shares * rng.uniform(0.5, 1.2)),
            "netIncome": eps * shares, "debtToEquity": float(rng.uniform(20, 150)),
            "currentRatio": float(rng.uniform(0.8, 2.5)), "beta": float(rng.uniform(0.5, 1.6)),
            "averageVolume": float(rng.uniform(1e4, 1e6)),
            "returnOnEquity": float(rng.uniform(0.02, 0.3)),
            "returnOnAssets": float(rng.uniform(0.01, 0.12)),
            "operatingMargins": float(rng.uniform(0.05, 0.3)),
            "earningsGrowth": float(rng.uniform(-0.1, 0.2)),
            "revenueGrowth": float(rng.uniform(-0.05, 0.15)),
            "fetched_at": (_NOW - timedelta(hours=2)).isoformat(),
        })
    return pd.DataFrame(rows)


SNAPSHOT = Path(__file__).parent / "snapshots" / "scored_universe.json"
_SNAPSHOT_COLS = ("fair_value", "Value Score", "margin_of_safety", "Sub MoS", "Sub Risk",
                  "Sub Quality", "Sub Momentum", "Sub Dividend", "Implied Return % (est.)",
                  "signal_code", "veto")


def _jsonable(v):
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (np.integer, np.floating, float, int)):
        f = float(v)
        return None if np.isnan(f) else round(f, 6)
    return v


class TestScoreSnapshot:
    def test_scored_universe_matches_snapshot(self):
        out = sc.compute_scores(_universe(30), computed_at=_NOW).set_index("Ticker").sort_index()
        current = {"model_version": sc.MODEL_VERSION,
                   "rows": {t: {c: _jsonable(out.loc[t, c]) for c in _SNAPSHOT_COLS} for t in out.index}}
        if os.environ.get("UVALU_UPDATE_SNAPSHOTS") == "1" or not SNAPSHOT.exists():
            SNAPSHOT.write_text(json.dumps(current, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        frozen = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        assert frozen["model_version"] == sc.MODEL_VERSION, \
            "MODEL_VERSION changed: regenerate the snapshot (UVALU_UPDATE_SNAPSHOTS=1)"
        for t, cols in frozen["rows"].items():
            for c, v in cols.items():
                got = current["rows"][t][c]
                if isinstance(v, float):
                    assert got == pytest.approx(v, abs=1e-6), (t, c)
                else:
                    assert got == v, (t, c)
        assert set(current["rows"]) == set(frozen["rows"])

    def test_no_decision_column_and_descriptive_labels(self):
        out = sc.compute_scores(_universe(), computed_at=_NOW)
        assert "Decision" not in out.columns and "TER %" not in out.columns
        assert set(out["Signal"]) <= set(sc.SIGNAL_LABELS.values())
        assert not {"Strong Buy", "Monitor", "Avoid"} & set(out["Signal"])


class TestMinimumMarginOfSafety:
    """Decision D1: Undervalued needs at least MIN_MOS_FLOOR whatever the setting."""

    def test_floor_applies_to_signal_methodology_and_reason(self):
        out = sc.compute_scores(_universe(30), min_mos=0.0, computed_at=_NOW)
        und = out[out["signal_code"] == sc.SIGNAL_UNDERVALUED]
        assert (und["margin_of_safety"] >= sc.MIN_MOS_FLOOR).all()
        assert sc.methodology(min_mos=0.0)["thresholds"]["undervalued_min_margin_of_safety"] == sc.MIN_MOS_FLOOR
        assert sc.methodology(min_mos=0.25)["thresholds"]["undervalued_min_margin_of_safety"] == 0.25
        assert sc.effective_min_mos(None) == sc.MIN_MOS_FLOOR

    def test_settings_id_uses_the_effective_floor(self):
        a = sc.compute_scores(_universe(10), min_mos=0.0, computed_at=_NOW)
        b = sc.compute_scores(_universe(10), min_mos=0.10, computed_at=_NOW)
        assert a["model_settings_id"].iloc[0] == b["model_settings_id"].iloc[0]


# ══════════════════════════════════════════════════════════════════════════════
# Screener — requirements
# ══════════════════════════════════════════════════════════════════════════════

class TestDataLicensing:
    """DATA-6: analyst targets and recommendation means are off by default."""

    def test_switch_defaults_off(self):
        assert sc.ANALYST_INPUTS_ENABLED is False

    def test_analyst_fields_do_not_move_any_output(self):
        df = _universe()
        a = sc.compute_scores(df.copy(), computed_at=_NOW).set_index("Ticker")
        df2 = df.copy()
        df2["targetMeanPrice"] *= 3
        df2["recommendationMean"] = 1.0
        b = sc.compute_scores(df2, computed_at=_NOW).set_index("Ticker")
        for col in ("fair_value", "Value Score", "signal_code"):
            pd.testing.assert_series_equal(a[col], b.loc[a.index, col])

    def test_dark_reason_names_the_licence(self):
        out = sc.compute_scores(_universe(5), computed_at=_NOW)
        assert all(r.get("analyst") == "not_licensed" for r in out["fv_dark_reasons"])

    def test_analyst_columns_are_not_in_the_output(self):
        out = sc.compute_scores(_universe(10), computed_at=_NOW)
        assert not set(sc.ANALYST_FIELDS) & set(out.columns)
        assert not set(sc.ANALYST_FIELDS) & set(sc.signal_records(out)[0])

    def test_analyst_columns_kept_when_licensed(self, monkeypatch):
        monkeypatch.setattr(sc, "ANALYST_INPUTS_ENABLED", True)
        out = sc.compute_scores(_universe(10), computed_at=_NOW)
        assert "targetMeanPrice" in out.columns

    def test_strip_analyst_fields_on_rows_and_caches(self):
        row = {"Ticker": "A.BR", "Price": 10.0, "targetMeanPrice": 12.0,
               "recommendationMean": 2.0, "fv_dark_reasons": {"analyst": "not_licensed"}}
        assert sc.strip_analyst_fields(row) == {"Ticker": "A.BR", "Price": 10.0,
                                                "fv_dark_reasons": {"analyst": "not_licensed"}}
        assert "targetMeanPrice" in row                       # not mutated
        cache = {"A.BR": dict(row), "B.BR": {"Price": 5.0, "targetLowPrice": 4.0}}
        stripped = sc.strip_analyst_fields(cache)
        assert stripped["B.BR"] == {"Price": 5.0}
        assert "targetMeanPrice" not in stripped["A.BR"]
        df = sc.strip_analyst_fields(_universe(3))
        assert not set(sc.ANALYST_FIELDS) & set(df.columns)


class TestPeerIndependence:
    """PER-1 / PER-2: a stock's signal never depends on who is looking."""

    def _with_user_extras(self):
        public = _universe(30)
        extras = _universe(6, seed=99, prefix="U")
        extras["Price"] *= 0.2          # deep "discounts" that would top the MoS ranks
        extras["returnOnEquity"] = 0.6  # ...and the quality ranks
        return public, pd.concat([public, extras], ignore_index=True)

    def test_without_a_mask_user_extras_would_move_public_scores(self):
        """Why the mask exists: unmasked, every row is a peer, so one user's
        manual tickers change everyone else's scores (the pre-v2.1.0 bug)."""
        public, combined = self._with_user_extras()
        a = sc.compute_scores(public.copy(), computed_at=_NOW).set_index("Ticker")["Value Score"]
        b = sc.compute_scores(combined.copy(), computed_at=_NOW).set_index("Ticker")["Value Score"]
        assert not np.allclose(a, b.loc[a.index])

    def test_peer_mask_keeps_public_scores_fixed(self):
        public, combined = self._with_user_extras()
        a = sc.compute_scores(public.copy(), computed_at=_NOW).set_index("Ticker")
        mask = sc.peer_mask_for(combined, public["Ticker"])
        b = sc.compute_scores(combined.copy(), peer_mask=mask, computed_at=_NOW).set_index("Ticker")
        for col in ("fair_value", "Value Score", "signal_code"):
            pd.testing.assert_series_equal(a[col], b.loc[a.index, col])
        assert b.loc[[t for t in b.index if t.startswith("U")], "signal_code"].ne(sc.SIGNAL_PENDING).all()

    def test_peer_mask_survives_rows_without_a_price(self):
        public, combined = self._with_user_extras()
        combined.loc[0, "Price"] = None    # dropped by _score_and_clean, index reset
        mask = sc.peer_mask_for(combined, public["Ticker"])
        out = sc.run_screener_from_df(combined, peer_mask=mask).set_index("Ticker")
        ref = sc.run_screener_from_df(combined[combined["Ticker"].isin(public["Ticker"])]).set_index("Ticker")
        pd.testing.assert_series_equal(out.loc[ref.index, "Value Score"], ref["Value Score"])

    def test_user_selected_set_without_reference_gets_no_ranked_signal(self):
        holdings = _universe(8, prefix="H")
        holdings.loc[0, "debtToEquity"] = 5000.0          # a veto still shows
        out = sc.compute_scores(holdings, user_selected=True, computed_at=_NOW).set_index("Ticker")
        assert out.loc["H0.BR", "signal_code"] == sc.SIGNAL_FAILS
        rest = out.drop(index="H0.BR")
        assert (rest["signal_code"] == sc.SIGNAL_PENDING).all()
        assert rest["Value Score"].isna().all()
        assert rest["fair_value"].notna().all()           # fair values are not rank-based

    def test_user_selected_fair_values_ignore_the_other_holdings(self):
        """PER-1: on the cold-start path, sector P/E and P/B medians of the
        user's own holdings must not set anyone's fair value. Eight holdings
        in one sector is enough for a sector median (MIN_SECTOR_SAMPLE)."""
        holdings = _universe(8, prefix="H")
        holdings["sector"] = "Technology"
        other = holdings.copy()
        other.loc[1:, "trailingPE"] *= 3.0       # the *other* holdings get pricier
        other.loc[1:, "bookValue"] /= 3.0
        a = sc.compute_scores(holdings.copy(), user_selected=True, computed_at=_NOW).set_index("Ticker")
        b = sc.compute_scores(other.copy(), user_selected=True, computed_at=_NOW).set_index("Ticker")
        for col in ("pe_fair_value", "pb_fair_value", "fair_value", "margin_of_safety"):
            assert a.loc["H0.BR", col] == pytest.approx(b.loc["H0.BR", col], nan_ok=True), col
        # ...whereas a public-universe pass does use the peers' medians
        pa = sc.compute_scores(holdings.copy(), computed_at=_NOW).set_index("Ticker")
        pb = sc.compute_scores(other.copy(), computed_at=_NOW).set_index("Ticker")
        assert pa.loc["H0.BR", "fair_value"] != pytest.approx(pb.loc["H0.BR", "fair_value"])

    def test_public_universe_flag(self):
        public, combined = self._with_user_extras()
        mask = sc.peer_mask_for(combined, public["Ticker"])
        out = sc.compute_scores(combined, peer_mask=mask, computed_at=_NOW).set_index("Ticker")
        assert out.loc[public["Ticker"], "public_universe"].all()
        assert not out.loc[[t for t in out.index if t.startswith("U")], "public_universe"].any()
        held = sc.compute_scores(_universe(8, prefix="H"), user_selected=True, computed_at=_NOW)
        assert not held["public_universe"].any()

    def test_user_selected_set_with_reference_matches_the_universe(self):
        universe = _universe(30)
        ref_out: dict = {}
        full = sc.compute_scores(universe.copy(), reference_out=ref_out, computed_at=_NOW).set_index("Ticker")
        held = universe.iloc[[2, 5, 11]].copy()
        out = sc.compute_scores(held, reference=ref_out["ref"], user_selected=True,
                                computed_at=_NOW).set_index("Ticker")
        for col in ("Value Score", "signal_code"):
            pd.testing.assert_series_equal(out[col], full.loc[out.index, col])

    def test_no_reference_is_exported_from_a_user_selected_pass(self):
        ref_out: dict = {}
        sc.compute_scores(_universe(8), user_selected=True, reference_out=ref_out, computed_at=_NOW)
        assert "ref" not in ref_out


class TestProvenance:
    """REC-3 / REC-4 / REC-11."""

    def test_columns_present_on_every_row(self):
        out = sc.compute_scores(_universe(10), computed_at=_NOW)
        assert (out["signal_computed_at"] == _NOW.isoformat(timespec="seconds")).all()
        assert out["price_as_of"].notna().all()
        assert (out["model_version"] == sc.MODEL_VERSION).all()
        assert (out["data_source"] == sc.DATA_SOURCE).all()
        assert out["model_settings_id"].nunique() == 1

    def test_stale_and_missing_price_timestamps_are_flagged(self):
        df = _universe(25)
        df.loc[0, "fetched_at"] = (_NOW - timedelta(hours=sc.PRICE_STALE_HOURS + 1)).isoformat()
        df.loc[1, "fetched_at"] = None
        out = sc.compute_scores(df, computed_at=_NOW).set_index("Ticker")
        assert "price_stale" in out.loc["P0.BR", "data_flags"]
        assert "price_missing_timestamp" in out.loc["P1.BR", "data_flags"]
        assert "price_stale" not in out.loc["P2.BR", "data_flags"]

    def test_small_peer_group_is_flagged(self):
        out = sc.compute_scores(_universe(5), computed_at=_NOW)
        assert all("small_peer_group" in f for f in out["data_flags"])

    def test_settings_id_tracks_the_settings(self):
        base = dict(max_debt_equity=500.0, max_payout=0.9, min_mos=0.0, buy_threshold=70.0,
                    weights=(0.24, 0.22, 0.24, 0.15, 0.15))
        assert sc.model_settings_id(**base) == sc.model_settings_id(**base)
        assert sc.model_settings_id(**base) != sc.model_settings_id(**{**base, "buy_threshold": 75.0})

    def test_signal_records_are_json_safe(self):
        import json
        recs = sc.signal_records(sc.compute_scores(_universe(10), computed_at=_NOW))
        assert len(recs) == 10
        json.dumps(recs)
        assert {"signal_code", "model_version", "model_settings_id", "fair_value"} <= set(recs[0])


class TestQualityScreenRules:
    """REC-2 / BDG-3: a failed screen names the rule it failed."""

    def test_veto_rules_name_the_rule(self):
        df = _universe(25)
        df.loc[0, "debtToEquity"] = 5000.0
        df.loc[1, "averageVolume"] = 0.0
        df["revenueHistory"] = None
        df["revenueHistory"] = df["revenueHistory"].astype(object)
        df.at[2, "revenueHistory"] = [70.0, 80.0, 90.0, 100.0]
        out = sc.compute_scores(df, computed_at=_NOW).set_index("Ticker")
        assert out.loc["P0.BR", "veto_rules"][0] == sc.VETO_RULE_DEBT_EQUITY
        assert sc.VETO_RULE_NO_VOLUME in out.loc["P1.BR", "veto_rules"]
        assert sc.VETO_RULE_REVENUE_DECLINE in out.loc["P2.BR", "veto_rules"]
        assert (out["veto_rules"].map(bool) == out["veto"]).all()
        assert "debt-to-equity" in sc.signal_reason(out.loc["P0.BR"])

    def test_every_rule_has_a_label(self):
        codes = {v for k, v in vars(sc).items() if k.startswith("VETO_RULE_") and isinstance(v, str)}
        assert codes == set(sc.VETO_RULE_LABELS)


class TestFounderDisclosure:
    """REC-8: any founder position is flagged, and only flagged."""

    def test_flag_is_set_and_moves_nothing(self):
        df = _universe(25)
        a = sc.compute_scores(df.copy(), computed_at=_NOW).set_index("Ticker")
        b = sc.compute_scores(df.copy(), founder_holdings={"P3.BR"}, computed_at=_NOW).set_index("Ticker")
        assert b["founder_holds"].sum() == 1 and b.loc["P3.BR", "founder_holds"]
        assert not a["founder_holds"].any()
        for col in ("fair_value", "Value Score", "signal_code", "model_settings_id"):
            pd.testing.assert_series_equal(a[col], b.loc[a.index, col])
        assert "founder_holds" in sc.signal_records(b.reset_index())[0]

    def test_load_founder_holdings(self, tmp_path):
        path = tmp_path / "founder.json"
        assert sc.load_founder_holdings(path) == frozenset()
        path.write_text('{"updated": "2026-10-04", "tickers": ["ABI.BR", " KBC.BR "]}', encoding="utf-8")
        assert sc.load_founder_holdings(path) == {"ABI.BR", "KBC.BR"}
        path.write_text('{"tickers": "ABI.BR"}', encoding="utf-8")
        with pytest.raises(ValueError):
            sc.load_founder_holdings(path)


class TestMethodologyAndDistribution:
    """REC-5 / REC-6 / REC-10."""

    def test_methodology_reports_the_live_thresholds(self):
        m = sc.methodology(min_mos=0.15, buy_threshold=72.0)
        assert m["thresholds"]["undervalued_min_score"] == 72.0
        assert m["thresholds"]["undervalued_min_margin_of_safety"] == 0.15
        assert m["thresholds"]["low_score_below"] == sc.SCORE_AVOID
        assert "analyst_target" not in m["fair_value"]["model_base_weights"]
        assert set(m["signals"]) == set(sc.SIGNAL_LABELS)
        assert m["risk_warning"] and m["horizon"] and m["sensitivity"]

    def test_distribution_sums_to_one_and_skips_pending(self):
        out = sc.compute_scores(_universe(30), computed_at=_NOW)
        dist = sc.signal_distribution(out)
        assert sum(dist.values()) == pytest.approx(1.0)
        assert sc.SIGNAL_PENDING not in dist


_ADVICE_WORDS = re.compile(r"\b(buy|sell|avoid|advice|advis[eo]r?|recommend\w*|should|you)\b", re.I)


class TestWording:
    """BDG-1 / DIS-6: signal labels, definitions and reasons are descriptive."""

    def test_labels_and_definitions(self):
        for text in [*sc.SIGNAL_LABELS.values(), *sc.SIGNAL_DEFINITIONS.values()]:
            assert not _ADVICE_WORDS.search(str(text)), text

    def test_signal_reason_strings(self):
        literals = re.findall(r'_\("([^"]*)"', inspect.getsource(sc.signal_reason))
        assert literals
        for text in literals:
            assert not _ADVICE_WORDS.search(text), text

    def test_signal_reason_covers_every_state(self):
        out = sc.compute_scores(_universe(30), computed_at=_NOW)
        for _, row in out.iterrows():
            assert sc.signal_reason(row, buy_threshold=70.0, min_mos=0.0)


# ══════════════════════════════════════════════════════════════════════════════
# Signal history (REC-7)
# ══════════════════════════════════════════════════════════════════════════════

def _rec(code="neutral", at=_NOW, **kw):
    return {"Ticker": "A.BR", "signal_code": code, "signal_computed_at": at.isoformat(),
            "public_universe": True, "model_version": "v1", "model_settings_id": "s1", **kw}


class TestSignalHistory:
    def test_only_changes_are_logged_and_pending_never(self, tmp_path):
        path = tmp_path / "h.jsonl"
        assert signal_history.record_changes([_rec()], path) == 1
        assert signal_history.record_changes([_rec()], path) == 0
        assert signal_history.record_changes([_rec("pending")], path) == 0
        assert signal_history.record_changes([_rec("undervalued")], path) == 1
        hist = signal_history.history_for("A.BR", path, now=_NOW)
        assert [h["signal_code"] for h in hist] == ["neutral", "undervalued"]
        assert [h["log_reason"] for h in hist] == ["first", "signal_change"]

    def test_model_or_settings_change_is_logged_but_not_shown_as_a_badge_change(self, tmp_path):
        path = tmp_path / "h.jsonl"
        signal_history.record_changes([_rec()], path)
        assert signal_history.record_changes([_rec(model_settings_id="s2")], path) == 1
        assert signal_history.record_changes([_rec(model_settings_id="s2", model_version="v2")], path) == 1
        assert len(signal_history.history_for("A.BR", path, now=_NOW)) == 1
        full = signal_history.history_for("A.BR", path, now=_NOW, signal_changes_only=False)
        assert [h["log_reason"] for h in full] == ["first", "model_change", "model_change"]

    def test_user_rows_never_reach_the_shared_log(self, tmp_path):
        path = tmp_path / "h.jsonl"
        assert signal_history.record_changes([_rec(public_universe=False)], path) == 0
        assert signal_history.record_changes([{k: v for k, v in _rec().items()
                                                if k != "public_universe"}], path) == 0
        assert not path.exists()

    def test_end_to_end_with_a_masked_universe(self, tmp_path):
        public = _universe(25)
        combined = pd.concat([public, _universe(3, seed=7, prefix="U")], ignore_index=True)
        out = sc.compute_scores(combined, peer_mask=sc.peer_mask_for(combined, public["Ticker"]),
                                computed_at=_NOW)
        path = tmp_path / "h.jsonl"
        assert signal_history.record_changes(sc.signal_records(out), path) == 25
        assert not any(t.startswith("U") for t in signal_history.last_signals(path))

    def test_history_window(self, tmp_path):
        path = tmp_path / "h.jsonl"
        signal_history.record_changes([_rec(at=_NOW - timedelta(days=400))], path)
        assert signal_history.history_for("A.BR", path, now=_NOW) == []
        assert len(signal_history.history_for("A.BR", path, days=500, now=_NOW)) == 1

    def test_torn_line_does_not_hide_history(self, tmp_path):
        path = tmp_path / "h.jsonl"
        signal_history.record_changes([_rec()], path)
        with path.open("a", encoding="utf-8") as fh:
            fh.write('{"Ticker": "A.BR", "sig')
        assert signal_history.last_signals(path) == {"A.BR": "neutral"}

    def test_daily_snapshot_once_per_day_public_only(self, tmp_path):
        day = _NOW.date()
        recs = [_rec(), _rec(Ticker="U.BR", public_universe=False)]
        assert signal_history.write_daily_snapshot(recs, day=day, directory=tmp_path) is not None
        assert signal_history.write_daily_snapshot([_rec("undervalued")], day=day, directory=tmp_path) is None
        snap = signal_history.read_snapshot(day, directory=tmp_path)
        assert [r["Ticker"] for r in snap] == ["A.BR"] and snap[0]["signal_code"] == "neutral"
        assert signal_history.read_snapshot(day - timedelta(days=1), directory=tmp_path) == []


class TestSettingsAudit:
    """REC-9 / REC-11: evidence for the founder's trading blackout."""

    def test_settings_diff_logs_one_event_per_changed_key(self, tmp_path):
        path = tmp_path / "a.jsonl"
        before = {"min_mos": 0.0, "buy_threshold": 70.0, "screen_style": "balanced"}
        after = {**before, "min_mos": 10.0, "screen_style": "income"}
        assert settings_audit.record_settings_change("admin@x", before, after, at=_NOW, path=path) == 2
        assert settings_audit.record_settings_change("admin@x", after, after, path=path) == 0
        ev = settings_audit.read_log(path, event=settings_audit.EVENT_SETTING)
        assert {(e["key"], e["old"], e["new"]) for e in ev} == {("min_mos", 0.0, 10.0),
                                                              ("screen_style", "balanced", "income")}
        assert all(e["actor"] == "admin@x" and e["at"] == _NOW.isoformat(timespec="seconds") for e in ev)

    def test_model_version_logged_on_change_only(self, tmp_path):
        path = tmp_path / "a.jsonl"
        assert settings_audit.record_model_version("v1", "s1", path=path)
        assert not settings_audit.record_model_version("v1", "s1", path=path)
        assert settings_audit.record_model_version("v1", "s2", path=path)
        assert len(settings_audit.read_log(path, event=settings_audit.EVENT_MODEL_VERSION)) == 2

    def test_planned_change(self, tmp_path):
        path = tmp_path / "a.jsonl"
        settings_audit.record_planned_change("admin@x", "raise min_mos to 10%", at=_NOW, path=path)
        (ev,) = settings_audit.read_log(path)
        assert ev["event"] == settings_audit.EVENT_PLANNED and ev["description"].startswith("raise")


# ══════════════════════════════════════════════════════════════════════════════
# Risk
# ══════════════════════════════════════════════════════════════════════════════

_PRESCRIPTIVE = re.compile(
    r"\b(trim|reduce|rotate|replace|redeploy|exit\w*|sell\w*|buy\w*|favou?r|consider|should|"
    r"immediate\w*|required|rebalanc\w*|diversify|avoid|add\b|top up|hold\b|review\b|monitor\w*|"
    r"size the|accept)\b", re.I)


def _string_literals(obj) -> list[str]:
    src = inspect.getsource(obj) if not isinstance(obj, str) else obj
    return re.findall(r'"([^"\n]{12,})"', src)


class TestRiskWording:
    """PER-4: describe, never prescribe."""

    def test_band_descriptions(self):
        for _upper, label, description, _tone in risk.RISK_BANDS:
            assert not _PRESCRIPTIVE.search(description), description

    def test_every_stage8_message(self):
        literals = [t for t in _string_literals(risk._stage8_observations)
                    if "{" in t or " " in t]
        assert len(literals) > 15
        for text in literals:
            assert not _PRESCRIPTIVE.search(text), text

    def test_observation_has_no_action_field(self):
        assert "action" not in risk.RiskObservation.__dataclass_fields__
        assert "action" not in risk.CompositeScore.__dataclass_fields__


def _patch_history(monkeypatch, tickers):
    idx = pd.bdate_range("2023-01-02", periods=300)
    rng = np.random.default_rng(11)
    frame = pd.DataFrame({t: 100 * np.cumprod(1 + rng.normal(0, 0.015, len(idx))) for t in tickers},
                         index=idx)
    monkeypatch.setattr(risk, "_fetch_history", lambda tks, period="5y", f=frame: f)
    monkeypatch.setattr(risk, "_fetch_ff_csv",
                        lambda url: (_ for _ in ()).throw(ConnectionError("offline")))
    monkeypatch.setattr(marketdata, "fx_to_eur_frame", lambda *a, **k: pd.DataFrame())


def _portfolio():
    rows = [("BIG.BR", 6000.0, "Technology"), ("B.BR", 1500.0, "Technology"),
            ("C.BR", 1500.0, "Industrials"), ("D.BR", 1000.0, "Utilities")]
    pf = pd.DataFrame([{"ticker": t, "name": t, "current_value": v, "shares": v / 100,
                        "live_price": 100.0, "sector": s, "country": "Belgium",
                        "expected_annual": 0.0, "fair_value": 80.0} for t, v, s in rows])
    cache = {t: {"Currency": "EUR", "beta": 1.2, "debtToEquity": 900.0} for t, _, _ in rows}
    return pf, cache


class TestRiskEquivalenceAndRules:
    def test_weightings_move_only_the_composite(self, monkeypatch):
        pf, cache = _portfolio()
        _patch_history(monkeypatch, pf["ticker"].tolist() + [risk.BENCHMARK_TICKER])
        std = risk.assess_portfolio(pf, cache, weighting="standard")
        inc = risk.assess_portfolio(pf, cache, weighting="income_weighted")
        assert std.concentration.hhi == inc.concentration.hhi
        assert [p.rating for p in std.position_profiles] == [p.rating for p in inc.position_profiles]
        assert (std.composite.weighting, inc.composite.weighting) == ("standard", "income_weighted")

    def test_held_veto_is_not_turned_into_an_observation(self, monkeypatch):
        """PER-5: the pre-v2.1.0 risk.py paired a held stock's veto with
        'consider reducing or exiting'; no observation mentions the veto now."""
        pf, cache = _portfolio()
        _patch_history(monkeypatch, pf["ticker"].tolist() + [risk.BENCHMARK_TICKER])
        vetoes = {t: True for t in pf["ticker"]}
        rep = risk.assess_portfolio(pf, cache, veto_lookup=vetoes)
        assert not any("veto" in str(i.message) for i in rep.observations.items)

    def test_user_targets_are_marked_as_user_basis(self, monkeypatch):
        pf, cache = _portfolio()
        _patch_history(monkeypatch, pf["ticker"].tolist() + [risk.BENCHMARK_TICKER])
        rep = risk.assess_portfolio(pf, cache, targets={"tickers": {"BIG.BR": 0.30},
                                                                  "hhi_max": 0.20})
        user = [i for i in rep.observations.items if i.basis == "user_target"]
        assert {i.scope for i in user} >= {"BIG.BR", "Portfolio"}

    def test_disclosures_ship_with_the_report(self, monkeypatch):
        pf, cache = _portfolio()
        _patch_history(monkeypatch, pf["ticker"].tolist() + [risk.BENCHMARK_TICKER])
        rep = risk.assess_portfolio(pf, cache)
        assert any("estimates" in str(d) for d in rep.disclosures)

    def test_unknown_weighting_is_rejected(self):
        pf, cache = _portfolio()
        with pytest.raises(ValueError):
            risk.assess_portfolio(pf, cache, weighting="retirement")

    def test_position_flags_name_the_comparison(self, monkeypatch):
        pf, cache = _portfolio()
        _patch_history(monkeypatch, pf["ticker"].tolist() + [risk.BENCHMARK_TICKER])
        rep = risk.assess_portfolio(pf, cache)
        assert {p.valuation_flag for p in rep.position_profiles} == {"Above model fair value"}
