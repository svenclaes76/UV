"""portfolio_enrichment.enrich_for_risk — builds the frame risk.assess_portfolio
expects from a raw portfolio + the screener's scored DataFrame + a price feed."""
import pandas as pd

from portfolio_enrichment import enrich_for_risk


def _pf():
    return pd.DataFrame([
        {"ticker": "AAA.BR", "name": "Alpha", "shares": 10},
        {"ticker": "BBB.PA", "name": "Beta", "shares": 4},
    ])


def _scored():
    return pd.DataFrame([
        {"Ticker": "AAA.BR", "fair_value": 120.0, "sector": "Tech",
         "country": "Belgium", "trailingAnnualDividendRate": 3.0, "dividendRate": None},
        {"Ticker": "BBB.PA", "fair_value": 55.0, "sector": "Health",
         "country": "France", "trailingAnnualDividendRate": None, "dividendRate": 1.5},
    ]).set_index("Ticker")


def test_maps_price_and_scored_fields():
    prices = {"AAA.BR": {"price": 100.0}, "BBB.PA": {"price": 50.0}}
    out = enrich_for_risk(_pf(), _scored(), prices)

    a = out.set_index("ticker").loc["AAA.BR"]
    assert a["live_price"] == 100.0
    assert a["current_value"] == 1000.0            # 100 × 10
    assert a["fair_value"] == 120.0
    assert a["sector"] == "Tech" and a["country"] == "Belgium"
    assert a["div_rate"] == 3.0
    assert a["expected_annual"] == 30.0            # 3.0 × 10

    b = out.set_index("ticker").loc["BBB.PA"]
    assert b["div_rate"] == 1.5                    # falls back to dividendRate
    assert b["expected_annual"] == 6.0


def test_missing_price_leaves_value_nan_not_crash():
    out = enrich_for_risk(_pf(), _scored(), {"AAA.BR": {"price": 100.0}})
    b = out.set_index("ticker").loc["BBB.PA"]
    assert pd.isna(b["live_price"]) and pd.isna(b["current_value"])


def test_none_scored_frame_yields_nan_fields_and_zero_income():
    out = enrich_for_risk(_pf(), None, {"AAA.BR": {"price": 100.0}, "BBB.PA": {"price": 50.0}})
    assert out["fair_value"].isna().all()
    assert out["sector"].isna().all()
    assert (out["div_rate"] == 0).all()
    assert (out["expected_annual"] == 0).all()


def test_does_not_mutate_the_input():
    pf = _pf()
    enrich_for_risk(pf, _scored(), {"AAA.BR": {"price": 100.0}})
    assert "live_price" not in pf.columns
