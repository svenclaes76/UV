"""V3 (model M3): normalised EPS for the P/E and Graham models, growth from
the history, and the one-off flag (docs/valuation-model-review.md V3)."""

import pandas as pd
import pytest

import screener as sc


def test_a_one_off_year_no_longer_sets_the_eps():
    # Newprinces-like: a disposal gain makes the latest year 10× the others.
    row = pd.Series({"Price": 20.0, "trailingEps": 7.5, "sharesOutstanding": 1.0,
                     "netIncomeHistory": [7.5, 0.8, 0.7, 0.75]})
    eps, basis = sc._normalised_eps(row)
    assert basis == "normalised"
    assert eps == pytest.approx((0.75 + 0.8) / 2)        # 7.5 and 0.7 trimmed


def test_without_three_years_the_trailing_eps_is_used():
    row = pd.Series({"trailingEps": 2.0, "sharesOutstanding": 1.0, "netIncomeHistory": [2.0, 1.0]})
    assert sc._normalised_eps(row) == (2.0, "trailing")
    assert sc._normalised_eps(pd.Series({"trailingEps": 2.0})) == (2.0, "trailing")


def test_growth_needs_positive_ends():
    assert sc._tilt_growth(pd.Series({"netIncomeHistory": [2.0, 1.0, -0.5]})) is None
    assert sc._tilt_growth(pd.Series({"netIncomeHistory": [4.0, 2.0, 1.0]})) == pytest.approx(1.0)


def test_one_off_suspect_flag_only_on_trailing_basis():
    df = pd.DataFrame([
        {"eps_basis": "trailing", "trailingPE": 1.8},      # WE.CONNECT-like
        {"eps_basis": "normalised", "trailingPE": 1.8},    # history already handled it
        {"eps_basis": "trailing", "trailingPE": 9.0},
        {"eps_basis": "trailing", "trailingPE": None},
    ])
    assert list(sc._eps_one_off_suspect(df)) == [True, False, False, False]


def test_a_suspect_row_is_never_undervalued_and_carries_the_flag():
    rows = [{"Ticker": f"P{i}.PA", "Price": 10.0, "trailingEps": 1.0 + i / 20, "bookValue": 8.0,
             "trailingPE": 9.0, "sector": "Industrials"} for i in range(25)]
    rows.append({"Ticker": "ALWEC.PA", "Price": 22.8, "trailingEps": 12.72, "bookValue": 33.0,
                 "trailingPE": 1.8, "sector": "Industrials", "beta": 1.0})
    out = sc.run_screener_from_df(pd.DataFrame(rows), min_mos=0.10)
    r = out[out["Ticker"] == "ALWEC.PA"].iloc[0]
    assert r["signal_code"] != sc.SIGNAL_UNDERVALUED
    assert "eps_one_off_suspect" in r["data_flags"]


def test_a_one_class_share_count_is_replaced_by_the_implied_count():
    # CBE.PA-like: sharesOutstanding covers one class; market cap ÷ price
    # gives the whole company's count.
    row = pd.Series({"Price": 620.1, "trailingEps": 45.26, "sharesOutstanding": 122_792.0,
                     "marketCap": 1_300_959_872.0,
                     "netIncomeHistory": [103_427_000.0, 90_068_000.0, 74_598_000.0, 76_020_000.0]})
    eps, basis = sc._normalised_eps(row)
    assert basis == "normalised"
    assert 30.0 < eps < 60.0           # per share of the whole company, not ~700


def test_a_plausible_share_count_is_kept_even_with_a_one_off():
    # DR0.DE-like: price × shares matches the market cap; the trailing EPS
    # holds a one-off, which must not change the share count.
    row = pd.Series({"Price": 85.7, "trailingEps": 31.9, "sharesOutstanding": 5_000_000.0,
                     "marketCap": 428_500_000.0,
                     "netIncomeHistory": [160_000_000.0, 40_000_000.0, 35_000_000.0, 30_000_000.0]})
    assert sc._eps_share_count(row) == 5_000_000.0
