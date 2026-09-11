"""
Tests for tools/valuation_audit.py — see docs/valuation_audit_plan.md §2.8.

Each check function gets a positive fixture (fires on the shape it's meant to
catch) and a negative fixture (does not fire on the corresponding real
counterexample — tools/valuation_audit_fixtures.py's §2.7 falsifying-fixture
data serves directly as these negative cases). Aggregation, severity tiering,
and the suppression-log diff logic are tested independently of any one check.
"""
import json

import pandas as pd
import pytest

from tools import valuation_audit as va
from tools import valuation_audit_fixtures as fx


def _df(*rows):
    return pd.DataFrame(list(rows))


# ══════════════════════════════════════════════════════════════════════════
# Basis-integrity checks
# ══════════════════════════════════════════════════════════════════════════

class TestImpliedPtbFloor:
    def test_fires_on_snb_shaped_row(self):
        df = _df(fx.SNB_LEGITIMATE_LOW_SHARE_COUNT)
        hits = va.check_implied_ptb_floor(df)
        assert bool(hits.iloc[0]) is True

    def test_leaves_normal_ptb_alone(self):
        df = _df({"Price": 50.0, "bookValue": 40.0})
        hits = va.check_implied_ptb_floor(df)
        assert bool(hits.iloc[0]) is False

    def test_leaves_missing_book_value_alone(self):
        df = _df({"Price": 50.0, "bookValue": None})
        hits = va.check_implied_ptb_floor(df)
        assert bool(hits.iloc[0]) is False


class TestNetIncomeCrossValidation:
    def test_fires_on_corrupted_eps(self):
        # BC.MI-shaped: trailingEps wildly inconsistent with netIncomeHistory.
        df = _df({"trailingEps": 111_944.91, "sharesOutstanding": 68_000_000.0,
                  "netIncomeHistory": [135_034_000.0]})
        hits, coverage = va.check_net_income_cross_validation(df)
        assert bool(hits.iloc[0]) is True
        assert bool(coverage.iloc[0]) is True

    def test_fires_on_sign_mismatch(self):
        df = _df({"trailingEps": 17.67, "sharesOutstanding": 2_320_333.0,
                  "netIncomeHistory": [-4_824_000.0]})   # VEZ.DE-shaped
        hits, _ = va.check_net_income_cross_validation(df)
        assert bool(hits.iloc[0]) is True

    def test_leaves_alnrg_counterexample_alone(self):
        df = _df(fx.REJECTED_PE_FLOOR_COUNTEREXAMPLE)
        hits, _ = va.check_net_income_cross_validation(df)
        assert bool(hits.iloc[0]) is False

    def test_leaves_ambiguous_volatility_alone(self):
        df = _df(fx.AMBIGUOUS_NET_INCOME_ROW)
        hits, _ = va.check_net_income_cross_validation(df)
        assert bool(hits.iloc[0]) is False

    def test_coverage_false_when_fields_missing(self):
        df = _df({"trailingEps": 5.0, "sharesOutstanding": None, "netIncomeHistory": None})
        hits, coverage = va.check_net_income_cross_validation(df)
        assert bool(coverage.iloc[0]) is False
        assert bool(hits.iloc[0]) is False

    def test_near_zero_eps_is_excluded_from_coverage(self):
        # Real universe shape: a near-zero trailingEps (rounding/precision, not
        # corruption) collapses implied_ni toward 0 regardless of the true
        # value, mechanically tripping the ratio test on pure noise.
        df = _df({"trailingEps": 0.00, "sharesOutstanding": 200_116_500.0,
                  "netIncomeHistory": [46_731_000.0]})
        hits, coverage = va.check_net_income_cross_validation(df)
        assert bool(coverage.iloc[0]) is False
        assert bool(hits.iloc[0]) is False

    def test_zero_shares_is_excluded_from_coverage(self):
        # Real universe shape: the .SW duplicate-quote-line pattern
        # (sharesOutstanding == 0) collapses implied_ni to exactly 0 the same
        # mechanical way — already flagged by shares_outstanding_sanity, so
        # counting it here too would be double-counted noise, not new signal.
        df = _df({"trailingEps": 5.63, "sharesOutstanding": 0.0,
                  "netIncomeHistory": [13_984_000_000.0]})
        hits, coverage = va.check_net_income_cross_validation(df)
        assert bool(coverage.iloc[0]) is False
        assert bool(hits.iloc[0]) is False


