<!--
Uvalu public legal page. Status: FINAL TEXT, pending counsel review and the [TBD] items listed in README.md.
Rewritten from the implementation, not the original draft: the draft listed DCF and EV/EBITDA models (not implemented),
"Near fair value"/"Overvalued" labels and a different composite.
Source of truth: screener_compliant.methodology(), risk_compliant.REF_* / RISK_BANDS / RISK_DISCLOSURES,
docs/legal/stock_valuation_algorithm_compliant.md, docs/legal/portfolio_risk_assessment_algorithm_compliant.md.
The in-app page must be rendered from methodology() so the numbers cannot drift; this file is the reference text.
Update it in the same release as any model or threshold change.
Counsel points: signal labels "Neutral"/"Low score" deviate from BDG-1 on purpose (see algorithm-compliance-review.md §2);
whether "Undervalued" still counts as Uvalu's own "opinion" under MAR.
Requires before launch: shared min_mos default raised from 0% to 10% in code (stated here as 10%).
Other IDs: REC-2..7, REC-10, DIS-3, DIS-4.
-->

# Methodology

**Version:** 1.0 · **Last updated:** 1 January 2027 · **Model version:** [TBD: MODEL_VERSION AT LAUNCH]

This page explains how Uvalu calculates fair values, scores, model signals and risk figures. Everything described here is a model output: an estimate based on public data and assumptions. It is not a fact and not personal advice.

## 1. Principles

- **Same for everyone.** Every stock is scored with the same formulas and the same settings for every user. Your holdings, income, goals and risk tolerance are not used, and the stocks you add yourself do not change anyone's results.
- **Transparent.** Each result shows the models behind it, the inputs used and when it was calculated.
- **Shared settings.** The thresholds and weights below are set centrally by Uvalu and are the same for all users. The values in force are always shown on this page.
- **Automated.** Results are calculated by formulas. No analyst reviews individual stocks.

## 2. Facts and estimates

| Shown as fact | Shown as estimate |
| --- | --- |
| Reported financial figures, prices, dividends paid | Fair value, margin of safety, composite score, model signal, implied return |
| Share counts, currency rates | Growth rates, discount rates, normalised earnings |
| Your own portfolio entries | VaR, CVaR, Monte Carlo ranges, stress tests, factor exposures, risk score |

Facts come from third parties and can still contain errors. See the Data sources page.

## 3. Valuation models

Each model produces a fair value per share. A model is skipped when its required inputs are missing or when it does not suit the company; the stock page shows which models were used and why the others were not.

**Discount rate.** Models that discount future income use a cost of equity of 3% (risk-free rate) + beta × 5% (equity risk premium). Beta is taken from the data provider, adjusted two-thirds of the way towards the market average of 1.0, and replaced by 1.0 when it is missing or outside 0.1–5.0.

| Model | What it does | Main inputs | Default assumptions | Not used when |
| --- | --- | --- | --- | --- |
| Graham Number | Conservative value from earnings and book value: square root of 22.5 × earnings per share × book value per share | Earnings per share, book value per share | Multiplier 22.5 | Earnings or book value zero or negative; real estate and financial companies |
| Price/earnings value | Earnings per share × the median price/earnings ratio of the company's sector, adjusted for earnings growth | Earnings per share, sector P/E, earnings growth | Sector multiple limited to 6–30×; 15× when the sector has fewer than 5 priced peers; growth adjustment limited to 0.7–1.5× | Earnings zero or negative; real estate companies |
| Earnings power value (EPV) | Values current normalised operating earnings with no growth: earnings after tax divided by the cost of capital, minus net debt | Operating earnings (EBIT) of the last 3–4 years, tax rate, cost of capital, net debt, shares outstanding | Normalised EBIT = median (3 years) or trimmed mean (4 or more years); statutory tax rate of the company's country, 25% if unknown | Normalised value negative; real estate and financial companies |
| Dividend model, single stage | Present value of dividends growing at a constant rate | Dividend per share, dividend growth, cost of equity | Growth = historical dividend growth, limited to 0–5% and to at least 3 points below the discount rate | No dividend; payout ratio at or below 5% or at or above 95% |
| Dividend model, multi-stage | Five years of higher dividend growth, then a constant terminal growth | Dividend per share, dividend growth, cost of equity | Growth in years 1–5 limited to 15%; terminal growth 2% | As above |
| Book value (fallback) | Book value per share × the median price/book ratio of the sector | Book value per share, sector P/B | Sector multiple limited to 0.5–4×; 1.5× when the sector has fewer than 5 peers | Only used when none of Graham, P/E and EPV could be calculated; main anchor for banks, insurers and real estate |
| Free cash flow value (fallback) | Free cash flow × 15, minus net debt, per share | Free cash flow, net debt, shares outstanding | Multiple 15× (about a 6.7% free-cash-flow yield) | Only used when none of Graham, P/E and EPV could be calculated; free cash flow negative |

