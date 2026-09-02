"""Shared-component tests (redesign Phase 2): signal badge, fair-value ladder,
signals feed — see uvalu/components.py.

Pure mapping functions are asserted directly; the render_* functions (which
call st.markdown/st.caption) are exercised through AppTest so a broken f-string
or missing import fails loudly instead of only showing up visually.
"""
import pandas as pd
from streamlit.testing.v1 import AppTest

import numpy as np

from uvalu.components import (signal_badge_for_decision, signal_badge_html, is_hard_veto,
                              score_color, radial_gauge_svg, sub_score_bar_html,
                              sparkline_svg, veto_reason_str, _fair_value_bar_html,
                              holdings_row_html, _score_bar_cell_html,
                              quality_score_color, _gain_color)


def test_signal_badge_for_decision_maps_known_labels():
    assert signal_badge_for_decision("Strong Buy") == ("buy", "BUY")
    assert signal_badge_for_decision("Monitor") == ("monitor", "MONITOR")
    assert signal_badge_for_decision("Avoid") == ("avoid", "AVOID")


def test_signal_badge_for_decision_veto_overrides_decision():
    assert signal_badge_for_decision("Strong Buy", veto=True) == ("veto", "VETO")


def test_signal_badge_for_decision_missing_decision_is_nodata_not_avoid():
    # A holding with no scored screener row (fundamentals gap) has no Decision
    # and a NaN veto cell — it must read as "NO DATA", never AVOID or (via
    # bool(nan)) VETO (WP-DQ6).
    assert signal_badge_for_decision("") == ("neutral", "NO DATA")
    assert signal_badge_for_decision(None) == ("neutral", "NO DATA")
    assert signal_badge_for_decision(np.nan) == ("neutral", "NO DATA")
    assert signal_badge_for_decision("Something Else") == ("neutral", "NO DATA")
    assert signal_badge_for_decision(np.nan, veto=np.nan) == ("neutral", "NO DATA")


def test_is_hard_veto_is_nan_safe():
    assert is_hard_veto(True) is True
    assert is_hard_veto(False) is False
    assert is_hard_veto(None) is False
    assert is_hard_veto(np.nan) is False
    assert is_hard_veto(1) is True


def test_signal_badge_html_renders_expected_span():
    html = signal_badge_html("buy", "BUY")
    assert html == '<span class="uv-badge uv-badge-buy">BUY</span>'


