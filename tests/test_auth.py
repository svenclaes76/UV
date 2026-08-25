"""
Unit tests for auth.py — bcrypt password hashing, JWT sessions, and the
encrypted user store.

Each test gets an isolated USERS_FILE (via monkeypatch, pointed at tmp_path)
and a fixed ENCRYPTION_KEY, so nothing here touches the real .cache/users.json
or depends on the developer's real secrets.
"""

import json

import jwt as pyjwt
import pytest

import auth


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", "unit-test-key-123")
    monkeypatch.setattr(auth, "USERS_FILE", tmp_path / ".cache" / "users.json")


# ── register ──────────────────────────────────────────────────────────────

class TestRegister:
    def test_first_user_is_promoted_to_admin_regardless_of_requested_role(self):
        ok, msg = auth.register("first@example.com", "password123", role="Viewer")
        assert ok
        users = auth._load_users()
        assert users["first@example.com"]["role"] == "Admin"

    def test_second_user_gets_requested_role(self):
        auth.register("first@example.com", "password123")
        ok, msg = auth.register("second@example.com", "password123", role="Viewer")
        assert ok
        users = auth._load_users()
        assert users["second@example.com"]["role"] == "Viewer"

    def test_email_is_normalized_to_lowercase_and_stripped(self):
        auth.register("  Mixed.Case@Example.com  ", "password123")
        users = auth._load_users()
        assert "mixed.case@example.com" in users

    def test_password_is_hashed_not_stored_in_plaintext(self):
        auth.register("first@example.com", "password123")
        users = auth._load_users()
        assert users["first@example.com"]["password_hash"] != "password123"

    @pytest.mark.parametrize("email", ["", "not-an-email", "   "])
    def test_rejects_invalid_email(self, email):
        ok, msg = auth.register(email, "password123")
        assert not ok
        assert "valid email" in msg

    def test_rejects_short_password(self):
        ok, msg = auth.register("first@example.com", "short")
        assert not ok
        assert "8 characters" in msg

    def test_rejects_unknown_role(self):
        ok, msg = auth.register("first@example.com", "password123", role="SuperUser")
        assert not ok
        assert "Unknown role" in msg

    def test_rejects_duplicate_email(self):
        auth.register("first@example.com", "password123")
        ok, msg = auth.register("first@example.com", "password123")
        assert not ok
        assert "already exists" in msg

    def test_corrupted_store_blocks_registration_instead_of_bootstrapping_admin(self):
        # A corrupted/undecryptable existing file also loads as {} via
        # _load_users() -- register() must not mistake that for "no users
        # yet" and silently grant the new signup Admin.
        auth.USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        auth.USERS_FILE.write_text("not valid encrypted content")
        ok, msg = auth.register("someone@example.com", "password123")
        assert not ok
        assert "could not be read" in msg


# ── login / verify_token ─────────────────────────────────────────────────

class TestLogin:
    def test_success_returns_verifiable_jwt(self):
        auth.register("first@example.com", "password123")
        ok, token = auth.login("first@example.com", "password123")
        assert ok
        email, role = auth.verify_token(token)
        assert email == "first@example.com"
        assert role == "Admin"

    def test_wrong_password_fails(self):
        auth.register("first@example.com", "password123")
        ok, msg = auth.login("first@example.com", "wrong-password")
        assert not ok
        assert "Invalid email or password" in msg

    def test_unknown_email_fails(self):
        ok, msg = auth.login("nobody@example.com", "password123")
        assert not ok
        assert "Invalid email or password" in msg

    def test_corrupted_store_gives_honest_error_not_invalid_password(self):
        auth.register("first@example.com", "password123")
        auth.USERS_FILE.write_text("not valid encrypted content")
        ok, msg = auth.login("first@example.com", "password123")
        assert not ok
        assert "could not be read" in msg

    def test_suspended_account_cannot_login(self):
        auth.register("first@example.com", "password123")
        auth.register("second@example.com", "password12345", role="Admin")
        auth.set_status("first@example.com", "Suspended")
        ok, msg = auth.login("first@example.com", "password123")
        assert not ok
        assert "suspended" in msg.lower()

    def test_invited_account_activates_on_first_login(self):
        auth.register("admin@example.com", "password123")
        ok, msg, temp_password = auth.invite_user("new@example.com", role="Viewer")
        assert ok
        auth.login("new@example.com", temp_password)
        users = auth._load_users()
        assert users["new@example.com"]["status"] == "Active"

    def test_login_updates_last_active(self):
        auth.register("first@example.com", "password123")
        before = auth._load_users()["first@example.com"]["last_active"]
        assert before == ""
        auth.login("first@example.com", "password123")
        after = auth._load_users()["first@example.com"]["last_active"]
        assert after != ""


