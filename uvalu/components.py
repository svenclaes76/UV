"""Shared visual components used across multiple screens (redesign Phase 2):
the signal badge pill, the fair-value ladder, and the signals feed/list.

These render raw HTML via st.markdown(unsafe_allow_html=True) against the
uv-badge/brand-token CSS in uvalu/styles.py. Used by uvalu/drawer.py and
uvalu/pages_/analysis.py (the stock-detail drawer + deep-dive page).
"""
import pandas as pd
import streamlit as st

from settings import get_veto_thresholds
from uvalu.formatting import fmt_eur as _fmt_eur

# ── Signal badge ─────────────────────────────────────────────────────────────

_DECISION_BADGE = {
    "Strong Buy": ("buy", "BUY"),
    "Monitor":    ("monitor", "MONITOR"),
    "Avoid":      ("avoid", "AVOID"),
}

_TIP_LABELS = {"warn": "HIGH", "caution": "NOTE", "ok": "OK", "neutral": "INFO"}


def signal_badge_for_decision(decision: str, veto: bool = False) -> tuple[str, str]:
    """Map a screener Decision string (+ veto flag) to a (kind, label) badge pair."""
    if veto:
        return "veto", "VETO"
    return _DECISION_BADGE.get(decision, ("avoid", decision.upper() if decision else "—"))


def veto_reason_str(row: "pd.Series") -> str:
    """Human-readable, stock-specific reason a row's hard veto tripped.

    Mirrors screener.py's compute_scores() `_hard_veto` formula exactly:
    (debtToEquity > max_debt_equity) | (freeCashflow < 0) |
    (Div Flag == "At Risk" AND dividendCoverage < 1.0) — the last one is a
    single AND-combined condition, not two independent ones, so it's only
    listed as failing when BOTH sub-conditions hold. Shared by
    uvalu/drawer.py and uvalu/pages_/analysis.py so the two veto banners
    never drift out of sync with each other or with the real formula.
    """
    max_de, _, _, _ = get_veto_thresholds()
    de = row.get("debtToEquity"); fcf = row.get("freeCashflow")
    div_flag = row.get("Div Flag"); coverage = row.get("dividendCoverage")
    reasons = []
    if pd.notna(de) and de > max_de:
        reasons.append(f"debt/equity of {de:.0f}% exceeds the {max_de:.0f}% limit")
    if pd.notna(fcf) and fcf < 0:
        reasons.append(f"negative free cash flow ({_fmt_eur(fcf)})")
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
                      composite: float | None = None, currency: str = "€") -> None:
    """Compact per-model fair-value list: a thin bar, the model's value, and
    its delta vs. the current price, ending in an explicit composite row —
    matching Uvalu.dc.html's Six-model fair value spec (a flat comparison
    list, not a verdict paragraph).

    `models` is an ordered list of (label, value) pairs — callers pick
    whichever of Graham #/PE fair value/DDM/Analyst target are actually
    available for a given stock. Delta is (model value − price) / model
    value, matching the same margin-of-safety convention used for the
    composite row and for fair_value_bar_compact elsewhere.
    """
    valid = [(lbl, float(v)) for lbl, v in models if v is not None and pd.notna(v) and v > 0]
    if not valid or not price or pd.isna(price):
        st.caption("Not enough model data for a fair-value ladder.")
        return

    price = float(price)
    scale = max([price] + [v for _, v in valid]) * 1.08

    def _row(label: str, value: float, delta_pct: float, bold: bool = False) -> str:
        color = _ladder_bar_color(delta_pct)
        _weight = 600 if bold else 500
        return f"""
<div style="display:flex;align-items:center;gap:10px;margin-top:8px;">
  <span style="width:84px;flex:none;font-size:12px;font-weight:{_weight};color:var(--uv-muted);text-align:right;">{label}</span>
  <div style="width:110px;flex:none;height:6px;border-radius:3px;background:var(--uv-track,#EEF1F5);position:relative;">
    <div style="position:absolute;left:0;top:0;height:6px;border-radius:3px;width:{min(100.0, value / scale * 100):.1f}%;background:{color};"></div>
  </div>
  <span style="font-family:var(--uv-mono);font-size:12.5px;font-weight:{_weight};width:64px;text-align:right;">{currency}{value:,.0f}</span>
  <span style="font-family:var(--uv-mono);font-size:11.5px;font-weight:{_weight};color:{color};width:56px;text-align:right;">{delta_pct:+.1f}%</span>
</div>"""

    rows_html = "".join(_row(lbl, v, (v - price) / v * 100) for lbl, v in valid)

    composite_html = ""
    if composite is not None and pd.notna(composite) and composite > 0:
        composite = float(composite)
        mos = (composite - price) / composite * 100
        composite_html = f"""
<div style="margin-top:10px;padding-top:10px;border-top:0.5px solid var(--uv-line,rgba(13,31,60,0.1));">
  {_row("Composite", composite, mos, bold=True)}
</div>"""

    st.markdown(f"""
<div style="font-size:10.5px;letter-spacing:0.04em;text-transform:uppercase;color:var(--uv-muted);margin-bottom:2px;">
  Current price {currency}{price:,.2f}</div>
{rows_html}
{composite_html}
""", unsafe_allow_html=True)


