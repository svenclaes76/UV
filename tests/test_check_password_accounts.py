"""T1: the read-only check for accounts locked out by password-only sign-in."""
from tools.check_password_accounts import passwordless_accounts


def test_lists_only_active_accounts_without_a_password():
    users = {
        "pw@x.be": {"status": "Active", "password_hash": "$2b$..."},
        "google@x.be": {"status": "Active", "password_hash": None,
                        "linked_identities": [{"provider": "google", "subject": "1"}]},
        "invited@x.be": {"status": "Invited", "password_hash": None},
        "suspended@x.be": {"status": "Suspended"},
    }
    assert passwordless_accounts(users) == [
        ("google@x.be", "Active", ["google"]),
        ("suspended@x.be", "Suspended", []),
    ]


def test_nothing_to_report_when_everyone_has_a_password():
    assert passwordless_accounts({"a@x.be": {"status": "Active", "password_hash": "h"}}) == []
