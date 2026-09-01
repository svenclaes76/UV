"""Help page — signal legend, the six fair-value models, hard-veto rules and
an FAQ, matching Uvalu.dc.html's Help screen spec (`help.signals`/
`help.models`/`help.vetoes`/`help.faqs` in the design file's `<script>`
section). Every section here is static text with no interactive widgets, so
each card is built as one raw-HTML block (header + all rows) inside a single
`st.container(key="help_card_...", border=True)` instead of one
st.container per row — sidesteps the sibling-gap/height-underestimation CSS
dance documented for Settings/Analysis entirely, since nothing on this page
needs an individual widget key.

The six fair-value models list below stays the app's real model set (Graham
Number/PE Fair Value/EPV/DDM 1-stage/DDM 2-stage/Analyst target, see
screener.py's `_fair_value_models()`) rather than the mockup's generic
"Dividend discount"/"DCF" pair — this app has no DCF model at all, so
documenting one would describe a feature that doesn't exist. Same reasoning
for the hard-veto rules: grounded in the real `_hard_veto` formula in
screener.py's compute_scores(), not the mockup's own demo bullets — the
mockup includes a "Going-concern or audit red flags" item this app has no
corresponding check for, so it's omitted rather than documented as if it
were real. The signal legend's BUY/MONITOR text also deliberately doesn't
hardcode the mockup's demo thresholds (75 / 55) since both are
user-configurable in Settings → Screening & veto rules — stating a fixed
number here would go stale the moment someone changes that slider.

The mockup's closing "Still stuck? Contact support" banner is left out on
explicit confirmation from Sven when re-applying this design (2026-07-23) —
this app has no support channel to send anyone to, so a decorative button
that does nothing was rejected in favour of leaving it out entirely, same
call as the previous pass on this page.
"""
import streamlit as st

from uvalu import nav as nav_registry
from uvalu.components import signal_badge_html

_SIGNAL_LEGEND = [
    ("buy", "BUY", "Composite score clears the BUY threshold and the margin of safety clears its "
                  "target — both conditions together, set in Settings → Screening &amp; veto rules."),
    ("monitor", "MONITOR", "Composite score is decent but the margin of safety hasn't cleared the "
                          "target yet, or the score itself sits below the BUY threshold — worth watching."),
    ("avoid", "AVOID", "Composite score falls well below the BUY threshold."),
    ("veto", "VETO", "A hard-veto rule tripped (see below) — excluded from BUY scoring no matter "
                     "what the composite score would otherwise be."),
    ("neutral", "NO DATA", "No scored screener row for this holding — the fundamentals feed "
                           "returned nothing (or no price) for it, so there is no fair value, "
                           "score or signal to show. Not a veto."),
]

_MODELS = [
    ("Graham Number", "√(22.5 × EPS × book value per share) — Benjamin Graham's classic value "
                      "formula. Needs positive trailing earnings and book value per share."),
    ("PE Fair Value", "Trailing EPS × a sector-typical fair P/E multiple."),
    ("EPV (Earnings Power Value)", "Normalised earnings capitalised at the cost of capital, "
                                   "deliberately ignoring speculative growth."),
    ("DDM — 1-stage", "Gordon growth model: next year's expected dividend discounted at "
                      "(cost of equity − perpetual growth rate). Only applies to dividend payers."),
    ("DDM — 2-stage", "A higher-growth phase followed by a stable terminal-growth phase, each "
                      "discounted back separately. Also dividend-payer only."),
    ("Analyst target", "Mean 12-month analyst price target, sourced from Yahoo Finance."),
]

_VETO_RULES = [
    "Debt / equity exceeds the Max debt/equity threshold set in Settings → Screening &amp; veto "
    "rules (default 500%).",
    "Free cash flow (trailing twelve months) is negative.",
    "The dividend is flagged \"At risk\" (payout ratio, cash payout ratio, or coverage breach) "
    "<em>and</em> dividend coverage is below 1.0× — both conditions together, not either alone.",
]

_FAQ = [
    ("How is the composite fair value calculated?",
     "Each holding is valued by all six models. Outliers are trimmed and the remainder averaged "
     "into a single composite fair value. Margin of safety is the discount of the current price "
     "to that figure."),
    ("What does the conviction score mean?",
     "A 0–100 weighted mean of the signal scores across your scored holdings, weighted by "
     "position size. Vetoed names are excluded from the average."),
    ("How often do prices update?",
     "Quotes refresh on the interval set in Settings → Data during market hours (default every "
     "15 minutes). Fundamentals update daily after each exchange close."),
    ("Why is a holding excluded from scoring?",
     "It has breached a hard-veto rule. It still appears in your portfolio and valuations, but "
     "is left out of the conviction score until the flag clears."),
    ("Which exchanges are covered?",
     "Euronext Amsterdam/Brussels/Paris, XETRA, SIX Swiss, and Borsa Italiana."),
]

