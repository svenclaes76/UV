# Stock Valuation Algorithm
A systematic pipeline for identifying undervalued stocks and deciding whether they are worth buying.

This document describes the algorithm as implemented in [`screener.py`](../screener.py) (`compute_scores()` and its helpers), which is the single source of fair value, risk, and decision logic used across the Screener, Analysis, Portfolio, Risk, and Dashboard pages. Thresholds marked **(configurable)** below are user-adjustable sliders under Settings → Screening & veto rules (`settings.get_veto_thresholds()`); the values shown are the shipped defaults.
---
## Stage 1 — Data Collection
A single point-in-time snapshot per ticker via `yfinance`, cached to `.cache/fundamentals.json` and refreshed every ~24h ± 4h jitter per ticker (`screener._fetch_one`). There is no multi-year financial-statement history, no peer/comparable-company dataset, and no external macro feed — the risk-free rate and equity risk premium are fixed constants, not live indicators.

**Fields fetched:**
- Price, EPS (`trailingEps`), book value per share (`bookValue`)
- Dividend rate (`trailingAnnualDividendRate` / `dividendRate`), 5-yr average dividend yield, ex-dividend and payment dates
- Analyst mean target price (`targetMeanPrice`)
- EBIT, enterprise value, shares outstanding
- Debt/equity, current ratio, interest coverage, free cash flow, net income, beta, average volume, payout ratio
- ROE, ROA, operating margin, profit margin
- Earnings growth, revenue growth, analyst recommendation mean
- Sector, country

Trailing P/E, price-to-book, and EV/EBITDA are also fetched but are **display-only** — they do not feed any fair-value model.
---
## Stage 2 — Fair Value Estimation (Multi-Model)
Six models run per stock; each stock's composite is a weighted average of whichever models produced a positive value for it (`screener._fair_value_models`).

