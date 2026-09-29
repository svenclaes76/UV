"""Shared visual components used across multiple screens (redesign Phase 2):
the signal badge pill, the fair-value ladder, and the signals feed/list.

These render raw HTML via st.markdown(unsafe_allow_html=True) against the
uv-badge/brand-token CSS in uvalu/styles.py. Used by uvalu/drawer.py and
uvalu/pages_/analysis.py (the stock-detail drawer + deep-dive page).
"""
import math
import re
import unicodedata

import pandas as pd
import streamlit as st

from risk import SCORE_LOW, SCORE_ELEVATED, risk_band
from screener import _fcf_hard_veto, _trend_veto, LEVERAGE_EXEMPT_SECTORS
from settings import get_veto_thresholds
from uvalu.formatting import fmt_eur as _fmt_eur
from uvalu.i18n import (N_, _, ccy_code, fmt_date, fmt_int, fmt_money, fmt_num, fmt_pct, h_,
                        ngettext, pgettext, tr)

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
    return "neutral", _("NO DATA")


def veto_reason_str(row: "pd.Series") -> str:
    """Human-readable, stock-specific reason a row's hard veto tripped.

    Mirrors screener.py's compute_scores() `_hard_veto` formula exactly:
    ((debtToEquity > max_debt_equity) AND sector not in
    LEVERAGE_EXEMPT_SECTORS) | _fcf_hard_veto(row) [FCF negative 3
    consecutive years, falling back to the single most recent period when
    less history is available] | _trend_veto(row) [multi-year revenue
    decline / EBIT collapse / retained-earnings erosion / a recent
    dividend cut on thin cover] | (Div Flag == "At Risk" AND
    dividendCoverage < 1.0) | (averageVolume == 0) [a confirmed zero — the
    ticker genuinely hasn't traded, e.g. treasury shares or a dormant
    secondary listing] — the Div Flag condition is a single AND-combined
    condition, not two independent ones, so it's only listed as failing
    when BOTH sub-conditions hold. Shared by uvalu/drawer.py and
    uvalu/pages_/analysis.py so the two veto banners never drift out of
    sync with each other or with the real formula.
    """
    max_de = get_veto_thresholds()[0]
    de = row.get("debtToEquity"); fcf = row.get("freeCashflow")
    sector = row.get("sector")
    div_flag = row.get("Div Flag"); coverage = row.get("dividendCoverage")
    volume = row.get("averageVolume")
    reasons = []
    if pd.notna(de) and de > max_de and sector not in LEVERAGE_EXEMPT_SECTORS:
        reasons.append(_("debt/equity of {ratio}% exceeds the {limit}% limit",
                         ratio=fmt_num(de, 0), limit=fmt_num(max_de, 0)))
    if _fcf_hard_veto(row):
        history = row.get("fcfHistory")
        if isinstance(history, list) and len(history) >= 3:
            reasons.append(_("free cash flow negative for 3 consecutive years"))
        else:
            reasons.append(_("negative free cash flow ({amount})", amount=_fmt_eur(fcf)))
    reasons.extend(tr(r) for r in _trend_veto(row))
    if div_flag == "At Risk" and pd.notna(coverage) and coverage < 1.0:
        reasons.append(_("dividend flagged at risk with {coverage}× coverage", coverage=fmt_num(coverage, 2)))
    if pd.notna(volume) and volume == 0:
        reasons.append(_("no confirmed trading volume"))
    return "; ".join(reasons) if reasons else _("a hard-veto rule")


def signal_badge_html(kind: str, label: str) -> str:
    """Raw <span> markup for a signal badge — embed inside markdown/HTML contexts."""
    return f'<span class="uv-badge uv-badge-{kind}">{label}</span>'


def render_signal_tips(tips: list[tuple[str, str]]) -> None:
    """OK/NOTE/HIGH/INFO badge + plain-language text list."""
    if not tips:
        return
    st.caption(_("Signals"))
    st.caption(
        "<br>".join(
            f'{signal_badge_html(sev if sev in _TIP_LABELS else "neutral", _TIP_LABELS.get(sev, "INFO"))} {tip}'
            for sev, tip in tips
        ),
        unsafe_allow_html=True,
    )


def _html_attr(text: str) -> str:
    """Escape translated text for an HTML attribute value (title=…)."""
    import html as _html_mod
    return _html_mod.escape(text, quote=True)


# ── Column widths that fit their header ─────────────────────────────────────
# Column headers are 10px uppercase with 0.06em tracking; translations run up
# to ~35% longer than English (spec L-07), so a fixed design width that fits
# "PRICE" can't fit "GEM. AANKOOPPRIJS". fit_widths() widens a column to its
# header's estimated width; header and rows pass the same list to st.columns
# so they stay aligned.
# Glyph advances (px) at 10px uppercase + 0.06em tracking, measured in the
# browser; accented capitals use their base letter, anything else _HEADER_CHAR_PX.
_HEADER_GLYPH_PX = {
    **dict.fromkeys("0123456789", 6.0),
    "A": 7.1, "B": 6.3, "C": 6.6, "D": 7.6, "E": 5.7, "F": 5.5, "G": 7.5, "H": 7.7, "I": 3.3,
    "J": 3.8, "K": 6.4, "L": 5.3, "M": 9.6, "N": 8.1, "O": 8.1, "P": 6.2, "Q": 8.1, "R": 6.6,
    "S": 5.9, "T": 6.0, "U": 7.5, "V": 6.8, "W": 9.9, "X": 6.5, "Y": 6.1, "Z": 6.3,
    " ": 3.3, ".": 2.8, ",": 2.8, ":": 2.8, "'": 2.9, "/": 4.5, "-": 4.6, "(": 3.6, ")": 3.6,
    "&": 8.6, "%": 8.8,
}
_HEADER_CHAR_PX = 7.0
_HEADER_PAD_PX = 4      # breathing room between neighbouring headers


def header_width_px(label: str) -> float:
    """Estimated rendered width of a column header, with a 3% margin for
    columns that end up a little narrower than their design px."""
    text = unicodedata.normalize("NFKD", (label or "").upper())
    text_px = sum(_HEADER_GLYPH_PX.get(ch, _HEADER_CHAR_PX) for ch in text if not unicodedata.combining(ch))
    return text_px * 1.03 + _HEADER_PAD_PX


def fit_widths(widths: list, labels: list, *, px_per_unit: float = 1.0) -> list:
    """``widths`` with each column raised to fit its (already translated)
    header label. ``px_per_unit`` converts relative st.columns weights to px
    (1.0 when the weights are the design's px widths)."""
    out = list(widths)
    for i, label in enumerate(labels):
        if i < len(out) and label:
            out[i] = max(out[i], round(header_width_px(label) / px_per_unit, 3))
    return out


def fit_grid_cols(template: str, labels: list) -> str:
    """A CSS grid-template-columns string with each fixed ``px`` track raised
    to fit its (already translated) header label; ``fr`` tracks absorb the
    difference."""
    tracks = template.split()
    for i, label in enumerate(labels):
        if i < len(tracks) and label and tracks[i].endswith("px"):
            need = math.ceil(header_width_px(label))
            tracks[i] = f"{max(float(tracks[i][:-2]), need):g}px"
    return " ".join(tracks)


def header_cell_html(label: str, *, right: bool = False) -> str:
    """One 10px uppercase column label; ellipsis + tooltip when even the
    fitted column is narrower than the text (a narrow window)."""
    import html as _html_mod
    t = _html_mod.escape(label or "")
    align = "text-align:right;" if right else ""
    return (f'<div title="{t}" style="font-size:10px;letter-spacing:0.06em;text-transform:uppercase;'
            f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--faint);{align}">{t}</div>')


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
    "cash":   '<rect x="3" y="6" width="18" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M6 9v.01M18 15v.01"/>',
}


