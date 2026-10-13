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
import settings


class _NoBreachResponse:
    """Fake requests.Response — a k-anonymity range lookup with no matching
    suffix, i.e. "not found in the breach corpus". Patched onto
    auth.requests.get (not check_password_breached itself) so the REAL
    validate_new_password()/check_password_breached() implementation runs in
    every test by default, without ever making a real HIBP network call —
    specific tests re-patch requests.get to exercise breached/unreachable
    scenarios instead."""
    status_code = 200
    text = ""
    def raise_for_status(self): pass


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", "unit-test-key-123")
    monkeypatch.setattr(auth, "USERS_FILE", tmp_path / ".cache" / "users.json")
    # login()'s rate-limit thresholds come from the shared (Admin-controlled)
    # settings file — isolate it too so these tests can't read/leak real
    # data/settings/shared.json and can freely override the thresholds.
    monkeypatch.setattr(settings, "_SHARED_FILE", tmp_path / "data" / "settings" / "shared.json")
    monkeypatch.setattr(auth.requests, "get", lambda *a, **k: _NoBreachResponse())


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


class TestNoUsersExist:
    def test_true_for_a_fresh_store(self):
        assert auth.no_users_exist()

    def test_false_once_any_account_exists(self):
        auth.register("someone@example.com", "password123")
        assert not auth.no_users_exist()


class TestBootstrapAdminFromEnv:
    def test_creates_and_promotes_admin_when_store_empty_and_both_vars_set(self, monkeypatch):
        monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
        monkeypatch.setenv("ADMIN_PASSWORD", "bootstrap-password123")
        result = auth.bootstrap_admin_from_env()
        assert result == (True, "Account created. You can now log in.")
        users = auth._load_users()
        assert users["boss@example.com"]["role"] == "Admin"

    def test_skipped_when_admin_email_set_without_password(self, monkeypatch):
        monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
        assert auth.bootstrap_admin_from_env() is None
        assert auth._load_users() == {}

    def test_skipped_when_neither_var_set(self, monkeypatch):
        monkeypatch.delenv("ADMIN_EMAIL", raising=False)
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
        assert auth.bootstrap_admin_from_env() is None
        assert auth._load_users() == {}

    def test_skipped_when_store_already_has_an_account(self, monkeypatch):
        auth.register("existing@example.com", "password123")
        monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
        monkeypatch.setenv("ADMIN_PASSWORD", "bootstrap-password123")
        assert auth.bootstrap_admin_from_env() is None
        assert "boss@example.com" not in auth._load_users()

    def test_second_call_is_a_no_op(self, monkeypatch):
        monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
        monkeypatch.setenv("ADMIN_PASSWORD", "bootstrap-password123")
        auth.bootstrap_admin_from_env()
        assert auth.bootstrap_admin_from_env() is None
        assert len(auth._load_users()) == 1


# ── login / verify_token ─────────────────────────────────────────────────

class TestLogin:
    def test_success_returns_verifiable_jwt(self):
        auth.register("first@example.com", "password123")
        ok, token = auth.login("first@example.com", "password123")
        assert ok
        email, role, sid = auth.verify_token(token)
        assert email == "first@example.com"
        assert role == "Admin"
        assert sid  # login() always mints one

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

    def test_invited_account_activates_on_accepting_the_invite(self):
        # Activation now happens at invite-acceptance (see TestAcceptInvite),
        # not at first login with a temp password -- a pending invite has no
        # password to log in with at all until then.
        auth.register("admin@example.com", "password123")
        ok, msg, token = auth.invite_user("new@example.com", role="Viewer")
        assert ok
        auth.accept_invite_with_password(token, "a-real-password")
        users = auth._load_users()
        assert users["new@example.com"]["status"] == "Active"


# ── login rate limiting / lockout ────────────────────────────────────────

