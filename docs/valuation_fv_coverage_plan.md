# Fair-Value Coverage — Investigation & Improvement Plan

> **Status:** FV-1 + FV-2 implemented 2026-09-09 (branch
> `feat/fv-coverage-quickwins`) — see `CHANGELOG.md` `[Unreleased]`. FV-3…FV-8
> still open.
>
> Point-in-time analysis, 2026-09-09. Triggered by portfolio holdings whose
> drawer "Six-model fair value" section shows "—" for most or all sub-models
> (NEXI.MI, BPOST.BR, PAH3.DE, MELE.BR, SYENS.BR, LIGHT.AS observed).
> Re-verify against current code before acting — the WS-10…WS-18 pass
> (`stock_valuation_improvement_plan.md`) is the known-clean baseline.

Scope: `screener.py` `_fair_value_models` / `_row_is_scorable` / `_fetch_one`,
`uvalu/components.py::fair_value_ladder`, `uvalu/drawer.py`, `uvalu/data.py`
`data_thin`. Numbering continues as **FV-1…FV-8** (WS track ended at WS-18).

---

## 1. What was observed

Real cached rows (`.cache/portfolio_fundamentals.json`, fetched 2026-09-09),
run through the live `screener._fair_value_models`:

| Ticker | GAAP EPS | Graham | P/E FV | EPV | DDM ×2 | Analyst | Composite | Models feeding it |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| NEXI.MI  | −2.80 | — | — | — | — | ✓ 4.04 | **3.64** | 1 (haircut analyst only) |
| BPOST.BR | −0.18 | — | — | −2.33→— | — | ✓ 2.08 | **1.87** | 1 (haircut analyst only) |
| PAH3.DE  | 0.31* | 28.5 | 4.65 | — | — | — | **17.61** | 2 (Graham + P/E, both off derived EPS) |
| SYENS.BR | −0.85 | — | — | ✓ 50.3 | — | ✓ 81.9 | **57.76** | 2 |
| MELE.BR  | 2.57 | 24.9 | 31.1 | ✓ 32.9 | — | ✓ 75.5 | **34.61** | 4 |
| LIGHT.AS | 1.25 | 24.9 | 13.1 | ✓ 29.2 | — | ✓ 17.1 | **22.29** | 4 |

\* PAH3 `trailingEps` is WP-B-derived from `trailingPE` — its Yahoo payload also
dropped `enterpriseValue`, `beta`, `sector`, `country`, `targetMeanPrice`,
`payoutRatio`.

None of these are `data_thin` (they all have a non-null composite), so the UI
shows a fully-populated "Fair value" tile, a Composite score, and a
MONITOR/BUY-ish signal with **no caveat that the number rests on one weak model**.

---

## 2. Coverage impact — universe-wide, not 6 stocks

The observed tickers are the visible tip. Each root cause run across the **full
fetched screener universe** (3,714 priced names, `.cache/fundamentals.json`,
2026-09-09) and the 32-name portfolio:

| Signal | Screener universe | Portfolio |
|---|---:|---:|
| No composite fair value at all | **19.8 %** (736) | 12.5 % (4/32) |
| Fair value rests on < 2 models | **30.0 %** (1 113) | 18.8 % (6/32) |
| Lose Graham **and** P/E — no positive EPS, no `trailingPE` (RC-3) | **32.3 %** (1 199) | 15.6 % (5/32) |
| `enterpriseValue` missing → EPV can't run (RC-4a) | **14.0 %** (520) | 18.8 % (6/32) |
| EPV computes ≤ 0 → silently dropped (RC-4b) | 305 | 4/32 |
| DDM killed by a bad `payoutRatio` that cash/coverage would rescue (RC-1) | **8.0 % of payers** (182 / 2 262) | 11 % of payers (3/27) |
| EBIT mean ≤ 0 but median > 0 (RC-2) | 61 | 2/32 |
| Rows getting **all six** models | only **12.8 %** (477) | 34 % (11/32) |

Distribution of how many sub-models feed the composite (screener universe):

| models | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---:|---:|---:|---:|---:|---:|---:|
| rows | 736 | 377 | 424 | 501 | 430 | 769 | 477 |

**Per-workstream generality**

- **FV-3** (P/B + FCF fallback) — the most general fix. RC-3 hits ~⅓ of the
  universe: every loss-maker, most financials, holding companies, trough-cycle
  cyclicals, recent listings — all currently with **no** fundamentals-anchored
  fair value.
- **FV-4** (EV reconstruction) — 14 % of the universe; pipeline robustness.
- **FV-5** (thin-basis flag + heal) — infrastructure: 30 % of names push a
  ≤ 1-model fair value downstream today as if fully valued, with a Composite
  score and a signal.
