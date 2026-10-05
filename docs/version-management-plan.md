# Version management — implementation plan

Plan for `uvalu-version-management-requirements.md` (VM-01..VM-10, VD-01..VD-10).
Written 5 October 2026 against master `dc1d456` (v2.1.1).

---

## 0. Where we start

| Area | Today | Gap |
|---|---|---|
| Scheme | Adapted SemVer, `2.1.1` (CONTRIBUTING.md § Versioning and releases) | Switch to CalVer `YYYY.MM.N` |
| Source of truth | `pyproject.toml` `version`; `uvalu/logkit/filters.py` reads it for logs | No runtime module; no commit/build date/environment |
| Tags | Annotated `vX.Y.Z` on the `--no-ff` merge commit, by hand | No automated check that tag = pyproject = CHANGELOG |
| "Build" | None. Deploy = `git pull` + `run_app.py` (`run_app.bat`) | Need a deploy-time stamp step |
| Environment | `UVALU_ENV` (`development` default) via `logkit.config.resolve_environment()` | Map to dev / test / production; show it |
| Changelog | `CHANGELOG.md`, Keep-a-Changelog style, Added/Changed/Fixed | Technical wording, file paths; not shown in the app |
| "Database" | No database: encrypted JSON under `data/` (portfolio, settings, cash, watchlist, dividends, compliance logs) and `.cache/users.json`. Ad-hoc lazy migrations on read (`cash._migrate`, `portfolio._migrate_div_hist`) | No recorded schema version, no migration runner, no startup check |
| UI | Footer (`uvalu/shell.py:467 render_footer`) has disclaimer + legal links, no version | Version marker, About, What's new, env badge, admin system info |
| Machine-readable | Streamlit's built-in `/_stcore/health` only (liveness, no version) | Version endpoint |
| Logs | JSON log lines carry `build_version` + `environment` | No commit hash; user-facing error box has no version reference |

**Interpretation of VM-08/VM-09 for Uvalu.** "Database schema" means the
on-disk data layout under `data/` and `.cache/`. A schema version is recorded in
`data/schema_version.json` and changes only through numbered migrations. This
replaces the current CONTRIBUTING rule "on-disk schema change → MAJOR".

---

## 1. Decisions to confirm before starting

Recommendations are marked ★. These are the only open choices; everything else
in the plan follows from the requirements.

| # | Decision | Options | ★ Recommendation |
|---|---|---|---|
| D1 | First CalVer release | `2026.10.1` (next release after 2.1.1) | ★ `2026.10.1`. Old `v1.x`/`v2.x` tags stay as they are; never retag. CalVer sorts above them (`2026 > 2`). |
| D2 | What a dev build is called (VM-06) | (a) `<last release>-dev+<sha>` — "built on top of 2026.10.1"; (b) `<next release>-dev+<sha>` — needs a guess of N | ★ (a): no guessing; pyproject on master always holds the last released version. Example: `2026.10.1-dev+a1b2c3d`. Add `.dirty` when the working tree has uncommitted changes. |
| D3 | When a build counts as a release | HEAD is exactly the annotated tag `v<pyproject version>` and the tree is clean | ★ as stated; anything else is `-dev`. |
| D4 | Environment names (VM-04) | `UVALU_ENV` = `development` / `test` / `production` | ★ keep the existing variable, display as `DEV` / `TEST` / `PROD`. An unknown value counts as non-production (badge shown). |
| D5 | Version endpoint (VD-07) | (a) static file via Streamlit static serving, `/app/static/version.json`; (b) a custom route on Streamlit's server | ★ (a): supported, no monkey-patching. Liveness stays on `/_stcore/health`. (b) only after a spike shows Streamlit 1.60 supports custom routes cleanly. |
| D6 | Language of What's new | English only (like the beta legal pages) vs. translated | ★ English only, with the same "no translation yet" notice the legal page uses. Translating every changelog entry 6× per release would hold releases hostage to the i18n strict gate. UI chrome around it (titles, buttons) is translated. |
| D7 | Migration on deploy | (a) `run_app.py` runs pending migrations automatically, after a backup; (b) operator runs them by hand | ★ (a) for upgrades; downgrades are always manual. `app.py` still refuses to serve on a mismatch (VM-09) — covers anyone starting Streamlit directly. |
| D8 | Is the commit hash public? | `version.json` and the footer are reachable before sign-in? | ★ Footer marker shows only `v2026.10.1` (plus `-dev+sha` on dev builds). Commit hash on About (signed-in) and in `version.json`. A short commit hash of a private repo is not sensitive. |

