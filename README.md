# UV — Undervalued

A Streamlit web app for European stock analysis and personal portfolio management. UV combines a multi-exchange value screener, live portfolio tracking, dividend management, and quantitative risk assessment in a single secure application.

> Not financial advice.

---

## Features

- **Screener** — ranks 750+ stocks across 6 European exchanges using a 6-stage valuation algorithm (Graham Number, PE Fair Value, EPV, DDM, Analyst Target). Each stock receives a composite score and a Buy / Monitor / Avoid signal.
- **Portfolio tracker** — track open positions with live prices, unrealised P&L, and benchmark comparison. Manage realised trades and dividend history.
- **Dashboard** — KPI cards, performance heatmap, sector allocation, portfolio value chart with S&P 500 / Euro Stoxx 50 overlays, and a risk snapshot.
- **Risk assessment** — 8-stage quantitative analysis: concentration (Herfindahl), volatility, Value-at-Risk, factor exposure, stress tests (Dot-com / 2008 / COVID / 2022), and 10,000-path Monte Carlo simulation.
- **Multi-user** — email/password authentication with JWT sessions. First registered user becomes admin. Per-user data is isolated and encrypted at rest.

---

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager (recommended) or pip

---

## Install

```bash
# Clone the repo and install dependencies
uv sync
```

Or with pip:

```bash
pip install -r requirements.txt
```

---

## Configuration

Create a `.env` file in the project root (never commit this):

```env
AUTH_SECRET=<64-char hex string>
ENCRYPTION_KEY=<64-char hex string>
```

Generate both values with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Run that command twice — once for each key.

---

## Run

```bash
streamlit run app.py
```

The app runs on `https://localhost:8501`. On first launch a self-signed TLS certificate is generated automatically; accept the browser warning for localhost.

Register the first account — it is automatically granted the **admin** role.

---

## Data storage

All user data is stored locally and never sent to a third party:

| Path | Contents |
|---|---|
| `.cache/users.json` | User accounts (bcrypt-hashed passwords) |
| `.cache/fundamentals.json` | Screener fundamentals cache (24 h TTL) |
| `data/portfolio/{hash}/` | Per-user portfolio, sold positions, dividends, watchlist, value history |
| `data/settings/{hash}.json` | Per-user settings (encrypted) |
| `data/settings/shared.json` | Admin settings (enabled exchanges) |

`{hash}` is a SHA-256 digest of the user's email address.

---

## Documentation

| Document | Description |
|---|---|
| [docs/user-guide.md](docs/user-guide.md) | Feature walkthrough for end users |
| [docs/architecture.md](docs/architecture.md) | Codebase structure and data flow |
| [docs/configuration.md](docs/configuration.md) | All settings, env vars, and constants |
| [docs/stock_valuation_algorithm.md](docs/stock_valuation_algorithm.md) | 6-stage valuation pipeline with formulas |
| [docs/portfolio_risk_assessment_algorithm.md](docs/portfolio_risk_assessment_algorithm.md) | 8-stage risk assessment methodology |
| [docs/uvalu-brand-guidelines.md](docs/uvalu-brand-guidelines.md) | Visual identity — colours, typography, logo usage |
| [CHANGELOG.md](CHANGELOG.md) | Version history and notable changes |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Dev setup, conventions, and PR process |
