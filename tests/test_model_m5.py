"""Model M5 (exchange expansion EX-W5b, decisions D33–D35, plan P8).

Uses the fixed risk-free snapshot from conftest (EUR 3%, CHF 1%, GBP 4.5%,
no ISK).
"""
import pandas as pd
import pytest

import screener
from uvalu import riskfree


def _off(*keys):
    screener._m5_state.update({k: False for k in keys})


# ── riskfree snapshot ─────────────────────────────────────────────────────

class TestRiskFreeSnapshot:
    def test_rate_per_currency(self):
        assert riskfree.rate("EUR") == 0.03
        assert riskfree.rate("chf") == 0.01
        assert riskfree.rate("GBp") == 0.045      # pence share the pound's rate
        assert riskfree.rate("ISK") is None
        assert riskfree.rate(None) is None

    def test_committed_snapshot_has_the_bund_and_the_planned_currencies(self, monkeypatch):
        from pathlib import Path
        monkeypatch.setattr(riskfree, "SNAPSHOT",
                            Path(riskfree.__file__).parent / "risk_free_rates.json")
        riskfree._data.cache_clear()
        rates = riskfree.rates()
        assert {"EUR", "CHF", "GBP", "SEK", "DKK", "NOK", "PLN"} <= set(rates)
        assert all(0 < r < 0.15 for r in rates.values())
        assert riskfree.as_of() and riskfree.period("EUR")


# ── D33: rate per currency ────────────────────────────────────────────────

class TestRatePerCurrency:
    def test_wacc_uses_the_currency_rate(self):
        assert screener._approx_wacc(1.0, "CHF") == pytest.approx(0.01 + 0.05)
        assert screener._approx_wacc(1.0, "GBP") == pytest.approx(0.045 + 0.05)
        assert screener._approx_wacc(1.0) == pytest.approx(0.08)   # no currency: EUR

    def test_currency_without_a_rate_uses_eur_and_is_unknown(self):
        assert screener._risk_free("ISK") == (0.03, False)
        assert screener._risk_free("EUR") == (0.03, True)

    def test_switch_off_is_m4(self):
        _off("m5_rate_per_currency")
        assert screener._risk_free("CHF") == (screener.RISK_FREE_RATE, True)
        assert screener._risk_free("ISK") == (screener.RISK_FREE_RATE, True)

    def test_portfolio_rate_is_the_eur_rate(self):
        assert screener.portfolio_risk_free() == 0.03


# ── D34: EPV tax ──────────────────────────────────────────────────────────

class TestEpvTax:
    def test_known_and_unknown_registrations(self):
        assert screener._epv_tax_rate("Germany") == 0.30
        assert screener._epv_tax_rate("Bermuda") == screener.DEFAULT_TAX_RATE
        assert screener._epv_tax_rate("Estonia") == 0.22

    def test_near_zero_rate_uses_the_default(self, monkeypatch):
        monkeypatch.setitem(screener.COUNTRY_TAX_RATES, "Jersey", 0.0)
        assert screener._epv_tax_rate("Jersey") == screener.DEFAULT_TAX_RATE

    def test_switch_off_is_m4(self, monkeypatch):
        monkeypatch.setitem(screener.COUNTRY_TAX_RATES, "Jersey", 0.0)
        _off("m5_epv_tax_floor")
        assert screener._epv_tax_rate("Jersey") == 0.0
        assert screener._epv_tax_rate("Estonia") == screener.DEFAULT_TAX_RATE


# ── D35: liquidity in EUR ─────────────────────────────────────────────────