Graham, P/E and book value models are also skipped when the price is below 2% of book value per share, which indicates that the per-share data is unreliable.

Uvalu does not use analyst price targets. Discounted cash flow (DCF) and EV/EBITDA models are not used.

## 4. Fair value and margin of safety

- **Fair value** is a weighted average of the models that could be calculated. Base weights: Graham 17.8%, P/E 15.0%, EPV 20.8%, each dividend model 16.7%. The dividend weights are scaled down when the payout ratio is outside 30–70%, reaching zero at 5% and 95%. The fallback models weigh 10% each. Weights of models that could not be calculated are spread over the others.
- **Sanity check.** If the weighted fair value is more than twice the price while at most one model supports such a high value, the fair value is set to the median of the models (never below the price), and this is flagged.
- **Basis.** When fewer than two independent models are behind the fair value, it is flagged as thin.
- The stock page shows each model's value next to the fair value, as a sign of uncertainty.
- **Margin of safety** = (fair value − current price) ÷ fair value. A positive figure means the price is below the model's fair value.
- **Implied return (estimate)** = gap between price and fair value + dividend yield + assumed dividend growth (limited to 0–10%, halved when a dividend model contributed). It holds only if the fair value and the dividend assumptions are right. It is not an expected or promised return.

## 5. Composite score

The composite score runs from 0 to 100. Each component is first turned into a sub-score from 0 to 100, which is half the stock's percentile rank among all covered stocks and half a fixed absolute scale. The weights are:

| Component | Weight | What it measures |
| --- | --- | --- |
| Margin of safety | 24% | Distance between price and model fair value |
| Risk | 22% | Financial health, earnings quality, market risk (beta), dividend risk and trading liquidity; lower risk scores higher |
| Quality | 24% | Return on equity and assets, operating margin, free-cash-flow yield, current ratio |
| Momentum | 15% | Earnings growth and revenue growth |
| Dividend | 15% | Yield against its 5-year average, payout and cash payout ratios, dividend cover, dividend growth; non-payers get a neutral value |

These are the "balanced" weights currently in force. Uvalu can switch all users at once to one of the other published weightings below. The weighting in force is always shown on this page.

| Weighting | Margin of safety | Risk | Quality | Momentum | Dividend |
| --- | --- | --- | --- | --- | --- |
| Balanced (in force) | 24% | 22% | 24% | 15% | 15% |
| Value | 38% | 18% | 26% | 6% | 12% |
| Growth | 16% | 14% | 28% | 34% | 8% |
| Income | 20% | 20% | 16% | 6% | 38% |

When fewer than 20 stocks are available for comparison, the score is flagged as based on a small peer group.

## 6. Model signals

A model signal summarises the result in one label. It describes where the stock stands on the model's scale. It does not tell you what to do.

| Signal | Meaning | Rule |
| --- | --- | --- |
| **Undervalued** | High model score with the price clearly below a well-supported model fair value | Composite score ≥ 70, margin of safety ≥ 10%, and fair value based on at least two independent models |
| **Neutral** | Middle of the model's scale, or a high score without a confirmed margin of safety | Composite score from 40 to below 70; or ≥ 70 without the other conditions for Undervalued |
| **Low score** | Low on the model's scale | Composite score below 40. This does not by itself mean the price is above fair value. |
| **Fails quality screen** | One or more exclusion criteria apply, whatever the valuation; the composite score is set to 0 | Any of: debt/equity above 500% (not applied to financial, real estate and utility companies); negative free cash flow in the 3 latest years; dividend at risk with dividend cover below 1.0×; revenue falling for 3 or more years in a row; negative operating earnings in the 3 latest years; negative and further declining retained earnings for 2 or more years; a dividend cut in the last 2 years with cover below 1.5×; no trading volume |
| **No signal** | Not enough comparison data to rank the stock yet | — |

A dividend is "at risk" when the payout ratio is above 90%, the cash payout ratio is above 80%, dividend cover is below 1.2×, or the dividend was cut in the last 3 years.

