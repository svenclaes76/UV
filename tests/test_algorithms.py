"""
Algorithm validation suite — checks the screener (6-stage valuation) and
risk (8-stage assessment) math against hand-computed expected values.

All tests are offline: synthetic DataFrames and cache dicts, no yfinance calls.

Run:  python -m pytest tests/ -v
"""

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
    _financial_health_score,
    _earnings_quality_score,
    _market_risk_score,
    _dividend_risk_score,
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
    _ratio_label,
    _position_rating,
    _risk_label_action,
    _stage1_position_profiles,
    _stage2_concentration,
    _stage3_quant,
    _stage5_income,
    _stage6_stress,
    _stage8_rebalance,
    _score_fundamental,
    PositionRisk,
    ConcentrationMetrics,
    QuantMetrics,
    IncomeRisk,
    ScenarioResult,
    MonteCarloResult,
    StressResults,
)
from prices import _day_change


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

    def test_zero_growth_is_respected_not_defaulted(self):
        # g=0.0 must mean zero growth (2/0.08 = 25), not the 2% missing-data default
        assert _ddm_single(2.0, 0.08, 0.0) == pytest.approx(25.0)
        assert _ddm_single(2.0, 0.08, None) == pytest.approx(34.0)   # default 2%
        assert _ddm_multistage(2.0, 0.08, 0.0) != pytest.approx(
            _ddm_multistage(2.0, 0.08, None))


class TestFairValueBlend:
    def test_weighted_average_of_available_models(self):
        # Only Graham (0.18), PE (0.18), analyst (0.25) available.
        row = pd.Series({"Price": 50.0, "trailingEps": 5.0, "bookValue": 20.0,
                         "targetMeanPrice": 90.0})
        fv = _fair_value_models(row)
        gn, pe, an = 2250 ** 0.5, 75.0, 90.0
        expected = (gn * 0.18 + pe * 0.18 + an * 0.25) / (0.18 + 0.18 + 0.25)
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

        good = out[out["Ticker"] == "GOOD"].iloc[0]
        meh = out[out["Ticker"] == "MEH"].iloc[0]
        assert good["Value Score"] > meh["Value Score"]

        # Fair value blend for GOOD: Graham + PE + analyst only
        gn, pe, an = 2250 ** 0.5, 75.0, 90.0
        expected_fv = (gn * 0.18 + pe * 0.18 + an * 0.25) / 0.61
        assert good["fair_value"] == pytest.approx(expected_fv, abs=0.01)
        assert good["MoS %"] == pytest.approx(
            (expected_fv - 50.0) / expected_fv * 100, abs=0.1)

    def test_rows_without_price_dropped(self, synthetic_universe):
        df = synthetic_universe.copy()
        df.loc[len(df)] = {"Name": "Ghost", "Ticker": "GHOST"}   # no price
        out = run_screener_from_df(df)
        assert "GHOST" not in set(out["Ticker"])
        assert len(out) == 4


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
        assert _ratio_label(None, 1.6) == "Strong"
        assert _ratio_label(1.2, None) == "Acceptable"
        assert _ratio_label(0.5, None) == "Suboptimal"
        assert _ratio_label(None, None) == "N/A"

    def test_risk_label_boundaries(self):
        assert _risk_label_action(25.0)[0] == "Low risk"
        assert _risk_label_action(25.1)[0] == "Moderate risk"
        assert _risk_label_action(50.1)[0] == "Elevated risk"
        assert _risk_label_action(70.1)[0] == "High risk"
        assert _risk_label_action(85.1)[0] == "Critical risk"


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
            income_concentration_flag=True, flagged_payers=[],
            flagged_income_pct=0.0)
        mc = MonteCarloResult(1, -0.2, -0.05, 0.05, 0.15, 0.3, 0.3)
        stress = StressResults(
            historical=[ScenarioResult("Crash", "x", -0.30, -0.45, 450.0)],
            factor_scenarios=[], mc_1y=mc, mc_3y=mc, mc_5y=mc)

        r = _stage8_rebalance(profiles, conc, quant, income, stress, 1000.0)

        hard_text = " | ".join(r.hard_triggers)
        assert "BIG" in hard_text and "20%" in hard_text     # overweight position
        assert "beta 1.60" in hard_text                       # excessive beta
        assert "45%" in hard_text                             # income cut scenario
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
