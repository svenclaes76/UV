# Stock Valuation Algorithm (legal-compliance version)
A systematic pipeline that estimates a model fair value for each stock in the public coverage universe and summarises the result in a descriptive model signal. The output is general information, the same for every user. It is not a personal recommendation and does not say whether anyone should buy or sell.

> **Status.** This is the legal-compliance copy of [`docs/stock_valuation_algorithm.md`](../stock_valuation_algorithm.md), aligned with *Uvalu — Legal Requirements for Launch* (Oct 2, 2026). It describes [`screener_compliant.py`](../../screener_compliant.py), the candidate replacement for `screener.py`, which is not yet wired into the app. Changes from the original spec are listed in [§ Changes from the original spec](#changes-from-the-original-spec) and reviewed in [`algorithm-compliance-review.md`](algorithm-compliance-review.md). Counsel review is pending.

This document describes the algorithm as implemented in [`screener_compliant.py`](../../screener_compliant.py) (`compute_scores()` and its helpers). It is the single source of fair value, risk and signal logic for the Screener, Analysis, Portfolio, Risk and Dashboard pages. Thresholds marked **(configurable)** below are **shared, admin-only** model settings under Settings → Screening & veto rules (`settings.get_veto_thresholds()`). Every user sees signals computed with the same settings (PER-2). The values shown are the shipped defaults. The same card carries a **Screening style** picker (`settings.get_score_weights()`) that swaps the Stage 5 composite weights; see Stage 5. The live values of every threshold and weight are published on the methodology page, which is generated from `screener_compliant.methodology()` so it cannot drift from the code (REC-5).

> The 0–10 fundamental scorers `_financial_health_score`, `_earnings_quality_score` and `_dividend_sustainability_flag` (plus `_clamp` / `_get_num`) live in [`scoring.py`](../../scoring.py) and are shared with the portfolio risk engine. Stage 1 (data collection and the fetch cache) is imported unchanged from [`screener.py`](../../screener.py).

### Data source and licensing (DATA-1 to DATA-6)

All inputs currently come from Yahoo Finance via `yfinance` (`screener_compliant.DATA_SOURCE`). That source is very likely **not licensed** for a paid, multi-user service; this is a launch blocker (requirements §9). Once a provider contract is signed, `DATA_SOURCE` must carry its name and required attribution, and every scored row repeats it in its `data_source` column. **Analyst estimates are excluded** until a licence covers them; see Stage 2.

---
## Stage 1 — Data Collection
A mostly point-in-time snapshot per ticker via `yfinance`, cached to `.cache/fundamentals.json` and refreshed every ~24h ± 4h jitter per ticker (`screener._fetch_one`). Several multi-year series are pulled per ticker on each refresh:
- **Annual Free Cash Flow**, up to ~4-5 years from the cash flow statement (`fcfHistory`, `screener._fcf_history`) — feeds the hard veto and the earnings-quality consistency check below.
- **Annual income-statement / balance-sheet / cash-flow lines** (`screener._statement_history`), most recent fiscal year first, ~4 years as yfinance exposes them: `revenueHistory`, `ebitHistory`, `netIncomeHistory`, `cfoHistory`, `retainedEarningsHistory`, `totalAssetsHistory`. Each is `None` when the statement fetch fails or the row isn't exposed (some ADRs, recent IPOs), and callers fall back to the point-in-time field. Feeds the trend-based hard vetoes, the accrual term in earnings quality, and a normalised EPV.
- **Dividend payment history** (`marketdata.dividends`, disk-cached at `.cache/dividends/{ticker}.csv`, weekly refresh), reduced by `screener._dividend_stats` to `true_dgr` (annual-DPS CAGR over a ~6yr window), `dividend_growth_streak`, `dividend_payment_years` and `dividend_last_cut_year`.

There is a partial multi-year financial-statement history (the lines listed above, ~4 years each — not a full filing history), but still no peer/comparable-company dataset and no external macro feed. The risk-free rate and equity risk premium are fixed constants (3% and 5% — `screener.RISK_FREE_RATE`, `EQUITY_RISK_PREMIUM`), not live indicators. EPV's tax rate is country-aware (`screener.COUNTRY_TAX_RATES`, keyed on the already-fetched `country` field) but still a static table of headline statutory rates, not a live feed; unmapped or missing countries fall back to `DEFAULT_TAX_RATE` (25%).

**Fields fetched:**
- Price, EPS (`trailingEps`), book value per share (`bookValue`)
- Dividend rate (`trailingAnnualDividendRate` / `dividendRate`), 5-yr average dividend yield, ex-dividend and payment dates
- Analyst target price — mean (`targetMeanPrice`), high / low (`targetHighPrice` / `targetLowPrice`, for dispersion), and analyst count (`numberOfAnalystOpinions`, for coverage depth). **Fetched but not used** while `ANALYST_INPUTS_ENABLED` is off (DATA-6).
- EBIT, enterprise value, shares outstanding, plus `totalDebt` / `totalCash` / `marketCap` (FV-4: to rebuild enterprise value when the provider drops it)
- Debt/equity, current ratio, interest coverage, free cash flow (current + up to ~4-5yr history via `fcfHistory`), net income, beta, average volume, payout ratio
- ROE, ROA, operating margin, profit margin
- Earnings growth, revenue growth, analyst recommendation mean (the last **not used** while `ANALYST_INPUTS_ENABLED` is off)
- Sector, country, quote currency
- Multi-year statement history → `revenueHistory`, `ebitHistory`, `netIncomeHistory`, `cfoHistory`, `retainedEarningsHistory`, `totalAssetsHistory` (`screener._statement_history`)
- Dividend history → `true_dgr`, `dividend_growth_streak`, `dividend_payment_years`, `dividend_last_cut_year` (`screener._dividend_stats`)

EV/EBITDA is fetched but **display-only**. Trailing P/E is display-only per row, but its **sector median across the screened universe** sets the PE Fair Value multiple (Stage 2). Price-to-book is display-only for a normally-valued stock, but its **sector median** feeds the FV-3 book-value fallback below when a stock has no earnings anchor.
---
## Stage 2 — Fair Value Estimation (Multi-Model)
Six core models are defined; the composite is a weighted average of whichever produced a positive value (`screener_compliant._fair_value_models`).

> **Analyst model off by default (DATA-6).** Sell-side price targets and the consensus recommendation mean are licensed separately from prices and fundamentals. While `screener_compliant.ANALYST_INPUTS_ENABLED` is `False`, the analyst model is dark for every stock (`fv_dark_reasons["analyst"] = "not_licensed"`). Its weight drops out, and the blend re-normalises over the remaining models exactly as it does for a stock without analyst coverage. In effect **five** core models run. Wherever the text below mentions the analyst model or "six models", it applies only once a licence is in place and the switch is turned on. The UI must not show the raw `targetMeanPrice` either while the switch is off. Two further **fallback** models (book value, FCF) join the blend **only** for a stock where none of the three earnings-anchored core models (Graham / PE / EPV) could be computed — see "Fallback models" below.

### Models
| Model | Formula / Approach | Base weight |
|---|---|---|
| **Graham Number** | `√(22.5 × EPS × BVPS)` — requires positive EPS and BVPS. **FV-8: skipped for `Real Estate` and `Financial Services`** (`_GRAHAM_EPV_SKIP_SECTORS`, matched on the *resolved* sector — `sector_for()`, so a provider-null REIT still counts) — a REIT's EPS carries IFRS fair-value revaluation gains, a bank/insurer has no industrial "earnings power". Banks then value off P/E + **P/B** + DDM + analyst (the book-value model is a primary anchor for that cohort, not just a loss-maker fallback); REITs off P/B + DDM + analyst. **Also skipped when `Price / BVPS < PTB_SANITY_FLOOR`** (0.02, per-share input sanity floor, below) regardless of sector. | 0.178 (`W_GRAHAM`) |
| **PE Fair Value** | `EPS × m`, where `m` is the median trailing P/E of the stock's own **sector** across the current screened universe (`screener._sector_pe_medians`), winsorized to `PE_MULTIPLE_BAND` (6–30×), then multiplied by a bounded PEG tilt `clamp(1 + earningsGrowth, 0.7, 1.5)` (`PEG_TILT_BAND`). Falls back to a flat `PE_MULTIPLE_FALLBACK` (15×, the value used unconditionally before this) when the sector has fewer than `MIN_SECTOR_SAMPLE` (5) priced peers, or when `trailingPE`/`sector` aren't in the frame (pre-WS-10 caches, direct callers). The 15× fallback is *not* Graham's no-growth base multiplier (8.5×) — just a round heuristic near the long-run market-average P/E. **FV-8: skipped for `Real Estate`** (`_PE_SKIP_SECTORS`) — revaluation-distorted EPS; banks/insurers keep it. **Also skipped when `Price / BVPS < PTB_SANITY_FLOOR`**, same guard as Graham above — despite being an EPS-anchored model, not a book-value one (see the guard's own rationale below). | 0.150 (`W_PE`) |
| **Earnings Power Value (EPV)** | `EPV_EV = EBIT × (1 − t) / WACC`, where **EBIT is a robust central value of `ebitHistory`** (`screener._normalised_ebit`, ≥ `_EBIT_MIN_YEARS` = 3 finite years): the **median** at exactly 3 years, a **symmetric trimmed mean** (drop the min and the max, average the rest) at 4+. This removes a lone crisis (a one-off multi-billion writedown) or windfall year without the MAD-based rule's failure of flagging a fast grower's newest, most-relevant year as the "outlier" (FV-2, review). Fewer than 3 finite years → point-in-time `ebit` (recent IPOs / failed statement fetches). Converted to per-share as `(EPV_EV − NetDebt) / SharesOutstanding` where `NetDebt = EnterpriseValue − (Price × SharesOutstanding)` — subtracts actual net debt directly rather than assuming EPV_EV's implied capital structure mirrors the market's EV/market-cap ratio; falls back to the `Price × (EPV_EV / EnterpriseValue)` EV-ratio shortcut when `sharesOutstanding` is unavailable. **`EnterpriseValue` itself** (FV-4) is the provider's `enterpriseValue` when positive, else reconstructed as `(marketCap or Price × shares) + totalDebt − totalCash` (`screener._enterprise_value`, `ev_source` records which) — yfinance drops `enterpriseValue` on a partial payload while keeping the balance-sheet legs; when the EV was reconstructed, `NetDebt` is taken straight from `totalDebt − totalCash` so a multi-class `marketCap` leg can't inject phantom debt (review). A per-share EPV that comes out **≤ 0** (net debt exceeds the capitalised earnings power — routine for leveraged names) is kept out of the blend by the `> 0` filter but sets **`epv_negative`** so the UI can explain the gap. `t` is the country's statutory corporate tax rate from the static `COUNTRY_TAX_RATES` table (e.g. 21% US, 30% Germany, 12.5% Ireland), falling back to 25% when `country` is missing or unlisted. **FV-8: skipped entirely for `Real Estate` and `Financial Services`** — a Greenwald EPV needs an operating EBIT that neither cohort has. | 0.208 (`W_EPV`) |
| **DDM — single-stage** | Gordon growth: `D₁ / (WACC − g)`, `g` = the true DPS CAGR (`_dgr_estimate`, FV-7), clamped to 0–5% **and further to `WACC − DDM_MIN_SPREAD`** so the denominator floors at 3 pp — a low-beta payer keeps the model with a conservative growth assumption rather than losing it silently (review). Dropped only when WACC itself is ≤ `DDM_MIN_SPREAD` | 0.167 (`W_DDM_SINGLE`) × payout ramp |
| **DDM — multi-stage** | 5-year explicit high-growth phase (`g_high` = the same DPS CAGR, clamped to `min(15%, WACC − DDM_MIN_SPREAD)` so the explicit terms can't compound above the discount rate — review) + Gordon terminal value (terminal g = 2%). Dropped when `WACC − 2% < DDM_MIN_SPREAD` | 0.167 (`W_DDM_MULTI`) × payout ramp |
| **Analyst target price** *(only with `ANALYST_INPUTS_ENABLED`, DATA-6)* | `targetMeanPrice × (1 − 10%)` — a flat haircut (`screener.ANALYST_TARGET_HAIRCUT`) applied before it feeds the composite, to discount sell-side targets' well-documented optimism bias. The undiscounted `targetMeanPrice` is still what the drawer / Analyst "Six-model" ladder row shows (only the model *input* is haircut); FV-6 adds a caption there — "the composite applies a −10% haircut to the Analyst Target shown" — so the printed row and the composite reconcile. | 0.130 (`W_ANALYST`) × dispersion & coverage factor |

#### Fallback models (FV-3) — only when Graham, PE **and** EPV all failed

Both are crude anchors, present in the blend only for a stock with no earnings-anchored value at all: a loss-maker with negative/absent EPS and an EPV that couldn't run, **or** (FV-8) any `Real Estate` / `Financial Services` name — the earnings trio is skipped there, so `_trio` is 0 and the **book-value** model (a NAV proxy) becomes the primary valuation, alongside DDM and analyst. A single live core model leaves them dark, so a normally-valued stock's composite is unchanged. Their weights sit **outside** the six-model sum (they are conditionally applied, like the DDM payout ramp).

| Model | Formula / Approach | Weight |
|---|---|---|
| **Book value** | `bookValue × m`, `m` = winsorized (`PB_MULTIPLE_BAND` 0.5–4.0) sector-median `priceToBook` across the screened universe (`screener._sector_pb_medians`), or `PB_MULTIPLE_FALLBACK` (1.5) for a sector with < `MIN_SECTOR_SAMPLE` peers. **Also skipped when `Price / BVPS < PTB_SANITY_FLOOR`**, below — the model FV-8 makes a *primary* NAV anchor for banks/REITs is exactly the one this guard has to reach too. | 0.10 (`W_PB`) |
| **FCF value** | `(freeCashflow × FCF_MULTIPLE − NetDebt) / SharesOutstanding`, `FCF_MULTIPLE` = 15 (≈ 6.7% FCF yield, fixed — not `1/(WACC−g)`), `NetDebt = EnterpriseValue − Price×Shares` (same as EPV); guarded on `freeCashflow > 0` | 0.10 (`W_FCF`) |

In the drawer / Analysis "Six-model fair value" ladder these do **not** add rows — when they fire, whichever produced a value is slotted into the first dark Graham / PE / EPV row and relabelled "Book value" / "FCF value" (`components.six_model_ladder_rows`), so the ladder stays six rows.

`DCF`, comparable multiples (EV/EBITDA, P/S), and a peer/comps dataset are still **not implemented**.

**Per-share input sanity floor (`PTB_SANITY_FLOOR` = 0.02).** `bookValue` and
`trailingEps` are both scaled by the same `sharesOutstanding` figure for a
given row, so an implied `Price / bookValue` this far below the market's own
price is evidence that basis is broken for the *whole* row — either a data
defect (a secondary/cross-listing whose per-share fundamentals were computed
off a different share count or class than the one actually priced) or a
genuine structural mismatch (a central-bank-style issuer whose legally capped
dividend breaks the standard proportional-equity-claim assumption these
models rely on). When it fires, Graham, PE Fair Value, and the Book value
model are all held dark for that row, regardless of sector — deliberately
P/B-only, not a symmetric P/E floor: `trailingEps` is a flow figure that
legitimately swings on ordinary earnings volatility (a real one-off gain can
push implied P/E below 1 with nothing wrong), while `bookValue` is
comparatively stable, so an implausible P/B is a much cleaner standalone
signal. Found via the Swiss National Bank (`SNBN.SW`): only 100,000 shares
outstanding against a genuinely enormous balance sheet produces a bookValue
and trailingEps per share in the hundreds of thousands, feeding a >CHF 6M
"fair value" against a ~CHF 3,140 price — while the market price correctly
reflects that the National Bank Act caps the dividend shareholders can
receive, so book value/earnings per share don't translate to a proportional
equity claim at all.

**WACC** = 3% risk-free rate + beta × 5% equity risk premium. A raw beta outside [0.1, 5.0] (or missing/NaN) is rejected and defaults to 1.0; an in-band beta is **Blume-adjusted** — shrunk two-thirds of the way toward the market beta of 1.0 (`0.67 × raw + 0.33 × 1.0`, `screener.BLUME_WEIGHT` / `_adjust_beta`) — since yfinance's trailing single-estimate beta is noisy and mean-reverts.

**DDM payout ramp:** both DDM base weights are multiplied by `screener._ddm_weight_factor(div_rate, payout)`, a continuous factor in `[0, 1]` keyed on a payout ratio (`_DDM_PAYOUT_KNOTS = 0.05 / 0.30 / 0.70 / 0.95`): **0** for a non-payer or a payout at/below 5% or at/above 95%, **1.0** (full base weight) across the 30–70% comfortable band, and a **linear ramp** on each shoulder in between. It is continuous at every knot, so there is no cliff anywhere in the payout range — an 89%-payout payer and a 91%-payout payer differ by a sliver of DDM weight, not the whole ≈0.334 combined block (this replaces the earlier hard 5–90% in/out gate, itself a replacement for a still-earlier "graduated 30–50%" scheme). Whatever DDM weight is not used drops out and the remaining available models (Graham, PE, EPV, Analyst) are re-normalized over their own weights, since there is no DCF or comps model to receive it instead.

The `payout` fed to the ramp is **not** the raw reported field — it is `screener._payout_signal(row)` (FV-1). yfinance's `payoutRatio` divides by trailing GAAP net income, so for a loss-making, trough-earnings or freshly-demerged payer it returns an absurd value (1.4×, 7.7×), a negative, or null — and *any* value outside `[0, 0.95]` collapses the whole DDM block. `_payout_signal` trusts the reported ratio only while it sits in `[0, _DDM_PAYOUT_KNOTS[3]]` (the regime where the GAAP denominator is sound), then falls back to the **cash payout ratio** (`cashPayoutRatio` = DPS × shares / FCF, ≤ `_PAYOUT_CASH_MAX` = 1.5), then to **1 / dividend coverage** (`1 / (EPS/DPS)`); only when no proxy is available does it surface the extreme reported value so the ramp still zeroes it. Which source was used is recorded on the scored row as **`payout_source`** (`reported` / `cash` / `coverage` / `none`). The dividend **risk** and **sustainability** scores (Stage 3–4) are unaffected — they still read the raw `payoutRatio` directly.

**Analyst dispersion & coverage factor:** the analyst weight is `W_ANALYST × _analyst_weight_factor(row)`, itself the product of two multipliers, each `1.0` when its input is missing (an absent field never penalizes):
- **dispersion** — from `spread = (targetHighPrice − targetLowPrice) / targetMeanPrice`: `1.0` while `spread ≤ 0.20` (`_ANALYST_SPREAD_TIGHT`), then a linear ramp down to `0.30` (`_ANALYST_DISPERSION_FLOOR`) at `spread = 0.80` (`_ANALYST_SPREAD_WIDE`), staying at the floor for any wider spread. Wide disagreement among analysts ⇒ the mean target carries less information.
- **coverage** — `clamp(numberOfAnalystOpinions / 8, 0.30, 1.0)` (`_ANALYST_COVERAGE_FULL` / `_ANALYST_COVERAGE_FLOOR`). A target built from one or two analysts is downweighted toward the floor.

The six **core** base weights (`W_GRAHAM`, `W_PE`, `W_EPV`, `W_DDM_SINGLE`, `W_DDM_MULTI`, `W_ANALYST`) sum to exactly **1.00**. They were originally 0.18/0.18/0.19/0.20/0.20/0.25 (a stale sum of 1.20), rescaled to 0.150/0.150/0.158/0.167/0.167/0.208, then — since sell-side targets are optimism-biased and slow to react to regime changes — the analyst weight was cut to **0.130** and the freed ≈0.078 handed to the two most fundamentals-anchored models: `W_EPV` 0.158 → **0.208** and `W_GRAHAM` 0.150 → **0.178**. The FV-3 fallback weights (`W_PB`, `W_FCF`, 0.10 each) are **not** part of this sum — they are 0 unless the fallback is both eligible (no core model fired) and produced a value, at which point the composite re-normalises over whatever is in `avail` exactly as it does for a conditionally-absent DDM.

### Dividend-Specific Valuation Checks
| Check | Formula | Where it's used |
|---|---|---|
| **Payout ratio** | `payoutRatio` (as reported) | Dividend sustainability flag, dividend risk/score |
| **Cash payout ratio** | `(DPS × Shares) / FCF` | Dividend sustainability flag, dividend risk/score |
| **Dividend coverage ratio** | `EPS / DPS` | Dividend sustainability flag, dividend risk/score, hard veto |
| **Dividend growth rate (DGR)** | `screener._dgr_estimate(row)` — the **true DGR** below when the dividend history has ≥2 complete years, else the `earningsGrowth` (TTM) proxy. A real `0.0` (flat DPS) wins over the proxy. Used in the implied return, dividend risk score, dividend score | Implied return, dividend risk/score |
| **Dividend yield vs. historical average** | `dividendYield / fiveYearAvgDividendYield`, feeds the dividend score | Dividend score |
| **Dividend yield vs. sector peers** | *Not implemented* — no peer-median dataset exists | — |
| **True DGR** `(DPS_t / DPS_{t-n})^(1/(n-1)) − 1` | **Implemented** (`screener._dividend_stats.true_dgr`) — CAGR of annual DPS across the complete calendar years in a ~6yr window (the incomplete current year is dropped); `None` with fewer than 2 such years | DGR estimate above |

### Weighted Composite Fair Value
```
Intrinsic Value = Σ (Model weight × Model fair value) / Σ (Model weight)
```
summed over whichever models produced a value for that stock; the weighted average becomes the **model fair value** (`fair_value` column).

**Presentation (REC-2, REC-6).** The fair value is a model estimate, not a fact or a price target. Wherever it is shown, it is labelled "Model fair value (estimate)" and sits next to the model values that fed it, the number of independent models (`fv_model_count`) and its data flags (Stage 6). The methodology page carries the key assumptions, read from the live constants: risk-free rate, equity risk premium, terminal growth, the P/E fallback and band, and the FCF multiple. It also carries the sensitivity note (`SIGNAL_SENSITIVITY`): with a 2% growth rate, raising the discount rate from 8% to 9% lowers a dividend-model fair value by about 14%.
---
## Stage 3 — Margin of Safety & Model-Implied Return
### Margin of Safety (MoS)
```
MoS = (Fair Value − Price) / Fair Value
```
There is no fixed 20–30% band on MoS itself. Instead, the **Undervalued** signal additionally requires MoS to clear a configurable minimum (`min_mos`, default **0%**); see Stage 6. *Recommendation:* at the 0% default, a price 0.5% below the model fair value can be labelled "Undervalued". Raise the shared default to about 10% before launch so that the label stays meaningful.

### Model-Implied Return (estimate)
```
Implied Return % (est.) = Gap to model fair value % + Forward dividend yield % + Assumed DGR %
```
where Gap to model fair value % = `(Fair Value − Price) / Price × 100`, and Assumed DGR is `_dgr_estimate` (true DPS CAGR when available, else the `earningsGrowth` proxy) clamped to 0–10%. It is published as the column `Implied Return % (est.)` (formerly `TER %`, "Total Expected Return"). It is a model estimate that holds only if the model fair value is right and the dividend assumptions hold. **It is not an expected or promised return** (REC-2, DIS-5). It is never classified into bands such as "Attractive / Acceptable / Unattractive", and it must not be used in marketing.

**DGR halving when DDM contributed:** if either DDM variant fed that stock's composite fair value (`ddm_contributed`), the Assumed DGR term is halved before summing. In that case growth is already embedded in the gap term through the DDM-derived fair value, so adding the full DGR proxy on top would double-count it.

### Dividend Sustainability Flag
`scoring._dividend_sustainability_flag` (re-exported from `screener`) returns `"At Risk"`, `"OK"`, or `""` (non-payer). **Any** of:
- Payout ratio > 90% **(configurable, `max_payout`)** → **At Risk**
- Cash payout ratio > 80% → **At Risk**
- Dividend coverage ratio < 1.2× → **At Risk**
- **DPS cut within the last 3 complete years** — `dividend_last_cut_year ≥ current_year − 3` (`scoring._DIV_RECENT_CUT_YEARS`). This is the spec's fourth check, now implemented off the dividend history.

There is still no automatic **+5–10pp MoS bump** for flagged stocks; a flagged stock passes the same `min_mos` threshold as any other. Note that "At Risk" + coverage < 1.0× is a hard veto (Stage 6), so a recent DPS cut on a thinly-covered payer now vetoes.
---
## Stage 4 — Risk, Quality, Momentum, and Dividend Scoring
The composite **risk** score averages **five** dimensions (0–10 each, higher = safer) and inverts the result — not the seven dimensions described in earlier drafts. Quality and Momentum are computed as separate top-level 0–10 scores, not risk sub-dimensions.

| Dimension | Key metrics | Part of |
|---|---|---|
| **Financial health** | Debt/equity, current ratio, interest coverage | Risk |
| **Earnings quality** | FCF-to-net-income conversion **blended with** `fcfHistory` consistency (fraction of positive years + level stability via coefficient of variation, when ≥3 years) **and** a Sloan **accrual ratio** `(netIncome − operating cash flow) / totalAssets` from the latest `cfoHistory` / `totalAssetsHistory` year (falls back to `freeCashflow` for CFO; skipped when total assets are unavailable) — large positive accruals score low. Any subset of the three that has inputs is averaged; conversion ratio alone otherwise, then neutral 5.0 | Risk |
| **Market risk** | Beta, **Blume-adjusted** (shrunk toward 1.0 — same `_adjust_beta` as WACC) so a noisy trailing estimate can't swing the dimension as hard | Risk |
| **Dividend risk** | Payout ratio, cash payout ratio, dividend coverage, DGR (`_dgr_estimate` — true DGR when available, else `earningsGrowth`) | Risk |
| **Liquidity** | Average daily volume — a confirmed 0 scores worst-case (0/10), a missing value stays neutral (5/10); a confirmed 0 also forces the Stage 6 hard veto, see above | Risk |
| **Quality** | ROE, ROA, operating margin, FCF yield, current ratio | *Separate score* |
| **Momentum** | Earnings growth, revenue growth (+ analyst recommendation mean only with `ANALYST_INPUTS_ENABLED`, DATA-6) | *Separate score* |

`Momentum`'s analyst component (`recommendationMean`), when licensed and enabled, is a current-snapshot rating, not a trend of analyst revisions over time. A **Qualitative dimension** (competitive moat, management track record, ESG flags) is **not implemented** — there is no data source for it, so the risk composite has no room reserved for it.

The **Dividend score** (separate from dividend risk, feeds Stage 5 directly) combines: yield vs. 5-yr average, payout ratio safety, cash payout ratio, dividend coverage, and `_dgr_estimate` (true DGR when available, else the `earningsGrowth` proxy) — non-payers get a neutral 5.0 so they're neither rewarded nor penalized.
---
## Stage 5 — Composite Score
Before weighting, MoS, Risk, Quality, Momentum and Dividend are each turned into a **0–100 sub-score** (`screener._blend_ranks`, higher = better for all five), a blend of two views of the same value:
- **Cross-sectional percentile rank** (`screener._pct_rank`): the stock's standing *within the public peer universe*, meaning every enabled exchange together (a shared setting). NaN rows get a neutral 50. **The peer universe never depends on the user (PER-1, PER-2):**
  - Only rows marked by `peer_mask` (built with `peer_mask_for(df, public_tickers)` from the enabled exchanges' ticker lists) set the sector P/E and P/B medians and the rank distributions. Rows a user added (manual tickers, holdings on a disabled exchange) are scored *against* those peers without moving them. The original spec put "portfolio holdings on disabled exchanges", and in the code each user's manual tickers, into the universe itself, so one user's additions shifted everyone's scores.
  - Holdings and watchlists scored by the portfolio lane are ranked against the same public universe through its `ScoreReference`, so a stock gets the same score and signal on every screen and for every user.
  - A user-selected set scored **without** a reference (`user_selected=True`, e.g. before the first universe build) is **not** ranked among itself, as the original spec allowed. Its rows get signal **No signal** (`pending`) and no composite score. Fair values (not rank-based) and quality-screen failures (absolute rules) are still shown.
- **Absolute band** (`screener._abs_band`) — the same value mapped through a fixed piecewise-linear scale, independent of the universe:
  - MoS: `≤ 0 → 0`, `10% → 40`, `25% → 70`, `≥ 50% → 100` (`_BAND_MOS`).
  - Quality / Momentum / Dividend: the raw 0–10 score × 10 (`_BAND_0_10`).
  - Risk: `(10 − risk_raw) × 10`, so a low raw risk scores high (`_BAND_RISK`).

`sub_score = BLEND_PCT × percentile + (1 − BLEND_PCT) × absolute_band`, `BLEND_PCT = 0.5`. Pure percentile ranking (the earlier behaviour, `BLEND_PCT = 1`) inflates a mediocre stock in a weak universe and makes MoS_rank meaningless when *every* stock is overvalued; the absolute anchor keeps the score honest in that case. It complements — doesn't replace — the small-universe flag below.
```
Score = 0.24×MoS_sub + 0.22×Risk_sub + 0.24×Quality_sub + 0.15×Momentum_sub + 0.15×Dividend_sub
```
(Risk_sub is already oriented so that safer = higher, so it's added, not subtracted.) The default weights are `screener.W_MOS` / `W_RISK` / `W_QUALITY` / `W_MOMENTUM` / `W_DIVIDEND` (`0.24 / 0.22 / 0.24 / 0.15 / 0.15` — the **balanced** style). These were rebalanced from an earlier MoS-led `0.30 / 0.18 / 0.22 / 0.15 / 0.15`: margin of safety now co-leads with quality rather than dominating, and risk is weighted more heavily, so a wide discount can't on its own outvote weak fundamentals or a poor risk profile. Settings → Screening & veto rules → **Screening style** swaps in one of four shared, admin-controlled vectors (`settings._SCORE_STYLES`, each summing to 1.0, passed to `compute_scores(weights=…)` via `settings.get_score_weights()`): *balanced*, *value* (MoS + quality lead), *growth* (momentum + quality lead, thin MoS), *income* (dividend-led). The `Sub MoS` / `Sub Risk` / … columns carry the blended sub-scores; only the final weighting changes with the style.

**Universe-size guard:** a small or low-quality universe can still let a mediocre stock rank high on the percentile half of each sub-score. `compute_scores` sets `small_universe = True` on every row when the **peer** universe has fewer than `MIN_UNIVERSE_SIZE` (20, a heuristic threshold) stocks. The row also carries the `small_peer_group` data flag, which is shown next to the signal.
---
## Stage 6 — Model Signal
The composite score is summarised in a **descriptive model signal** (BDG-1). It states where the stock sits on the model's scale; it does not say what to do. Each row carries a stable machine value `signal_code` (store and compare this) and an English display label `Signal` (shown through `tr()` in the user's language).

| Rule (first match wins) | `signal_code` | Label |
|---|---|---|
| Fails the quality screen (any hard-veto rule below) | `fails_screen` | **Fails quality screen** |
| No public peer basis (user-selected set without a reference, Stage 5) | `pending` | **No signal** |
| Score ≥ 70 **(configurable, `buy_threshold`)** *and* MoS ≥ `min_mos` (default 0%) *and* the fair value is not `fv_basis_thin` (FV-5) | `undervalued` | **Undervalued** |
| Score ≥ 40 (`SCORE_AVOID`); or ≥ 70 without a confirmed margin of safety / corroborated fair value | `neutral` | **Neutral** |
| Score < 40 | `low_score` | **Low score** |

These replace the original **Strong Buy / Monitor / Avoid** decision. A vetoed stock has its own state instead of being folded into Avoid (BDG-3), and its composite score is set to 0. A `fv_basis_thin` fair value (fewer than `MIN_FV_MODELS` (2) independent sub-models behind the composite, e.g. a lone book-value fallback) is not a quality-screen failure. It only keeps the row out of **Undervalued**, so it falls through to **Neutral** on score.

**Why not "Near fair value" / "Overvalued" for the lower bands.** The requirements' BDG-1 suggests MONITOR → "Near fair value" and AVOID → "Overvalued". Those labels would often be false: the bands come from the composite score (margin of safety + risk + quality + momentum + dividend), not from valuation alone, and a stock 30% below its model fair value with weak quality can sit in the lowest band. A label must describe what the model measured (REC-2; WER VI.97). Hence "Neutral" and "Low score". **[Counsel]** to confirm.

### What every signal is shown with (BDG-2, BDG-3, REC-3, REC-4, REC-6)
A signal is never shown on its own. The badge, or the row it sits in, carries:
- a visible **"Model signal"** header, or the qualifier "model signal" wherever the badge appears without that context (exports, emails, share cards, screenshots);
- the tooltip `SIGNAL_TOOLTIP`, *"Model output based on public data and the settings shown. Not a recommendation tailored to you."*, plus a link to the methodology page;
- the **model fair value**, the **margin of safety**, and the models behind it (`fv_model_count`);
- **`signal_computed_at`** (UTC) and **`price_as_of`** (when the price used was fetched);
- **`data_flags`**: `price_stale` (price older than `PRICE_STALE_HOURS` = 72 h), `price_missing_timestamp`, `fair_value_missing`, `fair_value_thin_basis`, `fair_value_clamped`, `eps_derived_from_pe`, `small_peer_group`;
- **`data_source`**, plus any attribution the data licence requires.

`signal_reason(row)` gives a one-line statement of the rule and figures behind the signal, e.g. *"Model score 74 is at or above 70, and the price is 18% below the model fair value (minimum 0%)."* It uses descriptive terms only: no "buy", "avoid", "advice" or second-person phrasing (DIS-6).

### Methodology, horizon and risk warning (REC-5, REC-6)
`methodology(**settings)` returns everything the public methodology page must show, read from the live constants and the active shared settings: every model and its base weight, the composite weights, the rank blend, the exact signal thresholds, every quality-screen rule, the signal definitions (`SIGNAL_DEFINITIONS`), the assumed horizon (`SIGNAL_HORIZON`: a multi-year view on current fundamentals, nothing about short-term price moves), the risk warning (`SIGNAL_RISK_WARNING`), the sensitivity note and the stale-price limit. Every badge links to that page.

### Update frequency, history and reproducibility (REC-7, REC-10, REC-11)
- **Update frequency.** Fundamentals refresh about every 24 h (± 4 h jitter per ticker, `CACHE_TTL_HOURS` / `CACHE_TTL_JITTER`), and signals are recomputed whenever the cache changes. The methodology page states this.
- **History.** After each universe build, `signal_history.record_changes(signal_records(scored))` appends one record per stock whose `signal_code` changed. Each stock page shows `history_for(ticker)`: every badge change of the last 12 months, kept for at least that long.
- **Reproducibility.** Every row and log record carries `model_version` (`MODEL_VERSION`, bumped on any change that can move a fair value, score or signal) and `model_settings_id` (a hash of the shared thresholds, weights and the analyst switch), next to the inputs and model fair values. This makes any past signal reproducible on request.
- **Distribution.** `signal_distribution(df)` gives the share of covered stocks per signal (e.g. 12% Undervalued, 55% Neutral), shown on the methodology page (REC-10).

### Hard Veto Rules (quality screen)
`compute_scores`'s `_hard_veto` is true when **any** of the following holds; the stock's signal is then **Fails quality screen**. The
static, point-in-time checks:
- Debt/equity ratio > **500%** i.e. 5.0× **(configurable, `max_debt_equity`)** — **skipped for Financial Services, Real Estate, and Utilities** (`screener.LEVERAGE_EXEMPT_SECTORS`), since high leverage is a structural feature of those business models (deposits/float, debt-financed property, capex-heavy regulated assets), not a distress signal. Other sectors are unaffected.
- Free cash flow negative for the **3 most recent consecutive fiscal years** (`fcfHistory`, from the cash flow statement's "Free Cash Flow" row, newest first — `screener._fcf_history`). Falls back to the **single most recent reported period** (`freeCashflow`) when fewer than 3 years of history are available (recent IPOs, or tickers where the statement fetch failed/doesn't expose the row) — a single bad year no longer vetoes an otherwise-sound stock on its own once 3-year history exists.
- Dividend sustainability flag is **At Risk** *and* dividend coverage < 1.0×
- **Confirmed zero average trading volume** (`averageVolume == 0`, not merely unreported) — the instrument genuinely hasn't traded (e.g. treasury shares or a dormant secondary listing sharing a company's market data with its real, actively-traded line, as with `NAITR.AS` vs `NAI.AS`). A *missing* `averageVolume` field is not evidence of no trading and stays neutral in the Liquidity risk sub-score below — only a confirmed 0 vetoes.

…and the multi-year **deterioration trends** (`screener._trend_veto`, each requiring at least `_TREND_MIN_YEARS` = 3 points of the relevant series from `screener._statement_history`; a shorter or absent series never triggers):
- **Revenue decline** — `revenueHistory` has fallen year-over-year for at least `_TREND_DECLINE_RUN` (2) consecutive years at the newest end (i.e. 3+ straight declining years).
- **EBIT collapse** — `ebitHistory` negative for the 3 most recent consecutive fiscal years (a coarse stand-in for a deteriorating interest-coverage trend, for which there's no multi-year series yet).
- **Retained-earnings erosion** — `retainedEarningsHistory` is negative in the latest year *and* has been getting more negative for 2+ consecutive years (an accumulated-deficit spiral).
- **Recent dividend cut on thin cover** — `dividend_last_cut_year` within the last `_DIV_CUT_VETO_YEARS` (2) complete years *and* `dividendCoverage` < `_DIV_CUT_VETO_COVERAGE` (1.5×). This promotes a recent DPS cut from a mere sustainability flag to a veto when the payout is also thinly covered.

Not implemented — no data source exists: active fraud investigation / accounting restatement, or an imminent covenant breach or liquidity crisis.
---
## Algorithm Summary
```
Data collection (yfinance snapshot + FCF & dividend history, 24h cache; DPS history via marketdata.dividends)
    ↓
Fair value estimation
  (Graham Number + PE Fair Value [sector-median trailing P/E × bounded PEG tilt] + EPV [on a median/trimmed-mean multi-year EBIT, EV reconstructed if the provider dropped it] + DDM single-stage + DDM multi-stage [g clamped so the Gordon denominator ≥ DDM_MIN_SPREAD] + Analyst target [only when licensed — ANALYST_INPUTS_ENABLED, off by default (DATA-6); 10% haircut, weight scaled by dispersion & coverage]; Graham/PE/EPV skipped for Real Estate / Financial Services [FV-8, NAV-driven, on the resolved sector] — those value off P/B + DDM + analyst [banks also keep P/E]; Book-value/FCF *fallbacks* otherwise fire only when none of Graham/PE/EPV did; Graham/PE/Book-value also held dark, any sector, when Price/BVPS < PTB_SANITY_FLOOR [0.02] — bookValue and trailingEps share a sharesOutstanding basis, so an implausible implied P/B taints both]
    ↓
Weighted fair value
  (base weights sum to 1.00; combined DDM weight ≈0.334 × a continuous payout
   ramp — full across 30–70% payout, tapering to 0 by 5% / 95%; the ramp reads
   _payout_signal: reported payoutRatio in [0,95%], else cash payout, else
   1/coverage; the unused part re-normalizes over Graham/PE/EPV/Analyst)
    ↓
Margin of Safety = (Fair Value − Price) / Fair Value
Implied Return % (est.) = Gap to model fair value % + Forward Yield % + Assumed DGR % (true DPS CAGR, else earnings-growth proxy) [DGR halved if DDM contributed to Fair Value] — a model estimate, not an expected return
Dividend Sustainability Flag (payout ratio, cash payout ratio, coverage ratio, DPS cut in last 3 complete years)
    ↓
Risk scoring (5 dimensions; earnings quality blends FCF-history consistency + a Sloan accrual ratio, dividend risk uses true DGR) + separate Quality score + separate Momentum score + Dividend score
    ↓
Each sub-score (0–100) = BLEND_PCT×(percentile rank within the PUBLIC peer universe — peer_mask / ScoreReference, never a user's own set) + (1−BLEND_PCT)×(absolute band); BLEND_PCT = 0.5
    ↓
Composite Score = w_mos×MoS_sub + w_risk×Risk_sub + w_quality×Quality_sub + w_momentum×Momentum_sub + w_dividend×Dividend_sub  (Risk_sub already oriented safer = higher; weights from the Settings screening style, default balanced 0.24/0.22/0.24/0.15/0.15)
    ↓
Hard veto check — static: D/E [sector-exempt for Financials/Real Estate/Utilities], FCF negative 3+ consecutive years [or single period if <3yr history], at-risk dividend + coverage < 1.0×, confirmed zero average volume [== 0, not unreported]; trend (_trend_veto, needs 3+yr history): 3+yr revenue decline, EBIT negative 3yr, retained-earnings erosion, recent dividend cut + cover < 1.5× → Fails quality screen (score 0)
    ↓
Model signal: Undervalued (score ≥ threshold AND MoS ≥ min_mos AND fair value not fv_basis_thin) | Neutral | Low score | Fails quality screen | No signal (no public peer basis)
    ↓
Shown with: tooltip + methodology link, model fair value, MoS, signal_computed_at, price_as_of, data_flags, data_source; changes logged to signal_history (12 months); model_version + model_settings_id per row
```

---
## Design rules that keep the output general (PER-1 to PER-7)
These constrain any future change to this algorithm. Review them before each release that touches signals or alerts (PER-9).
1. Fair values, scores and signals use only instrument data and the **shared** model settings. They never use a user's holdings, position sizes, income, goals, age, horizon or risk tolerance (PER-1).
2. The peer universe is the public coverage only. A user's manual tickers or holdings never enter the sector medians or rank distributions (PER-2).
3. No questionnaire (knowledge, objectives, risk appetite) may feed any input or setting of this algorithm (PER-3).
4. No alert may combine a signal with the user's own portfolio, such as "a stock you hold is now Low score" (PER-5). Alerts on thresholds the user sets on their own watchlist are allowed.
5. No order button, broker deep link or affiliate link next to a signal (PER-7).
6. The signal labels, definitions, `signal_reason` texts, the tooltip and the methodology page are legal texts. They exist in every offered language before that language is released (INT-1, INT-3, INT-4).

## Changes from the original spec
| Area | Original (`docs/stock_valuation_algorithm.md`) | This version | Req. |
|---|---|---|---|
| Purpose | "identifying undervalued stocks and deciding whether they are worth buying" | Model fair value plus a descriptive signal; general information, not a recommendation | DIS-5, DIS-6, PER |
| Settings | "user-adjustable sliders" | Shared, admin-only model settings; the same for every user | PER-2 |
| Data source | yfinance, licence not addressed | Data source stated per row; licence named as a launch blocker | DATA-1/2, REC-3 |
| Analyst inputs | Analyst target model (weight 0.13) + recommendation mean in momentum | Off until licensed; the blend re-normalises | DATA-6 |
| Peer universe | Enabled exchanges + holdings on disabled exchanges (+ in code: each user's manual tickers); holdings ranked among themselves before the first build | Public universe only (`peer_mask`); user rows scored against it; no ranked signal without a public reference | PER-1, PER-2 |
| Stage 3 | "Total Expected Return" | "Implied Return % (est.)", explicitly not an expected return | REC-2, DIS-5 |
| Stage 6 | Decision: Strong Buy / Monitor / Avoid, veto → Avoid | Model signal: Undervalued / Neutral / Low score / Fails quality screen / No signal | BDG-1, BDG-3 |
| Presentation | — | Tooltip, methodology link, fair value + MoS, timestamps, data flags and source with every signal | BDG-2/3, REC-3/4 |
| Methodology | Thresholds only in this spec | `methodology()` generates the public page from the live constants: horizon, risk warning, sensitivity | REC-5, REC-6 |
| History | — | Signal-change log, 12 months, visible per stock; distribution of signals | REC-7, REC-10 |
| Reproducibility | — | `model_version` + `model_settings_id` per row and log record | REC-11 |