---

## 2. Architecture

```
pyproject.toml  version = "2026.10.1"          ← the one hand-edited place (VM-02)
       │
       ▼
tools/stamp_build.py  (run by run_app.py at deploy/start, and by CI)
       │  reads: pyproject version, git rev-parse/describe/status, UTC now, UVALU_ENV,
       │         schema version expected by the code
       ▼
build_info.json  (repo root, git-ignored, never edited by hand — VM-05)
static/version.json  (same data + live schema version, served at /app/static/version.json)
       │
       ▼
uvalu/buildinfo.py  — BuildInfo dataclass, loaded once per process
       │  fallback when build_info.json is missing (tests, `streamlit run app.py`):
       │  compute the same fields in-process, source="runtime"
       ▼
footer · About · What's new · env badge · admin System tab · logkit · error box
```

### 2.1 `uvalu/buildinfo.py` (new)

```python
@dataclass(frozen=True)
class BuildInfo:
    version: str          # "2026.10.1"            — from pyproject
    display_version: str  # "2026.10.1" or "2026.10.1-dev+a1b2c3d[.dirty]"
    commit: str           # "a1b2c3d"  (7 chars) or "unknown"
    commit_full: str
    built_at: str         # ISO-8601 UTC, "2026-10-12T09:41:07Z"
    environment: str      # "development" | "test" | "production"
    is_release: bool
    dirty: bool
    schema_expected: int  # highest migration number in this code
    source: str           # "stamp" | "runtime"

def current() -> BuildInfo          # cached; one read per process
def build_id() -> str               # f"{display_version}@{built_at}" — used by VD-09
```

- `CALVER_RE = r"^\d{4}\.(0[1-9]|1[0-2])\.[1-9]\d*$"` — validated on load; an
  invalid pyproject version logs `critical` and displays `0.0.0-invalid`.
- No git call ever happens on a render path; `current()` is computed once.
- `uvalu/logkit/filters.py` `_build_version()` is replaced by
  `buildinfo.current().display_version` (keeps logkit free of tomllib).

### 2.2 `tools/stamp_build.py` (new)

- `python tools/stamp_build.py [--env production] [--check]`.
- Writes `build_info.json` and `static/version.json` atomically (temp + rename).
- Git missing / not a checkout (e.g. a zip deploy) → commit `unknown`, build is
  `-dev`. Never fails the start-up.
- `run_app.py` calls it in-process before launching Streamlit; `run_app.bat`
  needs no change (`git pull` already runs first).
- `.gitignore`: `build_info.json`, `static/version.json`.

### 2.3 Data schema + migrations (VM-08, VM-09, VM-10)

```
uvalu/migrations/
    __init__.py        # registry: discovers m####_*.py, EXPECTED = max number
    __main__.py        # CLI: status | upgrade | downgrade --to N | stamp-baseline
    runner.py          # lock, backup, apply, record
    m0001_baseline.py  # no-op: today's layout (after the lazy cash/div-history migrations)
```

Each migration module:

```python
NUMBER = 2
DESCRIPTION = "Rename watchlist key 'added' to 'added_at'"
REVERSIBLE = True
def up(ctx: MigrationContext) -> None: ...
def down(ctx: MigrationContext) -> None: ...   # required when REVERSIBLE
```

`MigrationContext` gives paths (`data/`, `.cache/`), the per-user portfolio
folders, and `read_encrypted`/`write_encrypted` helpers so migrations don't
reimplement crypto.

`data/schema_version.json` (plain JSON — holds no personal data):

