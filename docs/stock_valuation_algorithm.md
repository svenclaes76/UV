# Stock Valuation Algorithm
A systematic pipeline for identifying undervalued stocks and deciding whether they are worth buying.
---
## Stage 1 — Data Collection
Gather financial statements (income statement, balance sheet, cash flow statement), market price, peer group data, and macro indicators (interest rates, sector cycle). Data quality is the foundation — garbage in, garbage out.
**Required inputs:**
- Financial statements (last 3–5 years)
- Current market price
- Peer / comparable company data
- Macro indicators (risk-free rate, sector cycle, inflation)
- Dividend history (DPS per year, last 5–10 years)
- Dividend payout ratio and payout policy
- Ex-dividend dates and payment frequency
---
## Stage 2 — Fair Value Estimation (Multi-Model)
No single model is reliable in isolation. The algorithm runs several in parallel and combines them into a weighted composite.
### Models
| Model | Formula / Approach | Best suited for |
|---|---|---|
| **DCF** | Discount projected free cash flows at WACC + terminal value | Most companies; rigorous but sensitive to assumptions |
| **Comparable multiples** | P/E, EV/EBITDA, P/S vs sector peers | Quick sanity check; penalises contrarian plays |
| **Dividend Discount Model (DDM) — single stage** | Gordon growth: `P = D₁ / (r − g)` | Stable, mature dividend-paying stocks |
| **DDM — multi-stage** | High-growth phase (explicit DPS forecast) + stable terminal phase | Dividend growers with an accelerating early period |
| **Asset-based / P/B** | Book value, Price-to-Book ratio | Banks, capital-heavy businesses, distressed situations |
| **Graham Number** | `√(22.5 × EPS × BVPS)` | Conservative floor / deep value screen |
| **Earnings Power Value (EPV)** | `EPV = EBIT(1 − t) / WACC` | Downside anchor; assumes zero growth |
> **DDM weight guidance:** Assign high DDM weight (30–50%) for stocks with 5+ years of uninterrupted dividends and a payout ratio of 30–70%. Set DDM weight to zero for non-dividend payers or stocks with a payout ratio > 90% (signals unsustainability).
### Dividend-Specific Valuation Checks
Run these alongside the main models for any dividend-paying stock:
| Check | Formula | Signal |
|---|---|---|
| **Dividend yield vs historical average** | `Yield = DPS / Price` | Yield > 5-yr avg → potentially undervalued |
| **Dividend yield vs sector peers** | Compare to peer median | Premium yield may indicate value or distress |
| **Dividend growth rate (DGR)** | `DGR = (DPS_t / DPS_{t-5})^(1/5) − 1` | Consistent DGR > inflation = quality compounder |
| **Payout ratio** | `DPS / EPS` | 30–70% = sustainable; > 85% = at risk |
| **Cash payout ratio** | `DPS × Shares / FCF` | Should be < 80% to ensure FCF covers dividends |
| **Dividend coverage ratio** | `EPS / DPS` | > 1.5× considered safe |
### Weighted Composite Fair Value
Each model is assigned a weight based on how well-suited it is to the specific company. For non-dividend payers, DDM weight is zero and DCF/EPV weights are increased proportionally.
```
Intrinsic Value = Σ (Model weight × Model fair value estimate)
```
The weighted average becomes the **intrinsic value estimate**.
---
## Stage 3 — Margin of Safety & Total Expected Return
### Margin of Safety (MoS)
```
MoS = (Intrinsic Value − Market Price) / Intrinsic Value
```
A stock only enters the buy zone if MoS exceeds a minimum threshold (typically **20–30%**). This buffers against model error and estimation uncertainty.
> The higher the uncertainty in the valuation, the higher the required MoS.
### Total Expected Return (TER)
For dividend-paying stocks, price appreciation alone understates the true return. Compute TER over a 1-year horizon:
```
TER = (Intrinsic Value − Market Price) / Market Price + Dividend Yield
```
Or more precisely, incorporating dividend growth:
```
TER = Capital gain % + Forward dividend yield + Expected DGR
```
| TER range | Interpretation |
|---|---|
| > 15% | Attractive |
| 8–15% | Acceptable |
| < 8% | Unattractive vs risk-free alternatives |
> A stock with a modest MoS (e.g. 15%) but a 5% growing dividend yield can be more attractive than a stock with 25% MoS and no dividend.
### Dividend Sustainability Flag
Before proceeding, apply a hard check on dividend sustainability:
- Payout ratio > 90% → flag as **at risk**
- Cash payout ratio > 80% → flag as **at risk**
- Dividend coverage ratio < 1.2× → flag as **at risk**
- DPS cut in last 5 years → flag as **history of cuts**
Flagged stocks require a higher MoS threshold (+5–10 pp) to compensate.
---
## Stage 4 — Risk Scoring
Each dimension is scored on a 0–10 scale and aggregated into a composite risk score. High risk penalises the final composite score.
| Dimension | Key metrics |
|---|---|
| **Financial health** | Debt/equity, interest coverage, current ratio |
| **Earnings quality** | Accruals ratio, FCF vs reported net income |
| **Market risk** | Beta, sector cyclicality, macro sensitivity |
| **Qualitative** | Competitive moat, management track record, ESG flags |
| **Growth & momentum** | Revenue CAGR, EPS trend, analyst revisions |
| **Dividend risk** | Payout ratio, cash payout ratio, DPS cut history, DGR consistency |
| **Liquidity / concentration** | Market float, average daily volume |
---
## Stage 5 — Composite Score
```
Score = α × MoS − β × Risk + γ × Quality + δ × Momentum + ε × DividendScore
```
Where `DividendScore` combines: dividend yield vs historical average, DGR consistency, payout ratio safety, and dividend coverage ratio (each sub-scored 0–10).
The weights reflect your investment style:
- **Value investor** → higher α (MoS) weight
- **Growth investor** → higher γ (Quality) and δ (Momentum) weight
- **Income / dividend investor** → higher ε (DividendScore) weight; penalise non-payers or DPS cut history
> Calibrate weights by backtesting against historical data.
---
## Stage 6 — Decision
| Score | Action |
|---|---|
| High (e.g. > 70) | **Strong buy** |
| Mid (40–70) | **Monitor / watch list** |
| Low (< 40) | **Avoid** |
### Hard Veto Rules
The following conditions trigger an automatic **avoid** regardless of score:
- Negative free cash flow for 3+ consecutive years
- Debt/equity ratio > 5×
- Active fraud investigation or accounting restatement
- Imminent covenant breach or liquidity crisis
- Dividend cut in current or prior fiscal year with no recovery plan disclosed
---
## Algorithm Summary
```
Data collection (financials + dividend history + macro indicators)
    ↓
Fair value estimation
  (DCF + Comps + DDM single-stage + DDM multi-stage + Graham + EPV)
    ↓
Weighted intrinsic value estimate
  (DDM weight 30–50% for established dividend payers; 0% for non-payers)
    ↓
Margin of Safety = (Intrinsic Value − Price) / Intrinsic Value
Total Expected Return = Capital Gain % + Forward Yield + Expected DGR
Dividend Sustainability Flag (payout ratio, cash payout, coverage ratio)
    ↓
Risk scoring (7 dimensions incl. Dividend Risk)
    ↓
Composite Score = α×MoS − β×Risk + γ×Quality + δ×Momentum + ε×DividendScore
    ↓
Strong Buy | Monitor | Avoid
```
