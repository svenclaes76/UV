# Stock Valuation Improvement Plan

> **Status: complete (Aug 2026).** All of WS-10…WS-18 shipped on branch
> `feat/ws1-marketdata-provider`, plus the EPV normalised-EBIT follow-up (review 2.3)
> and the composite-weight rebalance (review 4.2 / 5.2, `W_MOS/W_RISK/W_QUALITY`
> → 0.24 / 0.22 / 0.24). This document is kept as the historical rationale; the
> shipped behaviour is described in [`stock_valuation_algorithm.md`](stock_valuation_algorithm.md)
> and `CHANGELOG.md`. The "Still open" column below records what was *deliberately
> deferred* (all no-data-source items).

Turns the external technical review (`valuation_cop.md`, Aug 2026) into a sequenced
workstream plan, cross-referenced against what already shipped in the WS-1…WS-9
risk-engine rework and the four rounds of `screener.py` valuation fixes
(see `valuation-algorithm-fixes` / `risk-algorithm-fixes` memories and
[`stock_valuation_algorithm.md`](stock_valuation_algorithm.md)).

Scope: the `screener.py` / `scoring.py` valuation track only — `risk.py`'s 8-stage
portfolio engine is untouched. Workstream numbering continues from the risk track
(which ended at WS-9), so the items below are WS-10…WS-18.

> Point-in-time plan. Re-verify against current code before acting on any item —
> the prior fix rounds are the known-clean baseline, not a re-derivation target.

---

## 1. Review status vs. shipped work

| Review point | Already shipped | Still open |
|---|---|---|
| **2.1** Analyst weight 20.8% | 10% haircut on the model input (`ANALYST_TARGET_HAIRCUT`); weight rebalanced 0.25 → `W_ANALYST=0.208` | Still the single largest weight; no conditioning on analyst dispersion or coverage count |
| **2.2** PE = EPS × 15 | Only the *label* corrected (doc no longer calls it "Graham's multiple") | Formula unchanged — no sector-relative or PEG adjustment |
| **2.3** EPV net-debt subtraction | Exact `(EPV_EV − NetDebt)/shares`, `NetDebt = EV − Price×Shares`, EV-ratio fallback; country-aware tax rate (`COUNTRY_TAX_RATES`) | EBIT still point-in-time → EPV unstable for volatile-EBIT firms |
| **2.4** Binary DDM gate (5–90% payout) | Nothing — still a hard `0.05 ≤ payout ≤ 0.90` cliff | Graduated weighting |
| **3.1 / 5.2** MoS dominates composite | WS-18 style presets (`balanced`/`value`/`growth`/`income`) **and** the `balanced` default rebalanced to `W_MOS=0.24` / `W_RISK=0.22` / `W_QUALITY=0.24` — MoS no longer the sole top weight | — |
| **3.2 / 4.3** `earningsGrowth` as DGR proxy | `true_dgr` from real DPS history (`_dividend_stats`); `_dgr_estimate` prefers it; TER halves DGR when DDM contributed | Largely closed. Only gap: UI doesn't show when the weak proxy is still in use |
| **4.1** Beta from yfinance | `risk.py` regresses beta per holding vs `^STOXX50E` (`_resolve_betas` / `_ols_beta`) | `screener.py`'s `_approx_wacc` + `_market_risk_score` still consume raw `beta` |
| **4.2** Earnings quality misses accruals | `_earnings_quality_score` blends FCF/NI conversion with multi-year `fcfHistory` consistency (positive-year fraction + CV) | No accrual ratio `(NI − CFO)/assets` |
| **5.1** Percentile ranking fragile | `MIN_UNIVERSE_SIZE=20` + `small_universe` flag surfaced as a caption caveat | Ranks still purely cross-sectional — an all-overvalued universe still yields a full 0–100 spread |
| **6** Missing trend vetoes | FCF negative 3 consecutive years; `dividend_last_cut_year` feeds the sustainability flag | No revenue-decline, EBIT/interest-coverage-trend, retained-earnings, or standalone dividend-cut veto |
| **7** Data pipeline | +multi-year FCF, +full DPS history, +price history / FX / Fama-French factors (risk side) | No multi-year income statement / balance sheet; no peer-comps dataset; risk-free/ERP still static constants |

**Deliberately not doing** (no data source — keep documented as known limitations,
as the spec already does under Stage 1 / Stage 6 "Not implemented"): covenant-breach
risk, active fraud / restatement detection, sector-specific regulatory vetoes (bank
capital ratios, REIT FFO payout), a live macro feed for `RISK_FREE_RATE` /
`EQUITY_RISK_PREMIUM`, and a peer-multiples fair-value model.