def fair_value_bar_compact(price: float, fair_value: float | None, mos_pct: float | None,
                           currency: str = "€") -> None:
    """Single condensed discount-to-fair-value bar — for list/row contexts
    (e.g. Screener rows, Dashboard holdings) where a full ladder wouldn't fit.

    Shows the absolute price/fair-value figures above the bar and colors it
    in three tiers (undervalued/near fair/overvalued), matching Uvalu.dc.html's
    "Holdings · price vs fair value" legend.
    """
    if fair_value is None or pd.isna(fair_value) or not price or pd.isna(price) or mos_pct is None or pd.isna(mos_pct):
        st.caption("—")
        return
    price, fair_value, mos_pct = float(price), float(fair_value), float(mos_pct)
    if mos_pct > _NEAR_FAIR_BAND:
        color = "var(--uv-mint)"
    elif mos_pct >= -_NEAR_FAIR_BAND:
        color = "var(--teal, #1A8C6E)"
    else:
        color = "var(--uv-neg-txt)"
    pos = mos_pct >= 0
    width = min(100.0, abs(mos_pct))
    bar_html = (
        f'<div style="position:absolute;right:50%;width:{width/2:.1f}%;height:8px;background:{color};border-radius:4px"></div>'
        f'<div style="position:absolute;left:50%;top:-2px;width:1.5px;height:12px;background:var(--axis,#5F5E5A)"></div>'
        if not pos else
        f'<div style="position:absolute;left:0;width:{width:.1f}%;height:8px;background:{color};border-radius:4px"></div>'
    )
    st.markdown(f"""
<div style="display:flex;justify-content:space-between;font:500 10.5px var(--uv-mono);margin-bottom:5px">
  <span>{currency}{price:,.2f}</span><span style="color:var(--uv-muted)">fv {currency}{fair_value:,.2f}</span>
</div>
<div style="height:8px;border-radius:4px;background:var(--uv-track);position:relative;overflow:hidden">{bar_html}</div>
""", unsafe_allow_html=True)


def _score_bar_cell_html(score: float | None) -> str:
    """Compact progress bar + number for a stock-list row's Score cell.
    3-tier brand coloring — higher composite Value Score is better here
    (BUY territory), the opposite sense of the risk-score scale."""
    if score is None or pd.isna(score):
        return "—"
    score = float(score)
    color = "var(--uv-pos-txt)" if score >= 70 else "#854F0B" if score >= 40 else "var(--uv-neg-txt)"
    pct = max(0.0, min(100.0, score))
    return f"""
<div style="display:flex;align-items:center;gap:7px;">
  <div style="flex:1;height:5px;border-radius:3px;background:var(--uv-track);position:relative;">
    <div style="position:absolute;left:0;top:0;height:5px;border-radius:3px;background:{color};width:{pct:.0f}%;"></div>
  </div>
  <span style="font-family:var(--uv-mono);font-size:12px;color:{color};flex:none;">{score:.0f}</span>
</div>"""


