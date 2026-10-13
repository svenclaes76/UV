# Deployment

How the production server is set up and looked after. Phase 2 of the [before-strangers plan](before-strangers-plan.md) completes this page with the full baseline (SR2): reverse proxy, TLS, headers, firewall, rate limits.

## The master secrets (`.env`)

`.env` in the app folder holds the two secrets that protect every account:

- `AUTH_SECRET` signs sessions. Anyone who has it can sign in as anyone.
- `ENCRYPTION_KEY` encrypts the user store, portfolios, settings and backups. Without it, none of that data, including the offsite backups, can be read.

**The app never hands these out.** There is no download in Admin (removed for SR5, [security review](security-review.md) #5), and routine backups don't include `.env`. They move only as described below.

### Keep an offline copy

Keep one copy of `.env` outside the server, in a password manager entry or printed and stored safely. Don't keep it next to the backups. If the server is lost, this copy is the only way to read the offsite backups (SR6).

Update the copy whenever either secret changes.

### Moving to a new server

1. Set up the new server and install the app, but don't start it yet.
2. Copy `.env` from the old server over SSH, straight to the new one or through your own machine:

   ```bash
   scp olduser@old-server:/path/to/uvalu/.env newuser@new-server:/path/to/uvalu/.env
   ```

3. On the new server, make the file readable only by the app's user:

   ```bash
   chmod 600 /path/to/uvalu/.env
   ```

4. Restore the data: copy the data folders, or restore a backup in Admin › Backups.
5. Start the app and sign in. If the user store can't be read, the key doesn't match. Check that `.env` arrived unchanged.
6. If you copied `.env` through your own machine, delete that copy. The offline copy above is the only one that should exist besides the server's.

### Rotating a secret

Not written yet; it's part of SR6. In short:

- Changing `AUTH_SECRET` signs everyone out.
- Changing `ENCRYPTION_KEY` needs every encrypted file re-encrypted first.

Don't change either by hand until the procedure exists.
