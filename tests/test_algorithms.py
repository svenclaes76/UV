"""
Algorithm validation suite — checks the screener (6-stage valuation) and
risk (8-stage assessment) math against hand-computed expected values.

All tests are offline: synthetic DataFrames and cache dicts, no yfinance calls.

Run:  python -m pytest tests/ -v
"""

import datetime as dt
import os

import numpy as np
import pandas as pd
import pytest

import screener
from screener import (
    _approx_wacc,
    _ddm_single,
    _ddm_multistage,
    _fair_value_models,
    _margin_of_safety,
    _total_expected_return,
    _dividend_sustainability_flag,
    _dividend_stats,
    _dgr_estimate,
    _financial_health_score,
    _earnings_quality_score,
    _market_risk_score,
    _dividend_risk_score,
    _dividend_score_raw,
    _liquidity_score,
    _quality_raw,
    _momentum_raw,
    _pct_rank,
    compute_scores,
    run_screener_from_df,
)
import risk
from risk import (
    _safe,
    _mdd,
    _hhi_label,
    _beta_label,
    _vol_label,
    _mdd_label,
    _sharpe_label,
    _sortino_label,
    _position_rating,
    _risk_label_action,
    _to_eur,
    _ols_beta,
    _resolve_betas,
    BENCHMARK_TICKER,
    assess_portfolio,
    _stage1_position_profiles,
    _stage2_concentration,
    _stage3_quant,
    _stage4_factor,
    _stage5_income,
    _stage6_stress,
    _stage8_rebalance,
    _score_fundamental,
    _fetch_ff_csv,
    PositionRisk,
    ConcentrationMetrics,
    QuantMetrics,
    IncomeRisk,
    ScenarioResult,
    MonteCarloResult,
    StressResults,
)
from prices import _day_change
import marketdata


@pytest.fixture(autouse=True)
def _isolate_factor_cache(tmp_path, monkeypatch):
    """Keep _stage4_factor's on-disk Fama-French cache out of the real
    .cache/factors, and reset the in-process URL cache between tests."""
    monkeypatch.setattr(risk, "_FACTORS_DIR", tmp_path / "factors")
    monkeypatch.setattr(risk, "_ff_cache", {})


# ══════════════════════════════════════════════════════════════════════════════
# Screener Stage 2 — fair value models
# ══════════════════════════════════════════════════════════════════════════════

class TestWacc:
    def test_normal_beta(self):
        assert _approx_wacc(1.0) == pytest.approx(0.08)   # 3% rf + 1.0 × 5% ERP
        assert _approx_wacc(2.0) == pytest.approx(0.13)

    def test_missing_or_absurd_beta_falls_back_to_default(self):
        assert _approx_wacc(None) == pytest.approx(0.08)
        assert _approx_wacc(6.0) == pytest.approx(0.08)    # out of [0.1, 5.0]
        assert _approx_wacc(0.05) == pytest.approx(0.08)


class TestGrahamAndPE:
    def test_graham_number(self):
        # sqrt(22.5 × EPS × BVPS) = sqrt(22.5 × 5 × 20) = sqrt(2250)
        fv = _fair_value_models(pd.Series({"Price": 50.0, "trailingEps": 5.0,
                                           "bookValue": 20.0}))
        assert fv["graham_number"] == pytest.approx(2250 ** 0.5)
        assert fv["pe_fair_value"] == pytest.approx(75.0)   # EPS × 15

    def test_negative_eps_gives_no_graham_or_pe(self):
        fv = _fair_value_models(pd.Series({"Price": 50.0, "trailingEps": -2.0,
                                           "bookValue": 20.0}))
        assert fv["graham_number"] is None
        assert fv["pe_fair_value"] is None


class TestDDM:
    def test_single_stage_gordon(self):
        # D1 / (wacc − g) = 2×1.02 / (0.08 − 0.02) = 34.0
        assert _ddm_single(2.0, 0.08, 0.02) == pytest.approx(34.0)

    def test_growth_clamped_to_5pct(self):
        # g=0.10 → clamped 0.05 → 2×1.05 / 0.03 = 70.0
        assert _ddm_single(2.0, 0.08, 0.10) == pytest.approx(70.0)

    def test_wacc_below_growth_returns_none(self):
        assert _ddm_single(2.0, 0.04, 0.05) is None

    def test_non_payer_returns_none(self):
        assert _ddm_single(None, 0.08, 0.02) is None
        assert _ddm_single(0.0, 0.08, 0.02) is None

    def test_multistage_matches_manual_dcf(self):
        wacc, g_high, g_stable, years, d0 = 0.08, 0.05, 0.02, 5, 2.0
        dps, expected = d0, 0.0
        for t in range(1, years + 1):
            dps *= (1 + g_high)
            expected += dps / (1 + wacc) ** t
        expected += (dps * (1 + g_stable) / (wacc - g_stable)) / (1 + wacc) ** years
        assert _ddm_multistage(d0, wacc, g_high) == pytest.approx(expected)

    def test_multistage_high_growth_clamped_to_15pct(self):
        assert _ddm_multistage(2.0, 0.08, 0.50) == pytest.approx(
            _ddm_multistage(2.0, 0.08, 0.15))

    def test_multistage_non_payer_returns_none(self):
        assert _ddm_multistage(None, 0.08, 0.05) is None
        assert _ddm_multistage(0.0, 0.08, 0.05) is None

    def test_multistage_wacc_below_terminal_growth_returns_none(self):
        assert _ddm_multistage(2.0, 0.015, 0.05) is None

    def test_zero_growth_is_respected_not_defaulted(self):
        # g=0.0 must mean zero growth (2/0.08 = 25), not the 2% missing-data default
        assert _ddm_single(2.0, 0.08, 0.0) == pytest.approx(25.0)
        assert _ddm_single(2.0, 0.08, None) == pytest.approx(34.0)   # default 2%
        assert _ddm_multistage(2.0, 0.08, 0.0) != pytest.approx(
            _ddm_multistage(2.0, 0.08, None))


class TestFairValueBlend:
    def test_weighted_average_of_available_models(self):
        # Only Graham, PE, analyst available.
        row = pd.Series({"Price": 50.0, "trailingEps": 5.0, "bookValue": 20.0,
                         "targetMeanPrice": 90.0})
        fv = _fair_value_models(row)
        gn, pe, an = 2250 ** 0.5, 75.0, 90.0 * (1 - screener.ANALYST_TARGET_HAIRCUT)
        wg, wp, wa = screener.W_GRAHAM, screener.W_PE, screener.W_ANALYST
        expected = (gn * wg + pe * wp + an * wa) / (wg + wp + wa)
        assert fv["fair_value"] == pytest.approx(expected, abs=0.01)

    def test_no_models_available(self):
        fv = _fair_value_models(pd.Series({"Price": 50.0}))
        assert fv["fair_value"] is None

    def test_ddm_excluded_when_payout_extreme(self):
        # payout 0.95 > 0.90 → DDM ineligible even though dividend exists
        row = pd.Series({"Price": 50.0, "trailingAnnualDividendRate": 2.0,
                         "payoutRatio": 0.95, "beta": 1.0})
        fv = _fair_value_models(row)
        assert fv["ddm"] is None and fv["ddm_multistage"] is None

    def test_epv_included_when_ebit_and_ev_available(self):
        row = pd.Series({"Price": 50.0, "ebit": 1_000_000.0, "enterpriseValue": 10_000_000.0,
                         "beta": 1.0})
        fv = _fair_value_models(row)
        assert fv["epv"] is not None
        assert fv["epv"] > 0

    def test_epv_none_without_ebit_or_ev(self):
        fv = _fair_value_models(pd.Series({"Price": 50.0, "beta": 1.0}))
        assert fv["epv"] is None


# ══════════════════════════════════════════════════════════════════════════════
# Screener Stage 3 — MoS, TER, dividend sustainability
# ══════════════════════════════════════════════════════════════════════════════

class TestStage3:
    def test_margin_of_safety(self):
        assert _margin_of_safety(80.0, 100.0) == pytest.approx(0.20)
        assert _margin_of_safety(120.0, 100.0) == pytest.approx(-0.20)
        assert _margin_of_safety(None, 100.0) is None
        assert _margin_of_safety(80.0, None) is None

    def test_total_expected_return(self):
        # 20% cap gain + 3% yield + 5% DGR = 28.0
        assert _total_expected_return(100.0, 120.0, 0.03, 0.05) == pytest.approx(28.0)

    def test_ter_dgr_clamped_to_10pct(self):
        assert _total_expected_return(100.0, 100.0, 0.0, 0.50) == pytest.approx(10.0)

    def test_ter_none_price_returns_none(self):
        assert _total_expected_return(None, 100.0, 0.03, 0.05) is None
        assert _total_expected_return(0.0, 100.0, 0.03, 0.05) is None

    def test_div_flag(self):
        assert _dividend_sustainability_flag(pd.Series({})) == ""          # non-payer
        assert _dividend_sustainability_flag(pd.Series(
            {"trailingAnnualDividendRate": 2.0, "payoutRatio": 0.95})) == "At Risk"
        assert _dividend_sustainability_flag(pd.Series(
            {"trailingAnnualDividendRate": 2.0, "cashPayoutRatio": 0.85})) == "At Risk"
        assert _dividend_sustainability_flag(pd.Series(
            {"trailingAnnualDividendRate": 2.0, "dividendCoverage": 1.1})) == "At Risk"
        assert _dividend_sustainability_flag(pd.Series(
            {"trailingAnnualDividendRate": 2.0, "payoutRatio": 0.50,
             "cashPayoutRatio": 0.50, "dividendCoverage": 2.0})) == "OK"

    def test_div_flag_recent_cut(self):
        this_year = dt.datetime.now(dt.timezone.utc).year
        healthy = {"trailingAnnualDividendRate": 2.0, "payoutRatio": 0.50,
                   "cashPayoutRatio": 0.50, "dividendCoverage": 2.0}
        # A cut within the last 3 complete years flags an otherwise-healthy payer…
        assert _dividend_sustainability_flag(pd.Series(
            {**healthy, "dividend_last_cut_year": this_year - 1})) == "At Risk"
        # …but an old cut does not.
        assert _dividend_sustainability_flag(pd.Series(
            {**healthy, "dividend_last_cut_year": this_year - 8})) == "OK"


