# UV Architecture

## Overview

UV is a single-process Streamlit application. All logic runs server-side in Python; the browser renders Streamlit's output and a small amount of custom HTML/CSS for the sidebar. There is no separate backend API — page routing, authentication, data access, and business logic are all handled within `app.py` and supporting modules.

---

## File structure

```
UV/
├── app.py                  # Entry point — routing, UI, page controllers
├── run_app.py              # Launcher (generates self-signed TLS cert, starts Streamlit)
├── auth.py                 # Authentication (register, login, JWT verify)
├── portfolio.py            # Portfolio persistence and CRUD
├── screener.py             # 6-stage valuation algorithm and scoring
├── prices.py               # Live price fetching via yfinance
├── risk.py                 # 8-stage portfolio risk assessment
├── settings.py             # User and shared settings I/O
├── crypto.py               # Symmetric encryption (Fernet)
├── backup.py               # Export/import (ZIP, Excel)
├── fetch_tickers.py        # Stock universe loader (6 exchanges)
├── requirements.txt
├── .env                    # Secrets — never committed
├── .streamlit/
│   └── config.toml         # TLS cert paths
├── .ssl/                   # Auto-generated self-signed certs
├── .cache/
│   ├── users.json          # User account store
│   └── fundamentals.json   # Screener fundamentals cache
├── data/
│   ├── portfolio/{hash}/   # Per-user portfolio data (encrypted JSON)
│   └── settings/           # Per-user and shared settings (encrypted JSON)
└── docs/
```

---

## Module responsibilities

### `app.py`

The main Streamlit entry point. Responsibilities:
- Reads `?page=` query parameter to route between pages
- Renders the sidebar navigation (custom HTML to avoid widget flashing)
- Calls the appropriate page controller function
- Manages `st.session_state` for auth tokens, cached data, and UI state
- Contains all page-level UI code (tables, charts, forms)

Page controllers: `show_dashboard()`, `show_screener()`, `show_portfolio()`, `show_risk()`, `show_settings()`, `show_help()`

### `auth.py`

Email/password authentication with JWT sessions.

- `register(email, password)` — hash password with bcrypt, store in `.cache/users.json`. First user becomes admin.
- `login(email, password)` — verify bcrypt hash, issue HS256 JWT (24 h TTL, signed with `AUTH_SECRET`).
- `verify_token(token)` → `(email, role)` — validate JWT signature and expiry.
- `list_users()`, `set_role()`, `delete_user()` — admin helpers.

The JWT is persisted in browser `localStorage` via a hidden iframe bridge and reloaded on each page refresh into `st.session_state`.

### `portfolio.py`

Encrypted JSON persistence for all per-user portfolio data.

- `set_user(email)` — derives the user's data directory path from `SHA256(email)`.
- `load_portfolio()` / `save_portfolio()` — open positions as DataFrame ↔ `portfolio.json`.
- `add_position()`, `update_positions()`, `remove_positions()` — CRUD on open positions.
- `sell_position()` — move a position to `sold.json`, compute CAGR.
- `add_dividend()`, `update_div_hist()` — dividend record management.
- `load_value_history()`, `record_value_snapshot()`, `backfill_value_history()` — daily portfolio value snapshots for the time-series chart (backfill uses yfinance 5Y price history).

All files are read and written through `crypto.py`.

### `screener.py`

6-stage valuation pipeline run once per exchange per cache cycle.

1. Fetch fundamentals from yfinance (batched, 4 workers, 0.5 s delay between requests).
2. Compute fair value estimates: Graham Number, PE Fair Value, EPV, DDM 1-stage, DDM 2-stage, Analyst Target.
3. UV Fair Value = equal-weighted average of available model outputs.
4. Compute Margin of Safety (MoS) and Total Expected Return (TER).
5. Score each dimension (financial health, earnings quality, market risk, dividend risk, liquidity) as a 0–100 percentile rank within the exchange universe.
6. Composite Score = 30% MoS rank + 18% (100 − Risk rank) + 22% Quality rank + 15% Momentum rank + 15% Dividend rank.

Results are cached in `.cache/fundamentals.json` with a per-ticker TTL of 24 h ± 4 h jitter. Cache is refreshed in a background thread so the UI stays responsive.

### `prices.py`

Fetches live prices for all portfolio tickers in a single `yfinance.download()` call.

Returns per-ticker: current price, previous close, day change %, and volume.

