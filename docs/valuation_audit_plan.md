# Valuation & Risk Accuracy Audit — Problem, Solution, Process

Status: **proposed, not built**. This document describes the gap found during the
2026-09-11 investigation session (the `NAITR.AS` incident and its follow-ons) and
the tool proposed to close it. No code has been written yet.

---

## 1. Problem

### 1.1 What happened

A screenshot of the Screener page showed `NAITR.AS` (New Amsterdam Invest N.V.
*treasury shares*) as a **Strong Buy** with a +99.7% margin of safety, a 562.5%
dividend yield, and a +32,222.5% total return — against a real, actively-traded
sibling line (`NAI.AS`) quoted at roughly 200× the price. Investigating that one
screenshot led to three separate, real, currently-live valuation bugs across three
sessions of work:

- **`NAITR.AS`** — an untraded secondary listing scored off a corrupted price, with
  no liquidity check and no cap on how thin the fair-value basis behind a BUY
  signal could be. Fixed: `screener.py` v-next (zero-volume hard veto,
  `fv_basis_thin` Strong-Buy gate).
- **`SNBN.SW`** (Swiss National Bank) — a legitimate but structurally unusual
  issuer (100,000 shares against a multi-billion-franc balance sheet, dividend
  capped by statute) whose astronomically large per-share `bookValue`/`trailingEps`
  fed a >CHF 6M "fair value" against a ~CHF 3,140 price. Fixed:
  `PTB_SANITY_FLOOR`.
- **`BC.MI`** (Brunello Cucinelli) — an isolated, ~40,000× corrupted `trailingEps`
  with an entirely normal `bookValue`, producing a spurious Strong Buy that neither
  fix above reaches. **Not fixed** — documented as an accepted limitation
  (`docs/data-contracts.md`) after the obvious remedy (a standalone P/E floor) was
  *disproven*, not just judged risky, by a real counterexample (`ALNRG.PA`, a
  legitimate micro-cap with an even more extreme implied P/E).

Alongside these, two further shapes were found and are **known, documented,
unfixed** gaps: `INPHI.AS` (a phantom cross-listing with no volume data at all,
currently inert only by chance) and `LISPE.SW` (a Lindt & Sprüngli participation
certificate whose cached fundamentals were silently contaminated by its sibling
registered share).

### 1.2 Why this took as long as it did

None of the above was found by a test suite, a linter, or an alert. It was found
because a human happened to look at one screenshot and ask "does this look right?"
Finding the *next* three took a human-driven, ad-hoc investigation each time:

- A fresh Python one-liner against `.cache/fundamentals.json` for every question
  ("what's this row's raw data", "what's the distribution of P/B across the
  universe", "did my fix change anything else").
- Reasoning that had to be re-derived from scratch each time — e.g. the P/B floor
  was calibrated once by hand; the P/E floor's rejection (proven unsafe by
  `ALNRG.PA`) is currently recorded only in prose, not in a check any future change
  re-runs.
- No record of *what was already checked and found clean* — every new session
  starts from zero, at risk of re-litigating settled questions or, worse, missing
  a regression on a ticker already known to be fragile (`BC.MI`'s cache flapped
  between empty and corrupted twice mid-session, with no record of that outside
  this conversation).
- No way to know whether a `screener.py` change broke something on the *real*
  universe. The unit test suite (~900 tests, synthetic fixtures) is necessary but
  not sufficient — the `fv_basis_thin`/row-`D` interaction in
  `TestVectorisedStage3And6.test_decision_matches_scalar_ladder` was only caught
  because a later, unrelated change happened to touch the exact synthetic
  fixture that exposed it.

### 1.3 The actual gap

The data needed to catch all of this was **already local** — nothing needed to be
exported or newly collected. What was missing was a **repeatable, structured way
to look at it**: a documented set of checks, a place to record what's already been
triaged, and a way to run both against the real, current, live cache on a
predictable cadence — rather than reconstructing the entire investigation
methodology from memory every time someone notices something looks wrong.

---

## 2. Solution

