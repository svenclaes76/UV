# Uvalu — Authentication Implementation Plan

Primary methods: password + OAuth (Google). Optional add-on: TOTP 2FA. Future premium upgrade: Passkeys (WebAuthn).

Design principle: one unified identity (`users` table) with multiple ways to authenticate into it, rather than separate systems per method.

---

## Phase 1 — Foundation: unified identity + password + OAuth

### Data model

Extend the existing `users` table so one account can have either or both login methods:

| Field | Notes |
|---|---|
| `id` | primary key |
| `email` | unique |
| `password_hash` | nullable — null if OAuth-only |
| `auth_provider` | `local` / `google` / etc., nullable |
| `oauth_subject_id` | nullable — the `sub` claim from the provider |
| `created_at` | |
| `role` | existing Owner / Editor / Viewer |

Password hashing: `argon2-cffi` (preferred for new projects) or `passlib[bcrypt]`. Never roll your own.

### Password path

- Login form: email + password → look up user → verify hash.
- Signup: enforce a minimum password policy (length over complexity — NIST guidance is 12+ chars). Check against a breached-password list via `zxcvbn` or the k-anonymity HaveIBeenPwned API. Skip arbitrary "must contain a symbol" rules.
- Rate-limit login attempts per account/IP (simple counter in DB or Redis) — Streamlit has no built-in throttling.
- Session handling: Streamlit reruns the whole script on every interaction, so store `user_id` in `st.session_state` after login, backed by a signed, httpOnly cookie (`streamlit-cookies-manager` or a small custom component) so sessions survive a page refresh, not just script reruns.

### OAuth path (Google, optionally Microsoft)

Streamlit's native `st.login()` / `st.user` (requires `streamlit[auth]`, i.e. Authlib) handles the full OIDC flow.

Config in `.streamlit/secrets.toml`:

```toml
[auth]
redirect_uri = "https://yourapp.com/oauth2callback"
cookie_secret = "<random 32+ char string>"

[auth.google]
client_id = "..."
client_secret = "..."
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

- On first Google login, look up or create a user row keyed on `email`/`sub`, linked to the same `users` table as password accounts (so a user could later also set a password on the same account).
- `st.user.is_logged_in` and `st.user.email` are the source of truth for the OAuth path; reconcile against the `users` table for role/RBAC.

**Effort**: the bulk of the work, but nothing here needs a custom browser component — deliberately the easiest phase, to get a solid base before adding complexity.

### First-admin bootstrap (no GUI surface)

A fresh Uvalu instance needs a way to create its first Owner account without exposing any setup flow in the app itself.

**Primary mechanism: env-var bootstrap on startup**
- On app startup, check whether the `users` table is empty (fresh instance).
- If empty *and* `ADMIN_EMAIL` is set in the environment / `secrets.toml`, create or promote that account to `role = Owner`:
  - **Password path**: if `ADMIN_PASSWORD` is also set, create the user with that password (hashed, as usual) and `role = Owner`.
  - **OAuth path**: no password needed — when a Google login completes for an email matching `ADMIN_EMAIL`, auto-promote that account to `role = Owner` on creation instead of the default role new signups get.
- Guard the whole check on "table is empty," not on a version flag or a one-time marker file — this makes it naturally idempotent (safe to leave in the codebase permanently) and it never re-triggers once any user exists.
- No GUI surface at all: entirely a deploy-time config value, not discoverable or reachable through the app UI, and there's no setup-wizard race window between deploy and first login.

**Recovery/complement: one-off CLI script**
- `scripts/create_admin.py --email you@example.com` inserts directly into the DB with `role = Owner`.
- Prompts interactively for a password (password path) so it's never left in shell history.
- Run once from the server/container shell — not through the app — for local dev setup or as a "break glass" path if the bootstrap account is ever lost or misconfigured.

---

## Phase 2 — Optional TOTP add-on

- Schema addition: `totp_secret` (encrypted at rest), `totp_enabled` (bool).
- Applies only to the **password** login path — OAuth users already benefit from whatever 2FA they have on Google's side.
- Settings page: "Enable 2FA" → generate secret with `pyotp.random_base32()` → render QR via `qrcode` (`pyotp.totp.TOTP(secret).provisioning_uri(...)`) → user scans and confirms a code before `totp_enabled` flips to `True`.
- Login flow: password OK → if `totp_enabled`, show a second input → verify with `pyotp.TOTP(secret).verify(code, valid_window=1)`.
- Provide 8–10 single-use backup codes at setup (hashed in storage like passwords) — the standard recovery path if a device is lost.
- Optional: "remember this device for 30 days" via a signed cookie.

**Effort**: low — pure server-side Python, fits Streamlit's model like the password flow.

---

## Phase 3 — Passkeys (premium/optional upgrade, later)

- Schema addition: `passkeys` table (one user can have several): `credential_id`, `public_key`, `sign_count`, `device_label`, `created_at`.
- Server-side: `py_webauthn` (Duo Labs, actively maintained) handles generating registration/authentication challenges and verifying responses — don't implement WebAuthn's CBOR/attestation parsing yourself.
- **Streamlit-specific blocker**: WebAuthn ceremonies (`navigator.credentials.create/get`) are browser JavaScript APIs; Streamlit has no native hook into them. Requires a small custom Streamlit component (minimal React or vanilla-JS wrapper using `streamlit-component-lib`) whose only job is: receive a challenge from Python → call the browser API → return the signed response to Python. Self-contained, one-time build.
- Treat as additive to Phase 2, not a replacement — keep password/OAuth as fallback, and allow multiple passkeys per user (phone + laptop) since losing the only one otherwise blocks recovery.
- Ship registration only first, verify round-trip end to end on a test account, then add the login flow.

---

## Suggested build order

1. Password auth + user table (own it fully — fallback for everyone)
2. `st.login()` Google OAuth wired to the same user table
3. TOTP settings page + backup codes
4. Passkey custom component, gated behind a feature flag until tested on a few real devices
