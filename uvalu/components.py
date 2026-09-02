"""Shared visual components used across multiple screens (redesign Phase 2):
the signal badge pill, the fair-value ladder, and the signals feed/list.

These render raw HTML via st.markdown(unsafe_allow_html=True) against the
uv-badge/brand-token CSS in uvalu/styles.py. Used by uvalu/drawer.py and
uvalu/pages_/analysis.py (the stock-detail drawer + deep-dive page).
"""
import pandas as pd
import streamlit as st

from screener import _fcf_hard_veto, _trend_veto, LEVERAGE_EXEMPT_SECTORS
from settings import get_veto_thresholds
from uvalu.formatting import fmt_eur as _fmt_eur

# ── Signal badge ─────────────────────────────────────────────────────────────

_DECISION_BADGE = {
    "Strong Buy": ("buy", "BUY"),
    "Monitor":    ("monitor", "MONITOR"),
    "Avoid":      ("avoid", "AVOID"),
}

_TIP_LABELS = {"warn": "HIGH", "caution": "NOTE", "ok": "OK", "neutral": "INFO"}


def is_hard_veto(v: object) -> bool:
    """NaN-safe truthiness for a scored row's ``veto`` cell. A holding with no
    scored screener row (fundamentals gap) merges in as NaN, and ``bool(nan)``
    is ``True`` in Python — which was painting dataless rows as hard vetoes
    (the 6-vs-5 "under hard veto" mismatch between the Holdings ladder and the
    Risk page). Only a real truthy, non-NaN value counts."""
    if v is None:
        return False
    if isinstance(v, float) and pd.isna(v):
        return False
    return bool(v)


def signal_badge_for_decision(decision: object, veto: object = False) -> tuple[str, str]:
    """Map a screener Decision string (+ veto flag) to a (kind, label) badge pair.

    Three distinct states, not two: a real hard veto → VETO; a scored
    BUY/MONITOR/AVOID → that; anything else (no Decision — the row has no
    scored screener data at all) → a neutral "NO DATA" badge, so a
    fundamentals gap never masquerades as an AVOID or, via ``bool(nan)``, a
    VETO."""
    if is_hard_veto(veto):
        return "veto", "VETO"
    decision = "" if decision is None or (isinstance(decision, float) and pd.isna(decision)) else str(decision)
    if decision in _DECISION_BADGE:
        return _DECISION_BADGE[decision]
    return "neutral", "NO DATA"


def veto_reason_str(row: "pd.Series") -> str:
    """Human-readable, stock-specific reason a row's hard veto tripped.

    Mirrors screener.py's compute_scores() `_hard_veto` formula exactly:
    ((debtToEquity > max_debt_equity) AND sector not in
    LEVERAGE_EXEMPT_SECTORS) | _fcf_hard_veto(row) [FCF negative 3
    consecutive years, falling back to the single most recent period when
    less history is available] | _trend_veto(row) [multi-year revenue
    decline / EBIT collapse / retained-earnings erosion / a recent
    dividend cut on thin cover] | (Div Flag == "At Risk" AND
    dividendCoverage < 1.0) — the last one is a single AND-combined
    condition, not two independent ones, so it's only listed as failing
    when BOTH sub-conditions hold. Shared by uvalu/drawer.py and
    uvalu/pages_/analysis.py so the two veto banners never drift out of
    sync with each other or with the real formula.
    """
    max_de, _, _, _ = get_veto_thresholds()
    de = row.get("debtToEquity"); fcf = row.get("freeCashflow")
    sector = row.get("sector")
    div_flag = row.get("Div Flag"); coverage = row.get("dividendCoverage")
    reasons = []
    if pd.notna(de) and de > max_de and sector not in LEVERAGE_EXEMPT_SECTORS:
        reasons.append(f"debt/equity of {de:.0f}% exceeds the {max_de:.0f}% limit")
    if _fcf_hard_veto(row):
        history = row.get("fcfHistory")
        if isinstance(history, list) and len(history) >= 3:
            reasons.append("free cash flow negative for 3 consecutive years")
        else:
            reasons.append(f"negative free cash flow ({_fmt_eur(fcf)})")
    reasons.extend(_trend_veto(row))
    if div_flag == "At Risk" and pd.notna(coverage) and coverage < 1.0:
        reasons.append(f"dividend flagged at risk with {coverage:.2f}× coverage")
    return "; ".join(reasons) if reasons else "a hard-veto rule"


def signal_badge_html(kind: str, label: str) -> str:
    """Raw <span> markup for a signal badge — embed inside markdown/HTML contexts."""
    return f'<span class="uv-badge uv-badge-{kind}">{label}</span>'


def render_signal_tips(tips: list[tuple[str, str]]) -> None:
    """OK/NOTE/HIGH/INFO badge + plain-language text list."""
    if not tips:
        return
    st.caption("Signals")
    st.caption(
        "<br>".join(
            f'{signal_badge_html(sev if sev in _TIP_LABELS else "neutral", _TIP_LABELS.get(sev, "INFO"))} {tip}'
            for sev, tip in tips
        ),
        unsafe_allow_html=True,
    )


# ── Delta chip ───────────────────────────────────────────────────────────────
# Matches Uvalu.dc.html's shared _chip(up) helper — a colored pill (not plain
# text) for any up/down delta: KPI card deltas, the value-chart's range
# delta, and the Holdings/Top-movers "Today" day-change cells all use it.

def chip_html(text: str, positive: bool = True) -> str:
    """Raw <span> markup for a colored up/down delta pill — embed inside
    markdown/HTML contexts (e.g. a table cell's <div>)."""
    bg = "var(--up-bg)" if positive else "var(--down-bg)"
    color = "var(--up-txt)" if positive else "var(--down-txt)"
    return (f'<span style="display:inline-flex;align-items:center;gap:2px;'
           f'font-family:var(--uv-mono);font-size:11.5px;font-weight:500;'
           f'padding:2px 7px;border-radius:5px;background:{bg};color:{color};">{text}</span>')


# ── KPI card ─────────────────────────────────────────────────────────────────
# Shared by the Dashboard KPI strip and Portfolio's summary rows (overview +
# the three full-page drill-downs) so every screen's headline numbers render
# as the same bordered/shadowed card instead of Streamlit's bare st.metric.

# Small stroke icons (24x24 viewBox, currentColor) matching the mockup's
# leading-icon-per-tile treatment (Uvalu.dc.html's {{ k.icon }}).
KPI_ICONS = {
    "wallet": '<path d="M17 8v-3a1 1 0 0 0 -1 -1h-10a2 2 0 0 0 0 4h12a1 1 0 0 1 1 1v3m0 4v3a1 1 0 0 1 -1 1h-12a2 2 0 0 1 -2 -2v-11"/><path d="M20 12v4h-4a2 2 0 0 1 0 -4h4"/>',
    "trend":  '<path d="M3 17l6 -6l4 4l8 -8"/><path d="M14 7l7 0l0 7"/>',
    "coin":   '<circle cx="12" cy="12" r="9"/><path d="M14.8 9a2 2 0 0 0 -1.8 -1h-2a2 2 0 0 0 0 4h2a2 2 0 0 1 0 4h-2a2 2 0 0 1 -1.8 -1"/><path d="M12 6v2m0 8v2"/>',
    "target": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="0.5" fill="currentColor"/>',
}


