# Expert Profile: Quant / Data Scientist

**Project:** Uvalu — stock screening and portfolio tool for solo retail investors
**Priority:** High — needed before any backtest or performance claim is shown

---

## Why Uvalu needs this expert

Uvalu combines valuation signals with a portfolio risk framework (HHI concentration, VaR, CVaR, maximum drawdown, Sharpe/Sortino, Fama-French Developed 5-factor + momentum exposure, historical and hypothetical stress scenarios) and risk bands. If backtests are used to show that signals "work", they must be free of the classic biases, or they will mislead users and create regulatory risk. Data quality from the vendor also has to be measured, not assumed.

## Required expertise

- Quantitative finance background (MSc/PhD in quantitative finance, statistics, econometrics, or a comparable track record in a quant team)
- Rigorous **backtesting methodology**: point-in-time data, avoiding **look-ahead bias** (reporting lags, restated fundamentals), **survivorship bias** (delisted stocks), transaction costs, rebalancing rules, out-of-sample and walk-forward testing, multiple-testing / overfitting control
- Risk modelling: historical vs. parametric vs. Monte Carlo VaR and CVaR, factor models (Fama-French), concentration measures, correlation estimation
- **Data-quality engineering**: missing values, splits and dividends adjustments, currency handling, outlier detection, cross-checking vendors
- Strong Python (pandas, NumPy, statsmodels) — able to read and review Uvalu's code directly

## Scope of review

1. **Data audit:** completeness and accuracy of prices and fundamentals (Yahoo Finance today, EODHD planned); corporate-action adjustments; availability of delisted tickers and point-in-time fundamentals
2. **Backtest design:** universe definition, signal timing, fundamental reporting lags, costs, benchmark choice
3. **Bias checks:** explicit tests for look-ahead and survivorship bias
4. **Statistical validity:** significance, stability over regimes, overfitting risk from threshold tuning
5. **Risk framework:** correctness of VaR/CVaR, factor regressions, stress-scenario assumptions (replayed vs. beta-estimated drawdowns, hypothetical shocks)
6. **Risk-band thresholds:** whether the Low / Moderate / Elevated / High / Critical bands (0–25 / 25–50 / 50–70 / 70–85 / 85–100) are calibrated, stable and explainable
7. **Monitoring:** automated data-quality checks and alerts in the data pipeline

## Expected deliverables

- Data-quality report with concrete defects and mitigation
- Backtest protocol (written spec) and review of any existing backtest results
- Code review notes on the risk framework with corrections
- Calibrated risk-band thresholds with rationale
- Plain-language summary of what backtests can and cannot claim (input for marketing and the methodology page)

## Material to prepare

- `docs/portfolio_risk_assessment_algorithm.md` and `risk.py`
- `docs/stock_valuation_algorithm.md` and `screener.py` (signal logic)
- Access to the data store or sample extracts
- Any existing backtest notebooks and results

## Questions to ask when selecting

- How would you get point-in-time fundamentals from an end-of-day vendor?
- How do you handle delisted companies in a backtest?
- What is your approach to preventing overfitting when tuning thresholds?

## Red flags

- Shows impressive backtest returns without discussing biases
- Only machine-learning experience, no financial time-series work
- Cannot review Python code directly

## Where to find

- Quant freelancers (via professional networks, Toptal-type platforms)
- University quantitative-finance departments (KU Leuven, UGent, UAntwerpen) — researchers or PhD students
- Former risk/quant staff at Belgian banks and asset managers