class TestSharesOutstandingSanity:
    def test_fires_on_lispe_shaped_zero(self):
        df = _df({"sharesOutstanding": 0.0})
        hits = va.check_shares_outstanding_sanity(df)
        assert bool(hits.iloc[0]) is True

    def test_leaves_snb_legitimate_low_count_alone(self):
        df = _df(fx.SNB_LEGITIMATE_LOW_SHARE_COUNT)
        hits = va.check_shares_outstanding_sanity(df)
        assert bool(hits.iloc[0]) is False

    def test_leaves_upper_bound_counterexamples_alone(self):
        # Proves the dropped upper bound isn't secretly still enforced.
        for shares in fx.SHARES_OUTSTANDING_UPPER_BOUND_COUNTEREXAMPLES.values():
            df = _df({"sharesOutstanding": shares})
            hits = va.check_shares_outstanding_sanity(df)
            assert bool(hits.iloc[0]) is False

    def test_leaves_missing_shares_alone(self):
        df = _df({"sharesOutstanding": None})
        hits = va.check_shares_outstanding_sanity(df)
        assert bool(hits.iloc[0]) is False


# ══════════════════════════════════════════════════════════════════════════
# Signal-safety checks
# ══════════════════════════════════════════════════════════════════════════

class TestZeroVolumeVsStrongBuy:
    def test_fires(self):
        df = _df({"averageVolume": 0.0, "Decision": "Strong Buy"})
        assert bool(va.check_zero_volume_vs_strong_buy(df).iloc[0]) is True

    def test_missing_volume_does_not_fire(self):
        df = _df({"averageVolume": None, "Decision": "Strong Buy"})
        assert bool(va.check_zero_volume_vs_strong_buy(df).iloc[0]) is False

    def test_zero_volume_but_not_strong_buy_does_not_fire(self):
        df = _df({"averageVolume": 0.0, "Decision": "Avoid"})
        assert bool(va.check_zero_volume_vs_strong_buy(df).iloc[0]) is False


class TestFvBasisThinVsStrongBuy:
    def test_fires(self):
        df = _df({"fv_basis_thin": True, "Decision": "Strong Buy"})
        assert bool(va.check_fv_basis_thin_vs_strong_buy(df).iloc[0]) is True

    def test_thin_but_not_strong_buy_does_not_fire(self):
        df = _df({"fv_basis_thin": True, "Decision": "Monitor"})
        assert bool(va.check_fv_basis_thin_vs_strong_buy(df).iloc[0]) is False


class TestDecisionVetoConsistency:
    def test_fires_on_mismatch(self):
        df = _df({"veto": True, "Decision": "Monitor"})
        assert bool(va.check_decision_veto_consistency(df).iloc[0]) is True

    def test_consistent_veto_does_not_fire(self):
        df = _df({"veto": True, "Decision": "Avoid"})
        assert bool(va.check_decision_veto_consistency(df).iloc[0]) is False

    def test_no_veto_does_not_fire(self):
        df = _df({"veto": False, "Decision": "Strong Buy"})
        assert bool(va.check_decision_veto_consistency(df).iloc[0]) is False


# ══════════════════════════════════════════════════════════════════════════
# Display-correctness checks
# ══════════════════════════════════════════════════════════════════════════

class TestFairValuePriceRatio:
    def test_below_informational_band_is_none(self):
        df = _df({"Price": 100.0, "fair_value": 1_000.0})   # 10x
        tier = va.check_fair_value_price_ratio(df)
        assert pd.isna(tier.iloc[0])

    def test_tpg0_shaped_row_lands_informational_only(self):
        df = _df({"Price": 0.966, "fair_value": 22.70})   # ~23.5x, real & legitimate
        tier = va.check_fair_value_price_ratio(df)
        assert tier.iloc[0] == "informational"

    def test_notable_band(self):
        df = _df({"Price": 1.0, "fair_value": 60.0})   # 60x
        assert va.check_fair_value_price_ratio(df).iloc[0] == "notable"

    def test_critical_band(self):
        df = _df({"Price": 1.0, "fair_value": 250.0})   # 250x
        assert va.check_fair_value_price_ratio(df).iloc[0] == "critical"


class TestDividendYieldSanity:
    def test_fires_on_naitr_shaped_yield(self):
        df = _df({"dividendYield": 5.625})   # 562.5%
        assert bool(va.check_dividend_yield_sanity(df).iloc[0]) is True

    def test_normal_yield_does_not_fire(self):
        df = _df({"dividendYield": 0.035})
        assert bool(va.check_dividend_yield_sanity(df).iloc[0]) is False