def kpi_card(label: str, value: str, delta_text: str = "", positive: bool = True,
            sub: str = "", icon: str = "wallet") -> None:
    """One headline-number card: icon+label, a large mono value, and an
    optional colored delta + grey sub-caption — matches Uvalu.dc.html's KPI
    tile exactly. `delta_text`/`sub` may be left empty for a plain value-only
    card (e.g. a count with nothing to compare it against)."""
    _icon_svg = (f'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{KPI_ICONS.get(icon, "")}'
                f'</svg>')
    # `_delta_row` is built as a single-line string (not split across f-string
    # template lines) — a blank/whitespace-only line here (when delta_text is
    # "") resets CommonMark's HTML-block parsing context, and the *next*
    # line's leading spaces then get read as an indented code block instead
    # of continued HTML, rendering the sub-caption as literal escaped text.
    _delta_html = chip_html(delta_text, positive) if delta_text else ""
    _delta_row = f'{_delta_html}<span style="font-size:11px;color:var(--faint);">{sub}</span>'
    # min-height on the delta row — the chip (padding:2px 7px around 11.5px
    # text, ~22px tall) is taller than the plain sub-caption span alone, so
    # a value-only card with no delta_text (e.g. "Avg fair value upside")
    # would otherwise render ~5px shorter than its siblings in the same
    # st.columns() row, since each card's height is purely content-driven.
    st.markdown(f"""
<div style="background:var(--panel);border:0.5px solid var(--line);border-radius:12px;padding:15px 17px;box-shadow:var(--shadow);">
  <div style="display:flex;align-items:center;gap:6px;font-size:10.5px;letter-spacing:0.06em;text-transform:uppercase;color:var(--faint);font-weight:500;">
    {_icon_svg}{label}</div>
  <div style="font-family:var(--uv-mono);font-size:26px;font-weight:500;letter-spacing:-0.02em;margin-top:10px;line-height:1;color:var(--text);">{value}</div>
  <div style="margin-top:9px;min-height:22px;display:flex;align-items:center;gap:8px;">{_delta_row}</div>
</div>""", unsafe_allow_html=True)


# ── Fair-value ladder ────────────────────────────────────────────────────────

# "Near fair" band — a MoS within +/-3% reads as priced-at-fair-value rather
# than a genuine under/overvaluation signal (matches the mockup's 3-tier
# Undervalued/Near fair/Overvalued legend, not a plain positive/negative split).
_NEAR_FAIR_BAND = 3.0


def _ladder_bar_color(delta_pct: float) -> str:
    """3-tier band matching fair_value_bar_compact's Undervalued/Near
    fair/Overvalued legend — kept in sync so a model bar and a table's
    compact bar never disagree about what counts as "near fair"."""
    if delta_pct > _NEAR_FAIR_BAND:
        return "var(--uv-mint)"
    if delta_pct >= -_NEAR_FAIR_BAND:
        return "var(--teal, #1A8C6E)"
    return "var(--uv-neg-txt)"


def fair_value_ladder(price: float, models: list[tuple[str, float]],
                      composite: float | None = None, currency: str = "€",
                      composite_label: str = "Composite fair value",
                      bar_width: int = 110) -> None:
    """Compact per-model fair-value list: a thin bar, the model's value, and
    its delta vs. the current price, ending in an explicit composite row —
    matching Uvalu.dc.html's Six-model fair value spec exactly: every model
    passed in gets its own row (an unavailable model shows "–", it isn't
    dropped from the list — the design always renders a fixed row count),
    each row separated by a hairline, label left-aligned via flex:1 rather
    than a fixed right-aligned column. No "current price" caption — that's
    redundant with the caller's own price KPI tile and isn't part of the
    design spec for this component.

    `models` is an ordered list of (label, value) pairs — value may be
    None/NaN for a model that couldn't be computed for this stock. Delta is
    (model value − price) / model value, matching the same margin-of-safety
    convention used for the composite row and for fair_value_bar_compact
    elsewhere. `bar_width` lets callers match the design's per-context bar
    size (96px in the drawer vs. 110px on the Analysis screen).
    """
    if not price or pd.isna(price):
        st.caption("Not enough model data for a fair-value ladder.")
        return
    price = float(price)

    valid_vals = [float(v) for _, v in models if v is not None and pd.notna(v) and v > 0]
    if not valid_vals:
        st.caption("Not enough model data for a fair-value ladder.")
        return
    scale = max([price] + valid_vals) * 1.08

    def _row(label: str, value: float | None) -> str:
        if value is None or pd.isna(value) or value <= 0:
            return (f'<div style="display:flex;align-items:center;gap:12px;padding:9px 0;border-bottom:0.5px solid var(--line-2);">'
                   f'<span style="flex:1;font-size:12.5px;color:var(--muted);">{label}</span>'
                   f'<div style="width:{bar_width}px;flex:none;height:5px;border-radius:3px;background:var(--uv-track,#EEF1F5);"></div>'
                   f'<span style="font-family:var(--uv-mono);font-size:12.5px;font-weight:500;width:64px;text-align:right;color:var(--faint);">–</span>'
                   f'<span style="font-family:var(--uv-mono);font-size:11px;width:52px;text-align:right;color:var(--faint);">–</span></div>')
        value = float(value)
        delta_pct = (value - price) / value * 100
        color = _ladder_bar_color(delta_pct)
        return (f'<div style="display:flex;align-items:center;gap:12px;padding:9px 0;border-bottom:0.5px solid var(--line-2);">'
               f'<span style="flex:1;font-size:12.5px;color:var(--muted);">{label}</span>'
               f'<div style="width:{bar_width}px;flex:none;height:5px;border-radius:3px;background:var(--uv-track,#EEF1F5);position:relative;">'
               f'<div style="position:absolute;left:0;top:0;height:5px;border-radius:3px;width:{min(100.0, value / scale * 100):.1f}%;background:{color};"></div></div>'
               f'<span style="font-family:var(--uv-mono);font-size:12.5px;font-weight:500;width:64px;text-align:right;">{currency}{value:,.0f}</span>'
               f'<span style="font-family:var(--uv-mono);font-size:11px;width:52px;text-align:right;color:{color};">{delta_pct:+.1f}%</span></div>')

    rows_html = "".join(_row(lbl, v) for lbl, v in models)

    # Composite row is a flat label+value pair (no bar, no delta) — matches
    # Uvalu.dc.html's "Composite fair value" row in both the Analysis screen
    # and the drawer, which is visually distinct from the per-model rows
    # above it, not just a bolded variant of the same shape.
    composite_html = ""
    if composite is not None and pd.notna(composite) and composite > 0:
        composite = float(composite)
        # Composite value isn't width-constrained like the per-model value
        # column (that one stays 0dp — a real fair value can run into the
        # thousands for this app's actual stock universe, unlike the
        # design's smaller demo figures, and would overflow its fixed 64px
        # column at 2dp), so it can show full 2-decimal precision safely.
        composite_html = (f'<div style="display:flex;align-items:center;gap:12px;padding:11px 0 2px;">'
                          f'<span style="flex:1;font-size:12.5px;font-weight:600;">{composite_label}</span>'
                          f'<span style="font-family:var(--uv-mono);font-size:14px;font-weight:600;color:var(--mint);">{currency}{composite:,.2f}</span></div>')

    st.markdown(rows_html + composite_html, unsafe_allow_html=True)


