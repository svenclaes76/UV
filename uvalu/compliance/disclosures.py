"""
Legal display texts — one source for every screen (M1 Track D of
docs/legal/compliance-implementation-plan.md).

English msgids, translated at render time through uvalu.i18n.tr(). They are
legal texts: a change here needs the same review as a change to the public
legal pages in docs/legal/policies/, and every offered language needs a
reviewed translation (INT-1, INT-4).

Producer identity (REC-1, BIZ-3): the free beta runs under the founder's own
name as a sole trader, without an enterprise number yet (decision B6). Update
PRODUCER_* when the entity is registered.
"""

from uvalu.i18n import N_

# ── Free beta (decision B7) ─────────────────────────────────────────────────
BETA = True
# L1: who may join (Terms of use §5: residents of the European Economic Area,
# 18 or older). ISO 3166-1 alpha-2 codes; names come from CLDR in the user's
# language (uvalu.i18n.country_name).
EEA_COUNTRIES = (
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE",
    "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
    "IS", "LI", "NO",
)

BETA_BANNER = N_("Free beta: a test version. Features and data can change, "
                 "and the beta can end at any time.")

# ── Producer (REC-1, BIZ-3, decision B6) ────────────────────────────────────
PRODUCER_NAME = "Sven Claes"
PRODUCER_TRADING_AS = "Uvalu"
PRODUCER_ADDRESS = "Pol Heynsstraat 7, 2200 Herentals, Belgium"
PRODUCER_CONTACT = "support@uvalu.app"
PRODUCER_PRIVACY_CONTACT = "privacy@uvalu.app"
PRODUCER_ENTERPRISE_NUMBER = None   # None until the KBO/BCE registration
ENTERPRISE_NUMBER_PENDING = N_("enterprise number: registration pending")
NOT_SUPERVISED = N_("Not authorised or supervised by the FSMA as an investment firm.")
# INT-5/6: stated in the Terms of use (eligibility). No longer in the footer;
# kept for the invite-acceptance screen (M3).
NOT_DIRECTED = N_("Not directed at residents of the United Kingdom, the United States or Switzerland.")

# ── Disclaimers (DIS-1) ──────────────────────────────────────────────────────
SHORT_DISCLAIMER = N_(
    "Uvalu is an analysis tool. Scores, fair values and signals are model outputs based on "
    "public data and are the same for every user. They are not personal investment advice "
    "and do not take your situation into account. Investing involves risk, including loss "
    "of capital. Decisions are your own.")
FULL_DISCLAIMER = N_(
    "Uvalu ({producer}) is not an investment firm, bank or broker and is not authorised or "
    "supervised by the FSMA to provide investment services. Uvalu does not provide investment "
    "advice, portfolio management or order execution. All valuations, scores, signals and "
    "risk figures are generated automatically from third-party data and from assumptions that "
    "may be wrong, incomplete or out of date. They are general information made available to "
    "all users on the same basis. Before investing, consider your own circumstances and, where "
    "appropriate, consult an authorised adviser. Positions held by the founder in covered "
    "instruments are disclosed on the stock page and in the conflicts of interest policy.")

# ── Support (PER-6) ──────────────────────────────────────────────────────────
SUPPORT_REFUSAL = N_("Support explains how Uvalu works; we can't comment on whether you "
                     "should buy, hold or sell any stock.")

# ── Records, not orders (PER-7) ──────────────────────────────────────────────
RECORDS_NOTE = N_("Your records · nothing is executed")

# ── Data sources shown on the stock page (REC-3, decision B2) ────────────────
DATA_SOURCE_ROWS = (
    (N_("Prices"), N_("Yahoo Finance · delayed quotes, with the time they were fetched")),
    (N_("Fundamentals"), N_("Yahoo Finance · refreshed about every 24 hours")),
    (N_("Dividends"), N_("Yahoo Finance payment history · your own entries are your records")),
    (N_("FX"), N_("ECB reference rates via frankfurter.dev")),
)

# ── Tax estimates (TAX-1, TAX-2, TAX-5, TAX-6) ───────────────────────────────
TAX_RULES_REVIEWED = "2026-10-04"   # TAX-5: date the rates and rules below were last checked
TAX_TITLE = N_("Tax figures are estimates")
TAX_RULES = N_("Rules applied: Belgium. Foreign withholding at the rate you set per exchange in "
               "Settings, then the Belgian withholding tax (roerende voorheffing) of {be_rate} on "
               "the remainder; not applied to stock (scrip) dividends. Rates last reviewed {date}.")
TAX_NOT_HANDLED = N_("Not handled: the dividend exemption and its carry-forward, substantial "
                     "holdings, funds with a bond component, non-Belgian residents, split "
                     "ownership, professional or speculative trading.")
TAX_RESPONSIBILITY = N_("You remain responsible for your tax return. Check these figures against "
                        "your bank statements or with a tax professional.")

# ── Legal pages (in-app, uvalu/pages_/legal.py) ──────────────────────────────
# key → (title msgid, file name in docs/legal/policies/). A file in
# docs/legal/policies/beta/ overrides the launch version while BETA is on (B4).
LEGAL_DOCS = (
    ("terms", N_("Terms of use"), "terms-of-use.md"),
    ("privacy", N_("Privacy notice"), "privacy-notice.md"),
    ("methodology", N_("Methodology"), "methodology.md"),
    ("data", N_("Data sources"), "data-sources.md"),
    ("conflicts", N_("Conflicts of interest"), "conflicts-of-interest.md"),
    ("complaints", N_("Complaints & Consumer Mediation Service"), "complaints.md"),
    ("accessibility", N_("Accessibility statement"), "accessibility.md"),
)
# Shorter labels for the footer's one-line link row; the legal page itself
# keeps the full titles above.
FOOTER_LINK_LABELS = {"complaints": N_("Complaints"), "accessibility": N_("Accessibility")}
REFERENCE_LANGUAGE_NOTE = N_("Reference language: English. You may rely on the version shown "
                             "to you in your own language.")
NOT_YET_TRANSLATED = N_("This page is not yet available in your language; the English "
                        "reference version is shown.")