- **FV-7** (DDM growth from `true_dgr`) — every DDM payer with real dividend
  history (thousands), not an edge case.
- **FV-1** (payout signal) — moderate count, skewed toward exactly the
  trough-earnings names a value screener exists to catch.
- **FV-2** (median EBIT) — smallest count (~1.6 %) but high impact per case
  (single-crisis-year names) and removes a known distortion.
- **FV-6** (reason strings) / **FV-8** (REIT Graham guard) — universe-wide UX /
  sector-wide.

**Honest ceiling.** Part of the 19.8 % "no fair value" is genuinely unvaluable —
pre-revenue, zero analyst coverage, negative book equity — and no model change
rescues those (FV-3's P/B needs positive book value). Realistic outcome: "all
six models" coverage rises from ~13 % substantially, and "no fair value at all"
roughly halves — not to zero.

---

## 3. Root causes

### RC-1 — `payoutRatio` is the only DDM gate, and it is frequently garbage
`_ddm_weight_factor` zero-weights **both** DDM variants when `payoutRatio` is
`None` or outside `[0.05, 0.95]`. yfinance's `payoutRatio` divides by trailing
**GAAP net income**, so for trough-earnings / loss-making / freshly-spun-off
names it returns nonsense:

| Ticker | `payoutRatio` | `cashPayoutRatio` (DPS·sh / FCF) | `dividendCoverage` (EPS/DPS) | DDM today |
|---|---:|---:|---:|---|
| NEXI.MI  | 1.087 | **0.448** | — | suppressed |
| SYENS.BR | 7.742 | **0.309** | — | suppressed |
| LIGHT.AS | 1.256 | **0.386** | 0.80 | suppressed |
| MELE.BR  | 1.440 | 1.359 | 0.69 | suppressed (correctly — stretched on every metric) |
| BPOST.BR | 0.0 | — | — | suppressed (correctly — dividend suspended, rate 0.0) |
| PAH3.DE  | None | — | 0.21 | suppressed |

`_fetch_one` already derives `cashPayoutRatio` and `dividendCoverage`; the DDM
gate ignores both. A sane fallback chain rescues NEXI/SYENS/LIGHT and correctly
leaves MELE/BPOST dark.

### RC-2 — `_normalised_ebit` is a plain mean, dominated by one crisis year
EPV needs `ebit > 0`. `ebit` (point-in-time) is `None` for **every** cached
ticker, so EPV leans entirely on `mean(ebitHistory)`:

- **PAH3.DE** EBIT history `[+2.96bn, −19.79bn, +5.44bn, +5.41bn]` → mean
  **−1.50bn** → EPV refused. Median is **+4.19bn**.
- **NEXI.MI** one −2.89bn year drags the 4-yr mean to **−0.58bn** → EPV refused.

No trimming, winsorizing, or median option.

### RC-3 — No model survives a negative GAAP EPS
Graham **and** P/E fair value both require `eps > 0`; when Yahoo also suppresses
`trailingPE` (it does for loss-makers) WP-B can't recover an EPS either. That
leaves only EPV + analyst target — and EPV often fails too (RC-2 / RC-4).
Meanwhile `bookValue`, `priceToBook`, and usually `freeCashflow` are present and
sane for these same rows and **no model uses them**:

| Ticker | bookValue | priceToBook | freeCashflow |
|---|---:|---:|---:|
| NEXI.MI  | 5.79 | 0.71 | **+786m** |
| BPOST.BR | 4.30 | 0.29 | +234m |
| SYENS.BR | 60.8 | 1.34 | +534m |
| PAH3.DE  | 116.7 | 0.25 | None |

NEXI is the textbook case: −€2.80 GAAP EPS (acquired-intangible amortization)
but **+€786m FCF** — unvaluable by every model the app currently runs.

### RC-4 — EPV has two silent single points of failure
1. **`enterpriseValue` missing** (PAH3) → EPV abandoned. Never reconstructed
   from `marketCap + totalDebt − totalCash` — and `totalDebt` / `totalCash` /
   `marketCap` aren't even in `VALUATION_FIELDS`.
2. **Net-debt sign flip**: `(EPV_EV − net_debt) / shares` goes negative for
   leveraged names (BPOST −€2.33, AED −€42) and is dropped by the `v > 0`
   filter with no flag — indistinguishable from "no data".

### RC-5 — Degraded Yahoo payloads are never healed
PAH3 returned with 6 key fields null. Because one model (Graham, off a derived
EPS) still yields a number, `_row_is_scorable` is `True`, so the row keeps the
**full 24 h TTL** instead of the 3 h `CACHE_TTL_SHORT_HOURS` thin-row heal.
"At least one model works" is too weak a bar for "this row is healthy".

### RC-6 — The UI can't tell "missing" from "refused" from "negative"
`fair_value_ladder` renders a bare "—" for all three. `data_thin` only fires
when the **composite** is null, so a composite that is 100 % haircut-analyst
(NEXI €3.64 = €4.04 × 0.9) looks identical to a well-corroborated one. The
drawer's "Analyst Target" row also shows the **raw** €4.04 while the composite
uses the **haircut** €3.64, so the on-screen numbers don't reconcile.

### RC-7 — DDM growth input is inconsistent with the rest of the app
`_fair_value_models` passes raw `earningsGrowth` to `_ddm_single` /
`_ddm_multistage`; TER and the dividend scores use `_dgr_estimate` (real DPS
CAGR from `_dividend_stats`, `earningsGrowth` only as fallback).

### RC-8 (surfaced in passing) — Graham/P-E meaningless for REITs
AED.BR Graham €131.8 / P/E FV €131.5 vs €66 price — property-revaluation gains
inflate both EPS and book value. No sector guard.

---

## 4. Improvement plan

### FV-1 — Robust DDM payout signal *(RC-1)* — effort **S** — ✅ shipped 2026-09-09
- `screener._payout_signal(row) -> (value|None, source)`: `payoutRatio` when
  finite in `[0.0, _DDM_PAYOUT_KNOTS[3]]` (0–0.95 — the ramp's own contributing
  band, where the GAAP denominator is sound) → else `cashPayoutRatio` when
  finite in `(0.0, 1.5]` (`_PAYOUT_CASH_MAX`) → else `1 / dividendCoverage`
  (capped at 10) when `dividendCoverage > 0` → else the extreme reported value
  if present (ramp zeroes it) → else `None`.
- `_ddm_weight_factor(div_rate, payout)` unchanged — it just receives the signal.
- `payout_source` (`reported` / `cash` / `coverage` / `none`) persisted on the
  scored row for FV-6.
- `_row_is_scorable`'s DDM branch now checks
  `_ddm_weight_factor(div, _payout_signal(row)[0]) > 0` (was: `payoutRatio is not None`).
- **Result on the reference portfolio:** DDM restored for NEXI.MI (composite
  3.64 → 8.31), SYENS.BR (57.76 → 43.39), LIGHT.AS (now all 6 models);
  MELE.BR (cash 1.36) and BPOST.BR (dividend suspended) correctly stay dark.
  PAH3.DE unchanged — needs FV-4 (no `enterpriseValue`).

### FV-2 — Normalised EBIT: median + outlier guard *(RC-2)* — effort **S** — ✅ shipped 2026-09-09
- `_normalised_ebit`: with ≥ `_EBIT_MIN_YEARS` (3) finite years, drop every year
  more than `_EBIT_OUTLIER_MAD_K` (3) MADs from the median, then mean the rest
  (≥2 kept, else the median); degenerate spread → the median; < 3 years →
  point-in-time `ebit`.
- `_row_is_scorable` unchanged (its EBIT branch is already lenient).
- **Result:** PAH3 EBIT base −1.50bn → +4.60bn (the −19.8bn year dropped);
  NEXI +0.19bn (was −0.58bn). EPV still negative for both on *net-debt* grounds
  (FV-4b), but the earnings-power input is no longer the blocker.

### FV-3 — Book-value & FCF fallback models for loss-makers *(RC-3)* — effort **M**
Two new models in `_fair_value_models`, contributing **only** when the
fundamentals trio (Graham / P/E / EPV) produced ≤ 1 value:
- **P/B fair value** = `bookValue × sector_median_pb` — new
  `_sector_pb_medians(df)` sibling of `_sector_pe_medians`, winsorized to a
  `PB_MULTIPLE_BAND` (≈ 0.6–3.0), `PB_MULTIPLE_FALLBACK` ≈ 1.0.
- **FCF value** = `(freeCashflow / sharesOutstanding) × FCF_MULTIPLE` (≈ 12–18,
  or `1/(wacc − g_stable)` capped), guarded on `freeCashflow > 0`.
- New weights `W_PB`, `W_FCF` (≈ 0.10 each); rebalance the base-weight block to
  keep the sum at 1.00. Add both to `_row_is_scorable`.
- **Decision needed:** drawer ladder becomes an 8-row list, *or* the two dark
  fundamentals slots are swapped for whichever fallback fired. Recommend: keep 6
  rows, relabel slot 1/2 dynamically ("Book value" / "FCF value") when they
  substitute, with a tooltip.
- Expected: NEXI gets FCF + P/B; BPOST / SYENS get P/B.

### FV-4 — EPV hardening *(RC-4)* — effort **S–M**
- Add `totalDebt`, `totalCash`, `marketCap` to `VALUATION_FIELDS`
  (each `_safe_float`, isolated — a miss must not trip the ticker backoff).
- When `enterpriseValue` is `None`, reconstruct
  `ev = (marketCap or price·shares) + totalDebt − totalCash`.
- When per-share EPV ≤ 0, keep it out of the blend but set `epv_negative=True`.
- Optionally expose an EV-level EPV (no net-debt subtraction) as a secondary,
  clearly-labelled figure for `LEVERAGE_EXEMPT_SECTORS`.

### FV-5 — Thin-basis detection & heal *(RC-5)* — effort **S**
- `screener._fair_value_model_count(row)` → how many sub-models produced a value.
- `uvalu/data.py`: new column `fv_basis_thin = count < MIN_FV_MODELS` (default 2).
- Add `fv_basis_thin` rows to the thin-row retry set in `compute_scores` so they
  heal on `CACHE_TTL_SHORT_HOURS`, alongside `~_row_is_scorable`.
- Optionally asterisk / down-weight the Composite score when `fv_basis_thin`.

### FV-6 — UI: reasons for dark / refused models *(RC-6)* — effort **M**
- `fair_value_ladder(..., reasons: dict[str,str] | None)` — muted suffix or
  hover on a dark row: "no positive EPS", "EPV negative — net debt", "dividend
  not covered (payout 144 %)", "no analyst coverage", "input pending — refetch".
- Add a "basis: N of 6 models" line under the composite; caption when N < 2.
- "Analyst Target" ladder row shows the **haircut** value used in the composite
  (or annotates "−10 % optimism haircut applied downstream") so the numbers
  reconcile.

### FV-7 — DDM growth from `true_dgr` *(RC-7)* — effort **S**
- Pass `_dgr_estimate(row)` into `_ddm_single` / `_ddm_multistage` instead of
  raw `earningsGrowth`. Aligns the fair-value DDM with TER / dividend scoring.

### FV-8 — Sector guard on Graham / P-E *(RC-8)* — effort **M**
- Skip Graham (and optionally P/E) for `LEVERAGE_EXEMPT_SECTORS`; rely on the
  FV-3 P/B model + DDM there. Add a regression test on AED.BR.

---

## 5. Sequencing

```
FV-2  median EBIT            ─┐  independent quick wins,
FV-1  robust payout signal    │  land in any order, no UI change
FV-7  DDM growth = true_dgr  ─┘  → restores DDM/EPV for NEXI, SYENS, LIGHT, PAH3

FV-4a fetch totalDebt/Cash/mcap   ── prereq for FV-4b and helps FV-3
FV-4b EV reconstruction + epv_negative

FV-5  thin-basis flag + heal      ── independent

FV-3  P/B + FCF fallback models   ── the big one; needs the ladder-layout call

FV-6  reason strings + basis line ── last; consumes flags from FV-1/4/5
FV-8  REIT sector guard           ── independent, pairs with FV-3
```

**Minimal quick win (≈1 day, no UI work):** FV-1 + FV-2 alone bring back DDM
and/or EPV for **4 of the 6** screenshotted names.

**Full coverage:** add FV-3 (+ FV-4) so negative-GAAP-EPS names
(NEXI, BPOST, SYENS) get a real fundamentals-anchored fair value instead of a
lone haircut analyst target.

---

## 6. Cross-cutting constraints (every FV workstream)

- Keep `_row_is_scorable` in lock-step with `_fair_value_models`' per-model
  input guards (the docstring already says so).
- Every new fetch field wrapped so a miss degrades that field to `None` and
  never triggers the whole-ticker retry/backoff.
- New models covered in `tests/test_algorithms.py`; the two-lane agreement test
  `tests/test_data_contracts.py::test_the_two_fetch_lanes_agree_on_whether_a_held_ticker_has_a_fair_value`
  must still pass.
- Update `docs/stock_valuation_algorithm.md` (model list, weights) and
  `docs/data-contracts.md` (new columns: `payout_source`, `epv_negative`,
  `fv_basis_thin`, `fv_model_count`).
- Weight blocks must re-sum to 1.00 after adding `W_PB` / `W_FCF`.

---

## 7. Conflicts with `stock_valuation_algorithm.md`

Checked every FV item against the spec. **No item violates a core invariant** —
base weights summing to 1.00, the plain weighted-average composite, WACC / Blume
beta, the hard-veto rules, and Stage 5 scoring are all untouched. What exists is
mostly documentation-sync (the spec *describes* the current mechanism and
several FV items change it), plus **one explicit reversal** (FV-3) and **one
small UI conflict** (FV-6).

| FV item | Conflict type | Spec lines to revise |
|---|---|---|
| **FV-1** robust payout signal | **Doc-sync.** Lines 48 / 59 state the DDM ramp is "keyed on **the payout ratio**", with knots (`0.05 / 0.30 / 0.70 / 0.95`) calibrated for the *accounting* `payoutRatio`. Feeding `cashPayoutRatio` / `1 ÷ coverage` through the same knots is a semantic mismatch — those ratios have different distributions. Needs the Stage 2 "DDM payout ramp" paragraph + summary lines 162–164 rewritten, ideally with per-source knots. | 48, 59–61, 162–164 |
| **FV-2** median / trimmed EBIT | **Doc-sync, reverses a deliberate choice.** Lines 39 & 159 say three times "EBIT is the **mean** over `ebitHistory` … so a peak or trough year doesn't set the valuation". The PAH3 case (one −19.8 bn year) shows the mean does *not* survive a lone catastrophe — frame FV-2 as revising review 2.3, not a bug fix. | 39, 159 |
| **FV-3** P/B + FCF models | **Explicit reversal + structural.** Line 44: "an **asset-based / P/B model are not implemented**". Line 29: "Price-to-book and EV/EBITDA … are **display-only**". Line 32: "**Six models** run per stock". And line 68–71's composite is a flat weighted average over *available* models — "contribute only when Graham/PE/EPV gave ≤ 1" is new conditional-gating the design doesn't have. FCF-capitalisation also overlaps EPV (double-weighting cash-flow valuation). | 29, 32, 44, 54, 68–71, Stage 2 table, summary |
| **FV-4** EPV hardening | **Additive, minor.** New fetched fields extend line 17–27; EV reconstruction extends the `NetDebt = EV − Price×Shares` chain in line 39. `epv_negative` is UI-only — line 32 already excludes non-positive models. No principle conflict. | 21, 39 |
| **FV-5** thin-basis flag + heal | **No conflict** with this spec (TTL / `data_thin` live elsewhere). The *optional* "down-weight the Composite score" would reach into Stage 5/6 — keep that as a separate proposal. | 26 (optional) |
| **FV-6** reason strings | **UI-only, except** the "show the haircut analyst value in the ladder" sub-point — line 42 documents raw-vs-haircut display as *intentional* ("the undiscounted `targetMeanPrice` is still shown as-is elsewhere in the UI"). Keep raw, annotate instead. | 42 |
| **FV-7** DDM growth from `true_dgr` | **Doc-sync, consistent direction.** Lines 40–41 don't say where `g` comes from; line 62 lists `_dgr_estimate` for TER / dividend scores but not the DDM models. Strengthens (doesn't break) the Stage 3 DGR-halving rationale. | 62, Dividend-Specific table |
| **FV-8** skip Graham/PE for REITs | **Structural addition.** Line 37 has no sector gate; `LEVERAGE_EXEMPT_SECTORS` (line 142) is currently veto-only; Stage 2 applies all six models uniformly. Conceptually consistent with the existing sector-exempt pattern, but new. | 37, 142, Stage 2 |