def kpi_card(label: str, value: str, delta_text: str = "", positive: bool = True,
            sub: str = "", icon: str = "wallet", value_color: str = "var(--text)",
            delta_style: str | None = None) -> None:
    """One headline-number card: icon+label, a large mono value, and an
    optional colored delta + grey sub-caption — matches Uvalu.dc.html's KPI
    tile exactly. `delta_text`/`sub` may be left empty for a plain value-only
    card (e.g. a count with nothing to compare it against)."""
    _icon_svg = (f'<svg width="13" height="13" style="flex:none;" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{KPI_ICONS.get(icon, "")}'
                f'</svg>')
    # `_delta_row` is built as a single-line string (not split across f-string
    # template lines) — a blank/whitespace-only line here (when delta_text is
    # "") resets CommonMark's HTML-block parsing context, and the *next*
    # line's leading spaces then get read as an indented code block instead
    # of continued HTML, rendering the sub-caption as literal escaped text.
    if delta_text and delta_style is not None:
        _delta_html = f'<span style="{delta_style}">{delta_text}</span>'
    else:
        _delta_html = chip_html(delta_text, positive) if delta_text else ""
    # Label and sub-caption stay on one line (ellipsis + tooltip) so every
    # tile keeps the same shape whatever the language's text length.
    _sub_title = re.sub(r"<[^>]+>", "", sub).replace('"', "&quot;")
    _delta_row = (f'<span style="flex:none;display:inline-flex;">{_delta_html}</span>' if _delta_html else "") + (
        f'<span title="{_sub_title}" style="font-size:11px;color:var(--faint);min-width:0;white-space:nowrap;'
        f'overflow:hidden;text-overflow:ellipsis;">{sub}</span>')
    # min-height on the delta row — the chip (padding:2px 7px around 11.5px
    # text, ~22px tall) is taller than the plain sub-caption span alone, so
    # a value-only card with no delta_text (e.g. "Avg fair value upside")
    # would otherwise render ~5px shorter than its siblings in the same
    # st.columns() row, since each card's height is purely content-driven.
    st.markdown(f"""
<div style="background:var(--panel);border:0.5px solid var(--line);border-radius:12px;padding:15px 17px;box-shadow:var(--shadow);">
  <div style="display:flex;align-items:center;gap:6px;font-size:10.5px;letter-spacing:0.06em;text-transform:uppercase;color:var(--faint);font-weight:500;">
    {_icon_svg}<span title="{re.sub(r"<[^>]+>", "", label).replace('"', "&quot;")}" style="min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{label}</span></div>
  <div style="font-family:var(--uv-mono);font-size:26px;font-weight:500;letter-spacing:-0.02em;margin-top:10px;line-height:1;color:{value_color};">{value}</div>
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


def _is_live(v) -> bool:
    return v is not None and not (isinstance(v, float) and pd.isna(v)) and v > 0


def six_model_ladder_rows(row) -> list[tuple[str, "float | None"]]:
    """The ordered (label, value) list for the drawer / Analysis "Six-model fair
    value" ladder. Always six rows in a fixed order (Graham, P/E, EPV, DDM
    single, DDM 2-stage, Analyst). FV-3: when a book-value or FCF *fallback*
    produced a value (they only do so for a loss-maker where none of
    Graham / P·E / EPV could be computed), it is slotted into the first
    still-dark of those three rows and relabelled "Book value" / "FCF value" —
    so the ladder stays six rows rather than sprouting a seventh/eighth that is
    dark for every healthy stock. Callers show the explanatory caption when
    `row` carries a live `pb_fair_value` / `fcf_fair_value`.
    """
    rows = [
        [N_("Graham Number"),     row.get("graham_number")],
        [N_("P/E fair value"),    row.get("pe_fair_value")],
        ["EPV",                   row.get("epv")],
        [N_("Dividend discount"), row.get("ddm")],
        [N_("DDM 2-stage"),       row.get("ddm_multistage")],
        [N_("Analyst Target"),    row.get("targetMeanPrice")],
    ]
    fallbacks = [(N_("Book value"), row.get("pb_fair_value")),
                 (N_("FCF value"),  row.get("fcf_fair_value"))]
    for label, value in fallbacks:
        if not _is_live(value):
            continue
        for i in (0, 1, 2):                         # Graham / P/E / EPV slots
            if not _is_live(rows[i][1]):
                rows[i] = [label, value]
                break
    return [(lbl, v) for lbl, v in rows]


# FV-6: display text for the `fv_dark_reasons` codes that `_fv_dark_reasons`
# emits from `_fair_value_models` (the codes are authoritative — built where the
# model guards live; this only formats them).
_REASON_TEXT = {
    "sector":         N_("n/a for this sector"),
    "no_eps":         N_("no positive EPS"),
    "no_book":        N_("no book value"),
    "implausible_book": N_("price too far below book value to trust"),
    "epv_negative":   N_("net debt > earnings"),
    "no_ev":          N_("no enterprise value"),
    "no_ebit":        N_("no multi-year EBIT"),
    "low_ebit":       N_("through-cycle EBIT ≤ 0"),
    "non_payer":      N_("not a dividend payer"),
    "payout_missing": N_("no usable payout ratio"),
    "payout_band":    N_("payout outside DDM range"),
    "spread":         N_("discount rate ≈ dividend growth"),
    "no_coverage":    N_("no analyst coverage"),
}
_REASON_LABELS = {"graham_number": "Graham Number", "pe_fair_value": "P/E fair value",
                  "epv": "EPV", "analyst": "Analyst Target"}


def six_model_ladder_reasons(row) -> dict:
    """FV-6: {ladder label → short 'why dark' phrase}. Formats the authoritative
    `fv_dark_reasons` codes from `_fair_value_models` — no model logic is
    re-derived here. A row scored before that field existed simply gets no
    hints (the ladder still renders) until the next re-score."""
    codes = row.get("fv_dark_reasons")
    if not isinstance(codes, dict):
        return {}
    out: dict = {}
    for key, code in codes.items():
        text = _REASON_TEXT.get(code)
        text = tr(text) if text else text
        if not text:
            continue
        if key == "ddm":
            out["Dividend discount"] = text
            out["DDM 2-stage"] = text
        elif key in _REASON_LABELS:
            out[_REASON_LABELS[key]] = text
    return out


def six_model_ladder_caption(row) -> "str | None":
    """FV-6: the one-line note under the ladder — flags the FV-3 book/FCF
    substitution and the analyst-target haircut so the printed rows reconcile
    with the composite. `None` when neither applies."""
    parts = []
    if _is_live(row.get("pb_fair_value")) or _is_live(row.get("fcf_fair_value")):
        parts.append(_("“Book value” / “FCF value” stand in where a core model (Graham, P/E, EPV) couldn’t be computed."))
    if _is_live(row.get("targetMeanPrice")):
        parts.append(_("The composite applies a −10% optimism haircut to the Analyst Target shown."))
    return " ".join(parts) if parts else None


def fair_value_ladder(price: float, models: list[tuple[str, float]],
                      composite: float | None = None, currency: str = "€",
                      composite_label: str = "Composite fair value",
                      bar_width: int = 110, reasons: "dict | None" = None,
                      basis_count: "int | None" = None,
                      basis_thin: bool = False) -> None:
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

    FV-6: `reasons` maps a dark row's label → a short "why" phrase (see
    `six_model_ladder_reasons`), shown in the bar slot and on hover.
    `basis_count` / `basis_thin` render the "basis · N of 6 models" line under
    the composite (`fv_model_count` / `fv_basis_thin`).
    """
    if not price or pd.isna(price):
        st.caption(_("Not enough model data for a fair-value ladder."))
        return
    price = float(price)
    ccy = ccy_code(currency)

    valid_vals = [float(v) for _lbl, v in models if v is not None and pd.notna(v) and v > 0]
    if not valid_vals:
        st.caption(_("Not enough model data for a fair-value ladder."))
        return
    scale = max([price] + valid_vals) * 1.08

    def _row(label: str, value: float | None) -> str:
        if value is None or pd.isna(value) or value <= 0:
            # FV-6: a dark row shows *why* in the (otherwise meaningless) bar
            # slot, with the full phrase on hover, instead of a bare empty track.
            why = (reasons or {}).get(label)
            slot = (f'<div style="width:{bar_width}px;flex:none;height:5px;border-radius:3px;background:var(--uv-track,#EEF1F5);"></div>'
                    if not why else
                    f'<span style="width:{bar_width}px;flex:none;font-size:9.5px;line-height:1.15;'
                    f'color:var(--faint);text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{why}</span>')
            _t = f' title="{why}"' if why else ''
            return (f'<div{_t} style="display:flex;align-items:center;gap:12px;padding:9px 0;border-bottom:0.5px solid var(--line-2);">'
                   f'<span style="flex:1;font-size:12.5px;color:var(--muted);">{tr(label)}</span>'
                   f'{slot}'
                   f'<span style="font-family:var(--uv-mono);font-size:12.5px;font-weight:500;width:64px;text-align:right;color:var(--faint);">–</span>'
                   f'<span style="font-family:var(--uv-mono);font-size:11px;width:52px;text-align:right;color:var(--faint);">–</span></div>')
        value = float(value)
        delta_pct = (value - price) / value * 100
        color = _ladder_bar_color(delta_pct)
        return (f'<div style="display:flex;align-items:center;gap:12px;padding:9px 0;border-bottom:0.5px solid var(--line-2);">'
               f'<span style="flex:1;font-size:12.5px;color:var(--muted);">{tr(label)}</span>'
               f'<div style="width:{bar_width}px;flex:none;height:5px;border-radius:3px;background:var(--uv-track,#EEF1F5);position:relative;">'
               f'<div style="position:absolute;left:0;top:0;height:5px;border-radius:3px;width:{min(100.0, value / scale * 100):.1f}%;background:{color};"></div></div>'
               f'<span style="font-family:var(--uv-mono);font-size:12.5px;font-weight:500;width:64px;text-align:right;">{fmt_money(value, ccy, 0)}</span>'
               f'<span style="font-family:var(--uv-mono);font-size:11px;width:52px;text-align:right;color:{color};">{fmt_pct(delta_pct, signed=True)}</span></div>')

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
                          f'<span style="flex:1;font-size:12.5px;font-weight:600;">{tr(composite_label)}</span>'
                          f'<span style="font-family:var(--uv-mono);font-size:14px;font-weight:600;color:var(--mint);">{fmt_money(composite, ccy)}</span></div>')

    # FV-6: "basis" line — how many sub-models actually back the composite, and a
    # muted flag when that's a weakly-corroborated one (fv_basis_thin).
    basis_html = ""
    if basis_count is not None and not pd.isna(basis_count):
        _c = "var(--uv-neg-txt)" if basis_thin else "var(--faint)"
        _tail = h_("· lightly corroborated") if basis_thin else ""
        _sep = " " if _tail else ""
        basis_html = (f'<div style="padding:2px 0 0;font-size:10.5px;color:{_c};">'
                      f'{h_("basis · {count} of 6 models", count=int(basis_count))}{_sep}{_tail}</div>')

    st.markdown(rows_html + composite_html + basis_html, unsafe_allow_html=True)


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
            _tip = _html_attr(_("Fair value pending: this holding's fundamentals record came back incomplete and is being refetched"))
            return (f'<span title="{_tip}" style="font:500 10px var(--uv-mono);'
                    'color:var(--uv-muted,var(--muted));border:0.5px solid var(--line);'
                    f'border-radius:5px;padding:1px 7px;white-space:nowrap;">{h_("fv pending")}</span>')
        return '<span style="color:var(--uv-faint,var(--faint));">—</span>'
    price, fair_value, mos_pct = float(price), float(fair_value), float(mos_pct)
    ccy = ccy_code(currency)
    color = _ladder_bar_color(mos_pct)
    scale = max(price, fair_value) * 1.08
    price_pct = min(100.0, price / scale * 100)
    fair_pct = min(100.0, fair_value / scale * 100)
    # Single-line — see the matching note in holdings_row_html().
    return (f'<div style="display:flex;justify-content:space-between;font:500 10.5px var(--uv-mono);margin-bottom:5px">'
           f'<span>{fmt_money(price, ccy)}</span><span style="color:var(--uv-muted)">{h_("fv {amount}", amount=fmt_money(fair_value, ccy))}</span></div>'
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
HOLDINGS_GRID_COLS = "210px 78px 1fr 82px 66px 108px 96px"


def holdings_row_html(*, ticker: str, sector: str | None, name: str,
                      decision: str, veto: bool,
                      price: float | None, fair_value: float | None, mos_pct: float | None,
                      weight: float, value: float, total_gain: float | None,
                      price_stale: bool = False, data_thin: bool = False,
                      currency: str = "€", grid_cols: str | None = None) -> str:
    """Full inner grid markup for one Holdings table row — ticker+sector+name,
    signal badge, fair-value ladder, margin-of-safety/weight/value, and a
    P&L cell — matching Uvalu.dc.html's row spec column-for-column.
    `mos_pct` is the margin of safety, (fair_value − price) / fair_value — the
    same convention as _margin_of_safety() and the ladder legend, not raw
    upside (fair_value / price − 1). `total_gain` is the position's unrealised
    P&L in € (current_value − purchase_value, excluding dividends) — same
    formula and semantics as the Portfolio page's "Unrealised P&L" column, not
    the day's price move. `price_stale` dims the P&L cell and adds a "delayed
    quote" tooltip when this row isn't on a fresh intraday tick (WP-DQ8) —
    `total_gain` is derived from the live price, so a stale quote still means
    a stale P&L figure. `data_thin` (WP-E) renders "fv pending" for the
    ladder and margin-of-safety cells instead of a bare "—" when there's no
    fair value because the fundamentals record came back incomplete. Embed
    inside an outer st.markdown(unsafe_allow_html=True) call; pair with a
    HOLDINGS_GRID_COLS-templated header for aligned column labels."""
    sector_html = (f"<span style='font-size:9.5px;color:var(--muted);border:0.5px solid var(--line);"
                   f"border-radius:5px;padding:1px 6px;white-space:nowrap;'>{tr(sector)}</span>"
                   if sector and pd.notna(sector) else "")
    kind, label = signal_badge_for_decision(decision, veto=veto)
    ladder_html = _fair_value_bar_html(price, fair_value, mos_pct, currency, data_thin=data_thin)
    if mos_pct is not None and pd.notna(mos_pct):
        mos_pct = float(mos_pct)
        _mos_color = "var(--up-txt)" if mos_pct >= 0 else "var(--down-txt)"
        mos_html = (f"<span style='font-family:var(--uv-mono);font-size:13px;font-weight:500;"
                    f"color:{_mos_color};'>{fmt_pct(mos_pct, signed=True)}</span>")
    elif data_thin:
        mos_html = (f"<span title='{_html_attr(_('Margin of safety pending, no fair value yet'))}' "
                    f"style='color:var(--muted);font-family:var(--uv-mono);font-size:11px;'>{h_('pending')}</span>")
    else:
        mos_html = "<span style='color:var(--faint);'>—</span>"
    if total_gain is not None and pd.notna(total_gain):
        total_gain = float(total_gain)
        _gain_color = "var(--up-txt)" if total_gain >= 0 else "var(--down-txt)"
        gain_html = (f"<span style='font-family:var(--uv-mono);font-size:13px;font-weight:500;"
                    f"color:{_gain_color};'>{fmt_money(total_gain, 'EUR', signed=True)}</span>")
    else:
        gain_html = "<span style='color:var(--faint);'>—</span>"
    if price_stale:
        gain_html = (f"<span title='{_html_attr(_('Delayed quote — not a live intraday price'))}' "
                    f"style='opacity:0.45;'>{gain_html}</span>")
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
    return (f'<div style="display:grid;grid-template-columns:{grid_cols or HOLDINGS_GRID_COLS};gap:14px;align-items:center;">'
           f'<div style="min-width:0;"><div style="display:flex;align-items:center;gap:8px;">'
           f'<span style="font-family:var(--uv-mono);font-size:13px;font-weight:500;">{ticker}</span>{sector_html}</div>'
           f'<div style="font-size:12px;color:var(--muted);margin-top:3px;white-space:nowrap;overflow:hidden;'
           f'text-overflow:ellipsis;">{name}</div></div>'
           f'<div>{signal_badge_html(kind, label)}</div>'
           f'<div style="min-width:0;">{ladder_html}</div>'
           f'<div style="text-align:right;">{mos_html}</div>'
           f'<div style="text-align:right;font-family:var(--uv-mono);font-size:12.5px;color:var(--muted);">{fmt_pct(weight * 100)}</div>'
           f'<div style="text-align:right;font-family:var(--uv-mono);font-size:13px;font-weight:500;">{_fmt_eur(value)}</div>'
           f'<div style="text-align:right;">{gain_html}</div></div>')


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
  <span style="font-family:var(--uv-mono);font-size:13px;font-weight:500;color:{text_color};flex:none;">{fmt_num(score, 0)}</span>
</div>"""


def stock_row(*, key: str, ticker: str, name: str, exchange: str | None, decision: str,
             veto: bool, score: float | None, mos_pct: float | None, price: float | None,
             pe: float | None, div_yield: float | None,
             show_action: bool = True, action_active: bool = False, action_help: str = "",
             action_disabled: bool = False, widths: list | None = None) -> dict:
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
        _widths = widths or [0.5, 3.0, 1.0, 1.5, 1.0, 0.9, 0.8, 0.9]
        _cols = st.columns(_widths, vertical_alignment="center")
        _i = 0
        if show_action:
            with _cols[_i]:
                _action_clicked = st.button("★", key=f"{key}_action", type="tertiary",
                                            help=(_("Viewer role is read-only") if action_disabled else action_help),
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
                           f"font-weight:500;color:{_mos_color};'>{fmt_pct(mos_pct, signed=True)}</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div style='text-align:right;color:var(--muted);'>—</div>", unsafe_allow_html=True)
        _i += 1
        with _cols[_i]:
            # Matches r.price: mono 12.5px, var(--muted) — not the default
            # text color; price/P-E/yield are all muted-gray in the design,
            # only the ticker/score/upside figures are full-strength text.
            _price_str = fmt_money(price, "EUR")
            st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12.5px;"
                       f"color:var(--muted);'>{_price_str}</div>", unsafe_allow_html=True)
        _i += 1
        with _cols[_i]:
            # Matches r.pe: mono 12.5px, var(--muted) — was 0.875rem (14px)
            # with no font-family, drifting from both the mockup's exact
            # size and its monospace figure column convention.
            st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12.5px;color:var(--muted);'>"
                       f"{fmt_num(pe, 1)}</div>", unsafe_allow_html=True)
        _i += 1
        with _cols[_i]:
            # Matches r.dy — same fix as P/E above.
            st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12.5px;color:var(--muted);'>"
                       f"{fmt_pct(div_yield, 2, fraction=True)}</div>",
                       unsafe_allow_html=True)
        # Invisible button covering the WHOLE row (styles.py positions it via
        # `position:absolute;inset:0` against the row's own position:relative)
        # — clicking anywhere on the row opens the drawer, matching the
        # Dashboard holdings row's click behavior exactly (previously scoped
        # to just the ticker/name cell). The leading star stays independently
        # clickable via a higher z-index (styles.py), so this can't swallow
        # its clicks despite sitting on top of the whole row.
        _view_clicked = st.button(_("View"), key=f"{key}_view", type="tertiary")
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


def skeleton_kpi_card_html() -> str:
    """One shimmering placeholder matching kpi_card()'s exact card shell —
    label/value/delta bars in place of real content — for a KPI tile whose
    figure isn't computable yet (e.g. Dashboard's Avg margin of safety while
    the PORTFOLIO_FETCH lane is still scoring holdings)."""
    return (
        '<div style="background:var(--panel);border:0.5px solid var(--line);border-radius:12px;'
        'padding:15px 17px;box-shadow:var(--shadow);">'
        '<div class="uv-skel-bar" style="width:60%;height:9px;margin:0;"></div>'
        '<div class="uv-skel-bar" style="width:50%;height:22px;margin:10px 0 0;"></div>'
        '<div class="uv-skel-bar" style="width:38%;height:16px;margin:9px 0 0;"></div>'
        '</div>'
    )


def skeleton_holdings_row_html(grid_cols: str | None = None) -> str:
    """One shimmering placeholder row matching holdings_row_html()'s grid
    (HOLDINGS_GRID_COLS column-for-column) — for the Dashboard Holdings table
    while the PORTFOLIO_FETCH lane hasn't scored any rows yet. Pair with
    uvalu.ui.poll_while_fetching(lane="portfolio") so the skeleton resolves
    into real rows on its own."""
    return (
        f'<div style="display:grid;grid-template-columns:{grid_cols or HOLDINGS_GRID_COLS};gap:14px;align-items:center;'
        'padding:13px 20px;border-bottom:0.5px solid var(--line-2);min-height:60px;">'
        '<div><div class="uv-skel-bar" style="width:76px;height:11px;margin:0;"></div>'
        '<div class="uv-skel-bar" style="width:130px;height:9px;margin:8px 0 0;"></div></div>'
        '<div class="uv-skel-bar" style="width:48px;height:18px;margin:0;border-radius:6px;"></div>'
        '<div class="uv-skel-bar" style="width:100%;height:6px;margin:0;border-radius:3px;"></div>'
        '<div class="uv-skel-bar" style="width:42px;height:11px;margin:0 0 0 auto;"></div>'
        '<div class="uv-skel-bar" style="width:36px;height:11px;margin:0 0 0 auto;"></div>'
        '<div class="uv-skel-bar" style="width:56px;height:11px;margin:0 0 0 auto;"></div>'
        '</div>'
    )


def skeleton_holdings_table_html(n_rows: int = 3, grid_cols: str | None = None) -> str:
    """`n_rows` stacked skeleton_holdings_row_html() rows — matches the
    Dashboard Holdings panel's real row list exactly so the panel's shape
    appears before the first row is scored."""
    return "".join(skeleton_holdings_row_html(grid_cols) for _ in range(max(1, n_rows)))


def skeleton_chart_html(height: int = 160) -> str:
    """A single shimmering block sized like a chart, for a chart whose data
    isn't ready yet."""
    return f'<div class="uv-skel-bar" style="width:100%;height:{height}px;margin:0;border-radius:8px;"></div>'


