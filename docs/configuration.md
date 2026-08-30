# UV Configuration Reference

## Environment variables

Stored in `.env` in the project root. Required — the app will not start without them.

| Variable | Type | Description |
|---|---|---|
| `AUTH_SECRET` | 64-char hex | HMAC-SHA256 signing key for JWT tokens. Must be kept secret. |
| `ENCRYPTION_KEY` | 64-char hex | Fernet key for encrypting portfolio and settings files at rest. Must be kept secret. Changing this key makes all existing encrypted files unreadable. |

Generate both with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Run the command twice to get two independent values.

---

## Streamlit configuration

**`.streamlit/config.toml`**

```toml
[server]
sslCertFile = ".ssl/cert.pem"
sslKeyFile  = ".ssl/key.pem"
```

The TLS certificate and key are auto-generated on first launch by `run_app.py` using the `cryptography` library (x509). They are self-signed and valid for `localhost` only.

To use a real certificate (e.g. from Let's Encrypt), replace the paths and values accordingly.

---

## Admin settings (shared)

Stored in `data/settings/shared.json` (Fernet-encrypted), defaults in `settings._SHARED_DEFAULTS`. `enabled_exchanges` is managed in the **Admin portal → Data feeds**; the rest live in **Settings → Screening & veto rules** and are admin-gated there.

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled_exchanges` | list of strings | All 6 exchanges | Which exchanges the screener and portfolio analysis cover. Valid values: `"Brussels"`, `"Amsterdam"`, `"Paris"`, `"Milan"`, `"Frankfurt"`, `"Swiss"`. |
| `max_debt_equity` | float (%) | `500.0` | Hard-veto D/E ceiling (`get_veto_thresholds()`). Sector-exempt for Financials / Real Estate / Utilities. |
| `max_payout` | float (%) | `90.0` | Payout ratio above which a dividend is flagged "At Risk". |
| `min_mos` | float (%) | `0.0` | Minimum margin of safety a stock must clear for a BUY signal. |
| `buy_threshold` | float | `70.0` | Composite score required for a BUY signal. |
| `screen_style` | string | `"balanced"` | Composite sub-score weighting preset (`settings._SCORE_STYLES` / `get_score_weights()`): `balanced`, `value`, `growth`, `income`. |
| `benchmark_stoxx` | bool | `false` | Default state of the Dashboard's Euro Stoxx 50 overlay checkbox. |
| `us_listed_enabled` | bool | `false` | No-op toggle — no US ticker universe exists yet. |

---

## Screener constants

Defined in `screener.py`. Edit the file directly to change defaults.

| Constant | Default | Description |
|---|---|---|
| `CACHE_TTL_HOURS` | `24` | Base TTL for fundamentals cache entries (hours). A ±4 h random jitter is added per ticker to spread cache expiry. |
| `MAX_WORKERS` | `4` | Number of parallel yfinance requests for batch fundamentals fetch. Increase with caution — yfinance rate-limits aggressively. |
| `REQUEST_DELAY` | `0.5` | Seconds to wait between ticker requests within a worker. |
| `RISK_FREE_RATE` | `0.03` | Risk-free rate used in EPV and DDM fair value models (3%). Shared with `risk.py`. |
| `EQUITY_RISK_PREMIUM` | `0.05` | Equity risk premium used in the WACC / discount rate (5%). |
| `DDM_STABLE_GROWTH` | `0.02` | Terminal growth rate in the multi-stage DDM model (2%). |
| `BLUME_WEIGHT` | `0.67` | Blume shrink applied to raw beta before it feeds WACC and market risk (`0.67·raw + 0.33·1.0`). |
| `DEFAULT_TAX_RATE` | `0.25` | EPV tax-rate fallback when `country` is missing / unmapped in `COUNTRY_TAX_RATES`. |
| `MIN_UNIVERSE_SIZE` | `20` | Below this the `small_universe` caveat flag is set on every scored row. |
| `ANALYST_TARGET_HAIRCUT` | `0.10` | Flat discount applied to `targetMeanPrice` before it feeds the composite. |

**Composite score weights** — the `balanced` preset; `settings._SCORE_STYLES` swaps in `value` / `growth` / `income`. Authoritative table and rationale in [stock_valuation_algorithm.md](stock_valuation_algorithm.md) Stage 5.

| Component | Weight (`balanced`) |
|---|---|
| Margin of Safety sub-score (`W_MOS`) | 24% |
| Risk sub-score (`W_RISK`, oriented safer = higher) | 22% |
| Quality sub-score (`W_QUALITY`) | 24% |
| Momentum sub-score (`W_MOMENTUM`) | 15% |
| Dividend sub-score (`W_DIVIDEND`) | 15% |

**Fair-value model base weights** (`W_GRAHAM` / `W_PE` / `W_EPV` / `W_DDM_SINGLE` / `W_DDM_MULTI` / `W_ANALYST`) sum to 1.00 — see the valuation spec Stage 2.

**Hard veto rules** (decision forced to Avoid regardless of composite score) — full definitions in [stock_valuation_algorithm.md](stock_valuation_algorithm.md) Stage 6:
- Static: D/E > `max_debt_equity` (sector-exempt for Financials / Real Estate / Utilities); FCF negative for 3 consecutive fiscal years (single period if <3 yr history); dividend flagged "At Risk" **and** coverage < 1.0×.
- Trend (`_trend_veto`, needs ≥3 yr statement history): 3+ consecutive years of revenue decline; EBIT negative 3 years; retained-earnings erosion; a dividend cut in the last 2 years with coverage < 1.5×.

---

## Risk assessment constants

Defined in `risk.py`.

| Constant | Default | Description |
|---|---|---|
| `MONTE_CARLO_PATHS` | `10_000` | Simulation paths per horizon (1 / 3 / 5 years). |
| `MONTE_CARLO_SEED` | `42` | Fixed seed so Monte Carlo runs are reproducible. |
| `_MC_MIN_OBS` | `60` | Minimum aligned observations to block-bootstrap; below this the Monte Carlo falls back to an iid-Normal draw. |
| `STRESS_HISTORY_PERIOD` | `"10y"` | Price-history window fetched; Stages 1/3/4 run on the trailing-5y slice, Stage 6 gets the full series for crisis-window replay. |
| `BENCHMARK_TICKER` | `"^STOXX50E"` | Euro-denominated benchmark that per-holding betas and `portfolio_beta_regression` are regressed against. |

Parametric VaR uses inline z-multipliers `1.645` (95%) and `2.326` (99%); both confidence levels are reported. VaR / CVaR / max drawdown / Sharpe / Sortino / correlations are otherwise computed from the actual EUR-restated return series, with the parametric formulas as the fallback below ~20 days of history. The risk-free rate is `screener.RISK_FREE_RATE` (3%), shared with the valuation engine.

**Stress test scenarios** (`risk.HISTORICAL_SCENARIOS`):

| Scenario | Window | Benchmark drawdown |
|---|---|---|
| Dot-com crash | 2000-03 – 2002-10 | −49% |
| Global financial crisis | 2007-10 – 2009-03 | −57% |
| COVID crash | 2020-02 – 2020-03 | −34% |
| 2022 rate hike cycle | 2022-01 – 2022-10 | −25% |

When the held basket's own 10-year EUR return series covers a window (≥60% of its business days), that scenario's portfolio drawdown is the basket's real peak-to-trough; otherwise it's `portfolio_beta × benchmark_drawdown`.

**Composite risk score weights** (`risk._W_DEFAULT` / `_W_INCOME`, selected by the `income_portfolio` flag — a manual **Income mode** toggle on the Risk page). Authoritative table in [portfolio_risk_assessment_algorithm.md](portfolio_risk_assessment_algorithm.md) Stage 7.

| Sub-score | Default weight | Income-mode weight |
|---|---|---|
| Concentration | 25% | 20% |
| Volatility | 20% | 15% |
| Tail risk | 20% | 15% |
| Factor exposure | 15% | 10% |
| Fundamental | 15% | 20% |
| Income risk | 5% | 20% |

When the Fama-French feed can't be fetched, the factor slot is dropped and the remaining five weights are renormalised.

---

## Data paths

All paths are relative to the project root and are created automatically on first run.

| Path | Description |
|---|---|
| `.env` | Environment secrets |
| `.ssl/cert.pem` | Auto-generated TLS certificate |
| `.ssl/key.pem` | Auto-generated TLS private key |
| `.cache/users.json` | User account store (bcrypt hashes, roles) |
| `.cache/fundamentals.json` | Screener fundamentals cache |
| `data/portfolio/{hash}/portfolio.json` | Open positions (encrypted) |
| `data/portfolio/{hash}/sold.json` | Realised positions (encrypted) |
| `data/portfolio/{hash}/dividends_history.json` | Dividend payment history (encrypted) |
| `data/portfolio/{hash}/watchlist.json` | Saved tickers (encrypted) |
| `data/portfolio/{hash}/value_history.json` | Daily portfolio value snapshots (encrypted) |
| `data/settings/shared.json` | Admin (shared) settings |
| `data/settings/{hash}.json` | Per-user settings (encrypted) |

`{hash}` is `SHA256(email)[:16]`.

---

## Stock universe

Ticker lists are fetched from [stockanalysis.com](https://stockanalysis.com) at startup and cached for the session. If the fetch fails, hardcoded fallback lists are used.

| Exchange | Approx. stocks | Fallback index |
|---|---|---|
| Brussels | ~125 | BEL 20 (20 stocks) |
| Amsterdam | ~125 | AEX 25 (25 stocks) |
| Paris | ~200 | CAC 40 (40 stocks) |
| Milan | ~150 | FTSE MIB (40 stocks) |
| Frankfurt | ~160 | DAX 40 (40 stocks) |
| Swiss | ~60 | SMI 20 (20 stocks) |

To enable or disable an exchange, go to the **Admin portal → Data feeds** (admin only).

---

## Session and token settings

Defined in `auth.py`.

| Setting | Value | Description |
|---|---|---|
| JWT algorithm | HS256 | HMAC-SHA256 |
| JWT TTL | 24 hours | Fixed expiry from issue time (not a sliding/inactivity window); re-login required after |
| Password hashing | bcrypt | `bcrypt.hashpw` with a per-password salt |