class TestVerifyToken:
    def test_garbage_token_returns_none_none(self):
        email, role = auth.verify_token("not-a-real-jwt")
        assert (email, role) == (None, None)

    def test_tampered_token_returns_none_none(self):
        auth.register("first@example.com", "password123")
        _, token = auth.login("first@example.com", "password123")
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        email, role = auth.verify_token(tampered)
        assert (email, role) == (None, None)

    def test_expired_token_returns_none_none(self):
        # Craft a token identical in shape to login()'s but already expired.
        from datetime import datetime, timedelta, timezone
        expired = pyjwt.encode(
            {
                "sub": "first@example.com",
                "role": "Admin",
                "exp": datetime.now(timezone.utc) - timedelta(hours=1),
                "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            },
            auth._JWT_SECRET,
            algorithm=auth._JWT_ALGO,
        )
        email, role = auth.verify_token(expired)
        assert (email, role) == (None, None)


# ── invite_user ───────────────────────────────────────────────────────────

class TestInviteUser:
    def test_creates_invited_status_with_temp_password(self):
        ok, msg, temp_password = auth.invite_user("new@example.com", role="Analyst")
        assert ok
        assert temp_password is not None
        users = auth._load_users()
        assert users["new@example.com"]["status"] == "Invited"
        assert users["new@example.com"]["role"] == "Analyst"

    def test_temp_password_actually_works_for_login(self):
        ok, msg, temp_password = auth.invite_user("new@example.com")
        login_ok, _ = auth.login("new@example.com", temp_password)
        assert login_ok

    def test_duplicate_email_fails(self):
        auth.register("first@example.com", "password123")
        ok, msg, temp_password = auth.invite_user("first@example.com")
        assert not ok
        assert temp_password is None

    def test_rejects_unknown_role(self):
        ok, msg, temp_password = auth.invite_user("new@example.com", role="SuperUser")
        assert not ok
        assert temp_password is None

    def test_rejects_invalid_email(self):
        ok, msg, temp_password = auth.invite_user("not-an-email")
        assert not ok
        assert "valid email" in msg
        assert temp_password is None


# ── admin helpers ─────────────────────────────────────────────────────────

class TestListUsers:
    def test_excludes_password_hash(self):
        auth.register("first@example.com", "password123")
        rows = auth.list_users()
        assert "password_hash" not in rows[0]

    def test_sorted_by_created_at(self):
        auth.register("first@example.com", "password123")
        auth.register("second@example.com", "password123456")
        rows = auth.list_users()
        assert [r["email"] for r in rows] == ["first@example.com", "second@example.com"]


class TestSetRole:
    def test_changes_role(self):
        auth.register("first@example.com", "password123")
        auth.register("second@example.com", "password123456")
        ok, msg = auth.set_role("second@example.com", "Viewer")
        assert ok
        assert auth._load_users()["second@example.com"]["role"] == "Viewer"

    def test_rejects_unknown_role(self):
        auth.register("first@example.com", "password123")
        ok, msg = auth.set_role("first@example.com", "SuperUser")
        assert not ok

    def test_unknown_user_fails(self):
        ok, msg = auth.set_role("nobody@example.com", "Viewer")
        assert not ok
        assert "not found" in msg

    def test_blocks_demoting_the_last_admin(self):
        auth.register("first@example.com", "password123")
        auth.register("second@example.com", "password123456", role="Viewer")
        ok, msg = auth.set_role("first@example.com", "Viewer")
        assert not ok
        assert "last active Admin" in msg
        assert auth._load_users()["first@example.com"]["role"] == "Admin"

    def test_allows_demoting_an_admin_when_another_remains(self):
        auth.register("first@example.com", "password123")
        auth.register("second@example.com", "password123456", role="Admin")
        ok, _ = auth.set_role("first@example.com", "Viewer")
        assert ok
        assert auth._load_users()["first@example.com"]["role"] == "Viewer"

    def test_a_suspended_other_admin_does_not_prevent_the_block(self):
        # The guard only counts OTHER admins who are also Active -- a
        # suspended admin-role account can't log in to fix anything either,
        # so it doesn't count as a safe fallback.
        auth.register("first@example.com", "password123")
        auth.register("second@example.com", "password123456", role="Admin")
        auth.set_status("second@example.com", "Suspended")
        ok, msg = auth.set_role("first@example.com", "Viewer")
        assert not ok
        assert "last active Admin" in msg


class TestSetStatus:
    def test_suspend_and_reactivate(self):
        auth.register("first@example.com", "password123")
        auth.register("second@example.com", "password12345", role="Admin")
        ok, _ = auth.set_status("first@example.com", "Suspended")
        assert ok
        assert auth._load_users()["first@example.com"]["status"] == "Suspended"
        auth.set_status("first@example.com", "Active")
        assert auth._load_users()["first@example.com"]["status"] == "Active"

    def test_rejects_unknown_status(self):
        auth.register("first@example.com", "password123")
        ok, msg = auth.set_status("first@example.com", "OnVacation")
        assert not ok
        assert "Unknown status" in msg

    def test_unknown_user_fails(self):
        ok, msg = auth.set_status("nobody@example.com", "Suspended")
        assert not ok
        assert "not found" in msg

    def test_blocks_suspending_the_last_active_admin(self):
        auth.register("first@example.com", "password123")
        ok, msg = auth.set_status("first@example.com", "Suspended")
        assert not ok
        assert "last active Admin" in msg
        assert auth._load_users()["first@example.com"]["status"] == "Active"

    def test_allows_suspending_an_admin_when_another_active_one_remains(self):
        auth.register("first@example.com", "password123")
        auth.register("second@example.com", "password123456", role="Admin")
        ok, _ = auth.set_status("first@example.com", "Suspended")
        assert ok

    def test_does_not_block_reactivating_an_admin(self):
        # The guard only applies to Suspended -- reactivating back to Active
        # never reduces the active-admin count, so it should never be blocked.
        auth.register("first@example.com", "password123")
        auth.register("second@example.com", "password123456", role="Admin")
        auth.set_status("second@example.com", "Suspended")
        ok, _ = auth.set_status("second@example.com", "Active")
        assert ok


class TestResetPassword:
    def test_new_password_allows_login_old_does_not(self):
        auth.register("first@example.com", "password123")
        auth.reset_password("first@example.com", "newpassword456")
        assert not auth.login("first@example.com", "password123")[0]
        assert auth.login("first@example.com", "newpassword456")[0]

    def test_rejects_short_password(self):
        auth.register("first@example.com", "password123")
        ok, msg = auth.reset_password("first@example.com", "short")
        assert not ok

    def test_unknown_user_fails(self):
        ok, msg = auth.reset_password("nobody@example.com", "newpassword456")
        assert not ok


class TestDeleteUser:
    def test_removes_account(self):
        auth.register("first@example.com", "password123")
        auth.register("second@example.com", "password12345", role="Admin")
        ok, _ = auth.delete_user("first@example.com")
        assert ok
        assert "first@example.com" not in auth._load_users()

    def test_unknown_user_fails(self):
        ok, msg = auth.delete_user("nobody@example.com")
        assert not ok
        assert "not found" in msg

    def test_blocks_deleting_the_last_active_admin(self):
        auth.register("first@example.com", "password123")
        ok, msg = auth.delete_user("first@example.com")
        assert not ok
        assert "last active Admin" in msg
        assert "first@example.com" in auth._load_users()

    def test_allows_deleting_a_non_admin(self):
        auth.register("first@example.com", "password123")
        auth.register("second@example.com", "password123456", role="Viewer")
        ok, _ = auth.delete_user("second@example.com")
        assert ok


# ── internal helpers ──────────────────────────────────────────────────────

class TestNormalizeUser:
    @pytest.mark.parametrize(
        "legacy_role,expected",
        [("admin", "Admin"), ("user", "Analyst")],
    )
    def test_legacy_roles_are_migrated(self, legacy_role, expected):
        normalized = auth._normalize_user({"role": legacy_role})
        assert normalized["role"] == expected

    def test_unknown_role_defaults_to_analyst(self):
        normalized = auth._normalize_user({"role": "GrandWizard"})
        assert normalized["role"] == "Analyst"

    def test_fills_in_missing_status_and_last_active(self):
        normalized = auth._normalize_user({"role": "Admin"})
        assert normalized["status"] == "Active"
        assert normalized["last_active"] == ""


class TestLoadUsers:
    def test_missing_file_returns_empty_dict(self):
        assert auth._load_users() == {}

    def test_corrupt_file_returns_empty_dict(self):
        auth.USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        auth.USERS_FILE.write_bytes(b"not a valid encrypted payload")
        assert auth._load_users() == {}