A standalone **audit script** (`tools/valuation_audit.py`, working name) that runs
`screener.compute_scores` over the full cached universe and applies a documented,
versioned set of checks, producing a triaged report — not a data export, and not
an auto-fixer.

### 2.1 Pipeline

1. Load `.cache/fundamentals.json` (no export step — this *is* the data
   `compute_scores` already runs against in production).
2. Run `screener.compute_scores` once over the full frame (~2 seconds for the
   current ~7,900-ticker universe).
3. Apply the check catalog (§2.2) to the scored frame.
4. Tier each hit by severity (§2.3).
5. Attach the algorithm's own explanation fields to each hit (§2.4) — no
   re-deriving "why does this look wrong" by hand.
6. Diff against the persisted suppression/history log (§2.5); drop anything
   already triaged and unchanged.
7. Run the distribution-drift comparison against the previous run (§2.6).
8. Write one markdown report, stamped with the universe size and the
   `screener.py` git commit it ran against.

### 2.2 Check catalog

Each check is a named, documented unit — what it catches, its threshold and the
reasoning behind it, and its known false-positive history. Starting set, all
already exercised by hand this session:

| Check | Catches | Notes |
|---|---|---|
| **Implied P/B floor** | A per-share basis broken for the whole row (`bookValue` *and* `trailingEps`, which share a `sharesOutstanding` divisor) | Already shipped as `PTB_SANITY_FLOOR`; the audit re-asserts it holds, it doesn't re-derive it |
| **Net-income cross-validation** | `trailingEps × sharesOutstanding` wildly inconsistent with `netIncomeHistory[0]` — catches a corrupted EPS *even when the implied P/B looks normal* (the `BC.MI` shape) | Coverage-limited: only evaluates rows with both fields present; ambiguous on genuine year-over-year earnings volatility (`ALGTR.PA`) — flag as informational, not critical, when the mismatch is under some higher multiple |
| **Zero-volume vs. Strong Buy** | A `Strong Buy` on a confirmed-zero-`averageVolume` row | Already shipped as a hard veto; the audit re-asserts, doesn't re-derive |
| **`fv_basis_thin` vs. Strong Buy** | A `Strong Buy` resting on a single uncorroborated fair-value model | Already shipped as a Stage 6 gate; same as above |
| **Fair-value/price ratio outliers** | Any row (regardless of `Decision`) with `fair_value` many multiples of `Price` | Broader net than the two above — catches display-level nonsense even on `Avoid` rows (the `VEZ.DE`/`MLVST.PA`/`ALHGO.PA` shape), which matters for "does this look right" even when it isn't a signal-safety issue |
| **Known-rejected checks, recorded as such** | Nothing — deliberately not implemented | e.g. a standalone P/E floor. Recorded in the catalog specifically so nobody re-proposes and re-tests it without first reading why it failed |

New checks get added to this table with the same four columns before they're
wired in — the table is the spec, the code is the implementation.

### 2.3 Severity tiers

- **Critical** — currently `Strong Buy` (or `Decision` better than the check
  would imply) *and* fails a check. Review before anything else.
- **Notable** — fails a check but is already gated to `Avoid`/`Monitor` by
  something else (an unrelated veto, a low score). Real defect, low urgency —
  worth fixing for display correctness, not signal safety.
- **Informational** — fails a check at low confidence (e.g. the net-income
  cross-check on a name with plausible real earnings volatility). Surfaced for
  awareness, not for action, unless a pattern emerges across runs.

### 2.4 Self-explanation surfacing

Every flagged row carries `fv_dark_reasons`, `decision_reason`, and
`veto_reason_str` output inline in the report. These fields already exist in the
algorithm specifically to explain a row's own state (FV-6, WP-DQ9) — the audit
reuses them rather than re-deriving the explanation.

### 2.5 Suppression / history log

A gitignored, persisted file (alongside `.cache/`, not committed — same treatment
as the fundamentals cache itself) recording, per ticker + check:

- **First seen** (run timestamp, `screener.py` commit).
- **Disposition** — `fixed` (with the commit that fixed it), `documented-gap`
  (with the `data-contracts.md` section), or `dismissed-false-positive` (with a
  one-line reason, e.g. "real earnings volatility, see netIncomeHistory").