def skeleton_row(widths: list, *, name_col: int = 0) -> None:
    """Render one shimmer placeholder row via st.columns(widths) — matches
    ANY real row built the same way (stock_row, portfolio_open_row/
    portfolio_closed_row/portfolio_dividend_row) column-for-column for free,
    since it's rendered with that row's own exact widths rather than a
    hand-replicated CSS grid. `name_col` gets a two-line ticker+name-shaped
    shimmer (matching every one of those rows' own leading cell); every
    other column gets one right-aligned shimmer line."""
    for _i, _c in enumerate(st.columns(widths, vertical_alignment="center")):
        with _c:
            if _i == name_col:
                st.markdown(
                    '<div class="uv-skel-bar" style="width:70%;height:11px;margin:0;"></div>'
                    '<div class="uv-skel-bar" style="width:50%;height:9px;margin:8px 0 0;"></div>',
                    unsafe_allow_html=True)
            else:
                st.markdown(
                    '<div class="uv-skel-bar" style="width:60%;height:11px;margin:0 0 0 auto;"></div>',
                    unsafe_allow_html=True)


def skeleton_rows(widths: list, *, n: int = 5, name_col: int = 0, key_prefix: str = "uv_skel_row") -> None:
    """`n` stacked skeleton_row() rows, each hairline-divided like the real
    row lists they stand in for (stock_row/portfolio_*_row's own shared
    divider convention). Each row is its own `st.container(key=...)` — the
    divider itself is a global CSS rule keyed off `key_prefix`
    (`[class*="st-key-<key_prefix>_"]` in uvalu/styles.py), the same
    "wrap in a keyed container, style it globally" idiom every other row
    component in this app already uses (e.g. stock_row's own `st-key-scr_row_`
    rule) — a bottom-border can't be applied any other way around a row built
    from native st.columns()."""
    for _i in range(max(1, n)):
        with st.container(key=f"{key_prefix}_{_i}"):
            skeleton_row(widths, name_col=name_col)


