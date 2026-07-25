# Uvalu User Guide

## Getting started

### Registration and login

On first launch, navigate to the app's URL and register an account with your
email and a password. The first account created is automatically assigned
the **Admin** role; every subsequent account defaults to **Analyst** unless
an admin invites them with a different role.

Roles: **Admin** (full access + the Admin portal), **Analyst** (full
read/write access), **Viewer** (read-only — Buy/Sell/Edit/Add-dividend
controls are shown disabled).

Your session is maintained via a JWT token stored in the browser. Sessions
expire after 24 hours, after which you are prompted to log in again.

---

## Shell

A dark top bar replaces the old sidebar: the logo, horizontal navigation
(Dashboard/Screener/Watchlist/Portfolio/Risk), a live-data indicator, and an
avatar menu (Settings, Help & docs, Admin portal — admin role only, Sign
out). The **Analysis** deep-dive page and the **Admin portal** are
deliberately not in the main navigation — Analysis is reached from a stock's
preview drawer, Admin from the avatar menu.

---

## Dashboard

The home screen after login — a real-time snapshot of your portfolio.

**KPI strip** — Current value (with gain %/€), Total return (price gain plus
dividends), Fwd income / yr (estimated forward 12-month dividend income;
falls back to Dividends received if yield data is missing), Avg fair value
upside (average margin of safety across your holdings).

**Portfolio value over time** — a range-selectable (1M/3M/6M/1Y/All) chart
with optional S&P 500 / Euro Stoxx 50 overlays rebased to the same amount
invested.

**Conviction & risk** — a gauge showing the portfolio-value-weighted mean
signal score across scored holdings, next to the portfolio risk score
(Low/Moderate/Elevated) with Beta, Volatility and Max drawdown.

**Holdings · price vs fair value** — one row per position with its signal
badge and a compact price-vs-fair-value bar. Click a row to open the stock
preview drawer.

**Bottom row** — Sector allocation (donut), Upcoming dividends, Top movers today.

---

## Screener

One unified, ranked list across every exchange enabled in the Admin portal's
Data feeds section (Brussels, Amsterdam, Paris, Milan, Frankfurt, Swiss).

**Columns** — Company, Ticker, Market, Signal, Score, MoS %, Price, P/E, Div
Yield. Every column is sortable by clicking its header.

**Decision signal** — each stock receives BUY / MONITOR / AVOID based on its
composite score (0–100) *and* its margin of safety, both checked against the
thresholds set in Settings → Screening & veto rules:
- **BUY** — composite score ≥ BUY threshold (default 70) **and** margin of
  safety ≥ the configured minimum (default 0%).
- **MONITOR** — composite score ≥ 40.
- **AVOID** — composite score < 40, or a hard veto below.

A stock receives a hard veto regardless of score if: Debt/Equity exceeds the
configured maximum (default 500%), free cash flow is negative, or the
dividend is flagged "At Risk" with coverage below 1.0×.

**Filter bar** — Search (ticker or name), Signal chips (All/Buy/Monitor/
Avoid), Sector select, Market select, Min score slider, Min margin-of-safety
slider, Hide-positions-I-own toggle. **Reset filters** clears everything;
**Export list** downloads the currently filtered rows as CSV.

For the full valuation and scoring methodology, see
[stock_valuation_algorithm.md](stock_valuation_algorithm.md).

---

## Watchlist

A standalone page for tickers you're tracking but don't hold. Add one via
the ★ toggle in any stock's preview drawer, or type a ticker directly into
the form at the top of the page (works for any market, not just the enabled
exchanges). The results table mirrors the Screener's columns; use the
**Remove tickers** expander to take stocks off the list.

---

## Portfolio

An **overview** page (5-card summary strip + a preview of each area) with
**"View all →"** links that drill into a full page for Open positions,
Closed positions, or Dividends. Prices refresh automatically (interval
configurable in Settings), and a daily value snapshot is recorded with an
automatic back-fill of missing trading days.

### Open positions

- Toolbar: **View** (optional column groups), **Buy**, **Edit**
  (shares/amount/date, or tick 🗑️ to delete), **Sell** (records shares and
  proceeds, moves the position to Closed).
