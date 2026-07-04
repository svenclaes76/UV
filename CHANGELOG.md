# Changelog

All notable changes to UV are documented here.

---

## [Unreleased]

### Changed
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