def skeleton_filter_bar_html() -> str:
    """Six label+control shimmer shapes approximating the Screener filter
    bar's Search/Signal/Sector/Market/Min-score/Min-MoS row (scr_filter_row).
    Every control shares the same 40px height (the search input's own box,
    measured live) and the label-to-control gap is 15px (also measured live
    on the real row) — the real controls all sit in the same 40px band once
    centered in the row, so a uniform bar height is what actually reads as
    one level row instead of the previous 24/30/34px staircase, and matches
    the real row's 64px content height (9px label + 15px gap + 40px control)
    so scr_filter_panel's pinned min-height (styles.py) needs no fudging."""
    _shapes = [150, 170, 130, 130, 110, 150]
    _cells = "".join(
        f'<div style="display:flex;flex-direction:column;gap:15px;">'
        f'<div class="uv-skel-bar" style="width:60px;height:9px;margin:0;"></div>'
        f'<div class="uv-skel-bar" style="width:{_w}px;height:40px;margin:0;border-radius:8px;"></div></div>'
        for _w in _shapes
    )
    return f'<div style="display:flex;gap:32px;flex-wrap:wrap;">{_cells}</div>'


def skeleton_metrics_grid_html(n_cells: int = 6, n_cols: int = 3) -> str:
    """A `grid-template-columns:repeat(n_cols,1fr)` grid of label/value/sub
    shimmer cells — matches both the Risk page's 6-cell metrics grid
    (risk_card_metrics) and the Dashboard Conviction card's 3-cell one
    (db_conv_metrics), which use the identical grid shape at different
    cell counts."""
    _cell = (
        '<div style="padding:18px 20px;">'
        '<div class="uv-skel-bar" style="width:70%;height:9px;margin:0;"></div>'
        '<div class="uv-skel-bar" style="width:45%;height:20px;margin:9px 0 0;"></div>'
        '<div class="uv-skel-bar" style="width:80%;height:9px;margin:7px 0 0;"></div></div>'
    )
    return (f'<div style="display:grid;grid-template-columns:repeat({n_cols},1fr);">'
           f'{_cell * max(1, n_cells)}</div>')


def skeleton_gauge_card_html(size: int = 132) -> str:
    """A shimmering ring + two shimmer lines, centered — matches the Risk
    page's composite-score gauge card and the Dashboard Conviction card's
    smaller gauge (same shape at a different `size`)."""
    return (
        '<div style="display:flex;flex-direction:column;align-items:center;text-align:center;">'
        f'<div class="uv-skel-bar" style="width:{size}px;height:{size}px;margin:0;border-radius:50%;"></div>'
        '<div class="uv-skel-bar" style="width:120px;height:14px;margin:14px 0 0;"></div>'
        '<div class="uv-skel-bar" style="width:180px;height:11px;margin:8px 0 0;"></div>'
        '</div>'
    )


def skeleton_factor_rows_html(n: int = 6) -> str:
    """`n` stacked label+bar+caption shimmer blocks matching the Risk page's
    factor-breakdown rows (risk_card_factors) and its Concentration panel's
    bar rows (risk_card_conc) — same 3-line shape, both real sections use it."""
    _row = (
        '<div style="margin-bottom:15px;">'
        '<div style="display:flex;justify-content:space-between;margin-bottom:7px;">'
        '<div class="uv-skel-bar" style="width:70px;height:11px;margin:0;"></div>'
        '<div class="uv-skel-bar" style="width:50px;height:11px;margin:0;"></div></div>'
        '<div class="uv-skel-bar" style="width:100%;height:7px;margin:0;border-radius:4px;"></div>'
        '<div class="uv-skel-bar" style="width:60%;height:9px;margin:6px 0 0;"></div></div>'
    )
    return _row * max(1, n)


def skeleton_risk_holding_row_html(grid_cols: str | None = None) -> str:
    """One shimmering placeholder row matching risk_holding_row_html()'s
    grid (RISK_HOLDINGS_GRID_COLS column-for-column) — for the Risk page's
    holdings-contribution table while load_portfolio_risk() is still
    computing in the background. RISK_HOLDINGS_GRID_COLS is defined further
    down in this module (Risk holdings table section) — fine to reference
    here since it's resolved at call time, not definition time.

    Padding is baked in here (13px 20px, matching the real risk_hold_ row's
    12px 20px from its own st-key-risk_hold_ CSS) rather than relying on a
    wrapping container, since all of these rows are concatenated into one
    st.markdown() call by skeleton_risk_holdings_html() below — there's no
    per-row Streamlit container here to hang per-row CSS off of, the way
    skeleton_holdings_row_html() (Dashboard) does it the same inline way."""
    return (
        f'<div style="display:grid;grid-template-columns:{grid_cols or RISK_HOLDINGS_GRID_COLS};gap:14px;'
        'align-items:center;padding:13px 20px;border-bottom:0.5px solid var(--line-2);">'
        '<div><div class="uv-skel-bar" style="width:60px;height:11px;margin:0;"></div>'
        '<div class="uv-skel-bar" style="width:140px;height:9px;margin:8px 0 0;"></div></div>'
        '<div class="uv-skel-bar" style="width:36px;height:11px;margin:0 0 0 auto;"></div>'
        '<div class="uv-skel-bar" style="width:28px;height:11px;margin:0 0 0 auto;"></div>'
        '<div class="uv-skel-bar" style="width:28px;height:11px;margin:0 0 0 auto;"></div>'
        '<div class="uv-skel-bar" style="width:100%;height:6px;margin:0;border-radius:3px;"></div>'
        '<div class="uv-skel-bar" style="width:50px;height:11px;margin:0;"></div>'
        '</div>'
    )


def skeleton_risk_holdings_html(n_rows: int = 5, grid_cols: str | None = None) -> str:
    """`n_rows` stacked skeleton_risk_holding_row_html() rows."""
    return "".join(skeleton_risk_holding_row_html(grid_cols) for _ in range(max(1, n_rows)))


def skeleton_text_html(widths: tuple = (100, 92, 96, 60)) -> str:
    """A handful of shimmering bars of varying width mimicking paragraph
    text, for descriptive copy that loads alongside a scored result."""
    _bars = "".join(
        f'<div class="uv-skel-bar" style="width:{w}%;height:11px;margin:0;"></div>' for w in widths
    )
    return f'<div style="display:flex;flex-direction:column;gap:10px;">{_bars}</div>'


def spinner_html(label: str, size: int = 32) -> str:
    """A centered ring spinner + caption, for a whole panel with nothing else
    to show yet (matches the "Loading dashboard…" tile in the design)."""
    return (
        f'<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;'
        f'gap:14px;padding:24px 0;"><div style="width:{size}px;height:{size}px;border-radius:50%;'
        f'border:3px solid var(--line);border-top-color:var(--mint);animation:uvSpin 0.8s linear infinite;">'
        f'</div><div style="font-size:12.5px;color:var(--muted);">{label}</div></div>'
    )


