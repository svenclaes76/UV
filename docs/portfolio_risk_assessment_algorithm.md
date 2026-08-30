# Portfolio Risk Assessment Algorithm

A systematic pipeline for measuring, scoring, and managing the risk of a stock portfolio — from individual position risk through to portfolio-level stress testing and actionable rebalancing signals.

Implemented in [`risk.py`](../risk.py); `assess_portfolio(pf_df, cache, income_portfolio, veto_lookup, targets, prior_snapshot) → RiskReport`. Build `pf_df` with [`portfolio_enrichment.enrich_for_risk()`](../portfolio_enrichment.py). Time-series data (price history, dividends, FX, Fama-French factors) comes through [`marketdata.py`](../marketdata.py), disk-cached under `.cache/{history,dividends,factors}/`.

### Implementation notes (what the engine actually does now)

- **Everything is EUR.** `risk._to_eur` restates each holding's native-currency close series in EUR (per-ticker `Currency` from the fundamentals cache, FX from `marketdata.fx_to_eur_frame`) *before* any metric is computed, so `port_rets` is never a currency blend.
- **Betas are regressed**, not taken from yfinance. `risk._resolve_betas` runs an OLS of each holding's own EUR daily returns on `BENCHMARK_TICKER` (`^STOXX50E`, euro-denominated) over the trailing window (≥ 60 aligned obs); falls back to the cached yfinance `beta`, then 1.0. `PositionRisk.beta_source` records which. `QuantMetrics.portfolio_beta_regression` adds the direct OLS of `port_rets` on the benchmark as a cross-check.
- **10-year fetch, 5-year quant.** `assess_portfolio` fetches a 10y window; Stages 1/3/4 run on the trailing-5y slice, Stage 6 gets the full series (for crisis-window replay).
- **Factor set:** Developed 5-factor + momentum first, US Fama-French as an automatic fallback; parsed frames are disk-cached weekly with a stale-copy fallback when the network is down (`risk._factor_data`).
- **Targets / snapshot:** when `targets` (per-user `portfolio.load_targets()`) or `prior_snapshot` (`portfolio.load_risk_snapshot()`, one per calendar day) are supplied, Stage 8 switches the relevant soft triggers from absolute levels to drift-vs-target / drift-since-snapshot.

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
Stage 5 — Dividend & income risk (for income portfolios)
    ↓
Stage 6 — Stress testing & scenario analysis
    ↓
Stage 7 — Composite portfolio risk score
    ↓
Action: Rebalance | Monitor | Hold
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
| **Valuation risk** | MoS from stock valuation algo (negative MoS = overvalued) | Negative MoS = elevated risk |
| **Dividend sustainability** | Payout ratio, coverage ratio, **DPS cut in last 3 complete years** (`scoring._dividend_sustainability_flag`) | Flags income risk |
| **Earnings quality score** | FCF-to-net-income conversion blended with `fcfHistory` consistency (`scoring._earnings_quality_score`) | Low score = red flag |
| **Financial health score** | D/E, interest coverage, current ratio (`scoring._financial_health_score`) | Low score = red flag |

**Position risk rating:** Each stock is rated Low / Medium / High / Critical from weight, beta, MoS, financial-health and earnings-quality (`_position_rating`). Days-to-liquidate does *not* feed the rating (it surfaces as its own Stage 8 soft trigger), so the composite is unaffected by it.

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

### 2e. Dividend Concentration (Income Portfolios)

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

Estimate the maximum expected loss over a given time horizon at a confidence level.

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
| > 25% | High — assess recovery time |

### 3f. Sharpe & Sortino Ratios

```
Sharpe = (Portfolio return − Risk-free rate) / Portfolio volatility
Sortino = (Portfolio return − Risk-free rate) / Downside deviation
```

Sortino is preferred for income portfolios as it penalises only downside volatility. Because downside deviation is ≤ total volatility by construction, Sortino runs structurally higher than Sharpe for the same portfolio, so the two carry **separate label bands** (`risk._sharpe_label` / `_sortino_label`):

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
- Unintended negative loading on Profitability or Value → review stock selection

