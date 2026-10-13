# Deployment

How the production server is set up and looked after. This covers:

- the baseline from the [security review](security-review.md) (SR2)
- the offsite backups the privacy notice promises (L8)
- the master secrets (SR5, SR6)

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
sudo -u uvalu .venv/bin/pip install -r requirements.txt
```

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
sudo -u uvalu .venv/bin/pip install -r requirements.txt
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