### Models
| Model | Formula / Approach | Base weight |
|---|---|---|
| **Graham Number** | `√(22.5 × EPS × BVPS)` — requires positive EPS and BVPS | 0.18 |
| **PE Fair Value** | `EPS × 15` (Graham's conservative no-growth multiple) | 0.18 |
| **Earnings Power Value (EPV)** | `EBIT × (1 − 25%) / WACC`, scaled to per-share via `Price × (EPV_EV / EnterpriseValue)` | 0.19 |
| **DDM — single-stage** | Gordon growth: `D₁ / (WACC − g)`, g clamped to 0–5% | 0.20 (0 if DDM-ineligible) |
| **DDM — multi-stage** | 5-year explicit high-growth phase (g clamped 0–15%) + Gordon terminal value (terminal g = 2%) | 0.20 (0 if DDM-ineligible) |
| **Analyst target price** | `targetMeanPrice`, used directly as a model input | 0.25 |

`DCF`, comparable multiples (P/E, EV/EBITDA, P/S), and an asset-based / P/B model are **not implemented** — they don't exist as separate fair-value inputs.

**WACC** = 3% risk-free rate + beta × 5% equity risk premium; beta is clamped to [0.1, 5.0] and defaults to 1.0 if missing or out of range.

**DDM eligibility gate:** both DDM weights are set to zero unless the stock pays a dividend (`div_rate > 0`) **and** its payout ratio is between 5% and 90%. This is a binary eligibility gate, not the graduated 30–50% weighting scheme described in earlier drafts of this document — when DDM is ineligible, its 0.40 combined weight is absorbed by re-normalizing over the remaining available models (Graham, PE, EPV, Analyst), since there is no DCF or comps model to receive it instead.

### Dividend-Specific Valuation Checks
| Check | Formula | Where it's used |
|---|---|---|
| **Payout ratio** | `payoutRatio` (as reported) | Dividend sustainability flag, dividend risk/score |
| **Cash payout ratio** | `(DPS × Shares) / FCF` | Dividend sustainability flag, dividend risk/score |
| **Dividend coverage ratio** | `EPS / DPS` | Dividend sustainability flag, dividend risk/score, hard veto |
| **Dividend growth rate (DGR)** | *Not computed.* `earningsGrowth` (TTM, from yfinance) is used everywhere DGR would be needed — TER, dividend risk score, dividend score, momentum score — as the best available proxy | TER, dividend risk/score |
| **Dividend yield vs. historical average** | `dividendYield / fiveYearAvgDividendYield`, feeds the dividend score | Dividend score |
| **Dividend yield vs. sector peers** | *Not implemented* — no peer-median dataset exists | — |
| **True DGR** `(DPS_t / DPS_{t-5})^(1/5) − 1` | *Not implemented* — no 5–10yr DPS history is fetched | — |

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
where Capital gain % = `(Fair Value − Price) / Price × 100`, and Expected DGR uses the `earningsGrowth` proxy clamped to 0–10%. TER is displayed per-stock but there is **no >15% / 8–15% / <8% attractiveness banding** applied anywhere — it is not classified into "Attractive / Acceptable / Unattractive".

### Dividend Sustainability Flag
`screener._dividend_sustainability_flag` returns `"At Risk"`, `"OK"`, or `""` (non-payer):
- Payout ratio > 90% **(configurable, `max_payout`)** → **At Risk**
- Cash payout ratio > 80% → **At Risk**
- Dividend coverage ratio < 1.2× → **At Risk**

The spec's fourth check — **DPS cut in the last 5 years** — is not implemented (no multi-year DPS history is fetched). There is also no automatic **+5–10pp MoS bump** for flagged stocks; a flagged stock passes the same `min_mos` threshold as any other.
---
## Stage 4 — Risk, Quality, Momentum, and Dividend Scoring
The composite **risk** score averages **five** dimensions (0–10 each, higher = safer) and inverts the result — not the seven dimensions described in earlier drafts. Quality and Momentum are computed as separate top-level 0–10 scores, not risk sub-dimensions.

| Dimension | Key metrics | Part of |
|---|---|---|
| **Financial health** | Debt/equity, current ratio, interest coverage | Risk |
| **Earnings quality** | FCF vs. net income | Risk |
| **Market risk** | Beta | Risk |
| **Dividend risk** | Payout ratio, cash payout ratio, dividend coverage, `earningsGrowth` (DGR proxy) | Risk |
| **Liquidity** | Average daily volume | Risk |
| **Quality** | ROE, ROA, operating margin, FCF yield, current ratio | *Separate score* |
| **Momentum** | Earnings growth, revenue growth, analyst recommendation mean | *Separate score* |

`Momentum`'s analyst component (`recommendationMean`) is a current-snapshot rating, not a trend of analyst revisions over time. A **Qualitative dimension** (competitive moat, management track record, ESG flags) is **not implemented** — there is no data source for it, so the risk composite has no room reserved for it.

The **Dividend score** (separate from dividend risk, feeds Stage 5 directly) combines: yield vs. 5-yr average, payout ratio safety, cash payout ratio, dividend coverage, and the `earningsGrowth` DGR proxy — non-payers get a neutral 5.0 so they're neither rewarded nor penalized.
---
## Stage 5 — Composite Score
Before weighting, MoS, Risk (inverted), Quality, Momentum, and Dividend are each converted to a **0–100 cross-sectional percentile rank** across the current screener universe (`screener._pct_rank`) — this is a normalization step not present in earlier drafts of this document, which described a raw weighted sum of the sub-scores directly.
```
Score = 0.30×MoS_rank + 0.18×(100−Risk_rank) + 0.22×Quality_rank + 0.15×Momentum_rank + 0.15×Dividend_rank
```
Weights are fixed constants (`screener.W_MOS`, `W_RISK`, `W_QUALITY`, `W_MOMENTUM`, `W_DIVIDEND`) — they are not currently adjustable per investment style (value / growth / income), though the composite's shape mirrors that intent.
---
## Stage 6 — Decision
| Score | Action |
|---|---|
| ≥ 70 **(configurable, `buy_threshold`)** — *and* MoS ≥ `min_mos` (default 0%) | **Strong Buy** |
| 40–70 | **Monitor / watch list** |
| < 40 | **Avoid** |

A hard veto forces **Avoid** regardless of score.

### Hard Veto Rules
`screener.compute_scores`'s `_hard_veto` is true when **any** of:
- Debt/equity ratio > **500%** i.e. 5.0× **(configurable, `max_debt_equity`)** — **skipped for Financial Services, Real Estate, and Utilities** (`screener.LEVERAGE_EXEMPT_SECTORS`), since high leverage is a structural feature of those business models (deposits/float, debt-financed property, capex-heavy regulated assets), not a distress signal. Other sectors are unaffected.
- Free cash flow is negative — checked for the **single most recent reported period**, not "3+ consecutive years" as earlier drafts of this document described (no multi-year FCF history is fetched)
- Dividend sustainability flag is **At Risk** *and* dividend coverage < 1.0×

Not implemented — no data source exists for any of these: active fraud investigation / accounting restatement, imminent covenant breach or liquidity crisis, or a standalone "dividend cut in current or prior fiscal year" veto (the closest proxy is the coverage-based check above).
---
## Algorithm Summary
```
Data collection (yfinance point-in-time snapshot, 24h cache)
    ↓
Fair value estimation
  (Graham Number + PE Fair Value + EPV + DDM single-stage + DDM multi-stage + Analyst target)
    ↓
Weighted fair value
  (DDM weight 0.40 combined if eligible — payer with 5–90% payout; 0 otherwise,
   re-normalized over Graham/PE/EPV/Analyst)
    ↓
Margin of Safety = (Fair Value − Price) / Fair Value
Total Expected Return = Capital Gain % + Forward Yield % + Earnings-growth-proxy DGR %
Dividend Sustainability Flag (payout ratio, cash payout ratio, coverage ratio)
    ↓
Risk scoring (5 dimensions) + separate Quality score + separate Momentum score + Dividend score
    ↓
Percentile-rank each sub-score (0–100) across the current universe
    ↓
Composite Score = 0.30×MoS_rank + 0.18×(100−Risk_rank) + 0.22×Quality_rank + 0.15×Momentum_rank + 0.15×Dividend_rank
    ↓
Hard veto check (D/E [sector-exempt for Financials/Real Estate/Utilities], FCF, at-risk dividend + low coverage) → forces Avoid
    ↓
Strong Buy (score ≥ threshold AND MoS ≥ min_mos) | Monitor | Avoid
```
