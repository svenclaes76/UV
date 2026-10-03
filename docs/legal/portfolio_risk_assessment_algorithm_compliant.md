# Portfolio Risk Assessment Algorithm (legal-compliance version)

A systematic pipeline that **describes** the risk of a user's own stock portfolio, from individual position risk through to portfolio-level stress testing, a composite risk score and a list of risk observations. It describes and never prescribes (PER-4). It states what the figures show and which reference they were compared with, and never what the user should buy, sell, trim or rebalance.

> **Status.** This is the legal-compliance copy of [`docs/portfolio_risk_assessment_algorithm.md`](../portfolio_risk_assessment_algorithm.md), aligned with *Uvalu — Legal Requirements for Launch* (Oct 2, 2026). It describes [`risk_compliant.py`](../../risk_compliant.py), the candidate replacement for `risk.py`, which is not yet wired into the app. All metrics, scores and thresholds are computed **exactly as in `risk.py`** (pinned by `tests/test_compliance_algorithms.py`); only the wording and the output structure change. See [§ Changes from the original spec](#changes-from-the-original-spec) and [`algorithm-compliance-review.md`](algorithm-compliance-review.md). Counsel review is pending.

Implemented in [`risk_compliant.py`](../../risk_compliant.py); `assess_portfolio(pf_df, cache, weighting, veto_lookup, targets, prior_snapshot) → RiskReport`. Build `pf_df` with [`portfolio_enrichment.enrich_for_risk()`](../../portfolio_enrichment.py). Time-series data (price history, dividends, FX, Fama-French factors) comes through [`marketdata.py`](../../marketdata.py), disk-cached under `.cache/{history,dividends,factors}/`.

**Why portfolio data may be used here but not in signals.** This engine necessarily reads the user's holdings; describing them is its purpose, and PER-4 allows portfolio analytics that describe. What it must not do is turn that description into a personal recommendation: no actions, no "you should", and no combination of a stock signal with the fact that the user holds the stock (PER-5).

### Implementation notes (what the engine actually does now)

- **Everything is EUR.** `risk._to_eur` restates each holding's native-currency close series in EUR (per-ticker `Currency` from the fundamentals cache, FX: ECB reference rates from frankfurter.dev via `fx.py`, reached through `marketdata.fx_to_eur_frame`) *before* any metric is computed, so `port_rets` is never a currency blend.
- **Betas are regressed**, not taken from yfinance. `risk._resolve_betas` runs an OLS of each holding's own EUR daily returns on `BENCHMARK_TICKER` (`^STOXX50E`, euro-denominated) over the trailing window (≥ 60 aligned obs); falls back to the cached yfinance `beta`, then 1.0. `PositionRisk.beta_source` records which. `QuantMetrics.portfolio_beta_regression` adds the direct OLS of `port_rets` on the benchmark as a cross-check.
- **10-year fetch, 5-year quant.** `assess_portfolio` fetches a 10y window; Stages 1/3/4 run on the trailing-5y slice, Stage 6 gets the full series (for crisis-window replay).
- **Factor set:** Developed 5-factor + momentum first, US Fama-French as an automatic fallback; parsed frames are disk-cached weekly with a stale-copy fallback when the network is down (`risk._factor_data`).
- **Targets / snapshot:** when `targets` (per-user `portfolio.load_targets()`, set by the user themselves) or `prior_snapshot` (`portfolio.load_risk_snapshot()`, one per calendar day) are supplied, Stage 8 compares against the user's own targets (`basis = "user_target"`) or the previous snapshot (`basis = "since_snapshot"`) instead of the model's reference levels. Comparisons against thresholds the user set are allowed (PER-5).

---

## Overview

```
Portfolio holdings + market data
    ↓
Stage 1 — Position-level risk profiling
    ↓
Stage 2 — Concentration & diversification analysis
    ↓
Stage 3 — Portfolio-level quantitative risk metrics
    ↓
Stage 4 — Factor exposure analysis
    ↓
Stage 5 — Dividend & income risk
    ↓
Stage 6 — Stress testing & scenario analysis
    ↓
Stage 7 — Composite portfolio risk score (band + description)
    ↓
Stage 8 — Risk observations (descriptive) + disclosures
```

---

## Stage 1 — Position-Level Risk Profiling

Assess risk at the individual stock level before aggregating to the portfolio. Each position inherits the risk profile from the stock valuation algorithm, extended with portfolio-specific metrics.

| Metric | Formula / Approach | Risk signal |
|---|---|---|
| **Weight in portfolio** | `Position value / Total portfolio value` | > 10% = concentrated |
| **Individual beta** | OLS of the holding's own EUR daily returns on `^STOXX50E` (`_resolve_betas`); yfinance / 1.0 fallback, source recorded in `beta_source` | > 1.3 = high sensitivity |
| **Volatility / VaR (95%)** | Realised annualised vol from the holding's own EUR series when it has ≥ 60 days of history; `|beta| × market-vol` proxy otherwise | Baseline per position |
| **Days to liquidate** | `shares_held / (averageVolume × 0.20)` — trading days to exit at 20% of average volume, position-size aware. `liquidity_flag` when > 10 | > 10 days = thin for this size |
| **Valuation gap** | MoS against the model fair value from the stock valuation algorithm, at the live price. Flag: **Above model fair value** (MoS < −5%), **Near model fair value** (−5% to 10%), **Below model fair value** (≥ 10%). These were "Overvalued / Fairly Valued / Undervalued"; renamed so they cannot clash with the screener's *Undervalued* signal, which also needs a high composite score (REC-2) | Negative MoS = elevated risk on the model's scale |
| **Dividend sustainability** | Payout ratio, coverage ratio, **DPS cut in last 3 complete years** (`scoring._dividend_sustainability_flag`) | Flags income risk |
| **Earnings quality score** | FCF-to-net-income conversion blended with `fcfHistory` consistency (`scoring._earnings_quality_score`) | Low score = red flag |
| **Financial health score** | D/E, interest coverage, current ratio (`scoring._financial_health_score`) | Low score = red flag |

**Position risk rating:** Each stock is rated Low / Medium / High / Critical from weight, beta, MoS, financial-health and earnings-quality (`_position_rating`). Days-to-liquidate does *not* feed the rating (it surfaces as its own Stage 8 observation), so the composite is unaffected by it. The rating describes the position on the model's scale; it carries no action.

---

## Stage 2 — Concentration & Diversification Analysis

Concentrated portfolios amplify both returns and losses. Measure concentration across multiple dimensions.

### 2a. Position Concentration

```
Herfindahl-Hirschman Index (HHI) = Σ (weight_i)²
```

| HHI | Interpretation |
|---|---|
| < 0.10 | Well diversified |
| 0.10 – 0.18 | Moderately concentrated |
| > 0.18 | Highly concentrated — elevated idiosyncratic risk |

**Top-N weight check:**
- Top 1 position > 15% → flag
- Top 3 positions > 35% → flag
- Top 5 positions > 50% → flag

### 2b. Sector Concentration

```
Sector weight = Σ position weights within sector
```

| Sector weight | Signal |
|---|---|
| > 30% in one sector | High sector concentration |
| > 50% in two sectors | Poorly diversified |
| No sector > 20% | Well spread |

### 2c. Geographic Concentration

Buckets by the holding's `country` field (listing / domicile). Mapping to *primary revenue geography* is a documented non-goal — no free data source.

| Geography weight | Signal |
|---|---|
| > 60% one country | High country risk |
| < 30% international | Limited global diversification |

### 2d. Factor Concentration

Check if holdings cluster around the same investment factor (e.g. all high-beta, all small-cap, all momentum). Use factor exposure analysis in Stage 4.

### 2e. Dividend Concentration

```
Dividend HHI = Σ (dividend income from stock_i / total portfolio dividend income)²
```

If top 3 dividend payers contribute > 50% of total income → income concentration risk.

---

## Stage 3 — Portfolio-Level Quantitative Risk Metrics

All of the below run on the EUR-restated trailing-5y daily return series (`port_rets`). VaR / CVaR / MDD / Sharpe / Sortino / correlations are computed from the actual return history — the parametric formulas below are the fallback when there is too little history (< ~20 days). The risk-free rate is the single euro-area `screener.RISK_FREE_RATE` (3%), shared with the valuation engine.

### 3a. Portfolio Beta

```
Portfolio Beta = Σ (weight_i × beta_i)      # beta_i regressed vs ^STOXX50E (Stage 1)
```

`QuantMetrics.portfolio_beta_regression` also reports the direct OLS of `port_rets` on the benchmark; the risk page surfaces it alongside the weighted sum when they diverge by ≥ 0.15.

| Beta | Interpretation |
|---|---|
| < 0.8 | Defensive — underperforms in bull markets |
| 0.8 – 1.2 | Market-like |
| > 1.2 | Aggressive — amplified drawdowns in bear markets |

### 3b. Volatility (Annualised)

```
Portfolio Volatility = √(wᵀ Σ w) × √252
```

Where `Σ` is the covariance matrix of daily returns and `w` is the weight vector.

| Volatility | Interpretation |
|---|---|
| < 10% | Low |
| 10 – 20% | Moderate |
| > 20% | High |

### 3c. Value at Risk (VaR)

An **estimate** of the one-day loss that, under the model's assumptions and the historical data used, is exceeded on only 5% (or 1%) of days. It is **not** a maximum loss: real losses can and do exceed it (DIS-3).

```
VaR (parametric, 1-day, 95%) = Portfolio Value × σ_daily × 1.645
VaR (parametric, 1-day, 99%) = Portfolio Value × σ_daily × 2.326
```

Use historical simulation (rolling 252-day returns) as a cross-check.

### 3d. Conditional Value at Risk (CVaR / Expected Shortfall)

```
CVaR = Average loss in the worst (1 − confidence level) % of scenarios
```

CVaR captures tail risk beyond VaR. Prefer CVaR over VaR for portfolios with non-normal return distributions (e.g. dividend stocks with skewed returns).

### 3e. Maximum Drawdown (MDD)

```
MDD = (Peak portfolio value − Trough portfolio value) / Peak portfolio value
```

Measure over the last 1, 3, and 5 years.

| MDD | Interpretation |
|---|---|
| < 10% | Low historical drawdown |
| 10 – 25% | Moderate |
| > 25% | High |

### 3f. Sharpe & Sortino Ratios

```
Sharpe = (Portfolio return − Risk-free rate) / Portfolio volatility
Sortino = (Portfolio return − Risk-free rate) / Downside deviation
```

Sortino penalises only downside volatility. Because downside deviation is ≤ total volatility by construction, Sortino runs structurally higher than Sharpe for the same portfolio, so the two carry **separate label bands** (`risk._sharpe_label` / `_sortino_label`):

| Value | Sharpe (`ratio_label`) | Sortino (`sortino_label`) |
|---|---|---|
| Strong | > 1.5 | > 2.0 |
| Acceptable | > 1.0 | > 1.5 |
| Suboptimal | ≤ 1.0 | ≤ 1.5 |

### 3g. Correlation Matrix

Compute pairwise return correlations between all holdings. Flag pairs with correlation > 0.80 — these positions do not diversify each other.

```
Effective diversification = 1 − Average pairwise correlation
```

---

## Stage 4 — Factor Exposure Analysis

Decompose portfolio returns into known systematic risk factors. A portfolio overexposed to a single factor carries hidden concentration risk.

### Fama-French 5-Factor Model

| Factor | Exposure interpretation |
|---|---|
| **Market (Mkt-RF)** | Sensitivity to broad market moves |
| **Size (SMB)** | Tilt toward small-cap vs large-cap |
| **Value (HML)** | Tilt toward value vs growth stocks |
| **Profitability (RMW)** | Tilt toward high- vs low-profitability firms |
| **Investment (CMA)** | Tilt toward conservative vs aggressive investment |

**Add Momentum (WML)** as a 6th factor for portfolios with trend-following characteristics.

**Data source (`risk._factor_data`):** the **Developed** region 5-factor + momentum daily files from Ken French's library, with the **US** Fama-French files as an automatic fallback if Developed is unreachable. Parsed frames are disk-cached at `.cache/factors/{set}_{kind}.csv` and served for up to 7 days; on a total network failure the newest stale copy is served and flagged (`FactorExposure.stale`, `.as_of`, `.factor_set`). The regression is `(port_rets − RF) ~ α + Σ βₖ·factorₖ`, subtracting the factor file's own RF (internally consistent regardless of set).

### Factor Risk Flags

- Factor loading > 1.5 on any single factor → concentrated factor bet
- > 60% of return variance explained by one factor → factor-dominated portfolio
- Negative loading on Profitability or Value → reported as a negative factor tilt

---

## Stage 5 — Dividend & Income Risk

*The `weighting = "income_weighted"` model setting only raises this stage's weight in the composite (Stage 7); the metrics are computed for every portfolio. The setting is chosen by the user on the Risk page as a model assumption (PER-8). It is never derived from the user's goals or a questionnaire (PER-3).*

### 5a. Portfolio Dividend Yield

```
Portfolio yield = Σ (weight_i × dividend yield_i)
```

Compare to: risk-free rate, inflation rate, and historical portfolio yield.

### 5b. Weighted Dividend Growth Rate (DGR)

```
Portfolio DGR = Σ (dividend income_i / total portfolio income × DGR_i)
```

`DGR_i` is the holding's `true_dgr` (annual-DPS CAGR from the dividend history) when the fundamentals cache carries it, else the `earningsGrowth` proxy. A portfolio DGR above inflation preserves real purchasing power of income.

### 5c. Income Stability Score

**Implemented** (`IncomeRisk.income_stability`). Per payer with dividend history, a 0–10 score from:
- `min(dividend_payment_years, 10) × 0.4`
- `min(dividend_growth_streak, 10) × 0.4`
- `+2.0` if no DPS cut in the last 5 complete years, else `+0`

```
Portfolio income stability = Σ (income share_i × stability score_i)   # over payers with history
```

`None` when no held payer has usable dividend history yet. Feeds Stage 7's income-risk score: `< 5` adds +12, `< 3` adds +25.

### 5d. Dividend Cut Scenario

Simulate income impact if the top 3 dividend payers cut dividends by 50%:

```
Income at risk = Σ (dividend income from top 3 payers × 50%)
```

If income at risk > 20% of total portfolio income → flag as income-concentrated.

### 5e. Payout Sustainability Flag

Flag positions where:
- Cash payout ratio > 80%
- Payout ratio > 90%
- Dividend coverage ratio < 1.2×
- DPS cut in last 3 years

Aggregate: if > 20% of portfolio income comes from flagged positions → portfolio-level income risk.

---

## Stage 6 — Stress Testing & Scenario Analysis

Test how the portfolio performs under adverse market conditions.

### 6a. Historical Scenarios

Each scenario carries an explicit window. When the held basket's own 10-year EUR return series **substantially covers** that window (≥ 60% of its business days, series starting before it), the portfolio drawdown is the basket's real peak-to-trough over the window (`ScenarioResult.method = "replayed"`). Otherwise it's `portfolio_beta × benchmark_drawdown` (`method = "beta-estimated"`). As the per-ticker history cache accrues, more windows become replayable.

| Scenario | Window | Benchmark drawdown |
|---|---|---|
| Dot-com crash | 2000-03 – 2002-10 | −49% |
| Global financial crisis | 2007-10 – 2009-03 | −57% |
| COVID crash | 2020-02-19 – 2020-03-23 | −34% |
| 2022 rate hike cycle | 2022-01 – 2022-10 | −25% |

### 6b. Hypothetical / Factor Scenarios

| Scenario | Shock applied |
|---|---|
| Rate rise +200 bps | High-P/E holdings repriced via a duration proxy |
| Recession | −25% in cyclical sectors, −10% in defensives |
| Sector crash (−40%) | Applied to the largest sector concentration |
| Credit crunch | High-D/E holdings repriced |
| Dividend freeze | Full annual dividend income lost |

*(USD-strengthening is not implemented — it needs geographic revenue splits, a documented non-goal.)*

### 6c. Monte Carlo Simulation

10,000 paths over 1, 3, and 5 years. **Block bootstrap** (20-day blocks) of the portfolio's own EUR daily return series — preserves the realised fat tails and volatility clustering that an iid-Normal draw discards — re-centred on an explicit **CAPM drift** `(RF + portfolio_beta × ERP) / 252` so the forward mean is an assumption, not an extrapolation of the trailing period. Falls back to an iid-Normal draw (same CAPM drift, `beta × market-vol` sigma) when there are fewer than `_MC_MIN_OBS` (60) days of history. Seeded (`MONTE_CARLO_SEED`), so runs are reproducible.

Output per horizon: the p05 / p25 / p50 / p75 / p95 outcome distribution and the probability of loss.

**Disclosure (DIS-3).** Historical replays, hypothetical shocks and Monte Carlo paths are statistical estimates based on historical data and assumptions (in particular the CAPM drift). Real losses can exceed them, and future crises can be larger, longer or different in kind. `RiskReport.disclosures` (`risk_compliant.RISK_DISCLOSURES`) carries this text, and the Risk page shows it next to the VaR, CVaR, stress and Monte Carlo figures, in the user's language.

---

## Stage 7 — Composite Portfolio Risk Score

Aggregate all dimensions into a single portfolio risk score (0 = minimum risk, 100 = maximum risk).

```
Portfolio Risk Score =
    w₁ × Concentration Risk Score       (HHI, top-N weights, sector/geo)
  + w₂ × Volatility Risk Score          (annualised vol, beta, MDD)
  + w₃ × Tail Risk Score                (VaR, CVaR, stress test results)
  + w₄ × Factor Risk Score              (factor loading concentration)
  + w₅ × Fundamental Risk Score         (weighted avg of position risk ratings)
  + w₆ × Income Risk Score              (dividend sustainability, cut scenario)
```

Weights (`_W_DEFAULT` / `_W_INCOME`, selected by the `weighting` model setting: `"standard"` / `"income_weighted"`; any other value is rejected):

| Component | Standard | Income-weighted |
|---|---|---|
| Concentration risk | 25% | 20% |
| Volatility risk | 20% | 15% |
| Tail risk | 20% | 15% |
| Factor risk | 15% | 10% |
| Fundamental risk | 15% | 20% |
| Income risk | 5% | 20% |

**Factor unavailable:** when the Fama-French feed can't be fetched or built, the factor slot is *dropped* and the remaining five weights are renormalised — a flat placeholder score no longer drags every portfolio toward the middle.

### Score Interpretation

`risk_compliant.RISK_BANDS` is the single source of truth for the label, **description** and **UI colour** of a composite score. `risk_band()` → `uvalu.components.score_color` / `risk_score_meter_html` derive from it. The colour scale is three-tone: **green** for *Low*, **amber** (`#C98A3A`) for *Moderate* and *Elevated*, **red** (`#A32D2D`) for *High* and *Critical*. The green→amber break is at 25 and amber→red at 70. Colours mark position on the scale; they do not signal "act now".

| Risk score | Rating | Colour | Description (shown with the gauge) |
|---|---|---|---|
| 0 – 25 | Low risk | green | Composite risk score 0–25: the lowest band of the model's scale. |
| 26 – 50 | Moderate risk | amber | Composite risk score 25–50: below the scale's midpoint. |
| 51 – 70 | Elevated risk | amber | Composite risk score 50–70: above the scale's midpoint. |
| 71 – 85 | High risk | red | Composite risk score 70–85: the upper band of the model's scale. |
| 86 – 100 | Critical risk | red | Composite risk score above 85: the highest band of the model's scale. |

The original spec paired each band with an **action** ("Hold; monitor quarterly" … "Immediate rebalancing required", "Defensive repositioning — reduce exposure"). That made the score a personal recommendation (PER-4), so the action column is removed. `CompositeScore.action` is now `CompositeScore.description`, and `CompositeScore.weighting` records the preset used.

The Risk page's per-metric band labels (beta, volatility, max drawdown, Sharpe) are tinted on the same three-tone scale via `band_tone()`.

---

## Stage 8 — Risk Observations

`risk_compliant._stage8_observations(..., targets, prior_snapshot) → RiskObservations`. This replaces the original "Rebalancing Decision" (`_stage8_rebalance → RebalanceSignals`). It runs the **same checks with the same thresholds**, but each produces a `RiskObservation`, which states the figure and the reference it was compared with:

| Field | Meaning |
|---|---|
| `level` | `high` (above an upper model reference; was "hard trigger, act immediately") or `notice` (was "soft trigger, review and plan") |
| `scope` | a ticker, a sector or pair list, or `Portfolio` |
| `message` | the observation, e.g. *"BIG.BR is 60% of the portfolio, above the model's 20% single-position reference level"* |
| `basis` | `model_reference` (the model's own level), `user_target` (a target the user set), or `since_snapshot` (change since the last snapshot) |
| `mode` | `absolute` (level check), `drift` (vs a target or the prior snapshot), or `transition` (a rating change) |

There is **no `action` field**, so no code path can attach advice to an observation. The model's thresholds are called *reference levels*, never limits or the user's tolerance; the app knows nothing about the user's tolerance (PER-1). They are named constants (`REF_*`) so the methodology page can publish them.

### Level `high` — above an upper model reference level

| Check | Reference |
|---|---|
| Single position weight | > 20% (`REF_POSITION_WEIGHT`) |
| Portfolio beta | > 1.5 (`REF_PORTFOLIO_BETA`) |
| Estimated 1-day 99% VaR | > 3% of portfolio value (`REF_VAR99_1D_PCT`); was "exceeds 3% loss tolerance" |
| Income from dividend-at-risk positions | > 40% (`REF_FLAGGED_INCOME`) |
| Worst historical scenario replay | drawdown worse than −40% (`REF_WORST_SCENARIO`) |
| Position risk rating | Critical |

**Removed:** *"A position under a hard veto from the stock valuation algorithm"* with the action "Review fundamentals; consider reducing or exiting". It paired the screener's signal with the fact that the user holds the stock, which is the exact pattern PER-5 forbids. The quality-screen failure stays visible on the stock's own badge, the same for every user. `veto_lookup` still feeds `PositionRisk.veto` but no observation.

### Level `notice`

Drift-aware when the data exists, absolute otherwise:

| Check | With `targets` / `prior_snapshot` (`basis`) | Fallback (`model_reference`) |
|---|---|---|
| Sector | drift vs the user's `targets["sectors"]` ≥ 5 pp (`user_target`) | largest sector > 30% |
| Per-name | drift vs the user's `targets["tickers"]` ≥ 5 pp (`user_target`) | (the 20% `high` check only) |
| HHI | above the user's `targets["hhi_max"]` (`user_target`); **and** rise since the snapshot > 0.05 (`since_snapshot`) | 0.10 / 0.18 bands (`REF_HHI_MODERATE` / `REF_HHI_HIGH`) |
| Sharpe | below 1.0 in two consecutive risk reports (`since_snapshot`) | below 1.0 once (`REF_SHARPE`) |
| Risk rating | change into High/Critical vs the snapshot (`since_snapshot`, `mode = transition`) | current High rating |
| Days to liquidate | full position > 10 trading days at 20% of ADV | — |
| DGR | weighted portfolio DGR < 2.5% (`REF_DGR_INFLATION`) | (same) |
| Correlation | holding pairs with correlation > 0.80 | (same) |

The per-user target allocation is edited under **Settings → Target allocation**; the snapshot is upserted once per calendar day by the Risk page.

### Removed: rebalancing actions

The original spec mapped each issue to an action: *"Trim to target weight; redeploy to underweights"*, *"Reduce highest-weight sector; add to lagging sectors"*, *"Rotate into low-beta / defensive stocks"*, *"Diversify dividend income across more payers"*, *"Add positions with offsetting factor loadings"*, *"Add uncorrelated assets or sectors"*, and in the code also *"Replace one position per pair with uncorrelated exposure"*, *"Favor payers with stronger dividend growth track records"*, *"Size the position to what you can exit in a few days"*. All are removed (PER-4). Uvalu shows the figures; the decision is the user's. Any future "plan my portfolio" or goal-based feature needs a prior legal review, because it would also touch the Belgian rules on financial planning (Law of 25 April 2014).

---

## Update Frequency

What the app recomputes, and when. This replaces the original "Monitoring Cadence" table, which read as a schedule the user should follow ("Full rebalancing review: semi-annually").

| Data | Refresh |
|---|---|
| Risk report (all stages) | On opening the Risk page or Dashboard; reused for up to 1 hour while holdings, targets and quality-screen states are unchanged |
| Comparison snapshot (`prior_snapshot`) | Saved once per calendar day by the Risk page |
| Prices for current value | Live quote at report time |
| Price history (Stages 1, 3, 4, 6) | Disk-cached per ticker, extended as new days arrive |
| Fundamentals (ratings, income stages) | About every 24 h ± 4 h per ticker |
| Fama-French factor data | Cached up to 7 days; a stale copy is flagged with its date when the source is unreachable |

`RiskReport.generated_at` is shown with the report.

---

## Disclosures (DIS-3)

`RiskReport.disclosures` (`RISK_DISCLOSURES`) is shown with every report, in the user's language:
- VaR, CVaR, Monte Carlo and stress-test figures are statistical estimates based on historical data and model assumptions. Real losses can exceed them.
- Historical scenarios replay past market moves; future crises can be larger, longer or different in kind.
- The composite risk score and its bands describe this portfolio's figures on the model's scale. They are not a personal risk assessment and do not say what to do.
- Factor data: Kenneth R. French Data Library (Tuck School of Business, Dartmouth). Its terms of use for a paid service still need checking (DATA-6).

---

> **Cash is out of scope.** The portfolio's cash balance (Cash Management v1,
> `cash.py`) is deliberately excluded from every stage here — HHI, VaR/CVaR,
> factor exposure, stress tests and Monte Carlo run on the invested positions
> only. The Risk page states this in a banner above the report.

---

## Changes from the original spec

| Area | Original (`docs/portfolio_risk_assessment_algorithm.md`) | This version | Req. |
|---|---|---|---|
| Purpose | "measuring, scoring, and managing … actionable rebalancing signals" | Describes the portfolio's risk; never prescribes | PER-4 |
| Overview | Ends in "Action: Rebalance / Monitor / Hold" | Ends in composite score + descriptive observations + disclosures | PER-4 |
| Stage 1 | Valuation flag "Overvalued / Fairly Valued / Undervalued" | "Above / Near / Below model fair value" | REC-2 |
| Stage 3 | VaR = "maximum expected loss"; MDD "assess recovery time" | VaR described as an estimate that can be exceeded; MDD band without an instruction | DIS-3, PER-4 |
| Stage 4 | "→ review stock selection" | Reported as a negative factor tilt | PER-4 |
| Stages 5/7 | `income_portfolio` flag, "income mandate" | `weighting` model setting chosen by the user; never from goals or a questionnaire | PER-3, PER-8 |
| Stage 6 | — | Stress / Monte Carlo disclosure | DIS-3 |
| Stage 7 | Band → action ("Immediate rebalancing required" …) | Band → description; colours mark position on the scale only | PER-4 |
| Stage 8 | Rebalancing Decision: hard/soft triggers + actions; held-veto trigger; "loss tolerance" | Risk observations with level, basis and reference; no actions; held-veto trigger removed; model reference levels | PER-1, PER-4, PER-5 |
| Cadence | Monitoring schedule for the user | What the app recomputes, and when | PER-4 |
| Disclosures | — | `RiskReport.disclosures` with every report | DIS-3 |
