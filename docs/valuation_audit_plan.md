# Valuation & Risk Accuracy Audit — Problem, Solution, Process

Status: **proposed, not built**. This document describes the gap found during the
2026-09-11 investigation session (the `NAITR.AS` incident and its follow-ons) and
the tool proposed to close it. No code has been written yet.

**Revision history:**
- v1.0 — initial draft.
- v1.1 — check catalog reorganized into four functional families per human
  review; thresholds corrected to match the actually-shipped `PTB_SANITY_FLOOR`
  formula; three new checks added (net-income cross-validation refinement,
  `sharesOutstanding` sanity, Decision/veto consistency, dividend-yield sanity,
  catalog-integrity meta-checks); one proposed check (`Price vs. sibling
  listings`) evaluated against evidence already gathered this session and kept
  out of v1 — see §2.2.1.
- v1.2 — self-review pass: findings aggregate per ticker rather than per check
  (§2.1); rejected checks now require a persisted falsifying fixture, not
  prose alone (§2.2's catalog-integrity family); the `LISPE.SW`-shaped catalog
  gap stated explicitly rather than left implicit (§2.2.2); report volume
  control and an explicit report-vs-log division of labor added (§3.2);
  "change-triggered" decided as a `CONTRIBUTING.md` convention rather than left
  as an open question (§3.1, §4).

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
4. **Aggregate hits per ticker, not per check.** A single row commonly fails
   more than one check at once — a treasury-share-style listing typically trips
   both the zero-volume veto *and* `fv_basis_thin` simultaneously, as several
   Amsterdam rows did this session. One finding per ticker, listing every check
   it failed, not one fragment per check-row pair scattered across sections.
5. Tier each finding by severity (§2.3), using the *worst* check confidence it
   carries once aggregated.
6. Attach the algorithm's own explanation fields to each finding (§2.4) — no
   re-deriving "why does this look wrong" by hand.
7. Diff against the persisted suppression/history log (§2.5); drop anything
   already triaged and unchanged.
8. Run the distribution-drift comparison against the previous run (§2.6).
9. Write one markdown report, stamped with the universe size and the
   `screener.py` git commit it ran against.

### 2.2 Check catalog (v1.1)

Reorganized (per human review) into four functional families, each check
carrying an explicit **status** — `shipped` (re-asserts real code, doesn't
re-derive it), `calibrated` (threshold checked against this session's real
data), or `proposed` (plausible, not yet validated against the real universe —
must be calibrated before it's trusted at anything above informational
severity). New checks get added to this catalog with the same fields — status,
threshold, false-positive evidence — before they're wired in; the catalog is
the spec, the code is the implementation.

#### Basis-integrity checks (structural correctness)

Detect structural corruption in fundamentals — the kind that produces absurd
fair values even when the algorithm itself behaves correctly.

- **Implied P/B floor** — `shipped`. Re-asserts `screener.PTB_SANITY_FLOOR`.
  Threshold: `Price / bookValue < 0.02` (the audit reads the constant from
  `screener.py` rather than hardcoding it, so the two can never drift apart).
  False positives: none found — a controlled before/after diff across the full
  7,859-ticker cached universe changed exactly the one targeted row
  (`SNBN.SW`), confirmed this session.
- **Net-income cross-validation** — `calibrated`. Catches a corrupted
  `trailingEps` even when the implied P/B looks entirely normal (the `BC.MI`
  shape — `priceToBook` was a plausible 9.76). Threshold:
  `(trailingEps × sharesOutstanding) / netIncomeHistory[0] > 20` or `< 0.05`,
  **or** a sign mismatch (implied net income positive, latest reported net
  income negative, or vice versa) — stated as its own explicit trigger rather
  than relying on the ratio going negative to fall under `0.05`, which works
  but is easy to miss when reading the check. 20×/0.05× keeps real earnings
  volatility (`ALGTR.PA`, ~2.2× either direction) safely below the line while
  still catching every corrupted case found this session (`BC.MI` ~56,000×,
  `MLVST.PA` ~4,838×, `ALHGO.PA` ~100×). Coverage-limited: only evaluates rows
  with both `sharesOutstanding` and `netIncomeHistory` present — report
  coverage explicitly (see "Check coverage completeness" below). *Proposed
  refinement, not yet scoped*: a
  confidence band keyed to sector-level earnings volatility, to narrow the
  ambiguous zone around `ALGTR.PA`-shaped cases — needs a volatility metric
  that doesn't exist yet, so this stays a noted idea, not v1 scope.
- **`sharesOutstanding` sanity** — `proposed`, **not yet validated**. Candidate
  thresholds: `< 1,000` or `> 10 billion`. Flagged as informational-only, and
  only escalated when combined with another hit, specifically because the
  lower bound has a known real counterexample already in this catalog: `SNBN.SW`
  has a genuine, legitimate `sharesOutstanding` of 100,000 — an order of
  magnitude above a naive "implausibly low" cutoff, but real. Calibrate the
  actual bounds against the live universe (same method used for the P/B floor
  — find the real floor/ceiling among currently-legitimate rows) before
  trusting this beyond informational.

#### Signal-safety checks (protecting BUY / Strong Buy)

Assert that no BUY / Strong Buy is issued on structurally unsafe data —
regression sentinels for the Stage 6 rules specifically.

- **Zero-volume vs. Strong Buy** — `shipped`. Re-asserts the hard veto.
  `averageVolume == 0` (confirmed, not missing) **and** `Decision == "Strong Buy"`
  should never co-occur.
- **`fv_basis_thin` vs. Strong Buy** — `shipped`. Re-asserts the Stage 6 gate.
  `fv_basis_thin == True` **and** `Decision == "Strong Buy"` should never
  co-occur.
- **`Decision` / `veto` internal consistency** — `calibrated` (as a code
  invariant, not against ticker data). Asserts `veto == True ⟹ Decision ==
  "Avoid"` — a pure internal-consistency check, not tied to any specific
  ticker, so it has no false-positive risk by construction: either the
  invariant holds or `compute_scores`' own Stage 6 logic has regressed. This is
  the real-data counterpart to `TestVectorisedStage3And6.
  test_decision_matches_scalar_ladder`, which already caught one instance of
  this exact class of drift (the `fv_basis_thin`/row-`D` case) — on synthetic
  fixtures only. Worth extending to the full Stage 6 formula (`Strong Buy ⟹
  score ≥ buy_threshold ∧ MoS ≥ min_mos ∧ ¬fv_basis_thin ∧ ¬veto`) rather than
  just the veto leg, as a fast-follow.

#### Display-correctness checks (nonsense values even when the signal is safe)

Catch rows that "look wrong" even where they don't affect BUY/Strong-Buy
safety — the `VEZ.DE`/`MLVST.PA`/`ALHGO.PA` shape, already `Avoid` via an
unrelated veto but still showing a garbage `fair_value`.

- **Fair-value/price ratio outliers** — `calibrated`, with an important
  caveat. Bands: informational `> 20×`, notable `> 50×`, critical `> 200×` —
  but this check's own magnitude alone must **not** set final severity, only a
  confidence floor within it. `TPG0.DE`, a real, currently-legitimate `Strong
  Buy`, sits at ~23.5× — informational by this check alone, and correctly so.
  Final severity still comes from the §2.3 Decision-context rule (is it
  currently reaching Strong Buy); this check's bands should only push a
  finding toward `critical` when corroborated by a basis-integrity hit on the
  same row, the same combinability rule applied to `sharesOutstanding` sanity
  above.
- **Dividend-yield sanity** — `calibrated`, and explicitly a *symptom* check,
  not an independent root-cause detector. Threshold: yield `> 40%` or `< -5%`.
  Directly motivated by `NAITR.AS`'s 562.5% figure, but that number is
  `screener.py`'s own documented `trailingAnnualDividendRate / Price`
  computation working exactly as designed on an already-corrupted price — this
  check will almost always co-fire with a basis-integrity or zero-volume hit
  on the same row, not stand alone. The `< -5%` branch is untested: the
  current `dividendYield` computation has no code path that produces a
  negative value, so this branch is defensive (if it ever fires, something
  upstream is already broken) rather than calibrated against an observed case.

##### 2.2.1 Considered and not included: price vs. sibling listings

Proposed: flag cross-listed tickers whose price differs from a same-company
sibling by more than 50×, as a cheap way to catch phantom/treasury-style
listings (`NAITR.AS` vs. `NAI.AS`, `INPHI.AS` vs. `PHIA.AS`).

**Not included in v1.1.** This is the same approach — same-company duplicate
price/listing detection — already investigated and rejected earlier in this
session, for a reason a 50× threshold doesn't route around: real, legitimate
cross-listings routinely exceed it. The concrete counterexample already in
hand: Berkshire Hathaway's own dual share classes differ by design by roughly
**1,500×** (each Class A share converts to 1,500 Class B shares) — a real,
public, well-known ratio, not a data defect — and its actual Frankfurt
cross-listings in this session's own data showed exactly that shape (`BRH
646000` vs. `BRHF 22.6`, a ~28,600× spread from currency/depositary-ratio
effects on top of the real A/B split). A same-page duplicate-name scan across
all six exchanges earlier in this session found 681 duplicate company names on
Frankfurt alone, the large majority legitimate multi-tranche listings of
foreign megacaps (`NVIDIA`, `Alphabet`, `Roche` all appear twice there, several
with both lines actively trading) — see `docs/data-contracts.md`'s "Known
residual gap" entries for the full evidence. A ratio threshold, even used only
as an informational tiebreaker, would misfire across a meaningful share of
that population. If this is revisited, it needs the same missing ingredient
identified in `data-contracts.md`: reliable cross-ticker company-identity data
(`ISIN` is fetched into the schema but populated on 0 of 7,861 cached tickers
today), not a price-ratio heuristic.

##### 2.2.2 Known catalog gap: share-class fundamentals contamination

Stated plainly rather than left implicit: **`LISPE.SW`'s failure shape is not
covered by anything in v1.1.** `LISPE.SW` (a Lindt & Sprüngli participation
certificate whose cached `bookValue`/`trailingEps` were silently copied from
its sibling registered share, `LISN.SW`) has a normal-looking implied P/B, real
trading volume, and enough corroborating models to clear `fv_basis_thin` — none
of the four families above reach it. The one approach that would (comparing a
row's fundamentals against a same-company sibling's) is exactly what §2.2.1
rejects, for good reason. Four functional families covering every check in this
catalog should not be read as four families covering every *failure shape* —
this one is a known, accepted, currently-uncovered gap, tracked in
`docs/data-contracts.md` rather than in this catalog, and it stays that way
until reliable cross-ticker company-identity data exists.

#### Catalog-integrity checks (meta-level consistency)

Keep the audit itself correct and legible across versions, distinct from
checks that assess ticker data.

- **Known-rejected checks, recorded as such** — `shipped` (as documentation),
  backed by a **falsifying fixture**, not prose alone. Every check considered
  and rejected (the standalone P/E floor, disproven by `ALNRG.PA`;
  price-vs-sibling-listings, §2.2.1) stays in the catalog with its
  `catalog_version`, its rejection evidence, *and* the actual counterexample
  data point that disproved it, persisted as a permanent test fixture (e.g.
  `ALNRG.PA`'s real field values from this session; the Berkshire A/B ratio).
  A prose warning only works if someone reads it first; a fixture means a
  reintroduced version of either check fails a real assertion the moment it's
  wired in, the same way a shipped regression test protects code rather than
  a code comment.
- **Check coverage completeness** — `proposed`, meta-check. For each row,
  record which checks *could* run given the fields present (e.g. "EPS present,
  `netIncomeHistory` missing → net-income cross-validation skipped, not
  passed"). A silent row in the report must be distinguishable from "checked,
  clean" — this directly answers the coverage question raised in §2.2's
  net-income check.

### 2.3 Severity tiers

Two separate axes, not one: a check's own threshold bands (§2.2 — e.g. the
fair-value/price ratio's informational/notable/critical bands) set how
*confident* that single check is; final severity also depends on the row's
`Decision` context, and the two combine rather than either alone deciding:

- **Critical** — currently `Strong Buy` (or `Decision` better than a
  signal-safety check implies — see the `Decision`/`veto` consistency check)
  *and* fails a check at calibrated or shipped confidence. Review before
  anything else.
- **Notable** — fails a check but is already gated to `Avoid`/`Monitor` by
  something else (an unrelated veto, a low score). Real defect, low urgency —
  worth fixing for display correctness, not signal safety.
- **Informational** — fails a check at low confidence (a `proposed`,
  not-yet-validated check; a display-correctness check firing without
  basis-integrity corroboration; the net-income cross-check on a name with
  plausible real earnings volatility). Surfaced for awareness, not action,
  unless a pattern emerges across runs.

### 2.4 Self-explanation surfacing

Every flagged row carries `fv_dark_reasons`, `decision_reason`, and
`veto_reason_str` output inline in the report. These fields already exist in the
algorithm specifically to explain a row's own state (FV-6, WP-DQ9) — the audit
reuses them rather than re-deriving the explanation.

### 2.5 Suppression / history log

A gitignored, persisted file (alongside `.cache/`, not committed — same treatment
as the fundamentals cache itself) recording, per ticker + check:

- **First seen** (run timestamp, `screener.py` commit, and the check
  catalog's own version — e.g. `v1.1` — so a disposition made under an older
  catalog is visibly stale if the check that produced it later changes).
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
2. **Change-triggered.** Run after any edit to `screener.py`'s valuation logic
   (`_fair_value_models`, `compute_scores`, the Stage 5/6 rules). This is the
   higher-value trigger: it catches real-world edge cases the ~900 synthetic
   unit tests structurally cannot, at a cost of ~2 seconds per run. **Default
   mechanism: a checklist line in `CONTRIBUTING.md`** (which already governs
   the release checklist) — "run the valuation audit before committing a
   change to `_fair_value_models`/`compute_scores`" — not a git hook. A
   convention needs zero new infrastructure to start; an enforced pre-commit
   hook is a valid upgrade later (§4) once the convention has actually been
   used a few times.

### 3.2 Output

One markdown report per run: critical findings first (each aggregated per
ticker per §2.1 — its numbers, its algorithm-native explanation, and a
suggested next step), then notable, then informational, then the drift-check
summary.

- **Volume control.** Critical and notable findings are always shown in full.
  Informational findings are capped — the top N (by check confidence) shown in
  full, the remainder summarized by count ("+ 47 more informational hits, see
  the full log") rather than dumped inline. Today's own scan surfaced dozens of
  borderline P/B/P/E rows in the tail; an uncapped report would be unreadable
  within a few runs.
- **Report vs. log, explicit division of labor.** The markdown report is a
  human-readable snapshot of *this run only* — nothing should ever need to
  parse it back out. The suppression/history log (§2.5) is the durable,
  structured, machine-readable state; any future automation (the run-over-run
  diff in §2.6, a later tool) reads the log, never the report.

Written to disk (gitignored, alongside `.cache/`), not committed — it's
operational output, not documentation of a decision. A decision *about* a
finding belongs in `data-contracts.md` / `CHANGELOG.md`, same as the three
fixes from this session.

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
- Decided (§3.1): "change-triggered" defaults to a `CONTRIBUTING.md` checklist
  convention, not a git hook. Open remainder: once that convention has actually
  been used a few times, is a real pre-commit/pre-push hook worth the added
  infrastructure, or does the convention hold up on its own?
- Is a scheduled (cron/cloud-agent) cadence worth adding on top of the
  change-triggered run, given the fundamentals cache itself only refreshes on a
  24h (main) / 3h (thin-row heal) cycle — or does that make a daily scheduled run
  redundant with the change-triggered one in practice?
- Exposure-weighting (prioritize held/watchlisted tickers) and distribution-drift
  checks were proposed as fast-follows, not v1 scope — confirm that's still right
  once the core catalog is in use.
- The two `proposed` (not yet validated) checks — `sharesOutstanding` sanity and
  the net-income cross-check's sector-volatility confidence band — need the same
  real-universe calibration pass the P/B floor and the 20×/0.05× net-income
  bounds already got before they should count for more than informational
  severity. Do that calibration before or as part of v1 build, not after.
