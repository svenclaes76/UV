"""Help page — full app guide plus the column reference glossary."""
import streamlit as st

from uvalu.formatting import COLUMN_HELP


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

    (_t_overview, _t_dashboard, _t_portfolio, _t_risk, _t_screener,
     _t_detail, _t_settings, _t_columns) = st.tabs([
        "Overview", "Dashboard", "Portfolio", "Risk", "Screener",
        "Stock details", "Settings", "Column reference",
    ])

    # ── Overview ──────────────────────────────────────────────────────────────
    with _t_overview:
        st.markdown("""
#### What uvalu does

uvalu screens European stocks for value and tracks your own portfolio against
the same fair-value models. It combines up to five intrinsic-value estimates
into a single **Fair Value** and a 0–100 **Score**, then lets you follow the
positions you own, the dividends they pay, and the risk they carry.

#### The five pages

| Page | What it's for |
|:--|:--|
| **Dashboard** | At-a-glance summary of your portfolio: value, return, risk, movers and dividends. |
| **Portfolio** | Your holdings, realised (sold) positions and dividend history — with full CRUD and charts. |
| **Risk** | Deep portfolio-risk analysis: concentration, VaR, factor exposure, stress tests and Monte Carlo. |
| **Screener** | Browse valued stocks per exchange, filter and sort them, and manage your watchlist. |
| **Settings** | Import/export, backups, enabled exchanges, appearance and (for admins) user management. |

#### A typical workflow

1. **Screen** — open **Screener**, pick an exchange, and sort by Score or MoS % to find undervalued stocks.
2. **Inspect** — click any row to open the **stock detail** dialog (valuation, price history, risk, model estimates).
3. **Track** — buy a position from the Screener or Portfolio page; it then appears on the **Dashboard**.
4. **Monitor risk** — check the **Risk** page for concentration, volatility and rebalancing triggers.
5. **Review income** — track received and expected dividends in **Portfolio → Dividends**.

Almost every table is interactive: **click a row to open its stock detail dialog**, and
hover any column header to see what it means. The full glossary lives in the
**Column reference** tab.
""")

    # ── Dashboard ─────────────────────────────────────────────────────────────
    with _t_dashboard:
        st.markdown("""
#### Dashboard

A one-screen summary of the portfolio you hold. If you have no portfolio yet, it
points you to the Screener or to **Settings → Import**.

**KPI cards (top row)**
- **Current value** — live market value of all holdings, with total gain in % and €.
- **Total return** — price gain plus dividends received, in € and %.
- **Fwd income / yr** — estimated forward 12-month dividend income (dividend yield × current value per holding). Falls back to **Dividends received** if yield data is missing.
- **Avg fair value upside** — average margin of safety across your positions, based on the fair-value estimate.

**Risk banner** — a compact summary of the Risk page: an overall label
(*Low / Moderate / Elevated risk*), the composite score, portfolio beta,
annualised volatility and max drawdown, with a link to the full risk analysis.

**Today's performance** — a treemap of holdings sized by position value and
coloured by today's price change (green up, red down).

**Top movers today** — the seven positions with the largest absolute move today.

**Sector allocation** — a donut of current value grouped by sector.

**Upcoming dividends** — the next ex-dividend dates among your holdings (from the
screener cache; click **Refresh** in the Screener if dates are missing).

**Portfolio value over time** — the full value history, with optional
**S&P 500** and **Euro Stoxx 50** overlays rebased to the same amount invested.
""")

    # ── Portfolio ─────────────────────────────────────────────────────────────
    with _t_portfolio:
        st.markdown("""
#### Portfolio

Three sub-tabs — **Positions**, **Realised**, **Dividends** — with full add/edit/delete.
Prices refresh automatically about once a minute, and a daily value snapshot is
recorded (with an automatic back-fill of any missing trading days).

**Positions**
- Summary cards: **Invested**, **Current value** (with gain), **Dividends**, **Total return**.
- Toolbar:
  - **View** — toggle optional column groups (Valuation, Valuation models, Risk, Multiples, Quality, Growth, Dividends, Geography, Score). See the *Column reference* tab for every column.
  - **Buy** — add a new position (company, shares, buy date, amount invested).
  - **Edit** — change shares / amount / date, or tick 🗑️ to delete positions.
  - **Sell** — close a position by recording shares and proceeds; it moves to **Realised**.
- Click any row to open the stock detail dialog.
- Charts (tabbed): **Performance** (gain/loss treemap — total or daily — plus P&L per position), **Value history** (value vs invested over time, with benchmark overlays and a **Rebuild history** button), and **Breakdown** (sector / country / position donut and allocation bar).

**Realised** — closed positions with **Invested**, **Proceeds**, **Price Gain**,
**Dividends**, **Price Gain %** and an annualised **Annual Return %** (CAGR over
the holding period). Summary cards show positions sold, total invested/proceeds
and realised return. **Edit** to correct or delete sold rows.

**Dividends**
- Cards: **Total received**, **Current holdings**, **Expected 12 months**, **Portfolio yield**.
- **Add** / **Edit** individual dividend payments and filter the history by year.
- The history table shows **Gross**, **Tax (30%)** and **Net** — tax is a Belgian withholding-tax estimate of 30% of gross.
- Charts: total received per stock, and dividends by year.
""")

    # ── Risk ──────────────────────────────────────────────────────────────────
    with _t_risk:
        st.markdown("""
#### Risk

A full portfolio-risk workbench. The top of the page shows a **composite score**
(0–100, higher = riskier) with a label and a recommended action, followed by any
**hard triggers** (act now) and **soft triggers** (review and plan), and a bar
chart of the six sub-scores that make up the composite.

Toggle **Income mode** to weight the analysis toward dividend-income risk. The
report is cached for one hour (or until the portfolio changes); use **Refresh
risk report** on the Rebalancing tab to force a rebuild.

**The eight detail tabs**
- **Positions** — one risk profile per holding: weight, beta, VaR, MoS, valuation, dividend sustainability, financial health, earnings quality and an overall Low/Medium/High/Critical rating.
- **Concentration** — HHI plus top-1/top-3/top-5 weights, and sector & geographic breakdowns with flags for over-concentration.
- **Volatility & VaR** — portfolio beta, annual volatility, Sharpe & Sortino, VaR/CVaR at 95% and 99%, max drawdown over 1/3/5y, and a return-correlation heatmap.
- **Factor Exposure** — Fama-French 5-factor (+ momentum) loadings, R² and annualised alpha.
- **Income Risk** — portfolio yield, annual income, weighted dividend growth rate, and a "top-3 payers cut 50%" stress scenario.
- **Stress Tests** — historical crisis replays (beta-adjusted) and hypothetical shock scenarios (rate rise, recession, sector crash, credit crunch).
- **Monte Carlo** — 10,000 simulated return paths over 1/3/5 years, shown as a fan chart with P5/median/P95 and probability-of-loss.
- **Rebalancing** — an actions table mapping each issue to a concrete next step, with the full hard/soft trigger lists.

Each tab has a **Methodology** expander explaining exactly how its numbers are
computed. The *Column reference → Portfolio Risk* tab is a glossary of these metrics.
""")

    # ── Screener ──────────────────────────────────────────────────────────────
    with _t_screener:
        st.markdown("""
#### Screener

Browse valued stocks one exchange at a time. Tabs are your **Watchlist** first,
then each enabled exchange (Brussels, Amsterdam, Paris, Milan, Frankfurt, Swiss —
configured in **Settings → Screener**).

**Reading the table** — Core columns are always shown: company, ticker, price,
analyst target, **Fair Value**, **MoS %**, **TER %** and a **Score** signal
(BUY > 70 · MONITOR 40–70 · AVOID < 40). Click any row to open the stock detail dialog.

**Toolbar & filters**
- **View** — add optional column groups (Valuation models, Risk, Multiples, Quality, Growth, Dividends, Geography). Added columns are tinted.
- **Sector filter** and **Score filter** popovers narrow the list.
- **Buy** — add any listed stock straight to your portfolio.
- Per exchange: an **index-only** toggle (e.g. BEL 20, AEX, CAC 40, MIB ESG, DAX, SMI), an **unvalued** toggle to include stocks without a fair value, and **Refresh** to rebuild the cache.

**Watchlist** — the first tab collects starred stocks. Add them by opening any
stock's detail dialog and clicking ★, or use **Add** to add a stock by ticker
from any market (e.g. `AAPL`, `7203.T`, `BP.L`).

While fresh data is being fetched, the page shows a progress caption and
auto-refreshes until it's ready.
""")

    # ── Stock details ─────────────────────────────────────────────────────────
    with _t_detail:
        st.markdown("""
#### Stock detail dialog

Opens whenever you click a row in any table (Screener, Portfolio, Risk). The
header shows the company name, ticker, a decision badge (**BUY / MONITOR / AVOID**,
or **VETO** when a hard rule fails) and a **★ watchlist** toggle.

**Four tabs**
- **Snapshot** — key valuation, quality and dividend/growth figures side by side.
- **Price History** — a 2-year price chart with fair-value and analyst-target reference lines.
- **Risk & Fit** — beta, leverage, liquidity and risk score; when opened from a portfolio context it also shows how the stock fits your current sector/country weights.
- **Model Estimates** — a bar chart comparing each valuation model (Graham, PE fair value, DDM, analyst target) against the current price.

Every tab ends with **Signals** — plain-language notes flagged by severity
(**HIGH / NOTE / OK / INFO**) that summarise what the numbers mean.
""")

    # ── Settings ──────────────────────────────────────────────────────────────
    with _t_settings:
        st.markdown("""
#### Settings

What you see depends on your role. Every user has **Export** and **Appearance**;
admins additionally get **Users**, **Screener**, **Backup & Restore** and **Import**.

- **Export** — download a human-readable Excel workbook (positions, dividends, sold history, watchlist), handy for inspection or migration.
- **Appearance** — the theme follows your system preference; override it from the app menu (top-right **⋮ → Settings → Theme**).
- **Users** *(admin)* — add, edit or remove accounts and set roles. The first account created becomes admin automatically.
- **Screener** *(admin)* — choose which exchanges are included in the screener and portfolio analysis.
- **Backup & Restore** *(admin)* — download an **encrypted ZIP** bundling all user data plus the encryption key (needed to restore on another machine), and restore from such a ZIP. Restoring **overwrites** current data — download a backup first.
- **Import** *(admin)* — upload an Excel file to import positions, sold history and dividends. This **replaces** all existing portfolio data for the account.
""")

    # ── Column reference ──────────────────────────────────────────────────────
    with _t_columns:
        _column_reference()