def _run(fn) -> AppTest:
    at = AppTest.from_function(fn, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def test_render_signal_tips_renders_ok_and_warn_badges():
    def _script():
        from uvalu.components import render_signal_tips
        render_signal_tips([("ok", "Looks healthy."), ("warn", "Elevated risk.")])

    at = _run(_script)
    caption_html = "".join(c.value for c in at.caption)
    assert "uv-badge-ok" in caption_html
    assert "uv-badge-warn" in caption_html
    assert "Looks healthy." in caption_html


def test_render_signal_tips_noop_on_empty_list():
    def _script():
        from uvalu.components import render_signal_tips
        render_signal_tips([])
        import streamlit as st
        st.caption("sentinel")

    at = _run(_script)
    # Only the sentinel caption should exist — no empty "Signals" header.
    assert len(at.caption) == 1
    assert at.caption[0].value == "sentinel"


def test_fair_value_ladder_renders_bars_and_composite_row():
    def _script():
        from uvalu.components import fair_value_ladder
        fair_value_ladder(
            price=214.60,
            models=[("Graham #", 236.0), ("PE fair val", 261.0), ("Analyst", 245.0)],
            composite=256.0,
        )

    at = _run(_script)
    html = at.markdown[0].value
    assert "€236" in html and "€261" in html and "€245" in html
    # Composite is a flat label+value row (no bar/delta) — matches
    # Uvalu.dc.html's "Composite fair value" row exactly, distinct from the
    # per-model bar+value+delta rows above it.
    assert "Composite fair value" in html and "€256" in html


def test_fair_value_ladder_handles_missing_model_data():
    def _script():
        from uvalu.components import fair_value_ladder
        fair_value_ladder(price=100.0, models=[("Graham #", None)], composite=None)

    at = _run(_script)
    assert "Not enough model data" in at.caption[0].value


def test_fair_value_ladder_no_price_shows_caption():
    def _script():
        from uvalu.components import fair_value_ladder
        fair_value_ladder(price=None, models=[("Graham #", 120.0)], composite=None)

    at = _run(_script)
    assert "Not enough model data" in at.caption[0].value


def test_stock_row_without_action_hides_star():
    def _script():
        from uvalu.components import stock_row
        stock_row(key="row1", ticker="AAA.BR", name="Alpha Corp", exchange="Brussels",
                 decision="Strong Buy", veto=False, score=80.0, mos_pct=None,
                 price=100.0, pe=15.0, div_yield=0.03, show_action=False)

    at = _run(_script)
    assert not any(b.key == "row1_action" for b in at.button)


def test_stock_row_missing_mos_shows_dash():
    def _script():
        from uvalu.components import stock_row
        stock_row(key="row1", ticker="AAA.BR", name="Alpha Corp", exchange="Brussels",
                 decision="Strong Buy", veto=False, score=80.0, mos_pct=None,
                 price=100.0, pe=15.0, div_yield=0.03)

    at = _run(_script)
    html = "".join(m.value for m in at.markdown)
    assert "<div style='text-align:right;color:var(--muted);'>—</div>" in html


def test_portfolio_dividend_row_without_edit_hides_button():
    def _script():
        from uvalu.components import portfolio_dividend_row
        portfolio_dividend_row(key="div1", name="Alpha Corp", ticker="AAA.BR",
                               date="15 Mar 2024", amount=12.5, show_edit=False)

    at = _run(_script)
    assert len(at.button) == 0


def test_fair_value_ladder_shows_dash_for_unavailable_model_not_dropped_row():
    def _script():
        from uvalu.components import fair_value_ladder
        fair_value_ladder(
            price=100.0,
            models=[("Graham #", 120.0), ("EPV", None), ("Analyst", float("nan"))],
            composite=None,
        )

    at = _run(_script)
    html = at.markdown[0].value
    # All 3 rows render (fixed row count matches the design spec), including
    # the two with no data — they show a "–" placeholder instead of being
    # silently dropped from the list.
    assert "EPV" in html and "Analyst" in html
    # Each missing-data row shows 2 dashes (value column + delta column).
    assert html.count("–") == 4


def test_fair_value_bar_compact_flags_overvalued_vs_undervalued():
    def _script():
        from uvalu.components import fair_value_bar_compact
        fair_value_bar_compact(price=100.0, fair_value=120.0, mos_pct=16.7)
        fair_value_bar_compact(price=100.0, fair_value=90.0, mos_pct=-11.1)
        fair_value_bar_compact(price=100.0, fair_value=101.5, mos_pct=1.5)

    at = _run(_script)
    assert "var(--uv-mint)" in at.markdown[0].value
    assert "var(--uv-neg-txt)" in at.markdown[1].value
    assert "var(--teal" in at.markdown[2].value  # within the near-fair band
    # Shows the absolute price/fair-value figures instead of a below/above label
    assert "€100.00" in at.markdown[0].value and "fv €120.00" in at.markdown[0].value


def test_signals_feed_renders_bold_entity_and_message():
    def _script():
        from uvalu.components import signals_feed
        signals_feed([("#1DD6A4", "Enel", "crossed into BUY")])

    at = _run(_script)
    html = at.markdown[0].value
    assert "<b" in html and "Enel" in html and "crossed into BUY" in html


def test_signals_feed_empty_shows_caption():
    def _script():
        from uvalu.components import signals_feed
        signals_feed([])

    at = _run(_script)
    assert "No recent signals" in at.caption[0].value


def test_score_color_bands():
    assert score_color(20) == ("#1DD6A4", "#0F6E56")
    assert score_color(55) == ("#854F0B", "#854F0B")
    assert score_color(85) == ("#A32D2D", "#A32D2D")


def test_radial_gauge_svg_clamps_and_scales_offset():
    svg_zero = radial_gauge_svg(0, "#1DD6A4")
    svg_full = radial_gauge_svg(100, "#1DD6A4")
    svg_over = radial_gauge_svg(150, "#1DD6A4")
    assert "<svg" in svg_zero and "stroke-dashoffset" in svg_zero
    # Full score -> zero offset (ring fully drawn); out-of-range clamps to same as 100.
    assert 'stroke-dashoffset="0.00"' in svg_full
    assert svg_over == svg_full


def test_sub_score_bar_html_contains_label_and_value():
    html = sub_score_bar_html("Concentration", 58)
    assert "Concentration" in html
    assert "58" in html
    assert "#854F0B" in html  # 58 falls in the caution band


def test_sparkline_svg_returns_empty_for_insufficient_data():
    assert sparkline_svg([]) == ""
    assert sparkline_svg([5.0]) == ""


def test_sparkline_svg_renders_polyline_for_valid_series():
    svg = sparkline_svg([100, 105, 98, 110, 103])
    assert "<svg" in svg
    assert "<polyline" in svg
    assert "<polygon" in svg


class TestVetoReasonStr:
    def test_debt_to_equity_reason(self, isolated_data):
        row = pd.Series({"debtToEquity": 900.0})
        assert "debt/equity of 900%" in veto_reason_str(row)

    def test_negative_fcf_reason(self, isolated_data):
        row = pd.Series({"freeCashflow": -5_000_000.0})
        assert "negative free cash flow" in veto_reason_str(row)

    def test_dividend_at_risk_and_low_coverage_reason(self, isolated_data):
        row = pd.Series({"Div Flag": "At Risk", "dividendCoverage": 0.8})
        assert "dividend flagged at risk" in veto_reason_str(row)

    def test_at_risk_flag_alone_without_low_coverage_is_not_a_reason(self, isolated_data):
        # The dividend condition is a single AND-combined check, not two
        # independent ones — "At Risk" alone (coverage still healthy)
        # shouldn't surface as its own veto reason.
        row = pd.Series({"Div Flag": "At Risk", "dividendCoverage": 2.0})
        assert veto_reason_str(row) == "a hard-veto rule"

    def test_multiple_reasons_joined(self, isolated_data):
        row = pd.Series({"debtToEquity": 900.0, "freeCashflow": -1.0})
        result = veto_reason_str(row)
        assert "debt/equity" in result and "negative free cash flow" in result
        assert "; " in result

    def test_no_reasons_falls_back_to_generic_message(self, isolated_data):
        assert veto_reason_str(pd.Series({})) == "a hard-veto rule"

    def test_leverage_exempt_sector_does_not_surface_debt_reason(self, isolated_data):
        # Financial Services/Real Estate/Utilities are exempt from the D/E
        # veto (structural leverage, not distress) — high D/E alone shouldn't
        # surface as a reason for those sectors, matching screener.py's
        # _hard_veto formula.
        row = pd.Series({"debtToEquity": 900.0, "sector": "Financial Services"})
        assert veto_reason_str(row) == "a hard-veto rule"

    def test_single_bad_fcf_year_not_a_reason_with_three_year_history(self, isolated_data):
        # A single negative year no longer vetoes once 3-year fcfHistory
        # exists — only 3 consecutive negative years do.
        row = pd.Series({"freeCashflow": -1.0, "fcfHistory": [-1.0, 50.0, 80.0]})
        assert veto_reason_str(row) == "a hard-veto rule"

    def test_three_consecutive_negative_fcf_years_is_a_reason(self, isolated_data):
        row = pd.Series({"freeCashflow": -1.0, "fcfHistory": [-1.0, -2.0, -3.0]})
        assert "3 consecutive years" in veto_reason_str(row)

    def test_revenue_decline_trend_is_a_reason(self, isolated_data):
        row = pd.Series({"revenueHistory": [60.0, 80.0, 95.0, 110.0]})
        assert "revenue fell" in veto_reason_str(row)

    def test_ebit_collapse_trend_is_a_reason(self, isolated_data):
        row = pd.Series({"ebitHistory": [-3.0, -2.0, -1.0]})
        assert "operating income negative" in veto_reason_str(row)

    def test_recent_dividend_cut_on_thin_cover_is_a_reason(self, isolated_data):
        import datetime as _dt
        yr = _dt.datetime.now(_dt.timezone.utc).year
        row = pd.Series({"dividend_last_cut_year": yr - 1, "dividendCoverage": 1.2})
        assert "dividend cut in" in veto_reason_str(row)

    def test_short_history_does_not_add_a_trend_reason(self, isolated_data):
        row = pd.Series({"revenueHistory": [80.0, 100.0]})   # < 3 years
        assert veto_reason_str(row) == "a hard-veto rule"


class TestFairValueBarHtml:
    def test_missing_data_returns_dash(self):
        assert _fair_value_bar_html(None, 100.0, 10.0) == '<span style="color:var(--uv-faint,var(--faint));">—</span>'
        assert _fair_value_bar_html(100.0, None, 10.0) == '<span style="color:var(--uv-faint,var(--faint));">—</span>'
        assert _fair_value_bar_html(100.0, 120.0, None) == '<span style="color:var(--uv-faint,var(--faint));">—</span>'

    def test_valid_data_renders_bar(self):
        html = _fair_value_bar_html(100.0, 120.0, 16.7)
        assert "€100.00" in html
        assert "fv €120.00" in html

    def test_data_thin_renders_pending_chip_not_dash(self):
        html = _fair_value_bar_html(100.0, None, None, data_thin=True)
        assert "fv pending" in html
        assert "—" not in html

    def test_data_thin_ignored_once_fair_value_is_present(self):
        html = _fair_value_bar_html(100.0, 120.0, 16.7, data_thin=True)
        assert "fv pending" not in html
        assert "€100.00" in html


class TestHoldingsRowHtml:
    def _row(self, **overrides):
        kwargs = dict(ticker="AAA.BR", sector="Technology", name="Alpha Corp",
                      decision="Strong Buy", veto=False, price=100.0, fair_value=120.0,
                      mos_pct=16.7, weight=0.25, value=2500.0, day_change_pct=1.5)
        kwargs.update(overrides)
        return holdings_row_html(**kwargs)

    def test_missing_mos_pct_shows_dash(self):
        html = self._row(mos_pct=None)
        assert "<span style='color:var(--faint);'>—</span>" in html

    def test_missing_day_change_shows_dash(self):
        html = self._row(day_change_pct=None)
        assert html.count("<span style='color:var(--faint);'>—</span>") == 1  # only day-change dash

    def test_no_sector_omits_sector_pill(self):
        html = self._row(sector=None)
        assert "border-radius:5px;padding:1px 6px" not in html

    def test_dataless_row_renders_nodata_badge_not_veto(self):
        # A held ticker with no scored screener row merges in as NaN veto /
        # empty decision — must be NO DATA, never VETO via bool(nan) (WP-DQ6).
        html = self._row(decision="", veto=np.nan, fair_value=np.nan, mos_pct=np.nan)
        assert "uv-badge-neutral" in html and ">NO DATA<" in html
        assert "uv-badge-veto" not in html

    def test_data_thin_row_shows_pending_for_ladder_and_mos(self):
        # WP-E: incomplete fundamentals -> "fv pending", not a bare "—".
        html = self._row(fair_value=None, mos_pct=None, data_thin=True)
        assert "fv pending" in html
        assert ">pending<" in html          # the MoS cell
        assert "—" not in html

    def test_thin_flag_without_data_thin_still_dashes(self):
        html = self._row(fair_value=None, mos_pct=None, data_thin=False)
        assert "fv pending" not in html
        assert "—" in html


class TestScoreBarCellHtml:
    def test_missing_score_returns_dash(self):
        assert _score_bar_cell_html(None) == "—"

    def test_present_score_renders_bar(self):
        html = _score_bar_cell_html(80.0)
        assert "80" in html
        assert "var(--uv-mint)" in html


class TestQualityScoreColor:
    def test_high_is_mint(self):
        assert quality_score_color(80) == ("var(--uv-mint)", "var(--uv-mint)")

    def test_mid_is_teal(self):
        assert quality_score_color(50) == ("var(--teal, #1A8C6E)", "var(--teal, #1A8C6E)")

    def test_low_is_amber(self):
        assert quality_score_color(20) == ("#C98A3A", "#C98A3A")


class TestGainColor:
    def test_none_is_faint(self):
        assert _gain_color(None) == "var(--faint)"

    def test_nan_is_faint(self):
        assert _gain_color(float("nan")) == "var(--faint)"

    def test_positive_is_up(self):
        assert _gain_color(5.0) == "var(--up-txt)"

    def test_negative_is_down(self):
        assert _gain_color(-5.0) == "var(--down-txt)"

    def test_zero_is_up(self):
        assert _gain_color(0.0) == "var(--up-txt)"
