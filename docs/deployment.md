# Deployment

How the app is run outside a developer's machine. This covers:

- what the app does itself for security (from the [security review](security-review.md))
- the master secrets (SR5, SR6)
- the demo on Streamlit Community Cloud (DM-6), the only hosted deployment today

**No production server for now.** The Hetzner server setup (Ubuntu, Caddy in front of Streamlit, a systemd
service, borg offsite backups to a Storage Box, the content security policy and the restore test) was removed
on 24 October 2026 because no beta is planned soon. Its files and the 9-step guide are in git history, last
in commit `648559b` (`deploy/`) and in this file before that date. Open items SR2, SR4 (CSP) and L8 are parked
until a beta is planned.

## What the app does itself

- **Per-IP sign-in limit:** 20 failed password sign-ins from one address in 15 minutes block that address for the rest of the window, silently, with the same message as any failure. A proxy can't do this, because sign-in happens inside Streamlit's websocket. Behind a reverse proxy (`UVALU_BEHIND_PROXY=1`, see `run_app.py`) the app reads the client address from its `X-Forwarded-For` header, and trusts it only on a localhost connection.
- **Per-account lock:** set in Admin › Security.
- **Session cookies:** `SameSite=Strict`, and `Secure` when served over HTTPS.
- **Security logs:** kept 31 days.

## The master secrets (`.env`)

`.env` in the app folder holds the two secrets that protect every account:

- `AUTH_SECRET` signs sessions. Anyone who has it can sign in as anyone.
- `ENCRYPTION_KEY` encrypts the user store, portfolios, settings and backups. Without it, none of that data, including the offsite backups, can be read.

