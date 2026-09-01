# Changelog

All notable changes to UV are documented here.

---

## [Unreleased]

### Fixed

- Risk page: the score-gauge caption no longer renders "Moderate risk **risk**" — `composite.label` already carries the "… risk" suffix, the template appended a second one (WP-DQ5).
- Risk page: the **Max drawdown (1Y)** tier word ("Low"/"Moderate"/"High") is now derived from the 1-year drawdown it sits next to, not the 5-year figure — the number said −15% while the label said "High" off the deeper 2022 drawdown. The composite risk score still uses the 5-year drawdown independently (WP-DQ5).
- Dashboard / Screener / Watchlist: the fair-value column and KPI tile are labelled **"Margin of safety"** instead of "Upside" — the value shown has always been `(fair value − price) / fair value`, not raw upside `(fair value / price − 1)`, which differ materially for deep-discount names (WP-DQ2).

### Performance

- Screener: `compute_scores` computes `margin_of_safety` and the `Decision` label with vectorised pandas/NumPy expressions instead of a per-row `df.apply` — bit-identical output, locked by an equivalence test (WP-7). The fair-value models and the composite risk sub-scores stay row-wise (scoring math shared with the risk engine).

---

## [1.2.0] — 2026-08-31

### Performance

Every screen now paints from already-computed data and fills in as background
work lands, instead of blocking the render thread on the screener fetch + scoring
(WP-1…WP-6 of the instant-paint plan).

- **Universe scoring moved off the render thread** — new `uvalu/store.py` (`_UniverseStore`): `_load_all_screener_data()` is now a non-blocking accessor that returns the last-computed per-exchange scored frames immediately and kicks a single background daemon worker when the fundamentals-cache token has moved. The worker runs the `compute_scores` pass **and** the 1–6 live `stockanalysis.com` ticker-list scrapes (`fetch_tickers.py` has no memoisation of its own, so those had been re-running on every render-thread cache miss)
- **Re-score debounce** — `_cache_version()` holds its token steady while a background fetch churns `fundamentals.json`, so a 20–40 min cold fetch triggers ~10 recomputes instead of one per ~20 s cache-file rewrite (`RECOMPUTE_DEBOUNCE_S`)
- **Dashboard / Portfolio / Risk** no longer score the whole enabled-exchange universe just to look up their ~30 holdings — a new `_load_portfolio_scored()` fast path scores only held + sold tickers through the dedicated `PORTFOLIO_FETCH` lane (held tickers on a disabled exchange are covered now too)
- **Version-diffed timed refreshes** — `ui._auto_rerun` / `price_autorefresh` only fire a full rerun when a plain signature (store version, fetch progress, price bucket, portfolio token) has actually changed since the last one, with a `max_idle_ticks` anti-freeze fallback; the dialog-open guard is unchanged
- **Cold-cache loading skeletons** for Screener and Watchlist (`components.loading_skeleton_html` + `ui.poll_while_fetching`) — a still-loading list shows shimmer rows and refreshes itself, instead of a bare "no data" line (Watchlist previously had no auto-refresh at all and looked identical to a genuinely empty watchlist)
- Dropped a dead per-render ~14 MB `fundamentals.json` `json.loads` from the Screener page (the unused `_scr_pf_context` / `open_drawer(pf_context)` path), and made `screener._warm_live_cache` a double-checked lock so two cold-start sessions don't both parse the file

---

## [1.1.0] — 2026-08-30

Valuation + portfolio-risk engine overhaul (WS-1…WS-18): a dedicated market-data
provider, an EUR-consistent quantitative risk engine, and a multi-model fair
value that no longer leans on point-in-time snapshots or sell-side targets.

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
- Settings → Screening & veto rules → **Screening style** (balanced / value / growth / income) — an admin-controlled composite-weight preset threaded through `compute_scores` via `settings.get_score_weights()` (WS-18)
- Screener: **trend-based hard vetoes** (`screener._trend_veto`) — a stock is now vetoed on 3+ straight years of revenue decline, 3 years of negative EBIT, an eroding negative retained-earnings balance, or a dividend cut in the last 2 years while coverage is under 1.5×; surfaced in the drawer/Analysis veto banner and the Analysis "Hard-veto checks" panel (WS-15)

