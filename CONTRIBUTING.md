# Contributing to UV

## Dev environment setup

**Requirements:** Python 3.12+, [uv](https://github.com/astral-sh/uv)

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

- **Python version:** 3.12+
- **Formatter:** none enforced — match the style of the surrounding code
- **No type annotations** required but welcome on new public functions
- **No comments** unless the reason is non-obvious (a hidden constraint, a workaround, a subtle invariant)
- **No premature abstractions** — solve the problem at hand, not hypothetical future ones
- **Streamlit state:** use `st.session_state` for ephemeral UI state; never store secrets in session state
- **Valuation logic changes:** run `.venv/Scripts/python.exe -m tools.valuation_audit` before committing a
  change to `screener._fair_value_models`, `screener.compute_scores`, or the Stage 5/6 scoring rules —
  it catches real-world edge cases the unit tests' synthetic fixtures structurally can't (see
  `docs/archive/valuation_audit_plan.md`).

---

## Translations (i18n)

All UI text goes through `uvalu/i18n.py` (spec: `docs/i18n-spec.md`, translator notes: `locales/README.md`):

- Wrap user-facing text: `_("…")`, `ngettext(singular, plural, n)`, `pgettext(context, "…")`; use `h_("…")` inside HTML strings (escapes the translation, not the placeholder values). Pass values as named placeholders, already formatted: `_("Last changed {date}.", date=fmt_date(d))` — never build sentences from pieces.
- Format numbers, money, percentages and dates with `fmt_num` / `fmt_money` / `fmt_total` / `fmt_pct` / `fmt_date` (region format, never the language). Parse typed numbers with `parse_num`, or use `locale_ui.number_field()`.
- Values that are data (sector names, statuses, labels used as keys) stay English; mark them with `N_()` and show them with `tr()`. Text built outside a request (background jobs, caches) uses `lazy_()`.
- Widget options that are translated must keep stable values (`format_func=frozen(tr)`), so filters survive a language switch.
- Never use `_` as a throwaway variable in a function that calls `_()` (`tests/test_i18n_guards.py` checks this).
- After changing UI text run `python tools/i18n_update.py` and draft the new entries (fuzzy); CI runs `tools/i18n_compile.py` and `tools/i18n_update.py --check`, and release tags run `tools/i18n_compile.py --strict`.
- **Merge conflicts in `locales/`:** never resolve them by hand or with "ours"/"theirs" — either side drops the other branch's drafts and reviews. Resolve the code conflicts, then run `python tools/i18n_merge.py`: it merges each entry three-way, rebuilds the catalogs and stages `locales/`. An entry both branches changed differently comes out unreviewed with the other version in a `# merge:` comment. Run it after a clean merge that touched `locales/` on both sides too, so the `.mo` files match.

## Branching and PRs

- Branch from `master`: `git checkout -b feature/<short-description>`
- Keep PRs focused — one feature or fix per PR
- Update `CHANGELOG.md` under `[Unreleased]` for any user-visible change
- Fill in the PR template; its *Translations* section is the output of `python tools/i18n_update.py --since master` (new/removed texts, unreviewed entries per language), so the review backlog before a release stays visible
- No force-pushes to `master`

---

## Versioning and releases

Uvalu uses **calendar versioning, `YYYY.MM.N`**: year, two-digit month, and the
release's sequence number within that month, starting at 1. `2026.10.2` is the
second release of October 2026. Uvalu is an app, not a library — nobody depends
on an API — so the version only says *when*; *what* and *how big* go in the
changelog. Releases before October 2026 used SemVer (`v1.0.0`–`v2.1.1`); those
tags stay as they are.

- **One source**: `version` in `pyproject.toml`. Nothing else holds a version;
  the app reads it through `uvalu/buildinfo.py`.
- **Build metadata** (commit, UTC build time, environment, release or dev) is
  written by `tools/stamp_build.py` into the git-ignored `build_info.json` and
  `static/version.json`. `run_app.py` runs it on every start and CI runs it
  before the tests. Never edit or commit these files.
- **Release vs. dev build**: a build is a release only when HEAD is exactly the
  annotated tag `v<version>` and the working tree is clean. Anything else shows
  as `<last release>-dev+<commit>` (plus `.dirty` with uncommitted changes),
  e.g. `2026.10.1-dev+a1b2c3d`.
- **Environment**: `UVALU_ENV` = `development` / `test` / `production`.
  Everything other than `production` shows an environment badge in the app.

### Two sets of release notes

Every change goes into **both** files under `## [Unreleased]`:

- **`CHANGELOG.md` — the internal record.** Everything that changed, for the
  team, operators and admins: admin tools, backups, data migrations, required
  `.env` keys, sign-in policy. It is the GitHub Release text.
- **`RELEASE_NOTES.md` — the public notes.** What a subscriber notices, shown
  in the app under *What's new*. Lead each entry with what it does for them
  (*"Find new ideas faster in the Screener: …"*), then where to find it. Groups
  are `### New`, `### Improved`, `### Fixed`, `### Removed`. Leave out what
  subscribers never see: admin and operator tools, hosting, backups, test
  builds, restarts, data versions, internal names. A release with nothing to
  notice still gets a section — one line is enough.

`check-changelog` fails when a CalVer release is in one file but not the
other, or the dates differ.

### What the changelog must call out

The number no longer signals impact, so the release section's first paragraph
does. Say it plainly when a release:

- **needs an action** beyond pull + restart — a new required `.env` key, a
  rotated `AUTH_SECRET` / `ENCRYPTION_KEY`, a raised Python floor, a removed or
  renamed page URL, an auth change that signs everyone out;
- **changes scores or signals** — any valuation or risk algorithm change that
  moves scores or flips BUY/AVOID, even when it's "a fix";
- **migrates stored data** — add `Data schema: N` (see `uvalu/migrations/`).

In `CHANGELOG.md`, group entries under `### Added`, `### Changed`, `### Fixed`,
`### Removed` only, in plain words — name a file, command or setting when an
operator needs it, but no function names or work-package ids (those belong in
commits). The public notes say the same things in a subscriber's terms: an
action they must take, and whether their scores or signals change.
`python tools/release.py check-changelog` checks both files; the test suite runs
the same check.

Never retag or renumber a release that's already tagged and pushed.

### Release checklist

All steps on the feature branch first, so the merge commit that gets the tag
already carries the right version:

1. Translations: every entry reviewed in all languages. Run
   `python tools/i18n_update.py --check && python tools/i18n_compile.py --strict`
   — both must pass. Release CI runs the same strict gate on the tag, but by then
   the tag is public and can't be redone (see above), so catch it here. Commit
   the rebuilt `.mo` files if they changed.
2. `python tools/release.py prepare` — picks the next number for the current
   month from the existing tags (`release.py next` only prints it), sets
   `pyproject.toml`, turns `## [Unreleased]` into `## [YYYY.MM.N] — YYYY-MM-DD`
   with a fresh `## [Unreleased]` above it in both `CHANGELOG.md` and
   `RELEASE_NOTES.md`, and checks both. Use
   `--version`/`--date` if the merge happens on another day or month.
3. Commit: `chore(release): YYYY.MM.N`.
4. `git checkout master && git merge --no-ff <branch>`.
5. `git tag -a vYYYY.MM.N <merge-commit> -m "vYYYY.MM.N — <one-line summary>"`;
   push `master` and the tag; delete the branch (local + remote).
6. The `release` workflow verifies the tag (annotated, CalVer, equals
   `pyproject.toml` at that commit, on `master`, has a changelog section and
   public notes) and
   publishes the GitHub Release with the changelog section as its body. If the
   guard fails, no Release is published — fix it before anyone pulls the tag.

---

## Secrets and data

- Never commit `.env` — it is git-ignored
- Never commit files under `data/` or `.cache/` — they contain encrypted user data
- The `.env.example` file shows which variables are required; keep it in sync if new env vars are added