### `risk.py`

8-stage portfolio risk assessment. See [portfolio_risk_assessment_algorithm.md](portfolio_risk_assessment_algorithm.md) for full methodology.

Stage summary:
1. Position risk profiling (weight, beta, VaR, valuation flag, dividend sustainability)
2. Concentration analysis (Herfindahl index, top-N weights, sector/country concentration)
3. Quantitative metrics (portfolio beta, annual volatility, max drawdown, correlation matrix)
4. Factor exposure (sector-beta aggregation)
5. Dividend risk (payout sustainability, income concentration)
6. Stress tests (4 historical scenarios)
7. Monte Carlo simulation (10,000 paths, 252 days)
8. Composite risk score (weighted sub-scores) + rebalancing signals

### `crypto.py`

Symmetric encryption using Fernet (AES-128-CBC + HMAC-SHA256).

- Key derivation: PBKDF2-SHA256 from `ENCRYPTION_KEY` env var with a fixed salt (required for persistence across process restarts).
- `encrypt_text(plaintext)` / `decrypt_text(ciphertext)` — string-level helpers.
- `read_encrypted(path)` / `write_encrypted(path, data)` — file I/O wrappers used by `portfolio.py` and `settings.py`.

### `fetch_tickers.py`

Builds the stock universe for each exchange.

- Primary: scrapes ticker lists from stockanalysis.com.
- Fallback: hardcoded index constituent lists (BEL 20, AEX 25, CAC 40, FTSE MIB, DAX 40, SMI 20).
- Returns: list of `{name, isin, ticker, mic}` dicts.

### `backup.py`

- `export_zip()` — bundle all `data/` and `.env` into an encrypted ZIP for offsite backup.
- `export_excel()` — human-readable Excel workbook (sheets: Positions, Sold, Dividends, Watchlist).
- `import_zip()` — restore data from a previously exported ZIP.

### `settings.py`

- `load_shared_settings()` / `save_shared_settings()` — admin settings in `data/settings/shared.json` (e.g. `enabled_exchanges`).
- `load_settings(email)` / `save_settings(email, data)` — per-user settings in `data/settings/{hash}.json` (encrypted).

---

## Data flow

```
Browser
  │
  │  HTTPS (self-signed TLS)
  ▼
app.py (Streamlit)
  │
  ├─ auth.py ──────────────────────► .cache/users.json
  │    JWT → st.session_state
  │
  ├─ screener.py
  │    ├─ fetch_tickers.py ────────► stockanalysis.com (HTTP)
  │    └─ yfinance ───────────────► .cache/fundamentals.json
  │
  ├─ portfolio.py ─────────────────► data/portfolio/{hash}/*.json
  │    └─ crypto.py (encrypt/decrypt)
  │
  ├─ prices.py ───────────────────► yfinance (live prices)
  │
  ├─ risk.py
  │    └─ yfinance (5Y price history)
  │
  └─ settings.py ──────────────────► data/settings/*.json
```

---

## Authentication flow

1. User submits login form → `auth.login()` verifies bcrypt hash → returns JWT.
2. JWT is written to `localStorage` via a hidden iframe `postMessage` bridge.
3. On each Streamlit rerender, a JavaScript snippet reads `localStorage` and writes the token back into a hidden `st.text_input`, which is picked up by `st.session_state`.
4. `auth.verify_token()` validates the JWT on every page load. Expired or invalid tokens redirect to the login screen.

---

## Caching strategy

| Layer | Mechanism | TTL |
|---|---|---|
| Screener fundamentals | `.cache/fundamentals.json` (mtime per ticker) | 24 h ± 4 h jitter |
| Screener DataFrame | `@st.cache_data` | Until manual refresh |
| Live prices | `@st.cache_data` | 5 minutes |
| Risk report | `st.session_state` | 1 hour |
| Value history | `data/portfolio/{hash}/value_history.json` | Daily snapshot |

---

## Security notes

- Passwords are hashed with bcrypt (cost factor 12).
- JWTs are signed HS256 with a 64-char random secret. They are stored in `localStorage`, not cookies, to avoid CSRF exposure.
- All portfolio and settings files are Fernet-encrypted at rest.
- The `.env` file containing secrets must never be committed to version control (add to `.gitignore`).
- The self-signed TLS cert is regenerated on each launch if absent; it is for localhost only and should not be used in production.
