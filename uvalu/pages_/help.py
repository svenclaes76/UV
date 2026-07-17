"""Help page — signal legend, the six fair-value models, hard-veto rules and
an FAQ, matching Uvalu.dc.html's single-page Help spec. Replaces the earlier
per-screen-guide-tabs + column-reference-glossary structure by explicit user
choice (that content was more comprehensive but didn't exist in the mockup
at all; the mockup's quick-reference sections didn't exist anywhere before
this page).

The hard-veto rules list below is grounded in the real veto logic in
screener.py's compute_scores() (`_hard_veto`), not the mockup's own demo
bullets — the mockup includes a "Going-concern or audit red flags" item this
app has no corresponding check for, so it's omitted rather than documented
as if it were real. Same reasoning for the mockup's "Contact support" banner:
this app has no support channel to send anyone to, so it's left out rather
than faked.
"""
import streamlit as st

from uvalu.components import signal_badge_html

_SIGNAL_LEGEND = [
    ("buy", "BUY", "Composite score clears the BUY threshold and the margin of safety clears its "
                  "target — both conditions together, set in Settings → Screening & veto rules."),
    ("monitor", "MONITOR", "Composite score is decent but the margin of safety hasn't cleared the "
                          "target yet, or the score itself sits below the BUY threshold — worth watching."),
    ("avoid", "AVOID", "Composite score falls well below the BUY threshold."),
    ("veto", "VETO", "A hard-veto rule tripped (see below) — excluded from BUY scoring no matter "
                     "what the composite score would otherwise be."),
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
    "Debt / equity exceeds the Max debt/equity threshold set in Settings → Screening & veto "
    "rules (default 500%).",
    "Free cash flow (trailing twelve months) is negative.",
    "The dividend is flagged \"At risk\" (payout ratio, cash payout ratio, or coverage breach) "
    "*and* dividend coverage is below 1.0× — both conditions together, not either alone.",
]

_FAQ = [
    ("How is the composite fair value calculated?",
     "It's the average of whichever of the six models above produce a usable number for that "
     "stock — not every model applies to every company (the two DDM variants need a dividend "
     "payer, for instance)."),
    ("Why does a stock show MONITOR instead of BUY even with a high score?",
     "A BUY needs the composite score above the BUY threshold *and* the margin of safety above "
     "the target in Settings → Screening & veto rules. A high score alone doesn't override a "
     "thin margin of safety."),
    ("Why is a stock excluded even though its numbers look fine?",
     "It's hit one of the hard-veto rules below — the composite score is forced to 0 and it can "
     "never show as BUY, regardless of what the six models say."),
    ("Why is data missing for some of my holdings?",
     "Fundamentals are fetched in the background from Yahoo Finance and cached. Make sure the "
     "ticker's exchange is enabled in Admin → Data feeds, or give it time for the next fetch "
     "cycle — manually-added tickers (Watchlist, or positions outside your enabled exchanges) "
     "are fetched the same way, just queued alongside everything else."),
    ("Does uvalu send emails or push notifications?",
     "No — the toggles in Settings → Alerts & data are stored preferences only. There's no "
     "email or push delivery in this app yet."),
]


def render() -> None:
    st.markdown('<div style="font-size:22px;font-weight:500;letter-spacing:-0.02em;">Help &amp; docs</div>',
               unsafe_allow_html=True)
    st.caption("Signal legend, the six fair-value models, hard-veto rules and frequently asked questions.")

    # ── Signal legend ─────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("##### Signal legend")
        for kind, label, meaning in _SIGNAL_LEGEND:
            with st.container(horizontal=True, vertical_alignment="center", gap="small"):
                st.markdown(signal_badge_html(kind, label), unsafe_allow_html=True)
                st.caption(meaning)

    # ── The six fair-value models ─────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("##### The six fair-value models")
        _mc1, _mc2 = st.columns(2)
        for _i, (name, desc) in enumerate(_MODELS):
            with (_mc1 if _i % 2 == 0 else _mc2):
                st.markdown(f"**{name}**")
                st.caption(desc)

    # ── Hard-veto rules ───────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("##### Hard-veto rules")
        st.caption("Any one of these excludes a stock from BUY scoring entirely — its composite "
                  "score is forced to 0 regardless of what the six fair-value models say.")
        for rule in _VETO_RULES:
            st.markdown(f"- {rule}")

    # ── Frequently asked ──────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("##### Frequently asked")
        for question, answer in _FAQ:
            with st.expander(question):
                st.caption(answer)