# ══════════════════════════════════════════════════════════════════════════════
# Screener — dividend history stats (WS-4)
# ══════════════════════════════════════════════════════════════════════════════

class TestDividendStats:
    def _annual_series(self, year_to_dps: dict) -> pd.Series:
        # two semi-annual payments per year so groupby-year-sum reconstructs the
        # target annual DPS
        idx, vals = [], []
        for y, dps in year_to_dps.items():
            idx += [pd.Timestamp(f"{y}-03-15"), pd.Timestamp(f"{y}-09-15")]
            vals += [dps / 2, dps / 2]
        return pd.Series(vals, index=pd.to_datetime(idx))

    def test_non_payer(self, monkeypatch):
        monkeypatch.setattr(screener.marketdata, "dividends", lambda t: pd.Series(dtype=float))
        s = _dividend_stats("X", now_year=2026)
        assert s == {"true_dgr": None, "dividend_growth_streak": 0,
                     "dividend_payment_years": 0, "dividend_last_cut_year": None}

    def test_steady_grower(self, monkeypatch):
        series = self._annual_series({2020: 1.0, 2021: 1.1, 2022: 1.21,
                                      2023: 1.331, 2024: 1.4641, 2025: 1.61051})
        monkeypatch.setattr(screener.marketdata, "dividends", lambda t: series)
        s = _dividend_stats("X", now_year=2026)
        assert s["true_dgr"] == pytest.approx(0.10, abs=1e-3)      # 10%/yr CAGR
        assert s["dividend_payment_years"] == 6
        assert s["dividend_growth_streak"] == 5
        assert s["dividend_last_cut_year"] is None

    def test_detects_a_cut_and_resets_streak(self, monkeypatch):
        series = self._annual_series({2020: 1.0, 2021: 1.1, 2022: 0.7,
                                      2023: 0.8, 2024: 0.9})
        monkeypatch.setattr(screener.marketdata, "dividends", lambda t: series)
        s = _dividend_stats("X", now_year=2026)
        assert s["dividend_last_cut_year"] == 2022
        assert s["dividend_growth_streak"] == 2                    # 2023,2024 up
        assert s["true_dgr"] == pytest.approx((0.9 / 1.0) ** (1 / 4) - 1, abs=1e-4)

    def test_drops_incomplete_current_year(self, monkeypatch):
        series = self._annual_series({2023: 1.0, 2024: 1.2, 2025: 1.4, 2026: 0.3})
        monkeypatch.setattr(screener.marketdata, "dividends", lambda t: series)
        s = _dividend_stats("X", now_year=2026)
        assert s["dividend_payment_years"] == 3                    # 2026 excluded
        assert s["dividend_last_cut_year"] is None                 # the 0.3 stub ignored

    def test_single_complete_year_has_no_dgr(self, monkeypatch):
        series = self._annual_series({2025: 1.0})
        monkeypatch.setattr(screener.marketdata, "dividends", lambda t: series)
        s = _dividend_stats("X", now_year=2026)
        assert s["true_dgr"] is None and s["dividend_payment_years"] == 1

    def test_fetch_failure_returns_empty_stats(self, monkeypatch):
        def _boom(_t):
            raise RuntimeError("offline")
        monkeypatch.setattr(screener.marketdata, "dividends", _boom)
        assert _dividend_stats("X")["true_dgr"] is None


class TestDgrEstimate:
    def test_prefers_true_dgr_including_zero(self):
        assert _dgr_estimate(pd.Series({"true_dgr": 0.0, "earningsGrowth": 0.4})) == 0.0
        assert _dgr_estimate(pd.Series({"true_dgr": 0.07, "earningsGrowth": 0.4})) == 0.07

    def test_falls_back_to_earnings_growth(self):
        assert _dgr_estimate(pd.Series({"earningsGrowth": 0.05})) == 0.05
        assert _dgr_estimate(pd.Series({"true_dgr": float("nan"),
                                        "earningsGrowth": 0.05})) == 0.05

    def test_none_when_neither_present(self):
        assert _dgr_estimate(pd.Series({})) is None


# ══════════════════════════════════════════════════════════════════════════════
# Screener Stage 4 — risk dimension scores (all 0–10)
# ══════════════════════════════════════════════════════════════════════════════

class TestDimensionScores:
    def test_financial_health(self):
        # D/E 100 (=1.0×) → 7.5; CR 2.0 → 10; IC 10 → 5 → mean 7.5
        row = pd.Series({"debtToEquity": 100.0, "currentRatio": 2.0,
                         "interestCoverage": 10.0})
        assert _financial_health_score(row) == pytest.approx(7.5)
        assert _financial_health_score(pd.Series({})) == 5.0   # no data → neutral

    def test_earnings_quality(self):
        assert _earnings_quality_score(pd.Series(
            {"freeCashflow": 100.0, "netIncome": 100.0})) == pytest.approx(8.0)
        assert _earnings_quality_score(pd.Series(
            {"freeCashflow": -100.0, "netIncome": 100.0})) == pytest.approx(2.0)
        assert _earnings_quality_score(pd.Series({})) == 5.0

    def test_market_risk(self):
        assert _market_risk_score(pd.Series({"beta": 1.0})) == pytest.approx(6.5)
        assert _market_risk_score(pd.Series({"beta": 3.0})) == 0.0   # clamped
        assert _market_risk_score(pd.Series({})) == 5.0

    def test_liquidity_tiers(self):
        assert _liquidity_score(pd.Series({"averageVolume": 600_000})) == 10.0
        assert _liquidity_score(pd.Series({"averageVolume": 150_000})) == 7.5
        assert _liquidity_score(pd.Series({"averageVolume": 30_000})) == 5.0
        assert _liquidity_score(pd.Series({"averageVolume": 10_000})) == 2.5
        assert _liquidity_score(pd.Series({})) == 5.0

    def test_dividend_risk_non_payer_neutral(self):
        assert _dividend_risk_score(pd.Series({})) == 5.0

    @pytest.mark.parametrize("payout,expected", [
        (0.50, 10.0),   # sweet spot 30-70%
        (0.20, 7.0),    # low payout
        (0.80, 4.0),    # elevated but not extreme
        (0.95, 0.0),    # > 85% at risk
    ])
    def test_dividend_risk_payout_tiers(self, payout, expected):
        row = pd.Series({"trailingAnnualDividendRate": 2.0, "payoutRatio": payout})
        assert _dividend_risk_score(row) == pytest.approx(expected)

    def test_dividend_score_raw_non_payer_neutral(self):
        assert _dividend_score_raw(pd.Series({})) == 5.0

    def test_dividend_score_raw_yield_vs_average(self):
        row = pd.Series({"trailingAnnualDividendRate": 2.0,
                         "dividendYield": 0.04, "fiveYearAvgDividendYield": 0.02})
        # ratio 2x avg -> clamped to 10
        assert _dividend_score_raw(row) == pytest.approx(10.0)

    @pytest.mark.parametrize("payout,expected", [
        (0.50, 10.0), (0.20, 7.0), (0.80, 4.0), (0.95, 0.0),
    ])
    def test_dividend_score_raw_payout_tiers(self, payout, expected):
        row = pd.Series({"trailingAnnualDividendRate": 2.0, "payoutRatio": payout})
        assert _dividend_score_raw(row) == pytest.approx(expected)

    def test_dividend_score_raw_uses_cash_payout_and_coverage(self):
        row = pd.Series({"trailingAnnualDividendRate": 2.0,
                         "cashPayoutRatio": 0.3, "dividendCoverage": 3.0})
        # cpr score: 10 - 0.3*10 = 7; coverage score: clamp(3*2,0,10)=6 -> mean 6.5
        assert _dividend_score_raw(row) == pytest.approx(6.5)

    def test_all_scores_bounded_0_10(self):
        extreme = pd.Series({"debtToEquity": 900.0, "currentRatio": 0.1,
                             "interestCoverage": 0.5, "freeCashflow": -1e9,
                             "netIncome": 1e6, "beta": 4.0, "averageVolume": 100,
                             "trailingAnnualDividendRate": 5.0, "payoutRatio": 2.0,
                             "cashPayoutRatio": 3.0, "dividendCoverage": 0.1,
                             "earningsGrowth": -0.9, "returnOnEquity": -0.5,
                             "returnOnAssets": -0.3, "operatingMargins": -0.4,
                             "fcfYield": -0.2, "revenueGrowth": -0.8,
                             "recommendationMean": 5.0})
        for fn in (_financial_health_score, _earnings_quality_score,
                   _market_risk_score, _dividend_risk_score, _liquidity_score,
                   _quality_raw, _momentum_raw):
            v = fn(extreme)
            assert 0.0 <= v <= 10.0, f"{fn.__name__} out of bounds: {v}"

    def test_nan_field_scores_same_as_missing_field(self):
        # compute_scores calls these via df.apply(fn, axis=1) on a DataFrame,
        # where a field missing for this ticker (or reindexed in for schema
        # compatibility) reads as float NaN, not a missing dict key. A NaN
        # value must be treated the same as an absent one -- not silently
        # corrupt the whole np.mean(scores) to NaN for that dimension.
        present = pd.Series({
            "debtToEquity": 100.0, "currentRatio": 2.0, "interestCoverage": 10.0,
            "freeCashflow": 1e8, "netIncome": 5e7, "beta": 1.0,
            "averageVolume": 1e6, "trailingAnnualDividendRate": 2.0,
            "payoutRatio": 0.5, "cashPayoutRatio": 0.3, "dividendCoverage": 3.0,
            "earningsGrowth": 0.05, "returnOnEquity": 0.15, "returnOnAssets": 0.08,
            "operatingMargins": 0.20, "fcfYield": 0.06, "revenueGrowth": 0.04,
            "recommendationMean": 2.0, "dividendYield": 0.03,
            "fiveYearAvgDividendYield": 0.025,
        })
        # Same fields, but with a subset present-as-NaN instead of absent --
        # simulating a reindexed DataFrame row rather than a plain dict.
        nan_fields = ["interestCoverage", "fcfYield", "cashPayoutRatio",
                      "fiveYearAvgDividendYield"]
        noisy = present.copy()
        for f in nan_fields:
            noisy[f] = np.nan
        missing = present.drop(index=nan_fields)

        for fn in (_financial_health_score, _earnings_quality_score,
                   _market_risk_score, _dividend_risk_score, _liquidity_score,
                   _quality_raw, _momentum_raw, _dividend_score_raw):
            v_noisy   = fn(noisy)
            v_missing = fn(missing)
            assert not np.isnan(v_noisy), f"{fn.__name__} corrupted to NaN"
            assert v_noisy == pytest.approx(v_missing), (
                f"{fn.__name__}: NaN field ({v_noisy}) != absent field ({v_missing})")