---

## Stage 5 — Dividend & Income Risk

*The `income_portfolio` flag only raises this stage's weight in the composite (Stage 7); the metrics are computed for every portfolio.*

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

Weights (`risk._W_DEFAULT` / `_W_INCOME`, selected by the `income_portfolio` flag):

| Component | Default | Income mandate |
|---|---|---|
| Concentration risk | 25% | 20% |
| Volatility risk | 20% | 15% |
| Tail risk | 20% | 15% |
| Factor risk | 15% | 10% |
| Fundamental risk | 15% | 20% |
| Income risk | 5% | 20% |

**Factor unavailable:** when the Fama-French feed can't be fetched or built, the factor slot is *dropped* and the remaining five weights are renormalised — a flat placeholder score no longer drags every portfolio toward the middle.

### Score Interpretation

| Risk score | Rating | Action |
|---|---|---|
| 0 – 25 | Low risk | Hold; monitor quarterly |
| 26 – 50 | Moderate risk | Review annually; minor rebalancing |
| 51 – 70 | Elevated risk | Active monitoring; targeted rebalancing |
| 71 – 85 | High risk | Immediate rebalancing required |
| 86 – 100 | Critical risk | Defensive repositioning — reduce exposure |

---

## Stage 8 — Rebalancing Decision

`risk._stage8_rebalance(..., targets, prior_snapshot)`. Each `RebalanceItem` carries a `mode`: `absolute` (level check), `drift` (vs a target or the prior snapshot), or `transition` (a rating change). Hard triggers are always absolute.

### Hard Rebalancing Triggers (act immediately)

- Any single position > 20% of portfolio
- Portfolio beta > 1.5
- 1-day 99% VaR > 3% of portfolio value
- > 40% portfolio income from dividend-at-risk positions
- Worst historical scenario implies > 40% portfolio drawdown
- A position under a hard veto from the stock valuation algorithm, or a Critical risk rating

### Soft Rebalancing Triggers (review and plan)

Drift-aware when the data exists, absolute otherwise:

| Trigger | With `targets` / `prior_snapshot` | Fallback |
|---|---|---|
| Sector | drift vs `targets["sectors"]` > 5 pp | largest sector > 30% |
| Per-name | drift vs `targets["tickers"]` > 5 pp | (hard 20% cap only) |
| HHI | vs `targets["hhi_max"]` ceiling; **and** drift since the snapshot > 0.05 | 0.10 / 0.18 bands |
| Sharpe | below 1.0 for a *second consecutive* review (snapshot) | below 1.0 once |
| Risk rating | upgrade into High/Critical vs the snapshot (`mode = transition`) | current High rating |
| Days to liquidate | > 10 trading days at 20% of ADV | — |
| DGR | weighted portfolio DGR < 2.5% | (same) |
| Correlation | holding pairs with correlation > 0.80 | (same) |

The per-user target allocation is edited under **Settings → Target allocation**; the snapshot is upserted once per calendar day by the Risk page.

### Rebalancing Actions

| Issue | Action |
|---|---|
| Position overweight | Trim to target weight; redeploy to underweights |
| Sector overconcentration | Reduce highest-weight sector; add to lagging sectors |
| High beta in downturn | Rotate into low-beta / defensive stocks |
| Income concentration | Diversify dividend income across more payers |
| Factor overexposure | Add positions with offsetting factor loadings |
| Low diversification | Add uncorrelated assets or sectors |

---

## Monitoring Cadence

| Activity | Frequency |
|---|---|
| Position risk ratings update | Monthly |
| Concentration metrics (HHI, sector, geo) | Monthly |
| Quantitative metrics (VaR, vol, beta) | Monthly |
| Factor exposure analysis | Quarterly |
| Stress testing & Monte Carlo | Quarterly |
| Full composite risk score | Quarterly |
| Hard trigger checks | Continuous / real-time alerts |
| Full rebalancing review | Semi-annually or after major market events |
