"""T1: accounts locked out by password-only sign-in during the beta."""
import auth
import run_app
from uvalu import oauth


def test_lists_only_active_accounts_without_a_password():
    users = {
        "pw@x.be": {"status": "Active", "password_hash": "$2b$..."},
        "google@x.be": {"status": "Active", "password_hash": None,
                        "linked_identities": [{"issuer": "https://accounts.google.com", "subject": "1"}]},
        "invited@x.be": {"status": "Invited", "password_hash": None},
        "suspended@x.be": {"status": "Suspended"},
    }
    assert auth.passwordless_accounts(users) == [
        ("google@x.be", "Active", ["https://accounts.google.com"]),
        ("suspended@x.be", "Suspended", []),
    ]


def test_nothing_to_report_when_everyone_has_a_password():
    assert auth.passwordless_accounts({"a@x.be": {"status": "Active", "password_hash": "h"}}) == []


def test_startup_warns_about_locked_out_accounts(monkeypatch, capsys):
    monkeypatch.setattr(oauth, "providers_enabled", lambda: False)
    monkeypatch.setattr(auth, "passwordless_accounts", lambda: [("google@x.be", "Active", [])])
    run_app._check_passwordless_accounts()
    out = capsys.readouterr().out
    assert "WARNING: 1 account(s) have no password" in out and "google@x.be" in out


def test_startup_is_quiet_when_providers_are_offered(monkeypatch, capsys):
    monkeypatch.setattr(oauth, "providers_enabled", lambda: True)
    monkeypatch.setattr(auth, "passwordless_accounts", lambda: [("google@x.be", "Active", [])])
    run_app._check_passwordless_accounts()
    assert capsys.readouterr().out == ""
