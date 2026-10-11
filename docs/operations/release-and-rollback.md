# Release, deploy and rollback

How a Uvalu version gets from a branch to a running server, and how to go
back to an earlier one (requirements VM-03, VM-05, VM-08..VM-10). The rules
behind the version number are in
[CONTRIBUTING.md § Versioning and releases](../../CONTRIBUTING.md#versioning-and-releases).

Commands assume the repo root with the venv's Python
(`.venv/Scripts/python.exe` on Windows).

---

## 1. Release

Follow the checklist in CONTRIBUTING.md. In short:

```bash
python tools/i18n_update.py --check && python tools/i18n_compile.py --strict
python tools/release.py prepare            # next YYYY.MM.N, pyproject + CHANGELOG + RELEASE_NOTES
git commit -am "chore(release): 2026.10.1"
git checkout master && git merge --no-ff <branch>
git tag -a v2026.10.1 -m "v2026.10.1 — <one-line summary>"
git push origin master v2026.10.1
```

The `release` workflow then checks the tag and publishes the GitHub Release.
A tag that fails the check gets no Release: fix it before anyone pulls it.

## 2. Deploy

**Before deploying**, while the beta offers password sign-in only, check for
accounts that have no password (created through Google sign-in): they can't
sign in.

```bash
python tools/check_password_accounts.py   # read-only; exit 1 lists them
```

For each account it lists: Admin portal → Users → ⋯ → **Send password
reset** → **Generate reset link**, and send the person the link; it lets them
set a password even if they never had one. `run_app.py` repeats this check on
every start (a warning, never a stop) and the Users page lists the same
accounts, so a missed step still shows up.

```bash
git pull
python run_app.py          # or run_app.bat, which pulls first
```

On every start `run_app.py`:

1. brings the stored data up to the schema this version expects
   (`python -m uvalu.migrations upgrade`), after a snapshot ZIP in
   `data/migration-snapshots/` — only when there is something to migrate;
2. warns about accounts without a password while sign-in is password-only;
3. stamps the build metadata (`build_info.json`, `static/version.json`):
   version, commit, UTC build time, environment;
4. starts Streamlit.

If the data can't be migrated, it stops with the reason and the snapshot to
restore. Starting Streamlit directly (`streamlit run app.py`) skips step 1: the
app then shows a maintenance screen until the data matches, and logs
`startup.schema_mismatch` with the exact command to run.

Check what is running: footer marker, **About Uvalu** in the user menu,
Admin → **System**, or `GET /app/static/version.json`.

## 3. Roll back

Stop the app first.

```bash
python tools/rollback.py --to v2026.10.1          # dry run: prints the plan
python tools/rollback.py --to v2026.10.1 --yes
python run_app.py
```

What it does, in this order:

1. **Downgrade the data with the current code** if the target expects an older
   schema (`python -m uvalu.migrations downgrade --to N`). Only the newer code
   knows how to undo its own migrations, so this must happen *before* the
   checkout. `python tools/release.py schema-of v2026.10.1` shows the target's
   schema; release notes say `Data schema: N` when it changes.
2. **Check out the tag** (detached HEAD). It refuses when there are
   uncommitted changes.

**Irreversible migration on the way down?** The tool stops and names the
snapshot taken just before that migration. Restore it instead of downgrading:

```bash
python -m uvalu.migrations restore-snapshot <snapshot-id> --yes
git checkout --detach v2026.10.1
python run_app.py
```

Anything written after that snapshot is lost — that's the price of an
irreversible change, and why migrations should have a `down()` whenever
possible.

**Roll forward again:**

```bash
git checkout master
python run_app.py          # re-applies the migrations
```

## 4. Useful commands

| Command | What it does |
|---|---|
| `python -m uvalu.migrations status` | Recorded schema, what this code expects, applied/pending steps, recent history. Exit 2 on a mismatch. |
| `python -m uvalu.migrations upgrade [--to N]` | Apply pending migrations (snapshot first). |
| `python -m uvalu.migrations downgrade --to N` | Undo migrations down to N (snapshot first). |
| `python -m uvalu.migrations snapshots` | List the snapshots (the last 10 are kept). |
| `python -m uvalu.migrations restore-snapshot <id> --yes` | Put a snapshot's files back, including its schema version. |
| `python tools/release.py next` / `schema-of <tag>` / `verify-tag <tag>` | Release helpers. |
| `python tools/stamp_build.py [--env test]` | Re-stamp the build metadata by hand (`run_app.py` does this). |

Snapshots hold the data files (already encrypted at rest) and `.cache/users.json`,
never `.env`. Restoring one needs the same `ENCRYPTION_KEY`.

## 5. Writing a migration

Add `uvalu/migrations/m000N_<what>.py` with `NUMBER = N`, a one-line
`DESCRIPTION`, `up(ctx)` and — whenever possible — `down(ctx)`. Rules:

- `up` must be idempotent: restoring an older backup re-runs it over all data.
- Read and write through `ctx.read_json` / `ctx.write_json` (they handle the
  encryption); iterate users with `ctx.user_dirs()` / `ctx.settings_files()`.
- Never log decrypted content.
- Test it with the fixtures in `tests/test_migrations.py`, including the
  upgrade → downgrade → upgrade round trip.
- Add `Data schema: N` to the release's changelog intro.
