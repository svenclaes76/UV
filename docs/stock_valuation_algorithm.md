# Stock Valuation Algorithm
A systematic pipeline for identifying undervalued stocks and deciding whether they are worth buying.

This document describes the algorithm as implemented in [`screener.py`](../screener.py) (`compute_scores()` and its helpers), which is the single source of fair value, risk, and decision logic used across the Screener, Analysis, Portfolio, Risk, and Dashboard pages. Thresholds marked **(configurable)** below are user-adjustable sliders under Settings → Screening & veto rules (`settings.get_veto_thresholds()`); the values shown are the shipped defaults. The same admin-only card also carries a **Screening style** picker (`settings.get_score_weights()`) that swaps the Stage 5 composite weights — see Stage 5.

> The 0–10 fundamental scorers `_financial_health_score`, `_earnings_quality_score` and `_dividend_sustainability_flag` (plus `_clamp` / `_get_num`) now live in [`scoring.py`](../scoring.py) and are shared with the portfolio risk engine; `screener.py` re-exports them, so every `from screener import …` call site is unchanged.

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
- Analyst target price — mean (`targetMeanPrice`), high / low (`targetHighPrice` / `targetLowPrice`, for dispersion), and analyst count (`numberOfAnalystOpinions`, for coverage depth)
- EBIT, enterprise value, shares outstanding
- Debt/equity, current ratio, interest coverage, free cash flow (current + up to ~4-5yr history via `fcfHistory`), net income, beta, average volume, payout ratio
- ROE, ROA, operating margin, profit margin
- Earnings growth, revenue growth, analyst recommendation mean
- Sector, country, quote currency
- Multi-year statement history → `revenueHistory`, `ebitHistory`, `netIncomeHistory`, `cfoHistory`, `retainedEarningsHistory`, `totalAssetsHistory` (`screener._statement_history`)
- Dividend history → `true_dgr`, `dividend_growth_streak`, `dividend_payment_years`, `dividend_last_cut_year` (`screener._dividend_stats`)

Price-to-book and EV/EBITDA are also fetched but are **display-only** — they do not feed any fair-value model. Trailing P/E is display-only per row, but its **sector median across the screened universe** now sets the PE Fair Value multiple (Stage 2).
---
## Stage 2 — Fair Value Estimation (Multi-Model)
Six models run per stock; each stock's composite is a weighted average of whichever models produced a positive value for it (`screener._fair_value_models`).

### Models
| Model | Formula / Approach | Base weight |
|---|---|---|
| **Graham Number** | `√(22.5 × EPS × BVPS)` — requires positive EPS and BVPS | 0.178 (`W_GRAHAM`) |
| **PE Fair Value** | `EPS × m`, where `m` is the median trailing P/E of the stock's own **sector** across the current screened universe (`screener._sector_pe_medians`), winsorized to `PE_MULTIPLE_BAND` (6–30×), then multiplied by a bounded PEG tilt `clamp(1 + earningsGrowth, 0.7, 1.5)` (`PEG_TILT_BAND`). Falls back to a flat `PE_MULTIPLE_FALLBACK` (15×, the value used unconditionally before this) when the sector has fewer than `MIN_SECTOR_SAMPLE` (5) priced peers, or when `trailingPE`/`sector` aren't in the frame (pre-WS-10 caches, direct callers). The 15× fallback is *not* Graham's no-growth base multiplier (8.5×) — just a round heuristic near the long-run market-average P/E | 0.150 (`W_PE`) |
| **Earnings Power Value (EPV)** | `EPV_EV = EBIT × (1 − t) / WACC`, where **EBIT is the mean over `ebitHistory`** (`screener._normalised_ebit`, ≥ 3 finite years) so a peak or trough year doesn't set the valuation — falling back to point-in-time `ebit` for recent IPOs / failed statement fetches. Converted to per-share as `(EPV_EV − NetDebt) / SharesOutstanding` where `NetDebt = EnterpriseValue − (Price × SharesOutstanding)` — subtracts actual net debt directly rather than assuming EPV_EV's implied capital structure mirrors the market's EV/market-cap ratio; falls back to the `Price × (EPV_EV / EnterpriseValue)` EV-ratio shortcut when `sharesOutstanding` is unavailable. `t` is the country's statutory corporate tax rate from the static `COUNTRY_TAX_RATES` table (e.g. 21% US, 30% Germany, 12.5% Ireland), falling back to 25% when `country` is missing or unlisted | 0.208 (`W_EPV`) |
| **DDM — single-stage** | Gordon growth: `D₁ / (WACC − g)`, g clamped to 0–5% | 0.167 (`W_DDM_SINGLE`) × payout ramp |
| **DDM — multi-stage** | 5-year explicit high-growth phase (g clamped 0–15%) + Gordon terminal value (terminal g = 2%) | 0.167 (`W_DDM_MULTI`) × payout ramp |
| **Analyst target price** | `targetMeanPrice × (1 − 10%)` — a flat haircut (`screener.ANALYST_TARGET_HAIRCUT`) applied before it feeds the composite, to discount sell-side targets' well-documented optimism bias. The undiscounted `targetMeanPrice` is still shown as-is elsewhere in the UI (e.g. the Analysis/drawer "Analyst Target" tile) — only the model input is haircut. | 0.130 (`W_ANALYST`) × dispersion & coverage factor |