_HEADER_HTML = ('<div style="padding:15px 20px;border-bottom:0.5px solid var(--line-2);font-size:13px;'
               'font-weight:600;letter-spacing:0.03em;text-transform:uppercase;color:var(--faint);">{label}</div>')

_VETO_X_SVG = ('<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--down-txt)" '
              'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
              'style="flex:none;margin-top:2px;"><path d="M18 6L6 18M6 6l12 12"/></svg>')


def _signal_row_html(kind: str, label: str, desc: str) -> str:
    return ('<div style="display:flex;align-items:flex-start;gap:14px;padding:14px 20px;'
           'border-bottom:0.5px solid var(--line-2);">'
           f'<div style="width:74px;flex:none;padding-top:1px;">{signal_badge_html(kind, label)}</div>'
           f'<div style="font-size:13px;color:var(--muted);line-height:1.55;">{desc}</div></div>')


def _model_cell_html(name: str, desc: str) -> str:
    return ('<div style="padding:14px 20px;border-bottom:0.5px solid var(--line-2);">'
           f'<div style="font-size:13px;font-weight:500;margin-bottom:5px;">{name}</div>'
           f'<div style="font-size:12px;color:var(--muted);line-height:1.55;">{desc}</div></div>')


def _veto_row_html(rule: str) -> str:
    return ('<div style="display:flex;align-items:flex-start;gap:10px;padding:9px 0;'
           f'border-bottom:0.5px solid var(--line-2);">{_VETO_X_SVG}'
           f'<span style="font-size:12.5px;color:var(--muted);line-height:1.5;">{rule}</span></div>')


def _faq_row_html(question: str, answer: str) -> str:
    return ('<div style="padding:14px 20px;border-bottom:0.5px solid var(--line-2);">'
           f'<div style="font-size:13px;font-weight:500;margin-bottom:6px;">{question}</div>'
           f'<div style="font-size:12.5px;color:var(--muted);line-height:1.6;">{answer}</div></div>')


def render() -> None:
    _dash_page = nav_registry.pages.get("dashboard")
    if _dash_page is not None and st.button("← Back", key="help_back", type="tertiary"):
        st.switch_page(_dash_page)

    st.markdown('<div style="font-size:22px;font-weight:500;letter-spacing:-0.02em;">Help &amp; docs</div>',
               unsafe_allow_html=True)
    st.caption("How Uvalu scores value, builds fair value and applies veto discipline.")

    # ── Signal legend ─────────────────────────────────────────────────────────
    with st.container(key="help_card_signals", border=True):
        st.markdown(_HEADER_HTML.format(label="Signal legend")
                   + '<div style="padding-bottom:6px;">'
                   + "".join(_signal_row_html(kind, label, desc) for kind, label, desc in _SIGNAL_LEGEND)
                   + "</div>",
                   unsafe_allow_html=True)

    # ── The six fair-value models ─────────────────────────────────────────────
    with st.container(key="help_card_models", border=True):
        st.markdown(_HEADER_HTML.format(label="The six fair-value models")
                   + '<div style="display:grid;grid-template-columns:1fr 1fr;padding-bottom:6px;">'
                   + "".join(_model_cell_html(name, desc) for name, desc in _MODELS)
                   + "</div>",
                   unsafe_allow_html=True)

    # ── Hard-veto rules | Frequently asked ────────────────────────────────────
    # align-items:start in the design spec (not stretch) — the veto card has
    # far fewer rows than the FAQ card and should size to its own content, not
    # balloon to match its taller neighbour.
    _veto_col, _faq_col = st.columns([1, 1.3], gap="medium")
    with _veto_col, st.container(key="help_card_vetoes", border=True):
        st.markdown(_HEADER_HTML.format(label="Hard-veto rules")
                   + '<div style="padding:8px 20px 14px;">'
                   + "".join(_veto_row_html(rule) for rule in _VETO_RULES)
                   + "</div>",
                   unsafe_allow_html=True)
    with _faq_col, st.container(key="help_card_faqs", border=True):
        st.markdown(_HEADER_HTML.format(label="Frequently asked")
                   + '<div style="padding-bottom:6px;">'
                   + "".join(_faq_row_html(q, a) for q, a in _FAQ)
                   + "</div>",
                   unsafe_allow_html=True)
