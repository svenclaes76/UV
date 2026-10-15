"""Shared-component tests (redesign Phase 2): signal badge, fair-value ladder,
signals feed — see uvalu/components.py.

Pure mapping functions are asserted directly; the render_* functions (which
call st.markdown/st.caption) are exercised through AppTest so a broken f-string
or missing import fails loudly instead of only showing up visually.
"""
import re

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import numpy as np

from uvalu.components import (signal_badge_for, signal_badge_html, model_signal_badge_html, is_hard_veto,
                              score_color, band_tone_color, risk_score_meter_html,
                              radial_gauge_svg, sub_score_bar_html,
                              sparkline_svg, veto_reason_str, _fair_value_bar_html,
                              holdings_row_html, _score_bar_cell_html,
                              quality_score_color, _gain_color)


def test_signal_badge_for_maps_every_signal_code():
    assert signal_badge_for("undervalued") == ("buy", "Undervalued")
    assert signal_badge_for("neutral") == ("monitor", "Mid score")
    assert signal_badge_for("low_score") == ("avoid", "Low score")
    assert signal_badge_for("fails_screen") == ("veto", "Screened out")
    assert signal_badge_for("pending") == ("neutral", "No signal")


def test_signal_badge_for_veto_overrides_the_code():
    assert signal_badge_for("undervalued", veto=True) == ("veto", "Screened out")


def test_signal_badge_for_missing_code_is_nodata_not_low_score():
    # A holding with no scored screener row (fundamentals gap) has no
    # signal_code and a NaN veto cell — it must read as "No data", never a
    # low score or (via bool(nan)) a failed screen (WP-DQ6).
    for code in ("", None, np.nan, "Strong Buy"):
        assert signal_badge_for(code) == ("neutral", "No data")
    assert signal_badge_for(np.nan, veto=np.nan) == ("neutral", "No data")


def test_model_signal_badge_carries_the_bdg2_tooltip():
    html = model_signal_badge_html("undervalued")
    assert 'title="Model output based on public data and the settings shown. ' \
           'Not a recommendation tailored to you. See Methodology for thresholds."' in html
    assert ">Undervalued<" in html


def test_is_hard_veto_is_nan_safe():
    assert is_hard_veto(True) is True
    assert is_hard_veto(False) is False
    assert is_hard_veto(None) is False
    assert is_hard_veto(np.nan) is False
    assert is_hard_veto(1) is True


def test_signal_badge_html_renders_expected_span():
    html = signal_badge_html("buy", "OK")
    assert html == '<span class="uv-badge uv-badge-buy">OK</span>'


def _run(fn) -> AppTest:
    at = AppTest.from_function(fn, default_timeout=60)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def test_page_header_renders_title_subtitle_and_actions():
    def _script():
        import streamlit as st
        from uvalu.components import page_header
        with page_header("Value screener", "**12** of 40 <stocks> pass",
                         provenance='<div class="uv-provenance">model M1</div>'):
            st.button("Reset filters")

    at = _run(_script)
    head = at.markdown[0].value
    assert '<div class="uv-page-title" role="heading" aria-level="1">Value screener</div>' in head
    # Bold kept, the rest escaped.
    assert '<div class="uv-page-sub"><b>12</b> of 40 &lt;stocks&gt; pass</div>' in head
    assert head.index("uv-page-sub") < head.index("uv-provenance")
    assert [b.label for b in at.button] == ["Reset filters"]


def test_card_header_html_data_and_support_padding():
    from uvalu.components import card_header_html
    data = card_header_html("Holdings <all>", '<a href="#">Full analysis →</a>')
    assert "padding:16px 20px 14px" in data and "border-bottom:0.5px solid var(--line-2)" in data
    assert "font-size:15px;font-weight:500" in data and "Holdings &lt;all&gt;" in data
    assert "Full analysis →" in data
    assert "padding:14px 20px;" in card_header_html("Display", support=True)


def test_table_header_html_right_aligns_number_columns():
    from uvalu.components import table_header_html
    html = table_header_html(["Company", "Value"], "1fr 80px", right={1})
    assert "grid-template-columns:1fr 80px" in html and "padding:10px 20px" in html
    assert html.count("text-align:right") == 1
    assert html.split("<div title=")[2].startswith("\"Value\"") and "text-align:right" in html.split("<div title=")[2]


