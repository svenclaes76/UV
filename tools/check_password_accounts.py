"""List accounts that can't sign in during the beta: no password (T1 in
docs/open-items.md). Read-only.

Usage, on the server, from the repo root (needs the same .env as the app):
    python tools/check_password_accounts.py

Since the free beta signs in with a password only (provider buttons hidden,
no OAuth auto-provisioning), an active account that was created through
Google sign-in and never set a password is locked out. Fix each one with
Admin portal → Users → Send password reset → Generate reset link: the
single-use link sets a password even when the account never had one. Invited accounts are skipped: they set
a password when they accept the invite.

Exit code 0 when every active account has a password, 1 otherwise.
``run_app.py`` runs the same check on every start (warning only), and the
Admin portal → Users page lists these accounts.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from auth import _load_users, passwordless_accounts
    users = _load_users()
    found = passwordless_accounts(users)
    print(f"{len(users)} account(s) in the user store.")
    if not found:
        print("Every active account has a password. Nothing to do.")
        return 0
    print(f"{len(found)} account(s) without a password — locked out during the beta:")
    for email, status, providers in found:
        print(f"  {email}  status={status or '-'}  linked={', '.join(providers) or 'none'}")
    print("Fix: Admin portal → Users → Send password reset → Generate reset link; send each person the link.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