# ══════════════════════════════════════════════════════════════════════════════
# Screener Stage 5+6 — percentile ranks, composite score, decision
# ══════════════════════════════════════════════════════════════════════════════

class TestCompositeScore:
    def test_weights_sum_to_one(self):
        assert (screener.W_MOS + screener.W_RISK + screener.W_QUALITY
                + screener.W_MOMENTUM + screener.W_DIVIDEND) == pytest.approx(1.0)

    def test_pct_rank(self):
        r = _pct_rank(pd.Series([1.0, 2.0, 3.0, np.nan]))
        assert r.iloc[0] == pytest.approx(100 / 3)
        assert r.iloc[2] == pytest.approx(100.0)
        assert r.iloc[3] == 50.0                     # NaN → neutral
        r_desc = _pct_rank(pd.Series([1.0, 2.0, 3.0]), ascending=False)
        assert r_desc.iloc[0] == pytest.approx(100 - 100 / 3)

    @pytest.fixture
    def synthetic_universe(self):
        return pd.DataFrame([
            {"Name": "Good Co", "Ticker": "GOOD", "Price": 50.0,
             "trailingEps": 5.0, "bookValue": 20.0, "targetMeanPrice": 90.0,
             "beta": 1.0, "returnOnEquity": 0.20, "returnOnAssets": 0.10,
             "operatingMargins": 0.25, "freeCashflow": 1e9, "netIncome": 8e8,
             "debtToEquity": 50.0, "currentRatio": 2.0, "averageVolume": 1e6,
             "earningsGrowth": 0.08, "revenueGrowth": 0.06,
             "recommendationMean": 2.0},
            {"Name": "Veto Co", "Ticker": "VETO", "Price": 30.0,
             "trailingEps": 3.0, "bookValue": 10.0, "targetMeanPrice": 60.0,
             "freeCashflow": -5e8, "netIncome": 1e8},          # negative FCF → veto
            {"Name": "Meh Co", "Ticker": "MEH", "Price": 100.0,
             "trailingEps": 2.0, "bookValue": 8.0, "targetMeanPrice": 80.0,
             "beta": 1.8, "debtToEquity": 300.0, "currentRatio": 0.8,
             "freeCashflow": 1e8, "netIncome": 4e8, "averageVolume": 50_000,
             "earningsGrowth": -0.10, "revenueGrowth": -0.05,
             "recommendationMean": 4.0},
            {"Name": "NoData Co", "Ticker": "NODATA", "Price": 10.0},
        ])

    def test_end_to_end_scoring(self, synthetic_universe):
        out = compute_scores(synthetic_universe)

        assert set(out["Decision"]).issubset({"Strong Buy", "Monitor", "Avoid"})
        assert out["Value Score"].between(0, 100).all()
        assert list(out["Value Score"]) == sorted(out["Value Score"], reverse=True)

        veto = out[out["Ticker"] == "VETO"].iloc[0]
        assert veto["Value Score"] == 0.0
        assert veto["Decision"] == "Avoid"
        assert bool(veto["veto"]) is True

        good = out[out["Ticker"] == "GOOD"].iloc[0]
        meh = out[out["Ticker"] == "MEH"].iloc[0]
        assert good["Value Score"] > meh["Value Score"]
        assert bool(good["veto"]) is False

        # Fair value blend for GOOD: Graham + PE + analyst only
        gn, pe, an = 2250 ** 0.5, 75.0, 90.0 * (1 - screener.ANALYST_TARGET_HAIRCUT)
        wg, wp, wa = screener.W_GRAHAM, screener.W_PE, screener.W_ANALYST
        expected_fv = (gn * wg + pe * wp + an * wa) / (wg + wp + wa)
        assert good["fair_value"] == pytest.approx(expected_fv, abs=0.01)
        assert good["MoS %"] == pytest.approx(
            (expected_fv - 50.0) / expected_fv * 100, abs=0.1)

    def test_rows_without_price_dropped(self, synthetic_universe):
        df = synthetic_universe.copy()
        df.loc[len(df)] = {"Name": "Ghost", "Ticker": "GHOST"}   # no price
        out = run_screener_from_df(df)
        assert "GHOST" not in set(out["Ticker"])
        assert len(out) == 4

    def test_missing_price_column_is_added_as_all_none(self):
        # No "Price" column at all (not just missing values) -> every row
        # gets dropped as if all had no price, rather than raising a
        # KeyError.
        df = pd.DataFrame([{"Name": "No Price Co", "Ticker": "NOPRICE"}])
        out = run_screener_from_df(df)
        assert out.empty

    def test_all_rows_dropped_for_no_price_returns_empty_df(self):
        df = pd.DataFrame([{"Name": "Ghost", "Ticker": "GHOST", "Price": None}])
        out = run_screener_from_df(df)
        assert out.empty

    def test_weak_but_not_vetoed_row_gets_avoid_decision(self):
        # Composite scoring is cross-sectional (percentile rank against the
        # OTHER rows in the same call), so a single lone "weak" row alone
        # can't be driven below the Avoid threshold — a 2-row worst-case
        # bottoms out at exactly 50 (1/2 * 100). A 5-row gradient with one
        # row clearly worst on every dimension (but debt/equity kept just
        # under the hard-veto threshold, so it fails on SCORE alone, not
        # veto) is what actually reaches the plain "Avoid" fallback branch.
        grades = [
            dict(price=40.0,  eps=5.0, bvps=20.0, target=90.0, roe=0.20,  de=50.0,  cr=2.0, vol=1e6,
                 eg=0.08,  rg=0.06,  rm=1.5),
            dict(price=60.0,  eps=4.0, bvps=15.0, target=85.0, roe=0.15,  de=80.0,  cr=1.8, vol=8e5,
                 eg=0.05,  rg=0.04,  rm=2.0),
            dict(price=80.0,  eps=3.0, bvps=10.0, target=80.0, roe=0.10,  de=120.0, cr=1.5, vol=5e5,
                 eg=0.02,  rg=0.02,  rm=2.8),
            dict(price=95.0,  eps=2.0, bvps=5.0,  target=90.0, roe=0.05,  de=150.0, cr=1.2, vol=2e5,
                 eg=0.0,   rg=0.0,   rm=3.2),
            dict(price=200.0, eps=0.2, bvps=0.5,  target=50.0, roe=-0.20, de=450.0, cr=0.6, vol=5_000,
                 eg=-0.40, rg=-0.30, rm=4.9),
        ]
        rows = [{
            "Name": f"Co{i}", "Ticker": f"T{i}", "Price": g["price"],
            "trailingEps": g["eps"], "bookValue": g["bvps"], "targetMeanPrice": g["target"],
            "beta": 1.0, "returnOnEquity": g["roe"], "returnOnAssets": g["roe"] / 2,
            "operatingMargins": g["roe"], "freeCashflow": 1e8, "netIncome": 5e7,
            "debtToEquity": g["de"], "currentRatio": g["cr"], "averageVolume": g["vol"],
            "earningsGrowth": g["eg"], "revenueGrowth": g["rg"], "recommendationMean": g["rm"],
        } for i, g in enumerate(grades)]

        out = compute_scores(pd.DataFrame(rows))
        weakest = out[out["Ticker"] == "T4"].iloc[0]
        assert weakest["Decision"] == "Avoid"
        assert bool(weakest["veto"]) is False
        assert weakest["Value Score"] < screener.SCORE_AVOID

    def test_single_strong_row_reaches_strong_buy_decision(self):
        # A single high-conviction row (no cross-sectional dilution from
        # other rows in the percentile ranking) should clear both the
        # score and margin-of-safety thresholds for "Strong Buy".
        row = pd.DataFrame([{
            "Name": "Good Co", "Ticker": "GOOD", "Price": 50.0,
            "trailingEps": 5.0, "bookValue": 20.0, "targetMeanPrice": 90.0,
            "beta": 1.0, "returnOnEquity": 0.20, "returnOnAssets": 0.10,
            "operatingMargins": 0.25, "freeCashflow": 1e9, "netIncome": 8e8,
            "debtToEquity": 50.0, "currentRatio": 2.0, "averageVolume": 1e6,
            "earningsGrowth": 0.08, "revenueGrowth": 0.06, "recommendationMean": 2.0,
        }])
        out = compute_scores(row)
        assert out.iloc[0]["Decision"] == "Strong Buy"

    def test_missing_fair_value_cannot_reach_strong_buy(self):
        # NOVAL has no trailingEps/bookValue/targetMeanPrice/ebit/dividend at
        # all -> every fair-value model returns None -> fair_value and
        # margin_of_safety are both NaN. It otherwise tops WEAK on every other
        # dimension, so the composite score alone clears buy_threshold -- but
        # with no fair value there is no confirmed margin of safety, so this
        # must NOT be a Strong Buy (pre-fix, a NaN MoS silently passed the
        # "MoS >= min_mos" gate instead of failing it).
        noval = {
            "Name": "No Valuation Co", "Ticker": "NOVAL", "Price": 50.0,
            "beta": 1.0, "returnOnEquity": 0.20, "returnOnAssets": 0.10,
            "operatingMargins": 0.25, "fcfYield": 0.08,
            "freeCashflow": 1e9, "netIncome": 8e8,
            "debtToEquity": 50.0, "currentRatio": 2.0, "interestCoverage": 10.0,
            "averageVolume": 1e6,
            "trailingAnnualDividendRate": 0.0, "dividendRate": 0.0,
            "earningsGrowth": 0.08, "revenueGrowth": 0.06, "recommendationMean": 2.0,
        }
        weak = {
            "Name": "Weak Co", "Ticker": "WEAK", "Price": 100.0,
            "trailingEps": 2.0, "bookValue": 8.0, "targetMeanPrice": 80.0,
            "beta": 3.0, "returnOnEquity": -0.10, "returnOnAssets": -0.05,
            "operatingMargins": -0.10, "fcfYield": -0.10,
            "freeCashflow": -1e8, "netIncome": 4e8,
            "debtToEquity": 400.0, "currentRatio": 0.5, "interestCoverage": 0.2,
            "averageVolume": 10_000,
            "trailingAnnualDividendRate": 0.0, "dividendRate": 0.0,
            "earningsGrowth": -0.30, "revenueGrowth": -0.20, "recommendationMean": 4.5,
        }
        out = compute_scores(pd.DataFrame([noval, weak]))
        row = out[out["Ticker"] == "NOVAL"].iloc[0]
        assert pd.isna(row["fair_value"])
        assert pd.isna(row["margin_of_safety"])
        assert row["Value Score"] >= screener.SCORE_STRONG_BUY  # would have qualified pre-fix
        assert row["Decision"] != "Strong Buy"


