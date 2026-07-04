# Contributing to UV

## Dev environment setup

**Requirements:** Python 3.11+, [uv](https://github.com/astral-sh/uv)

```bash
git clone <repo-url>
cd UV
uv venv
uv pip install -r requirements.txt
cp .env.example .env
# Fill in AUTH_SECRET and ENCRYPTION_KEY in .env
python run_app.py
```

Dependencies are pinned in `requirements.txt` (plain `pip install -r requirements.txt` works too); `pyproject.toml` holds project metadata and tool config only.

---

## Project structure

The code splits into UI-agnostic **root modules** (business logic + persistence)
and the **`uvalu/` package** (the Streamlit app shell). The shell imports the
root modules; the root modules never import back.

**Root modules**

| File | Responsibility |
|---|---|
| `auth.py` | Authentication and JWT |
| `portfolio.py` | Portfolio persistence and CRUD |
| `screener.py` | Valuation algorithm, scoring, fundamentals cache |
| `prices.py` | Live price fetching |
| `risk.py` | Portfolio risk assessment |
| `crypto.py` | Encryption/decryption |
| `settings.py` | User and shared settings |
| `backup.py` | Export/import |
| `fetch_tickers.py` | Stock universe loader |

**App shell**

| Path | Responsibility |
|---|---|
| `app.py` | Entry-point shell: page config, styles, auth gate, `st.navigation`, sidebar |
| `run_app.py` | Launcher — generates the localhost TLS cert, then starts Streamlit |
| `uvalu/authgate.py` | JWT/localStorage bridges, logout, login wall |
| `uvalu/nav.py` | Registry of `st.Page` objects (breaks the app.py↔pages import cycle) |
| `uvalu/runtime.py` | Per-run accessors: `current_user()`, `theme_colors()` |
| `uvalu/data.py` | Cache-backed screener/price/fundamentals data layer |
| `uvalu/ui.py`, `formatting.py`, `styles.py`, `stock_dialog.py` | Shared rendering helpers |
| `uvalu/pages_/*.py` | One `render()` per page (dashboard, portfolio, risk, screener, settings, help) |

See [docs/architecture.md](docs/architecture.md) for a full breakdown.

---

## Conventions

- **Python version:** 3.11+
- **Formatter:** none enforced — match the style of the surrounding code
- **No type annotations** required but welcome on new public functions
- **No comments** unless the reason is non-obvious (a hidden constraint, a workaround, a subtle invariant)
- **No premature abstractions** — solve the problem at hand, not hypothetical future ones
- **Streamlit state:** use `st.session_state` for ephemeral UI state; never store secrets in session state

---

## Branching and PRs

- Branch from `master`: `git checkout -b feature/<short-description>`
- Keep PRs focused — one feature or fix per PR
- Update `CHANGELOG.md` under `[Unreleased]` for any user-visible change
- No force-pushes to `master`

---

## Secrets and data

- Never commit `.env` — it is git-ignored
- Never commit files under `data/` or `.cache/` — they contain encrypted user data
- The `.env.example` file shows which variables are required; keep it in sync if new env vars are added