- Click a row to open the stock preview drawer.
- Charts (tabbed): Performance (gain/loss treemap + P&L per position), Value
  history (with a **Rebuild history** button), Breakdown (sector/country/
  position donut and allocation bar).

### Closed positions

Realised trades — Invested, Proceeds, Price Gain, Dividends, Price Gain %,
and annualised Annual Return % (CAGR). **Edit** to correct or delete rows.

### Dividends

Cards: Total received, Current holdings, Expected 12 months, Portfolio
yield. **Add** / **Edit** individual payments, filter by year. The history
table shows Gross, Tax (30% — a Belgian withholding-tax estimate), and Net.

---

## Risk

The top of the page is always visible: a composite score gauge (0–100,
higher = riskier) with its label and recommended action, a 6-metric grid
(Beta, Volatility, VaR 95%, Sharpe, Max drawdown, Positions), any
hard/soft rebalancing triggers, a risk factor breakdown (Fama-French
5-factor + momentum), a concentration card (single-name/sector/country bars
against real 15%/30%/60% limits — naming the actual breaching position when
one exceeds its limit), and a risk-contribution-by-holding table.

**Composite score breakdown**

| Sub-score | Weight |
|---|---|
| Concentration | 25% |
| Volatility | 20% |
| Tail risk | 20% |
| Factor exposure | 15% |
| Fundamental | 15% |
| Income risk | 5% |

Toggle **Income mode** to weight the analysis toward dividend-income risk.
The report is cached for one hour (or until the portfolio changes) — use
**Refresh** to force a rebuild.

**Five deeper analysis tabs** below the always-visible section:
Volatility & VaR, Factor Exposure, Income Risk, Stress Tests, Monte Carlo.

For the full risk methodology, see
[portfolio_risk_assessment_algorithm.md](portfolio_risk_assessment_algorithm.md).

---

## Stock preview drawer & Analysis page

Clicking a row in any table opens a slide-in **preview drawer**: signal
badge, price/fair-value/margin-of-safety hero, a hard-veto banner when
applicable, the six-model fair-value ladder, key metrics, and a footer
action (Buy, or Sell if held).

**View full analysis** opens the full **Analysis** page: 4-card hero, a
1-year price-vs-fair-value chart, signal sub-scores (the five weighted
components behind the composite), the six-model fair-value table, a
financials grid, a hard-veto checklist, and a short value thesis.

---

## Settings

Available to every user — user/workspace administration lives in the
**Admin portal** instead.

- **Display** — Theme follows Streamlit's own app-menu setting; Table
  density affects card-based lists (native data tables use a fixed row
  height); Display currency and Number format are shown but not yet
  configurable (EUR only for now).
- **Screening & veto rules** — Max debt/equity, Max dividend payout, Target
  margin of safety, and BUY score threshold sliders drive every BUY/MONITOR/
  AVOID decision app-wide; a Euro Stoxx 50 benchmark default; an
  (unavailable) US-listed toggle.
- **Alerts & data** — four notification preferences (stored only — there's
  no email/push delivery in this app yet) and the portfolio price
  auto-refresh interval.
- **Import & export** — upload an Excel file to replace your portfolio data
  (expected sheets: `Positions`, `Sold`, `Dividends`), or download a
  human-readable Excel workbook.

---

## Admin portal

Reached from the avatar menu, not the main navigation — Admin role only.

- **Users** — stats strip, search, inline role selector (Admin/Analyst/
  Viewer), status badge, Suspend/Reactivate, and a ⋯ menu to delete an
  account. **Invite user** creates a real *Invited* account with a one-time
  temporary password shown on screen (no outbound email exists) — the
  status flips to *Active* on their first successful login.
- **Data feeds** — enable/disable exchanges included in the Screener and
  portfolio analysis. No live health/latency monitoring exists.
- **Backups** — every entry is a real, on-demand snapshot (this app has no
  scheduler — all entries are typed *Manual*). Create, download, or restore
  a previous snapshot (restoring overwrites current data).

---

## Help

The in-app Help page contains the same guidance as this document, plus a
full column reference glossary organised by column group.
