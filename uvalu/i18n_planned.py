"""Texts the i18n spec plans but the app doesn't show yet (docs/i18n-spec.md
L-11, L-13, F-12): legal links and disclaimers, the first-run tour and the
"last updated" stamp. Marked here with N_() so tools/i18n_update.py keeps
them in the catalogs for review instead of marking them obsolete. Move each
one to its real call site when the feature is built, then delete it here.
"""
from uvalu.i18n import N_

PLANNED = (
    # Disclaimers and legal links (L-11, G-03 — reviewed line by line)
    N_("Uvalu provides information, not investment advice. Valuations are estimates and can be wrong. "
       "Always do your own research."),
    N_("Past performance is no guarantee of future results."),
    N_("Privacy policy"),
    N_("Terms of use"),
    N_("By creating an account, you agree to the {terms} and the {privacy}."),
    # First-run tour (L-13)
    N_("Welcome to Uvalu"),
    N_("Find undervalued stocks in the Screener."),
    N_("Track your holdings and their fair value in Portfolio."),
    N_("Check concentration and downside in Risk."),
    N_("Next"),
    N_("Skip tour"),
    N_("Got it"),
    # Timestamps (F-12)
    N_("Last updated: {datetime}"),
)