def _fair_value_bar_html(price: float | None, fair_value: float | None, mos_pct: float | None,
                         currency: str = "€", data_thin: bool = False) -> str:
    """Raw markup for the price-vs-fair-value ladder — factored out of
    fair_value_bar_compact() so holdings_row_html() can embed it inside a
    larger row grid without a nested st.markdown() call.

    `data_thin` (WP-E) marks a row that has no fair value because its
    fundamentals record came back incomplete and is being refetched — rendered
    as a "fv pending" chip rather than the bare "—" a genuinely unvaluable
    business gets."""
    if fair_value is None or pd.isna(fair_value) or not price or pd.isna(price) or mos_pct is None or pd.isna(mos_pct):
        if data_thin:
            return ('<span title="Fair value pending: this holding&#39;s fundamentals record came '
                    'back incomplete and is being refetched" style="font:500 10px var(--uv-mono);'
                    'color:var(--uv-muted,var(--muted));border:0.5px solid var(--line);'
                    'border-radius:5px;padding:1px 7px;white-space:nowrap;">fv pending</span>')
        return '<span style="color:var(--uv-faint,var(--faint));">—</span>'
    price, fair_value, mos_pct = float(price), float(fair_value), float(mos_pct)
    color = _ladder_bar_color(mos_pct)
    scale = max(price, fair_value) * 1.08
    price_pct = min(100.0, price / scale * 100)
    fair_pct = min(100.0, fair_value / scale * 100)
    # Single-line — see the matching note in holdings_row_html().
    return (f'<div style="display:flex;justify-content:space-between;font:500 10.5px var(--uv-mono);margin-bottom:5px">'
           f'<span>{currency}{price:,.2f}</span><span style="color:var(--uv-muted)">fv {currency}{fair_value:,.2f}</span></div>'
           f'<div style="position:relative;height:7px;border-radius:4px;background:var(--uv-track);">'
           f'<div style="position:absolute;left:0;top:0;height:100%;border-radius:4px;width:{price_pct:.1f}%;background:{color};"></div>'
           f'<div style="position:absolute;top:-4px;width:0;height:15px;border-left:1.5px dashed var(--axis,#5F5E5A);'
           f'left:{fair_pct:.1f}%;"></div></div>')


def fair_value_bar_compact(price: float, fair_value: float | None, mos_pct: float | None,
                           currency: str = "€") -> None:
    """Single price-vs-fair-value ladder — for list/row contexts (e.g.
    Dashboard holdings) where a full multi-model ladder wouldn't fit.

    The bar fills from €0 to the current price on a 0-to-max(price,fair
    value)*1.08 scale, colored in three tiers (undervalued/near fair/
    overvalued); a dashed vertical marker pins the fair-value point on that
    same scale — matching Uvalu.dc.html's "Holdings · price vs fair value"
    ladder exactly (its fillStyle + markerStyle).
    """
    st.markdown(_fair_value_bar_html(price, fair_value, mos_pct, currency), unsafe_allow_html=True)


# ── Holdings row (fixed-px CSS Grid) ────────────────────────────────────────
# st.columns() only supports relative-ratio widths, not Uvalu.dc.html's
# actual grid-template-columns:210px 78px 1fr 82px 66px 108px 78px — every
# attempt to approximate those proportions with ratios produced visible
# drift (columns too wide/narrow at different viewport sizes) and fighting
# Streamlit's own flex/margin-auto vertical-centering caused a string of
# follow-on bugs (wrong intrinsic cell heights, asymmetric padding). Building
# the row as one raw CSS Grid via a single st.markdown() call matches the
# design byte-for-byte and sidesteps all of that — the grid's own
# align-items:center handles vertical centering natively. The one thing this
# can't do is a native onClick, so the caller renders this in a wide column
# next to a normal narrow st.button("→", ...) column for the drawer link.
HOLDINGS_GRID_COLS = "210px 78px 1fr 82px 66px 108px 78px"


