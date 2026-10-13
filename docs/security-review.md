# Security review

13 Oct 2026 · First-pass review in the role of expert profile [07](experts/07-security-tester.md): a web-application penetration tester. There is no separate persona file for this role. **This is a code review, not a penetration test.** Nothing was attacked, and the production server wasn't examined, because its set-up isn't in the repo. It doesn't replace the external test and retest the profile describes.

**Reviewed:**

- `auth.py` (login, lockout, sessions, two-factor, reset and invite tokens) and `uvalu/authgate.py` (cookie and session handling, logout).
- `crypto.py` and `backup.py`, the Admin portal's secrets export, and `workbook.py` (Excel export).
- `.streamlit/config.toml`, a sample of the HTML rendering in `uvalu/components.py`, and the installed versions of the security-relevant packages.

The two severe issues found in August 2026 (session revocation, secrets in backups) are fixed. This review confirmed the revocation check is in place.

## Conclusion

| # | Finding | Severity |
|---|---|---|
| 1 | The two-factor code can be guessed without limit | **High** |
| 2 | Login messages and timing reveal which emails have an account | Medium |
| 3 | The session token is readable by JavaScript and has no cookie flags | Medium |
| 4 | No production deployment is defined: TLS, proxy, security headers | Medium |
| 5 | Exporting the master secrets needs no re-authentication | Medium |
| 6 | Lockout is per account only: lock-out abuse and password spraying | Low–medium |
| 7 | Reset and invite tokens are stored as plain values | Low |
| 8 | Excel export: text starting with "=" becomes a formula | Low |
| 9 | Key escrow, key rotation and restore testing are not documented | Low–medium |
| 10 | No automated check for vulnerable dependencies | Low |

**What is done well:**

- bcrypt for passwords and backup codes
- the breached-password check sends only a 5-character hash prefix
- server-side session records, so suspension and revocation take effect at once
- a locked account doesn't check the password at all
- random reset and invite tokens (`token_urlsafe(24)`) with short lives: reset 30 minutes, invite 7 days
- the two-factor challenge lives only in server memory
- encrypted user store and portfolios
- master secrets kept out of routine backups
- company names HTML-escaped (`_name_html`)
- auth events logged with hashed user ids

## 1. Unlimited guessing of the two-factor code (high)

**Code.** `auth.complete_totp_login` checks the 6-digit code with `valid_window=1`, so three codes are valid at any moment. Nothing counts failures:

- A wrong code is logged, but it never adds to `failed_attempts` and never locks anything.
- The challenge stays open for 5 minutes (`_TOTP_PENDING_TTL_MIN`). After that, entering the correct password starts a new one and **resets** the password counter.
- `complete_backup_code_login` has the same gap.

**Impact.** Someone with a stolen password, which is exactly the case two-factor exists for, can try codes as fast as the app answers. Every 5 minutes they re-enter the password. Each try has a chance of about 3 in a million. At even a few tries per second, the second factor falls within hours to days. A valid code can also be used more than once within its 90-second window.

**Fix.**

- Count failed codes per account, for example 5. Then lock the account through the same `locked_until` path, and require the password again.
- Don't reset the counter on a correct password while a code challenge is pending.
- Remember the last accepted time step and reject its reuse.
- Apply the same rules to backup codes.

## 2. Account enumeration (medium)

**Code.** `auth.login` returns:

- for an unknown email: "Invalid email or password."
- for a known email with a wrong password: "Invalid email or password. 4 attempts remain…"
- for a locked account: "This account is temporarily locked…"

The function's docstring intends unknown emails not to reveal anything, but the *difference* between these messages does. The unknown-email path also returns without running bcrypt, so the response time differs by about the cost of one hash.

**Fix.** Return the same message for every failure. Drop the remaining-attempts count, or show it only after a successful sign-in. Run a dummy `bcrypt.checkpw` on the unknown-email path so the timing matches. The lockout itself can stay.

## 3. Session token handling (medium)

**Code.** After sign-in, a script stores the JWT in `localStorage` and sets the `uv_jwt` cookie from JavaScript (`authgate._sync_cookie_script`) with `path=/; max-age=86400`. There is no `Secure` and no `SameSite` attribute. Because JavaScript sets it, it can't be `HttpOnly`, and the copy in `localStorage` is readable by any script on the page.

**Impact.** One cross-site-scripting (XSS) flaw anywhere is a full account takeover for the token's lifetime: up to 7 days with the "7 d" session setting. That includes the Admin's account. The app renders HTML in 323 places (`unsafe_allow_html=True`). The places sampled escape provider data correctly, but that is a large surface to keep perfect by hand.

**Fix**, in order of effort:

1. Add `; Secure; SameSite=Strict` to both cookies (`uv_jwt`, `uv_td`).
2. Set a Content-Security-Policy at the reverse proxy (#4) that blocks inline scripts from other origins and framing.
3. Add a test that feeds `<img src=x onerror=…>` as a company name, ticker, note and display name through the main components, and asserts it comes out escaped.
4. Longer term, drop the `localStorage` copy and rely on the cookie alone. Streamlit's sandboxed iframe was the reason for the current design, so this needs a spike.

## 4. Production deployment (medium)

The repo has a localhost launcher with a self-signed certificate. The architecture doc itself says "not for production use". Nothing describes how the server is exposed: TLS termination, reverse proxy, firewall, security headers, process user, or where `.env` lives and with what file permissions.

**Fix.** Before anyone outside your own devices uses it, write and apply a short deployment baseline:

- A reverse proxy (Caddy or nginx) with a public certificate. Redirect HTTP to HTTPS, plus HSTS.
- Headers: CSP, `frame-ancestors 'none'`, `X-Content-Type-Options`, `Referrer-Policy`.
- Streamlit bound to localhost only, behind the proxy.
- A firewall that allows only 443 and SSH (keys only).
- The app running as an unprivileged user, with `.env` readable only by that user.
- Automatic security updates.

`enableStaticServing = true`: check that the static folder contains nothing private.

## 5. Master secrets export (medium)

**Code.** Admin › the `.env` dialog calls `backup.export_env_key()` and puts the bytes into a download button, so they are sent to the browser when the dialog opens. That file holds `AUTH_SECRET`, which can sign in as anyone, and `ENCRYPTION_KEY`, which can decrypt everyone's data. No password or two-factor check is asked first.

**Impact.** A hijacked Admin session (#3) becomes a full compromise of every account and all data, including the offsite backups.

**Fix.** Remove the export from the web UI. Copy `.env` over SSH when setting up a new server. If it has to stay, require the password and a two-factor code just before reading the file, and log the export as a high-severity event.

## 6. Lockout abuse and password spraying (low–medium)

The lockout counts per account, so anyone who knows an email (#2) can keep that account locked. Trying one common password against many accounts never triggers a lock. Per-IP limiting was deliberately deferred.

**Fix.** Add a per-IP limit at the reverse proxy (#4), which is simplest, or in the app using the forwarded client address. After #2 is fixed, knowing which emails exist becomes harder too.

## 7. Tokens stored as plain values (low)

Reset and invite tokens sit in the user store as issued. The store is encrypted, but anyone with the key or a decrypted backup gets usable links. **Fix:** store a SHA-256 of each token and compare against that. It costs one line per check.

## 8. Formulas in the Excel export (low)

`workbook._cell` writes strings as they are. openpyxl stores a string that starts with `=` as a formula. A note or name typed as `=HYPERLINK(…)` runs as a formula when the file is opened. The data is the user's own, but exported files get shared. **Fix:** prefix text that starts with `= + - @` with an apostrophe, or write those cells explicitly as text.

## 9. Keys, rotation and restores (low–medium)

- **One key protects everything** (PBKDF2 over `ENCRYPTION_KEY` with a fixed salt, then Fernet). That's acceptable. But if the server is lost and the only copy of the key was in its `.env`, every offsite backup is unreadable. Keep an offline copy of `.env`, in a password manager or on paper, separate from the backups.
- **Rotation:** there is no procedure for rotating `AUTH_SECRET` (all sessions end) or `ENCRYPTION_KEY` (re-encrypt everything). Write both down before you need them.
- **Restores:** no restore test is on record. Restore an offsite backup onto a fresh machine once, and note the date.

## 10. Dependencies (low)

The installed versions are recent: Streamlit 1.60, PyJWT 2.13, cryptography 48, bcrypt 5, PyOTP 2.10. No vulnerability scanner runs, and `pip-audit` isn't installed. **Fix:** add `pip-audit` to the CI workflow (`tests.yml`), and pin versions for the production server.

## Recommended changes, in order of value

1. **Two-factor attempt limit** and code-reuse protection (SR1). It is a small change, and two-factor is worthless without it.
2. **Deployment baseline** with TLS, a proxy, headers, a firewall and per-IP limits (SR2, which covers #4 and #6).
3. **Uniform login failures** with constant timing (SR3).
4. **Cookie flags, an XSS regression test,** and a CSP via the proxy (SR4).
5. **Remove the `.env` export from the UI,** or require re-authentication (SR5).
6. **Key escrow, a rotation procedure and one restore test** (SR6).
7. **Hashed tokens, safe Excel cells, `pip-audit` in CI** (SR7).

SR1–SR5 belong before inviting anyone you don't know personally, the same trigger as the legal items.

## For the real tester

Give them a staging copy of the production set-up (#4), a test account per role, a two-factor-enabled account, and this review. Ask them to:

- confirm #1–#3 against the running app
- test horizontal access (user A reaching user B's portfolio through crafted session state or URLs) and the role gates, which this review only read in code
- test Streamlit's websocket session handling
- retest after the fixes, with a short confirmation letter