def refresh_spinner_inline_html(label: str, dimmed_value: str) -> str:
    """A small inline spinner + label above a dimmed value, for a figure
    that's re-fetching in place (e.g. a ticking price) rather than loading
    for the first time."""
    return (
        '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;">'
        '<div style="display:flex;align-items:center;gap:8px;">'
        '<div style="width:14px;height:14px;border-radius:50%;border:2px solid var(--line);'
        'border-top-color:var(--teal);animation:uvSpin 0.7s linear infinite;"></div>'
        f'<span style="font-size:12.5px;color:var(--muted);">{label}</span></div>'
        f'<div style="font-family:var(--uv-mono);font-size:20px;font-weight:500;opacity:0.5;">{dimmed_value}</div>'
        '</div>'
    )


def refresh_top_bar_html() -> str:
    """A slim progress sweep pinned to the top of the viewport — a
    non-disruptive cue for a background re-fetch on a page already showing
    real data (a timer-triggered price refresh), as opposed to the
    skeleton_*_html helpers above (nothing to show yet). Render only for the
    one script run that uvalu.ui.consumed_tick() reports as a genuine timer
    tick — it disappears on its own once that run's fresh output paints.
    z-index sits above uvalu/shell.py's sticky top bar (999)."""
    return (
        '<div style="position:fixed;top:0;left:0;width:100%;height:2px;background:var(--line);'
        'z-index:1001;overflow:hidden;"><div style="position:absolute;top:0;height:2px;width:30%;'
        'background:var(--mint);animation:uvBar 0.9s ease-in-out infinite;"></div></div>'
    )


def fair_value_legend_row() -> None:
    """The Undervalued/Near fair/Overvalued/Fair-value-line legend strip that
    accompanies fair_value_bar_compact in a holdings/screener table header."""
    st.markdown(f"""
<div style="display:flex;align-items:center;gap:14px;font-size:11px;color:var(--faint);flex-wrap:wrap;">
  <div style="display:flex;align-items:center;gap:6px;"><span style="width:9px;height:9px;border-radius:2px;background:var(--mint);display:inline-block;"></span>{h_("Undervalued")}</div>
  <div style="display:flex;align-items:center;gap:6px;"><span style="width:9px;height:9px;border-radius:2px;background:var(--teal);display:inline-block;"></span>{h_("Near fair")}</div>
  <div style="display:flex;align-items:center;gap:6px;"><span style="width:9px;height:9px;border-radius:2px;background:#A32D2D;display:inline-block;"></span>{h_("Overvalued")}</div>
  <div style="display:flex;align-items:center;gap:6px;"><span style="width:16px;height:0;border-top:1.5px dashed var(--axis);display:inline-block;"></span>{h_("Fair value")}</div>
</div>""", unsafe_allow_html=True)


# ── Signals feed ─────────────────────────────────────────────────────────────

def signals_feed(items: list[tuple[str, str, str]]) -> None:
    """Colored-dot signal feed. Each item is (dot_color, bold_entity, message)."""
    if not items:
        st.caption(_("No recent signals."))
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

# tone (risk.RISK_BANDS) → (ring/bar hex, light-theme text hex, dark-theme text hex).
# The ring/bar hex is theme-constant (the Dashboard already trusts these three
# literals on both themes); the text hex mirrors runtime.theme_colors()'s
# up_txt / down_txt so a green/red label stays legible on the dark card surface,
# with the app's single house amber (#C98A3A — analysis rating, risk flags,
# stale-feed pill) for the mid tiers. Green covers "Low", amber "Moderate"+
# "Elevated", red "High"+"Critical" — break points risk.SCORE_LOW (25) and
# risk.SCORE_ELEVATED (70).
_RISK_TONE_COLORS = {
    "low":      ("#1DD6A4", "#0F6E56", "#1DD6A4"),
    "moderate": ("#C98A3A", "#C98A3A", "#C98A3A"),
    "elevated": ("#C98A3A", "#C98A3A", "#C98A3A"),
    "high":     ("#A32D2D", "#A32D2D", "#F0A6A6"),
    "critical": ("#A32D2D", "#A32D2D", "#F0A6A6"),
}


def score_color(value: float, dark: bool = False) -> tuple[str, str]:
    """(bar/ring color, text color) for a 0-100 composite risk score.

    The band cut-offs come from ``risk.risk_band`` (``RISK_BANDS``), so this
    mapper can never disagree with the Risk page's ``"Moderate risk"`` /
    ``"Elevated risk"`` label or the Dashboard's risk bar for the same score —
    the old hand-picked 40/70 split painted a 26–39 "Moderate" score green.

    Returned as literal hex, not ``var(--uv-*)`` — callers feed the ring color
    into an SVG ``stroke=`` attribute (``radial_gauge_svg``), where CSS custom
    properties don't resolve. Pass ``dark=True`` (from
    ``runtime.theme_colors().effective_light``) to get the dark-surface text hex.
    """
    _, _, tone = risk_band(value)
    ring, light_txt, dark_txt = _RISK_TONE_COLORS.get(tone, _RISK_TONE_COLORS["moderate"])
    return ring, (dark_txt if dark else light_txt)


def band_tone_color(tone: str, dark: bool = False) -> str:
    """Text hex for a quant band-label tone (``risk.band_tone`` output: ``low`` /
    ``moderate`` / ``high``); ``var(--faint)`` grey when the tone is empty (an
    ``"N/A"`` label). Lets the Risk page colour its metric-grid sub-labels on the
    same scale as the composite gauge instead of flat grey."""
    entry = _RISK_TONE_COLORS.get(tone)
    if entry is None:
        return "var(--faint)"
    return entry[2] if dark else entry[1]


def risk_score_meter_html(score: float, label: str, *, dark: bool = False,
                          heading: str | None = N_("Portfolio risk score")) -> str:
    """Horizontal composite-risk meter — gradient track + score marker + LOW/
    MODERATE/HIGH legend. Shared by the Dashboard's Conviction & risk card and
    the Risk page's gauge so both screens colour one score identically. The
    gradient stops are ``risk.SCORE_LOW`` (green→amber) and
    ``risk.SCORE_ELEVATED`` (amber→red); pass ``heading=None`` for just the
    track (the Risk page renders its own score text in the radial gauge).
    """
    num_txt = score_color(score, dark)[1]
    marker = min(100.0, max(0.0, float(score)))
    head = (
        f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:9px;">'
        f'<span style="font-size:12px;color:var(--muted);">{tr(heading)}</span>'
        f'<span style="font-family:var(--uv-mono);font-size:13px;font-weight:500;">'
        f'<span style="color:{num_txt};">{fmt_num(score, 0)}</span> · {label}</span></div>'
    ) if heading is not None else ""
    return (
        f'{head}'
        f'<div style="height:7px;border-radius:4px;background:linear-gradient(90deg,'
        f'#1DD6A4 0%,#1DD6A4 {SCORE_LOW}%,#C98A3A {SCORE_LOW}%,#C98A3A {SCORE_ELEVATED}%,'
        f'#A32D2D {SCORE_ELEVATED}%,#A32D2D 100%);position:relative;opacity:0.85;">'
        f'<div style="position:absolute;left:{marker:.1f}%;top:-3px;width:3px;height:13px;'
        f'border-radius:2px;background:var(--text);box-shadow:0 0 0 2px var(--panel);"></div></div>'
        f'<div style="display:flex;justify-content:space-between;font-size:9.5px;color:var(--faint);'
        f'margin-top:5px;font-family:var(--uv-mono);"><span>{h_("LOW")}</span><span>{h_("MODERATE")}</span><span>{h_("HIGH")}</span></div>'
    )


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
    <span style="font-size:12.5px;">{label}</span><span style="font-family:var(--uv-mono);font-size:12.5px;font-weight:500;color:{text_color}">{fmt_num(value, 0)}</span>
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
                       show_edit: bool = False, edit_disabled: bool = False,
                       income_12m: float | None = None, income_12m_gross: float | None = None,
                       ttm_yield_pct: float | None = None, yoc_pct: float | None = None,
                       widths: list | None = None) -> dict:
    """One open-position row — the whole row opens the detail drawer on
    click (matching the mockup's `h.onClick`); `show_edit=True` (the full
    Open positions page, not the Overview preview) adds a trailing
    edit-pencil button that opens a per-row edit dialog instead.

    `income_12m`/`income_12m_gross`/`ttm_yield_pct`/`yoc_pct` (WP-DIV4) add
    three columns — Income 12m (net, gross beneath), Yield, YoC net —
    matching Uvalu Dividend Management.dc.html's holdings-table spec.
    Passing None for all four (the default) renders the pre-dividend-v2
    7/8-column layout unchanged.

    Returns {"view": bool, "edit": bool} — `edit` is always False when
    show_edit=False.
    """
    _css_key = key.replace(".", "-")
    _name_w = 240 if show_edit else 200
    _show_income = income_12m is not None or ttm_yield_pct is not None or yoc_pct is not None
    _widths = [_name_w, 68, 88, 88, 108, 118, 132]
    if _show_income:
        _widths += [96, 60, 70]
    _widths += [96] + ([32] if show_edit else [])
    _widths = widths or _widths   # the page's header-fitted widths (fit_widths)
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
            _shares_str = fmt_int(int(shares)) if shares is not None and pd.notna(shares) else "—"
            st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12.5px;"
                       f"color:var(--muted);'>{_shares_str}</div>", unsafe_allow_html=True)
        with _cols[2]:
            _avg_str = fmt_money(avg_cost, "EUR")
            st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12.5px;"
                       f"color:var(--muted);'>{_avg_str}</div>", unsafe_allow_html=True)
        with _cols[3]:
            _price_str = fmt_money(price, "EUR")
            st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12.5px;'>{_price_str}</div>",
                       unsafe_allow_html=True)
        with _cols[4]:
            _cost_str = fmt_money(cost_basis, "EUR")
            st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12.5px;"
                       f"color:var(--muted);'>{_cost_str}</div>", unsafe_allow_html=True)
        with _cols[5]:
            _value_str = fmt_money(value, "EUR")
            st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:13px;"
                       f"font-weight:500;'>{_value_str}</div>", unsafe_allow_html=True)
        with _cols[6]:
            _gc = _gain_color(gain)
            _gain_str = fmt_money(gain, "EUR", 0, signed=True)
            _pct_str = fmt_pct(gain_pct, signed=True) if gain_pct is not None and pd.notna(gain_pct) else ""
            st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12.5px;"
                       f"font-weight:500;color:{_gc};'>{_gain_str}<div style='font-size:10.5px;font-weight:400;'>"
                       f"{_pct_str}</div></div>", unsafe_allow_html=True)
        _next = 7
        if _show_income:
            with _cols[7]:
                _inc_str = fmt_money(income_12m, "EUR", 0)
                _inc_gross_str = (h_("{amount} gr", amount=fmt_num(income_12m_gross, 0)) if income_12m_gross is not None
                                  and pd.notna(income_12m_gross) else "")
                st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12.5px;'>"
                           f"{_inc_str}<div style='font-size:10px;color:var(--faint);'>{_inc_gross_str}</div></div>",
                           unsafe_allow_html=True)
            with _cols[8]:
                _yld_str = fmt_pct(ttm_yield_pct)
                st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12.5px;"
                           f"color:var(--muted);'>{_yld_str}</div>", unsafe_allow_html=True)
            with _cols[9]:
                _yoc_str = fmt_pct(yoc_pct)
                _yoc_color = "var(--uv-mint)" if yoc_pct is not None and pd.notna(yoc_pct) and yoc_pct >= 4 else "inherit"
                st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12.5px;"
                           f"font-weight:500;color:{_yoc_color};'>{_yoc_str}</div>", unsafe_allow_html=True)
            _next = 10
        with _cols[_next]:
            _w = max(0.0, min(100.0, float(weight_pct) * 3.2)) if weight_pct is not None and pd.notna(weight_pct) else 0.0
            _weight_str = fmt_pct(weight_pct)
            st.markdown(f"<div style='display:flex;align-items:center;gap:8px;'>"
                       f"<div style='flex:1;height:6px;border-radius:3px;background:var(--uv-track,#EEF1F5);'>"
                       f"<div style='height:6px;border-radius:3px;width:{_w:.1f}%;background:var(--uv-mint);'></div></div>"
                       f"<span style='font-family:var(--uv-mono);font-size:11px;color:var(--muted);width:34px;"
                       f"text-align:right;'>{_weight_str}</span></div>", unsafe_allow_html=True)
        if show_edit:
            with _cols[_next + 1]:
                _edit_clicked = st.button("✎", key=f"{key}_edit", type="tertiary", help=_("Edit position"),
                                          disabled=edit_disabled)
        else:
            _edit_clicked = False
        _view_clicked = st.button(_("View"), key=f"{key}_view", type="tertiary")
    return {"view": _view_clicked, "edit": _edit_clicked}