`DCF`, comparable multiples (P/E, EV/EBITDA, P/S), and an asset-based / P/B model are **not implemented** — they don't exist as separate fair-value inputs.

**WACC** = 3% risk-free rate + beta × 5% equity risk premium. A raw beta outside [0.1, 5.0] (or missing/NaN) is rejected and defaults to 1.0; an in-band beta is **Blume-adjusted** — shrunk two-thirds of the way toward the market beta of 1.0 (`0.67 × raw + 0.33 × 1.0`, `screener.BLUME_WEIGHT` / `_adjust_beta`) — since yfinance's trailing single-estimate beta is noisy and mean-reverts.

**DDM payout ramp:** both DDM base weights are multiplied by `screener._ddm_weight_factor(div_rate, payout)`, a continuous factor in `[0, 1]` keyed on the payout ratio (`_DDM_PAYOUT_KNOTS = 0.05 / 0.30 / 0.70 / 0.95`): **0** for a non-payer or a payout at/below 5% or at/above 95%, **1.0** (full base weight) across the 30–70% comfortable band, and a **linear ramp** on each shoulder in between. It is continuous at every knot, so there is no cliff anywhere in the payout range — an 89%-payout payer and a 91%-payout payer differ by a sliver of DDM weight, not the whole ≈0.334 combined block (this replaces the earlier hard 5–90% in/out gate, itself a replacement for a still-earlier "graduated 30–50%" scheme). Whatever DDM weight is not used drops out and the remaining available models (Graham, PE, EPV, Analyst) are re-normalized over their own weights, since there is no DCF or comps model to receive it instead.

**Analyst dispersion & coverage factor:** the analyst weight is `W_ANALYST × _analyst_weight_factor(row)`, itself the product of two multipliers, each `1.0` when its input is missing (an absent field never penalizes):
- **dispersion** — from `spread = (targetHighPrice − targetLowPrice) / targetMeanPrice`: `1.0` while `spread ≤ 0.20` (`_ANALYST_SPREAD_TIGHT`), then a linear ramp down to `0.30` (`_ANALYST_DISPERSION_FLOOR`) at `spread = 0.80` (`_ANALYST_SPREAD_WIDE`), staying at the floor for any wider spread. Wide disagreement among analysts ⇒ the mean target carries less information.
- **coverage** — `clamp(numberOfAnalystOpinions / 8, 0.30, 1.0)` (`_ANALYST_COVERAGE_FULL` / `_ANALYST_COVERAGE_FLOOR`). A target built from one or two analysts is downweighted toward the floor.

The base weights above (`W_GRAHAM`, `W_PE`, `W_EPV`, `W_DDM_SINGLE`, `W_DDM_MULTI`, `W_ANALYST`) sum to exactly **1.00**. They were originally 0.18/0.18/0.19/0.20/0.20/0.25 (a stale sum of 1.20), rescaled to 0.150/0.150/0.158/0.167/0.167/0.208, then — since sell-side targets are optimism-biased and slow to react to regime changes — the analyst weight was cut to **0.130** and the freed ≈0.078 handed to the two most fundamentals-anchored models: `W_EPV` 0.158 → **0.208** and `W_GRAHAM` 0.150 → **0.178**.

### Dividend-Specific Valuation Checks
| Check | Formula | Where it's used |
|---|---|---|
| **Payout ratio** | `payoutRatio` (as reported) | Dividend sustainability flag, dividend risk/score |
| **Cash payout ratio** | `(DPS × Shares) / FCF` | Dividend sustainability flag, dividend risk/score |
| **Dividend coverage ratio** | `EPS / DPS` | Dividend sustainability flag, dividend risk/score, hard veto |
| **Dividend growth rate (DGR)** | `screener._dgr_estimate(row)` — the **true DGR** below when the dividend history has ≥2 complete years, else the `earningsGrowth` (TTM) proxy. A real `0.0` (flat DPS) wins over the proxy. Used in TER, dividend risk score, dividend score | TER, dividend risk/score |
| **Dividend yield vs. historical average** | `dividendYield / fiveYearAvgDividendYield`, feeds the dividend score | Dividend score |
| **Dividend yield vs. sector peers** | *Not implemented* — no peer-median dataset exists | — |
| **True DGR** `(DPS_t / DPS_{t-n})^(1/(n-1)) − 1` | **Implemented** (`screener._dividend_stats.true_dgr`) — CAGR of annual DPS across the complete calendar years in a ~6yr window (the incomplete current year is dropped); `None` with fewer than 2 such years | DGR estimate above |