# ══════════════════════════════════════════════════════════════════════════════
# Risk helpers
# ══════════════════════════════════════════════════════════════════════════════

class TestRiskHelpers:
    def test_safe(self):
        assert _safe("3.5") == 3.5
        assert _safe(None) is None
        assert _safe(float("nan"), 7) == 7
        assert _safe("abc", 1) == 1

    def test_mdd_known_path(self):
        # +10%, −50%, +10% → trough 0.55 vs peak 1.1 → −50% drawdown
        s = pd.Series([0.10, -0.50, 0.10])
        assert _mdd(s) == pytest.approx(-0.50)
        assert _mdd(pd.Series([0.1])) is None
        assert _mdd(pd.Series(dtype=float)) is None

    def test_labels(self):
        assert _hhi_label(0.05) == "Well diversified"
        assert _hhi_label(0.12) == "Moderately concentrated"
        assert _hhi_label(0.25) == "Highly concentrated"
        assert _beta_label(0.7) == "Defensive"
        assert _beta_label(1.0) == "Market-like"
        assert _beta_label(1.3) == "Aggressive"
        assert _vol_label(0.05) == "Low"
        assert _vol_label(0.15) == "Moderate"
        assert _vol_label(0.25) == "High"
        assert _mdd_label(-0.05) == "Low"
        assert _mdd_label(-0.35) == "High"
        assert _mdd_label(None) == "N/A"
        assert _sharpe_label(1.6) == "Strong"
        assert _sharpe_label(1.2) == "Acceptable"
        assert _sharpe_label(0.5) == "Suboptimal"
        assert _sharpe_label(None) == "N/A"
        # Sortino's bar sits higher than Sharpe's since downside deviation
        # alone is ≤ total volatility, so the same number needs a tougher bar.
        assert _sortino_label(2.2) == "Strong"
        assert _sortino_label(1.6) == "Acceptable"
        assert _sortino_label(1.2) == "Suboptimal"
        assert _sortino_label(None) == "N/A"

    def test_risk_label_boundaries(self):
        assert _risk_label_action(25.0)[0] == "Low risk"
        assert _risk_label_action(25.1)[0] == "Moderate risk"
        assert _risk_label_action(50.1)[0] == "Elevated risk"
        assert _risk_label_action(70.1)[0] == "High risk"
        assert _risk_label_action(85.1)[0] == "Critical risk"


class TestToEur:
    def _closes(self):
        idx = pd.bdate_range("2024-01-01", periods=4)
        return pd.DataFrame({
            "EU.PA": pd.Series([100.0, 101.0, 102.0, 103.0], index=idx),
            "US.N":  pd.Series([200.0, 202.0, 204.0, 206.0], index=idx),
        })

    def test_empty_closes_pass_through(self):
        assert _to_eur(pd.DataFrame(), {}).empty
        assert _to_eur(None, {}) is None

    def test_noop_when_currency_missing_no_fx_fetch(self, monkeypatch):
        def _boom(*a, **k):
            raise AssertionError("no FX fetch when every currency is EUR/unknown")
        monkeypatch.setattr(marketdata, "fx_to_eur_frame", _boom)
        closes = self._closes()
        pd.testing.assert_frame_equal(_to_eur(closes, {"EU.PA": {}, "US.N": {}}), closes)

    def test_noop_when_all_eur(self, monkeypatch):
        monkeypatch.setattr(marketdata, "fx_to_eur_frame",
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError("no fetch")))
        closes = self._closes()
        cache = {"EU.PA": {"Currency": "EUR"}, "US.N": {"Currency": "eur"}}
        pd.testing.assert_frame_equal(_to_eur(closes, cache), closes)

    def test_scales_only_the_foreign_column(self, monkeypatch):
        closes = self._closes()
        fx = pd.DataFrame({"USD": pd.Series([0.90, 0.90, 0.95, 0.95], index=closes.index)})
        monkeypatch.setattr(marketdata, "fx_to_eur_frame", lambda *a, **k: fx)
        out = _to_eur(closes, {"EU.PA": {"Currency": "EUR"}, "US.N": {"Currency": "USD"}})
        pd.testing.assert_series_equal(out["EU.PA"], closes["EU.PA"])
        assert out["US.N"].tolist() == pytest.approx([180.0, 181.8, 193.8, 195.7])

    def test_foreign_column_left_native_when_fx_history_absent(self, monkeypatch):
        closes = self._closes()
        monkeypatch.setattr(marketdata, "fx_to_eur_frame", lambda *a, **k: pd.DataFrame())
        out = _to_eur(closes, {"EU.PA": {"Currency": "EUR"}, "US.N": {"Currency": "USD"}})
        pd.testing.assert_frame_equal(out, closes)

    def test_fx_gaps_are_forward_filled_onto_close_dates(self, monkeypatch):
        closes = self._closes()
        # FX known only for the first and third day → ffill/bfill covers the rest.
        fx = pd.DataFrame({"USD": pd.Series(
            [0.90, 0.95], index=closes.index[[0, 2]])})
        monkeypatch.setattr(marketdata, "fx_to_eur_frame", lambda *a, **k: fx)
        out = _to_eur(closes, {"US.N": {"Currency": "USD"}})
        assert out["US.N"].tolist() == pytest.approx([180.0, 181.8, 193.8, 195.7])

    def test_assess_portfolio_volatility_is_computed_on_eur_series(self, monkeypatch):
        """End-to-end: a EUR+USD portfolio with a known FX path must report the
        volatility of the EUR-restated return series, not the currency blend."""
        idx = pd.bdate_range("2023-01-02", periods=260)
        rng = np.random.default_rng(7)
        eur_px = pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.01, 260)), index=idx)
        usd_px = pd.Series(200 * np.cumprod(1 + rng.normal(0, 0.01, 260)), index=idx)
        fx_usd = pd.Series(0.90 + np.cumsum(rng.normal(0, 0.002, 260)), index=idx)

        monkeypatch.setattr(risk, "_fetch_history",
                            lambda tickers, period="5y": pd.DataFrame({"EU.PA": eur_px, "US.N": usd_px}))
        monkeypatch.setattr(marketdata, "fx_to_eur_frame",
                            lambda *a, **k: pd.DataFrame({"USD": fx_usd}))
        monkeypatch.setattr(risk, "_fetch_ff_csv",
                            lambda url: (_ for _ in ()).throw(ConnectionError("offline")))
        monkeypatch.setattr(risk, "_ff_cache", {})

        pf = pd.DataFrame([
            {"ticker": "EU.PA", "name": "Eu",  "current_value": 500.0, "shares": 5,
             "live_price": 100.0, "sector": "Tech", "country": "France",
             "expected_annual": 0.0, "fair_value": 110.0},
            {"ticker": "US.N", "name": "Us",   "current_value": 500.0, "shares": 5,
             "live_price": 200.0, "sector": "Tech", "country": "United States",
             "expected_annual": 0.0, "fair_value": 210.0},
        ])
        cache = {"EU.PA": {"Currency": "EUR", "beta": 1.0},
                 "US.N":  {"Currency": "USD", "beta": 1.0}}

        report = assess_portfolio(pf, cache)

        eur_closes = pd.DataFrame({"EU.PA": eur_px, "US.N": usd_px * fx_usd})
        dr = eur_closes.pct_change().iloc[1:]
        exp_vol = float((dr.values @ np.array([0.5, 0.5])).std(ddof=1)) * np.sqrt(252)
        # _stage3_quant rounds volatility_annual to 4 dp.
        assert report.quant.volatility_annual == pytest.approx(exp_vol, abs=1e-4)

        # And it must NOT match the un-converted currency blend.
        dr_blend = pd.DataFrame({"EU.PA": eur_px, "US.N": usd_px}).pct_change().iloc[1:]
        blend_vol = float((dr_blend.values @ np.array([0.5, 0.5])).std(ddof=1)) * np.sqrt(252)
        assert abs(report.quant.volatility_annual - blend_vol) > 1e-3


# ══════════════════════════════════════════════════════════════════════════════
# Risk WS-3 — beta from history + realised position vol
# ══════════════════════════════════════════════════════════════════════════════