def test_kpi_card_value_is_26px_by_default():
    def _script():
        from uvalu.components import kpi_card
        kpi_card("Cash", "€ 1")

    html = _run(_script).markdown[0].value
    assert "font-size:26px" in html and "margin-top:10px" in html


def test_kpi_card_md_value_is_23px():
    def _script():
        from uvalu.components import kpi_card
        kpi_card("Cash", "€ 1", size="md")

    html = _run(_script).markdown[0].value
    assert "font-size:23px" in html and "margin-top:9px" in html


def test_back_link_is_keyed_for_the_shared_style():
    def _script():
        from uvalu.components import back_link
        back_link("← Back to Portfolio", key="back_x")

    at = _run(_script)
    assert at.button(key="back_x").label == "← Back to Portfolio"


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
                 signal_code="undervalued", veto=False, score=80.0, mos_pct=None,
                 price=100.0, pe=15.0, div_yield=0.03, show_action=False)

    at = _run(_script)
    assert not any(b.key == "row1_action" for b in at.button)


def test_stock_row_missing_mos_shows_dash():
    def _script():
        from uvalu.components import stock_row
        stock_row(key="row1", ticker="AAA.BR", name="Alpha Corp", exchange="Brussels",
                 signal_code="undervalued", veto=False, score=80.0, mos_pct=None,
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


def test_six_model_ladder_rows_relabels_dark_slots_with_fv3_fallbacks():
    from uvalu.components import six_model_ladder_rows
    # Graham + P/E dark (loss-maker), EPV present. Book-value and FCF fallbacks
    # fired → they take the first two dark fundamentals slots, relabelled.
    row = {"graham_number": None, "pe_fair_value": None, "epv": 30.0,
           "ddm": None, "ddm_multistage": None, "targetMeanPrice": 12.0,
           "pb_fair_value": 8.5, "fcf_fair_value": 10.2}
    rows = six_model_ladder_rows(row)
    assert [lbl for lbl, _ in rows] == [
        "Book value (fallback)", "FCF value (fallback)", "EPV", "Dividend, single stage", "Dividend, multi-stage"]
    assert rows[0] == ("Book value (fallback)", 8.5)
    assert rows[1] == ("FCF value (fallback)", 10.2)
    assert rows[2] == ("EPV", 30.0)


def test_six_model_ladder_rows_leaves_labels_untouched_for_a_healthy_row():
    from uvalu.components import six_model_ladder_rows
    row = {"graham_number": 52.0, "pe_fair_value": 60.0, "epv": 48.0,
           "ddm": 40.0, "ddm_multistage": 44.0, "targetMeanPrice": 55.0,
           "pb_fair_value": None, "fcf_fair_value": None}
    rows = six_model_ladder_rows(row)
    assert [lbl for lbl, _ in rows] == [
        "Graham Number", "P/E fair value", "EPV", "Dividend, single stage", "Dividend, multi-stage"]


def test_six_model_ladder_rows_show_the_analyst_target_only_when_licensed(monkeypatch):
    import screener
    from uvalu.components import six_model_ladder_rows
    row = {"graham_number": 52.0, "targetMeanPrice": 55.0}
    assert "Analyst Target" not in [lbl for lbl, _ in six_model_ladder_rows(row)]
    monkeypatch.setattr(screener, "ANALYST_INPUTS_ENABLED", True)
    assert ("Analyst Target", 55.0) in six_model_ladder_rows(row)


def test_six_model_ladder_reasons_formats_the_dark_codes():
    from uvalu.components import six_model_ladder_reasons
    # FV-6 (review): the component only maps codes emitted by _fair_value_models.
    row = {"fv_dark_reasons": {"graham_number": "no_eps", "pe_fair_value": "no_eps",
                               "epv": "epv_negative", "ddm": "non_payer",
                               "analyst": "no_coverage"}}
    r = six_model_ladder_reasons(row)
    assert r["Graham Number"] == "no positive EPS"
    assert r["P/E fair value"] == "no positive EPS"
    assert r["EPV"] == "net debt > earnings"
    assert r["Dividend, single stage"] == "not a dividend payer"
    assert r["Dividend, multi-stage"] == "not a dividend payer"
    assert r["Analyst Target"] == "no analyst coverage"
    # every EPV / DDM failure mode has distinct text
    for code, text in [("no_ev", "no enterprise value"), ("no_ebit", "no multi-year EBIT"),
                       ("low_ebit", "through-cycle EBIT ≤ 0"), ("sector", "n/a for this sector")]:
        assert six_model_ladder_reasons({"fv_dark_reasons": {"epv": code}})["EPV"] == text
    assert six_model_ladder_reasons(
        {"fv_dark_reasons": {"ddm": "spread"}})["Dividend, single stage"] == "discount rate ≈ dividend growth"
    # no field / a live model → no entry
    assert six_model_ladder_reasons({}) == {}
    assert "Graham Number" not in six_model_ladder_reasons({"fv_dark_reasons": {"epv": "sector"}})


def test_six_model_ladder_caption_flags_fallback_and_haircut():
    from uvalu.components import six_model_ladder_caption
    assert six_model_ladder_caption({"pb_fair_value": None, "fcf_fair_value": None,
                                     "targetMeanPrice": None}) is None
    cap = six_model_ladder_caption({"pb_fair_value": 8.0, "targetMeanPrice": 12.0})
    assert "book value fallback" in cap and "haircut" in cap


def test_six_model_ladder_caption_names_only_the_fallbacks_shown():
    from uvalu.components import six_model_ladder_caption
    # Book value only (the CPINV.BR case): no mention of an FCF value row.
    cap = six_model_ladder_caption({"pb_fair_value": 8.0})
    assert cap.startswith("The book value fallback stands in") and "FCF" not in cap
    cap = six_model_ladder_caption({"fcf_fair_value": 9.0})
    assert cap.startswith("The FCF fallback stands in") and "book value" not in cap
    assert six_model_ladder_caption({"pb_fair_value": 8.0, "fcf_fair_value": 9.0}).startswith(
        "The book value and FCF fallbacks stand in")
    # A live fallback with no dark Graham/P/E/EPV slot isn't on the ladder: no note.
    assert six_model_ladder_caption({"pb_fair_value": 8.0, "graham_number": 10.0,
                                     "pe_fair_value": 11.0, "epv": 12.0}) is None


def test_fair_value_ladder_shows_reason_and_basis_line():
    def _script():
        from uvalu.components import fair_value_ladder
        fair_value_ladder(
            price=50.0,
            models=[("Graham Number", None), ("P/E fair value", 60.0)],
            composite=58.0,
            reasons={"Graham Number": "no positive EPS"},
            basis_count=1, basis_thin=True,
        )

    at = _run(_script)
    html = at.markdown[0].value
    assert "no positive EPS" in html            # reason in the dark row
    assert "1 of 6 models" in html              # basis line
    assert "lightly corroborated" in html       # thin flag


def test_fair_value_bar_compact_flags_overvalued_vs_undervalued():
    def _script():
        from uvalu.components import fair_value_bar_compact
        fair_value_bar_compact(price=100.0, fair_value=120.0, mos_pct=16.7)
        fair_value_bar_compact(price=100.0, fair_value=90.0, mos_pct=-11.1)
        fair_value_bar_compact(price=100.0, fair_value=101.5, mos_pct=1.5)

    at = _run(_script)
    # Brand §8 ladder fills: --up-txt / --axis / --amber-fill (red is veto-only).
    assert "background:var(--up-txt)" in at.markdown[0].value
    assert "background:var(--amber-fill)" in at.markdown[1].value
    assert "background:var(--axis)" in at.markdown[2].value  # within the near-fair band
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
    # Green only for "Low" (<=25), amber for "Moderate"/"Elevated" (<=70),
    # red for "High"/"Critical" — cut-offs come from risk.RISK_BANDS.
    assert score_color(20) == ("#1DD6A4", "#0F6E56")
    # Amber text is the caution text token (#854F0B light), not the fill.
    assert score_color(55) == ("#C98A3A", "#854F0B")
    assert score_color(55, dark=True) == ("#C98A3A", "#E0B94D")
    assert score_color(85) == ("#A32D2D", "#A32D2D")
    # dark=True swaps only the text hex (mirrors runtime.theme_colors()).
    assert score_color(20, dark=True) == ("#1DD6A4", "#1DD6A4")
    assert score_color(85, dark=True) == ("#A32D2D", "#F0A6A6")


def test_score_color_36_is_amber_not_green():
    # Regression: a 26-39 score is labelled "Moderate risk" by risk.risk_band,
    # so its gauge must be amber. The old 40/70 split painted it green.
    import risk
    assert risk.risk_band(36)[0] == "Moderate risk"
    ring, _ = score_color(36)
    assert ring == "#C98A3A"


def test_score_color_breaks_align_with_risk_bands():
    # The colour flips exactly on risk.py's own band edges, so the two can't
    # drift apart again.
    import risk
    assert score_color(risk.SCORE_LOW)[0] == "#1DD6A4"
    assert score_color(risk.SCORE_LOW + 1)[0] == "#C98A3A"
    assert score_color(risk.SCORE_ELEVATED)[0] == "#C98A3A"
    assert score_color(risk.SCORE_ELEVATED + 1)[0] == "#A32D2D"


def test_band_tone_color_maps_quant_words():
    import risk
    assert band_tone_color(risk.band_tone("High")) == "#A32D2D"
    assert band_tone_color(risk.band_tone("Low")) == "#0F6E56"
    assert band_tone_color(risk.band_tone("Aggressive")) == "#A32D2D"
    assert band_tone_color(risk.band_tone("N/A")) == "var(--muted)"
    # G04: a weak Sharpe/Sortino is amber; red stays for a failed quality screen.
    assert risk.band_tone("Suboptimal") == risk.band_tone("Moderate")


def test_risk_score_meter_html_gradient_and_marker():
    import risk
    html = risk_score_meter_html(36, "Moderate risk")
    assert f"#1DD6A4 {risk.SCORE_LOW}%" in html
    assert f"#C98A3A {risk.SCORE_ELEVATED}%" in html
    assert "left:36.0%" in html
    assert "· Moderate risk" in html
    # heading=None drops the score-text row but keeps the track.
    assert "Portfolio risk score" not in risk_score_meter_html(36, "Moderate risk", heading=None)


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
    assert "#C98A3A" in html  # 58 falls in the amber (Moderate/Elevated) band


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
        assert veto_reason_str(row) == "a quality-screen rule"

    def test_multiple_reasons_joined(self, isolated_data):
        row = pd.Series({"debtToEquity": 900.0, "freeCashflow": -1.0})
        result = veto_reason_str(row)
        assert "debt/equity" in result and "negative free cash flow" in result
        assert "; " in result

    def test_no_reasons_falls_back_to_generic_message(self, isolated_data):
        assert veto_reason_str(pd.Series({})) == "a quality-screen rule"

    def test_leverage_exempt_sector_does_not_surface_debt_reason(self, isolated_data):
        # Financial Services/Real Estate/Utilities are exempt from the D/E
        # veto (structural leverage, not distress) — high D/E alone shouldn't
        # surface as a reason for those sectors, matching screener.py's
        # _hard_veto formula.
        row = pd.Series({"debtToEquity": 900.0, "sector": "Financial Services"})
        assert veto_reason_str(row) == "a quality-screen rule"

    def test_single_bad_fcf_year_not_a_reason_with_three_year_history(self, isolated_data):
        # A single negative year no longer vetoes once 3-year fcfHistory
        # exists — only 3 consecutive negative years do.
        row = pd.Series({"freeCashflow": -1.0, "fcfHistory": [-1.0, 50.0, 80.0]})
        assert veto_reason_str(row) == "a quality-screen rule"

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
        assert veto_reason_str(row) == "a quality-screen rule"

    def test_confirmed_zero_volume_is_a_reason(self, isolated_data):
        row = pd.Series({"averageVolume": 0.0})
        assert "no confirmed trading volume" in veto_reason_str(row)

    def test_missing_volume_is_not_a_reason(self, isolated_data):
        # Unreported volume (field absent, not a confirmed 0) must not
        # surface as a reason — matches screener.py's `== 0` (not
        # `.fillna(0)`) hard-veto test.
        row = pd.Series({"averageVolume": None})
        assert veto_reason_str(row) == "a quality-screen rule"


class TestFairValueBarHtml:
    def test_missing_data_returns_dash(self):
        assert _fair_value_bar_html(None, 100.0, 10.0) == '<span style="color:var(--muted);">—</span>'
        assert _fair_value_bar_html(100.0, None, 10.0) == '<span style="color:var(--muted);">—</span>'
        assert _fair_value_bar_html(100.0, 120.0, None) == '<span style="color:var(--muted);">—</span>'

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
                      signal_code="undervalued", veto=False, price=100.0, fair_value=120.0,
                      mos_pct=16.7, weight=0.25, value=2500.0, total_gain=125.0)
        kwargs.update(overrides)
        return holdings_row_html(**kwargs)

    def test_missing_mos_pct_shows_dash(self):
        html = self._row(mos_pct=None)
        assert "<span style='color:var(--muted);'>—</span>" in html

    def test_missing_total_gain_shows_dash(self):
        html = self._row(total_gain=None)
        assert html.count("<span style='color:var(--muted);'>—</span>") == 1  # only P&L dash

    def test_total_gain_is_a_percent_chip_against_cost(self):
        # value 2500, gain 125 -> cost 2375 -> +5.3%; the € amount is in the tooltip.
        up = self._row(total_gain=125.0)
        assert ">+5.3%</span>" in up and "background:var(--up-bg)" in up
        assert "Unrealised result against your average cost · +€125.00" in up
        down = self._row(total_gain=-125.0)
        assert ">-4.8%</span>" in down and "background:var(--down-bg)" in down

    def test_mos_colour_tiers(self):
        assert "color:var(--up-txt);'>+16.7%" in self._row(mos_pct=16.7)
        assert "color:var(--text);'>+5.0%" in self._row(mos_pct=5.0)
        assert "color:var(--amber-txt);'>-5.0%" in self._row(mos_pct=-5.0)

    def test_no_sector_omits_sector_pill(self):
        html = self._row(sector=None)
        assert "border-radius:5px;padding:1px 6px" not in html

    def test_dataless_row_renders_nodata_badge_not_veto(self):
        # A held ticker with no scored screener row merges in as NaN veto /
        # empty signal_code — must be "No data", never a failed screen via
        # bool(nan) (WP-DQ6).
        html = self._row(signal_code="", veto=np.nan, fair_value=np.nan, mos_pct=np.nan)
        assert "uv-badge-neutral" in html and ">No data<" in html
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

    def test_present_score_renders_bar(self, isolated_data):
        html = _score_bar_cell_html(80.0)
        assert "80" in html
        assert "background:var(--mint)" in html and "color:var(--up-txt)" in html

    @pytest.mark.parametrize("score,bar,text", [(70, "var(--mint)", "var(--up-txt)"),
                                                (69, "var(--teal)", "var(--text)"),
                                                (40, "var(--teal)", "var(--text)"),
                                                (39, "var(--amber-fill)", "var(--text)")])
    def test_bands_follow_70_and_40(self, isolated_data, score, bar, text):
        html = _score_bar_cell_html(float(score))
        assert f"background:{bar}" in html and f"color:{text}" in html

    def test_upper_band_moves_with_the_undervalued_threshold(self, isolated_data):
        import settings
        settings.save_shared_settings({**settings.load_shared_settings(), "buy_threshold": 80.0})
        assert "background:var(--teal)" in _score_bar_cell_html(75.0)


