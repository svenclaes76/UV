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
| `uvalu/data.py` | Cache-backed screener/price/fundamentals data layer (non-blocking accessors) |
| `uvalu/store.py` | Off-thread scored-universe store — background worker runs the screener fetch + scoring |
| `uvalu/ui.py`, `formatting.py`, `styles.py`, `components.py`, `drawer.py` | Shared rendering helpers (incl. the row-click stock-preview drawer) |
| `uvalu/pages_/*.py` | One `render()` per page (dashboard, portfolio, risk, screener, watchlist, analysis, settings, help, admin) |

See [docs/architecture.md](docs/architecture.md) for a full breakdown.

---

## Conventions

- **Python version:** 3.11+
- **Formatter:** none enforced — match the style of the surrounding code
- **No type annotations** required but welcome on new public functions
- **No comments** unless the reason is non-obvious (a hidden constraint, a workaround, a subtle invariant)
- **No premature abstractions** — solve the problem at hand, not hypothetical future ones
- **Streamlit state:** use `st.session_state` for ephemeral UI state; never store secrets in session state
- **Valuation logic changes:** run `.venv/Scripts/python.exe -m tools.valuation_audit` before committing a
  change to `screener._fair_value_models`, `screener.compute_scores`, or the Stage 5/6 scoring rules —
  it catches real-world edge cases the unit tests' synthetic fixtures structurally can't (see
  `docs/valuation_audit_plan.md`).

---

## Branching and PRs

- Branch from `master`: `git checkout -b feature/<short-description>`
- Keep PRs focused — one feature or fix per PR
- Update `CHANGELOG.md` under `[Unreleased]` for any user-visible change
- No force-pushes to `master`

---

## Versioning and releases

UV uses **`MAJOR.MINOR.PATCH`** (SemVer), but adapted for a deployed app rather
than a library: nobody imports UV, so "breaking change" is defined by what
breaks for the operator or user on `git pull && restart`, not by a public API.

### Which digit to bump

**MAJOR** — the release needs a migration step or a manual action; you can't
just pull and restart:

- On-disk schema change that isn't auto-migrated — `portfolio/*.json`,
  `value_history.json`, `manual_tickers.json`, the watchlist store, the backup
  ZIP format.
- A new **required** `.env` key, or a rotated `AUTH_SECRET` / `ENCRYPTION_KEY`
  (forces re-login or re-encryption).
- Python floor raised, or a dependency bump that changes stored-data
  compatibility.
- A page/URL removed or renamed (`/risk`, `/analysis`, …) that could be
  bookmarked.
- An auth-model change that invalidates existing sessions or user records.

**MINOR** — new capability, backward-compatible:

- A new page, screen, or subsystem.
- A new user-facing feature, or a materially new UX behaviour.
- A **valuation or risk algorithm change that moves scores or flips
  BUY/AVOID decisions** — even when it's "a fix". Call it out in the CHANGELOG.
- New *optional* config; a deprecation that still works but warns.

**PATCH** — nothing new; something wrong is now right:

- Bug fixes with no intended change to correct-path output.
- Performance, CSS/visual polish, copy changes.
- Refactors, test-only changes, docs, dependency bumps with no behaviour change.

**Tie-breaker (MINOR vs PATCH):** would a user *notice* or need to *do*
something? → MINOR. Does it only make a wrong thing right, with no new surface?
→ PATCH. Score-affecting changes always round up to MINOR.

Never retag or renumber a release that's already tagged and pushed.

### Release checklist

All steps on the feature branch first, so the merge commit that gets the tag
already carries the right version:

1. `CHANGELOG.md`: rename `## [Unreleased]` to `## [x.y.z] — YYYY-MM-DD`, then
   add a fresh empty `## [Unreleased]` above it.
2. `pyproject.toml`: `version = "x.y.z"`.
3. Commit: `chore(release): x.y.z`.
4. `git checkout master && git merge --no-ff <branch>`.
5. `git tag -a vx.y.z <merge-commit> -m "…"`; push `master` and the tag; delete
   the branch (local + remote).
6. Publish a GitHub Release for `vx.y.z` — body is the CHANGELOG section plus a
   full-changelog compare link.

---

## Secrets and data

- Never commit `.env` — it is git-ignored
- Never commit files under `data/` or `.cache/` — they contain encrypted user data
- The `.env.example` file shows which variables are required; keep it in sync if new env vars are added