class TestBetaResolution:
    def test_ols_beta_recovers_known_slope(self):
        rng = np.random.default_rng(1)
        x = rng.normal(0, 0.01, 500)
        y = 1.4 * x + rng.normal(0, 1e-5, 500)
        assert _ols_beta(y, x) == pytest.approx(1.4, abs=0.02)

    def test_ols_beta_none_when_market_has_no_variance(self):
        x = np.zeros(100)
        assert _ols_beta(np.arange(100.0), x) is None

    def _rets(self, n=260, seed=0):
        idx = pd.bdate_range("2023-01-02", periods=n)
        rng = np.random.default_rng(seed)
        bench = pd.Series(rng.normal(0, 0.01, n), index=idx)
        stock = pd.DataFrame({
            "HI": 1.6 * bench + rng.normal(0, 1e-4, n),   # high beta
            "LO": 0.4 * bench + rng.normal(0, 1e-4, n),   # low beta
        }, index=idx)
        return stock, bench

    def test_resolve_betas_prefers_regression(self):
        stock, bench = self._rets()
        cache = {"HI": {"beta": 0.9}, "LO": {"beta": 0.9}}  # yfinance disagrees
        betas, sources = _resolve_betas(["HI", "LO"], stock, bench, cache)
        assert sources == {"HI": "regression", "LO": "regression"}
        assert betas["HI"] == pytest.approx(1.6, abs=0.05)
        assert betas["LO"] == pytest.approx(0.4, abs=0.05)

    def test_resolve_betas_falls_back_to_yfinance_then_default(self):
        stock, bench = self._rets(n=30)          # < _BETA_MIN_OBS
        betas, sources = _resolve_betas(
            ["HI", "NOFD"], stock, bench, {"HI": {"beta": 1.1}})
        assert (sources["HI"], betas["HI"]) == ("yfinance", 1.1)
        assert (sources["NOFD"], betas["NOFD"]) == ("default", 1.0)

    def test_resolve_betas_no_benchmark_uses_yfinance(self):
        stock, _ = self._rets()
        betas, sources = _resolve_betas(["HI"], stock, None, {"HI": {"beta": 1.2}})
        assert (sources["HI"], betas["HI"]) == ("yfinance", 1.2)

    def test_stage3_portfolio_beta_uses_supplied_betas(self):
        pf = pd.DataFrame([
            {"ticker": "A", "current_value": 500.0},
            {"ticker": "B", "current_value": 500.0},
        ])
        q = _stage3_quant(pf, {"A": {"beta": 1.0}, "B": {"beta": 1.0}}, 1000.0,
                          pd.DataFrame(), betas={"A": 1.8, "B": 0.2},
                          portfolio_beta_regression=1.05)
        assert q.portfolio_beta == pytest.approx(1.0)          # 0.5×1.8 + 0.5×0.2
        assert q.portfolio_beta_regression == 1.05

    def test_stage1_sets_beta_source_and_uses_realised_vol(self):
        idx = pd.bdate_range("2023-01-02", periods=200)
        rng = np.random.default_rng(3)
        closes = pd.DataFrame(
            {"A": 100 * np.cumprod(1 + rng.normal(0, 0.02, 200))}, index=idx)
        pf = pd.DataFrame([{"ticker": "A", "name": "A", "current_value": 1000.0,
                            "live_price": 100.0, "fair_value": 110.0}])
        profs = _stage1_position_profiles(
            pf, {"A": {"beta": 3.0}}, 1000.0,
            betas={"A": 1.1}, beta_sources={"A": "regression"}, closes=closes)
        p = profs[0]
        assert p.beta == 1.1 and p.beta_source == "regression"
        # realised vol ≈ 0.02×√252 ≈ 0.32, nowhere near the 3.0-beta proxy (~0.57)
        exp = float(closes["A"].pct_change().dropna().std(ddof=1)) * np.sqrt(252)
        assert p.vol_annual == pytest.approx(exp, abs=1e-4)

    def test_stage1_falls_back_to_beta_proxy_without_history(self):
        pf = pd.DataFrame([{"ticker": "A", "name": "A", "current_value": 1000.0,
                            "live_price": 100.0, "fair_value": 110.0}])
        profs = _stage1_position_profiles(pf, {"A": {"beta": 2.0}}, 1000.0)
        p = profs[0]
        assert p.beta == 2.0 and p.beta_source == "yfinance"
        assert p.vol_annual == pytest.approx(2.0 * 0.012 * np.sqrt(252), abs=1e-4)

    def test_assess_portfolio_end_to_end_regression_beta(self, monkeypatch):
        idx = pd.bdate_range("2023-01-02", periods=260)
        rng = np.random.default_rng(11)
        bench_r = rng.normal(0, 0.011, 260)
        px = {
            "AAA": 100 * np.cumprod(1 + (1.7 * bench_r + rng.normal(0, 5e-4, 260))),
            "BBB": 100 * np.cumprod(1 + (0.5 * bench_r + rng.normal(0, 5e-4, 260))),
            BENCHMARK_TICKER: 1000 * np.cumprod(1 + bench_r),
        }
        monkeypatch.setattr(risk, "_fetch_history",
                            lambda tickers, period="5y": pd.DataFrame(
                                {t: px[t] for t in tickers if t in px}, index=idx))
        monkeypatch.setattr(risk, "_fetch_ff_csv",
                            lambda url: (_ for _ in ()).throw(ConnectionError("offline")))
        monkeypatch.setattr(risk, "_ff_cache", {})

        pf = pd.DataFrame([
            {"ticker": "AAA", "name": "A", "current_value": 600.0, "shares": 6,
             "live_price": 100.0, "sector": "Tech", "country": "France",
             "expected_annual": 0.0, "fair_value": 110.0},
            {"ticker": "BBB", "name": "B", "current_value": 400.0, "shares": 4,
             "live_price": 100.0, "sector": "Health", "country": "Germany",
             "expected_annual": 0.0, "fair_value": 105.0},
        ])
        cache = {"AAA": {"beta": 1.0, "Currency": "EUR"},
                 "BBB": {"beta": 1.0, "Currency": "EUR"}}

        r = assess_portfolio(pf, cache)

        by_ticker = {p.ticker: p for p in r.position_profiles}
        assert by_ticker["AAA"].beta_source == "regression"
        assert by_ticker["AAA"].beta == pytest.approx(1.7, abs=0.1)
        assert by_ticker["BBB"].beta == pytest.approx(0.5, abs=0.1)
        # weighted-sum ≈ 0.6×1.7 + 0.4×0.5 = 1.22, and the direct regression
        # cross-check is populated and in the same ballpark
        assert r.quant.portfolio_beta == pytest.approx(1.22, abs=0.1)
        assert r.quant.portfolio_beta_regression is not None
        assert r.quant.portfolio_beta_regression == pytest.approx(1.22, abs=0.15)


# ══════════════════════════════════════════════════════════════════════════════
# Risk Stage 1 — position profiling
# ══════════════════════════════════════════════════════════════════════════════

class TestStage1:
    def test_position_rating_points(self):
        # 0 pts → Low
        assert _position_rating(0.05, 1.0, 0.20, 8.0, 8.0) == "Low"
        # weight 0.12 → 1 pt → Medium
        assert _position_rating(0.12, 1.0, 0.20, 8.0, 8.0) == "Medium"
        # weight(1) + beta 1.4(1) + slight overvaluation(1) = 3 → High
        assert _position_rating(0.12, 1.4, -0.05, 8.0, 8.0) == "High"
        # everything bad: 2+2+2+2+1 = 9 → Critical
        assert _position_rating(0.16, 1.6, -0.15, 2.0, 2.0) == "Critical"

    def test_profiles_weights_var_and_valuation(self):
        pf = pd.DataFrame([
            {"ticker": "UND", "name": "Under Co", "current_value": 200.0,
             "live_price": 80.0, "fair_value": 100.0},
            {"ticker": "OVR", "name": "Over Co", "current_value": 800.0,
             "live_price": 110.0, "fair_value": 100.0},
        ])
        cache = {"UND": {"beta": 1.5}, "OVR": {}}
        profiles = _stage1_position_profiles(pf, cache, 1000.0)
        und, ovr = profiles

        assert und.weight == pytest.approx(0.20)
        assert und.mos == pytest.approx(0.20)
        assert und.valuation_flag == "Undervalued"
        # Parametric VaR: value × |beta| × market vol × 1.645
        assert und.var_95_1d_eur == pytest.approx(200 * 1.5 * 0.012 * 1.645, abs=0.01)

        assert ovr.weight == pytest.approx(0.80)
        assert ovr.mos == pytest.approx(-0.10)
        assert ovr.valuation_flag == "Overvalued"


# ══════════════════════════════════════════════════════════════════════════════
# Risk Stage 2 — concentration
# ══════════════════════════════════════════════════════════════════════════════

class TestStage2:
    def test_hhi_and_top_weights(self):
        pf = pd.DataFrame([
            {"ticker": "A", "current_value": 40.0, "sector": "Energy",
             "country": "Germany", "expected_annual": 6.0},
            {"ticker": "B", "current_value": 30.0, "sector": "Energy",
             "country": "Germany", "expected_annual": 3.0},
            {"ticker": "C", "current_value": 20.0, "sector": "Utilities",
             "country": "Germany", "expected_annual": 1.0},
            {"ticker": "D", "current_value": 10.0, "sector": "Utilities",
             "country": "France", "expected_annual": 0.0},
        ])
        c = _stage2_concentration(pf, 100.0)

        assert c.hhi == pytest.approx(0.16 + 0.09 + 0.04 + 0.01)
        assert c.hhi_label == "Highly concentrated"
        assert c.top1_ticker == "A" and c.top1_weight == pytest.approx(0.40)
        assert c.top3_weight == pytest.approx(0.90)
        assert c.top5_weight == pytest.approx(1.0)
        assert c.top1_flag and c.top3_flag and c.top5_flag

        assert c.sector_weights["Energy"] == pytest.approx(0.70)
        assert c.largest_sector == "Energy" and c.sector_flag
        assert c.geo_weights["Germany"] == pytest.approx(0.90)
        assert c.largest_geo == "Germany" and c.geo_flag

        # Income HHI: shares 0.6, 0.3, 0.1 → 0.36+0.09+0.01 = 0.46
        assert c.div_hhi == pytest.approx(0.46)
        assert c.div_top3_pct == pytest.approx(1.0)
        assert c.income_concentration_flag

    def test_equal_weight_portfolio_is_diversified(self):
        pf = pd.DataFrame([{"ticker": f"T{i}", "current_value": 5.0,
                            "sector": f"S{i % 12}", "country": f"C{i % 5}",
                            "expected_annual": 1.0} for i in range(20)])
        c = _stage2_concentration(pf, 100.0)
        assert c.hhi == pytest.approx(0.05)
        assert c.hhi_label == "Well diversified"
        assert not (c.top1_flag or c.top3_flag or c.top5_flag)

    def test_empty_portfolio_value(self):
        pf = pd.DataFrame([{"ticker": "A", "current_value": 0.0}])
        assert _stage2_concentration(pf, 0.0).hhi_label == "N/A"