def holdings_row_html(*, ticker: str, sector: str | None, name: str,
                      decision: str, veto: bool,
                      price: float | None, fair_value: float | None, mos_pct: float | None,
                      weight: float, value: float, day_change_pct: float | None,
                      price_stale: bool = False, data_thin: bool = False,
                      currency: str = "€") -> str:
    """Full inner grid markup for one Holdings table row — ticker+sector+name,
    signal badge, fair-value ladder, margin-of-safety/weight/value, and a
    day-change chip — matching Uvalu.dc.html's row spec column-for-column.
    `mos_pct` is the margin of safety, (fair_value − price) / fair_value — the
    same convention as _margin_of_safety() and the ladder legend, not raw
    upside (fair_value / price − 1). `price_stale` dims the day-change chip and
    adds a "delayed quote" tooltip when this row isn't on a fresh intraday
    tick (WP-DQ8). `data_thin` (WP-E) renders "fv pending" for the ladder and
    margin-of-safety cells instead of a bare "—" when there's no fair value
    because the fundamentals record came back incomplete. Embed inside an outer
    st.markdown(unsafe_allow_html=True) call; pair with a
    HOLDINGS_GRID_COLS-templated header for aligned column labels."""
    sector_html = (f"<span style='font-size:9.5px;color:var(--muted);border:0.5px solid var(--line);"
                   f"border-radius:5px;padding:1px 6px;white-space:nowrap;'>{sector}</span>"
                   if sector and pd.notna(sector) else "")
    kind, label = signal_badge_for_decision(decision, veto=veto)
    ladder_html = _fair_value_bar_html(price, fair_value, mos_pct, currency, data_thin=data_thin)
    if mos_pct is not None and pd.notna(mos_pct):
        mos_pct = float(mos_pct)
        _mos_color = "var(--up-txt)" if mos_pct >= 0 else "var(--down-txt)"
        mos_html = (f"<span style='font-family:var(--uv-mono);font-size:13px;font-weight:500;"
                    f"color:{_mos_color};'>{mos_pct:+.1f}%</span>")
    elif data_thin:
        mos_html = ("<span title='Margin of safety pending, no fair value yet' "
                    "style='color:var(--muted);font-family:var(--uv-mono);font-size:11px;'>pending</span>")
    else:
        mos_html = "<span style='color:var(--faint);'>—</span>"
    if day_change_pct is not None and pd.notna(day_change_pct):
        day_html = chip_html(f"{float(day_change_pct):+.2f}%", float(day_change_pct) >= 0)
    else:
        day_html = "<span style='color:var(--faint);'>—</span>"
    if price_stale:
        day_html = (f"<span title='Delayed quote — not a live intraday price' "
                    f"style='opacity:0.45;'>{day_html}</span>")
    # Built as one single-line string, not a multi-line f-string template —
    # confirmed live that Streamlit's frontend pre-estimates a markdown
    # element's height from something like a newline count in the *raw*
    # source text before the real DOM renders, and never corrects it
    # afterward for HTML content (where source newlines don't correspond to
    # visual lines at all): a nicely-indented multi-line template for this
    # exact same 43px-tall grid was being sized as ~27px regardless of
    # column layout, align-items, or display:contents overrides anywhere in
    # the wrapper chain — the row height itself, not just centering, was
    # wrong. Collapsing to one line fixed it outright.
    return (f'<div style="display:grid;grid-template-columns:{HOLDINGS_GRID_COLS};gap:14px;align-items:center;">'
           f'<div style="min-width:0;"><div style="display:flex;align-items:center;gap:8px;">'
           f'<span style="font-family:var(--uv-mono);font-size:13px;font-weight:500;">{ticker}</span>{sector_html}</div>'
           f'<div style="font-size:12px;color:var(--muted);margin-top:3px;white-space:nowrap;overflow:hidden;'
           f'text-overflow:ellipsis;">{name}</div></div>'
           f'<div>{signal_badge_html(kind, label)}</div>'
           f'<div style="min-width:0;">{ladder_html}</div>'
           f'<div style="text-align:right;">{mos_html}</div>'
           f'<div style="text-align:right;font-family:var(--uv-mono);font-size:12.5px;color:var(--muted);">{weight*100:.1f}%</div>'
           f'<div style="text-align:right;font-family:var(--uv-mono);font-size:13px;font-weight:500;">{_fmt_eur(value)}</div>'
           f'<div style="text-align:right;">{day_html}</div></div>')


def _score_bar_cell_html(score: float | None) -> str:
    """Compact progress bar + number for a stock-list row's Score cell.
    Matches Uvalu.dc.html's scoreFill/scoreColor exactly: the bar is a 3-tier
    mint/teal/amber scale (>=75/>=55/below — never red, this is a composite
    Value Score where higher is always better, not a risk scale) while the
    number itself is only ever mint (>=75) or the default text color."""
    if score is None or pd.isna(score):
        return "—"
    score = float(score)
    bar_color = "var(--uv-mint)" if score >= 75 else "var(--teal, #1A8C6E)" if score >= 55 else "#C98A3A"
    text_color = "var(--uv-mint)" if score >= 75 else "var(--text, inherit)"
    pct = max(0.0, min(100.0, score))
    return f"""
<div style="display:flex;align-items:center;gap:7px;">
  <div style="flex:1;height:5px;border-radius:3px;background:var(--uv-track);position:relative;">
    <div style="position:absolute;left:0;top:0;height:5px;border-radius:3px;background:{bar_color};width:{pct:.0f}%;"></div>
  </div>
  <span style="font-family:var(--uv-mono);font-size:13px;font-weight:500;color:{text_color};flex:none;">{score:.0f}</span>
</div>"""