### Changed
- Screener: **PE Fair Value** now uses the stock's own sector-median trailing P/E across the universe (winsorized 6–30×) with a bounded PEG tilt, instead of a flat 15× for every stock; 15× is kept as the small-sample fallback (WS-11)
- Screener: **DDM weight** now ramps continuously with the payout ratio (full across 30–70%, tapering to 0 by 5% / 95%) instead of a hard 5–90% in/out gate — no more fair-value cliff between an 89% and a 91% payer (WS-12)
- Screener: **earnings quality** adds a Sloan accrual ratio `(netIncome − operating cash flow) / totalAssets` alongside the FCF/NI conversion and FCF-history consistency terms (WS-16)
- Screener: **beta** is Blume-adjusted (`0.67 × raw + 0.33 × 1.0`) before it feeds WACC and the market-risk score, de-noising yfinance's trailing single-estimate beta; a beta outside [0.1, 5.0] still falls back to 1.0 (WS-17)
- Screener: each composite sub-score is now a **50/50 blend of its cross-sectional percentile rank and an absolute 0–100 band** (`_blend_ranks` / `_abs_band` / `BLEND_PCT`), so a universe where every stock is overvalued no longer produces a full spread of inflated MoS ranks (WS-14)
- Screener: **default composite weights rebalanced** from `0.30 / 0.18 / 0.22 / 0.15 / 0.15` to `0.24 MoS / 0.22 risk / 0.24 quality / 0.15 momentum / 0.15 dividend` (`screener.W_*` and the `balanced` screening style) — margin of safety now co-leads with quality instead of dominating, and risk is weighted more heavily, so a wide discount can't by itself outvote weak fundamentals; the `value` style keeps the old MoS-led weighting
- Screener: **EPV now capitalises the mean of `ebitHistory`** (`_normalised_ebit`, ≥3yr) instead of a single point-in-time EBIT, so a peak or trough year no longer sets the valuation (review 2.3)
- Screener: **analyst-target weight** cut from 0.208 to 0.130 (freed weight to EPV / Graham) and further scaled down per-stock when the sell-side estimates are widely dispersed (`(targetHighPrice − targetLowPrice) / targetMeanPrice`) or thinly covered (`numberOfAnalystOpinions`) (WS-13)
- All risk metrics computed on EUR-restated price history (was a currency blend)
- Composite score drops the factor slot and renormalises when the Fama-French feed is unavailable, instead of a flat placeholder
- `earnings_quality` blends multi-year FCF-history consistency with the FCF/net-income ratio
- Help page expanded from a column reference into a full in-app guide, with an overview and a section for every page (Dashboard, Portfolio, Risk, Screener, stock details, Settings) alongside the column glossary
- Column reference now documents the Ex-Div Date, Div Date, Sector and Country columns, and their tooltips show on the screener headers

### Docs
- `stock_valuation_algorithm.md` / `portfolio_risk_assessment_algorithm.md` brought fully in sync with the WS-1…WS-18 implementation
- `configuration.md` corrected — stale constant names, the pre-2026 veto list, and composite/risk weight tables that had drifted from the specs; weight and veto tables now reference the algorithm specs instead of duplicating the numbers
- `architecture.md` `formatting.py` entry and the table-density note updated to match the code

### Removed
- `uvalu/formatting.py`: dead `COLUMN_HELP` / `_HINT_WATCHLIST` tooltip dicts and the `fmt_div_flag` / `f_str` helpers (superseded by `help.py`)

---

## [1.0.0] — 2026-07-30

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
