"""Shared visual components used across multiple screens (redesign Phase 2):
the signal badge pill, the fair-value ladder, and the signals feed/list.

These render raw HTML via st.markdown(unsafe_allow_html=True) against the
uv-badge/brand-token CSS in uvalu/styles.py, matching the pattern already
used by uvalu/stock_dialog.py (which this module's badge/tips helpers were
extracted from).
"""
import pandas as pd
import streamlit as st

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

def fair_value_ladder(price: float, models: list[tuple[str, float]],
                      composite: float | None = None, currency: str = "€") -> None:
    """Horizontal-bar ladder comparing fair-value models against the current price.

    `models` is an ordered list of (label, value) pairs — callers pick whichever
    of Graham #/PE fair value/DDM/Analyst target are actually available for a
    given stock. Bars are teal when the model sits above price (undervalued
    signal by that model), red when below. A vertical rule marks the current
    price; a composite margin-of-safety callout renders underneath when
    `composite` is given.
    """
    valid = [(lbl, float(v)) for lbl, v in models if v is not None and pd.notna(v) and v > 0]
    if not valid or not price or pd.isna(price):
        st.caption("Not enough model data for a fair-value ladder.")
        return

    price = float(price)
    scale = max([price] + [v for _, v in valid]) * 1.08
    price_pct = min(96.0, max(4.0, price / scale * 100))

    rows_html = "".join(f"""
<div style="display:flex;align-items:center;gap:10px;margin-top:10px">
  <span style="width:84px;flex:none;font-size:12px;color:var(--uv-muted);text-align:right">{lbl}</span>
  <div style="flex:1;height:26px;position:relative;background:rgba(13,31,60,0.05);border-radius:6px">
    <div style="position:absolute;left:0;top:0;height:26px;border-radius:6px;width:{min(100.0, v / scale * 100):.1f}%;
                background:{"var(--uv-mint)" if v >= price else "var(--uv-neg-txt)"};display:flex;align-items:center;
                justify-content:flex-end;padding-right:8px;font:500 11px var(--uv-mono);
                color:{"#04231a" if v >= price else "#fff"};white-space:nowrap">{currency}{v:,.0f}</div>
  </div>
</div>""" for lbl, v in valid)

    composite_html = ""
    if composite is not None and pd.notna(composite) and composite > 0:
        composite = float(composite)
        mos = (composite - price) / composite * 100
        above = sum(1 for _, v in valid if v >= price)
        if above == len(valid):
            verdict = "All models above price — broad undervaluation"
        elif above > len(valid) / 2:
            verdict = "Most models above price — likely undervalued"
        elif above > 0:
            verdict = "Mixed signal across models"
        else:
            verdict = "All models below price — broad overvaluation"
        pos = mos >= 0
        bg, txt = ("var(--uv-pos-bg)", "var(--uv-pos-txt)") if pos else ("var(--uv-neg-bg)", "var(--uv-neg-txt)")
        composite_html = f"""
<div style="margin-top:16px;padding:12px 14px;background:{bg};border-radius:10px">
  <div style="font:500 12.5px -apple-system,sans-serif;color:{txt}">{verdict}</div>
  <div style="font:400 12px -apple-system,sans-serif;color:{txt};opacity:0.85;margin-top:3px">
    Composite fair value {currency}{composite:,.0f} · margin of safety <b>{mos:+.1f}%</b>
  </div>
</div>"""

    st.markdown(f"""
<div style="position:relative;padding-top:18px">
  <div style="position:absolute;left:{price_pct:.1f}%;top:18px;bottom:0;width:2px;background:var(--uv-navy);z-index:2"></div>
  <div style="position:absolute;left:{price_pct:.1f}%;top:0;transform:translateX(-50%);white-space:nowrap;
              font:500 10.5px var(--uv-mono);color:var(--uv-navy);z-index:3">{currency}{price:,.2f} price</div>
  {rows_html}
  {composite_html}
</div>
""", unsafe_allow_html=True)


def fair_value_bar_compact(price: float, fair_value: float | None, mos_pct: float | None,
                           currency: str = "€") -> None:
    """Single condensed discount-to-fair-value bar — for list/row contexts
    (e.g. Screener rows) where a full ladder wouldn't fit."""
    if fair_value is None or pd.isna(fair_value) or not price or pd.isna(price) or mos_pct is None or pd.isna(mos_pct):
        st.caption("—")
        return
    mos_pct = float(mos_pct)
    pos = mos_pct >= 0
    color = "var(--uv-mint)" if pos else "var(--uv-neg-txt)"
    width = min(100.0, abs(mos_pct))
    bar_html = (
        f'<div style="position:absolute;right:50%;width:{width/2:.1f}%;height:8px;background:{color};border-radius:4px"></div>'
        f'<div style="position:absolute;left:50%;top:-2px;width:1.5px;height:12px;background:#c9c9c4"></div>'
        if not pos else
        f'<div style="position:absolute;left:0;width:{width:.1f}%;height:8px;background:{color};border-radius:4px"></div>'
    )
    label = f"{mos_pct:+.1f}% below fair value" if pos else f"{abs(mos_pct):.1f}% above fair value"
    st.markdown(f"""
<div style="height:8px;border-radius:4px;background:var(--uv-track);position:relative;overflow:hidden">{bar_html}</div>
<div style="font:500 11px var(--uv-mono);color:{color};margin-top:4px">{label}</div>
""", unsafe_allow_html=True)


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
                     track_color: str = "#EEF1F5") -> str:
    """A ring gauge (0-100) as raw <svg> markup — overlay center text separately."""
    r = 42.0
    circumference = 2 * 3.141592653589793 * r
    score = max(0.0, min(100.0, score))
    offset = circumference * (1 - score / 100)
    return f"""<svg viewBox="0 0 100 100" style="width:{size}px;height:{size}px;transform:rotate(-90deg)">
  <circle cx="50" cy="50" r="{r}" fill="none" stroke="{track_color}" stroke-width="{stroke}"/>
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
