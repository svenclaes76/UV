# Contributing to UV

## Dev environment setup

**Requirements:** Python 3.11+, [uv](https://github.com/astral-sh/uv)

```bash
git clone <repo-url>
cd UV
uv sync
cp .env.example .env
# Fill in AUTH_SECRET and ENCRYPTION_KEY in .env
streamlit run app.py
```

---

## Project structure

| File | Responsibility |
|---|---|
| `app.py` | Routing, UI, page controllers |
| `auth.py` | Authentication and JWT |
| `portfolio.py` | Portfolio persistence and CRUD |
| `screener.py` | Valuation algorithm and scoring |
| `prices.py` | Live price fetching |
| `risk.py` | Portfolio risk assessment |
| `crypto.py` | Encryption/decryption |
| `settings.py` | User and shared settings |
| `backup.py` | Export/import |
| `fetch_tickers.py` | Stock universe loader |

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
