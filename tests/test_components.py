"""Shared-component tests (redesign Phase 2): signal badge, fair-value ladder,
signals feed — see uvalu/components.py.

Pure mapping functions are asserted directly; the render_* functions (which
call st.markdown/st.caption) are exercised through AppTest so a broken f-string
or missing import fails loudly instead of only showing up visually.
"""
from streamlit.testing.v1 import AppTest

from uvalu.components import (signal_badge_for_decision, signal_badge_html,
                              score_color, radial_gauge_svg, sub_score_bar_html,
                              sparkline_svg)


def test_signal_badge_for_decision_maps_known_labels():
    assert signal_badge_for_decision("Strong Buy") == ("buy", "BUY")
    assert signal_badge_for_decision("Monitor") == ("monitor", "MONITOR")
    assert signal_badge_for_decision("Avoid") == ("avoid", "AVOID")


def test_signal_badge_for_decision_veto_overrides_decision():
    assert signal_badge_for_decision("Strong Buy", veto=True) == ("veto", "VETO")


def test_signal_badge_for_decision_unknown_falls_back_to_avoid_kind():
    kind, label = signal_badge_for_decision("Something Else")
    assert kind == "avoid"
    assert label == "SOMETHING ELSE"


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