### Weighted Composite Fair Value
```
Intrinsic Value = Σ (Model weight × Model fair value) / Σ (Model weight)
```
summed over whichever models produced a value for that stock; the weighted average becomes the **fair value** (`fair_value` column).
---
## Stage 3 — Margin of Safety & Total Expected Return
### Margin of Safety (MoS)
```
MoS = (Fair Value − Price) / Fair Value
```
There is no fixed 20–30% buy-zone band on MoS itself. Instead, a **Strong Buy** decision additionally requires MoS to clear a configurable minimum (`min_mos`, default **0%**) — see Stage 6.

### Total Expected Return (TER)
```
TER = Capital gain % + Forward dividend yield % + Expected DGR %
```
where Capital gain % = `(Fair Value − Price) / Price × 100`, and Expected DGR is `_dgr_estimate` (true DPS CAGR when available, else the `earningsGrowth` proxy) clamped to 0–10%. TER is displayed per-stock but there is **no >15% / 8–15% / <8% attractiveness banding** applied anywhere — it is not classified into "Attractive / Acceptable / Unattractive".

**DGR halving when DDM contributed:** if either DDM variant fed that stock's composite fair value (`ddm_contributed`, `screener._fair_value_models`), the Expected DGR term is halved before summing. Growth is already embedded in the Capital gain % term via the DDM-derived fair value in that case, so adding the full DGR proxy on top would double-count it.

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
| **Liquidity** | Average daily volume | Risk |
| **Quality** | ROE, ROA, operating margin, FCF yield, current ratio | *Separate score* |
| **Momentum** | Earnings growth, revenue growth, analyst recommendation mean | *Separate score* |

`Momentum`'s analyst component (`recommendationMean`) is a current-snapshot rating, not a trend of analyst revisions over time. A **Qualitative dimension** (competitive moat, management track record, ESG flags) is **not implemented** — there is no data source for it, so the risk composite has no room reserved for it.

The **Dividend score** (separate from dividend risk, feeds Stage 5 directly) combines: yield vs. 5-yr average, payout ratio safety, cash payout ratio, dividend coverage, and `_dgr_estimate` (true DGR when available, else the `earningsGrowth` proxy) — non-payers get a neutral 5.0 so they're neither rewarded nor penalized.
---
## Stage 5 — Composite Score
Before weighting, MoS, Risk, Quality, Momentum and Dividend are each turned into a **0–100 sub-score** (`screener._blend_ranks`, higher = better for all five), a blend of two views of the same value:
- **Cross-sectional percentile rank** (`screener._pct_rank`) — the stock's standing *within the current screened universe*. NaN rows get a neutral 50.
- **Absolute band** (`screener._abs_band`) — the same value mapped through a fixed piecewise-linear scale, independent of the universe:
  - MoS: `≤ 0 → 0`, `10% → 40`, `25% → 70`, `≥ 50% → 100` (`_BAND_MOS`).
  - Quality / Momentum / Dividend: the raw 0–10 score × 10 (`_BAND_0_10`).
  - Risk: `(10 − risk_raw) × 10`, so a low raw risk scores high (`_BAND_RISK`).