# ══════════════════════════════════════════════════════════════════════════
# Falsifying fixtures (doc §2.2 catalog-integrity family / §2.7)
# ══════════════════════════════════════════════════════════════════════════

class TestFalsifyingFixtures:
    """No active check may fire on data that disproved a rejected check —
    if one of these starts failing, an active check has drifted back into
    the exact shape that was already found unsafe."""

    def test_alnrg_counterexample_clears_every_applicable_active_check(self):
        df = _df(fx.REJECTED_PE_FLOOR_COUNTEREXAMPLE)
        ni_hits, _ = va.check_net_income_cross_validation(df)
        assert bool(ni_hits.iloc[0]) is False
        assert bool(va.check_shares_outstanding_sanity(df).iloc[0]) is False

    def test_berkshire_ratio_disproves_any_shared_threshold(self):
        # Documents why no sibling-price-ratio check is in the registry: any
        # threshold low enough to catch the smallest confirmed bug ratio
        # necessarily also catches Berkshire's legitimate ratio.
        smallest_bug_ratio = min(fx.CONFIRMED_BUG_SIBLING_RATIOS.values())
        assert fx.BERKSHIRE_AB_SPLIT_RATIO > smallest_bug_ratio

    def test_shares_outstanding_upper_bound_counterexamples_stay_unflagged(self):
        for shares in fx.SHARES_OUTSTANDING_UPPER_BOUND_COUNTEREXAMPLES.values():
            df = _df({"sharesOutstanding": shares})
            assert bool(va.check_shares_outstanding_sanity(df).iloc[0]) is False


# ══════════════════════════════════════════════════════════════════════════
# Aggregation + severity (doc §2.1 step 4, §2.3)
# ══════════════════════════════════════════════════════════════════════════

class TestAggregationAndSeverity:
    def _outcome_for(self, df):
        return va.run_all_checks(df)

    def test_signal_safety_hit_is_always_critical(self):
        df = _df({"Ticker": "X", "Decision": "Strong Buy", "veto": False,
                  "averageVolume": 0.0, "fv_basis_thin": False,
                  "Price": 10.0, "fair_value": 12.0, "dividendYield": 0.02})
        findings = va.aggregate_findings(df, self._outcome_for(df))
        assert len(findings) == 1
        assert findings[0].severity == "critical"
        assert "zero_volume_vs_strong_buy" in findings[0].checks_failed

    def test_basis_integrity_hit_is_critical_when_strong_buy(self):
        row = dict(fx.SNB_LEGITIMATE_LOW_SHARE_COUNT)
        row.update({"Ticker": "SNBN.SW", "Decision": "Strong Buy", "veto": False,
                    "averageVolume": 100.0, "fv_basis_thin": False, "fair_value": None,
                    "dividendYield": None})
        df = _df(row)
        findings = va.aggregate_findings(df, self._outcome_for(df))
        assert len(findings) == 1
        assert findings[0].severity == "critical"

    def test_basis_integrity_hit_is_notable_when_not_strong_buy(self):
        row = dict(fx.SNB_LEGITIMATE_LOW_SHARE_COUNT)
        row.update({"Ticker": "SNBN.SW", "Decision": "Monitor", "veto": False,
                    "averageVolume": 100.0, "fv_basis_thin": False, "fair_value": None,
                    "dividendYield": None})
        df = _df(row)
        findings = va.aggregate_findings(df, self._outcome_for(df))
        assert len(findings) == 1
        assert findings[0].severity == "notable"

    def test_uncorroborated_display_correctness_is_informational_even_when_strong_buy(self):
        # TPG0.DE shape: real, legitimate Strong Buy at ~23.5x fair value/price,
        # no basis-integrity hit alongside it.
        df = _df({"Ticker": "TPG0.DE", "Decision": "Strong Buy", "veto": False,
                  "averageVolume": 489_489.0, "fv_basis_thin": False,
                  "Price": 0.966, "fair_value": 22.70, "bookValue": 8.465,
                  "sharesOutstanding": 24_986_493.0, "trailingEps": 2.05,
                  "netIncomeHistory": [42_016_174.0], "dividendYield": 0.0})
        findings = va.aggregate_findings(df, self._outcome_for(df))
        assert len(findings) == 1
        assert findings[0].severity == "informational"
        assert findings[0].checks_failed == ["fair_value_price_ratio"]

    def test_findings_aggregate_per_ticker_not_per_check(self):
        # A row failing two checks at once (the treasury-share shape this
        # session) produces ONE finding listing both, not two.
        df = _df({"Ticker": "NAITR.AS", "Decision": "Strong Buy", "veto": False,
                  "averageVolume": 0.0, "fv_basis_thin": True,
                  "Price": 0.04, "fair_value": 12.70, "dividendYield": 5.625})
        findings = va.aggregate_findings(df, self._outcome_for(df))
        assert len(findings) == 1
        assert set(findings[0].checks_failed) >= {
            "zero_volume_vs_strong_buy", "fv_basis_thin_vs_strong_buy", "dividend_yield_sanity",
        }

    def test_clean_row_produces_no_finding(self):
        df = _df({"Ticker": "CLEAN", "Decision": "Monitor", "veto": False,
                  "averageVolume": 500_000.0, "fv_basis_thin": False,
                  "Price": 50.0, "fair_value": 55.0, "bookValue": 40.0,
                  "dividendYield": 0.03})
        findings = va.aggregate_findings(df, self._outcome_for(df))
        assert findings == []


