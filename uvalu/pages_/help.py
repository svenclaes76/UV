"""Help page — signal legend, the six fair-value models, hard-veto rules and
an FAQ, matching Uvalu.dc.html's Help screen spec (`help.signals`/
`help.models`/`help.vetoes`/`help.faqs` in the design file's `<script>`
section). Every section here is static text with no interactive widgets, so
each card is built as one raw-HTML block (header + all rows) inside a single
`st.container(key="help_card_...", border=True)` instead of one
st.container per row — sidesteps the sibling-gap/height-underestimation CSS
dance documented for Settings/Analysis entirely, since nothing on this page
needs an individual widget key.

The fair-value models list below stays the app's real model set (Graham
Number/PE Fair Value/EPV/DDM 1-stage/DDM 2-stage plus the book-value and FCF
fallbacks, see screener.py's `_fair_value_models()`; the analyst target is
off while unlicensed, DATA-6) rather than the mockup's generic
"Dividend discount"/"DCF" pair — this app has no DCF model at all, so
documenting one would describe a feature that doesn't exist. Same reasoning
for the hard-veto rules: grounded in the real `_hard_veto` formula in
screener.py's compute_scores(), not the mockup's own demo bullets — the
mockup includes a "Going-concern or audit red flags" item this app has no
corresponding check for, so it's omitted rather than documented as if it
were real. The badge legend and the quality-screen list are generated from
screener.py (SIGNAL_LABELS, SIGNAL_DEFINITIONS, VETO_RULE_LABELS), so this
page — the methodology page every badge links to (REC-5) — can't drift from
the rules the code applies. Full redesign as "Methodology" (first named "Methodology & help"): M1 Track D
in docs/legal/compliance-implementation-plan.md.

The mockup's closing "Still stuck? Contact support" banner is left out on
explicit confirmation from Sven when re-applying this design (2026-07-23) —
this app has no support channel to send anyone to, so a decorative button
that does nothing was rejected in favour of leaving it out entirely, same
call as the previous pass on this page.
"""
import html

import streamlit as st

from screener import (SIGNAL_DEFINITIONS, SIGNAL_LABELS, SIGNAL_HORIZON, SIGNAL_RISK_WARNING,
                      SIGNAL_SENSITIVITY, VETO_RULE_LABELS)
from uvalu.compliance import disclosures
from uvalu.components import _SIGNAL_KIND, signal_badge_html, signal_tooltip, support_page
from uvalu.shell import producer_line
from uvalu.i18n import N_, _, h_, tr


def _t(text: str) -> str:
    """Translate a Help text for HTML: escaped, keeping the <em> emphasis the
    msgids carry (the compile check requires translations to keep it)."""
    return (html.escape(tr(text), quote=False)
            .replace("&lt;em&gt;", "<em>").replace("&lt;/em&gt;", "</em>"))

# English msgids (plain text, "&" not "&amp;"); rendered through _t().
def _signal_legend() -> list[tuple[str, str, str]]:
    """(badge kind, label msgid, definition msgid) per model signal (REC-6)."""
    return [(_SIGNAL_KIND[code], SIGNAL_LABELS[code], SIGNAL_DEFINITIONS[code]) for code in SIGNAL_LABELS]


_MODELS = [
    (N_("Graham Number"), N_("√(22.5 × EPS × book value per share) — Benjamin Graham's classic value "
                             "formula. Needs positive trailing earnings and book value per share.")),
    (N_("PE Fair Value"), N_("Trailing EPS × a sector-typical fair P/E multiple.")),
    (N_("EPV (Earnings Power Value)"), N_("Normalised earnings capitalised at the cost of capital, "
                                          "deliberately ignoring speculative growth.")),
    (N_("DDM — 1-stage"), N_("Gordon growth model: next year's expected dividend discounted at "
                             "(cost of equity − perpetual growth rate). Only applies to dividend payers.")),
    (N_("DDM — 2-stage"), N_("A higher-growth phase followed by a stable terminal-growth phase, each "
                             "discounted back separately. Also dividend-payer only.")),
    (N_("Book value and FCF fallbacks"), N_("Used only when Graham, P/E and EPV all fail (typically a "
                                            "loss-maker): book value × a sector P/B multiple, and free cash "
                                            "flow × a fixed multiple.")),
]

