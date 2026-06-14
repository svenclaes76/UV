# UV User Guide

## Getting started

### Registration and login

On first launch, navigate to `https://localhost:8501` and register an account with your email and a password. The first account created is automatically assigned the **admin** role. Subsequent accounts are assigned the **user** role.

Your session is maintained via a JWT token stored in the browser. Sessions expire after 24 hours, after which you are prompted to log in again.

---

## Dashboard

The dashboard is the home screen after login. It gives a real-time snapshot of your portfolio.

**KPI cards (top row)**
- **Current value** — live market value of all open positions
- **Total invested** — total capital deployed (cost basis)
- **Total return** — unrealised gain/loss including dividends received
- **Avg UV upside** — average margin of safety across holdings vs. UV fair value

**Today's performance (treemap)**
Positions sized by portfolio weight, coloured by day change %. Green = up, red = down.

**Sector allocation**
Donut chart of portfolio weight by GICS sector.

**Portfolio value over time**
Line chart of daily portfolio value vs. two benchmarks: S&P 500 and Euro Stoxx 50. Benchmarks are rebased to your portfolio's starting value for comparison.

**Top movers**
Top 3 gainers and bottom 3 losers by day change %.

**Upcoming dividends**
Stocks in your portfolio with ex-dividend dates in the next 30 days.

**Risk snapshot**
Summary of the four headline risk metrics: portfolio beta, annualised volatility, composite risk score, and maximum drawdown.

---

## Screener

The screener covers 750+ stocks across 6 European exchanges. Select an exchange tab at the top to browse that market.

**Exchange tabs**
| Tab | Exchange | Index |
|---|---|---|
| Brussels | Euronext Brussels | BEL 20 |
| Amsterdam | Euronext Amsterdam | AEX 25 |
| Paris | Euronext Paris | CAC 40 |
| Milan | Borsa Italiana | FTSE MIB |
| Frankfurt | Xetra | DAX 40 |
| Swiss | SIX Swiss Exchange | SMI 20 |
| ★ Watchlist | All exchanges | — |

**Decision signal**
Each stock receives one of three signals based on its composite score (0–100):
- 🟢 **Strong Buy** — score > 70
- 🟡 **Monitor** — score 40–70
- 🔴 **Avoid** — score < 40

A stock can also receive a hard **Avoid** veto regardless of score if: Debt/Equity > 5×, free cash flow is negative, or dividend coverage ratio < 1.0×.

**Core columns**
| Column | Description |
|---|---|
| ★ | Add to / remove from watchlist |
| Company | Full company name |
| Ticker | Exchange ticker symbol |
| Price | Live market price |
| Analyst Target | Consensus 12-month price target |
| 💎 UV Fair Value | UV intrinsic value estimate (average of valuation models) |
| MoS % | Margin of Safety — (Fair Value − Price) / Fair Value |
| TER % | Total Expected Return — price upside + dividend yield |
| Score | Composite score (0–100) |

**Optional column groups**

Toggle additional columns via the **View** button in the toolbar:

- **Valuation** — individual model outputs (Graham, PE Fair Value, EPV, DDM 1-stage, DDM 2-stage)
- **Risk & Size** — beta, market cap, daily volume
- **Multiples** — P/E, P/B, EV/EBITDA
- **Quality** — return on equity, debt/equity, free cash flow yield, interest coverage
- **Growth** — EPS growth, revenue growth
- **Dividends** — yield, payout ratio, dividend coverage, 5-year growth rate

**Filters**
- **Signal** — filter by Strong Buy / Monitor / Avoid
- **Sector** — filter by GICS sector
- **Index members only** — show only constituents of the exchange's headline index

**Toolbar actions**
- **Buy** — add a selected stock to your portfolio
- **Refresh** — clear the fundamentals cache and re-fetch data from yfinance (takes a few minutes)

**Watchlist**
Click ★ on any row to save a stock to your watchlist. The ★ Watchlist tab shows all saved stocks across all exchanges.

For a full explanation of the valuation models and scoring methodology, see [stock_valuation_algorithm.md](stock_valuation_algorithm.md).

---

## Portfolio