class TestQualityScoreColor:
    def test_high_is_mint(self, isolated_data):
        assert quality_score_color(80) == ("var(--mint)", "var(--up-txt)")

    def test_mid_is_teal_with_plain_text(self, isolated_data):
        # G34: plain text for the middle band, not the mockup's link colour.
        assert quality_score_color(50) == ("var(--teal)", "var(--text)")

    def test_low_is_amber(self, isolated_data):
        assert quality_score_color(20) == ("var(--amber-fill)", "var(--amber-txt)")


class TestScoreBandLabel:
    @pytest.mark.parametrize("score,label", [(85, "Upper band · 70–100"), (55, "Middle band · 40–69"),
                                             (12, "Lower band · 0–39")])
    def test_bands(self, isolated_data, score, label):
        from uvalu.components import score_band_label
        assert score_band_label(score) == label

    def test_excluded_and_no_signal(self, isolated_data):
        from uvalu.components import score_band_label
        assert score_band_label(0, excluded=True) == "Excluded · fails quality screen"
        assert score_band_label(None) == "No signal · no peer reference"


class TestMosTextColor:
    @pytest.mark.parametrize("mos,color", [(15, "var(--up-txt)"), (14.9, "var(--text)"), (0, "var(--text)"),
                                           (-0.1, "var(--amber-txt)"), (None, "var(--muted)")])
    def test_three_tiers_never_red(self, mos, color):
        from uvalu.components import mos_text_color
        assert mos_text_color(mos) == color