# ══════════════════════════════════════════════════════════════════════════════
# Risk Stage 3 — quantitative metrics on synthetic price history
# ══════════════════════════════════════════════════════════════════════════════

class TestStage3Quant:
    @pytest.fixture
    def synthetic_market(self):
        n = 260
        dates = pd.bdate_range("2024-01-02", periods=n + 1)
        # Two perfectly correlated alternating-return series (in phase)
        ret_a = np.array([0.0006 if i % 2 == 0 else 0.0004 for i in range(n)])
        ret_b = np.array([0.0100 if i % 2 == 0 else -0.0100 for i in range(n)])
        closes = pd.DataFrame({
            "AAA": 100 * np.cumprod(np.insert(1 + ret_a, 0, 1.0)),
            "BBB": 100 * np.cumprod(np.insert(1 + ret_b, 0, 1.0)),
        }, index=dates)
        pf = pd.DataFrame([
            {"ticker": "AAA", "current_value": 500.0},
            {"ticker": "BBB", "current_value": 500.0},
        ])
        cache = {"AAA": {"beta": 0.8}, "BBB": {"beta": 1.2}}
        port_rets = 0.5 * ret_a + 0.5 * ret_b
        return pf, cache, closes, port_rets

    def test_beta_vol_var(self, synthetic_market):
        pf, cache, closes, port_rets = synthetic_market
        q = _stage3_quant(pf, cache, 1000.0, closes)

        # weighted beta: 0.5×0.8 + 0.5×1.2 = 1.0
        assert q.portfolio_beta == pytest.approx(1.0)
        assert q.beta_label == "Market-like"

        exp_vol = float(np.std(port_rets, ddof=1)) * np.sqrt(252)
        assert q.volatility_annual == pytest.approx(exp_vol, rel=1e-2)

        exp_var95 = abs(float(np.percentile(port_rets, 5))) * 1000.0
        assert q.var_95_1d_eur == pytest.approx(exp_var95, rel=1e-2)
        assert q.cvar_95_1d_eur >= q.var_95_1d_eur * 0.99   # CVaR ≥ VaR

    def test_high_correlation_detected(self, synthetic_market):
        pf, cache, closes, _ = synthetic_market
        q = _stage3_quant(pf, cache, 1000.0, closes)
        assert len(q.high_corr_pairs) == 1
        a, b, corr = q.high_corr_pairs[0]
        assert {a, b} == {"AAA", "BBB"}
        assert corr == pytest.approx(1.0, abs=0.01)
        # Perfect correlation → zero diversification benefit
        assert q.effective_diversification == pytest.approx(0.0, abs=0.01)

    def test_var_is_zero_for_portfolio_that_never_loses(self):
        # All-positive daily returns → 5th percentile is a gain, not a loss;
        # VaR must report €0 at risk instead of flipping the sign.
        n = 260
        dates = pd.bdate_range("2024-01-02", periods=n + 1)
        ret = np.array([0.0010 if i % 2 == 0 else 0.0002 for i in range(n)])
        closes = pd.DataFrame(
            {"AAA": 100 * np.cumprod(np.insert(1 + ret, 0, 1.0))}, index=dates)
        pf = pd.DataFrame([{"ticker": "AAA", "current_value": 1000.0}])
        q = _stage3_quant(pf, {"AAA": {"beta": 1.0}}, 1000.0, closes)
        assert q.var_95_1d_eur == 0.0
        assert q.var_99_1d_eur == 0.0
        assert q.cvar_95_1d_eur == 0.0

    def test_no_history_degrades_gracefully(self, synthetic_market):
        pf, cache, *_ = synthetic_market
        q = _stage3_quant(pf, cache, 1000.0, pd.DataFrame())
        assert not q.returns_available
        assert q.volatility_annual is None
        assert q.portfolio_beta == pytest.approx(1.0)   # beta still computable


# ══════════════════════════════════════════════════════════════════════════════
# Risk Stage 4 — Fama-French factor exposure (network fetch + parsing)
# ══════════════════════════════════════════════════════════════════════════════

def _make_ff_zip(csv_body: str) -> bytes:
    """Build an in-memory zip matching Ken French's real file layout: one
    member file, whose text starts with an arbitrary header line, then the
    factor-name header row, then daily rows, then a trailing blank line."""
    import io as _io
    import zipfile as _zipfile
    buf = _io.BytesIO()
    with _zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("F-F_data.csv", csv_body)
    return buf.getvalue()


class _FakeUrlResponse:
    def __init__(self, data: bytes):
        self._data = data

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestFetchFfCsv:
    @pytest.fixture(autouse=True)
    def _clear_ff_cache(self, monkeypatch):
        # _fetch_ff_csv caches by URL in a module-level dict so it only
        # downloads once per process — clear it so each test actually
        # exercises the parse path instead of an earlier test's cached result.
        monkeypatch.setattr(risk, "_ff_cache", {})

    def test_parses_daily_factor_csv(self, monkeypatch):
        csv_body = (
            "Some descriptive header text from Ken French's site\n"
            ",Mkt-RF,SMB,HML,RMW,CMA,RF\n"
            "20200102,1.05,0.12,-0.34,0.05,0.02,0.01\n"
            "20200103,-0.50,0.08,0.10,-0.02,0.01,0.01\n"
            "\n"
            "Annual Factors: January-December\n"
        )
        fake_bytes = _make_ff_zip(csv_body)
        monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout=15: _FakeUrlResponse(fake_bytes))

        df = _fetch_ff_csv("http://example.test/ff5.zip")
        assert list(df.columns) == ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"]
        assert len(df) == 2
        # Values are stored as decimals, not percent (raw CSV / 100).
        assert df.iloc[0]["Mkt-RF"] == pytest.approx(0.0105)
        assert df.index[0] == pd.Timestamp("2020-01-02")

    def test_caches_result_across_calls(self, monkeypatch):
        csv_body = ",Mkt-RF,SMB,HML,RMW,CMA,RF\n20200102,1.0,0.0,0.0,0.0,0.0,0.0\n\n"
        fake_bytes = _make_ff_zip(csv_body)
        calls = []
        monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout=15:
                            (calls.append(url), _FakeUrlResponse(fake_bytes))[1])

        url = "http://example.test/ff5-cached.zip"
        _fetch_ff_csv(url)
        _fetch_ff_csv(url)
        assert calls == [url]  # second call served from _ff_cache, no re-fetch

    def test_malformed_response_raises(self, monkeypatch):
        monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout=15: _FakeUrlResponse(b"not a zip file"))
        with pytest.raises(Exception):
            _fetch_ff_csv("http://example.test/broken.zip")


class TestStage4Factor:
    def test_insufficient_history_is_unavailable(self):
        short_rets = pd.Series([0.001] * 30, index=pd.bdate_range("2024-01-01", periods=30))
        result = _stage4_factor(short_rets)
        assert result.available is False
        assert "Insufficient price history" in result.flags[0]

    def test_none_returns_unavailable(self):
        result = _stage4_factor(None)
        assert result.available is False

    def test_ff_fetch_failure_marks_unavailable(self, monkeypatch):
        monkeypatch.setattr(risk, "_ff_cache", {})

        def _boom(url):
            raise ConnectionError("network down")
        monkeypatch.setattr(risk, "_fetch_ff_csv", _boom)

        long_rets = pd.Series([0.001] * 100, index=pd.bdate_range("2024-01-01", periods=100))
        result = _stage4_factor(long_rets)
        assert result.available is False
        assert "Fama-French data unavailable" in result.flags[0]


# ══════════════════════════════════════════════════════════════════════════════
# Risk WS-5 — hardened factor data feed (disk cache + set fallback + as-of)
# ══════════════════════════════════════════════════════════════════════════════

def _ff5_frame(start="2022-01-03", n=400, seed=0):
    idx = pd.bdate_range(start, periods=n)
    rng = np.random.default_rng(seed)
    cols = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"]
    df = pd.DataFrame({c: rng.normal(0, 0.006, n) for c in cols}, index=idx)
    df["RF"] = 0.00012
    df.index.name = "Date"
    return df