The portfolio page has three subtabs: **Positions**, **Realised**, and **Dividends**.

### Positions

A table of all open holdings with live pricing.

**Core columns**
| Column | Description |
|---|---|
| Company | Company name |
| Ticker | Ticker symbol |
| Shares | Number of shares held |
| Buy Date | Date of purchase |
| Live Price | Current market price |
| Invested | Cost basis (shares × avg buy price) |
| Current Value | Live value (shares × live price) |
| Price Gain | Unrealised capital gain/loss (€ and %) |
| Dividends | Total dividends received for this holding |
| Total Return | Price gain + dividends received (%) |

Optional columns (via **View**) include UV Upside %, Analyst Target Upside, and all screener column groups.

**Actions**
- **Buy** — add a new position. Enter ticker, shares, price, and date.
- **Edit** — modify shares, price, or date of an existing position.
- **Sell** — record a sale. The position moves to the Realised tab with computed annualised return.

**Charts**
Below the table:
- **Heatmap** — positions sized by weight, coloured by today's return or total return
- **Portfolio value over time** — daily value with benchmark overlays
- **Sector / Country breakdown** — donut charts
- **Allocation** — bar chart of position weights
- **P&L per position** — bar chart of unrealised gain/loss

### Realised

A table of all closed positions, including:
- Entry and exit dates
- Proceeds vs. cost basis
- Absolute gain/loss
- Annualised return (CAGR)

You can edit or delete realised position records.

### Dividends

A record of all dividend payments received.

| Column | Description |
|---|---|
| Ticker | Stock that paid the dividend |
| Date | Payment date |
| Gross | Gross dividend received |
| Tax (30%) | Estimated withholding tax |
| Net | Net dividend after tax |

**Actions**
- Add or edit dividend records manually
- Filter by year
- Charts showing total dividends received per stock and per year

---

## Risk

The Risk page runs a comprehensive 8-stage analysis of your portfolio and produces a composite risk score from 0 (low risk) to 100 (high risk).

**Composite score breakdown**
| Sub-score | Weight |
|---|---|
| Concentration | 25% |
| Volatility | 20% |
| Tail risk | 20% |
| Factor exposure | 15% |
| Fundamental | 15% |
| Income risk | 5% |

For income-focused portfolios the income risk weight is elevated automatically.

**Position risk table**
Each holding is assessed individually for: portfolio weight, beta, 1-day 95% VaR, valuation flag (over/fair/under vs. UV fair value), dividend sustainability, financial health, earnings quality, and analyst rating.

**Rebalancing signals**
The report flags:
- **Hard triggers** — require action (e.g. single position > 30% of portfolio, sector > 50%)
- **Soft triggers** — worth monitoring (e.g. correlation > 0.85 between two positions)

**Stress tests**
Your portfolio is stress-tested against four historical scenarios:
| Scenario | Market drawdown |
|---|---|
| Dot-com crash (2000–2002) | −49% |
| Global financial crisis (2008) | −57% |
| COVID crash (2020) | −34% |
| 2022 rate shock | −25% |

**Monte Carlo simulation**
10,000 portfolio paths are simulated over a 252-day horizon using lognormal return distributions. The report shows the median, 5th, and 95th percentile outcomes.

For the full risk methodology including formulas and scoring weights, see [portfolio_risk_assessment_algorithm.md](portfolio_risk_assessment_algorithm.md).

---

## Settings

### Admin-only panels

**User management**
Add, edit, or delete user accounts. Assign or change roles (admin / user).

**Screener exchanges**
Toggle which of the 6 exchanges are included in the screener. Disabling an exchange removes it from the tab bar.

**Backup & restore**
Export all user data and the encryption key to an encrypted ZIP file. Restore from a previously exported ZIP.

**Import portfolio**
Upload an Excel workbook to bulk-import positions. Expected sheets: `Positions`, `Sold`, `Dividends`.

### All users

**Export Excel**
Download your portfolio data as a human-readable Excel workbook with separate sheets for Positions, Sold positions, Dividends, and Watchlist.

---

## Help

The Help page contains a full column reference with descriptions of every screener and portfolio column, organised by column group.