---

## 2. Workstreams

### WS-10 — Multi-year statement history *(foundational enabler)*

Highest-leverage addition: unlocks WS-11, WS-15, WS-16 and a real fix for 2.3.

- New `screener._statement_history(tkr)`, structured like the existing `_fcf_history`:
  one isolated `try/except` per call so a failure never trips the whole-ticker
  retry/backoff.
- Pulls `tkr.income_stmt` and `tkr.balance_sheet` (same shape as the `.cashflow`
  call already made). Stores, newest-first, on each cached row:
  - `revenueHistory` ("Total Revenue"), `ebitHistory` ("EBIT" / "Operating Income"),
    `netIncomeHistory`
  - `cfoHistory` ("Operating Cash Flow" — already fetching this statement for FCF)
  - `retainedEarningsHistory`, `totalAssetsHistory`
- **NaN-vs-None gotcha:** trailing statement years come back as `nan`, not `None` —
  filter with `math.isnan`, exactly as `_fcf_history` does.
- Add all six fields to `compute_scores`'s `all_fields` reindex list and to
  `tests/conftest.py`'s `make_scored_row` / `make_scored_df`.
- Cost: ~1 extra yfinance call per ticker per 24h refresh (`.income_stmt`;
  `.balance_sheet` optional if retained-earnings / assets deferred).
- Doc: Stage 1 "Fields fetched" + the "no full multi-year financial-statement
  history" note (now partially false).
- Effort: **M**

### WS-11 — Sector-relative / PEG-adjusted PE fair value *(review 2.2)*

- In `compute_scores`, before the `_fair_value_models` apply, build a sector P/E map
  from the universe itself: `df.groupby("sector")["trailingPE"].median()`, only for
  sectors with ≥ `MIN_SECTOR_SAMPLE` (5) non-null P/Es; winsorize each median to
  `PE_MULTIPLE_BAND = (6.0, 30.0)`.
- Pass the map into `_fair_value_models` as an optional arg (default `None` → falls
  back to `PE_MULTIPLE_FALLBACK = 15.0`, so direct callers and existing tests are
  unchanged).
