# UV Architecture

## Overview

UV (uvalu) is a single-process Streamlit application. All logic runs server-side in Python; the browser renders Streamlit's output plus a fair amount of custom raw-HTML/CSS (the top bar, stock-detail drawer, and several rebuilt screens use a dark-navy design-system look layered on top of native Streamlit widgets) and a small amount of JS for the auth bridge. There is no separate backend API — routing, authentication, data access and business logic all run inside the one Streamlit process.

The codebase is split into two layers:

- **Root modules** (`auth.py`, `portfolio.py`, `marketdata.py`, `screener.py`, `scoring.py`, `prices.py`, `risk.py`, `portfolio_enrichment.py`, `settings.py`, `crypto.py`, `backup.py`, `fetch_tickers.py`) — UI-agnostic business logic and persistence. These have no Streamlit page code and can be imported and tested in isolation.
- **The `uvalu/` package** — the Streamlit app shell (`app.py` entry point plus `uvalu/`): page bodies, navigation, the auth gate, the cache-backed data layer, and shared rendering helpers.

`app.py` is a thin shell: it wires up page config, global styles, the auth gate and `st.navigation`, then delegates each page to a `render()` function in `uvalu/pages_/`.

---

## File structure

```
UV/
├── app.py                      # Entry-point shell: page config, styles, auth gate, st.navigation, top bar
├── run_app.py                  # Launcher (generates self-signed TLS cert, starts Streamlit)
│
│   # ── Root modules (UI-agnostic logic + persistence) ──
├── auth.py                     # Authentication (register/invite, login, JWT verify, 3-tier roles + status)
├── portfolio.py                # Per-user portfolio persistence and CRUD (encrypted JSON); targets + risk snapshot
├── marketdata.py               # Single yfinance wrapper: disk-cached daily price history, dividends, FX-to-EUR
├── screener.py                 # Fundamentals fetch + valuation/scoring pipeline (configurable thresholds) + disk cache
├── scoring.py                  # Shared 0–10 fundamental scorers used by both screener.py and risk.py
├── prices.py                   # Live batch price fetching via yfinance
├── risk.py                     # 8-stage portfolio risk assessment
├── portfolio_enrichment.py     # Build the enriched frame risk.assess_portfolio expects (price + scored fields)
├── settings.py                 # User and shared settings I/O; exchange constants; veto-threshold helper
├── crypto.py                   # Symmetric encryption (Fernet)
├── backup.py                   # Export/import (encrypted ZIP, Excel workbook) + on-demand backup history
├── fetch_tickers.py            # Stock-universe loader (6 exchanges, scrape + hardcoded fallback)
│
│   # ── uvalu package (Streamlit app shell) ──
├── uvalu/
│   ├── __init__.py
│   ├── authgate.py             # JWT/localStorage bridges, logout, login wall
│   ├── nav.py                  # Registry of st.Page objects (breaks the app.py↔pages import cycle)
│   ├── shell.py                # Top bar: logo, nav, theme sync, avatar dropdown
│   ├── drawer.py                # Slide-in stock-preview panel (row-click target everywhere)
│   ├── components.py           # Pure-render helpers: signal badges, fair-value ladder, gauges, sparkline
│   ├── runtime.py              # Per-run accessors: current_user(), theme_colors()
│   ├── data.py                 # Cache-backed screener/price/fundamentals data layer
│   ├── formatting.py           # Pure value formatters (fmt_eur, safe_pct)
│   ├── styles.py               # Global CSS injected once per run (native-widget tokens + mockup tokens)
│   ├── ui.py                   # Reusable widgets: click-to-select table, charts, auto-refresh
│   └── pages_/
│       ├── dashboard.py        # Dashboard page render()
│       ├── screener.py         # Screener page render() (unified ranked list + filter bar)
│       ├── watchlist.py        # Watchlist page render()
│       ├── portfolio.py        # Portfolio page render() (overview + Open/Closed/Dividends drill-downs)
│       ├── risk.py             # Risk page render() (always-visible score section + 5 detail tabs)
│       ├── analysis.py         # Stock deep-dive page render() (reached from the drawer)
│       ├── settings.py         # Settings page render() (Display / Screening & veto rules / Alerts & data)
│       ├── admin.py            # Admin portal render() (Users / Data feeds / Backups — admin role only)
│       └── help.py             # Help page render() (app guide + column glossary)
│
├── requirements.txt
├── .env                        # Secrets — never committed
├── .streamlit/config.toml      # TLS cert paths
├── .ssl/                       # Auto-generated self-signed certs
├── .cache/
│   ├── users.json              # User account store
│   └── fundamentals.json       # Screener fundamentals cache
├── data/
│   ├── portfolio/{hash}/       # Per-user portfolio data (encrypted JSON)
│   ├── settings/               # Per-user and shared settings
│   └── backups/                # On-demand backup history (ZIPs + encrypted manifest)
├── tests/
└── docs/
```

