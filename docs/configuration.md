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

The TLS certificate and key are auto-generated on first launch by `run_app.py` using Python's `ssl` module. They are self-signed and valid for `localhost` only.

To use a real certificate (e.g. from Let's Encrypt), replace the paths and values accordingly.

---

## Admin settings (shared)

Stored in `data/settings/shared.json`. Managed via the Settings page (admin role required).

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled_exchanges` | list of strings | All 6 exchanges | Controls which exchange tabs appear in the screener. Valid values: `"Brussels"`, `"Amsterdam"`, `"Paris"`, `"Milan"`, `"Frankfurt"`, `"Swiss"`. |

---

## Screener constants

Defined in `screener.py`. Edit the file directly to change defaults.

| Constant | Default | Description |
|---|---|---|
| `CACHE_TTL_HOURS` | `24` | Base TTL for fundamentals cache entries (hours). A ±4 h random jitter is added per ticker to spread cache expiry. |
| `MAX_WORKERS` | `4` | Number of parallel yfinance requests for batch fundamentals fetch. Increase with caution — yfinance rate-limits aggressively. |
| `FETCH_DELAY` | `0.5` | Seconds to wait between ticker requests within a worker. |
| `RISK_FREE_RATE` | `0.03` | Risk-free rate used in EPV and DDM fair value models (3%). |
| `EQUITY_RISK_PREMIUM` | `0.05` | Equity risk premium used in discount rate calculation (5%). |
| `DDM_STABLE_GROWTH` | `0.02` | Terminal growth rate in the 2-stage DDM model (2%). |

**Composite score weights:**

| Component | Weight |
|---|---|
| Margin of Safety rank | 30% |
| (100 − Risk rank) | 18% |
| Quality rank | 22% |
| Momentum rank | 15% |
| Dividend rank | 15% |

**Hard veto rules (score overridden to Avoid regardless of composite score):**
- Debt/Equity ratio > 5×
- Free cash flow < 0
- Dividend coverage ratio < 1.0×

---

## Risk assessment constants

Defined in `risk.py`.

| Constant | Default | Description |
|---|---|---|
| `VAR_CONFIDENCE` | `0.95` | Confidence level for parametric Value-at-Risk calculation. |
| `MONTE_CARLO_PATHS` | `10_000` | Number of simulation paths in Monte Carlo analysis. |
| `MONTE_CARLO_DAYS` | `252` | Horizon for Monte Carlo simulation (trading days). |
| `PRICE_HISTORY_YEARS` | `5` | Years of daily price history fetched for volatility and drawdown calculations. |

**Stress test scenarios:**

| Scenario | Assumed market drawdown |
|---|---|
| Dot-com crash (2000–2002) | −49% |
| Global financial crisis (2008) | −57% |
| COVID crash (2020) | −34% |
| 2022 rate shock | −25% |

Each position's drawdown is estimated as `market_drawdown × position_beta`.

**Composite risk score weights:**

| Sub-score | Default weight | Income-mode weight |
|---|---|---|
| Concentration | 25% | 20% |
| Volatility | 20% | 15% |
| Tail risk | 20% | 15% |
| Factor exposure | 15% | 10% |
| Fundamental | 15% | 15% |
| Income risk | 5% | 25% |

Income mode is activated automatically when dividend income constitutes a significant share of the portfolio's expected return.

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

To disable an exchange, go to **Settings → Screener exchanges** (admin only).

---

## Session and token settings

Defined in `auth.py`.

| Setting | Value | Description |
|---|---|---|
| JWT algorithm | HS256 | HMAC-SHA256 |
| JWT TTL | 24 hours | Sessions expire after 24 hours of inactivity |
| Password hashing | bcrypt | Cost factor 12 |