class TestGainColor:
    def test_none_is_muted(self):
        assert _gain_color(None) == "var(--muted)"

    def test_nan_is_muted(self):
        assert _gain_color(float("nan")) == "var(--muted)"

    def test_positive_is_up(self):
        assert _gain_color(5.0) == "var(--up-txt)"

    def test_negative_is_down(self):
        assert _gain_color(-5.0) == "var(--down-txt)"

    def test_zero_is_up(self):
        assert _gain_color(0.0) == "var(--up-txt)"


# ── Provenance bar (REC-4 / REC-5 / REC-10; visual review 2026-10-04) ────────

def _signals_frame(price_ages_hours, codes=("undervalued",)):
    now = pd.Timestamp.now(tz="UTC")
    n = len(price_ages_hours)
    return pd.DataFrame({
        "Ticker": [f"T{i}.BR" for i in range(n)],
        "signal_computed_at": [now] * n,
        "price_as_of": [now - pd.Timedelta(hours=h) for h in price_ages_hours],
        "model_version": ["M1"] * n,
        "signal_code": [codes[i % len(codes)] for i in range(n)],
    })


def test_list_provenance_keeps_every_rec4_rec5_fact():
    from uvalu.components import list_provenance_html
    html = list_provenance_html(_signals_frame([1, 2]))
    assert "Signals computed" in html and "prices delayed" in html
    assert "model" in html and "M1" in html
    assert "Methodology" in html and "/legal?doc=methodology" in html


