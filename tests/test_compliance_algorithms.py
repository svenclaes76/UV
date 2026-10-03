"""
Legal-compliance copies of the algorithms — screener_compliant.py,
risk_compliant.py, signal_history.py (docs/legal/algorithm-compliance-review.md).

Two kinds of check:
  • equivalence — with the compliance-only switches neutralised, the copies
    compute exactly what screener.py / risk.py compute, so the copies change
    what is said, not what is calculated;
  • requirement — each requirement ID the copies claim to meet (PER-1/2/4/5,
    BDG-1/3, REC-3/4/5/7/10/11, DATA-6, DIS-3) is pinned by a test.

All offline: synthetic frames, monkeypatched price history and factor data.
"""

import inspect
import re
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

import marketdata
import risk
import risk_compliant
import screener
import screener_compliant as sc
import signal_history


@pytest.fixture(autouse=True)
def _isolate_factor_cache(tmp_path, monkeypatch):
    for mod in (risk, risk_compliant):
        monkeypatch.setattr(mod, "_FACTORS_DIR", tmp_path / "factors")
        monkeypatch.setattr(mod, "_ff_cache", {})


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


_DECISION_TO_CODE = {"Strong Buy": sc.SIGNAL_UNDERVALUED, "Monitor": sc.SIGNAL_NEUTRAL}


def _expected_code(row) -> str:
    if row["veto"]:
        return sc.SIGNAL_FAILS
    return _DECISION_TO_CODE.get(row["Decision"], sc.SIGNAL_LOW_SCORE)


# ══════════════════════════════════════════════════════════════════════════════
# Screener copy — equivalence
# ══════════════════════════════════════════════════════════════════════════════

class TestScreenerEquivalence:
    def test_same_numbers_and_mapped_signals_with_analyst_inputs_on(self, monkeypatch):
        """With the DATA-6 switch on and no peer mask, the copy is screener.py
        with renamed outputs: identical fair values and scores, and each
        Decision maps one-to-one onto a signal_code."""
        monkeypatch.setattr(sc, "ANALYST_INPUTS_ENABLED", True)
        df = _universe()
        orig = screener.compute_scores(df.copy()).set_index("Ticker")
        copy = sc.compute_scores(df.copy(), computed_at=_NOW).set_index("Ticker")
        for col in ("fair_value", "Value Score", "margin_of_safety", "Sub MoS", "Sub Risk"):
            pd.testing.assert_series_equal(copy[col], orig.loc[copy.index, col], check_names=False)
        expected = orig.loc[copy.index].apply(_expected_code, axis=1)
        assert copy["signal_code"].tolist() == expected.tolist()
        pd.testing.assert_series_equal(copy["Implied Return % (est.)"],
                                       orig.loc[copy.index, "TER %"], check_names=False)

    def test_no_decision_column_and_descriptive_labels(self):
        out = sc.compute_scores(_universe(), computed_at=_NOW)
        assert "Decision" not in out.columns
        assert set(out["Signal"]) <= set(sc.SIGNAL_LABELS.values())
        assert not {"Strong Buy", "Monitor", "Avoid"} & set(out["Signal"])


# ══════════════════════════════════════════════════════════════════════════════
# Screener copy — requirements
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


class TestPeerIndependence:
    """PER-1 / PER-2: a stock's signal never depends on who is looking."""

    def _with_user_extras(self):
        public = _universe(30)
        extras = _universe(6, seed=99, prefix="U")
        extras["Price"] *= 0.2          # deep "discounts" that would top the MoS ranks
        extras["returnOnEquity"] = 0.6  # ...and the quality ranks
        return public, pd.concat([public, extras], ignore_index=True)

    def test_original_screener_lets_user_extras_move_public_scores(self):
        """The finding: screener.py ranks every row it is given, so one user's
        manual tickers change everyone else's scores."""
        public, combined = self._with_user_extras()
        a = screener.compute_scores(public.copy()).set_index("Ticker")["Value Score"]
        b = screener.compute_scores(combined.copy()).set_index("Ticker")["Value Score"]
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

class TestSignalHistory:
    def test_only_changes_are_logged_and_pending_never(self, tmp_path):
        path = tmp_path / "h.jsonl"
        r = {"Ticker": "A.BR", "signal_code": "neutral", "signal_computed_at": _NOW.isoformat()}
        assert signal_history.record_changes([r], path) == 1
        assert signal_history.record_changes([r], path) == 0
        assert signal_history.record_changes([{**r, "signal_code": "pending"}], path) == 0
        assert signal_history.record_changes([{**r, "signal_code": "undervalued"}], path) == 1
        assert [h["signal_code"] for h in signal_history.history_for("A.BR", path, now=_NOW)] == \
            ["neutral", "undervalued"]

    def test_history_window(self, tmp_path):
        path = tmp_path / "h.jsonl"
        old = (_NOW - timedelta(days=400)).isoformat()
        signal_history.record_changes([{"Ticker": "A.BR", "signal_code": "neutral",
                                        "signal_computed_at": old}], path)
        assert signal_history.history_for("A.BR", path, now=_NOW) == []
        assert len(signal_history.history_for("A.BR", path, days=500, now=_NOW)) == 1

    def test_torn_line_does_not_hide_history(self, tmp_path):
        path = tmp_path / "h.jsonl"
        signal_history.record_changes([{"Ticker": "A.BR", "signal_code": "neutral",
                                        "signal_computed_at": _NOW.isoformat()}], path)
        with path.open("a", encoding="utf-8") as fh:
            fh.write('{"Ticker": "A.BR", "sig')
        assert signal_history.last_signals(path) == {"A.BR": "neutral"}