# ══════════════════════════════════════════════════════════════════════════
# Suppression / history log diff (doc §2.5)
# ══════════════════════════════════════════════════════════════════════════

class TestSuppressionLogDiff:
    def _finding(self, ticker="X", checks=("implied_ptb_floor",)):
        return va.Finding(ticker=ticker, decision="Strong Buy", veto=False,
                          severity="critical", checks_failed=list(checks),
                          details={c: "detail" for c in checks})

    def test_new_finding_is_shown_and_logged_with_no_disposition(self):
        shown, log, regressions = va.diff_against_log(
            [self._finding()], {}, commit="abc123", now="2026-09-12T00:00:00Z")
        assert len(shown) == 1
        assert regressions == []
        entry = log["X::implied_ptb_floor"]
        assert entry["disposition"] is None
        assert entry["commit"] == "abc123"

    def test_dismissed_false_positive_is_suppressed(self):
        log = {"X::implied_ptb_floor": {"disposition": "dismissed-false-positive",
                                        "reason": "real earnings volatility",
                                        "first_seen": "t0", "commit": "abc",
                                        "catalog_version": "v1.3", "last_confirmed": "t0"}}
        shown, updated, regressions = va.diff_against_log(
            [self._finding()], log, commit="def456", now="2026-09-13T00:00:00Z")
        assert shown == []
        assert regressions == []
        assert updated["X::implied_ptb_floor"]["last_confirmed"] == "2026-09-13T00:00:00Z"

    def test_documented_gap_is_suppressed(self):
        log = {"X::implied_ptb_floor": {"disposition": "documented-gap",
                                        "reason": "see data-contracts.md",
                                        "first_seen": "t0", "commit": "abc",
                                        "catalog_version": "v1.3", "last_confirmed": "t0"}}
        shown, _, regressions = va.diff_against_log(
            [self._finding()], log, commit="def456", now="2026-09-13T00:00:00Z")
        assert shown == []
        assert regressions == []

    def test_fixed_disposition_firing_again_is_a_regression(self):
        log = {"X::implied_ptb_floor": {"disposition": "fixed",
                                        "reason": "PTB_SANITY_FLOOR shipped",
                                        "first_seen": "t0", "commit": "abc",
                                        "catalog_version": "v1.3", "last_confirmed": "t0"}}
        shown, _, regressions = va.diff_against_log(
            [self._finding()], log, commit="def456", now="2026-09-13T00:00:00Z")
        assert len(shown) == 1
        assert regressions == ["X::implied_ptb_floor"]

    def test_pending_undispositioned_finding_still_shows(self):
        log = {"X::implied_ptb_floor": {"disposition": None, "reason": None,
                                        "first_seen": "t0", "commit": "abc",
                                        "catalog_version": "v1.3", "last_confirmed": "t0"}}
        shown, _, regressions = va.diff_against_log(
            [self._finding()], log, commit="def456", now="2026-09-13T00:00:00Z")
        assert len(shown) == 1
        assert regressions == []

    def test_ticker_disappears_from_shown_when_all_its_checks_are_suppressed(self):
        f = self._finding(checks=("implied_ptb_floor", "dividend_yield_sanity"))
        log = {
            "X::implied_ptb_floor": {"disposition": "documented-gap", "reason": "r",
                                     "first_seen": "t0", "commit": "abc",
                                     "catalog_version": "v1.3", "last_confirmed": "t0"},
            "X::dividend_yield_sanity": {"disposition": "documented-gap", "reason": "r",
                                         "first_seen": "t0", "commit": "abc",
                                         "catalog_version": "v1.3", "last_confirmed": "t0"},
        }
        shown, _, _ = va.diff_against_log([f], log, commit="def456", now="t1")
        assert shown == []

    def test_partial_suppression_keeps_only_the_undispositioned_check(self):
        f = self._finding(checks=("implied_ptb_floor", "dividend_yield_sanity"))
        log = {
            "X::implied_ptb_floor": {"disposition": "documented-gap", "reason": "r",
                                     "first_seen": "t0", "commit": "abc",
                                     "catalog_version": "v1.3", "last_confirmed": "t0"},
        }
        shown, _, _ = va.diff_against_log([f], log, commit="def456", now="t1")
        assert len(shown) == 1
        assert shown[0].checks_failed == ["dividend_yield_sanity"]