def portfolio_closed_row(*, key: str, ticker: str, exchange: str | None, name: str, closed_date: str,
                         shares: int, buy: float | None, sell: float | None,
                         pl: float | None, pl_pct: float | None, show_edit: bool = False,
                         edit_disabled: bool = False, widths: list | None = None) -> dict:
    """One closed-position row — never opens the drawer (the mockup's `s.`
    rows have no onClick, unlike the open-position `h.onClick`); `show_edit`
    adds a trailing edit-pencil button (the full Closed positions page only,
    not the Overview preview). Returns {"edit": bool}."""
    _css_key = key.replace(".", "-")
    _widths = widths or (([400] if show_edit else [300]) + [56, 74, 74, 110] + ([32] if show_edit else []))
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
                       f"overflow:hidden;text-overflow:ellipsis;'>{h_('{name} · closed {date}', name=name, date=fmt_date(closed_date, skeleton='yMMM'))}</div></div>",
                       unsafe_allow_html=True)
        with _cols[1]:
            _shares_str = fmt_int(int(shares)) if shares is not None and pd.notna(shares) else "—"
            st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12px;"
                       f"color:var(--muted);'>{_shares_str}</div>", unsafe_allow_html=True)
        with _cols[2]:
            _buy_str = fmt_money(buy, "EUR")
            st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12px;"
                       f"color:var(--muted);'>{_buy_str}</div>", unsafe_allow_html=True)
        with _cols[3]:
            _sell_str = fmt_money(sell, "EUR")
            st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12px;"
                       f"color:var(--muted);'>{_sell_str}</div>", unsafe_allow_html=True)
        with _cols[4]:
            _pc = _gain_color(pl)
            _pl_str = fmt_money(pl, "EUR", 0, signed=True)
            _pct_str = fmt_pct(pl_pct, signed=True) if pl_pct is not None and pd.notna(pl_pct) else ""
            st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12.5px;"
                       f"font-weight:500;color:{_pc};'>{_pl_str}<div style='font-size:10.5px;font-weight:400;'>"
                       f"{_pct_str}</div></div>", unsafe_allow_html=True)
        if show_edit:
            with _cols[5]:
                _edit_clicked = st.button("✎", key=f"{key}_edit", type="tertiary", help=_("Edit trade"),
                                          disabled=edit_disabled)
        else:
            _edit_clicked = False
    return {"edit": _edit_clicked}


def portfolio_dividend_row(*, key: str, name: str, ticker: str, date: str, amount: float | None,
                           show_edit: bool = False, edit_disabled: bool = False,
                           show_breakdown: bool = False, tax: float | None = None,
                           net: float | None = None, reinvested: bool = False,
                           widths: list | None = None) -> dict:
    """One dividend-payment row — flat list item, never opens the drawer;
    `show_edit` adds a trailing edit-pencil button (the full Dividends
    received page only, not the Overview preview). `show_breakdown` swaps
    the compact Position+date/Amount shape for separate Date/Gross/Tax/Net
    columns (full page only) — all EUR-converted figures, the caller passes
    `amount`/`tax`/`net` already through portfolio.dividends_in_eur().
    Returns {"edit": bool}."""
    _css_key = key.replace(".", "-")

    def _money(v: float | None) -> str:
        return fmt_money(v, "EUR")

    if show_breakdown:
        _widths = [3.4, 1.1, 1, 0.9, 1] + ([0.4] if show_edit else [])
    else:
        _widths = [6, 1.3] + ([0.4] if show_edit else [])
    _widths = widths or _widths

    with st.container(key=key):
        if show_edit:
            with st.container(key=f"uv_hidden_util_{_css_key}_edit"):
                st.markdown(f"<style>.st-key-{_css_key}_edit button {{ color: var(--faint) !important; }}"
                           f".st-key-{_css_key}_edit button:hover {{ color: var(--text) !important; }}</style>",
                           unsafe_allow_html=True)
        _cols = st.columns(_widths, vertical_alignment="center")
        if show_breakdown:
            with _cols[0]:
                _drip = f' <span style="color:var(--faint);">{h_("· DRIP")}</span>' if reinvested else ""
                st.markdown(f"<div style='min-width:0;'><div style='font-size:12.5px;white-space:nowrap;"
                           f"overflow:hidden;text-overflow:ellipsis;'>{name}{_drip}</div><div style='font-size:10.5px;"
                           f"color:var(--faint);font-family:var(--uv-mono);'>{ticker}</div></div>",
                           unsafe_allow_html=True)
            with _cols[1]:
                st.markdown(f"<div style='font-size:12px;color:var(--muted);'>{fmt_date(date)}</div>",
                           unsafe_allow_html=True)
            with _cols[2]:
                st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12.5px;'>"
                           f"{_money(amount)}</div>", unsafe_allow_html=True)
            with _cols[3]:
                st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12.5px;"
                           f"color:var(--down-txt);'>{_money(-tax) if tax else '—'}</div>", unsafe_allow_html=True)
            with _cols[4]:
                st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:13px;"
                           f"font-weight:500;color:var(--mint);'>{_money(net)}</div>", unsafe_allow_html=True)
            _edit_col = 5
        else:
            with _cols[0]:
                st.markdown(f"<div style='min-width:0;'><div style='font-size:12.5px;white-space:nowrap;"
                           f"overflow:hidden;text-overflow:ellipsis;'>{name}</div><div style='font-size:10.5px;"
                           f"color:var(--faint);font-family:var(--uv-mono);'>{ticker} · {fmt_date(date)}</div></div>",
                           unsafe_allow_html=True)
            with _cols[1]:
                st.markdown(f"<div style='text-align:right;font-family:var(--uv-mono);font-size:13px;"
                           f"font-weight:500;color:var(--mint);'>{_money(amount)}</div>", unsafe_allow_html=True)
            _edit_col = 2

        if show_edit:
            with _cols[_edit_col]:
                _edit_clicked = st.button("✎", key=f"{key}_edit", type="tertiary", help=_("Edit dividend"),
                                          disabled=edit_disabled)
        else:
            _edit_clicked = False
    return {"edit": _edit_clicked}