```json
{"schema_version": 1,
 "history": [{"number": 1, "direction": "up", "at": "2026-10-12T09:41:07Z",
              "app_version": "2026.10.1", "commit": "a1b2c3d", "backup_id": null}]}
```

Runner rules:

- **Upgrade**: file lock (`data/.migrate.lock`) → `backup.create_backup()`
  (existing, records `backup_id`) → apply each pending `up()` in order → write
  `schema_version.json` after **each** step (so a crash mid-chain leaves an
  accurate number) → log `uvalu.migrations` events.
- **Baseline**: no `schema_version.json` + existing data → stamp `1` without
  changes. Fresh install (no data) → stamp `EXPECTED`.
- **Downgrade**: `--to N`, manual only, runs `down()` from the newest down,
  refuses if any step on the path is `REVERSIBLE = False` and points to the
  backup recorded in `history` instead.
- The existing lazy `_migrate` functions stay (they are idempotent and cover
  old backups); new layout changes go through migrations only.

Startup check in `app.py` (right after `logkit.init_logging()`, before
`auth_wall()`):

| On-disk vs. code | Behaviour |
|---|---|
| equal | continue |
| on-disk < code | `run_app.py` already migrated (D7); if still lower here → maintenance screen, `st.stop()` |
| on-disk > code (rollback without downgrade) | maintenance screen, `st.stop()` |
| file unreadable | maintenance screen, `st.stop()` |

Log line (`critical`, event `startup.schema_mismatch`):
`Data schema is 3, this version (2026.10.1, a1b2c3d) expects 2. Run "python -m uvalu.migrations downgrade --to 2" with the newer code, or restore backup <id>.`
The maintenance screen shows a short neutral text to users and the full
instruction only to Admins. `run_app.py` performs the same check and exits
non-zero before Streamlit starts.

Backups: the backup manifest/ZIP records `schema_version` and `app_version`.
Restoring a backup with an older schema runs the upgrade chain on it; a newer
schema is refused with a clear message.

---

## 3. Work packages

Branch: `feature/version-management`. Ordered so each WP is mergeable on its
own and tests stay green. Sizes: S ≈ ½ day, M ≈ 1 day, L ≈ 2 days.

### WP-1 · CalVer switch + single source of truth — VM-01, VM-02 · S

- `CONTRIBUTING.md` § Versioning and releases: replace the SemVer rules with
  CalVer `YYYY.MM.N`. Keep a short "what to call out in the changelog" list
  (score-moving algorithm changes, manual actions, migrations) — that content
  moves from the version number into the changelog (requirements §1).
- `uvalu/buildinfo.py` with the runtime fallback only (stamp comes in WP-2).
- `logkit/filters.py` reads `buildinfo`; update
  `tests/test_logkit.py::test_build_version_matches_pyproject`.
- pyproject stays `2.1.1` until the release commit (WP-11) bumps it.
- Tests: CalVer regex (valid/invalid months, N ≥ 1); `display_version` for
  release / dev / dirty / no-git; a guard test that greps `uvalu/`, `app.py`
  and `pages_/` for a hard-coded `\d{4}\.\d{2}\.\d+` literal (VD-10).

### WP-2 · Build metadata stamp — VM-04, VM-05, VM-06 · M

- `tools/stamp_build.py`, wired into `run_app.py`; `.gitignore` entries.
- `buildinfo.current()` prefers `build_info.json` (`source="stamp"`), falls
  back to runtime.
- Environment mapping (D4); `.env.example` comment lists the three values.
- CI (`tests.yml`): run `python tools/stamp_build.py --env test` before pytest
  and assert the file validates.
- Tests: stamp output schema; atomic write; no-git fallback; a test that
  `build_info.json` is not tracked (`git ls-files`); release detection with a
  temp repo + annotated tag (`git` available on the CI runner).

### WP-3 · Release tooling + tag guard — VM-03, VM-07 · M

- `tools/release.py`:
  - `next` — prints the next version: scans `git tag -l "v2026.10.*"` for the
    current UTC month, N = highest + 1 (or 1).
  - `prepare` — sets pyproject `version`, renames `## [Unreleased]` to
    `## [2026.10.N] — YYYY-MM-DD`, adds a fresh `[Unreleased]`, runs the
    changelog check and the i18n strict gate. Does not commit or tag; prints
    the commands of the existing checklist.
