"""Help page — full app guide plus the column reference glossary."""
import streamlit as st

from uvalu.formatting import COLUMN_HELP
from uvalu.runtime import current_user


# ── Column reference sections (each maps to a screener/portfolio column group) ──
_COLUMN_SECTIONS = {
    "Core":             ["★", "Company", "Ticker", "Price", "Analyst Target", "UV",
                         "MoS %", "TER %", "Score"],
    "Valuation":        ["Graham #", "PE Fair Val", "EPV",
                         "DDM (1-stage)", "DDM (2-stage)"],
    "Risk & Size":      ["Risk Score", "Mkt Cap", "Beta", "Debt/Equity"],
    "Multiples":        ["P/E", "P/B", "EV/EBITDA"],
    "Quality":          ["ROE %", "ROA %", "Op Margin %", "FCF Yield %"],
    "Growth":           ["Rev Growth %", "EPS Growth %"],
    "Dividends":        ["Div Yield", "5yr Avg Yield", "Payout Ratio",
                         "Cash Payout", "Div Coverage", "Div Flag",
                         "Ex-Div Date", "Div Date"],
    "Geography":        ["Sector", "Country"],
    "Portfolio Risk":   [],
}

_PORTFOLIO_RISK_ROWS = [
    ("Composite score",   "Weighted aggregate of six sub-scores (0–100, higher = more risk). Sub-scores: Concentration 25%, Volatility 20%, Tail risk 20%, Factor exposure 15%, Fundamental 15%, Income risk 5%."),
    ("Position Weight",   "Position value as a percentage of total portfolio. Above 10% is concentrated; above 15% triggers a hard rebalancing flag."),
    ("Beta",              "Market sensitivity estimated by regression against the benchmark index. Above 1.2 amplifies market swings; below 0.8 is defensive. A portfolio beta above 1.5 triggers a hard flag."),
    ("VaR 95% (1d)",      "Maximum expected 1-day loss at 95% confidence using historical simulation. Interpreted as: on average, only 1 trading day in 20 should lose more than this amount."),
    ("CVaR 95% (1d)",     "Expected Shortfall — the average loss on the worst 5% of days. Captures tail risk that VaR alone understates."),
    ("MDD",               "Maximum drawdown: the largest peak-to-trough decline observed over the measurement period (1y / 3y / 5y windows)."),
    ("HHI",               "Herfindahl-Hirschman Index — sum of squared portfolio weights. Ranges from near 0 (fully diversified) to 1 (single position). Above 0.18 is considered highly concentrated."),
    ("Factor loading",    "Sensitivity of portfolio returns to a systematic risk factor (Fama-French 5-factor model + momentum). A loading above ±1.5 signals a concentrated factor bet."),
    ("R²",                "Fraction of portfolio return variance explained by the factor model. Above 0.6 means the portfolio is predominantly factor-driven rather than stock-specific."),
    ("Alpha",             "Annualised return above what the factor model predicts. Positive alpha suggests stock selection adds value beyond systematic factor exposure."),
    ("Portfolio Yield",   "Total expected annual dividend income divided by current portfolio value. Computed from each holding's dividend rate and share count."),
    ("Weighted DGR",      "Income-weighted dividend growth rate — proxy for how fast the dividend stream is growing. Below ~2.5% means purchasing power of income erodes in real terms."),
    ("Top-3 cut (50%)",   "Stress scenario: income impact if the three largest dividend payers each cut their dividend by 50%. Quantifies income concentration risk."),
    ("Hard trigger",      "A threshold breach that materially increases risk and requires prompt action (e.g. position >20%, portfolio beta >1.5, or a Critical-rated position)."),
    ("Soft trigger",      "An advisory signal worth monitoring and planning around, but not requiring same-day action (e.g. sector overweight, Sharpe below 1.0, or a High-rated position)."),
    ("Monte Carlo P5",    "5th percentile portfolio value after simulating 10,000 random return paths — the worst-case outcome at 5% probability over the stated horizon."),
    ("P(loss)",           "Probability of a negative total return over the simulation horizon, derived from the fraction of Monte Carlo paths that finish below the starting value."),
]


def _help_table(rows: "list[tuple[str, str]]") -> None:
    """Render label/description pairs as a compact markdown table."""
    st.markdown("\n".join(
        ["| Column | Description |", "|:--|:--|"]
        + [f"| `{col}` | {desc} |" for col, desc in rows]
    ))


