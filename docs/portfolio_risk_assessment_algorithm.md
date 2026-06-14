# Portfolio Risk Assessment Algorithm

A systematic pipeline for measuring, scoring, and managing the risk of a stock portfolio — from individual position risk through to portfolio-level stress testing and actionable rebalancing signals.

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
| **Individual beta** | Regression of stock returns vs market index | > 1.3 = high sensitivity |
| **Stock-level VaR (95%)** | Historical or parametric 1-day loss at 95% confidence | Baseline per position |
| **Valuation risk** | MoS from stock valuation algo (negative MoS = overvalued) | Negative MoS = elevated risk |
| **Dividend sustainability** | Payout ratio, coverage ratio, cut history | Flags income risk |
| **Earnings quality score** | Accruals ratio, FCF vs net income | Low score = red flag |
| **Financial health score** | D/E, interest coverage, current ratio | Low score = red flag |

**Position risk rating:** Each stock is rated Low / Medium / High / Critical based on the aggregated position-level metrics.

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

Map each stock to its primary revenue geography (not just listing country).

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

### 3a. Portfolio Beta

```
Portfolio Beta = Σ (weight_i × beta_i)
```

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

Sortino is preferred for income portfolios as it penalises only downside volatility.

| Sharpe / Sortino | Interpretation |
|---|---|
| > 1.5 | Strong risk-adjusted return |
| 1.0 – 1.5 | Acceptable |
| < 1.0 | Suboptimal — reassess positioning |

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

### Factor Risk Flags

- Factor loading > 1.5 on any single factor → concentrated factor bet
- > 60% of return variance explained by one factor → factor-dominated portfolio
- Unintended negative loading on Profitability or Value → review stock selection

---

## Stage 5 — Dividend & Income Risk

*Apply only to income or dividend-focused portfolios.*

### 5a. Portfolio Dividend Yield

```
Portfolio yield = Σ (weight_i × dividend yield_i)
```

Compare to: risk-free rate, inflation rate, and historical portfolio yield.

### 5b. Weighted Dividend Growth Rate (DGR)

```
Portfolio DGR = Σ (dividend income_i / total portfolio income × DGR_i)
```

A portfolio DGR above inflation preserves real purchasing power of income.

### 5c. Income Stability Score

For each dividend payer, score 0–10 based on:
- Years of consecutive dividend payments (10+ = 10 pts)
- Years of consecutive dividend growth (Dividend Aristocrats / Kings = bonus)
- Payout ratio stability (low variance = better)
- FCF coverage consistency

```
Portfolio income stability = Σ (dividend income share_i × stability score_i)
```

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

Replay the portfolio against past market crises using historical return data:

| Scenario | Period | Benchmark drawdown |
|---|---|---|
| Dot-com crash | 2000 – 2002 | −49% (S&P 500) |
| Global financial crisis | 2007 – 2009 | −57% |
| COVID crash | Feb – Mar 2020 | −34% |
| 2022 rate hike cycle | Jan – Oct 2022 | −25% |

For each scenario, compute estimated portfolio drawdown and income impact (if dividend-focused).

### 6b. Hypothetical / Factor Scenarios

| Scenario | Shock applied |
|---|---|
| Rate rise +200 bps | Re-price dividend stocks; sector rotation |
| Recession | Earnings cut 20–30% across cyclical sectors |
| USD strengthening +15% | Impact on international revenue exposure |
| Sector crash (−40%) | Apply to largest sector concentration |
| Credit crunch | Penalise high-leverage stocks |
| Dividend freeze | All dividend payers cut DPS to zero |

### 6c. Monte Carlo Simulation

Run 10,000 simulations of portfolio returns over 1, 3, and 5 years using:
- Expected returns per stock
- Covariance matrix
- Resampled return distributions (to capture fat tails)

Output: distribution of outcomes, probability of loss, expected worst-case outcome at 5th percentile.

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

Suggested default weights (adjust to portfolio mandate):

| Component | Default weight |
|---|---|
| Concentration risk | 25% |
| Volatility risk | 20% |
| Tail risk | 20% |
| Factor risk | 15% |
| Fundamental risk | 15% |
| Income risk | 5% (increase to 20% for income portfolios) |

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

### Hard Rebalancing Triggers (act immediately)

- Any single position > 20% of portfolio
- Portfolio beta > 1.5 (or < 0.5 for defensive mandate)
- 1-day 99% VaR exceeds pre-defined loss tolerance
- > 40% portfolio income from dividend-at-risk positions
- Stress test shows > 40% drawdown in worst-case scenario
- A position breaches a hard veto rule from the stock valuation algorithm

### Soft Rebalancing Triggers (review and plan)

- HHI drift > 0.05 from target since last rebalance
- Any sector weight drifts > 5 pp from target allocation
- Portfolio DGR drops below inflation rate
- Sharpe ratio falls below 1.0 for two consecutive quarters
- A position's risk rating is upgraded from Medium to High

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