class TestFactorData:
    def test_fresh_disk_cache_served_without_fetch(self, monkeypatch):
        risk._write_factor_cache("5f", "developed", _ff5_frame())

        def _boom(url):
            raise AssertionError("should not fetch when the disk cache is fresh")
        monkeypatch.setattr(risk, "_fetch_ff_csv", _boom)

        df, meta = risk._factor_data("5f")
        assert meta["set"] == "developed" and meta["source"] == "disk"
        assert meta["stale"] is False and meta["as_of"] is not None
        assert list(df.columns) == ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"]

    def test_network_success_writes_cache_and_labels_set(self, monkeypatch):
        frame = _ff5_frame()
        monkeypatch.setattr(risk, "_fetch_ff_csv", lambda url: frame)
        df, meta = risk._factor_data("5f")
        assert meta["set"] == "developed" and meta["source"] == "network"
        assert risk._factor_cache_path("5f", "developed").exists()

    def test_falls_back_to_us_set_when_developed_unreachable(self, monkeypatch):
        frame = _ff5_frame()

        def _fetch(url):
            if "Developed" in url:
                raise ConnectionError("developed 404")
            return frame
        monkeypatch.setattr(risk, "_fetch_ff_csv", _fetch)
        df, meta = risk._factor_data("5f")
        assert meta["set"] == "us" and meta["source"] == "network"

    def test_all_network_fails_serves_stale_disk_copy(self, monkeypatch):
        risk._write_factor_cache("5f", "us", _ff5_frame())
        p = risk._factor_cache_path("5f", "us")
        old = dt.datetime.now().timestamp() - (risk._FACTOR_MAX_AGE_DAYS + 2) * 86400
        os.utime(p, (old, old))

        def _boom(url):
            raise ConnectionError("offline")
        monkeypatch.setattr(risk, "_fetch_ff_csv", _boom)

        df, meta = risk._factor_data("5f")
        assert meta["stale"] is True and meta["source"] == "disk" and meta["set"] == "us"
        assert df is not None and not df.empty

    def test_all_network_fails_no_disk_returns_none(self, monkeypatch):
        def _boom(url):
            raise ConnectionError("offline")
        monkeypatch.setattr(risk, "_fetch_ff_csv", _boom)
        df, meta = risk._factor_data("5f")
        assert df is None and meta["stale"] is True and meta["set"] is None

    def test_stage4_full_regression_populates_provenance(self, monkeypatch):
        f5 = _ff5_frame(seed=1)

        def _fd(kind):
            if kind == "5f":
                return f5, {"set": "developed", "as_of": "2023-08-04",
                            "stale": False, "source": "network"}
            return None, {"set": None, "as_of": None, "stale": True, "source": None}
        monkeypatch.setattr(risk, "_factor_data", _fd)

        idx = f5.index[50:300]
        port_rets = pd.Series(np.random.default_rng(2).normal(0, 0.01, len(idx)), index=idx)
        fx = _stage4_factor(port_rets)

        assert fx.available is True
        assert set(fx.loadings) >= {"Mkt-RF", "SMB", "HML", "RMW", "CMA"}
        assert fx.factor_set == "developed" and fx.as_of == "2023-08-04"
        assert fx.stale is False and fx.n_obs is not None

    def test_stage4_flags_a_stale_cached_feed(self, monkeypatch):
        f5 = _ff5_frame(seed=3)

        def _fd(kind):
            meta = {"set": "us", "as_of": "2026-05-01", "stale": True, "source": "disk"}
            return (f5 if kind == "5f" else None), meta
        monkeypatch.setattr(risk, "_factor_data", _fd)

        idx = f5.index[50:200]
        port_rets = pd.Series(np.random.default_rng(4).normal(0, 0.01, len(idx)), index=idx)
        fx = _stage4_factor(port_rets)
        assert fx.available is True and fx.stale is True
        assert any("cached copy" in f for f in fx.flags)


# ══════════════════════════════════════════════════════════════════════════════
# Risk Stage 5 — income risk
# ══════════════════════════════════════════════════════════════════════════════

class TestStage5Income:
    def test_yield_dgr_and_concentration(self):
        pf = pd.DataFrame([
            {"ticker": "A", "current_value": 600.0, "expected_annual": 60.0},
            {"ticker": "B", "current_value": 300.0, "expected_annual": 30.0},
            {"ticker": "C", "current_value": 100.0, "expected_annual": 10.0},
        ])
        cache = {
            "A": {"earningsGrowth": 0.04, "trailingAnnualDividendRate": 2.0,
                  "payoutRatio": 0.95},                      # flagged payer
            "B": {"earningsGrowth": 0.02, "trailingAnnualDividendRate": 1.0,
                  "payoutRatio": 0.50, "dividendCoverage": 2.0,
                  "cashPayoutRatio": 0.4},
            "C": {"trailingAnnualDividendRate": 0.5, "payoutRatio": 0.50,
                  "dividendCoverage": 2.0, "cashPayoutRatio": 0.4},
        }
        inc = _stage5_income(pf, cache, 1000.0)

        assert inc.portfolio_yield == pytest.approx(0.10)
        assert inc.total_annual_income == pytest.approx(100.0)
        # weighted DGR = 0.6×0.04 + 0.3×0.02 = 0.03 (C has no growth data)
        assert inc.weighted_dgr == pytest.approx(0.03)
        # top-3 = all income → 50% cut removes 50% of income
        assert inc.top3_cut_pct == pytest.approx(0.50)
        assert inc.income_concentration_flag
        assert inc.flagged_payers == ["A"]
        assert inc.flagged_income_pct == pytest.approx(0.60)
        assert inc.income_stability is None                  # no DPS history in cache

    def test_weighted_dgr_prefers_true_dgr_over_earnings_growth(self):
        pf = pd.DataFrame([
            {"ticker": "A", "current_value": 500.0, "expected_annual": 50.0},
            {"ticker": "B", "current_value": 500.0, "expected_annual": 50.0},
        ])
        cache = {
            "A": {"true_dgr": 0.08, "earningsGrowth": 0.30},     # true_dgr wins
            "B": {"earningsGrowth": 0.02},                       # proxy fallback
        }
        inc = _stage5_income(pf, cache, 1000.0)
        assert inc.weighted_dgr == pytest.approx(0.5 * 0.08 + 0.5 * 0.02)

    def test_income_stability_from_dps_history(self):
        this_year = dt.datetime.now(dt.timezone.utc).year
        pf = pd.DataFrame([
            {"ticker": "AR", "current_value": 500.0, "expected_annual": 80.0},
            {"ticker": "CT", "current_value": 500.0, "expected_annual": 20.0},
        ])
        cache = {
            # aristocrat: 10+ payment years, 10+ growth streak, no cut → 8.0
            "AR": {"dividend_payment_years": 12, "dividend_growth_streak": 12,
                   "dividend_last_cut_year": None},
            # recent cutter: some history, streak 1, cut last year → 0.4*3 + 0.4*1 + 0
            "CT": {"dividend_payment_years": 3, "dividend_growth_streak": 1,
                   "dividend_last_cut_year": this_year - 1},
        }
        inc = _stage5_income(pf, cache, 1000.0)
        # AR: min(12,10)*.4 + min(12,10)*.4 + 2 = 10 (clamped)
        # CT: 3*.4 + 1*.4 + 0 (recent cut) = 1.6
        # weighted: 0.8*10 + 0.2*1.6 = 8.32
        assert inc.income_stability == pytest.approx(8.32, abs=1e-2)


# ══════════════════════════════════════════════════════════════════════════════
# Risk Stage 6 — stress testing & Monte Carlo
# ══════════════════════════════════════════════════════════════════════════════

class TestStage6Stress:
    @pytest.fixture
    def inputs(self):
        pf = pd.DataFrame([
            {"ticker": "CYC", "current_value": 700.0, "sector": "Energy",
             "expected_annual": 20.0},
            {"ticker": "DEF", "current_value": 300.0, "sector": "Utilities",
             "expected_annual": 10.0},
        ])
        cache = {"CYC": {"trailingPE": 20.0, "debtToEquity": 200.0},
                 "DEF": {"debtToEquity": 50.0}}
        conc = _stage2_concentration(pf, 1000.0)
        return pf, cache, conc

    def test_historical_scenarios_beta_scaled(self, inputs):
        pf, cache, conc = inputs
        s = _stage6_stress(pf, cache, 1.0, 1000.0, None, conc)
        covid = next(r for r in s.historical if "COVID" in r.name)
        assert covid.portfolio_drawdown == pytest.approx(-0.34)
        assert covid.portfolio_value_loss == pytest.approx(340.0)

        s2 = _stage6_stress(pf, cache, 2.0, 1000.0, None, conc)
        covid2 = next(r for r in s2.historical if "COVID" in r.name)
        assert covid2.portfolio_drawdown == pytest.approx(-0.68)

    def test_factor_scenarios(self, inputs):
        pf, cache, conc = inputs
        s = _stage6_stress(pf, cache, 1.0, 1000.0, None, conc)
        by_name = {fs["name"]: fs for fs in s.factor_scenarios}

        # Rate rise: only CYC has PE → 0.7 × (20/20) × −0.12 = −0.084
        assert by_name["Rate rise +200 bps"]["estimated_portfolio_impact"] == \
            pytest.approx(-0.084)
        # Recession: 0.7×−0.25 + 0.3×−0.10 = −0.205
        assert by_name["Recession (earnings cut 20–30%)"]["estimated_portfolio_impact"] == \
            pytest.approx(-0.205)
        # Sector crash: largest sector (Energy, 70%) × −0.40 = −0.28
        sector = next(v for k, v in by_name.items() if k.startswith("Sector crash"))
        assert sector["estimated_portfolio_impact"] == pytest.approx(-0.28)
        # Credit crunch: 0.7×−min(2.0×0.05,0.3) + 0.3×−min(0.5×0.05,0.3)
        assert by_name["Credit crunch"]["estimated_portfolio_impact"] == \
            pytest.approx(0.7 * -0.10 + 0.3 * -0.025)
        # Dividend freeze: full annual income
        assert by_name["Dividend freeze"]["estimated_loss_eur"] == pytest.approx(30.0)

    def test_monte_carlo_deterministic_and_ordered(self, inputs):
        pf, cache, conc = inputs
        s1 = _stage6_stress(pf, cache, 1.0, 1000.0, None, conc)
        s2 = _stage6_stress(pf, cache, 1.0, 1000.0, None, conc)
        assert s1.mc_1y == s2.mc_1y            # seeded → reproducible

        for mc in (s1.mc_1y, s1.mc_3y, s1.mc_5y):
            assert mc.p05 <= mc.p25 <= mc.p50 <= mc.p75 <= mc.p95
            assert 0.0 <= mc.prob_loss <= 1.0
        # Longer horizon with positive drift → lower probability of loss
        assert s1.mc_5y.prob_loss < s1.mc_1y.prob_loss

    def test_monte_carlo_drift_plausible(self, inputs):
        # beta 1.0 → mu = (3% + 5%)/252 daily, sigma = 1.2% daily.
        # Median 1y outcome should land near exp(mu·252 − σ²·252/2) − 1 ≈ 4–8%.
        pf, cache, conc = inputs
        s = _stage6_stress(pf, cache, 1.0, 1000.0, None, conc)
        assert 0.0 < s.mc_1y.p50 < 0.15
        assert 0.20 < s.mc_1y.prob_loss < 0.50


# ══════════════════════════════════════════════════════════════════════════════
# Risk WS-6 — historical replay + bootstrap Monte Carlo
# ══════════════════════════════════════════════════════════════════════════════