- `tools/changelog_check.py`: every release section uses only
  `### Added / Changed / Fixed / Removed` (VM-07), no empty groups, date
  present, versions descending, the `[Unreleased]` section exists. Runs in CI.
- New workflow `.github/workflows/release.yml`, on tag `v*`:
  - tag is annotated (`git cat-file -t` = `tag`), matches the CalVer regex,
    equals `v` + pyproject version, its commit is on `master`, a CHANGELOG
    section for it exists;
  - creates the GitHub Release with the CHANGELOG section as body plus the
    compare link (automates checklist step 7, which is done by hand today).
- Local guard: document a `pre-push` hook (optional, not installed by
  default) running the same tag checks.
- CONTRIBUTING release checklist rewritten around `tools/release.py`.

### WP-4 · Changelog rewrite rules — VM-07 · S

- Writing rules at the top of CHANGELOG.md: user language, no file paths or
  WP ids, "what you'll notice / what you need to do" first. A one-line
  `Data schema: N` note on releases that add a migration (feeds VM-10).
- Historical sections stay untouched (they are history). The What's new view
  (WP-7) shows CalVer sections only; older versions link to GitHub.

### WP-5 · Schema version + migrations — VM-08, VM-09 · L

- `uvalu/migrations/` as in §2.3, `m0001_baseline`.
- Startup check in `app.py` and `run_app.py`; maintenance screen component in
  `uvalu/shell.py` (`render_maintenance()`).
- `backup.py`: record `schema_version`/`app_version` in the manifest and ZIP;
  upgrade-on-restore, refuse newer.
- Tests (with the tmp-data monkeypatch recipes already used for
  `portfolio`/`settings`): baseline on existing data; fresh install;
  upgrade chain with two fake migrations; crash mid-chain leaves the right
  number; downgrade incl. an irreversible step refused; lock contention;
  startup check for =, <, >, corrupt; restore of old/new backups.
  AppTest: `app.py` shows the maintenance screen and stops on a mismatch.
- `docs/architecture.md` + `docs/data-contracts.md`: "Data schema and
  migrations" section; how to write a migration.

### WP-6 · Footer version marker + environment badge — VD-01, VD-03, VD-10 · S

- `render_footer()`: a muted `v2026.10.1` `st.page_link` to the About page's
  What's new section (VD-04), on every page including `/legal`. Dev builds show
  the full `display_version`.
- Environment badge when `environment != "production"`: a coloured pill
  (`DEV` amber, `TEST` violet — tokens added to `uvalu/styles.py`, contrast
  checked in light + dark) in the top bar next to the logo, plus a coloured
  2px top border so a screenshot also shows it. The admin shell (which skips
  the top bar) gets the same pill.
- New strings into `locales/messages.pot`, translated + reviewed in all 6
  languages (strict gate).
