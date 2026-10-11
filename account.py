"""
Account deletion — every trace of one account, at once (Settings › Privacy ›
Delete account and the Admin portal's Delete user).

Deleted at once: the login record (password hash, sessions, two-step
verification, trusted devices), the portfolio folder (positions, sales,
dividends, cash, watchlist, targets, history), the user's settings file and
the account's backups in the Admin backup history. Migration snapshots hold
every user's data and are pruned after 30 days
(uvalu.migrations.runner.SNAPSHOT_MAX_AGE_DAYS), so the privacy notice's
"removed from backups within 30 days" holds for them too. Logs carry only a
hashed user id and follow their own retention.

No Streamlit import — unit-tested in tests/test_account.py.
"""
from __future__ import annotations

import shutil

import auth
import backup
import portfolio
import settings
from uvalu import logkit


def can_delete(email: str) -> tuple[bool, str]:
    """(allowed, reason): an unknown account or the last active Admin is refused."""
    email = (email or "").strip().lower()
    users = auth._load_users()
    if not email or email not in users:
        return False, "User not found."
    if users[email].get("role") == "Admin" and auth._other_active_admins(users, email) == 0:
        return False, "Can't delete the last active Admin — promote another user first."
    return True, ""


def delete_account(email: str) -> tuple[bool, str]:
    """Delete an account and all its data. Returns (success, message); nothing
    is removed when it is refused."""
    email = (email or "").strip().lower()
    ok, reason = can_delete(email)
    if not ok:
        return False, reason
    removed_backups = backup.delete_backups_for(email)
    udir = portfolio.user_data_dir(email)
    if udir.name != "default":
        shutil.rmtree(udir, ignore_errors=True)
    settings._settings_file(email).unlink(missing_ok=True)
    ok, msg = auth.delete_user(email)
    if not ok:
        return False, msg
    try:
        from uvalu import migrations
        migrations.prune_expired_snapshots()
    except Exception:
        pass
    logkit.data_mutation(actor=logkit.user_id(), action="account.delete", entity_type="user",
                         entity_id=logkit.user_hash(email), backups_removed=removed_backups)
    return True, msg