def _column_reference() -> None:
    """Full column glossary, one tab per section (mirrors the table column groups)."""
    st.caption("Every column that can appear in the Screener and Portfolio tables. "
               "The same descriptions show as tooltips when you hover a column header.")
    tabs = st.tabs(list(_COLUMN_SECTIONS.keys()))
    for tab, (section, cols) in zip(tabs, _COLUMN_SECTIONS.items()):
        with tab:
            if section == "Portfolio Risk":
                _help_table(_PORTFOLIO_RISK_ROWS)
            else:
                _help_table([(col, COLUMN_HELP[col])
                             for col in cols if COLUMN_HELP.get(col)])


def render() -> None:
    """Full-page help: an overview, one section per page, and the column glossary."""
    st.caption("How every part of uvalu works. Pick a section below.")

    _is_admin = current_user().is_admin
    _tab_labels = ["Overview", "Dashboard", "Portfolio", "Risk", "Screener",
                  "Watchlist", "Stock details", "Settings", "Column reference"]
    if _is_admin:
        _tab_labels.append("Admin portal")
    _tabs = st.tabs(_tab_labels)
    _t = dict(zip(_tab_labels, _tabs))

    # ── Overview ──────────────────────────────────────────────────────────────
    with _t["Overview"]:
        st.markdown("""
#### What uvalu does

uvalu screens European stocks for value and tracks your own portfolio against
the same fair-value models. It combines up to six intrinsic-value estimates
(Graham number, PE fair value, EPV, two DDM variants, analyst target) into a
single **Fair Value** and a 0–100 **Score**, then lets you follow the
positions you own, the dividends they pay, and the risk they carry.

#### The pages

| Page | What it's for |
|:--|:--|
| **Dashboard** | Portfolio overview: KPI strip, conviction/risk gauge, holdings vs fair value, sector allocation, movers, dividends. |
| **Screener** | One ranked list across your enabled exchanges — search, filter by signal/sector/market, and adjust the score/MoS sliders. |
| **Watchlist** | Tickers you don't hold yet, added via the ★ toggle on any stock or typed in directly. |
| **Portfolio** | An overview with "View all" drill-downs into Open positions, Closed positions and Dividends — each with full add/edit/sell. |
| **Risk** | Composite score, factor breakdown, concentration and per-holding risk contribution, plus five deeper analysis tabs. |
| **Settings** | Display preferences, the screening/veto-rule thresholds, alerts, and portfolio import/export. |
| **Admin portal** *(admin only)* | Users, Data feeds (enabled exchanges) and Backups — reached from the avatar menu, not the main nav. |

#### A typical workflow

1. **Screen** — open **Screener** and sort by Score or MoS % to find undervalued stocks.
2. **Inspect** — click any row to open the quick-preview **drawer**; click **View full analysis** for the full **Analysis** page (valuation, price history, sub-scores, financials).
3. **Track** — buy a position from the drawer, Screener, Dashboard or Portfolio; it then appears on the **Dashboard**.
4. **Monitor risk** — check the **Risk** page for concentration, factor exposure and rebalancing triggers.
5. **Review income** — track received and expected dividends from Portfolio's Dividends drill-down.

Almost every table is interactive: **click a row to open its stock preview drawer**,
and hover any column header to see what it means. The full glossary lives in the
**Column reference** tab.
""")

    # ── Dashboard ─────────────────────────────────────────────────────────────
    with _t["Dashboard"]:
        st.markdown("""
#### Dashboard

A one-screen summary of the portfolio you hold. If you have no portfolio yet, it
points you to the Screener or to **Settings → Import & export**.

**KPI strip** — Current value (with gain %/€), Total return (incl. dividends),
Fwd income / yr (estimated forward 12-month dividend income; falls back to
Dividends received if yield data is missing), and Avg fair value upside
(average margin of safety across your positions).

**Portfolio value over time** — a range-selectable (1M/3M/6M/1Y/All) value
chart with optional **S&P 500** / **Euro Stoxx 50** overlays rebased to the
same amount invested (the Euro Stoxx default is set in Settings).

**Conviction & risk** — a gauge showing the portfolio-value-weighted mean
signal score across scored holdings, plus the portfolio risk score banded
Low/Moderate/Elevated with Beta, Volatility and Max drawdown underneath.

**Holdings · price vs fair value** — one row per position with its signal
badge and a compact price-vs-fair-value bar.

**Bottom row** — Sector allocation (donut), Upcoming dividends (next
ex-dividend dates among your holdings), and Top movers today.
""")

    # ── Portfolio ─────────────────────────────────────────────────────────────
    with _t["Portfolio"]:
        st.markdown("""
#### Portfolio

An **overview** page — a 5-card summary strip (Invested, Current value, Total
return, Dividends, Positions held) and a preview of each area — with
**"View all →"** links that drill into a full page for each. Prices refresh
automatically (interval configurable in Settings), and a daily value snapshot
is recorded with an automatic back-fill of any missing trading days.

**Open positions** (full page)
- Toolbar: **View** (optional column groups — see *Column reference*),
  **Buy**, **Edit** (shares/amount/date, or tick 🗑️ to delete), **Sell**
  (records shares and proceeds, moves the position to Closed).
- Click any row to open the stock preview drawer.
- Charts (tabbed): **Performance** (gain/loss treemap — total or daily —
  plus P&L per position), **Value history** (with a **Rebuild history**
  button), and **Breakdown** (sector/country/position donut and allocation bar).

**Closed positions** (full page) — realised trades with Invested, Proceeds,
Price Gain, Dividends, Price Gain % and an annualised **Annual Return %**
(CAGR over the holding period). **Edit** to correct or delete rows.

**Dividends** (full page)
- Cards: Total received, Current holdings, Expected 12 months, Portfolio yield.
- **Add** / **Edit** individual payments and filter the history by year.
- The history table shows Gross, **Tax (30%)** and Net — a Belgian
  withholding-tax estimate.
- Charts: total received per stock, and dividends by year.

Use **"← Back to overview"** at the top of any drill-down to return.
""")

    # ── Risk ──────────────────────────────────────────────────────────────────
    with _t["Risk"]:
        st.markdown("""
#### Risk

The top of the page is always visible (not a tab): a **composite score**
gauge (0–100, higher = riskier) with its label and recommended action, a
6-metric grid (Beta, Volatility, VaR 95%, Sharpe, Max drawdown, Positions),
any **hard triggers** (act now) / **soft triggers** (review and plan), a
**risk factor breakdown** (Fama-French 5-factor + momentum loadings) next to
a **concentration** card (single-name/sector/country bars against their real
15%/30%/60% limits, naming the actual breaching position when one exceeds
its limit), and a **risk contribution by holding** table (click a row to open
its preview drawer).

Toggle **Income mode** to weight the analysis toward dividend-income risk.
The report is cached for one hour (or until the portfolio changes) — use
**Refresh** to force a rebuild.

**Five deeper analysis tabs** below the always-visible section:
- **Volatility & VaR** — portfolio beta, annual volatility, Sharpe & Sortino,
  VaR/CVaR at 95% and 99%, max drawdown over 1/3/5y, and a return-correlation
  heatmap.
- **Factor Exposure** — Fama-French 5-factor (+ momentum) loadings, R² and
  annualised alpha.
- **Income Risk** — portfolio yield, annual income, weighted dividend growth
  rate, and a "top-3 payers cut 50%" stress scenario.
- **Stress Tests** — historical crisis replays (beta-adjusted) and
  hypothetical shock scenarios (rate rise, recession, sector crash, credit
  crunch).
- **Monte Carlo** — 10,000 simulated return paths over 1/3/5 years, shown as
  a fan chart with P5/median/P95 and probability-of-loss.

Each tab has a **Methodology** popover explaining exactly how its numbers are
computed. The *Column reference → Portfolio Risk* tab is a glossary of these metrics.
""")

    # ── Screener ──────────────────────────────────────────────────────────────
    with _t["Screener"]:
        st.markdown("""
#### Screener

One unified, ranked list across every exchange enabled in the Admin portal's
Data feeds (Brussels, Amsterdam, Paris, Milan, Frankfurt, Swiss).

**Reading the table** — Company, Ticker, Market, Signal (BUY/MONITOR/AVOID),
Score, MoS %, Price, P/E and Div Yield — every column is sortable by clicking
its header. Click any row to open the stock preview drawer.

**Filter bar**
- **Search** by ticker or company name.
- **Signal chips** — All / Buy / Monitor / Avoid.
- **Sector** and **Market** selects.
- **Min score** and **Min margin of safety** sliders.
- **Hide positions I own** toggle.
- **Reset filters** clears everything back to defaults; **Export list**
  downloads the currently filtered rows as CSV.

A stock only shows as **BUY** when both its composite score *and* its margin
of safety clear the thresholds set in **Settings → Screening & veto rules**
— a high score alone doesn't override a thin margin of safety. While fresh
data is being fetched, the page shows a progress caption and auto-refreshes
until it's ready.
""")

    # ── Watchlist ─────────────────────────────────────────────────────────────
    with _t["Watchlist"]:
        st.markdown("""
#### Watchlist

Tickers you're tracking but don't hold. Add one by opening any stock's
preview drawer and clicking **★**, or type a ticker (e.g. `AAPL`, `7203.T`,
`BP.L`) directly into the form at the top of this page — it works for any
market, not just the enabled exchanges.

The results table shows the same signal/score/valuation columns as the
Screener. Click a row to open its preview drawer. Use the **Remove tickers**
expander to take stocks off your watchlist.
""")

    # ── Stock details ─────────────────────────────────────────────────────────
    with _t["Stock details"]:
        st.markdown("""
#### Stock preview drawer & Analysis page

Clicking a row in any table (Screener, Watchlist, Portfolio, Risk, Dashboard
holdings) opens a slide-in **preview drawer**: the company name and ★
watchlist toggle, ticker and sector, signal badge, price/fair-value/margin-
of-safety hero, a hard-veto banner when applicable, the six-model fair-value
ladder, a few key metrics (Beta, Debt/equity, Risk score, P/E), and a
footer action — **Buy** if you don't hold the stock, or **Sell** if you do.

Click **View full analysis** in the drawer for the full **Analysis** page:
header with signal badge and composite score, a 4-card hero (price, fair
value, margin of safety, your position), a 1-year price-vs-fair-value chart,
**signal sub-scores** (the five weighted components behind the composite —
margin of safety, risk, quality, momentum, dividend), the six-model
fair-value table, a financials & valuation grid, a hard-veto checklist, and
a short value-thesis summary.
""")

    # ── Settings ──────────────────────────────────────────────────────────────
    with _t["Settings"]:
        st.markdown("""
#### Settings

Available to every user — user/workspace administration lives in the
**Admin portal** instead (avatar menu, admin role only).

- **Display** — Theme follows Streamlit's own app-menu setting (top-right
  **⋮ → Settings → Theme**); Table density affects card-based lists like the
  Dashboard holdings rows (native data tables use a fixed row height);
  Display currency and Number format are shown but not yet configurable
  (EUR only for now).
- **Screening & veto rules** — Max debt/equity, Max dividend payout, Target
  margin of safety and BUY score threshold sliders drive every BUY/MONITOR/
  AVOID decision across the whole app; a Euro Stoxx 50 benchmark default and
  an (as yet unavailable) US-listed toggle. Changes here immediately re-score
  the shared screener cache.
- **Alerts & data** — four notification preferences (stored, but nothing
  sends them yet — there's no email/push delivery in this app) and the
  portfolio price auto-refresh interval.
- **Import & export** — upload an Excel file to replace your portfolio data,
  or download a human-readable Excel workbook (positions, dividends, sold
  history, watchlist).
""")

    # ── Column reference ──────────────────────────────────────────────────────
    with _t["Column reference"]:
        _column_reference()

    # ── Admin portal (admin only) ──────────────────────────────────────────────
    if _is_admin:
        with _t["Admin portal"]:
            st.markdown("""
#### Admin portal

Reached from the avatar menu (top right), not the main navigation — visible
only to Admin-role accounts.

- **Users** — stats strip, search, an inline role selector (Admin/Analyst/
  Viewer) and status badge per row, Suspend/Reactivate, and a ⋯ menu to
  delete an account. **Invite user** creates a real account with status
  *Invited* and a one-time temporary password shown on screen — there's no
  outbound email, so share it with them yourself. The password resets to
  *Active* the moment they first log in with it.
- **Data feeds** — enable or disable exchanges included in the Screener and
  portfolio analysis. There's no live health/latency monitoring; this only
  reflects the enabled/disabled state.
- **Backups** — every entry is a real, on-demand snapshot (this app has no
  scheduler, so nothing is created automatically — all entries are typed
  *Manual*). **Create backup now**, **Download**, or **Restore** a previous
  snapshot (this overwrites current data — download a fresh backup first if
  you want to keep it).

**Viewer** accounts are read-only: Buy/Sell/Edit/Add-dividend controls are
shown disabled (with a "Viewer role is read-only" tooltip) across Dashboard,
Screener, Portfolio and the preview drawer.
""")
