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
Number, price/earnings value, EPV, the single- and multi-stage dividend
models plus the book-value and FCF fallbacks, see screener.py's
`_fair_value_models()`; the analyst target is off while unlicensed, DATA-6),
named exactly as in the legal Methodology document (G06). Same reasoning
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
from uvalu.shell import producer_line, producer_name
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


def _live_definitions() -> dict[str, str]:
    """G32: the badge definitions with the thresholds in force, as HTML.
    The quality-screen and No signal definitions carry no number."""
    from screener import (SCORE_AVOID, SIGNAL_LOW_SCORE, SIGNAL_NEUTRAL, SIGNAL_UNDERVALUED,
                          effective_min_mos)
    from settings import get_veto_thresholds
    from uvalu.i18n import fmt_num, fmt_pct
    _thr = get_veto_thresholds()
    hi, lo = _thr[3], SCORE_AVOID
    return {
        SIGNAL_UNDERVALUED: h_("Composite model score of {score} or more, the price at least {mos} below the "
                               "model fair value, and the fair value backed by two or more independent models.",
                               score=fmt_num(hi, 0), mos=fmt_pct(effective_min_mos(_thr[2]), 0, fraction=True)),
        SIGNAL_NEUTRAL: h_("Composite model score from {low} to {high}, or {score} or more without a confirmed "
                           "margin of safety.", low=fmt_num(lo, 0), high=fmt_num(hi - 1, 0), score=fmt_num(hi, 0)),
        SIGNAL_LOW_SCORE: h_("Composite model score below {low}.", low=fmt_num(lo, 0)),
    }


def _coverage_line() -> str:
    """"Coverage today": the share of covered stocks per signal (REC-10),
    the figure methodology.md says is shown live on this page. "—" before
    the universe is scored."""
    try:
        import pandas as pd
        from portfolio import load_manual_tickers
        from screener import (SIGNAL_FAILS, SIGNAL_LOW_SCORE, SIGNAL_NEUTRAL, SIGNAL_UNDERVALUED,
                              signal_distribution)
        from settings import ALL_EXCHANGES, get_score_weights, get_veto_thresholds, load_shared_settings
        from uvalu.data import _cache_version, _load_all_screener_data
        from uvalu.i18n import fmt_pct
        enabled = tuple(load_shared_settings().get("enabled_exchanges", ALL_EXCHANGES))
        manual = load_manual_tickers()
        dfs = _load_all_screener_data(_cache_version(), enabled, tuple(manual.keys()), tuple(manual.values()),
                                      get_veto_thresholds(), get_score_weights())
        frames = [d for d in dfs[:-1] if d is not None and not d.empty]
        dist = signal_distribution(pd.concat(frames, ignore_index=True)) if frames else {}
    except Exception:
        dist = {}
    if not dist:
        return "—"
    pct = lambda code: fmt_pct(dist.get(code, 0.0) * 100, 0)
    return h_("{a} Undervalued · {b} Mid score · {c} Low score · {d} Fails quality screen",
              a=pct(SIGNAL_UNDERVALUED), b=pct(SIGNAL_NEUTRAL), c=pct(SIGNAL_LOW_SCORE), d=pct(SIGNAL_FAILS))


_MODELS = [
    (N_("Graham Number"), N_("√(22.5 × EPS × book value per share) — Benjamin Graham's classic value "
                             "formula. Needs positive trailing earnings and book value per share.")),
    # Model names exactly as in the legal Methodology document, § 3 (G06).
    (N_("Price/earnings value"), N_("Trailing EPS × a sector-typical fair P/E multiple.")),
    (N_("Earnings power value (EPV)"), N_("Normalised earnings capitalised at the cost of capital, "
                                          "deliberately ignoring speculative growth.")),
    (N_("Dividend model, single stage"), N_("Gordon growth model: next year's expected dividend discounted at "
                                            "(cost of equity − perpetual growth rate). Only applies to dividend payers.")),
    (N_("Dividend model, multi-stage"), N_("A higher-growth phase followed by a stable terminal-growth phase, each "
                                           "discounted back separately. Also dividend-payer only.")),
    (N_("Book value (fallback)"), N_("Book value per share × the sector's median price/book ratio. Used only when "
                                     "Graham, P/E and EPV all fail, typically for a loss-maker.")),
    (N_("Free cash flow value (fallback)"), N_("Free cash flow × a fixed multiple, minus net debt, per share. "
                                               "Used only when Graham, P/E and EPV all fail.")),
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
        # Translators: Methodology › left-hand section list › the signal badges (Undervalued, Mid score, …).
        (_("Badges"), "#help-badges"),
        # Translators: Methodology › left-hand section list › the fair-value models (Graham Number, EPV, …).
        (_("Models"), "#help-models"),
        (_("Quality screens"), "#help-screens"),
        # Translators: Methodology › left-hand section list › frequently asked questions.
        (_("FAQ"), "#help-faq"),
        (_("Data sources"), "#help-data"),
        # Translators: Methodology › left-hand section list › short for "Conflicts of interest".
        (_("Conflicts"), "#help-conflicts"),
        (_("About Uvalu"), "#help-about"),
    ]