def stock_row(*, key: str, ticker: str, name: str, exchange: str | None, decision: str,
             veto: bool, score: float | None, mos_pct: float | None, price: float | None,
             pe: float | None, div_yield: float | None,
             show_action: bool = True, action_active: bool = False, action_help: str = "",
             action_disabled: bool = False) -> dict:
    """One custom row matching Uvalu.dc.html's Screener/Watchlist row spec:
    ticker+exchange+name, colored signal badge, score bar, colored margin of safety,
    price/P-E/yield, and a leading watchlist star. Renders as one
    hairline-divided list item (no per-row border/shadow — the caller wraps
    the whole header+rows list in one shared panel, see styles.py's
    `[class*="st-key-scr_row_"]`/`[class*="st-key-wl_row_"]` rule) — shared
    by uvalu/pages_/screener.py and watchlist.py so the two lists stay
    visually identical.

    Both callers pass show_action=True: Screener's star toggles watchlist
    membership either way, Watchlist's star is always rendered active
    (action_active=True, every row here is already on the watchlist by
    definition) and clicking it removes the ticker instead. The star glyph
    is always "★" — only its color changes via action_active — matching the
    design exactly; there's no separate outline-star glyph.

    The whole row opens the detail drawer on click — there's no separate
    trailing arrow button (matching the Dashboard holdings row's own
    whole-row click behavior): an invisible button is layered over the
    entire row via CSS (`position:absolute;inset:0`), with the leading star
    lifted above it with a higher z-index so it stays independently
    clickable instead of being swallowed by the row-wide overlay.

    `action_disabled` greys out and disables the star (pass the caller's
    own `current_user().is_viewer` check) — the star is a real write
    (toggles/removes a watchlist entry, persisted via save_watchlist()),
    so it needs the same Viewer-role gate every other write action in the
    app already has (portfolio.py's Add/Edit/Sell, drawer.py's Edit/Sell/Add).

    Returns {"view": bool, "action": bool}: `view` fires on clicking
    anywhere on the row (caller opens the drawer); `action` fires on the
    star (Screener: toggle watchlist membership; Watchlist: remove).
    """
    # Streamlit sanitizes "." to "-" when turning a widget key into its
    # ".st-key-<key>" CSS class (tickers like "CAMB.BR" are common in these
    # keys) — a raw dot in a CSS class selector is parsed as two chained
    # class selectors, not a literal character, so the color rules below
    # silently never matched without this.
    _css_key = key.replace(".", "-")
    with st.container(key=key):
        if show_action:
            _action_color = "var(--uv-mint)" if action_active else "var(--uv-muted, #5F5E5A)"
            # A per-row <style>-only markdown block is otherwise an unmarked
            # "invisible utility element" — it still counts as a sibling in
            # this row's own vertical block and eats a full ~16px flex gap
            # even at zero visible height, inflating every row far past its
            # real content height (same class of bug as styles.py's
            # uv_hidden_util rule, reused here via the same key convention).
            with st.container(key=f"uv_hidden_util_{_css_key}_action"):
                st.markdown(f"<style>.st-key-{_css_key}_action button {{ color: {_action_color} !important; }}</style>",
                           unsafe_allow_html=True)
        _widths = [0.5, 3.0, 1.0, 1.5, 1.0, 0.9, 0.8, 0.9]
        _cols = st.columns(_widths, vertical_alignment="center")
        _i = 0
        if show_action:
            with _cols[_i]:
                _action_clicked = st.button("★", key=f"{key}_action", type="tertiary",
                                            help=("Viewer role is read-only" if action_disabled else action_help),
                                            disabled=action_disabled)
        else:
            _action_clicked = False
        _i += 1
        with _cols[_i], st.container(key=f"{_css_key}_name_cell"):
            # Plain small mono text (Uvalu.dc.html's r.exch: 9px, var(--faint),
            # no border/background) — not a bordered pill; that was this
            # component's own embellishment, not part of the design spec.
            # pd.notna(), not a bare truthiness check — a manually-added
            # watchlist ticker's Exchange comes back as an actual NaN float
            # (not "" or None) when it doesn't match one of the tracked
            # exchanges, and NaN is truthy in Python, so `if exchange` let
            # the literal string "nan" through (confirmed live: "BDC nan").
            _exch_html = (f"<span style='font-size:9px;color:var(--faint);font-family:var(--uv-mono);"
                         f"margin-left:8px;'>{exchange}</span>" if exchange and pd.notna(exchange) else "")
            # Two explicit block divs (matching holdings_row_html's proven
            # compact ticker/name layout), not a <br>-separated pair of
            # inline spans — <br> plus each span's own browser default
            # line-height stacked to ~51px for this cell alone, inflating
            # the whole row well past the Dashboard holdings row's ~67px
            # (this cell was consistently the row's tallest, so its own
            # line-height set the row height for every other cell too).
            st.markdown(f"<div style='min-width:0;'>"
                       f"<div style='display:flex;align-items:center;gap:0;'>"
                       f"<span style='font-family:var(--uv-mono);font-size:13.5px;font-weight:500;'>{ticker}</span>{_exch_html}</div>"
                       f"<div style='font-size:12px;color:var(--muted);margin-top:3px;white-space:nowrap;"
                       f"overflow:hidden;text-overflow:ellipsis;'>{name}</div></div>", unsafe_allow_html=True)
        _i += 1
        with _cols[_i]:
            _kind, _label = signal_badge_for_decision(decision, veto=veto)
            st.markdown(signal_badge_html(_kind, _label), unsafe_allow_html=True)
        _i += 1
        with _cols[_i]:
            st.markdown(_score_bar_cell_html(score), unsafe_allow_html=True)
        _i += 1
        with _cols[_i]:
            if mos_pct is not None and pd.notna(mos_pct):
                # 3-tier upCol scale from Uvalu.dc.html: mint >=15% upside, plain
                # text 0-14% (priced near/at fair value), red only when negative.
                _mos_color = ("var(--uv-mint)" if mos_pct >= 15
                             else "var(--text, inherit)" if mos_pct >= 0 else "var(--down-txt)")
                # Matches Uvalu.dc.html's r.mos exactly: 13px, weight 500
                # (not the plain 400-weight the other numeric cells use —
                # upside is the one figure this table wants to read as
                # emphasized, same visual weight as the ticker/score cells).
                st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:13px;"
                           f"font-weight:500;color:{_mos_color};'>{mos_pct:+.1f}%</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div style='text-align:right;color:var(--muted);'>—</div>", unsafe_allow_html=True)
        _i += 1
        with _cols[_i]:
            # Matches r.price: mono 12.5px, var(--muted) — not the default
            # text color; price/P-E/yield are all muted-gray in the design,
            # only the ticker/score/upside figures are full-strength text.
            _price_str = f"€{price:,.2f}" if price is not None and pd.notna(price) else "—"
            st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12.5px;"
                       f"color:var(--muted);'>{_price_str}</div>", unsafe_allow_html=True)
        _i += 1
        with _cols[_i]:
            # Matches r.pe: mono 12.5px, var(--muted) — was 0.875rem (14px)
            # with no font-family, drifting from both the mockup's exact
            # size and its monospace figure column convention.
            st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12.5px;color:var(--muted);'>"
                       f"{f'{pe:.1f}' if pe is not None and pd.notna(pe) else '—'}</div>", unsafe_allow_html=True)
        _i += 1
        with _cols[_i]:
            # Matches r.dy — same fix as P/E above.
            st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12.5px;color:var(--muted);'>"
                       f"{f'{div_yield*100:.2f}%' if div_yield is not None and pd.notna(div_yield) else '—'}</div>",
                       unsafe_allow_html=True)
        # Invisible button covering the WHOLE row (styles.py positions it via
        # `position:absolute;inset:0` against the row's own position:relative)
        # — clicking anywhere on the row opens the drawer, matching the
        # Dashboard holdings row's click behavior exactly (previously scoped
        # to just the ticker/name cell). The leading star stays independently
        # clickable via a higher z-index (styles.py), so this can't swallow
        # its clicks despite sitting on top of the whole row.
        _view_clicked = st.button("View", key=f"{key}_view", type="tertiary")
    return {"view": _view_clicked, "action": _action_clicked}


def empty_results_html(message: str) -> str:
    """Centered muted placeholder text for an empty results table — matches
    Uvalu.dc.html's Screener/Watchlist "no results" panel, used in place of
    Streamlit's default st.info() alert banner. Wrap the caller's table in
    st.container(border=True) so this renders as one bordered panel like the
    header/rows it replaces would have."""
    return f'<div style="padding:48px 20px;text-align:center;color:var(--faint);font-size:13px;">{message}</div>'


def loading_skeleton_html(message: str, *, n_rows: int = 6) -> str:
    """A bordered panel with a caption and `n_rows` shimmer bars (styles.py's
    .uv-skel-bar), shown while a cold fundamentals cache is still being
    fetched. Replaces a bare st.info()/empty-state so a page paints its table
    shape immediately and visibly "fills in" as the background fetch lands
    rows. The caller pairs this with uvalu.ui.poll_while_fetching() so the
    view refreshes itself without an interaction."""
    _bars = "".join(
        f'<div class="uv-skel-bar" style="width:{w}%;margin:14px 0;"></div>'
        for w in ([92, 78, 85, 70, 88, 74, 81, 66, 90, 76][:max(1, n_rows)])
    )
    return (
        f'<div style="padding:22px 20px 8px;">'
        f'<div style="font-size:13px;color:var(--faint);margin-bottom:6px;">{message}</div>'
        f'{_bars}</div>'
    )


def fair_value_legend_row() -> None:
    """The Undervalued/Near fair/Overvalued/Fair-value-line legend strip that
    accompanies fair_value_bar_compact in a holdings/screener table header."""
    st.markdown("""
<div style="display:flex;align-items:center;gap:14px;font-size:11px;color:var(--faint);flex-wrap:wrap;">
  <div style="display:flex;align-items:center;gap:6px;"><span style="width:9px;height:9px;border-radius:2px;background:var(--mint);display:inline-block;"></span>Undervalued</div>
  <div style="display:flex;align-items:center;gap:6px;"><span style="width:9px;height:9px;border-radius:2px;background:var(--teal);display:inline-block;"></span>Near fair</div>
  <div style="display:flex;align-items:center;gap:6px;"><span style="width:9px;height:9px;border-radius:2px;background:#A32D2D;display:inline-block;"></span>Overvalued</div>
  <div style="display:flex;align-items:center;gap:6px;"><span style="width:16px;height:0;border-top:1.5px dashed var(--axis);display:inline-block;"></span>Fair value</div>
</div>""", unsafe_allow_html=True)


