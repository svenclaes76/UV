"""
Falsifying-fixture data for rejected checks — docs/valuation_audit_plan.md §2.7.

Every check the audit considered and rejected stays here as real, concrete
data (not just prose) so a reintroduced version of the check fails an actual
assertion the moment it's wired in. See §2.2's catalog-integrity family and
tests/test_valuation_audit.py, which asserts every active check in
CHECK_REGISTRY leaves these fixtures alone.

Do not add a check to tools/valuation_audit.CHECK_REGISTRY without first
checking it against every fixture here.
"""

# ── Rejected: standalone implied-P/E floor ───────────────────────────────────
# ALNRG.PA (SA Energisme) — real cached values at time of investigation
# (2026-09-11). Implied P/E ~= 0.0005, *lower* (more "extreme") than the
# actual corrupted case it was meant to catch (BC.MI, implied P/E ~= 0.0007).
# Legitimate: its net-income cross-check passes (implied NI ~= EUR20.5M vs.
# reported EUR16.0M, ~1.3x -- well inside the real net-income
# cross-validation's own 20x/0.05x band). No threshold that catches BC.MI can
# avoid also catching this row.
REJECTED_PE_FLOOR_COUNTEREXAMPLE = {
    "Ticker": "ALNRG.PA",
    "Name": "SA Energisme",
    "Price": 0.0038,
    "trailingEps": 7.53,
    "sharesOutstanding": 2_727_222.0,
    "netIncomeHistory": [15_998_776.0],
}

# ── Rejected: price vs. sibling listings ─────────────────────────────────────
# Berkshire Hathaway's Class A / Class B share structure: each Class A share
# converts to exactly 1,500 Class B shares -- a real, public, permanent ratio,
# not a data defect. No same-company price-ratio threshold intended to catch
# a phantom/treasury-style listing can both (a) catch the confirmed bugs this
# session (NAITR.AS/NAI.AS ~= 216x, QEV.AS/QEVT.AS ~= 670x) and (b) leave a
# real 1,500x ratio alone.
BERKSHIRE_AB_SPLIT_RATIO = 1500.0
CONFIRMED_BUG_SIBLING_RATIOS = {
    "NAITR.AS/NAI.AS": 216.0,
    "QEV.AS/QEVT.AS": 670.0,
}

# ── Considered and dropped: sharesOutstanding upper bound ────────────────────
# BCY.DE (Glencore's Frankfurt line) and HBC1.DE (HSBC's Frankfurt line) --
# both real, currently-legitimate Strong Buy rows with share counts far above
# any naive "implausibly high" cutoff. No bug found this session involved an
# implausibly *high* share count, so no upper bound ships at all.
SHARES_OUTSTANDING_UPPER_BOUND_COUNTEREXAMPLES = {
    "BCY.DE": 13_400_000_000.0,
    "HBC1.DE": 17_100_000_000.0,
}

# ── Legitimate low-implied-P/E rows (disprove a naive P/E floor a second way) ─
# All real, currently-legitimate Strong Buy rows this session, with implied
# P/E well under the levels a naive floor would need to clear BC.MI.
LEGITIMATE_LOW_PE_ROWS = {
    "TPG0.DE": 0.47,
    "ALOPM.PA": 0.73,
    "ALWEC.PA": 1.99,
    "NWL.MI": 2.04,
}

# ── Ambiguous net-income mismatch (not a hit, real earnings volatility) ──────
# ALGTR.PA's implied-vs-reported net income differs by ~2.2x either direction
# -- plausibly a real year-over-year earnings swing, not corruption. Must
# stay below the net-income cross-validation's 20x/0.05x band.
AMBIGUOUS_NET_INCOME_ROW = {
    "Ticker": "ALGTR.PA",
    "trailingEps": 3.73,
    "sharesOutstanding": 2_029_347.0,
    "netIncomeHistory": [16_672_000.0],   # implied ~= EUR7.57M, ratio ~= 0.45x
}

# ── SNBN.SW: real, legitimate outlier on sharesOutstanding and bookValue -----
# Genuine, tiny share count (Swiss National Bank) -- must not trip a fuzzy
# "implausibly low" sharesOutstanding band, only an exact-zero check.
SNB_LEGITIMATE_LOW_SHARE_COUNT = {
    "Ticker": "SNBN.SW",
    "sharesOutstanding": 100_000.0,
    "bookValue": 1_659_593.0,
    "trailingEps": 666_185.9,
    "Price": 3140.0,
}