# ══════════════════════════════════════════════════════════════════════════════
# Risk copy
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
        for _upper, label, description, _tone in risk_compliant.RISK_BANDS:
            assert not _PRESCRIPTIVE.search(description), description

    def test_every_stage8_message(self):
        literals = [t for t in _string_literals(risk_compliant._stage8_observations)
                    if "{" in t or " " in t]
        assert len(literals) > 15
        for text in literals:
            assert not _PRESCRIPTIVE.search(text), text

    def test_original_stage8_does_prescribe(self):
        """The finding this copy fixes, pinned so the contrast stays visible."""
        assert any(_PRESCRIPTIVE.search(t) for t in _string_literals(risk._stage8_rebalance))

    def test_observation_has_no_action_field(self):
        assert "action" not in risk_compliant.RiskObservation.__dataclass_fields__
        assert "action" not in risk_compliant.CompositeScore.__dataclass_fields__


def _patch_history(monkeypatch, tickers):
    idx = pd.bdate_range("2023-01-02", periods=300)
    rng = np.random.default_rng(11)
    frame = pd.DataFrame({t: 100 * np.cumprod(1 + rng.normal(0, 0.015, len(idx))) for t in tickers},
                         index=idx)
    for mod in (risk, risk_compliant):
        monkeypatch.setattr(mod, "_fetch_history", lambda tks, period="5y", f=frame: f)
        monkeypatch.setattr(mod, "_fetch_ff_csv",
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
    @pytest.mark.parametrize("weighting,income", [("standard", False), ("income_weighted", True)])
    def test_same_numbers_as_risk_py(self, monkeypatch, weighting, income):
        pf, cache = _portfolio()
        _patch_history(monkeypatch, pf["ticker"].tolist() + [risk.BENCHMARK_TICKER])
        orig = risk.assess_portfolio(pf, cache, income)
        copy = risk_compliant.assess_portfolio(pf, cache, weighting=weighting)
        assert copy.composite.score == orig.composite.score
        assert copy.composite.label == orig.composite.label
        assert copy.composite.sub_scores == orig.composite.sub_scores
        assert copy.quant.volatility_annual == orig.quant.volatility_annual
        assert copy.concentration.hhi == orig.concentration.hhi
        assert [p.rating for p in copy.position_profiles] == [p.rating for p in orig.position_profiles]

    def test_held_veto_is_not_turned_into_an_observation(self, monkeypatch):
        """PER-5: risk.py pairs a held stock's veto with 'consider reducing or
        exiting'; the copy does not observe the veto at all."""
        pf, cache = _portfolio()
        _patch_history(monkeypatch, pf["ticker"].tolist() + [risk.BENCHMARK_TICKER])
        vetoes = {t: True for t in pf["ticker"]}
        orig = risk.assess_portfolio(pf, cache, False, vetoes)
        copy = risk_compliant.assess_portfolio(pf, cache, veto_lookup=vetoes)
        assert any("veto" in str(i.message) for i in orig.rebalance.items)
        assert not any("veto" in str(i.message) for i in copy.observations.items)

    def test_user_targets_are_marked_as_user_basis(self, monkeypatch):
        pf, cache = _portfolio()
        _patch_history(monkeypatch, pf["ticker"].tolist() + [risk.BENCHMARK_TICKER])
        rep = risk_compliant.assess_portfolio(pf, cache, targets={"tickers": {"BIG.BR": 0.30},
                                                                  "hhi_max": 0.20})
        user = [i for i in rep.observations.items if i.basis == "user_target"]
        assert {i.scope for i in user} >= {"BIG.BR", "Portfolio"}

    def test_disclosures_ship_with_the_report(self, monkeypatch):
        pf, cache = _portfolio()
        _patch_history(monkeypatch, pf["ticker"].tolist() + [risk.BENCHMARK_TICKER])
        rep = risk_compliant.assess_portfolio(pf, cache)
        assert any("estimates" in str(d) for d in rep.disclosures)

    def test_unknown_weighting_is_rejected(self):
        pf, cache = _portfolio()
        with pytest.raises(ValueError):
            risk_compliant.assess_portfolio(pf, cache, weighting="retirement")

    def test_position_flags_name_the_comparison(self, monkeypatch):
        pf, cache = _portfolio()
        _patch_history(monkeypatch, pf["ticker"].tolist() + [risk.BENCHMARK_TICKER])
        rep = risk_compliant.assess_portfolio(pf, cache)
        assert {p.valuation_flag for p in rep.position_profiles} == {"Above model fair value"}