# ── Signals feed ─────────────────────────────────────────────────────────────

def signals_feed(items: list[tuple[str, str, str]]) -> None:
    """Colored-dot signal feed. Each item is (dot_color, bold_entity, message)."""
    if not items:
        st.caption("No recent signals.")
        return
    rows_html = "".join(f"""
<div style="display:flex;gap:9px;align-items:flex-start;margin-top:11px">
  <span style="margin-top:5px;width:7px;height:7px;border-radius:50%;background:{color};flex:none"></span>
  <div style="font:400 12px/1.45 -apple-system,sans-serif;color:var(--uv-muted)">
    <b style="color:var(--uv-navy)">{entity}</b> {message}
  </div>
</div>""" for color, entity, message in items)
    st.markdown(f'<div style="margin-top:-11px">{rows_html}</div>', unsafe_allow_html=True)


# ── Risk score visuals (radial gauge + sub-score bars) ───────────────────────
# Shared by the Dashboard risk-pulse widget (Phase 3.1) and the full Risk page's
# composite radial + six sub-scores (Phase 3.4) — same 3-tone brand scale for both.

def score_color(value: float) -> tuple[str, str]:
    """(bar/ring color, text color) for a 0-100 risk score, brand 3-tone scale.

    Returned as literal hex, not var(--uv-*) — callers feed the ring color into
    an SVG `stroke=` attribute (radial_gauge_svg), and CSS custom properties
    aren't reliably readable there the way they are inside a style="" string.
    """
    if value < 40:
        return "#1DD6A4", "#0F6E56"
    if value < 70:
        return "#854F0B", "#854F0B"
    return "#A32D2D", "#A32D2D"


def radial_gauge_svg(score: float, color: str, size: int = 96, stroke: int = 10,
                     track_color: str = "var(--line)") -> str:
    """A ring gauge (0-100) as raw <svg> markup — overlay center text separately.

    track_color defaults to the theme-aware `var(--line)` token, set via the
    `style=""` attribute rather than a bare `stroke=""` attribute — SVG
    presentation attributes don't reliably resolve CSS custom properties the
    way `style=""` strings do, so a bare `stroke="var(--line)"` silently fails
    and pins the track to whatever the browser's fallback is, never inverting
    between light/dark theme. The ring's own progress color is still passed
    as a literal hex (computed per-score, not a static token) via `stroke=`.
    """
    r = 42.0
    circumference = 2 * 3.141592653589793 * r
    score = max(0.0, min(100.0, score))
    offset = circumference * (1 - score / 100)
    return f"""<svg viewBox="0 0 100 100" style="width:{size}px;height:{size}px;transform:rotate(-90deg)">
  <circle cx="50" cy="50" r="{r}" fill="none" style="stroke:{track_color}" stroke-width="{stroke}"/>
  <circle cx="50" cy="50" r="{r}" fill="none" stroke="{color}" stroke-width="{stroke}"
          stroke-linecap="round" stroke-dasharray="{circumference:.2f}" stroke-dashoffset="{offset:.2f}"/>
</svg>"""


def quality_score_color(value: float) -> tuple[str, str]:
    """(bar/text color) for a 0-100 higher-is-better sub-score — e.g. the
    Analysis screen's Value/Quality/Momentum/Financial health/Dividend safety
    breakdown, where a high number is always good. The opposite sense of
    score_color's risk scale (there, low is good); mixing the two up made a
    strong 85/100 quality score render red. Matches Uvalu.dc.html's subScores
    coloring exactly: mint >=70, teal >=45, amber below — never red, since
    these are components of a score that's already risk-adjusted elsewhere.
    """
    if value >= 70:
        return "var(--uv-mint)", "var(--uv-mint)"
    if value >= 45:
        return "var(--teal, #1A8C6E)", "var(--teal, #1A8C6E)"
    return "#C98A3A", "#C98A3A"


def sub_score_bar_html(label: str, value: float, color: str | None = None) -> str:
    """One label/value/bar row for a sub-score list — matches the Analysis
    screen's Signal sub-scores spec (baseline-aligned 12.5px label/value,
    7px bar), its only caller today."""
    bar_color, text_color = score_color(value) if color is None else (color, color)
    return f"""
<div style="margin-bottom:14px;">
  <div style="display:flex;align-items:baseline;justify-content:space-between;margin-bottom:6px;">
    <span style="font-size:12.5px;">{label}</span><span style="font-family:var(--uv-mono);font-size:12.5px;font-weight:500;color:{text_color}">{value:.0f}</span>
  </div>
  <div style="height:7px;border-radius:4px;background:var(--uv-track);overflow:hidden;">
    <div style="width:{max(0.0, min(100.0, value)):.0f}%;height:7px;border-radius:4px;background:{bar_color}"></div>
  </div>
</div>"""


# ── Sparkline ────────────────────────────────────────────────────────────────

def sparkline_svg(values: list[float], width: int = 640, height: int = 120,
                  color: str = "#1DD6A4", fill_opacity: float = 0.28) -> str:
    """A minimal area+line sparkline as raw <svg> markup (no axes/labels)."""
    clean = [float(v) for v in values if v is not None and pd.notna(v)]
    if len(clean) < 2:
        return ""
    lo, hi = min(clean), max(clean)
    span = (hi - lo) or 1.0
    n = len(clean)
    pad = height * 0.08
    xs = [i / (n - 1) * width for i in range(n)]
    ys = [height - pad - (v - lo) / span * (height - 2 * pad) for v in clean]
    line_pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    area_pts = f"0,{height} " + line_pts + f" {width},{height}"
    gid = "uvSpark"
    return f"""<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" style="width:100%;height:{height}px;display:block">
  <defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{color}" stop-opacity="{fill_opacity}"/>
    <stop offset="1" stop-color="{color}" stop-opacity="0"/>
  </linearGradient></defs>
  <polygon points="{area_pts}" fill="url(#{gid})"/>
  <polyline points="{line_pts}" fill="none" stroke="{color}" stroke-width="2.5"/>
</svg>"""


# ── Portfolio rows ───────────────────────────────────────────────────────────
# Matches Uvalu.dc.html's Portfolio screen row specs exactly (Position/Shares/
# Avg cost/Price/Cost basis/Market value/Unrealised P&L/Weight for open
# positions; Position/Shares/Buy/Sell/Realised P&L for closed; name+ticker·
# date/amount for dividends). Same st.columns()-per-cell + real st.button()
# click-target pattern as stock_row() above (not a single raw-HTML grid block
# like holdings_row_html — these rows need real widgets: a whole-row "view"
# overlay for open positions, an optional trailing edit-pencil button for the
# full-page variants), sharing that function's z-index-layering CSS
# convention (styles.py's `pf_open_row_`/`pf_closed_row_`/`pf_div_row_`).