- `multiple = sector_median or 15.0`; optional PEG tilt:
  `multiple *= clamp(1 + earningsGrowth, 0.7, 1.5)` (bounded so a hyper-growth name
  can't explode the fair value).
- `trailingPE` and `sector` are already fetched — **no new data**.
- Tests (`test_algorithms.py`): thin sector → 15.0 fallback; populated sector → uses
  median; PEG bounds hold. Update the two existing fixtures that assume `eps*15` to
  reference `PE_MULTIPLE_FALLBACK`.
- Doc: Stage 2 PE row.
- Effort: **S–M**

### WS-12 — Graduated DDM weighting *(review 2.4 — kill the 89%/91% cliff)*

- Replace the binary `ddm_eligible` with `_ddm_weight_factor(div_rate, payout) →
  float ∈ [0,1]`:
  - `0` for a non-payer;
  - piecewise on payout: `0` at ≤5%, ramp to `1.0` over 5→30%, flat `1.0` over
    30→70%, ramp `1.0→0` over 70→95%, `0` above.
- Effective weights: `W_DDM_SINGLE * factor`, `W_DDM_MULTI * factor`, fed into the
  `candidates` list. The existing `w > 0` filter in `avail` still drops them cleanly
  when `factor == 0`, so today's exclusion behaviour is just the `factor == 0`
  endpoint — no discontinuity anywhere else.
- `ddm_contributed` logic unchanged in spirit (true if a weighted variant entered
  `avail`).
- Tests: payout 0.89 vs 0.91 now differ by a small delta, not all-or-nothing; payout
  0.50 identical to today; non-payer still 0.
- Doc: Stage 2 "DDM eligibility gate" — it already references "the graduated 30–50%
  weighting scheme described in earlier drafts"; this closes that gap, so rewrite
  that paragraph.
- Effort: **S**

### WS-13 — Analyst target: dispersion + coverage conditioning *(review 2.1)*

- Add `targetHighPrice`, `targetLowPrice`, `numberOfAnalystOpinions` to
  `VALUATION_FIELDS`.
- Effective analyst weight = `W_ANALYST × dispersion_factor × coverage_factor`
  (the 10% haircut stays on top):
  - `dispersion_factor`: `1.0` when `(high−low)/mean ≤ 0.20`, ramping down to ~`0.3`
    as the spread widens past ~0.8.
  - `coverage_factor`: `clamp(n_opinions / 8, 0.3, 1.0)`.
- Lower the base `W_ANALYST` from 0.208 toward **~0.13** (the review's "10–12%"
  target) and redistribute the freed ~0.08 to `W_EPV` / `W_GRAHAM` (fundamental
  anchors). Re-document the "weights sum to 1.00" set.
- Tests: wide-dispersion name gets materially less analyst pull; thin coverage
  downweights; a sum-to-1 invariant test; update the analyst-weight math in
  `test_algorithms.py` (already constant-referenced per round-1 item 9 — keep it
  that way).
- Doc: Stage 2 analyst row + weight table + Algorithm Summary.
- Effort: **M**

### WS-14 — Absolute-anchored composite sub-scores *(review 5.1)*

- New `_abs_band(value, breakpoints) → 0–100` with linear interpolation. Absolute
  bands per dimension:
  - **MoS:** <0 → 0, 0–10% → 40, 10–25% → 70, >25% → 100.
  - **Quality / Momentum / Dividend** raw 0–10 → ×10 directly.
  - **Risk** raw 0–10 (higher = riskier) → `(10 − raw) × 10`.
- Blend with the existing percentile rank:
  `sub_final = BLEND_PCT × pct_rank + (1 − BLEND_PCT) × abs_band`,
  `BLEND_PCT = 0.5` (new constant; a natural future Settings slider).
- Effect: a universe where every stock is overvalued now produces uniformly low MoS
  sub-scores instead of a spread that still tops out at 100. Complements — doesn't
  replace — the `small_universe` flag.
- Tests: degenerate all-negative-MoS universe → no Strong Buy; large healthy
  universe → behaviour close to today at `BLEND_PCT=0.5`; interpolation boundaries.
- Doc: Stage 5 (currently describes pure percentile ranking).
- Sequencing note: do this *after* the quick wins so it's tuned against an
  already-improved baseline, not the current one.
- Effort: **M**

### WS-15 — Trend-based hard vetoes *(review 6 — depends on WS-10)*

- `_trend_veto(row) → (bool, reason)`, same structure as `_fcf_hard_veto`. Each
  sub-check requires ≥3 years of the relevant series, else it's skipped (recent
  IPOs / failed fetches don't get vetoed for missing data):
  - **Revenue decline** — 3 consecutive YoY drops in `revenueHistory`.
  - **EBIT collapse** — `ebitHistory` negative 3 consecutive years (proxy for the
    interest-coverage-trend the review asks for; a true coverage trend needs
    interest-expense history, a later add).
  - **Retained-earnings erosion** — `retainedEarningsHistory` negative *and*
    declining 3 years (accumulated-deficit spiral).
  - **Standalone dividend cut** — `dividend_last_cut_year` within the last 2 complete
    years *and* `dividendCoverage < 1.5` — promotes today's flag-only signal to a
    veto.
- Fold into `compute_scores`'s `_hard_veto` OR-chain and `df["veto"]`.
- **Mandatory in the same commit:** update `uvalu/components.py::veto_reason_str()`
  *and* `uvalu/pages_/analysis.py`'s "Hard-veto checks" panel. This exact veto-UI
  drift has been fixed three times (rounds 3–4). Re-derive each panel row's boolean
  from the real `_hard_veto` formula from scratch; add regression tests in
  `test_components.py` + `test_pages_analysis.py`.
- Doc: Stage 6 hard-veto list + Algorithm Summary diagram.
- Effort: **M–L**

### WS-16 — Earnings-quality accrual term *(review 4.2)*

- Extend `scoring._earnings_quality_score` with a Sloan-style accrual ratio:
  `accr = (netIncome − cfo) / totalAssets` (falls back to
  `(netIncome − freeCashflow) / totalAssets` if CFO history isn't available). Map
  `accr ≤ 0 → 10`, `accr ≥ 0.15 → 0`, linear between; append to the existing blended
  `scores` list.
- Every new field read through `scoring._get_num` — a bare `is not None` here
  silently reintroduces the NaN corruption that round 2 fixed across all 8 scorers.
- Needs `totalAssets` (point-in-time is enough for a first cut; WS-10 gives the
  multi-year version). `netIncome` and `freeCashflow` already present.
- Tests (`test_scoring.py`): high-accrual firm scores lower; missing `totalAssets` →
  term skipped, dimension not NaN.
- Doc: Stage 4 earnings-quality row.
- Effort: **S**

### WS-17 — Beta de-noising in the screener *(review 4.1)*

- **Cheap, universal:** Blume adjustment in `_approx_wacc` and `_market_risk_score`
  — `beta_adj = 0.67·beta + 0.33·1.0` applied after the existing `[0.1, 5.0]` clamp.
  New constant `BLUME_WEIGHT = 0.67`. This alone removes most of the "unstable
  backward-looking beta" problem for the whole ~1500-ticker universe at zero data
  cost.
- **Optional, richer:** for portfolio + watchlist tickers only (the
  `PORTFOLIO_FETCH` lane), regress a 3-year weekly beta via
  `marketdata.price_history` against `^STOXX50E`, reusing `risk._ols_beta` /
  `_resolve_betas` (hoist them to `scoring.py` or a small shared `betas.py`). Store
  as `regressed_beta`; `_approx_wacc` / `_market_risk_score` prefer it when present.
  The screener universe stays on Blume-adjusted yfinance beta — regressing 1500
  tickers is too heavy.
- Tests: Blume math; regressed beta preferred when present; fallback path intact.
- Doc: Stage 2 WACC note + Stage 4 market-risk row.
- Effort: **S** (Blume) / **M** (regressed)

### WS-18 — Investment-style weight presets *(review 3.1 / 5.2 — optional, do last)*

- `settings` shared key `screen_style ∈ {balanced, value, growth, income}`, each
  mapping to a `(W_MOS, W_RISK, W_QUALITY, W_MOMENTUM, W_DIVIDEND)` vector (all
  summing to 1.0). `balanced` = the module constants (`0.30/0.18/0.22/0.15/0.15`
  at the time of this plan; later rebalanced to `0.24/0.22/0.24/0.15/0.15` per
  review 4.2 / 5.2); `value` lifts MoS+Quality, `income` lifts Dividend, `growth`
  lifts Momentum+Quality and cuts MoS.
- New `settings.get_score_weights()` alongside `get_veto_thresholds()`, threaded
  into `compute_scores(..., weights=...)` (default keeps the module constants).
- UI in Settings → Screening & veto rules — keep it **admin-gated** (that section
  was locked to admins per the `settings-page-fixes` history).
- Answers the "MoS overpowers fundamentals" critique without hardcoding a new bias —
  the user picks the lens.
- Tests: each preset sums to 1.0; `income` ranks a healthy REIT above a growth name
  that `balanced` prefers; AppTest for the settings control.
- Effort: **M**

---

## 3. Sequencing

```
WS-10  (enabler — statement history)         -- do first
   |
   +-- WS-11  sector/PEG PE           -+
   +-- WS-12  graduated DDM            |  independent quick wins,
   +-- WS-16  accrual term             |  land in any order
   +-- WS-17  Blume beta              -+
   |
   +-- WS-13  analyst dispersion         (independent, medium)
   |
   +-- WS-15  trend vetoes              (needs WS-10)
   |
   +-- WS-14  absolute-anchored composite (after the quick wins,
                                           so it's tuned vs the new baseline)

WS-18  style presets                     (last, optional)
```

Rough effort: WS-10 M · WS-11 S–M · WS-12 S · WS-13 M · WS-14 M · WS-15 M–L ·
WS-16 S · WS-17 S/M · WS-18 M.

---

## 4. Cross-cutting constraints (every workstream)

1. **NaN-vs-None:** any new optional numeric field read inside a `df.apply` scorer
   goes through `scoring._get_num`. A bare `is not None` / `x or default` silently
   reintroduces the corruption fixed across all 8 scorers in round 2
   (`nan-vs-none-dataframe-rows`).
2. **yfinance statement rows are `nan`, not `None`** for missing years — filter with
   `math.isnan`, like `_fcf_history`.
3. **Veto UI drift:** every change to `_hard_veto` must update
   `components.veto_reason_str()` *and* `analysis.py`'s "Hard-veto checks" panel in
   the same commit, re-deriving each row's boolean from the real formula. This bug
   has recurred three times.
4. **New `compute_scores` output columns** consumed by a page must be read via
   `.get(col, default)` and added to `tests/conftest.py` fakes (`make_scored_row` /
   `make_scored_df`) — a direct index KeyErrors on pre-existing fixtures (nearly
   happened with `small_universe`).
5. **Weight constants:** don't hardcode weight literals in tests — reference the
   named constants (round-1 item 9 precedent), so re-tuning doesn't break the suite.
6. **Keep [`stock_valuation_algorithm.md`](stock_valuation_algorithm.md) in sync per
   change** (the established practice through all four fix rounds) and add each item
   to `CHANGELOG.md` `[Unreleased]`.
7. Treat the four prior review rounds as the **known-clean baseline** — re-verify
   against current code, don't re-derive.