# Shared by dividend_log_header_html() and dividend_log_row() so the header
# labels and every row's cells sit on the exact same tracks. One CSS grid per
# row with align-items:center (same approach as holdings_row_html() on the
# Dashboard) — per-cell st.columns() let bare pill <span>s and 1-line cells
# settle on different baselines than the 2-line Position/Foreign WH cells.
DIVIDEND_LOG_GRID_COLS = ("minmax(0,168fr) minmax(0,92fr) minmax(0,92fr) minmax(0,70fr) minmax(0,70fr) "
                          "minmax(0,62fr) minmax(0,88fr) minmax(0,92fr) minmax(0,80fr) minmax(0,92fr) "
                          "minmax(0,62fr) minmax(0,56fr)")
# Row = [grid, edit pencil]; the header uses the same split so both grids get
# the same width.
DIVIDEND_LOG_COL_SPLIT = [1, 0.028]


def dividend_log_header_html() -> str:
    """Column labels for the Dividend log, on DIVIDEND_LOG_GRID_COLS."""
    _labels = [(h_("Position"), False), (h_("Ex-date"), False), (h_("Pay date"), False), (h_("Type"), False),
               (h_("Per share"), True), (h_("Shares"), True), (h_("Gross"), True), (h_("Foreign WH"), True),
               (h_("BE 30%"), True), (h_("Net"), True), (h_("Source"), False), ("DRIP", False)]
    _cells = "".join(
        f'<div style="white-space:nowrap;{"text-align:right;" if _r else ""}">{_l}</div>' for _l, _r in _labels)
    return (f'<div style="display:grid;grid-template-columns:{DIVIDEND_LOG_GRID_COLS};gap:14px;'
            f'align-items:center;font-size:10px;letter-spacing:0.06em;text-transform:uppercase;'
            f'color:var(--faint);">{_cells}</div>')


def dividend_log_row(*, key: str, ticker: str, exchange: str | None, name: str,
                     ex_date: str, pay_date: str,
                     div_type: str, per_share: float | None, shares: int | None,
                     gross: float | None, foreign_wh: float | None, wh_note: str,
                     be_wh: float | None, net: float | None, source: str, drip: bool,
                     needs_confirm: bool = False, edit_disabled: bool = False) -> dict:
    """One row of the full Dividend log (Portfolio -> Dividends full page) —
    matches Uvalu Dividend Management.dc.html's 13-column spec (Position /
    Ex-date / Pay date / Type / Per share / Shares / Gross / Foreign WH /
    BE 30% / Net / Source / DRIP / edit). The 12 data cells are one
    DIVIDEND_LOG_GRID_COLS grid; the edit pencil sits in its own trailing
    column. Always shows the edit pencil — unlike the other row renderers
    this has no `show_edit` toggle since it's only ever used on the full
    page, never a preview list.
    Returns {"edit": bool}."""
    _css_key = key.replace(".", "-")

    def _money(v: float | None) -> str:
        return fmt_money(v, "EUR")

    _num = "text-align:right;font-family:var(--uv-mono);font-size:12px;color:var(--muted);"
    _pill = "font-size:9.5px;font-family:var(--uv-mono);padding:2px 6px;border-radius:5px;white-space:nowrap;"
    _exch_html = (f"<span style='font-size:9px;color:var(--faint);font-family:var(--uv-mono);'>{exchange}</span>"
                 if exchange and pd.notna(exchange) else "")
    # Unconfirmed pay date (auto-imported: market data has no payment date,
    # so it defaults to the ex-date) — amber + tooltip rather than extra
    # "· confirm" text, which overflowed the Pay date track onto Type.
    _pay_attr = ("style='font-size:11.5px;font-family:var(--uv-mono);white-space:nowrap;color:#C98A3A;' "
                 f"title='{_html_attr(_('Payment date not confirmed. Defaulted to the ex-date; edit to set the actual date.'))}'"
                 if needs_confirm else
                 "style='font-size:11.5px;font-family:var(--uv-mono);white-space:nowrap;'")
    _type_style = ("background:#FDF0E8;color:#854F0B;" if div_type == "Special" else
                  "color:var(--muted);border:0.5px solid var(--line);")
    _ps_str = fmt_money(per_share, "EUR")
    _sh_str = fmt_int(int(shares)) if shares is not None and pd.notna(shares) else "—"
    _fwh_str = f"−{_money(foreign_wh)}" if foreign_wh else "—"
    _be_str = f"−{_money(be_wh)}" if be_wh else "—"
    _src_style = ("background:var(--uv-soft,rgba(29,214,164,0.08));color:var(--uv-mint,#1DD6A4);"
                 if source == "auto" else "border:0.5px solid var(--line);color:var(--muted);")
    _src_label = h_("Auto") if source == "auto" else h_("Manual")
    _drip_style = ("background:var(--uv-soft,rgba(29,214,164,0.08));color:var(--uv-mint,#1DD6A4);"
                  if drip else "color:var(--faint);")
    _html = (
        f'<div style="display:grid;grid-template-columns:{DIVIDEND_LOG_GRID_COLS};gap:14px;align-items:center;">'
        f"<div style='min-width:0;'><div style='display:flex;align-items:center;gap:7px;'>"
        f"<span style='font-family:var(--uv-mono);font-size:13px;font-weight:500;'>{ticker}</span>{_exch_html}</div>"
        f"<div style='font-size:11px;color:var(--muted);margin-top:3px;white-space:nowrap;"
        f"overflow:hidden;text-overflow:ellipsis;'>{name}</div></div>"
        f"<div style='font-size:11.5px;font-family:var(--uv-mono);white-space:nowrap;'>{fmt_date(ex_date)}</div>"
        f"<div {_pay_attr}>{fmt_date(pay_date)}</div>"
        f"<div><span style='{_pill}{_type_style}'>{_html_attr(tr(div_type)) if div_type else ''}</span></div>"
        f"<div style='{_num}'>{_ps_str}</div>"
        f"<div style='{_num}'>{_sh_str}</div>"
        f"<div style='text-align:right;font-family:var(--uv-mono);font-size:12.5px;'>{_money(gross)}</div>"
        f"<div><div style='{_num}'>{_fwh_str}</div><div style='text-align:right;font-size:9.5px;"
        f"color:var(--faint);white-space:nowrap;'>{wh_note or ''}</div></div>"
        f"<div style='{_num}'>{_be_str}</div>"
        f"<div style='text-align:right;font-family:var(--uv-mono);font-size:13px;"
        f"font-weight:500;color:var(--uv-mint,#1DD6A4);'>{_money(net)}</div>"
        f"<div><span style='{_pill}{_src_style}'>{_src_label}</span></div>"
        f"<div><span style='{_pill}{_drip_style}'>{'DRIP' if drip else h_('Cash')}</span></div>"
        f"</div>"
    )
    with st.container(key=key):
        with st.container(key=f"uv_hidden_util_{_css_key}_edit"):
            st.markdown(f"<style>.st-key-{_css_key}_edit button {{ color: var(--faint) !important; }}"
                       f".st-key-{_css_key}_edit button:hover {{ color: var(--text) !important; }}</style>",
                       unsafe_allow_html=True)
        _cols = st.columns(DIVIDEND_LOG_COL_SPLIT, vertical_alignment="center", gap="small")
        with _cols[0]:
            st.markdown(_html, unsafe_allow_html=True)
        with _cols[1]:
            _edit_clicked = st.button("✎", key=f"{key}_edit", type="tertiary", help=_("Edit dividend"),
                                      disabled=edit_disabled)
    return {"edit": _edit_clicked}


# ── Risk page — holdings risk-contribution table ────────────────────────────

RISK_HOLDINGS_GRID_COLS = "210px 78px 68px 68px 1fr 120px"


def risk_holding_row_html(*, ticker: str, exchange: str | None, name: str,
                          weight_pct: float, beta: float | None, vol_pct: float | None,
                          contrib_pct: float, contrib_bar_pct: float,
                          flag: str, flag_color: str, grid_cols: str | None = None) -> str:
    """Inner grid markup for one Risk-page "contribution by holding" row —
    matches Uvalu.dc.html's riskVM.holdings row spec (Position/Weight/Beta/
    Vol/Contribution-bar/Flag). Embed inside an outer st.markdown() call,
    same convention as holdings_row_html(); pair with a RISK_HOLDINGS_GRID_COLS-
    templated header for aligned column labels."""
    _exch_html = (f"<span style='font-size:9px;color:var(--faint);font-family:var(--uv-mono);'>{exchange}</span>"
                 if exchange and pd.notna(exchange) else "")
    _beta_str = fmt_num(beta, 2)
    _vol_str = fmt_pct(vol_pct, 0)
    _bar_pct = max(0.0, min(100.0, contrib_bar_pct))
    return (f'<div style="display:grid;grid-template-columns:{grid_cols or RISK_HOLDINGS_GRID_COLS};gap:14px;align-items:center;">'
           f'<div style="min-width:0;"><div style="display:flex;align-items:center;gap:8px;">'
           f'<span style="font-family:var(--uv-mono);font-size:13.5px;font-weight:500;">{ticker}</span>{_exch_html}</div>'
           f'<div style="font-size:12px;color:var(--muted);margin-top:3px;white-space:nowrap;overflow:hidden;'
           f'text-overflow:ellipsis;">{name}</div></div>'
           f'<div style="text-align:right;font-family:var(--uv-mono);font-size:12.5px;color:var(--muted);">{fmt_pct(weight_pct)}</div>'
           f'<div style="text-align:right;font-family:var(--uv-mono);font-size:12.5px;">{_beta_str}</div>'
           f'<div style="text-align:right;font-family:var(--uv-mono);font-size:12.5px;color:var(--muted);">{_vol_str}</div>'
           f'<div style="display:flex;align-items:center;gap:11px;">'
           f'<div style="flex:1;height:6px;border-radius:3px;background:var(--panel-2);overflow:hidden;">'
           f'<div style="height:6px;border-radius:3px;width:{_bar_pct:.1f}%;background:{flag_color if flag else "var(--teal)"};"></div></div>'
           f'<span style="font-family:var(--uv-mono);font-size:12px;width:44px;text-align:right;">{fmt_pct(contrib_pct)}</span></div>'
           f'<div style="font-size:11px;font-weight:500;color:{flag_color};">{tr(flag) if flag else ""}</div></div>')