class TestLoginRateLimiting:
    def test_wrong_password_gives_the_same_message_as_an_unknown_email(self):
        # SR3: no "attempts remain" count, which only known accounts had.
        auth.register("first@example.com", "password123")
        ok, msg = auth.login("first@example.com", "wrong-password")
        _, unknown_msg = auth.login("nobody@example.com", "wrong-password")
        assert not ok
        assert msg == unknown_msg == "Invalid email or password."

    def test_unknown_email_never_reports_attempts_or_locks(self):
        # No account to attach a counter to, and revealing a count would let
        # an attacker distinguish real emails from made-up ones.
        for _ in range(10):
            ok, msg = auth.login("nobody@example.com", "whatever")
            assert not ok
            assert msg == "Invalid email or password."
        assert auth.get_lockout("nobody@example.com") is None

    def test_account_locks_after_configured_attempts(self):
        settings.save_shared_settings({**settings.load_shared_settings(),
                                       "login_attempts_before_lock": 2, "lock_minutes": 10})
        auth.register("first@example.com", "password123")
        ok1, msg1 = auth.login("first@example.com", "wrong-password")
        assert not ok1 and msg1 == "Invalid email or password."
        ok2, msg2 = auth.login("first@example.com", "wrong-password")
        assert not ok2 and msg2 == "Invalid email or password."  # the lock is silent
        assert auth.get_lockout("first@example.com") is not None

    def test_locked_account_rejects_even_the_correct_password(self):
        settings.save_shared_settings({**settings.load_shared_settings(),
                                       "login_attempts_before_lock": 1, "lock_minutes": 10})
        auth.register("first@example.com", "password123")
        auth.login("first@example.com", "wrong-password")  # trips the lock
        ok, msg = auth.login("first@example.com", "password123")
        assert not ok
        assert msg == "Invalid email or password."  # same as any failure (SR3)

    def test_every_failure_path_costs_one_bcrypt_check(self, monkeypatch):
        # SR3: unknown, password-less and locked accounts take as long as a
        # wrong password, so response time can't reveal which emails exist.
        settings.save_shared_settings({**settings.load_shared_settings(),
                                       "login_attempts_before_lock": 1})
        auth.register("first@example.com", "password123")
        auth.invite_user("invited@example.com")  # no password yet
        auth.register("locked@example.com", "password123")
        auth.login("locked@example.com", "wrong-password")  # trips the lock
        calls = []
        real = auth.bcrypt.checkpw
        monkeypatch.setattr(auth.bcrypt, "checkpw", lambda *a: calls.append(1) or real(*a))
        for email in ("nobody@example.com", "invited@example.com",
                      "locked@example.com", "first@example.com"):
            calls.clear()
            ok, msg = auth.login(email, "wrong-password")
            assert not ok and msg == "Invalid email or password."
            assert len(calls) == 1, email

    def test_successful_login_clears_failed_attempts(self):
        auth.register("first@example.com", "password123")
        auth.login("first@example.com", "wrong-password")
        ok, _ = auth.login("first@example.com", "password123")
        assert ok
        users = auth._load_users()
        assert users["first@example.com"]["failed_attempts"] == 0
        assert users["first@example.com"]["locked_until"] is None

    def test_lock_expires_on_its_own(self):
        from datetime import datetime, timedelta, timezone
        settings.save_shared_settings({**settings.load_shared_settings(),
                                       "login_attempts_before_lock": 1})
        auth.register("first@example.com", "password123")
        auth.login("first@example.com", "wrong-password")  # trips the lock
        assert auth.get_lockout("first@example.com") is not None
        # Backdate the lock as if the window had already elapsed.
        users = auth._load_users()
        users["first@example.com"]["locked_until"] = (
            datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        auth._save_users(users)
        assert auth.get_lockout("first@example.com") is None
        ok, _ = auth.login("first@example.com", "password123")
        assert ok

    def test_login_updates_last_active(self):
        auth.register("first@example.com", "password123")
        before = auth._load_users()["first@example.com"]["last_active"]
        assert before == ""
        auth.login("first@example.com", "password123")
        after = auth._load_users()["first@example.com"]["last_active"]
        assert after != ""



def _enroll_totp(email: str) -> str:
    import pyotp
    secret, _ = auth.begin_totp_enrollment(email)
    auth.confirm_totp_enrollment(email, pyotp.TOTP(secret).now())
    return secret


def _set_attempts(n: int, minutes: int = 10) -> None:
    settings.save_shared_settings({**settings.load_shared_settings(),
                                   "login_attempts_before_lock": n, "lock_minutes": minutes})


class TestSecondFactorLimits:
    """SR1 (docs/security-review.md #1): wrong authenticator or backup codes
    count towards the lockout, a correct password doesn't reset that count,
    and an accepted code can't be replayed."""

    def _password_step(self):
        ok, result = auth.login("first@example.com", "password123")
        assert ok and result == auth.TOTP_REQUIRED

    def test_wrong_codes_lock_the_account(self):
        _set_attempts(3)
        auth.register("first@example.com", "password123")
        _enroll_totp("first@example.com")
        self._password_step()
        for _ in range(2):
            ok, msg = auth.complete_totp_login("first@example.com", "000000")
            assert not ok and "Try again" in msg
        ok, msg = auth.complete_totp_login("first@example.com", "000000")
        assert not ok and "now locked for 10 minutes" in msg
        assert auth.get_lockout("first@example.com") is not None

    def test_locked_account_refuses_even_the_correct_code_and_password(self):
        import pyotp
        _set_attempts(1)
        auth.register("first@example.com", "password123")
        secret = _enroll_totp("first@example.com")
        self._password_step()
        auth.complete_totp_login("first@example.com", "000000")  # trips the lock
        ok, msg = auth.complete_totp_login("first@example.com", pyotp.TOTP(secret).now())
        assert not ok and "temporarily locked" in msg
        ok, msg = auth.login("first@example.com", "password123")
        assert not ok and msg == "Invalid email or password."

    def test_correct_password_does_not_reset_the_code_counter(self):
        _set_attempts(3)
        auth.register("first@example.com", "password123")
        _enroll_totp("first@example.com")
        self._password_step()
        auth.complete_totp_login("first@example.com", "000000")
        auth.complete_totp_login("first@example.com", "000000")
        self._password_step()  # re-entering the password must not buy new guesses
        ok, msg = auth.complete_totp_login("first@example.com", "000000")
        assert not ok and "now locked" in msg

    def test_correct_code_resets_the_counter(self):
        import pyotp
        _set_attempts(3)
        auth.register("first@example.com", "password123")
        secret = _enroll_totp("first@example.com")
        self._password_step()
        auth.complete_totp_login("first@example.com", "000000")
        auth.complete_totp_login("first@example.com", "000000")
        ok, _ = auth.complete_totp_login("first@example.com", pyotp.TOTP(secret).now())
        assert ok
        assert auth._load_users()["first@example.com"]["totp_failed_attempts"] == 0

    def test_accepted_code_cannot_be_reused(self):
        import pyotp
        auth.register("first@example.com", "password123")
        secret = _enroll_totp("first@example.com")
        code = pyotp.TOTP(secret).now()
        self._password_step()
        ok, _ = auth.complete_totp_login("first@example.com", code)
        assert ok
        self._password_step()
        ok, msg = auth.complete_totp_login("first@example.com", code)
        assert not ok and "didn't match" in msg

    def test_wrong_backup_codes_count_towards_the_same_lock(self):
        _set_attempts(2)
        auth.register("first@example.com", "password123")
        _enroll_totp("first@example.com")
        auth.regenerate_backup_codes("first@example.com")
        self._password_step()
        auth.complete_totp_login("first@example.com", "000000")
        ok, msg = auth.complete_backup_code_login("first@example.com", "nope-nope")
        assert not ok and "now locked" in msg
        assert auth.get_lockout("first@example.com") is not None

    def test_locked_account_refuses_a_valid_backup_code(self):
        _set_attempts(1)
        auth.register("first@example.com", "password123")
        _enroll_totp("first@example.com")
        code = auth.regenerate_backup_codes("first@example.com")[0]
        self._password_step()
        auth.complete_backup_code_login("first@example.com", "nope-nope")  # trips the lock
        ok, msg = auth.complete_backup_code_login("first@example.com", code)
        assert not ok and "temporarily locked" in msg
        assert auth.backup_codes_remaining("first@example.com") == 10  # not consumed



class TestPerIpLimit:
    """SR2: one address can't spray passwords across many accounts. Silent
    like the account lock: same message, and every account stays usable
    from other addresses."""

    @pytest.fixture(autouse=True)
    def _clear(self, monkeypatch):
        monkeypatch.setattr(auth, "_ip_failures", {})
        monkeypatch.setattr(auth, "IP_MAX_FAILURES", 3)

    def test_blocks_an_address_after_failures_across_different_emails(self):
        auth.register("first@example.com", "password123")
        for email in ("a@example.com", "b@example.com", "first@example.com"):
            auth.login(email, "wrong-password", client_ip="203.0.113.7")
        assert auth.ip_blocked("203.0.113.7")
        ok, msg = auth.login("first@example.com", "password123", client_ip="203.0.113.7")
        assert not ok and msg == "Invalid email or password."

    def test_other_addresses_and_the_account_are_unaffected(self):
        auth.register("first@example.com", "password123")
        for _ in range(3):
            auth.login("nobody@example.com", "wrong-password", client_ip="203.0.113.7")
        ok, _ = auth.login("first@example.com", "password123", client_ip="198.51.100.4")
        assert ok
        assert auth._load_users()["first@example.com"]["failed_attempts"] == 0

    def test_failures_expire_after_the_window(self):
        from datetime import datetime, timedelta, timezone
        old = datetime.now(timezone.utc) - timedelta(minutes=auth.IP_WINDOW_MINUTES + 1)
        auth._ip_failures["203.0.113.7"] = [old, old, old]
        assert not auth.ip_blocked("203.0.113.7")

    def test_no_address_means_no_limit(self):
        for _ in range(5):
            auth.login("nobody@example.com", "wrong-password")
        assert auth._ip_failures == {}


class TestVerifyToken:
    def test_garbage_token_returns_none_none_none(self):
        email, role, sid = auth.verify_token("not-a-real-jwt")
        assert (email, role, sid) == (None, None, None)

    def test_tampered_token_returns_none_none_none(self):
        auth.register("first@example.com", "password123")
        _, token = auth.login("first@example.com", "password123")
        # Flip a character in the PAYLOAD segment, not the signature's last
        # base64 char: a 32-byte HMAC's final base64url char carries only 4
        # significant bits, so for the ~6% of tokens ending in "A" the old
        # "A"->"B" swap decoded to identical signature bytes and the token
        # still verified (flaky). Any change to the signed header.payload text
        # breaks the HMAC unconditionally.
        header, payload, sig = token.split(".")
        payload = ("A" if payload[0] != "A" else "B") + payload[1:]
        email, role, sid = auth.verify_token(f"{header}.{payload}.{sig}")
        assert (email, role, sid) == (None, None, None)

    def test_expired_token_returns_none_none_none(self):
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
        email, role, sid = auth.verify_token(expired)
        assert (email, role, sid) == (None, None, None)


# ── invite_user ───────────────────────────────────────────────────────────

class TestInviteUser:
    def test_creates_invited_status_with_no_usable_password_yet(self):
        ok, msg, token = auth.invite_user("new@example.com", role="Analyst")
        assert ok
        assert token is not None
        users = auth._load_users()
        assert users["new@example.com"]["status"] == "Invited"
        assert users["new@example.com"]["role"] == "Analyst"
        assert users["new@example.com"]["password_hash"] is None

    def test_pending_account_cannot_log_in_before_acceptance(self):
        # Nothing to log in with yet -- the point of the invite-token flow is
        # that the account isn't usable until accept_invite_with_password()/
        # accept_invite_with_oauth() finalizes it.
        auth.invite_user("new@example.com")
        login_ok, _ = auth.login("new@example.com", "anything-at-all")
        assert not login_ok

    def test_duplicate_email_fails(self):
        auth.register("first@example.com", "password123")
        ok, msg, token = auth.invite_user("first@example.com")
        assert not ok
        assert token is None

    def test_rejects_unknown_role(self):
        ok, msg, token = auth.invite_user("new@example.com", role="SuperUser")
        assert not ok
        assert token is None

    def test_rejects_invalid_email(self):
        ok, msg, token = auth.invite_user("not-an-email")
        assert not ok
        assert "valid email" in msg
        assert token is None

    def test_records_who_invited(self):
        auth.invite_user("new@example.com", invited_by="admin@example.com")
        invite = auth.get_pending_invite(
            auth._load_users()["new@example.com"]["invite_token"])
        assert invite["invited_by"] == "admin@example.com"


class TestAcceptInvite:
    def test_get_pending_invite_returns_email_and_role(self):
        _, _, token = auth.invite_user("new@example.com", role="Viewer", invited_by="admin@example.com")
        invite = auth.get_pending_invite(token)
        assert invite == {"email": "new@example.com", "role": "Viewer", "invited_by": "admin@example.com"}

    def test_unknown_token_returns_none(self):
        assert auth.get_pending_invite("not-a-real-token") is None

    def test_expired_token_returns_none(self):
        from datetime import datetime, timedelta, timezone
        _, _, token = auth.invite_user("new@example.com")
        users = auth._load_users()
        users["new@example.com"]["invite_token_expires"] = (
            datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        auth._save_users(users)
        assert auth.get_pending_invite(token) is None

    def test_accept_with_password_activates_and_logs_in(self):
        _, _, token = auth.invite_user("new@example.com", role="Viewer")
        ok, result = auth.accept_invite_with_password(token, "a-real-password")
        assert ok
        email, role, sid = auth.verify_token(result)
        assert email == "new@example.com"
        assert role == "Viewer"
        assert sid
        users = auth._load_users()
        assert users["new@example.com"]["status"] == "Active"
        assert users["new@example.com"]["invite_token"] is None

    def test_accept_with_password_can_then_log_in_normally(self):
        _, _, token = auth.invite_user("new@example.com")
        auth.accept_invite_with_password(token, "a-real-password")
        ok, _ = auth.login("new@example.com", "a-real-password")
        assert ok

    def test_accept_with_short_password_fails(self):
        _, _, token = auth.invite_user("new@example.com")
        ok, msg = auth.accept_invite_with_password(token, "short")
        assert not ok
        assert "characters" in msg

    def test_accept_with_invalid_token_fails(self):
        ok, msg = auth.accept_invite_with_password("garbage-token", "a-real-password")
        assert not ok
        assert "invalid or has expired" in msg

    def test_accept_with_oauth_links_identity_and_logs_in(self):
        _, _, token = auth.invite_user("new@example.com", role="Analyst")
        ok, result = auth.accept_invite_with_oauth(token, "https://accounts.google.com", "sub-123",
                                                   "new@example.com")
        assert ok
        email, role, _ = auth.verify_token(result)
        assert email == "new@example.com"
        assert role == "Analyst"
        users = auth._load_users()
        assert users["new@example.com"]["linked_identities"] == [
            {"issuer": "https://accounts.google.com", "subject": "sub-123",
             "email_at_link": "new@example.com",
             "linked_at": users["new@example.com"]["linked_identities"][0]["linked_at"]}
        ]

    def test_accept_with_oauth_refuses_mismatched_email(self):
        _, _, token = auth.invite_user("invited@example.com")
        ok, msg = auth.accept_invite_with_oauth(token, "https://accounts.google.com", "sub-123",
                                                "someone-else@example.com")
        assert not ok
        assert "invited@example.com" in msg


class TestAdminPasswordReset:
    def test_request_reset_for_unknown_user_fails(self):
        ok, msg, token = auth.admin_request_password_reset("nobody@example.com")
        assert not ok
        assert token is None

    def test_request_reset_for_invited_user_fails(self):
        auth.invite_user("pending@example.com")
        ok, msg, token = auth.admin_request_password_reset("pending@example.com")
        assert not ok
        assert "invite" in msg.lower()
        assert token is None

    def test_request_reset_returns_token_for_active_user(self):
        auth.register("first@example.com", "password123")
        ok, msg, token = auth.admin_request_password_reset("first@example.com", requested_by="admin@example.com")
        assert ok
        assert token
        assert auth.get_pending_reset(token) == {"email": "first@example.com"}

    def test_unknown_reset_token_returns_none(self):
        assert auth.get_pending_reset("not-a-real-token") is None

    def test_expired_reset_token_returns_none(self):
        from datetime import datetime, timedelta, timezone
        auth.register("first@example.com", "password123")
        _, _, token = auth.admin_request_password_reset("first@example.com")
        users = auth._load_users()
        users["first@example.com"]["reset_token_expires"] = (
            datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        auth._save_users(users)
        assert auth.get_pending_reset(token) is None

    def test_reset_link_is_valid_for_30_minutes(self):
        from datetime import datetime, timedelta, timezone
        auth.register("first@example.com", "password123")
        before = datetime.now(timezone.utc)
        auth.admin_request_password_reset("first@example.com")
        expires = datetime.fromisoformat(auth._load_users()["first@example.com"]["reset_token_expires"])
        assert timedelta(minutes=29) < expires - before <= timedelta(minutes=30, seconds=5)

    def test_complete_reset_sets_new_password_and_logs_in(self):
        auth.register("first@example.com", "password123")
        _, _, token = auth.admin_request_password_reset("first@example.com")
        ok, result = auth.complete_password_reset(token, "brand-new-password")
        assert ok
        email, role, sid = auth.verify_token(result)
        assert email == "first@example.com"
        assert sid
        users = auth._load_users()
        assert users["first@example.com"]["reset_token"] is None
        ok2, _ = auth.login("first@example.com", "brand-new-password")
        assert ok2

    def test_complete_reset_with_short_password_fails(self):
        auth.register("first@example.com", "password123")
        _, _, token = auth.admin_request_password_reset("first@example.com")
        ok, msg = auth.complete_password_reset(token, "short")
        assert not ok
        assert "characters" in msg

    def test_complete_reset_with_invalid_token_fails(self):
        ok, msg = auth.complete_password_reset("garbage-token", "brand-new-password")
        assert not ok
        assert "invalid or has expired" in msg

    def test_complete_reset_clears_existing_lockout(self):
        auth.register("first@example.com", "password123")
        users = auth._load_users()
        from datetime import datetime, timedelta, timezone
        users["first@example.com"]["locked_until"] = (
            datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
        users["first@example.com"]["failed_attempts"] = 5
        auth._save_users(users)
        _, _, token = auth.admin_request_password_reset("first@example.com")
        auth.complete_password_reset(token, "brand-new-password")
        users = auth._load_users()
        assert users["first@example.com"]["locked_until"] is None
        assert users["first@example.com"]["failed_attempts"] == 0

    def test_reset_token_is_single_use(self):
        auth.register("first@example.com", "password123")
        _, _, token = auth.admin_request_password_reset("first@example.com")
        auth.complete_password_reset(token, "brand-new-password")
        ok, msg = auth.complete_password_reset(token, "another-password")
        assert not ok
        assert "invalid or has expired" in msg


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


# ── logging (logkit Phase 1) ─────────────────────────────────────────────

import logging as _logging  # noqa: E402

from uvalu import logkit  # noqa: E402


def _events(caplog, slug):
    return [r for r in caplog.records if getattr(r, "event", None) == slug]


class TestAuthLogging:
    def test_successful_login_logs_auth_login_ok(self, caplog):
        caplog.set_level(_logging.DEBUG, logger="uvalu")
        auth.register("first@example.com", "password123")
        auth.login("first@example.com", "password123")
        (rec,) = _events(caplog, "auth.login.ok")
        assert rec.outcome == "ok"
        assert rec.user_id == logkit.user_hash("first@example.com")
        assert rec.role == "Admin"
        assert rec.was_invited is False
        assert "password123" not in caplog.text

    @pytest.mark.parametrize("scenario,reason", [
        ("unknown", "unknown_user"),
        ("badpw", "bad_password"),
        ("suspended", "suspended"),
    ])
    def test_failed_login_logs_reason_without_password(self, caplog, scenario, reason):
        caplog.set_level(_logging.DEBUG, logger="uvalu")
        auth.register("first@example.com", "password123")
        auth.register("second@example.com", "password12345", role="Admin")
        if scenario == "unknown":
            auth.login("nobody@example.com", "hunter2secret")
        elif scenario == "badpw":
            auth.login("first@example.com", "hunter2secret")
        else:
            auth.set_status("first@example.com", "Suspended")
            auth.login("first@example.com", "password123")
        (rec,) = _events(caplog, "auth.login.failed")
        assert rec.reason == reason
        assert rec.levelname == "WARNING"
        assert "hunter2secret" not in caplog.text

    def test_unreadable_store_logs_critical(self, caplog):
        auth.register("first@example.com", "password123")
        auth.USERS_FILE.write_text("not valid encrypted content")
        auth.login("first@example.com", "password123")
        (rec,) = _events(caplog, "auth.store.unreadable")
        assert rec.levelname == "CRITICAL"
        assert rec.op == "login"

    def test_register_logs_user_create_mutation(self, caplog):
        caplog.set_level(_logging.DEBUG, logger="uvalu")
        auth.register("first@example.com", "password123")
        (rec,) = _events(caplog, "mutation")
        assert rec.action == "user.create"
        assert rec.entity_id == logkit.user_hash("first@example.com")
        assert rec.bootstrap_admin is True

    def test_invite_logs_user_invite_mutation_without_temp_password(self, caplog):
        caplog.set_level(_logging.DEBUG, logger="uvalu")
        auth.register("admin@example.com", "password123")
        _, _, temp_pw = auth.invite_user("new@example.com", role="Viewer")
        invites = [r for r in _events(caplog, "mutation") if r.action == "user.invite"]
        assert len(invites) == 1
        assert invites[0].entity_id == logkit.user_hash("new@example.com")
        assert temp_pw not in caplog.text

    @pytest.mark.parametrize("call,action", [
        (lambda: auth.set_role("first@example.com", "Viewer"), "admin.demote_last_admin"),
        (lambda: auth.set_status("first@example.com", "Suspended"), "admin.suspend_last_admin"),
        (lambda: auth.delete_user("first@example.com"), "admin.delete_last_admin"),
    ])
    def test_last_admin_blocks_log_authz_denied(self, caplog, call, action):
        auth.register("first@example.com", "password123")   # sole Admin
        call()
        (rec,) = _events(caplog, "authz.denied")
        assert rec.action == action
        assert rec.resource == logkit.user_hash("first@example.com")
        assert rec.levelname == "WARNING"

    def test_set_role_success_logs_mutation_with_before_after(self, caplog):
        caplog.set_level(_logging.DEBUG, logger="uvalu")
        auth.register("first@example.com", "password123")
        auth.register("second@example.com", "password12345", role="Analyst")
        caplog.clear()
        auth.set_role("second@example.com", "Viewer")
        muts = [r for r in _events(caplog, "mutation") if r.action == "user.set_role"]
        assert len(muts) == 1
        assert muts[0].before == "Analyst" and muts[0].after == "Viewer"
        assert muts[0].entity_id == logkit.user_hash("second@example.com")

    def test_reset_password_logs_mutation_without_the_password(self, caplog):
        caplog.set_level(_logging.DEBUG, logger="uvalu")
        auth.register("first@example.com", "password123")
        caplog.clear()
        auth.reset_password("first@example.com", "brandnewsecret9")
        muts = [r for r in _events(caplog, "mutation") if r.action == "user.reset_password"]
        assert len(muts) == 1
        assert "brandnewsecret9" not in caplog.text

    def test_delete_user_success_logs_mutation(self, caplog):
        caplog.set_level(_logging.DEBUG, logger="uvalu")
        auth.register("first@example.com", "password123")
        auth.register("second@example.com", "password12345", role="Viewer")
        caplog.clear()
        auth.delete_user("second@example.com")
        muts = [r for r in _events(caplog, "mutation") if r.action == "user.delete"]
        assert len(muts) == 1 and muts[0].before == "Viewer"



def test_unknown_provider_identity_never_creates_an_account(isolated_store):
    """AD-01: invitation only — even with an allowed domain and the old
    auto-provision switch left on in stored settings."""
    import settings
    shared = settings.load_shared_settings()
    shared.update({"auto_provision_oauth": True, "allowed_email_domains": ["company.com"]})
    settings.save_shared_settings(shared)
    ok, result = auth.oauth_login("https://accounts.google.com", "sub-1", "new@company.com")
    assert (ok, result) == (False, "not_invited")
    assert "new@company.com" not in auth._load_users()