def _gain_color(v: float | None) -> str:
    """Matches Uvalu.dc.html's gainColor/plColor: up-txt for >=0, down-txt
    for negative — same sign convention as chip_html, just returning the
    bare color instead of a full pill (these cells aren't pills in the spec,
    just colored mono text)."""
    if v is None or pd.isna(v):
        return "var(--faint)"
    return "var(--up-txt)" if float(v) >= 0 else "var(--down-txt)"


def portfolio_open_row(*, key: str, ticker: str, exchange: str | None, name: str,
                       shares: int, avg_cost: float | None, price: float | None,
                       cost_basis: float | None, value: float | None,
                       gain: float | None, gain_pct: float | None, weight_pct: float | None,
                       show_edit: bool = False, edit_disabled: bool = False) -> dict:
    """One open-position row — the whole row opens the detail drawer on
    click (matching the mockup's `h.onClick`); `show_edit=True` (the full
    Open positions page, not the Overview preview) adds a trailing
    edit-pencil button that opens a per-row edit dialog instead.

    Returns {"view": bool, "edit": bool} — `edit` is always False when
    show_edit=False.
    """
    _css_key = key.replace(".", "-")
    _name_w = 240 if show_edit else 200
    _widths = [_name_w, 68, 88, 88, 108, 118, 132, 96] + ([32] if show_edit else [])
    with st.container(key=key):
        if show_edit:
            with st.container(key=f"uv_hidden_util_{_css_key}_edit"):
                st.markdown(f"<style>.st-key-{_css_key}_edit button {{ color: var(--faint) !important; }}"
                           f".st-key-{_css_key}_edit button:hover {{ color: var(--text) !important; }}</style>",
                           unsafe_allow_html=True)
        _cols = st.columns(_widths, vertical_alignment="center")
        _exch_html = (f"<span style='font-size:9px;color:var(--faint);font-family:var(--uv-mono);'>{exchange}</span>"
                     if exchange and pd.notna(exchange) else "")
        with _cols[0]:
            st.markdown(f"<div style='min-width:0;'><div style='display:flex;align-items:center;gap:8px;'>"
                       f"<span style='font-family:var(--uv-mono);font-size:13.5px;font-weight:500;'>{ticker}</span>{_exch_html}</div>"
                       f"<div style='font-size:12px;color:var(--muted);margin-top:3px;white-space:nowrap;"
                       f"overflow:hidden;text-overflow:ellipsis;'>{name}</div></div>", unsafe_allow_html=True)
        with _cols[1]:
            _shares_str = f"{int(shares):,}" if shares is not None and pd.notna(shares) else "—"
            st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12.5px;"
                       f"color:var(--muted);'>{_shares_str}</div>", unsafe_allow_html=True)
        with _cols[2]:
            _avg_str = f"€{avg_cost:,.2f}" if avg_cost is not None and pd.notna(avg_cost) else "—"
            st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12.5px;"
                       f"color:var(--muted);'>{_avg_str}</div>", unsafe_allow_html=True)
        with _cols[3]:
            _price_str = f"€{price:,.2f}" if price is not None and pd.notna(price) else "—"
            st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12.5px;'>{_price_str}</div>",
                       unsafe_allow_html=True)
        with _cols[4]:
            _cost_str = f"€{cost_basis:,.2f}" if cost_basis is not None and pd.notna(cost_basis) else "—"
            st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12.5px;"
                       f"color:var(--muted);'>{_cost_str}</div>", unsafe_allow_html=True)
        with _cols[5]:
            _value_str = f"€{value:,.2f}" if value is not None and pd.notna(value) else "—"
            st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:13px;"
                       f"font-weight:500;'>{_value_str}</div>", unsafe_allow_html=True)
        with _cols[6]:
            _gc = _gain_color(gain)
            _gain_str = f"€{gain:+,.0f}" if gain is not None and pd.notna(gain) else "—"
            _pct_str = f"{gain_pct:+.1f}%" if gain_pct is not None and pd.notna(gain_pct) else ""
            st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12.5px;"
                       f"font-weight:500;color:{_gc};'>{_gain_str}<div style='font-size:10.5px;font-weight:400;'>"
                       f"{_pct_str}</div></div>", unsafe_allow_html=True)
        with _cols[7]:
            _w = max(0.0, min(100.0, float(weight_pct) * 3.2)) if weight_pct is not None and pd.notna(weight_pct) else 0.0
            _weight_str = f"{weight_pct:.1f}%" if weight_pct is not None and pd.notna(weight_pct) else "—"
            st.markdown(f"<div style='display:flex;align-items:center;gap:8px;'>"
                       f"<div style='flex:1;height:6px;border-radius:3px;background:var(--uv-track,#EEF1F5);'>"
                       f"<div style='height:6px;border-radius:3px;width:{_w:.1f}%;background:var(--uv-mint);'></div></div>"
                       f"<span style='font-family:var(--uv-mono);font-size:11px;color:var(--muted);width:34px;"
                       f"text-align:right;'>{_weight_str}</span></div>", unsafe_allow_html=True)
        if show_edit:
            with _cols[8]:
                _edit_clicked = st.button("✎", key=f"{key}_edit", type="tertiary", help="Edit position",
                                          disabled=edit_disabled)
        else:
            _edit_clicked = False
        _view_clicked = st.button("View", key=f"{key}_view", type="tertiary")
    return {"view": _view_clicked, "edit": _edit_clicked}


