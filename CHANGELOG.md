# Changelog

All notable changes to UV are documented here.

---

## [Unreleased]

### Added
- Screener: **multi-year statement history** (`screener._statement_history`) — annual revenue, EBIT, net income, operating cash flow, retained earnings and total assets pulled per ticker on each 24h refresh, groundwork for trend-based vetoes, accrual-aware earnings quality and a normalised EPV (WS-10)
- **`marketdata.py`** — single yfinance wrapper: disk-cached daily price history (`.cache/history/`, incremental tail refetch), dividend payment history (`.cache/dividends/`), and EUR FX rates
- **`scoring.py`** — the shared 0–10 fundamental scorers, extracted from `screener.py` (which re-exports them); the risk engine no longer imports `screener.py`'s private namespace
- **`portfolio_enrichment.py`** — `enrich_for_risk()` builds the frame `risk.assess_portfolio` expects
- Risk engine: per-holding **beta regressed** against `^STOXX50E` (yfinance fallback), realised per-position volatility, and a days-to-liquidate liquidity check
- Risk engine: **true dividend growth rate** from DPS history feeds TER and the dividend scores; dividend-sustainability flag adds a "DPS cut in the last 3 years" check; `IncomeRisk.income_stability` score, wired into the composite
- Risk engine: Fama-French **Developed** 5-factor + momentum set (US fallback), disk-cached with a stale-copy fallback when offline
- Risk engine: historical stress scenarios **replay the held basket's real drawdown** when history covers the window; Monte Carlo is now a block bootstrap re-centred on a CAPM drift
- Risk engine: **drift-vs-target** rebalancing triggers — set a target allocation under Settings → Target allocation and a daily risk snapshot enables sector/name/HHI drift, two-period Sharpe, and rating-transition signals
- Settings → **Target allocation** editor (personal sector / per-name weights + HHI ceiling)

### Changed
- Screener: **PE Fair Value** now uses the stock's own sector-median trailing P/E across the universe (winsorized 6–30×) with a bounded PEG tilt, instead of a flat 15× for every stock; 15× is kept as the small-sample fallback (WS-11)
- Screener: **DDM weight** now ramps continuously with the payout ratio (full across 30–70%, tapering to 0 by 5% / 95%) instead of a hard 5–90% in/out gate — no more fair-value cliff between an 89% and a 91% payer (WS-12)
- Screener: **earnings quality** adds a Sloan accrual ratio `(netIncome − operating cash flow) / totalAssets` alongside the FCF/NI conversion and FCF-history consistency terms (WS-16)
- All risk metrics computed on EUR-restated price history (was a currency blend)
- Composite score drops the factor slot and renormalises when the Fama-French feed is unavailable, instead of a flat placeholder
- `earnings_quality` blends multi-year FCF-history consistency with the FCF/net-income ratio
- Help page expanded from a column reference into a full in-app guide, with an overview and a section for every page (Dashboard, Portfolio, Risk, Screener, stock details, Settings) alongside the column glossary
- Column reference now documents the Ex-Div Date, Div Date, Sector and Country columns, and their tooltips show on the screener headers

---

## [1.0.0] — 2026-06-14

### Added
- Multi-exchange screener covering 750+ stocks across Brussels, Amsterdam, Paris, Milan, Frankfurt, and Swiss exchanges
- 6-stage valuation algorithm: Graham Number, PE Fair Value, EPV, DDM (1-stage & 2-stage), Analyst Target
- Composite score (0–100) with Strong Buy / Monitor / Avoid signals
- Portfolio tracker with live pricing, unrealised P&L, and benchmark comparison (S&P 500, Euro Stoxx 50)
- Dashboard with KPI cards, performance treemap, sector allocation, and top movers
- Realised positions with annualised return (CAGR)
- Dividend history tracking with tax estimate
- 8-stage portfolio risk assessment: concentration, volatility, VaR, factor exposure, stress tests, Monte Carlo simulation
- Multi-user authentication with JWT sessions and role-based access (admin / user)
- Per-user encrypted data storage (Fernet)
- Watchlist across all exchanges
- Admin panel: user management, exchange toggles, backup & restore, Excel import
- Export to Excel (Positions, Sold, Dividends, Watchlist)
- Self-signed TLS for localhost HTTPS