class TestReplayDrawdown:
    def _series(self, start, n, seed=0):
        idx = pd.bdate_range(start, periods=n)
        rng = np.random.default_rng(seed)
        return pd.Series(rng.normal(0.0002, 0.01, n), index=idx)

    def test_none_or_empty(self):
        assert risk._replay_drawdown(None, "2022-01-03", "2022-10-12") is None
        assert risk._replay_drawdown(pd.Series(dtype=float), "2022-01-03", "2022-10-12") is None

    def test_series_starting_after_window_is_not_covered(self):
        s = self._series("2023-01-02", 400)
        assert risk._replay_drawdown(s, "2022-01-03", "2022-10-12") is None

    def test_partial_coverage_below_threshold(self):
        # starts before the window but ends ~2.5 months in — far short of the
        # ~9 month window, so coverage < 0.6
        s = self._series("2021-10-01", 120)          # ~2021-10-01 .. 2022-03-18
        assert risk._replay_drawdown(s, "2022-01-03", "2022-10-12", min_coverage=0.6) is None

    def test_covered_window_returns_segment_drawdown(self):
        idx = pd.bdate_range("2021-01-04", periods=700)
        rets = np.full(700, 0.0002)
        # a clean −20% peak-to-trough entirely inside the 2022 window
        w = (idx >= "2022-02-01") & (idx <= "2022-06-01")
        rets[w] = np.log(0.80) / w.sum()          # spread the drop evenly
        s = pd.Series(rets, index=idx)
        dd = risk._replay_drawdown(s, "2022-01-03", "2022-10-12")
        assert dd == pytest.approx(-0.20, abs=0.02)


class TestStage6HistoricalReplay:
    def _conc(self, pf):
        return _stage2_concentration(pf, float(pf["current_value"].sum()))

    def test_2022_window_is_replayed_others_beta_estimated(self):
        pf = pd.DataFrame([{"ticker": "A", "current_value": 1000.0,
                            "sector": "Technology", "expected_annual": 0.0}])
        # 6y of history so the 2022 window is fully covered, dot-com/GFC are not
        idx = pd.bdate_range("2020-06-01", periods=1500)
        rets = np.full(len(idx), 0.0003)
        w = (idx >= "2022-01-03") & (idx <= "2022-10-12")
        rets[w] = np.log(0.75) / w.sum()          # −25% over the window
        port_rets = pd.Series(rets, index=idx)

        s = _stage6_stress(pf, {"A": {}}, 1.3, 1000.0, port_rets, self._conc(pf))
        by = {r.name: r for r in s.historical}
        assert by["2022 rate hike cycle"].method == "replayed"
        assert by["2022 rate hike cycle"].portfolio_drawdown == pytest.approx(-0.25, abs=0.02)
        # not covered → beta × benchmark drawdown
        assert by["Dot-com crash"].method == "beta-estimated"
        assert by["Dot-com crash"].portfolio_drawdown == pytest.approx(1.3 * -0.49, abs=1e-6)

    def test_no_history_all_beta_estimated(self):
        pf = pd.DataFrame([{"ticker": "A", "current_value": 1000.0,
                            "sector": "Technology", "expected_annual": 0.0}])
        s = _stage6_stress(pf, {"A": {}}, 1.0, 1000.0, None, self._conc(pf))
        assert all(r.method == "beta-estimated" for r in s.historical)


class TestMonteCarloBootstrap:
    def _fat_series(self, n=800, seed=1):
        idx = pd.bdate_range("2021-01-04", periods=n)
        rng = np.random.default_rng(seed)
        r = rng.normal(0.0003, 0.007, n)
        r[rng.integers(0, n, size=12)] = -0.08          # a dozen crash days
        return pd.Series(r, index=idx)

    def _conc(self, pf):
        return _stage2_concentration(pf, float(pf["current_value"].sum()))

    def test_deterministic_and_ordered_on_bootstrap_path(self):
        pf = pd.DataFrame([{"ticker": "A", "current_value": 1000.0,
                            "sector": "Tech", "expected_annual": 0.0}])
        pr = self._fat_series()
        s1 = _stage6_stress(pf, {"A": {}}, 1.0, 1000.0, pr, self._conc(pf))
        s2 = _stage6_stress(pf, {"A": {}}, 1.0, 1000.0, pr, self._conc(pf))
        assert s1.mc_1y == s2.mc_1y
        for mc in (s1.mc_1y, s1.mc_3y, s1.mc_5y):
            assert mc.p05 <= mc.p25 <= mc.p50 <= mc.p75 <= mc.p95
            assert 0.0 <= mc.prob_loss <= 1.0

    def test_fat_tailed_bootstrap_p05_not_lighter_than_normal(self):
        pf = pd.DataFrame([{"ticker": "A", "current_value": 1000.0,
                            "sector": "Tech", "expected_annual": 0.0}])
        pr = self._fat_series()
        boot = _stage6_stress(pf, {"A": {}}, 1.0, 1000.0, pr, self._conc(pf)).mc_1y

        # matched-moment Normal MC over the same horizon / path count / seed
        drift = (risk.RISK_FREE_RATE + 1.0 * risk.EQUITY_RISK_PREMIUM) / risk.TRADING_DAYS
        r = pr.to_numpy()
        r = r - r.mean() + drift
        rng = np.random.default_rng(risk.MONTE_CARLO_SEED)
        paths = rng.normal(r.mean(), r.std(ddof=1),
                           size=(risk.MONTE_CARLO_PATHS, risk.TRADING_DAYS))
        cum = np.prod(1.0 + np.clip(paths, -0.5, 1.0), axis=1) - 1.0
        normal_p05 = float(np.percentile(cum, 5))

        assert boot.p05 <= normal_p05 + 1e-6      # bootstrap keeps the fat left tail


# ══════════════════════════════════════════════════════════════════════════════
# Risk Stage 7 — composite score
# ══════════════════════════════════════════════════════════════════════════════

class TestStage7:
    def test_weight_sets_sum_to_one(self):
        assert sum(risk._W_DEFAULT.values()) == pytest.approx(1.0)
        assert sum(risk._W_INCOME.values()) == pytest.approx(1.0)

    def test_fundamental_score_weighting(self):
        def prof(ticker, weight, rating):
            return PositionRisk(ticker=ticker, name=ticker, weight=weight,
                                beta=None, var_95_1d_eur=None, vol_annual=None, mos=None,
                                valuation_flag="N/A", div_sustainability="",
                                financial_health=5.0, earnings_quality=5.0,
                                rating=rating)
        assert _score_fundamental([prof("A", 0.5, "Low"),
                                   prof("B", 0.5, "Low")]) == 0.0
        assert _score_fundamental([prof("A", 0.5, "Critical"),
                                   prof("B", 0.5, "Critical")]) == 100.0
        # 50/50 Low+Critical → 50
        assert _score_fundamental([prof("A", 0.5, "Low"),
                                   prof("B", 0.5, "Critical")]) == pytest.approx(50.0)
        assert _score_fundamental([]) == 50.0


# ══════════════════════════════════════════════════════════════════════════════
# Risk Stage 8 — rebalancing signals
# ══════════════════════════════════════════════════════════════════════════════

class TestStage8:
    def test_hard_and_soft_triggers(self):
        profiles = [PositionRisk(
            ticker="BIG", name="Big Co", weight=0.25, beta=1.0,
            var_95_1d_eur=10.0, vol_annual=None, mos=0.1, valuation_flag="Undervalued",
            div_sustainability="OK", financial_health=7.0,
            earnings_quality=7.0, rating="Low")]
        conc = ConcentrationMetrics(
            hhi=0.16, hhi_label="Moderately concentrated", top1_weight=0.25,
            top1_ticker="BIG", top3_weight=0.6, top5_weight=0.8,
            top1_flag=True, top3_flag=True, top5_flag=True,
            sector_weights={"Tech": 0.4}, largest_sector="Tech",
            sector_flag=True, geo_weights={}, largest_geo=None, geo_flag=False,
            div_hhi=None, div_top3_pct=None, income_concentration_flag=False)
        quant = QuantMetrics(
            portfolio_beta=1.6, beta_label="Aggressive", volatility_annual=0.2,
            volatility_label="Moderate", var_95_1d_pct=-0.03, var_95_1d_eur=100.0,
            var_99_1d_eur=None, cvar_95_1d_eur=None, mdd_1y=None, mdd_3y=None,
            mdd_5y=None, mdd_label="N/A", sharpe=0.5, sortino=None,
            ratio_label="Suboptimal", corr_matrix=None,
            high_corr_pairs=[("A", "B", 0.9)], effective_diversification=None,
            returns_available=False)
        income = IncomeRisk(
            portfolio_yield=0.03, total_annual_income=100.0, weighted_dgr=0.01,
            top3_income_shares=[("A", 0.5), ("B", 0.3), ("C", 0.2)],
            top3_cut_eur=50.0, top3_cut_pct=0.45,
            income_concentration_flag=True, flagged_payers=["A", "B"],
            flagged_income_pct=0.45)
        mc = MonteCarloResult(1, -0.2, -0.05, 0.05, 0.15, 0.3, 0.3)
        stress = StressResults(
            historical=[ScenarioResult("Crash", "x", -0.30, -0.45, 450.0)],
            factor_scenarios=[], mc_1y=mc, mc_3y=mc, mc_5y=mc)

        r = _stage8_rebalance(profiles, conc, quant, income, stress, 1000.0)

        hard_text = " | ".join(r.hard_triggers)
        assert "BIG" in hard_text and "20%" in hard_text     # overweight position
        assert "beta 1.60" in hard_text                       # excessive beta
        assert "45%" in hard_text                             # dividend-at-risk income share
        assert "-45%" in hard_text                            # worst drawdown

        soft_text = " | ".join(r.soft_triggers)
        assert "HHI" in soft_text
        assert "Tech" in soft_text                            # sector guideline
        assert "DGR" in soft_text                             # income growth < 2.5%
        assert "Sharpe" in soft_text
        assert "A/B" in soft_text                             # correlated pair


# ══════════════════════════════════════════════════════════════════════════════
# Prices helper
# ══════════════════════════════════════════════════════════════════════════════

class TestPrices:
    def test_day_change(self):
        assert _day_change(110.0, 100.0) == pytest.approx(10.0)
        assert _day_change(95.0, 100.0) == pytest.approx(-5.0)
        assert _day_change(None, 100.0) is None
        assert _day_change(100.0, None) is None