class TestLiquidityEur:
    @pytest.mark.parametrize("value,score", [
        (20_000_000, 10.0), (15_000_000, 10.0), (3_000_000, 7.5),
        (600_000, 5.0), (100_000, 2.5)])
    def test_bands_on_traded_value(self, value, score):
        row = pd.Series({"averageVolume": 1_000, "traded_value_eur": value})
        assert screener._liquidity_score(row) == score

    def test_expensive_share_no_longer_illiquid(self):
        # Model review M5: one Maersk share costs about DKK 24,000.
        row = pd.Series({"averageVolume": 20_000, "traded_value_eur": 20_000 * 3_200})
        assert screener._liquidity_score(row) == 10.0

    def test_confirmed_zero_and_missing_stay_as_before(self):
        assert screener._liquidity_score(pd.Series({"averageVolume": 0, "traded_value_eur": 0})) == 0.0
        assert screener._liquidity_score(pd.Series({"averageVolume": None})) == 5.0

    def test_no_value_falls_back_to_shares(self):
        assert screener._liquidity_score(pd.Series({"averageVolume": 600_000})) == 10.0

    def test_switch_off_uses_shares(self):
        _off("m5_liquidity_eur")
        row = pd.Series({"averageVolume": 20_000, "traded_value_eur": 64_000_000})
        assert screener._liquidity_score(row) == 2.5

    def test_traded_value_converts_to_eur(self):
        df = pd.DataFrame({"averageVolume": [1_000, 1_000, None, 1_000],
                           "Price": [10.0, 10.0, 10.0, 500.0],
                           "Currency": ["EUR", "CHF", "EUR", "GBp"]})
        rates = {("CHF", "EUR"): 1.05, ("GBP", "EUR"): 1.2}
        out = screener._traded_value_eur(df, rate_fn=lambda a, b: rates[(a, b)])
        assert out[0] == pytest.approx(10_000)
        assert out[1] == pytest.approx(10_500)
        assert out[2] is None
        assert out[3] == pytest.approx(1_000 * 5.0 * 1.2)


# ── switches and version ──────────────────────────────────────────────────

class TestSwitches:
    def test_version_follows_the_switches(self):
        assert screener.model_version() == "M5"
        _off("m5_liquidity_eur")
        assert screener.model_version() == "M5*"
        _off(*screener.M5_SWITCHES)
        assert screener.model_version() == "M4"

    def test_switches_read_from_shared_settings(self):
        state = screener.refresh_model_switches({"m5_epv_tax_floor": False})
        assert state == {"m5_rate_per_currency": True, "m5_epv_tax_floor": False,
                         "m5_liquidity_eur": True}

    def test_settings_id_changes_with_a_switch(self):
        kw = dict(max_debt_equity=500, max_payout=0.9, min_mos=0.1, buy_threshold=70,
                  weights=(0.24, 0.22, 0.24, 0.15, 0.15))
        before = screener.model_settings_id(**kw)
        _off("m5_rate_per_currency")
        assert screener.model_settings_id(**kw) != before

    def test_shared_defaults_switch_m5_on(self):
        import settings
        assert all(settings._SHARED_DEFAULTS[k] is True for k in screener.M5_SWITCHES)


# ── a currency without a rate stays out of Undervalued ────────────────────

def test_rate_missing_keeps_a_row_out_of_undervalued(monkeypatch):
    monkeypatch.setattr(screener, "refresh_model_switches", lambda shared=None: dict(screener._m5_state))
    rows = []
    for i in range(30):
        rows.append({"Ticker": f"T{i}.AS", "Price": 10.0, "Currency": "EUR", "sector": "Industrials",
                     "trailingEps": 1.0 + i / 10, "bookValue": 8.0, "beta": 1.0,
                     "averageVolume": 100_000, "marketCap": 1e9, "sharesOutstanding": 1e8})
    rows[0]["Currency"] = "ISK"
    out = screener.compute_scores(pd.DataFrame(rows))
    isk = out[out["Ticker"] == "T0.AS"].iloc[0]
    assert bool(isk["rate_missing"]) is True
    assert "risk_free_rate_missing" in isk["data_flags"]
    assert isk["signal_code"] != screener.SIGNAL_UNDERVALUED
    assert not out[out["Ticker"] != "T0.AS"]["rate_missing"].any()
    assert (out["model_version"] == "M5").all()