---

## Module responsibilities

### App shell

#### `app.py`

The Streamlit entry point and app shell. Responsibilities:

- `st.set_page_config()` and `styles.inject()` for global CSS.
- Runs the auth-gate steps from `uvalu.authgate` (restore token, recover session, logout, login wall) and points the data layer at the current user via `portfolio.set_user()`.
- Builds one `st.Page` per page module, registers them in `uvalu.nav.pages`, and runs `st.navigation(..., position="hidden")`. `analysis` and `admin` are registered but deliberately left out of the visible top-bar nav — reached via the drawer's "View full analysis" link and the avatar dropdown respectively.
- Redirects legacy `?page=` deep-links to the new `st.navigation` URL paths.
- Renders the top bar via `shell.render_topbar()` (replaces the old sidebar).

Page bodies live in `uvalu/pages_/*.py`; each exposes a single `render()` function that `st.navigation` invokes.

#### `uvalu/authgate.py`

The authentication gate, run in order during boot:

- `recover_session_from_cookie()` — when there's no active session, restore one server-side from the `uv_jwt` cookie via `st.context.cookies` (survives a full page reload, e.g. the top bar's theme toggle, with no client-side redirect).
- `handle_logout()` — clear session + query params on `?logout=1`, and expire the `uv_jwt` cookie/localStorage entry.
- `auth_wall()` — verify the session JWT, or render the login form and `st.stop()` if unauthenticated.

#### `uvalu/nav.py`