def test_list_provenance_flags_prices_older_than_72_hours():
    from uvalu.components import list_provenance_html
    fresh = list_provenance_html(_signals_frame([1, 30]))
    stale = list_provenance_html(_signals_frame([1, 24 * 21]))
    assert "oldest" not in fresh
    assert "oldest 3 weeks" in stale
    assert "Some prices are more than 72 hours old." in stale
    # Brand v1.3: the Material `warning` symbol, not the ⚠ character.
    assert ">warning</span>" in stale and "⚠" not in stale


def test_provenance_is_a_quiet_caption_without_fill_or_border():
    """Option 1a: no box around the provenance; tints are for signals."""
    import re
    from uvalu.components import list_provenance_html
    html = list_provenance_html(_signals_frame([1, 2]))
    outer = re.match(r'<div[^>]*style="([^"]*)"', html).group(1)
    assert "background" not in outer and "border" not in outer
    assert "var(--faint)" not in html          # A5: muted text only, >= 4.5:1
    assert "font-size:12px" in outer


def test_provenance_methodology_link_is_inline_and_quiet():
    from uvalu.components import list_provenance_html
    html = list_provenance_html(_signals_frame([1, 2]))
    # The arrow marks it as a link, like every other link in the app.
    assert 'class="uv-quiet-link"' in html and ">Methodology →</a>" in html
    # Last fact on the line, after a separator — not pushed to the right.
    assert html.rstrip().endswith("</a></div>")
    assert "margin-left:auto" not in html