def portfolio_closed_row(*, key: str, ticker: str, exchange: str | None, name: str, closed_date: str,
                         shares: int, buy: float | None, sell: float | None,
                         pl: float | None, pl_pct: float | None, show_edit: bool = False,
                         edit_disabled: bool = False) -> dict:
    """One closed-position row — never opens the drawer (the mockup's `s.`
    rows have no onClick, unlike the open-position `h.onClick`); `show_edit`
    adds a trailing edit-pencil button (the full Closed positions page only,
    not the Overview preview). Returns {"edit": bool}."""
    _css_key = key.replace(".", "-")
    _widths = ([400] if show_edit else [300]) + [56, 74, 74, 110] + ([32] if show_edit else [])
    with st.container(key=key):
        if show_edit:
            with st.container(key=f"uv_hidden_util_{_css_key}_edit"):
                st.markdown(f"<style>.st-key-{_css_key}_edit button {{ color: var(--faint) !important; }}"
                           f".st-key-{_css_key}_edit button:hover {{ color: var(--text) !important; }}</style>",
                           unsafe_allow_html=True)
        _cols = st.columns(_widths, vertical_alignment="center")
        _exch_html = (f"<span style='font-size:9px;color:var(--faint);font-family:var(--uv-mono);'>{exchange}</span>"
                     if exchange and pd.notna(exchange) else "")
        with _cols[0]:
            st.markdown(f"<div style='min-width:0;'><div style='display:flex;align-items:center;gap:8px;'>"
                       f"<span style='font-family:var(--uv-mono);font-size:13px;font-weight:500;'>{ticker}</span>{_exch_html}</div>"
                       f"<div style='font-size:11px;color:var(--faint);margin-top:3px;white-space:nowrap;"
                       f"overflow:hidden;text-overflow:ellipsis;'>{name} · closed {closed_date}</div></div>",
                       unsafe_allow_html=True)
        with _cols[1]:
            _shares_str = f"{int(shares):,}" if shares is not None and pd.notna(shares) else "—"
            st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12px;"
                       f"color:var(--muted);'>{_shares_str}</div>", unsafe_allow_html=True)
        with _cols[2]:
            _buy_str = f"€{buy:,.2f}" if buy is not None and pd.notna(buy) else "—"
            st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12px;"
                       f"color:var(--muted);'>{_buy_str}</div>", unsafe_allow_html=True)
        with _cols[3]:
            _sell_str = f"€{sell:,.2f}" if sell is not None and pd.notna(sell) else "—"
            st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12px;"
                       f"color:var(--muted);'>{_sell_str}</div>", unsafe_allow_html=True)
        with _cols[4]:
            _pc = _gain_color(pl)
            _pl_str = f"€{pl:+,.0f}" if pl is not None and pd.notna(pl) else "—"
            _pct_str = f"{pl_pct:+.1f}%" if pl_pct is not None and pd.notna(pl_pct) else ""
            st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12.5px;"
                       f"font-weight:500;color:{_pc};'>{_pl_str}<div style='font-size:10.5px;font-weight:400;'>"
                       f"{_pct_str}</div></div>", unsafe_allow_html=True)
        if show_edit:
            with _cols[5]:
                _edit_clicked = st.button("✎", key=f"{key}_edit", type="tertiary", help="Edit trade",
                                          disabled=edit_disabled)
        else:
            _edit_clicked = False
    return {"edit": _edit_clicked}


def portfolio_dividend_row(*, key: str, name: str, ticker: str, date: str, amount: float | None,
                           show_edit: bool = False, edit_disabled: bool = False) -> dict:
    """One dividend-payment row — flat list item, never opens the drawer;
    `show_edit` adds a trailing edit-pencil button (the full Dividends
    received page only, not the Overview preview). Returns {"edit": bool}."""
    _css_key = key.replace(".", "-")
    _widths = [6, 1.3] + ([0.4] if show_edit else [])
    with st.container(key=key):
        if show_edit:
            with st.container(key=f"uv_hidden_util_{_css_key}_edit"):
                st.markdown(f"<style>.st-key-{_css_key}_edit button {{ color: var(--faint) !important; }}"
                           f".st-key-{_css_key}_edit button:hover {{ color: var(--text) !important; }}</style>",
                           unsafe_allow_html=True)
        _cols = st.columns(_widths, vertical_alignment="center")
        with _cols[0]:
            st.markdown(f"<div style='min-width:0;'><div style='font-size:12.5px;white-space:nowrap;"
                       f"overflow:hidden;text-overflow:ellipsis;'>{name}</div><div style='font-size:10.5px;"
                       f"color:var(--faint);font-family:var(--uv-mono);'>{ticker} · {date}</div></div>",
                       unsafe_allow_html=True)
        with _cols[1]:
            _amount_str = f"€{amount:,.2f}" if amount is not None and pd.notna(amount) else "—"
            st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:13px;"
                       f"font-weight:500;color:var(--mint);'>{_amount_str}</div>", unsafe_allow_html=True)
        if show_edit:
            with _cols[2]:
                _edit_clicked = st.button("✎", key=f"{key}_edit", type="tertiary", help="Edit dividend",
                                          disabled=edit_disabled)
        else:
            _edit_clicked = False
    return {"edit": _edit_clicked}


# ── Risk page — holdings risk-contribution table ────────────────────────────

RISK_HOLDINGS_GRID_COLS = "210px 78px 68px 68px 1fr 120px"


def risk_holding_row_html(*, ticker: str, exchange: str | None, name: str,
                          weight_pct: float, beta: float | None, vol_pct: float | None,
                          contrib_pct: float, contrib_bar_pct: float,
                          flag: str, flag_color: str) -> str:
    """Inner grid markup for one Risk-page "contribution by holding" row —
    matches Uvalu.dc.html's riskVM.holdings row spec (Position/Weight/Beta/
    Vol/Contribution-bar/Flag). Embed inside an outer st.markdown() call,
    same convention as holdings_row_html(); pair with a RISK_HOLDINGS_GRID_COLS-
    templated header for aligned column labels."""
    _exch_html = (f"<span style='font-size:9px;color:var(--faint);font-family:var(--uv-mono);'>{exchange}</span>"
                 if exchange and pd.notna(exchange) else "")
    _beta_str = f"{beta:.2f}" if beta is not None and pd.notna(beta) else "—"
    _vol_str = f"{vol_pct:.0f}%" if vol_pct is not None and pd.notna(vol_pct) else "—"
    _bar_pct = max(0.0, min(100.0, contrib_bar_pct))
    return (f'<div style="display:grid;grid-template-columns:{RISK_HOLDINGS_GRID_COLS};gap:14px;align-items:center;">'
           f'<div style="min-width:0;"><div style="display:flex;align-items:center;gap:8px;">'
           f'<span style="font-family:var(--uv-mono);font-size:13.5px;font-weight:500;">{ticker}</span>{_exch_html}</div>'
           f'<div style="font-size:12px;color:var(--muted);margin-top:3px;white-space:nowrap;overflow:hidden;'
           f'text-overflow:ellipsis;">{name}</div></div>'
           f'<div style="text-align:right;font-family:var(--uv-mono);font-size:12.5px;color:var(--muted);">{weight_pct:.1f}%</div>'
           f'<div style="text-align:right;font-family:var(--uv-mono);font-size:12.5px;">{_beta_str}</div>'
           f'<div style="text-align:right;font-family:var(--uv-mono);font-size:12.5px;color:var(--muted);">{_vol_str}</div>'
           f'<div style="display:flex;align-items:center;gap:11px;">'
           f'<div style="flex:1;height:6px;border-radius:3px;background:var(--panel-2);overflow:hidden;">'
           f'<div style="height:6px;border-radius:3px;width:{_bar_pct:.1f}%;background:{flag_color if flag else "var(--teal)"};"></div></div>'
           f'<span style="font-family:var(--uv-mono);font-size:12px;width:44px;text-align:right;">{contrib_pct:.1f}%</span></div>'
           f'<div style="font-size:11px;font-weight:500;color:{flag_color};">{flag}</div></div>')