- Tests: footer renders `buildinfo.current().display_version` (monkeypatched
  values prove it's not hard-coded); badge present for dev/test, absent for
  production.

### WP-7 · About + What's new page — VD-02, VD-04 · M

- New page `uvalu/pages_/about.py`, URL `/about`, registered in `app.py`,
  reachable from the footer marker and the user menu (*About Uvalu*), next to
  *Legal & policies*.
- **About card**: version, commit (link to the GitHub commit for Admins
  only), build date/time shown in the user's region format and UTC,
  environment, data-model version (`M1`, from `uvalu/compliance`) shown
  separately so the two "versions" aren't confused. *Copy details* button
  (one line, for support emails).
- **What's new**: parses CHANGELOG.md (cached by file mtime) into
  version → date → groups; newest first; anchors per version
  (`/about?v=2026.10.1`). English-only notice (D6). The markdown renderer and
  CSS from the legal page are reused.
- Tests: changelog parser (groups, ordering, malformed input degrades to raw
  markdown); page AppTest; deep link to one version.

### WP-8 · Version endpoint + log/error context — VD-07, VD-08 · S

- `.streamlit/config.toml`: `[server] enableStaticServing = true`;
  `static/version.json` (written by WP-2, plus `schema_version` written after
  migrations) → `GET /app/static/version.json`:
  `{"version","display_version","commit","built_at","environment","schema_version","is_release"}`.
  Nothing else goes in `static/` (check that `favicon.svg` etc. don't need to).
- logkit: add `commit` next to `build_version` in `ContextFilter`, the JSON
  formatter and `_STD_ATTRS`; bump the log `_SCHEMA_VERSION` in
  `logkit/formatters.py` (it's a log-format version, documented in
  `docs/logging.md`).
- The user-facing error box in `app.py` (render exception handler, ~line 157)
  gets a muted line: `Reference: <correlation id> · v2026.10.1 (a1b2c3d)`.
- Tests: JSON log line has both fields; error box shows them; version.json
  matches `buildinfo` (no network: read the file, no server).
- `docs/support-manual.md`: "Which version is a user on?" — footer, About,
  `version.json`, log fields.

### WP-9 · Admin system info — VD-06 · S

- Admin page: new **System** tab next to Users / Security / Feeds / Backups:
  - build (same fields as About) + data schema version, expected version,
    migration history table (from `schema_version.json`);
  - runtime: Python, Streamlit, pandas, numpy, yfinance, cryptography… via
    `importlib.metadata.version()` (list kept in one constant);
  - data sources: provider name + last successful fetch, reusing what
    `_render_feeds()` already computes (link to the Feeds tab instead of
    duplicating).
- Tests: tab renders for Admin, absent for Viewer (existing role-gate
  pattern).

### WP-10 · "What's new" notice + reload prompt — VD-05, VD-09 · M (S priority)

- **VD-05**: per-user `last_seen_version` in the user's settings file
  (`settings.py`). On sign-in, if the current *release* version is newer →
  dismissible notice under the beta banner: "Uvalu was updated to
  2026.10.2 — See what's new · Dismiss". Dismiss or opening What's new
  writes `last_seen_version`. New users get it set on first sign-in (no notice).
  Dev builds never trigger it.
- **VD-09**: a `st.fragment(run_every=60)` compares the session's
  `build_id()` (stored in `session_state` at session start) with
  `build_info.json` on disk (mtime-cached read). Different → banner
  "A new version is available — Reload". Needs `price_autorefresh`'s
  `mark_dialog_open` guard so it never closes an open dialog
  (see the drawer/dialog gotchas).
  - Caveat to verify in a spike first: a deploy here restarts the server,
    which ends sessions; the reconnecting browser runs the new Python code
    with a fresh `session_state`. The banner therefore mainly covers
    "pulled but not yet restarted" and future zero-downtime deploys. If the
    spike shows Streamlit's frontend already reloads itself after a server
    version change, document that and keep the fragment for the pull-before-
    restart case only.
- Tests: notice logic (new user, same version, newer release, dev build,
  dismissed); fragment comparison with a fake clock/file.

### WP-11 · Rollback documentation + rehearsal — VM-10 · M

- `docs/operations/release-and-rollback.md`:
  1. Find the target: `git tag -l "v*" --sort=-v:refname`; the target's
     expected schema: `python tools/release.py schema-of v2026.10.1` (reads
     `uvalu/migrations/` at that tag via `git show`).
  2. **With the current (newer) code** — it is the only one that knows the
     `down()` steps: `python -m uvalu.migrations downgrade --to <N>`.
  3. `git checkout v2026.10.1` (detached) → `python run_app.py`.
  4. Irreversible migration on the path → restore the pre-migration backup
     recorded in `schema_version.json` history instead (Admin → Backups or
     the import CLI), then step 3.
  5. Roll forward: `git checkout master && python run_app.py` (upgrade runs
     automatically).
- `tools/rollback.py --to v2026.10.1` automates 1–3 with a dry-run default
  and a confirmation prompt.
- Rehearsal in CI: on a fixture `data/` tree, upgrade → downgrade → upgrade
  must give byte-identical decrypted JSON for reversible chains.
- Each release section in CHANGELOG carries `Data schema: N` when it changes
  (WP-4), so the mapping is readable without tooling.

### WP-12 · Docs, release as `2026.10.1` · S

- Update `docs/architecture.md` (build info, migrations, version surfaces),
  `docs/configuration.md` (`UVALU_ENV`, static serving), `docs/user-guide.md`
  (About / What's new), README badge/version mention if any.
- Release via the new tooling: `tools/release.py prepare` → `2026.10.1`
  (or `.N` if another release lands in October first), first CHANGELOG
  section written per the new rules, merge `--no-ff`, annotated tag on the
  merge commit, `release.yml` publishes the GitHub Release.
- Afterwards: update the project memory "release versioning strategy"
  (SemVer → CalVer).

---

## 4. Order and estimate

```
WP-1 ─► WP-2 ─► WP-3 ─► WP-4
          │
          ├─► WP-5 ─► WP-11
          ├─► WP-6 ─► WP-7 ─► WP-10
          ├─► WP-8
          └─► WP-9 (needs WP-5 for schema info)
                                  all ─► WP-12
```

| Must-haves (M) | WP-1..WP-9, WP-11, WP-12 | ≈ 9–10 days |
|---|---|---|
| Should-haves (S) | WP-10 (VD-05, VD-09) | ≈ 1 day + VD-09 spike |

Suggested slicing: one release with WP-1..WP-9 + WP-11 + WP-12 as
`2026.10.1`; WP-10 can follow as `2026.10.2` / `2026.11.1`.

---

## 5. Traceability

| Req | Pri | Work package | Verified by |
|---|---|---|---|
| VM-01 CalVer | M | WP-1, WP-3 | regex tests; `release.yml` tag check |
| VM-02 single source | M | WP-1 | hard-coded-literal guard test; logkit test |
| VM-03 annotated tag on main | M | WP-3 | `release.yml` (annotated, on master, = pyproject) |
| VM-04 build metadata | M | WP-2 | stamp schema test |
| VM-05 injected automatically | M | WP-2 | file git-ignored + "not tracked" test; written by `run_app.py`/CI |
| VM-06 dev builds distinguishable | M | WP-2 | release/dev/dirty tests with a temp repo |
| VM-07 changelog groups | M | WP-3, WP-4 | `changelog_check.py` in CI |
| VM-08 versioned migrations + recorded version | M | WP-5 | migration runner tests |
| VM-09 refuse on mismatch | M | WP-5 | startup-check unit + AppTest |
| VM-10 rollback from tag | M | WP-11 | runbook + CI round-trip rehearsal |
| VD-01 footer marker | M | WP-6 | footer test |
| VD-02 About | M | WP-7 | page AppTest |
| VD-03 env badge | M | WP-6 | badge tests (dev/test/prod) |
| VD-04 label → What's new | M | WP-6, WP-7 | link target test |
| VD-05 one-time notice | S | WP-10 | notice logic tests |
| VD-06 admin extras | S | WP-9 | role-gate test |
| VD-07 machine-readable | M | WP-8 | `version.json` = `buildinfo` test |
| VD-08 version in logs/errors | M | WP-8 | log-field + error-box tests |
| VD-09 reload prompt | S | WP-10 | fragment test (after spike) |
| VD-10 never hard-coded | M | WP-1, WP-6 | literal guard + monkeypatched render tests |

---

## 6. Risks

- **i18n strict gate**: new UI strings (footer, badge, About, notices, maintenance
  screen, admin tab) must be reviewed in all 6 languages before tagging — budget
  for it in WP-6/7/9/10, not at release time.
- **Migrations touch encrypted user data**: always backup first; never log
  decrypted content; tests run on tmp copies only.
- **Static serving** exposes everything under `static/` without sign-in — the
  folder holds only `version.json`; a test asserts the folder's contents.
- **Two "versions" on screen** (app `2026.10.1` vs. data model `M1`) — label
  them distinctly ("App version", "Scoring model") on About and in the signal
  provenance.
- **Same-month numbering** relies on tags being pushed; `tools/release.py next`
  runs `git fetch --tags` first.
