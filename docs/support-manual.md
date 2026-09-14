# Uvalu Support Manual

Step-by-step procedures for whoever operates this deployment — the person who
signs in as Admin, or who has shell access to the server when nobody can sign
in at all. This is **not** the end-user feature guide (see
[user-guide.md](user-guide.md)) and it's not a settings reference (see
[configuration.md](configuration.md)) — it's "here's the exact sequence of
clicks/commands" for the support situations that come up.

Every procedure below either happens in the **Admin portal** (avatar menu →
Admin portal, Admin role required) or on the server's own command line. CLI
commands assume you're in the repo root with the venv active
(`.venv/Scripts/python.exe` on Windows).

---

## Creating an admin account

Which method applies depends on whether any account already exists.

### The very first account on a brand-new deployment

Pick one, before or at first launch:

1. **Set `ADMIN_EMAIL` / `ADMIN_PASSWORD` in `.env`** before starting the app
   for the first time. `bootstrap_admin_from_env()` creates that account at
   boot and promotes it to Admin. Best for a scripted/headless deployment —
   see [configuration.md](configuration.md) for the exact variables.
2. **Just open the login page.** If no account exists yet and the env vars
   above aren't set, the login screen itself shows **"Create the first admin
   account"** instead of the normal sign-in form — fill in an email and
   password there. Best for a human doing the first-run setup by hand.

Both are no-ops once any account exists (including one created via the other
method) — whichever happens first wins.

### Adding another admin (a working Admin already exists)

In the Admin portal → **Users** → **Invite user**, set the role to **Admin**,
and send the invite. There's no outbound email — the dialog shows a one-time
link (`?invite=<token>`, valid 7 days) that you copy and hand to the person
yourself. They open it, set a password (or connect a provider), and they're
in as Admin.

To promote an *existing* account to Admin instead of inviting a new one, use
the role dropdown in that same Users table.

### Break-glass — locked out, no working Admin at all

Every existing Admin got suspended, deleted, or locked out, and there's no
way to sign in and fix it from the UI. Run this on the server:

```bash
.venv/Scripts/python.exe scripts/create_admin.py --email you@example.com
```

It prompts for a password (twice, not echoed) and either creates the account
or promotes it if it already exists — either way, that email is an Admin
when it's done. This bypasses the app entirely (writes straight to
`.cache/users.json`), so it works even if the whole login flow is broken.

---

## Inviting a user / changing a role

Admin portal → **Users** → **Invite user**. Pick a role (**Admin** / Analyst
/ Viewer — see [user-guide.md](user-guide.md) for what each role can do),
send it, and hand the person the one-time link the same way as above. To
change an existing user's role later, use the role dropdown on their row.

You can't demote, suspend, or delete the **last active Admin** — the app
refuses with "Can't demote/suspend/delete the last active Admin — promote
another user first." Promote a second Admin before removing the first.

---

## A user is locked out

**Suspended by mistake, or the account should be re-enabled:** Admin portal →
Users → find the row → **Reactivate**.

**Too many failed password attempts (self-inflicted lockout):** this clears
itself automatically after the configured lock duration (Admin portal →
Security → Rate limiting, default 15 minutes) — there's no manual unlock
action, just wait it out or use the password reset below to get them in
sooner.

**Forgot their password:** there's no self-service reset (no outbound email
exists in this app). Admin portal → Users → row's **⋮** menu → **Send
password reset** → **Generate reset link**. Copy the one-time link (valid 24
hours) and send it to them yourself. Their other sessions stay signed in
until they actually use the link.

**Lost their authenticator device (2FA):** Admin portal → Users → row's **⋮**
menu → **Reset two-factor** (only shown when 2FA is ON for that user). This
disables 2FA on their account entirely — they'll need to re-enroll from
Settings → Security once they're back in.

**Suspicious activity / want to force a fresh sign-in everywhere:** Admin
portal → Users → row's **⋮** menu → **Sign out all sessions**. Combine with
a password reset (above) if the account may be compromised.

---

## Deleting an account

Admin portal → Users → row's **⋮** menu → **Delete account**. This is
permanent and cannot be undone. Blocked the same way as suspend/demote if
it's the last active Admin.

---

## Backups

Admin portal → **Backups**. There's no scheduler — every entry is a manual,
on-demand snapshot.

- **Create one:** **Create backup now**.
- **Download one:** **Download** on its row — you can only download your own
  backups (another admin's snapshot can contain their real portfolio data).
- **Restore one:** **Restore** on its row, then confirm. This replaces *all*
  current portfolio data and settings with that snapshot — read the warning,
  there's no undo.
- **Migrating to a new machine:** a routine backup does **not** include this
  deployment's encryption/signing keys (`AUTH_SECRET`, `ENCRYPTION_KEY`) —
  without them the new machine can't decrypt the old data. Use the separate
  **Export key** button, store that `.env` somewhere apart from your data
  backups, and load it on the new machine before restoring.

---

## Enabling/disabling an exchange

Admin portal → **Data feeds**. Toggling an exchange off removes it from the
Screener and portfolio analysis; you can't disable the last remaining one.

---

## Workspace-wide security policy

Password length/breach-check, 2FA requirement, lockout thresholds, session
lifetime, and OAuth auto-provisioning all live in Admin portal → **Security**
and apply to every account, not just yours. Field-by-field reference is in
[configuration.md](configuration.md); this manual only covers the
per-user actions above.