def stock_row(*, key: str, ticker: str, name: str, exchange: str | None, decision: str,
             veto: bool, score: float | None, mos_pct: float | None, price: float | None,
             pe: float | None, div_yield: float | None, rank: int | None = None,
             action_icon: str = "★", action_help: str = "") -> dict:
    """One custom row matching Uvalu.dc.html's Screener/Watchlist row spec:
    ticker+exchange+name, colored signal badge, score bar, colored MoS/upside,
    price/P-E/yield, a leading star-or-remove action, and a trailing view
    button (opens the detail drawer). Renders inside its own bordered
    container — shared by uvalu/pages_/screener.py and watchlist.py so the
    two lists stay visually identical.

    Returns {"view": bool, "action": bool}: `view` fires on the trailing "→"
    button (caller opens the drawer); `action` fires on the leading button
    (caller decides what it means — toggle watchlist membership on Screener,
    remove from the watchlist on Watchlist).
    """
    with st.container(key=key, border=True):
        _widths = [0.4] + ([0.4] if rank is not None else []) + [2.3, 0.9, 1.3, 0.9, 0.8, 0.7, 0.8, 0.5]
        _cols = st.columns(_widths, vertical_alignment="center")
        _i = 0
        with _cols[_i]:
            _action_clicked = st.button(action_icon, key=f"{key}_action", type="tertiary", help=action_help)
        _i += 1
        if rank is not None:
            with _cols[_i]:
                st.caption(f"#{rank}")
            _i += 1
        with _cols[_i]:
            _exch_html = (f"<span style='font-size:9.5px;color:var(--muted);border:0.5px solid var(--line);"
                         f"border-radius:5px;padding:1px 6px;margin-left:6px;'>{exchange}</span>"
                         if exchange else "")
            st.markdown(f"<span style='font-family:var(--uv-mono);font-size:13px;font-weight:500;'>{ticker}</span>"
                       f"{_exch_html}<br><span style='color:var(--muted);font-size:12px;white-space:nowrap;"
                       f"overflow:hidden;text-overflow:ellipsis;'>{name}</span>", unsafe_allow_html=True)
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
                _mos_color = "var(--up-txt)" if mos_pct >= 0 else "var(--down-txt)"
                st.markdown(f"<span style='font-family:var(--uv-mono);font-size:12.5px;color:{_mos_color};'>"
                           f"{mos_pct:+.1f}%</span>", unsafe_allow_html=True)
            else:
                st.caption("—")
        _i += 1
        with _cols[_i]:
            st.markdown(f"<span style='font-family:var(--uv-mono);font-size:12.5px;'>€{price:,.2f}</span>"
                       if price is not None and pd.notna(price) else "—", unsafe_allow_html=True)
        _i += 1
        with _cols[_i]:
            st.caption(f"{pe:.1f}" if pe is not None and pd.notna(pe) else "—")
        _i += 1
        with _cols[_i]:
            st.caption(f"{div_yield*100:.2f}%" if div_yield is not None and pd.notna(div_yield) else "—")
        _i += 1
        with _cols[_i]:
            _view_clicked = st.button("→", key=f"{key}_view", type="tertiary")
    return {"view": _view_clicked, "action": _action_clicked}


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


def sub_score_bar_html(label: str, value: float, color: str | None = None) -> str:
    """One label/value/bar row for a sub-score list (e.g. Concentration, Volatility)."""
    bar_color, text_color = score_color(value) if color is None else (color, color)
    return f"""
<div>
  <div style="display:flex;justify-content:space-between;font:400 11px -apple-system,sans-serif;color:var(--uv-muted)">
    <span>{label}</span><span style="font-family:var(--uv-mono);color:{text_color}">{value:.0f}</span>
  </div>
  <div style="height:4px;border-radius:2px;background:var(--uv-track);margin-top:3px">
    <div style="width:{max(0.0, min(100.0, value)):.0f}%;height:4px;border-radius:2px;background:{bar_color}"></div>
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