_VETO_X_SVG = ('<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--down-txt)" '
              'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
              'style="flex:none;margin-top:2px;"><path d="M18 6L6 18M6 6l12 12"/></svg>')


def _signal_row_html(kind: str, label: str, desc: str, desc_html: "str | None" = None) -> str:
    return ('<div style="display:flex;align-items:flex-start;gap:14px;padding:14px 20px;'
           'border-bottom:0.5px solid var(--line-2);">'
           f'<div style="width:150px;flex:none;padding-top:1px;">'
           f'{signal_badge_html(kind, _t(label), tooltip=signal_tooltip())}</div>'
           f'<div style="font-size:13px;color:var(--muted);line-height:1.55;">{desc_html or _t(desc)}</div></div>')


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
    _link = '<a href="/legal?doc={doc}" target="_self">{label}</a>'
    _content = support_page(_("Methodology"), back_key="help", rail=_rail(),
                            subtitle=h_("How each model works, what the badges mean, how often they change and where the data comes from."),
                            links_html=_link.format(doc="methodology", label=h_("Full methodology →"))
                            + _link.format(doc="data", label=h_("Data sources →"))
                            + _link.format(doc="conflicts", label=h_("Conflicts of interest →")))
    with _content:
        _render_cards()


def _render_cards() -> None:
    # (The links to the full legal pages, REC-5/REC-3/REC-8, sit in the header.)
    # ── Badges: meaning (REC-5 / REC-6) ───────────────────────────────────────
    _notes = "".join(
        f'<div style="font-size:12.5px;color:var(--muted);line-height:1.6;padding:4px 20px;">{_t(t)}</div>'
        for t in (SIGNAL_HORIZON, SIGNAL_RISK_WARNING))
    with st.container(key="help_card_signals", border=True):
        _defs = _live_definitions()
        _codes = list(SIGNAL_LABELS)
        st.markdown(_HEADER_HTML.format(anchor="help-badges", label=h_("Badges · meaning and thresholds"))
                   + '<div style="padding-bottom:6px;">'
                   + "".join(_signal_row_html(kind, label, desc, _defs.get(code))
                             for code, (kind, label, desc) in zip(_codes, _signal_legend()))
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
        (N_("Sensitivity."), SIGNAL_SENSITIVITY),
    ]
    with st.container(key="help_card_reading", border=True):
        st.markdown(
            _HEADER_HTML.format(anchor="help-reading", label=h_("Reading the badges"))
            + '<div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border-bottom:0.5px solid var(--line-2);">'
            + "".join(f'<div style="padding:14px 20px;"><div style="font-size:10px;letter-spacing:0.06em;'
                      f'text-transform:uppercase;color:var(--muted);">{k}</div>'
                      f'<div style="font-size:13px;margin-top:6px;line-height:1.5;">{v}</div></div>'
                      for k, v in [(_t(k), _t(v)) for k, v in _reading]
                      + [(h_("Coverage today"), _coverage_line())])
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
    # ── Frequently asked ──────────────────────────────────────────────────────
    with st.container(key="help_card_faqs", border=True):
        st.markdown(_HEADER_HTML.format(anchor="help-faq", label=h_("Frequently asked"))
                   + '<div style="padding-bottom:6px;">'
                   + "".join(_faq_row_html(q, a) for q, a in _FAQ)
                   + "</div>",
                   unsafe_allow_html=True)

    # ── Data sources, conflicts of interest (REC-3, REC-8) ─────────────────
    with st.container(key="help_card_sources", border=True):
        st.markdown(
            _HEADER_HTML.format(anchor="help-data", label=h_("Data sources"))
            + "".join(f'<div style="display:grid;grid-template-columns:120px minmax(0,1fr);gap:12px;'
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
            + f'<div>{h_("The founder’s position in a covered stock, of any size, is shown on that stock’s page and updated within 2 business days of each trade.")}</div>'
            + (f'<div>{h_("Uvalu receives no payment from issuers, brokers or data providers, has no affiliate or broker links and no income during the free beta.")}</div>'
               if disclosures.BETA else
               f'<div>{h_("Uvalu receives no payment from issuers, brokers or data providers and has no affiliate or broker links.")}</div>')
            + f'<div>{h_("The founder does not trade affected shares from the moment a model change is decided until 2 trading days after it is live.")}</div>'
            + "</div>", unsafe_allow_html=True)

    # ── About Uvalu: full disclaimer and producer (DIS-1, REC-1, PER-6) ─────
    with st.container(key="help_card_about", border=True):
        st.markdown(
            _HEADER_HTML.format(anchor="help-about", label=h_("About Uvalu"))
            + f'<div style="padding:14px 20px;font-size:12.5px;color:var(--muted);line-height:1.65;">'
              f'{html.escape(tr(disclosures.FULL_DISCLAIMER).format(producer=producer_name()))}</div>'
            + f'<div style="padding:0 20px 8px;font-size:11.5px;color:var(--muted);line-height:1.6;">'
              f'{html.escape(producer_line())}</div>'
            + f'<div style="padding:0 20px 14px;font-size:12px;color:var(--muted);line-height:1.6;">'
              f'{html.escape(tr(disclosures.SUPPORT_REFUSAL))}</div>',
            unsafe_allow_html=True)