# The quality-screen rules come from screener.VETO_RULE_LABELS (see render()).

_FAQ = [
    (N_("How is the composite fair value calculated?"),
     N_("Each stock is valued by every model that applies to it. Their values are combined into one "
        "weighted fair value, capped when a single model runs far above the others. Margin of safety "
        "is the discount of the price to that figure. Both are model estimates.")),
    (N_("What does the weighted composite score mean?"),
     N_("A 0–100 value-weighted mean of the model scores across your holdings. It describes the "
        "portfolio; it is not a recommendation. A holding that fails a quality screen counts with its "
        "score of 0; a holding without a score (No signal) is left out.")),
    (N_("How often do prices update?"),
     N_("During the free beta prices are delayed quotes from Yahoo Finance; each signal shows the time "
        "of the price it used. Fundamentals are refreshed about every 24 hours. Real-time prices are "
        "not offered.")),
    (N_("Why does a stock show “Fails quality screen”?"),
     N_("It breaks one of the quality rules listed on this page; the explanation next to the badge "
        "names which. Its composite score is set to 0. It still appears in your portfolio and "
        "valuations.")),
    (N_("Which exchanges are covered?"),
     N_("Euronext Amsterdam/Brussels/Paris, XETRA, SIX Swiss, and Borsa Italiana.")),
]

# Card header: sentence case, 15px/500 (styles.py .uv-card-head, brand §5),
# with the anchor the rail links to. One outer <div> so Markdown keeps it a
# raw HTML block (a leading <span> would make it a paragraph).
_HEADER_HTML = '<div><span id="{anchor}" class="uv-anchor"></span><div class="uv-card-head">{label}</div></div>'


def _rail() -> list[tuple[str, str]]:
    """The page's sections for the support_page rail."""
    return [
        # Translators: Methodology › left-hand section list › the signal badges (Undervalued, Neutral, …).
        (_("Badges"), "#help-badges"),
        # Translators: Methodology › left-hand section list › the fair-value models (Graham Number, EPV, …).
        (_("Models"), "#help-models"),
        (_("Quality screens"), "#help-screens"),
        (_("Data sources"), "#help-data"),
        # Translators: Methodology › left-hand section list › short for "Conflicts of interest".
        (_("Conflicts"), "#help-conflicts"),
        # Translators: Methodology › left-hand section list › frequently asked questions.
        (_("FAQ"), "#help-faq"),
    ]

_VETO_X_SVG = ('<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--down-txt)" '
              'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
              'style="flex:none;margin-top:2px;"><path d="M18 6L6 18M6 6l12 12"/></svg>')


def _signal_row_html(kind: str, label: str, desc: str) -> str:
    return ('<div style="display:flex;align-items:flex-start;gap:14px;padding:14px 20px;'
           'border-bottom:0.5px solid var(--line-2);">'
           f'<div style="width:150px;flex:none;padding-top:1px;">'
           f'{signal_badge_html(kind, _t(label), tooltip=signal_tooltip())}</div>'
           f'<div style="font-size:13px;color:var(--muted);line-height:1.55;">{_t(desc)}</div></div>')


def _model_cell_html(name: str, desc: str) -> str:
    return ('<div style="padding:14px 20px;border-bottom:0.5px solid var(--line-2);">'
           f'<div style="font-size:13px;font-weight:500;margin-bottom:5px;">{_t(name)}</div>'
           f'<div style="font-size:12px;color:var(--muted);line-height:1.55;">{_t(desc)}</div></div>')


