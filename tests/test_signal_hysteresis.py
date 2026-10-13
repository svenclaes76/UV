"""Q1 (model M2): a stock keeps its band until its score falls
SIGNAL_HYSTERESIS points past the edge (docs/quant-review.md Q1)."""

import pandas as pd

import screener as sc

U, N, L = sc.SIGNAL_UNDERVALUED, sc.SIGNAL_NEUTRAL, sc.SIGNAL_LOW_SCORE


def _df(code, score, mos=0.20, thin=False, ccy=False):
    return pd.DataFrame([{"Ticker": "T.BR", "signal_code": code, "Value Score": score,
                          "margin_of_safety": mos, "fv_basis_thin": thin, "currency_unverified": ccy}])


def _apply(df, prev):
    return sc._apply_signal_hysteresis(df, {"T.BR": prev}, buy_threshold=70.0, min_mos=0.10).iloc[0]


def test_a_small_dip_below_40_keeps_mid_score():
    assert _apply(_df(L, 39.9), N) == N       # the SRAIL.SW flicker
    assert _apply(_df(L, 38.0), N) == N
    assert _apply(_df(L, 37.9), N) == L       # a real drop still moves it


def test_a_small_dip_below_70_keeps_undervalued_if_everything_else_holds():
    assert _apply(_df(N, 69.0), U) == U
    assert _apply(_df(N, 67.9), U) == N


def test_the_margin_of_safety_floor_stays_strict():
    # D1: Undervalued never below the 10% minimum, hysteresis or not.
    assert _apply(_df(N, 69.0, mos=0.09), U) == N
    assert _apply(_df(N, 69.0, thin=True), U) == N
    assert _apply(_df(N, 69.0, ccy=True), U) == N


def test_entry_into_a_higher_band_is_unchanged():
    assert _apply(_df(N, 40.0), L) == N
    assert _apply(_df(U, 70.0), N) == U


def test_no_history_means_the_plain_thresholds():
    df = _df(L, 39.9)
    assert sc._apply_signal_hysteresis(df, {}, buy_threshold=70.0, min_mos=0.10).iloc[0] == L


def test_vetoes_are_never_softened():
    assert _apply(_df(sc.SIGNAL_FAILS, 39.9), N) == sc.SIGNAL_FAILS