# ── Cash Management v1 ───────────────────────────────────────────────────────
# Uvalu Cash Management.dc.html: the Portfolio cash strip (balance + invested-
# vs-cash split bar) and the Cash activity ledger table. Colours map the
# mockup's hex chips onto theme tokens (--amber-* for Fee / manual FX).

MINT_CHIP_STYLE = ("display:inline-flex;font-family:var(--uv-mono);font-size:11.5px;font-weight:500;"
                   "padding:2px 7px;border-radius:5px;background:var(--soft);color:var(--mint);")

_CASH_CHIP = ("display:inline-flex;align-items:center;font-size:9.5px;font-family:var(--uv-mono);"
              "padding:2px 7px;border-radius:5px;white-space:nowrap;")
_CASH_TYPE_STYLE = {
    "Deposit":    "background:var(--up-bg);color:var(--up-txt);",
    "Withdrawal": "background:var(--down-bg);color:var(--down-txt);",
    "Buy":        "color:var(--muted);border:0.5px solid var(--line);",
    "Sell":       "color:var(--text);border:0.5px solid var(--teal);",
    "Dividend":   "background:var(--soft);color:var(--mint);",
    "Interest":   "background:var(--soft);color:var(--mint);",
    "Fee":        "background:var(--amber-bg);color:var(--amber-txt);",
    "Adjustment": "color:var(--muted);border:0.5px dashed var(--faint);",
}
# fr tracks (like DIVIDEND_LOG_GRID_COLS) — each row is its own grid now, so
# fixed px tracks could no longer share one horizontally-scrolling wrapper.
CASH_LEDGER_GRID = ("minmax(0,96fr) minmax(0,100fr) minmax(0,250fr) minmax(0,124fr) minmax(0,74fr) "
                    "minmax(0,112fr) minmax(0,112fr) minmax(0,56fr)")
# Row = [grid, edit pencil]; the header uses the same split (dividend log).
CASH_LEDGER_COL_SPLIT = [1, 0.028]


def cash_type_chip_html(type_: str) -> str:
    return f'<span style="{_CASH_CHIP}{_CASH_TYPE_STYLE.get(type_, "")}">{_html_attr(tr(type_)) if type_ else ""}</span>'


def cash_balance_block_html(balance_text: str, last_text: str) -> str:
    return (f'<div style="font-family:var(--uv-mono);font-size:23px;font-weight:500;letter-spacing:-0.02em;'
            f'line-height:1;">{balance_text}</div>'
            f'<div style="font-size:11px;color:var(--faint);margin-top:8px;white-space:nowrap;">{last_text}</div>')


def cash_alloc_html(invested_pct: float, cash_pct: float, total_text: str) -> str:
    """Invested / Cash legend, 8px split bar, total-value caption."""
    inv = max(0.0, min(100.0, invested_pct))
    return (
        '<div style="min-width:0;">'
        '<div style="display:flex;justify-content:space-between;gap:12px;font-size:11.5px;margin-bottom:8px;">'
        '<span style="display:flex;align-items:center;gap:7px;color:var(--muted);"><span style="width:8px;height:8px;'
        f'border-radius:2px;background:var(--teal);"></span>{h_("Invested")} <span style="font-family:var(--uv-mono);'
        f'color:var(--text);">{fmt_pct(invested_pct)}</span></span>'
        '<span style="display:flex;align-items:center;gap:7px;color:var(--muted);"><span style="width:8px;height:8px;'
        f'border-radius:2px;background:var(--mint);"></span>{h_("Cash")} <span style="font-family:var(--uv-mono);'
        f'color:var(--text);">{fmt_pct(cash_pct)}</span></span></div>'
        '<div style="height:8px;border-radius:4px;background:var(--panel-2);display:flex;overflow:hidden;gap:2px;">'
        f'<div style="height:100%;background:var(--teal);width:{inv:.2f}%;"></div>'
        '<div style="height:100%;background:var(--mint);flex:1;"></div></div>'
        f'<div style="font-size:11px;color:var(--faint);margin-top:8px;">'
        f'{h_("Total portfolio value {amount} · risk metrics use the invested portion only", amount=total_text)}</div></div>')


def _cash_ledger_row_html(r: dict, base: str) -> str:
    import html as _html

    import cash as _cash

    is_adj = r["type"] == "Adjustment"
    if is_adj:
        orig = h_("set to {amount}", amount=_cash.money(float(r.get("target_balance") or 0.0), base))
    else:
        amt = float(r.get("amount") or 0.0)
        orig = ("+" if amt >= 0 else "−") + (r.get("currency") or base) + " " + fmt_num(abs(amt), 2)
    src = r.get("fx_source") or "base"
    if (r.get("currency") or base) == base or is_adj:
        fx_val, fx_note, fx_color = "—", "base", "var(--faint)"
    else:
        fx_val = fmt_num(float(r.get('fx_rate') or 0), 4)
        fx_note = h_("manual") if src == "manual" else h_("ECB")
        fx_color = "var(--amber-txt)" if src == "manual" else "var(--faint)"
    ref = r.get("ref_label") or ""
    if r.get("topup"):
        ref = (ref + " · " + _("top-up")) if ref else _("top-up")
    ref_html = (f'<div style="font-size:10.5px;color:var(--faint);font-family:var(--uv-mono);margin-top:2px;'
                f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{_html.escape(ref)}</div>'
                if ref else "")
    base_amt = float(r["base"])
    base_color = "var(--up-txt)" if base_amt >= 0 else "var(--text)"
    base_txt = ("+" if base_amt >= 0 else "−") + _cash.money(abs(base_amt), base)
    auto = bool(r.get("auto"))
    src_style = ("background:var(--soft);color:var(--mint);" if auto
                 else "color:var(--muted);border:0.5px solid var(--line);")
    note = _html.escape(_cash.note_text(r) or "—")
    return (
        f'<div class="uv-cash-row" style="display:grid;grid-template-columns:{CASH_LEDGER_GRID};gap:12px;'
        f'align-items:center;">'
        f'<div style="font-size:11.5px;font-family:var(--uv-mono);white-space:nowrap;">{_cash.fmt_date(r["date"])}</div>'
        f'<div>{cash_type_chip_html(r["type"])}</div>'
        f'<div style="min-width:0;"><div style="font-size:12.5px;white-space:nowrap;overflow:hidden;'
        f'text-overflow:ellipsis;" title="{note}">{note}</div>{ref_html}</div>'
        f'<div style="text-align:right;font-family:var(--uv-mono);font-size:12px;color:var(--muted);'
        f'white-space:nowrap;">{orig}</div>'
        f'<div style="text-align:right;"><div style="font-family:var(--uv-mono);font-size:12px;color:var(--muted);">'
        f'{fx_val}</div><div style="font-size:9.5px;margin-top:2px;color:{fx_color};">{fx_note}</div></div>'
        f'<div style="text-align:right;font-family:var(--uv-mono);font-size:12.5px;font-weight:500;'
        f'color:{base_color};white-space:nowrap;">{base_txt}</div>'
        f'<div style="text-align:right;font-family:var(--uv-mono);font-size:12.5px;white-space:nowrap;">'
        f'{_cash.money(float(r["bal"]), base)}</div>'
        f'<div><span style="{_CASH_CHIP}{src_style}">{h_("Auto") if auto else h_("Manual")}</span></div></div>')


def cash_ledger_header_html(base: str = "EUR") -> str:
    """Column labels for the Cash activity ledger, on CASH_LEDGER_GRID."""
    return (f'<div style="display:grid;grid-template-columns:{CASH_LEDGER_GRID};gap:12px;align-items:center;'
            f'font-size:10px;letter-spacing:0.06em;text-transform:uppercase;color:var(--faint);white-space:nowrap;">'
            f'<div>{h_("Date")}</div><div>{h_("Type")}</div><div>{h_("Description")}</div><div style="text-align:right;">{h_("Original")}</div>'
            f'<div style="text-align:right;">{h_("FX rate")}</div><div style="text-align:right;">{h_("Amount · {currency}", currency=base)}</div>'
            f'<div style="text-align:right;">{h_("Balance")}</div><div>{h_("Source")}</div></div>')


def cash_ledger_row(*, key: str, row: dict, base: str = "EUR", editable: bool,
                    edit_disabled: bool = False) -> bool:
    """One ledger row (a cash.replay() row) + trailing pencil — same
    [grid, pencil] split as dividend_log_row. `editable` (manual entries)
    opens the Edit dialog; automatic entries open the read-only linked-entry
    view instead, hence the different tooltip. Returns True when clicked."""
    _css_key = key.replace(".", "-")
    with st.container(key=key):
        with st.container(key=f"uv_hidden_util_{_css_key}_edit"):
            st.markdown(f"<style>.st-key-{_css_key}_edit button {{ color: var(--faint) !important; }}"
                        f".st-key-{_css_key}_edit button:hover {{ color: var(--text) !important; }}</style>",
                        unsafe_allow_html=True)
        _cols = st.columns(CASH_LEDGER_COL_SPLIT, vertical_alignment="center", gap="small")
        with _cols[0]:
            st.markdown(_cash_ledger_row_html(row, base), unsafe_allow_html=True)
        with _cols[1]:
            return st.button("✎", key=f"{key}_edit", type="tertiary", disabled=edit_disabled,
                             help=_("Edit entry") if editable else _("View linked entry"))