`sub_score = BLEND_PCT × percentile + (1 − BLEND_PCT) × absolute_band`, `BLEND_PCT = 0.5`. Pure percentile ranking (the earlier behaviour, `BLEND_PCT = 1`) inflates a mediocre stock in a weak universe and makes MoS_rank meaningless when *every* stock is overvalued; the absolute anchor keeps the score honest in that case. It complements — doesn't replace — the small-universe flag below.
```
Score = 0.24×MoS_sub + 0.22×Risk_sub + 0.24×Quality_sub + 0.15×Momentum_sub + 0.15×Dividend_sub
```
(Risk_sub is already oriented so that safer = higher, so it's added, not subtracted.) The default weights are `screener.W_MOS` / `W_RISK` / `W_QUALITY` / `W_MOMENTUM` / `W_DIVIDEND` (`0.24 / 0.22 / 0.24 / 0.15 / 0.15` — the **balanced** style). These were rebalanced from an earlier MoS-led `0.30 / 0.18 / 0.22 / 0.15 / 0.15`: margin of safety now co-leads with quality rather than dominating, and risk is weighted more heavily, so a wide discount can't on its own outvote weak fundamentals or a poor risk profile. Settings → Screening & veto rules → **Screening style** swaps in one of four shared, admin-controlled vectors (`settings._SCORE_STYLES`, each summing to 1.0, passed to `compute_scores(weights=…)` via `settings.get_score_weights()`): *balanced*, *value* (MoS + quality lead), *growth* (momentum + quality lead, thin MoS), *income* (dividend-led). The `Sub MoS` / `Sub Risk` / … columns carry the blended sub-scores; only the final weighting changes with the style.

**Universe-size guard:** a small or low-quality universe can still let a mediocre stock rank high on the percentile half of each sub-score. `compute_scores` sets `small_universe = True` on every row when the screened universe has fewer than `screener.MIN_UNIVERSE_SIZE` (20, a heuristic threshold) stocks; the Screener page surfaces this as a caption caveat next to the result count.
---
## Stage 6 — Decision
| Score | Action |
|---|---|
| ≥ 70 **(configurable, `buy_threshold`)** — *and* MoS ≥ `min_mos` (default 0%) | **Strong Buy** |
| 40–70 | **Monitor / watch list** |
| < 40 | **Avoid** |

A hard veto forces **Avoid** regardless of score.

### Hard Veto Rules
`screener.compute_scores`'s `_hard_veto` is true when **any** of the following holds. The
static, point-in-time checks:
- Debt/equity ratio > **500%** i.e. 5.0× **(configurable, `max_debt_equity`)** — **skipped for Financial Services, Real Estate, and Utilities** (`screener.LEVERAGE_EXEMPT_SECTORS`), since high leverage is a structural feature of those business models (deposits/float, debt-financed property, capex-heavy regulated assets), not a distress signal. Other sectors are unaffected.
- Free cash flow negative for the **3 most recent consecutive fiscal years** (`fcfHistory`, from the cash flow statement's "Free Cash Flow" row, newest first — `screener._fcf_history`). Falls back to the **single most recent reported period** (`freeCashflow`) when fewer than 3 years of history are available (recent IPOs, or tickers where the statement fetch failed/doesn't expose the row) — a single bad year no longer vetoes an otherwise-sound stock on its own once 3-year history exists.
- Dividend sustainability flag is **At Risk** *and* dividend coverage < 1.0×

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
  (Graham Number + PE Fair Value [sector-median trailing P/E × bounded PEG tilt] + EPV [on mean multi-year EBIT] + DDM single-stage + DDM multi-stage + Analyst target [10% haircut, weight scaled by dispersion & coverage])
    ↓
Weighted fair value
  (base weights sum to 1.00; combined DDM weight ≈0.334 × a continuous payout
   ramp — full across 30–70% payout, tapering to 0 by 5% / 95%; the unused part
   re-normalizes over Graham/PE/EPV/Analyst)
    ↓
Margin of Safety = (Fair Value − Price) / Fair Value
Total Expected Return = Capital Gain % + Forward Yield % + DGR % (true DPS CAGR, else earnings-growth proxy) [DGR halved if DDM contributed to Fair Value]
Dividend Sustainability Flag (payout ratio, cash payout ratio, coverage ratio, DPS cut in last 3 complete years)
    ↓
Risk scoring (5 dimensions; earnings quality blends FCF-history consistency + a Sloan accrual ratio, dividend risk uses true DGR) + separate Quality score + separate Momentum score + Dividend score
    ↓
Each sub-score (0–100) = BLEND_PCT×(cross-sectional percentile rank) + (1−BLEND_PCT)×(absolute band); BLEND_PCT = 0.5
    ↓
Composite Score = w_mos×MoS_sub + w_risk×Risk_sub + w_quality×Quality_sub + w_momentum×Momentum_sub + w_dividend×Dividend_sub  (Risk_sub already oriented safer = higher; weights from the Settings screening style, default balanced 0.24/0.22/0.24/0.15/0.15)
    ↓
Hard veto check — static: D/E [sector-exempt for Financials/Real Estate/Utilities], FCF negative 3+ consecutive years [or single period if <3yr history], at-risk dividend + coverage < 1.0×; trend (_trend_veto, needs 3+yr history): 3+yr revenue decline, EBIT negative 3yr, retained-earnings erosion, recent dividend cut + cover < 1.5× → forces Avoid
    ↓
Strong Buy (score ≥ threshold AND MoS ≥ min_mos) | Monitor | Avoid
```