class TestSetDisposition:
    def test_records_a_new_disposition(self, tmp_path):
        log_path = tmp_path / "log.json"
        va.set_disposition("SNBN.SW", "implied_ptb_floor", "fixed",
                           "PTB_SANITY_FLOOR shipped", log_path=log_path)
        log = json.loads(log_path.read_text(encoding="utf-8"))
        entry = log["SNBN.SW::implied_ptb_floor"]
        assert entry["disposition"] == "fixed"
        assert entry["reason"] == "PTB_SANITY_FLOOR shipped"

    def test_rejects_unknown_disposition(self, tmp_path):
        with pytest.raises(ValueError):
            va.set_disposition("X", "implied_ptb_floor", "not-a-real-disposition",
                               "reason", log_path=tmp_path / "log.json")

    def test_rejects_unknown_check(self, tmp_path):
        with pytest.raises(ValueError):
            va.set_disposition("X", "not_a_real_check", "fixed",
                               "reason", log_path=tmp_path / "log.json")


# ══════════════════════════════════════════════════════════════════════════
# Regression sentinels (doc §2.6) — asserted against real cached data by
# run_sentinels() itself; here we only test the plumbing handles an absent
# sentinel ticker gracefully, without needing the real .cache/fundamentals.json.
# ══════════════════════════════════════════════════════════════════════════

class TestSentinelPlumbing:
    def test_absent_sentinel_ticker_is_skipped_not_failed(self):
        df = _df({"Ticker": "SOMETHING_ELSE", "Decision": "Monitor"}).set_index("Ticker", drop=False)
        results = va.run_sentinels(df)
        assert results == {}

    def test_naitr_sentinel_passes_when_vetoed_and_avoid(self):
        df = _df({"Ticker": "NAITR.AS", "veto": True, "Decision": "Avoid",
                  "fetched_at": "2026-09-11T00:00:00Z"}).set_index("Ticker", drop=False)
        results = va.run_sentinels(df)
        assert results["NAITR.AS"] is None

    def test_naitr_sentinel_fails_when_regressed(self):
        df = _df({"Ticker": "NAITR.AS", "veto": False, "Decision": "Strong Buy",
                  "fetched_at": "2026-09-11T00:00:00Z"}).set_index("Ticker", drop=False)
        results = va.run_sentinels(df)
        assert results["NAITR.AS"] is not None

    def test_placeholder_row_is_skipped_not_failed(self):
        # screener._fetch_and_store's pending-fetch stub: {Name, Ticker, ISIN,
        # fetched_at: ""} and nothing else — confirmed live during this
        # tool's own build (another running app instance's background
        # fetcher left NAITR.AS in exactly this state).
        df = _df({"Ticker": "NAITR.AS", "Name": "New Amsterdam Invest N.V.",
                  "ISIN": "", "fetched_at": ""}).set_index("Ticker", drop=False)
        results = va.run_sentinels(df)
        assert results == {}

    def test_missing_fetched_at_column_is_also_treated_as_placeholder(self):
        df = _df({"Ticker": "NAITR.AS", "veto": True, "Decision": "Avoid"}).set_index("Ticker", drop=False)
        results = va.run_sentinels(df)
        assert results == {}