**Time horizon.** The models value a business on its current fundamentals and assume a multi-year holding horizon. They say nothing about short-term price movements.

**Current distribution.** The share of covered stocks per signal is shown live on this page in the app and updated with every recalculation.

## 7. Updates and history

- Prices are end-of-day closing prices, refreshed once per trading day.
- Fundamentals are refreshed about every 24 hours.
- Signals are recalculated whenever new data arrives. Each signal shows the date and time of calculation and the date of the price used.
- Each stock page shows the history of signal changes for at least the past 12 months.
- Every result carries the model version and a code for the settings used, so a past signal can be reproduced on request.
- Changes to models or thresholds are listed in the change log below and announced in the app when material.

## 8. Sensitivity and limits of the models

Small changes in assumptions can change the result a lot. For example, with a 2% growth rate, raising the discount rate from 8% to 9% lowers a dividend-model fair value by about 14%.

Known limits:

- Models rely on reported figures, which can be restated, delayed or wrong.
- Past cash flows and earnings may not continue.
- The models suit some businesses poorly, such as banks, insurers, early-stage and cyclical companies.
- The models ignore information outside the financial statements, such as litigation, management changes or new competitors.
- The risk-free rate and equity risk premium are fixed assumptions and do not follow market rates.
- Currency effects: fair values are calculated in the currency in which the share is quoted. Portfolio figures are converted to euro with European Central Bank reference rates.

## 9. Portfolio risk analytics

These figures describe the portfolio you entered. They do not judge whether it suits you and do not say what you should do. Cash is excluded.

| Measure | What it shows | Method |
| --- | --- | --- |
| Concentration (HHI) | How much the portfolio depends on a few positions | Sum of squared position weights |
| Value at Risk (VaR) | Estimated loss exceeded on only 5% (or 1%) of days | Historical, from the portfolio's daily returns in euro over the past 5 years; parametric when there is too little history. Confidence 95% and 99%, horizon 1 day |
| Conditional VaR (CVaR) | Average loss on the days beyond the VaR level | Same settings as VaR |
| Volatility, drawdown, Sharpe and Sortino ratios | Size and pattern of past fluctuations | Daily returns in euro over the past 5 years; risk-free rate 3% |
| Beta | Sensitivity to the EURO STOXX 50 | Weighted average of position betas, and a direct regression |
| Factor exposures | Sensitivity to market, size, value, profitability, investment and momentum factors | Regression of the portfolio's daily excess returns on the Fama-French Developed markets factors |
| Stress tests | Effect of past crises and hypothetical shocks | Replay of four historical periods (2000–2002, 2007–2009, 2020, 2022) where the history allows, otherwise beta × index fall; five hypothetical shocks |
| Monte Carlo simulation | Range of possible portfolio values | 10,000 simulated paths; resampling of 20-day blocks of the portfolio's own returns with an expected return of 3% + beta × 5%; horizons 1, 3 and 5 years |
| Composite risk score | Summary of the figures above on a 0–100 scale | Bands: Low (0–25), Moderate (25–50), Elevated (50–70), High (70–85), Critical (85–100) |

**Reference levels.** The risk page notes when a figure passes one of these model reference levels. They are not limits and not your personal tolerance, which Uvalu does not know.

| Figure | Reference level |
| --- | --- |
| Single position weight | above 20% |
| Concentration (HHI) | above 0.10 (moderate) and 0.18 (high) |
| Portfolio beta | above 1.5 |
| Estimated 1-day 99% VaR | above 3% of portfolio value |
| Income from dividends at risk | above 40% of dividend income |
| Worst historical scenario | fall worse than −40% |
| Sharpe ratio | below 1.0 |
| Weighted dividend growth | below 2.5% |

VaR, CVaR, Monte Carlo and stress-test figures are statistical estimates based on historical data and model assumptions. Real losses can exceed them. Historical scenarios replay past market moves; future crises can be larger, longer or different in kind.

## 10. Historical performance of signals

Uvalu does not publish performance figures for its signals.

## 11. Who produces this

Signals and valuations are produced by Sven Claes, sole trader trading as Uvalu, enterprise number [TBD: ENTERPRISE NUMBER — not yet registered], Belgium. Uvalu is not an investment firm and is not authorised or supervised by the FSMA to provide investment services. See also the Conflicts of interest page.

## 12. Change log

| Date | Model version | Change |
| --- | --- | --- |
| 1 January 2027 | [TBD: MODEL_VERSION AT LAUNCH] | First published version |
