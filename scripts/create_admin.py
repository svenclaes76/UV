#!/usr/bin/env python3
"""Break-glass CLI to create (or promote) an Admin account directly in
.cache/users.json, bypassing the app UI entirely.

Standalone — never imported by app.py or shipped as part of the running
app, same category as .claude/skills/run-uvalu/_dev_entry.py's dev-only
entrypoint. Two situations this covers:
  - Fresh instance, no ADMIN_EMAIL/ADMIN_PASSWORD bootstrap configured (or
    it failed) — creates the first account, which register() auto-promotes
    to Admin since the store is empty.
  - Break-glass recovery — the store already has accounts but no working
    Admin (e.g. the only Admin got suspended or locked out) — explicitly
    promotes the given account to Admin regardless of whether it's new or
    already existed.

Usage (from the repo root):
    python scripts/create_admin.py --email you@example.com
"""
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import auth  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True, help="Account to create or promote to Admin.")
    args = parser.parse_args()
    email = args.email.strip().lower()

    password = getpass.getpass("Password (min 8 characters, not echoed): ")
    if password != getpass.getpass("Confirm password: "):
        print("Passwords don't match.", file=sys.stderr)
        return 1

    ok, msg = auth.register(email, password)
    if not ok and "already exists" not in msg:
        print(msg, file=sys.stderr)
        return 1

    ok2, msg2 = auth.set_role(email, "Admin")
    if not ok2:
        print(msg2, file=sys.stderr)
        return 1
    print(f"{email} is now an Admin." if ok else f"{msg} {msg2}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