### Not in conflict (verified)

- **The EBIT-collapse hard veto is unaffected by FV-2** — it reads
  `_clean_history(row, "ebitHistory")` (`screener.py` ~L1516), not
  `_normalised_ebit`. FV-2's blast radius is EPV only (the sole caller of
  `_normalised_ebit`).
- **Dividend risk / dividend score still use raw `payoutRatio`** — FV-1 only
  touches `_ddm_weight_factor`; `_dividend_risk_score` / `_dividend_score_raw` /
  the sustainability flag are separate call sites, so line 59's "as reported"
  stays accurate for them.
- **WACC, Blume beta, Stage 5 weights, MoS / TER formulas, every veto** — untouched.

### Two decisions to settle before coding

1. **"Six models" identity.** FV-3 breaks the count that appears in the Stage 2
   title, line 32, the drawer section header, and `Uvalu.dc.html`'s design spec.
   Lower-conflict path: keep 6 ladder rows, dynamically relabel slots 1–2 as
   "Book value" / "FCF value" when they substitute (recommended in FV-3).
2. **Flat weighted average vs. conditional contribution.** Fallback models that
   fire only when the primary trio is thin depart from line 68–71. Alternative:
   give P/B and FCF permanent small weights and let the existing `v > 0` filter
   handle availability — stays within the current design.