A tiny module holding `pages: dict[str, st.Page]`. `app.py` builds the pages (it needs each module's `render` callable) and populates the registry at startup; page modules read from it at render time to link to siblings, avoiding an import cycle with `app.py`.

#### `uvalu/runtime.py`

Per-run shared-state accessors that read fresh from `st.session_state` / `st.context` on every call (so pages never bind stale module globals):

- `current_user()` → `CurrentUser(email, role, is_admin, is_viewer)`.
- `theme_colors()` → `ThemeColors` palette tokens resolved from the browser's active light/dark theme, used by all Plotly charts.

#### `uvalu/data.py`

The cache-backed data layer between pages and the root modules — no UI. Key functions:

- `_load_all_screener_data(cache_version, enabled, extra_tickers, extra_names, thresholds)` — `@st.cache_data` builder that returns per-exchange scored DataFrames plus one for extra (portfolio) tickers from disabled exchanges. Busted when `cache_version` (fundamentals file mtime), enabled exchanges, extra-ticker set, or the veto/scoring `thresholds` tuple (from `settings.get_veto_thresholds()`) change.
- `_fetch_prices_cached(tickers)` — batch live prices, `ttl=60s`.
- `_fetch_fundamentals(tickers)` — per-ticker fundamentals + fair-value estimates via `yf.info`, `ttl=6h`.
- `_fetch_live_data(tickers)` — merges fast prices with slower fundamentals.
- `_cache_version()`, `_cache_age_str()`, `_bust_cache()` — cache introspection and invalidation.

#### `uvalu/ui.py`

Reusable, theme-aware rendering helpers:

- `_row_select_table()` — `st.dataframe` with single-row click selection (used everywhere to open the stock-preview drawer via `uvalu.drawer.open_drawer`); a nonce in the widget key prevents the dialog from immediately re-opening after close.
- `_auto_rerun(seconds, key)` — timed page refresh.
- `_static_bar()`, `_donut_chart()`, `_hm_color()` — chart primitives and the treemap colour scale.

#### `uvalu/formatting.py`

Two pure value formatters — `fmt_eur` and `safe_pct`. The old `COLUMN_HELP` / `_HINT_WATCHLIST` tooltip dicts and the `fmt_div_flag` / `f_str` helpers were removed once the Help page moved to a signal-legend/FAQ layout and `help.py` took over column glossary text.

#### `uvalu/styles.py`

`inject()` writes the global brand CSS once per run: the original `--uv-*` widget tokens, the mockup's dark-navy token set (`--bg`, `--panel`, `--text`, `--up-bg`/`--down-bg`, etc.) plus a `[data-theme="light"]` override block, the login screen, and a `[data-density="compact"]` rule that tightens row padding. (The `density` preference is still read and applied, but the Settings UI control for it was removed — see [backend-feature-gaps.md](backend-feature-gaps.md) — so it stays at `comfortable` in practice.)

#### `uvalu/shell.py`

`render_topbar(nav)` — the top bar that replaced `st.sidebar`: logo, horizontal nav links, a live-data dot, and an avatar popover (Settings, Help, "Admin portal" gated on `current_user().is_admin`, Sign out). Also syncs the `data-theme`/`data-density` attributes on the parent document via small hidden `st.iframe` scripts, driven by Streamlit's own active theme and the stored (currently non-editable) density preference.

#### `uvalu/drawer.py`

`open_drawer(row, pf_context)` — the slide-in stock-preview panel opened from every row-click table (Dashboard holdings, Screener, Watchlist, Portfolio, Risk contribution table): compact hero, six-model fair-value list, key metrics, Buy/Sell footer action (disabled for `Viewer` role), star toggle to add/remove from the watchlist, and a "View full analysis" link to `uvalu/pages_/analysis.py`. Replaced the old single 4-tab `uvalu/stock_dialog.py` modal, which has been removed.

#### `uvalu/components.py`

Pure-render helpers shared by the drawer, Analysis page, and Dashboard: `signal_badge_html`/`signal_badge_for_decision`, `render_signal_tips`, `fair_value_ladder`, `fair_value_bar_compact`, `signals_feed`, `score_color`, `radial_gauge_svg`, `sub_score_bar_html`, `sparkline_svg`. No Streamlit or data-layer coupling — covered by `tests/test_components.py`.

#### `uvalu/pages_/`

One module per page, each exposing `render()`: `dashboard`, `screener`, `watchlist`, `portfolio`, `risk`, `analysis`, `settings`, `admin`, `help`. See [user-guide.md](user-guide.md) (and the in-app Help page) for what each page does.

### Root modules

#### `auth.py`

Email/password authentication with JWT sessions.

- `ROLES = ("Admin", "Analyst", "Viewer")`, `STATUSES = ("Active", "Invited", "Suspended")`. Older accounts stored with the pre-Admin-portal lowercase `admin`/`user` roles are transparently upgraded on load by `_normalize_user()` (`admin`→`Admin`, `user`→`Analyst`).
- `register(email, password, role=...)` — bcrypt-hash the password, store in `.cache/users.json`. First user becomes `Admin`.
- `invite_user(email, role=...)` — creates an account with `Invited` status and a random temporary password, returned once for the inviter to hand off manually (no outbound email is sent).
- `login(email, password)` — verify hash, reject `Suspended` accounts, flip `Invited`→`Active` and stamp `last_active` on success, issue an HS256 JWT (24 h TTL, signed with `AUTH_SECRET`).
- `verify_token(token)` → `(email, role)`.
- `list_users()`, `set_role()`, `set_status()`, `delete_user()` — admin helpers, surfaced in the Admin portal's Users tab. `reset_password()` exists but isn't wired into the Admin portal yet (see [backend-feature-gaps.md](backend-feature-gaps.md)).

The JWT is persisted in browser `localStorage` (`uv_jwt`) and reloaded on each refresh via the `uvalu.authgate` bridge.

#### `portfolio.py`

Encrypted JSON persistence for all per-user portfolio data.

- `set_user(email)` — derive the user's data directory from `SHA256(email)`.
- `load_portfolio()` / `save_portfolio()`, `add_position()`, `update_positions()` — open positions.
- `sell_position()` — move a position to `sold.json`, compute annualised return.
- `add_dividend()`, `update_div_hist()`, `load_div_hist()` — dividend records.
- `load_value_history()`, `record_value_snapshot()`, `backfill_value_history()` — daily value snapshots for the time-series chart (backfill uses yfinance price history + benchmark rebasing).
- `parse_excel()`, `load_watchlist()`, `save_watchlist()`, `load_manual_tickers()`, `save_manual_tickers()`.

All files are read/written through `crypto.py`.

#### `screener.py`

Fundamentals fetch plus the valuation/scoring pipeline. Fetches from yfinance (`MAX_WORKERS = 4`, `REQUEST_DELAY = 0.5s`), computes the fair-value models, and scores each stock. Results are cached in `.cache/fundamentals.json` with a per-ticker TTL of 24 h ± 4 h jitter (`CACHE_TTL_HOURS`), refreshed in a background thread so the UI stays responsive. See [stock_valuation_algorithm.md](stock_valuation_algorithm.md) for the full methodology.

Notable exports used by the data layer: `run_screener_from_df`, `fetch_fundamentals_nowait`, `_load_cache`, `cancel_background_fetch`, `clear_live_cache`, `get_fetch_progress`, `CACHE_FILE`, `_file_lock`.

#### `marketdata.py`

The single yfinance wrapper for time-series data, so `screener.py`, `prices.py` and `risk.py` don't each hold their own fetch/retry conventions. `price_history(tickers, period)` serves adjusted daily closes from a per-ticker CSV cache under `.cache/history/`, refetching only each ticker's missing tail; `dividends(ticker)` does the same for the payment history (`.cache/dividends/`, weekly refresh); `fx_to_eur_frame(currencies)` returns daily EUR-per-unit rates (FX pairs ride the same price-history cache). Retries Yahoo 429s / dropped connections with exponential backoff.

#### `scoring.py`

The 0–10 fundamental scorers shared by the screener and the risk engine — `_financial_health_score`, `_earnings_quality_score`, `_dividend_sustainability_flag`, plus `_clamp` / `_get_num`. `screener.py` re-exports them, so `risk.py` never imports from `screener.py`'s private namespace.

#### `prices.py`

`fetch_prices(tickers)` — live prices for many tickers in a batched yfinance call. Returns per-ticker current price, previous close, day change %, and volume.

#### `risk.py`

8-stage portfolio risk assessment; `assess_portfolio(pf, cache, income_mode, veto_lookup, targets, prior_snapshot)` → a `RiskReport`. See [portfolio_risk_assessment_algorithm.md](portfolio_risk_assessment_algorithm.md).

Stage summary: (1) position risk profiling (regression beta vs `^STOXX50E`, realised vol, days-to-liquidate), (2) concentration (HHI, top-N, sector/geo), (3) quantitative metrics (beta, volatility, VaR/CVaR, drawdown, correlation), (4) factor exposure (Developed → US Fama-French 5-factor + momentum, disk-cached with a stale fallback), (5) income/dividend risk incl. an income-stability score, (6) stress tests — real crisis-window replay where the 10y history covers them, else beta × benchmark — plus a block-bootstrap Monte Carlo, (7) composite score (factor slot renormalised out when unavailable), (8) rebalancing signals: absolute levels, or drift-vs-target / drift-since-snapshot when `targets` / `prior_snapshot` are supplied.

Price history is EUR-restated (`_to_eur`) before any metric is computed. `portfolio_enrichment.enrich_for_risk()` builds the input frame.

#### `portfolio_enrichment.py`

`enrich_for_risk(pf, scored_by_ticker, live_prices)` — turns a raw portfolio DataFrame into the frame `assess_portfolio` expects: live price + `current_value`, and `fair_value` / `sector` / `country` / forward dividend income looked up from the screener's scored DataFrame (not re-derived, so the Risk page matches the Screener/Analysis pages).

#### `crypto.py`

Symmetric encryption using Fernet (AES-128-CBC + HMAC-SHA256).

- Key derivation: PBKDF2-SHA256 from `ENCRYPTION_KEY` with a fixed salt (needed for persistence across restarts).
- `encrypt_text` / `decrypt_text`, and `read_encrypted` / `write_encrypted` file wrappers used by `portfolio.py` and `settings.py`.

#### `fetch_tickers.py`

Builds the stock universe per exchange: scrapes ticker lists, with hardcoded index-constituent fallbacks (BEL 20, AEX 25, CAC 40, FTSE MIB, DAX 40, SMI 20). The `_hardcoded_*` lists also drive the screener's index-only toggles.

#### `backup.py`

- `export_zip(email)` — bundle all user data plus the encryption key into an encrypted ZIP for offsite backup / migration.
- `export_excel()` — human-readable workbook (Positions, Sold, Dividends, Watchlist).
- `import_zip()` — restore data from a previously exported ZIP.
- `create_backup(email)` — on-demand export into `data/backups/`, appending a timestamped entry (type `Manual` — there is no scheduler) to an encrypted manifest; `list_backups()`, `get_backup_bytes(backup_id)`, `restore_backup(backup_id, email)` back the Admin portal's Backups tab (download / restore-from-history).

#### `settings.py`

- `load_shared_settings()` / `save_shared_settings()` — admin-controlled settings shared by all users: `enabled_exchanges`, the veto/scoring thresholds (`max_debt_equity`, `max_payout`, `min_mos`, `buy_threshold`), `benchmark_stoxx`, `us_listed_enabled`.
- `get_veto_thresholds()` — reads the shared veto fields and returns them as a `(max_debt_equity, max_payout, min_mos, buy_threshold)` tuple, passed to `screener.py`'s scoring functions and used as an `@st.cache_data` key in `uvalu/data.py`.
- `load_settings(email)` / `save_settings(s, email)` — per-user preferences: `density`, `refresh_interval_s`, and the four `alert_*` notification toggles (stored as preferences only — no delivery channel exists yet).
- Exchange constants: `ALL_EXCHANGES`, `EXCHANGE_LABELS`.

---

## Data flow

```
Browser
  │  HTTPS (self-signed TLS)
  ▼
app.py  ──►  uvalu.authgate ──────────► auth.py ──► .cache/users.json
  │            (JWT ⇄ localStorage)
  │
  └─►  st.navigation ──► uvalu/pages_/<page>.render()
                              │
                              ├─ uvalu.data ─┬─ screener.py ─┬─ fetch_tickers.py ─► stockanalysis.com
                              │              │  (+ scoring.py) └─ marketdata.py ───► yfinance ─► .cache/{fundamentals,history,dividends}
                              │              └─ prices.py ───────────────────────► yfinance (live)
                              │
                              ├─ portfolio.py ──► data/portfolio/{hash}/*.json  (positions, targets, risk snapshot; via crypto.py)
                              │
                              ├─ portfolio_enrichment.py ─► risk.py ─┬─ marketdata.py ─► .cache/{history,dividends,factors}
                              │                                      └─ scoring.py
                              │
                              ├─ uvalu.drawer (row-click stock-preview panel) ──► uvalu/pages_/analysis.py
                              │
                              └─ settings.py ───► data/settings/*.json
```

---

## Authentication flow

1. User submits the login form → `auth.login()` verifies the bcrypt hash and returns a JWT. `authgate.auth_wall()` stores it in `st.session_state` and writes it to both `localStorage` and a `uv_jwt` cookie via a hidden `st.iframe` script. `app.py` re-writes both on every authenticated render to keep them fresh.
2. On a fresh page load/reconnect with no session, `authgate.recover_session_from_cookie()` reads the `uv_jwt` cookie directly server-side via `st.context.cookies` and restores `st.session_state` — no client-side redirect involved (an earlier version redirected with the token as a `?_tok=` query param, but that's real top-level navigation, which `st.iframe()`'s sandbox blocks without `allow-top-navigation`; it silently never fired).
3. `auth_wall()` short-circuits re-verification once `jwt_token` + `user_email` are set for the session (prevents login flashes on timed auto-refresh). `?logout=1` clears session state, then a script expires the cookie/`localStorage` entry and reloads — both in the same script, so the clearing genuinely finishes before the reload starts a fresh (logged-out) session.

---

## Caching strategy

| Layer | Mechanism | TTL |
|---|---|---|
| Screener fundamentals (disk) | `.cache/fundamentals.json` (per-ticker mtime) | 24 h ± 4 h jitter |
| Screener DataFrames | `@st.cache_data` (`_load_all_screener_data`) | Until file mtime / enabled exchanges / extra tickers change |
| Live prices | `@st.cache_data` (`_fetch_prices_cached`) | 60 seconds |
| Per-ticker fundamentals | `@st.cache_data` (`_fetch_fundamentals`) | 6 hours |
| Risk report | `st.session_state` | 1 hour (or on portfolio change) |
| Value history | `data/portfolio/{hash}/value_history.json` | Daily snapshot (auto back-filled) |

---

## Security notes

- Passwords are hashed with bcrypt.
- JWTs are signed HS256 and stored in `localStorage` (not cookies) to avoid CSRF exposure.
- All portfolio and settings files are Fernet-encrypted at rest.
- `.env` (holding `AUTH_SECRET`, `ENCRYPTION_KEY`) must never be committed — keep it in `.gitignore`.
- The self-signed TLS cert is regenerated on launch if absent; it is for localhost only and not for production use.