def _veto_row_html(rule: str) -> str:
    return ('<div style="display:flex;align-items:flex-start;gap:10px;padding:9px 0;'
           f'border-bottom:0.5px solid var(--line-2);">{_VETO_X_SVG}'
           f'<span style="font-size:12.5px;color:var(--muted);line-height:1.5;">{_t(rule)[:1].upper() + _t(rule)[1:]}</span></div>')


def _faq_row_html(question: str, answer: str) -> str:
    return ('<div style="padding:14px 20px;border-bottom:0.5px solid var(--line-2);">'
           f'<div style="font-size:13px;font-weight:500;margin-bottom:6px;">{_t(question)}</div>'
           f'<div style="font-size:12.5px;color:var(--muted);line-height:1.6;">{_t(answer)}</div></div>')


def render() -> None:
    _content = support_page(_("Methodology"), back_key="help", rail=_rail(),
                            subtitle=h_("How each model works, what the badges mean, how often they change and where the data comes from."))
    with _content:
        _render_cards()


def _render_cards() -> None:
    # Links to the full legal pages (REC-5, REC-3, REC-8).
    _link = ('<a href="/legal?doc={doc}" target="_self" style="color:var(--link);text-decoration:none;'
             'margin-right:16px;font-size:12px;">{label}</a>')
    st.markdown(_link.format(doc="methodology", label=h_("Full methodology →"))
                + _link.format(doc="data", label=h_("Data sources →"))
                + _link.format(doc="conflicts", label=h_("Conflicts of interest →")),
                unsafe_allow_html=True)

    # ── Badges: meaning (REC-5 / REC-6) ───────────────────────────────────────
    _notes = "".join(
        f'<div style="font-size:12.5px;color:var(--muted);line-height:1.6;padding:4px 20px;">{_t(t)}</div>'
        for t in (SIGNAL_HORIZON, SIGNAL_RISK_WARNING, SIGNAL_SENSITIVITY))
    with st.container(key="help_card_signals", border=True):
        st.markdown(_HEADER_HTML.format(anchor="help-badges", label=h_("Badges · meaning"))
                   + '<div style="padding-bottom:6px;">'
                   + "".join(_signal_row_html(kind, label, desc) for kind, label, desc in _signal_legend())
                   + "</div>"
                   + f'<div style="padding:10px 0 14px;">{_notes}</div>',
                   unsafe_allow_html=True)

    # ── Reading the badges (REC-6, REC-7, PER-1/2) ───────────────────────────
    _reading = [
        (N_("Time horizon"), N_("3 to 5 years, the period the valuation models assume")),
        (N_("Updated"), N_("Fundamentals about every 24 hours; signals are recomputed when they change")),
        (N_("History"), N_("Every badge change kept 24 months, the last 12 shown on each stock page")),
    ]
    _reading_notes = [
        (N_("Same for every user."), N_("Badges, scores and fair values use only instrument data and the "
                                        "shared model settings. They never use your holdings, income, goals "
                                        "or risk tolerance.")),
        (N_("Risk."), N_("Model outputs can be wrong. Share prices can stay below or above fair value for "
                         "years, and you can lose capital.")),
    ]
    with st.container(key="help_card_reading", border=True):
        st.markdown(
            _HEADER_HTML.format(anchor="help-reading", label=h_("Reading the badges"))
            + '<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));border-bottom:0.5px solid var(--line-2);">'
            + "".join(f'<div style="padding:14px 20px;"><div style="font-size:12px;font-weight:500;'
                      f'color:var(--muted);">{_t(k)}</div>'
                      f'<div style="font-size:13px;margin-top:6px;line-height:1.5;">{_t(v)}</div></div>'
                      for k, v in _reading)
            + '</div><div style="padding:14px 20px;display:flex;flex-direction:column;gap:8px;font-size:12.5px;'
              'color:var(--muted);line-height:1.6;">'
            + "".join(f'<div><span style="color:var(--text);font-weight:500;">{_t(k)}</span> {_t(v)}</div>'
                      for k, v in _reading_notes)
            + "</div>", unsafe_allow_html=True)

    # ── The six fair-value models ─────────────────────────────────────────────
    with st.container(key="help_card_models", border=True):
        st.markdown(_HEADER_HTML.format(anchor="help-models", label=h_("The fair-value models"))
                   + '<div style="display:grid;grid-template-columns:1fr 1fr;padding-bottom:6px;">'
                   + "".join(_model_cell_html(name, desc) for name, desc in _MODELS)
                   + "</div>",
                   unsafe_allow_html=True)

    # ── Quality screens ───────────────────────────────────────────────────────
    with st.container(key="help_card_vetoes", border=True):
        st.markdown(_HEADER_HTML.format(anchor="help-screens", label=h_("Quality screens"))
                   + '<div style="padding:8px 20px 14px;">'
                   + "".join(_veto_row_html(rule) for rule in VETO_RULE_LABELS.values())
                   + "</div>",
                   unsafe_allow_html=True)
    # ── Data sources, conflicts of interest (REC-3, REC-8) ─────────────────
    with st.container(key="help_card_sources", border=True):
        st.markdown(
            _HEADER_HTML.format(anchor="help-data", label=h_("Data sources"))
            + "".join(f'<div style="display:grid;grid-template-columns:110px minmax(0,1fr);gap:12px;'
                      f'padding:10px 20px;border-bottom:0.5px solid var(--line-2);font-size:12.5px;">'
                      f'<span style="color:var(--muted);">{_t(k)}</span><span>{_t(v)}</span></div>'
                      for k, v in disclosures.DATA_SOURCE_ROWS)
            + f'<div style="padding:12px 20px;font-size:12px;color:var(--muted);line-height:1.55;">'
              f'{h_("Stale or missing inputs are flagged on the stock page. No analyst estimates or ratings are shown.")}</div>',
            unsafe_allow_html=True)
    with st.container(key="help_card_conflicts", border=True):
        st.markdown(
            _HEADER_HTML.format(anchor="help-conflicts", label=h_("Conflicts of interest"))
            + '<div style="padding:14px 20px;display:flex;flex-direction:column;gap:9px;font-size:12.5px;'
              'color:var(--muted);line-height:1.6;">'
            + f'<div>{h_("The founder discloses any position in a covered stock on that stock’s page, whatever its size.")}</div>'
            + f'<div>{h_("Uvalu receives no payment from issuers, brokers or data vendors for any output, and has no affiliate or broker links.")}</div>'
            + f'<div>{h_("The founder does not trade a stock from the moment a model change that would alter its signal is decided until 2 trading days after it is live.")}</div>'
            + "</div>", unsafe_allow_html=True)

    # ── Frequently asked ──────────────────────────────────────────────────────
    with st.container(key="help_card_faqs", border=True):
        st.markdown(_HEADER_HTML.format(anchor="help-faq", label=h_("Frequently asked"))
                   + '<div style="padding-bottom:6px;">'
                   + "".join(_faq_row_html(q, a) for q, a in _FAQ)
                   + "</div>",
                   unsafe_allow_html=True)


    # ── About Uvalu: full disclaimer and producer (DIS-1, REC-1, PER-6) ─────
    with st.container(key="help_card_about", border=True):
        st.markdown(
            _HEADER_HTML.format(anchor="help-about", label=h_("About Uvalu"))
            + f'<div style="padding:14px 20px;font-size:12.5px;color:var(--muted);line-height:1.65;">'
              f'{html.escape(tr(disclosures.FULL_DISCLAIMER).format(producer=producer_line()))}</div>'
            + f'<div style="padding:0 20px 14px;font-size:12px;color:var(--muted);line-height:1.6;">'
              f'{html.escape(tr(disclosures.SUPPORT_REFUSAL))}</div>',
            unsafe_allow_html=True)