**The app never hands these out.** There is no download in Admin (removed for SR5, [security review](security-review.md) #5), and backups don't include `.env`. They move only as described below.

### Keep an offline copy

Keep one copy of `.env` outside the machine that runs the app, in a password manager entry or printed and stored safely. Don't keep it next to the backups. If the machine is lost, this copy is the only way to read the backups (SR6).

Update the copy whenever either secret changes.

### Moving to another machine

1. Install the app on the new machine, but don't start it yet.
2. Copy `.env` over a secure channel (SSH, or a password manager), never by email or chat, and make it readable
   only by the user that runs the app.
3. Restore the data by copying the data folders or with Admin › Backups.
4. Start the app and sign in. If the user store can't be read, the key doesn't match: check that `.env` arrived
   unchanged.
5. Delete any copy of `.env` made on the way. The offline copy is the only one that should exist besides the
   machine's.

### Rotating a secret

Not written yet; it's part of SR6. In short:

- Changing `AUTH_SECRET` signs everyone out.
- Changing `ENCRYPTION_KEY` needs every encrypted file re-encrypted first.

Don't change either by hand until the procedure exists.

## The demo on Streamlit Community Cloud

The demo ([demo-mode-plan.md](demo-mode-plan.md)) runs on **Streamlit Community Cloud**. It is the same code in demo mode (`UVALU_DATA_MODE=demo`): no sign-in, a fixed snapshot of 9 stocks and 1 ETF, no data API at run time, and a temporary workspace per process, so no data survives a restart.

| | Personal app (your machine) | Community Cloud (demo) |
|---|---|---|
| Branch | `master` at a release | `deploy/demo` (the latest release tag plus data commits) |
| TLS | Self-signed localhost certificate (`run_app.py`) | Streamlit |
| Secrets | `.env` (`AUTH_SECRET`, `ENCRYPTION_KEY`, …) | Only `UVALU_DATA_MODE`; the demo makes throwaway keys itself |
| Data | Live fetches, `data/` and `.cache/` | `demo-data/`, refreshed by the `demo-data` GitHub workflow |
| Who | You | Invited viewers (private app) |

`.streamlit/config.toml` sets no certificate, so it starts on Community Cloud as it is. A local `python run_app.py` passes the self-signed localhost certificate on the command line; behind Caddy the app runs on plain HTTP, as before.

### 1. Data first

1. GitHub › Settings › Secrets and variables › Actions: `EODHD_API_KEY` (done 18 Oct 2026).
2. The `demo-data` workflow builds `deploy/demo` from the newest `v*` release tag. Merge the demo code into `master` and cut a release first (DM-D18); before that release exists, start the workflow by hand (Actions › demo-data › Run workflow) with `ref` = `master`.
3. The first run creates `deploy/demo`, merges the release, fetches the prices (11 EODHD calls) and the ECB rates, and pushes. Start it once more with `job` = `dividends` (10 calls) on a later day, or wait for Sunday's scheduled run.

*Check:* `deploy/demo` exists, its `demo-data/refresh.json` shows today's run, and `demo-data/budget.json` is at or below 18.

### 2. Create the app

On share.streamlit.io › Create app:

- **Repository:** `svenclaes76/UV` · **Branch:** `deploy/demo` · **Main file:** `app.py`
- **App URL:** `uvalu-demo` (DM-D20)
- **Advanced settings › Python:** 3.12 (the app needs 3.12 or newer; CI tests on 3.12)
- **Advanced settings › Secrets:**

  ```toml
  UVALU_DATA_MODE = "demo"
  # UVALU_FEEDBACK_URL = "https://…"   # once the form exists (DM-D10); adds "Give feedback →" to the notice
  ```

  Top-level secrets are also environment variables, which is how the app reads them. **Never** put `AUTH_SECRET`, `ENCRYPTION_KEY` or the EODHD key here: the demo doesn't need them.

Dependencies come from `requirements.txt` (there is no `uv.lock`, `Pipfile` or `environment.yml`, which would take precedence). It resolves on Linux with Python 3.12 from binary wheels; the first build takes a few minutes.

*Check:* the app starts on the Dashboard with the demo notice ("9 European stocks · end-of-day prices to <date> …"), the date matches `refresh.json`, and the logs (Manage app › Logs) show `demo workspace ready` and no `demo.offline_request` other than `^GSPC`.

### 3. Viewers

The app is **private** (the free tier allows one private app). Share › Invite viewers by email; they sign in to Streamlit with that address. Before inviting:

- Every invited viewer can see the app's analytics, including the last 20 viewers' email addresses (L36). Say so in the invitation, for example: "Other invited testers can see that you opened the demo."
- Testers you know only, until EODHD has answered in writing (L38) and the items before backers in [open-items.md](open-items.md) are done (L3, L4, L33).

Analytics: app menu › Analytics (total viewers, last 20 viewers). That's the only analytics during the invite-only phase (DM-D10).

### 4. Day to day

- **Data:** the workflow runs weekdays at 21:00 UTC (prices and FX) and Sundays (dividends). Each data commit redeploys the app. A failed fetch keeps yesterday's data; the notice shows its date. A run stopped by the budget fails visibly in Actions.
- **Code:** a new release tag reaches the demo with the next workflow run (it merges the tag into `deploy/demo`), or start the workflow by hand. Never commit to `deploy/demo` yourself, and never merge it into `master`.
- **Fundamentals:** after the annual reports (DM-D8), edit `demo-data/fundamentals/*.json` on `master` (`python tools/demo_fundamentals.py check`), release, and the next run brings them over.
- **Founder holdings:** a trade in one of the demo stocks goes into `demo-data/compliance/founder_holdings.json` within 2 business days, like `data/compliance/founder_holdings.json` (L32).
- **Sleep:** an app without visitors for about 12 hours sleeps; the next visitor sees a wake-up button and waits 30–60 s. Open it yourself before a presentation.
- **Before pushing a change:** run the demo locally (`.claude/launch.json` › `uvalu-demo`, port 8530). There's no second private app for a staging copy.

### 5. Trade-offs to know

- Community Cloud reads the whole private repository, including business plans and legal drafts (DM-D12). Accepted for the invite-only phase; revisit before the demo goes public.
- Hosting is in the US (Snowflake). The demo privacy notice ([policies/demo/privacy-notice.md](legal/policies/demo/privacy-notice.md)) covers it; Uvalu itself stores nothing about visitors.
- Limits: 1 private app, 2.7 GB per app (checked 18 Oct 2026).