def test_provenance_facts_never_wrap_mid_phrase():
    from uvalu.components import list_provenance_html
    html = list_provenance_html(_signals_frame([1, 2]))
    assert html.count('white-space:nowrap;">') >= 3


def test_signal_pill_shares_sum_to_about_100():
    """Option 1c / REC-10: the share per signal sits in the Screener's pills."""
    import re
    from screener import signal_distribution
    from uvalu.components import signal_share_label
    df = _signals_frame([1, 1, 1, 1, 1, 1, 1],
                        codes=("undervalued", "neutral", "neutral", "low_score", "fails_screen",
                               "fails_screen", "fails_screen"))
    shares = signal_distribution(df)
    labels = [signal_share_label(code, shares.get(code)) for code in
              ("undervalued", "neutral", "low_score", "fails_screen")]
    assert labels[0].startswith("Undervalued `") and labels[3].startswith("Screened out `")
    pcts = [int(re.search(r"`(\d+)\s*%`", label).group(1)) for label in labels]
    assert 98 <= sum(pcts) <= 102


def test_signal_pill_without_share_is_the_bare_label():
    from uvalu.components import signal_share_label
    assert signal_share_label("neutral", None) == "Mid score"


def test_fair_value_legend_above_is_amber_not_red():
    from uvalu.components import _ladder_bar_color, fair_value_legend_html
    html = fair_value_legend_html()
    assert "#A32D2D" not in html and "--amber-fill" in html
    assert "var(--faint)" not in html
    assert "amber" in _ladder_bar_color(-20.0)


