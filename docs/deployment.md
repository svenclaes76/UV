# Deployment

How the production server is set up and looked after. This covers:

- the baseline from the [security review](security-review.md) (SR2)
- the offsite backups the privacy notice promises (L8)
- the master secrets (SR5, SR6)
- the demo on Streamlit Community Cloud (DM-6), at the end

**Setup:** Ubuntu 24.04 LTS on a Hetzner Cloud server in the EU, Caddy in front of Streamlit, one systemd service, and daily encrypted offsite backups to a Hetzner Storage Box. The files are in [`deploy/`](../deploy/).

## Setting up the server

Do these in order. Each step ends with a check.

### 1. Create the server

- In Hetzner Cloud, create an Ubuntu 24.04 server in Falkenstein or Nuremberg, with **your SSH key only** (no root password).
- Attach a **Hetzner Cloud Firewall** that allows inbound TCP 22 (from your own IP address, if it's fixed), 80 and 443, and nothing else.
- Point DNS for `uvalu.app` and `www.uvalu.app` (A and AAAA records) at the server.

*Check:* `ssh root@<server>` works with your key.

### 2. Harden the base system

```bash
apt update && apt full-upgrade -y
apt install -y unattended-upgrades ufw borgbackup python3.12-venv git
dpkg-reconfigure -plow unattended-upgrades
adduser --disabled-password --gecos "" admin && usermod -aG sudo admin
mkdir -p /home/admin/.ssh && cp ~/.ssh/authorized_keys /home/admin/.ssh/ && chown -R admin: /home/admin/.ssh
```

`dpkg-reconfigure` asks whether to install security updates automatically: answer Yes.

In `/etc/ssh/sshd_config`, set `PasswordAuthentication no` and `PermitRootLogin no`, then `systemctl restart ssh`. Keep the current session open until a new login as `admin` works.

```bash
ufw default deny incoming && ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw enable
```

*Check:* `ssh admin@<server>` works, `ssh root@<server>` is refused, and `ufw status` lists only 22, 80 and 443.

### 3. Install the app

```bash
sudo adduser --system --group --home /opt/uvalu uvalu
sudo -u uvalu git clone git@github.com:svenclaes76/UV.git /opt/uvalu
cd /opt/uvalu && sudo -u uvalu python3.12 -m venv .venv
sudo -u uvalu .venv/bin/pip install -r requirements-lock.txt
```

`requirements-lock.txt` pins every package, including the ones the app's own
dependencies pull in, so the server runs the versions CI tested and audited
(SR7). Don't install from `requirements.txt` here: it also holds the test tools.

The repository is private. Give the server a **read-only deploy key** in GitHub (repo › Settings › Deploy keys), not your own key.

### 4. Put the secrets in place

When moving an existing deployment, copy `.env` as described under [Moving to a new server](#moving-to-a-new-server). On a first install, generate new secrets instead:

```bash
python3 -c "import secrets; print('AUTH_SECRET=' + secrets.token_hex(32)); print('ENCRYPTION_KEY=' + secrets.token_hex(32))" | sudo -u uvalu tee /opt/uvalu/.env > /dev/null
sudo chmod 600 /opt/uvalu/.env
```

Make the [offline copy](#keep-an-offline-copy) straight away.

*Check:* `ls -l /opt/uvalu/.env` shows `-rw------- uvalu uvalu`.

### 5. Run the app as a service

```bash
sudo cp /opt/uvalu/deploy/uvalu.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now uvalu
```

`run_app.py` sees `UVALU_BEHIND_PROXY=1` and starts Streamlit on `127.0.0.1:8501` over plain HTTP, with XSRF protection on. Caddy handles TLS.

*Check:* `systemctl status uvalu` is active, and `ss -tlnp | grep 8501` shows `127.0.0.1:8501` only, never `0.0.0.0`.

### 6. Put Caddy in front

Install Caddy from its official apt repository (caddyserver.com › Install › Debian/Ubuntu), then:

```bash
sudo cp /opt/uvalu/deploy/Caddyfile /etc/caddy/Caddyfile
sudo mkdir -p /var/log/caddy && sudo chown caddy: /var/log/caddy
sudo systemctl reload caddy
```

*Check:*

- `https://uvalu.app` shows the sign-in page.
- `http://uvalu.app` redirects to HTTPS.
- `curl -sI https://uvalu.app` shows `strict-transport-security`, `x-frame-options: DENY` and `content-security-policy-report-only`.
- The SSL Labs test gives A or better.

### 7. Offsite backups

Order a **Hetzner Storage Box** in an EU location, enable SSH access, and **leave its automatic snapshots off**. They would keep data longer than the 30 days privacy notice §8 promises.

On the server:

```bash
sudo mkdir -p /etc/uvalu && sudo chown uvalu: /etc/uvalu && sudo chmod 700 /etc/uvalu
sudo -u uvalu ssh-keygen -t ed25519 -N "" -f /etc/uvalu/storagebox_ed25519
```

Add `/etc/uvalu/storagebox_ed25519.pub` to the Storage Box (Hetzner Robot › Storage Box › SSH keys). Then write the repository address and a passphrase, and create the encrypted repository:

```bash
echo 'BORG_REPO=ssh://uXXXXXX@uXXXXXX.your-storagebox.de:23/./uvalu' | sudo -u uvalu tee /etc/uvalu/backup.env
sudo -u uvalu sh -c 'python3 -c "import secrets; print(secrets.token_urlsafe(32))" > /etc/uvalu/borg.pass && chmod 600 /etc/uvalu/borg.pass'
sudo -u uvalu sh -c '. /etc/uvalu/backup.env; export BORG_REPO BORG_PASSCOMMAND="cat /etc/uvalu/borg.pass" BORG_RSH="ssh -i /etc/uvalu/storagebox_ed25519"; borg init --encryption=repokey-blake2'
sudo cp /opt/uvalu/deploy/uvalu-backup.service /opt/uvalu/deploy/uvalu-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now uvalu-backup.timer
```

Then save the two things that unlock the backups, both in the same offline place as `.env`:

1. **The passphrase:** show it once with `sudo cat /etc/uvalu/borg.pass`, and copy it.
2. **The repository key:** in repokey mode borg keeps the key inside the repository on the Storage Box, protected by the passphrase. If that copy is ever damaged, the passphrase alone can't open the backups. Export it once:

   ```bash
   sudo -u uvalu sh -c '. /etc/uvalu/backup.env; export BORG_REPO BORG_PASSCOMMAND="cat /etc/uvalu/borg.pass" BORG_RSH="ssh -i /etc/uvalu/storagebox_ed25519"; borg key export --paper'
   ```

   This prints the key as short lines with checksums, made to be typed back in. Copy the whole block into the password manager entry, or print it. The key is useless without the passphrase, but keep both offline anyway.

The key doesn't change, so one export is enough unless you recreate the repository.

**What's backed up:**

- `data/`: portfolios, settings, the signal history and Admin backups
- `.cache/users.json`: accounts

The backup runs daily (`deploy/offsite-backup.sh`), borg-encrypted on top of the app's own encryption. `.env` is never backed up offsite. Migration snapshots stay local; the app prunes them after 30 days.

**Retention:** every run deletes archives older than 29 days (`borg prune --keep-within 29d`), so data removed from the app is gone from the offsite copies within 30 days.

*Check:* run `sudo systemctl start uvalu-backup`, then confirm `journalctl -u uvalu-backup` ends without errors and `borg list` shows one archive.

### 8. Content security policy

The Caddyfile sends the policy as **report-only** first. Streamlit and the app's own small scripts need inline script and style, so the policy can't be strict. It still forbids framing the app (`frame-ancestors 'none'`), plugins and foreign form targets.

1. Open every page in a browser with the developer console open: Dashboard, Screener, Watchlist, Portfolio, Risk, Analysis, Settings, Admin, and the sign-in page.
2. Look for "Content Security Policy" report messages. Add only what a real page needs.
3. When a full round shows none, rename the header to `Content-Security-Policy` in `/etc/caddy/Caddyfile` and in `deploy/Caddyfile`, then `systemctl reload caddy`.

### 9. Restore test (SR6)

Do this once after setup, and again after any change to the backup set-up. Use a throwaway server or VM, never production:

1. Install the app as in steps 2–3.
2. Put `.env` and `borg.pass` there from the **offline copies**, not from the production server.
3. `borg extract` the latest archive into `/opt/uvalu`. If borg reports the repository key missing or damaged, restore it from the offline paper key with `borg key import --paper`, and type it back in.
4. Start the app and sign in with your own account. Check your portfolio is there.
5. Delete the throwaway server, and record the date below.

| Date | Archive | Result | By |
|---|---|---|---|
| — | — | not done yet | — |

## Updating the app

```bash
cd /opt/uvalu && sudo -u uvalu git pull
sudo -u uvalu .venv/bin/pip install -r requirements-lock.txt
sudo systemctl restart uvalu
```

`run_app.py` migrates the data on start, after taking a snapshot.

## What the app does itself

- **Per-IP sign-in limit:** 20 failed password sign-ins from one address in 15 minutes block that address for the rest of the window, silently, with the same message as any failure. A proxy can't do this, because sign-in happens inside Streamlit's websocket. The app reads the client address from Caddy's `X-Forwarded-For` header, and trusts it only on a localhost connection.
- **Per-account lock:** set in Admin › Security.
- **Session cookies:** `SameSite=Strict`, and `Secure` when served over HTTPS.
- **Security logs:** kept 31 days. Caddy's access log uses the same retention.

## The master secrets (`.env`)

`.env` in the app folder holds the two secrets that protect every account:

- `AUTH_SECRET` signs sessions. Anyone who has it can sign in as anyone.
- `ENCRYPTION_KEY` encrypts the user store, portfolios, settings and backups. Without it, none of that data, including the offsite backups, can be read.

**The app never hands these out.** There is no download in Admin (removed for SR5, [security review](security-review.md) #5), and backups don't include `.env`. They move only as described below.

### Keep an offline copy

Keep one copy of `.env`, the borg passphrase and the exported borg key (step 7) outside the server, in a password manager entry or printed and stored safely. Don't keep them next to the backups. If the server is lost, these copies are the only way to read the offsite backups (SR6).

Update the copy whenever either secret changes.

### Moving to a new server

1. Set up the new server as in steps 1–3, but don't start the app yet.
2. Copy `.env` from the old server over SSH, straight to the new one or through your own machine:

   ```bash
   scp admin@old-server:/opt/uvalu/.env admin@new-server:/tmp/uvalu.env
   ```

3. On the new server, move it into place, readable only by the app's user:

   ```bash
   sudo mv /tmp/uvalu.env /opt/uvalu/.env && sudo chown uvalu: /opt/uvalu/.env && sudo chmod 600 /opt/uvalu/.env
   ```

4. Restore the data with `borg extract` from the offsite backups, by copying the data folders, or with Admin › Backups.
5. Start the app and sign in. If the user store can't be read, the key doesn't match. Check that `.env` arrived unchanged.
6. If you copied `.env` through your own machine, delete that copy. The offline copy is the only one that should exist besides the server's.

### Rotating a secret

Not written yet; it's part of SR6. In short:

- Changing `AUTH_SECRET` signs everyone out.
- Changing `ENCRYPTION_KEY` needs every encrypted file re-encrypted first.

Don't change either by hand until the procedure exists.

## The demo on Streamlit Community Cloud

The demo ([demo-mode-plan.md](demo-mode-plan.md)) runs on **Streamlit Community Cloud**, not on the Hetzner server. It is the same code in demo mode (`UVALU_DATA_MODE=demo`): no sign-in, a fixed snapshot of 9 stocks and 1 ETF, no data API at run time, and a temporary workspace per process, so no data survives a restart.

| | Hetzner (personal / beta) | Community Cloud (demo) |
|---|---|---|
| Branch | `master` at a release | `deploy/demo` (the latest release tag plus data commits) |
| TLS | Caddy | Streamlit |
| Secrets | `.env` (`AUTH_SECRET`, `ENCRYPTION_KEY`, …) | Only `UVALU_DATA_MODE`; the demo makes throwaway keys itself |
| Data | Live fetches, `data/` and `.cache/` | `demo-data/`, refreshed by the `demo-data` GitHub workflow |
| Who | Invited beta users | Invited viewers (private app) |

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
