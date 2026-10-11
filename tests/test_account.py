"""Unit tests for account.py — deleting an account and all its data."""
from __future__ import annotations

import pandas as pd

import account
import auth
import backup
import portfolio
import settings

ADMIN = "first@example.com"
USER = "second@example.com"


def _setup_user():
    auth.register(ADMIN, "password123-long")
    auth.register(USER, "password123-long")
    portfolio.set_user(USER)
    portfolio.save_portfolio(pd.DataFrame([{"ticker": "AAA.BR", "shares": 1}]))
    portfolio.save_watchlist({"BBB.BR"})
    s = settings.load_settings(USER)
    s["density"] = "compact"
    settings.save_settings(s, USER)
    backup.create_backup(USER)
    backup.create_backup(ADMIN)


def test_delete_account_removes_every_trace(isolated_data):
    _setup_user()
    udir = portfolio.user_data_dir(USER)
    assert (udir / "portfolio.json").exists() and settings._settings_file(USER).exists()

    ok, _ = account.delete_account(USER)

    assert ok
    assert USER not in auth._load_users()
    assert not udir.exists() or not any(udir.iterdir())
    assert not settings._settings_file(USER).exists()
    assert [b["email"] for b in backup.list_backups()] == [ADMIN]
    assert sorted(p.name for p in backup._BACKUPS_DIR.glob("*.zip")) == [backup.list_backups()[0]["filename"]]


def test_email_case_does_not_matter(isolated_data):
    _setup_user()
    ok, _ = account.delete_account("Second@Example.com ")
    assert ok and USER not in auth._load_users()


def test_last_admin_is_refused_and_nothing_is_removed(isolated_data):
    _setup_user()
    portfolio.set_user(ADMIN)
    portfolio.save_watchlist({"CCC.BR"})
    ok, msg = account.delete_account(ADMIN)
    assert not ok and "last active Admin" in msg
    assert ADMIN in auth._load_users()
    assert portfolio.load_watchlist() == {"CCC.BR"}
    assert len(backup.list_backups()) == 2


def test_unknown_account_is_refused(isolated_data):
    ok, msg = account.delete_account("nobody@example.com")
    assert not ok and msg == "User not found."