- **Last confirmed** (most recent run where the disposition was checked and still
  holds).

A finding only reappears in the headline report if its disposition changes —
e.g. a `dismissed-false-positive` ticker suddenly failing a *different* check, or
a `fixed` ticker's regression sentinel (§2.6) tripping again.

### 2.6 Regression sentinels + drift checks

- **Sentinels**: the specific tickers already found broken (`NAITR.AS`,
  `SNBN.SW`, `BC.MI`, …) are asserted against the *real, current* cache on every
  run — distinct from the synthetic-fixture unit tests, which don't catch a
  regression on the real data shape that originally broke.
- **Drift checks**: run-over-run comparison of aggregate statistics — count of
  `Strong Buy` rows, a sector's median P/E/P/B multiple, count of `veto`d rows —
  flagged when a jump is large enough to suggest a broken fetch or feed rather
  than one bad ticker. Lower priority than the per-row checks; proposed as a
  fast-follow, not part of v1.

---

## 3. Process

### 3.1 Triggers

1. **On-demand.** Run manually — after a suspicious screenshot, during a periodic
   review, or any time a real answer is needed rather than a memory of the last
   answer.
2. **Change-triggered.** Run automatically after any edit to `screener.py`'s
   valuation logic (`_fair_value_models`, `compute_scores`, the Stage 5/6 rules).
   This is the higher-value trigger: it catches real-world edge cases the ~900
   synthetic unit tests structurally cannot, at a cost of ~2 seconds per run.

### 3.2 Output

One markdown report per run: critical findings first (each with its numbers, its
algorithm-native explanation, and a suggested next step), then notable, then
informational, then the drift-check summary. Written to disk (gitignored,
alongside `.cache/`), not committed — it's operational output, not documentation
of a decision. A decision *about* a finding belongs in `data-contracts.md` /
`CHANGELOG.md`, same as the three fixes from this session.

### 3.3 Triage workflow

For each new critical or notable finding, the same process this session already
followed three times:

1. **Investigate** — confirm the finding is real (not a stale/transient fetch
   state, as `BC.MI` twice was mid-session).
2. **Verify against the algorithm** — check any proposed fix against the shipped
   design's actual invariants and calibrate it against the real current
   population, not just the one bad row (as with `PTB_SANITY_FLOOR`'s 5×+ safety
   margin, confirmed by a controlled before/after diff).
3. **Decide**: fix it (with tests + docs, same bar as this session), document it
   as an accepted limitation, or dismiss it as a false positive with a recorded
   reason.
4. **Record the disposition** in the suppression log (§2.5) so it doesn't
   resurface unchanged.

### 3.4 Explicit non-goals

- **No automatic fixes.** Every fix this session needed judgment the tool cannot
  supply — see `ALGTR.PA` (ambiguous), `BC.MI` (transient vs. stable), and the
  rejected P/E floor (disproven by a real counterexample the obvious fix would
  have missed). The tool's job ends at a triaged report.
- **No new data collection infrastructure.** The audit reads the cache that
  already exists; it doesn't export, mirror, or duplicate it anywhere.
- **No external cross-validation in the automated path.** Confirming a finding
  against real-world facts (as with `NAITR.AS` vs. `NAI.AS`'s real prices, or
  SNB's statutory dividend cap) stays a manual step for whoever reviews the
  report — it's inherently a judgment call, not a rule.

---

## 4. Open questions for v1 scoping

- Where does the persisted suppression log live exactly, and what format (JSON
  next to `.cache/`, or a small SQLite file)?
- Does "change-triggered" mean a git pre-commit/pre-push hook, or does it stay a
  manual "run it before you commit a valuation change" convention?
- Is a scheduled (cron/cloud-agent) cadence worth adding on top of the
  change-triggered run, given the fundamentals cache itself only refreshes on a
  24h (main) / 3h (thin-row heal) cycle — or does that make a daily scheduled run
  redundant with the change-triggered one in practice?
- Exposure-weighting (prioritize held/watchlisted tickers) and distribution-drift
  checks were proposed as fast-follows, not v1 scope — confirm that's still right
  once the core catalog is in use.