def test_signal_provenance_for_one_row():
    from uvalu.components import signal_provenance_html
    row = _signals_frame([2]).iloc[0]
    html = signal_provenance_html(row)
    assert "Signal computed" in html and "price as of" in html and "delayed" in html
    assert "M1" in html and "/legal?doc=methodology" in html


class TestDashboardBottomRow:
    def test_donut_has_a_slice_and_legend_row_per_sector(self):
        from uvalu.components import donut_html
        html = donut_html(pd.Series({"Technology": 700.0, "Healthcare": 300.0, "n/a": 50.0}))
        assert html.count("<circle") == 2 and "Technology" in html and "Healthcare" in html
        assert "n/a" not in html and ">Total</span>" in html
        assert "70.0%" in html and "30.0%" in html

    def test_donut_folds_the_tail_into_other(self):
        from uvalu.components import DONUT_MAX_SLICES, donut_html
        html = donut_html(pd.Series({f"S{i}": float(100 - i) for i in range(15)}))
        assert html.count("<circle") == DONUT_MAX_SLICES and "Other" in html

    def test_donut_empty_series_is_empty(self):
        from uvalu.components import donut_html
        assert donut_html(pd.Series(dtype=float)) == ""

    def test_dividend_row_shows_payment_date_only_on_or_after_the_ex_date(self):
        from uvalu.components import dividend_row_html
        with_pay = dividend_row_html(name="Alpha", ex_date="2026-11-03", pay_date="2026-11-20", net=12.0, gross=17.0)
        assert re.search(r"ex-date · pays (Nov 20|20 Nov)<", with_pay) and ">3</div>" in with_pay and ">Nov<" in with_pay
        stale = dividend_row_html(name="Alpha", ex_date="2026-11-03", pay_date="2026-05-20", net=12.0, gross=17.0)
        assert "pays" not in stale and ">ex-date<" in stale
        assert "€17 gross" in stale

    def test_mover_bar_diverges_from_the_centre(self):
        from uvalu.components import mover_row_html
        up = mover_row_html(ticker="AAA.BR", name="Alpha", change_pct=2.0, max_abs=4.0)
        down = mover_row_html(ticker="BBB.BR", name="Beta", change_pct=-4.0, max_abs=4.0)
        assert '<rect x="26.0" y="7" width="12.5"' in up and "fill:var(--up-txt)" in up
        assert '<rect x="1.0" y="7" width="25.0"' in down and "fill:var(--down-txt)" in down
        assert ">AAA.BR</span>" in up and "+2.00%" in up


def test_ladder_difference_text_uses_text_tokens():
    """Brand v1.3: --amber-fill is for bars; the difference text next to a
    model's bar uses --amber-txt (and --muted near fair value)."""
    from uvalu.components import _ladder_bar_color, _ladder_text_color
    assert _ladder_bar_color(-20) == "var(--amber-fill)"
    assert _ladder_text_color(-20) == "var(--amber-txt)"
    assert _ladder_text_color(1) == "var(--muted)"
    assert _ladder_text_color(20) == "var(--up-txt)"


def test_fmt_mos_pct_reads_a_price_far_above_fair_value_as_a_multiple():
    # UX3: "−125%" means nothing to a reader; say how far the price is above.
    from uvalu.components import fmt_mos_pct
    assert fmt_mos_pct(-125.3) == "price 2.3× fair value"
    assert fmt_mos_pct(-125.3, compact=True).startswith("< ")
    assert fmt_mos_pct(-40.0).startswith("-") or fmt_mos_pct(-40.0).startswith("−")
    assert fmt_mos_pct(None) == "—" and fmt_mos_pct(float("nan")) == "—"


def test_label_date_is_formatted_like_the_row():
    """A pencil's screen-reader name shows the date as the row does."""
    from uvalu.components import _label_date
    assert "00:00" not in _label_date("2026-11-25 00:00:00")
    assert _label_date(None) == ""
