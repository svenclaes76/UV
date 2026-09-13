"""
Email/password authentication with bcrypt hashing and JWT sessions.

Roles:
  Admin   — full access + user/workspace administration (Admin portal)
  Analyst — full read/write access to screener and portfolio
  Viewer  — read-only; mutating actions (Buy/Sell/Edit/Delete/Add dividend)
            are hidden or disabled across the app

Users are stored in .cache/users.json. The first account created is
automatically assigned the Admin role — on a fresh deployment (no accounts
yet, and the sign-in wall is invite-only) that first account normally comes
from bootstrap_admin_from_env() (ADMIN_EMAIL/ADMIN_PASSWORD) or the
scripts/create_admin.py break-glass CLI, rather than self-service signup.
The JWT secret is read from the AUTH_SECRET environment variable; a random
fallback is generated at startup (sessions survive until the process
restarts).
"""

import hashlib
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
import jwt
import pyotp
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from crypto import read_encrypted, write_encrypted  # noqa: E402
from settings import load_shared_settings  # noqa: E402
from uvalu import logkit  # noqa: E402

USERS_FILE  = Path(__file__).parent / ".cache" / "users.json"
_JWT_SECRET = os.environ.get("AUTH_SECRET") or secrets.token_hex(32)
_JWT_ALGO   = "HS256"
_JWT_TTL_H  = 24

# Sentinel login() returns instead of a JWT when the password checked out but
# a TOTP code is still needed — distinct from (False, error_message) since
# this isn't a failure, and distinct from (True, jwt) since no session has
# been minted yet. uvalu/authgate.py checks for this exact string before
# treating a truthy `login()` result as a completed sign-in.
TOTP_REQUIRED = "TOTP_REQUIRED"

# Session lifetime options surfaced on the Admin -> Security page
# (settings.py's "session_ttl" shared setting) -> hours, for _issue_session().
_SESSION_TTL_HOURS = {"8 h": 8, "24 h": 24, "7 d": 24 * 7}

ROLES = ("Admin", "Analyst", "Viewer")
STATUSES = ("Active", "Invited", "Suspended")

# Legacy accounts predate the 3-tier role model — normalized transparently
# on load so existing sessions/files don't need an explicit migration step.
_LEGACY_ROLE_MAP = {"admin": "Admin", "user": "Analyst"}


# ── User store ────────────────────────────────────────────────────────────────

def _normalize_user(data: dict) -> dict:
    role = _LEGACY_ROLE_MAP.get(data.get("role", ""), data.get("role", "Analyst"))
    if role not in ROLES:
        role = "Analyst"
    return {
        **data,
        "role":            role,
        "status":          data.get("status", "Active"),
        "last_active":     data.get("last_active", ""),
        "failed_attempts": data.get("failed_attempts", 0),
        "locked_until":    data.get("locked_until"),
        "sessions":        data.get("sessions", []),
        "password_changed_at": data.get("password_changed_at", data.get("created_at", "")),
        "linked_identities":   data.get("linked_identities", []),
        "invite_token":         data.get("invite_token"),
        "invite_token_expires": data.get("invite_token_expires"),
        "invited_by":           data.get("invited_by", ""),
        "reset_token":          data.get("reset_token"),
        "reset_token_expires":  data.get("reset_token_expires"),
        "totp_secret":      data.get("totp_secret"),
        "totp_enabled":     data.get("totp_enabled", False),
        "backup_codes":     data.get("backup_codes", []),
        "trusted_devices":  data.get("trusted_devices", []),
    }


def _load_users() -> dict:
    if USERS_FILE.exists():
        try:
            raw = json.loads(read_encrypted(USERS_FILE))
            return {email: _normalize_user(data) for email, data in raw.items()}
        except Exception:
            pass
    return {}


def _save_users(users: dict) -> None:
    write_encrypted(USERS_FILE, json.dumps(users, indent=2))


def _store_broken(users: dict) -> bool:
    """True if the user store file exists on disk but _load_users() came
    back empty — distinguishing a genuinely fresh install (no file yet) from
    a corrupted file or wrong ENCRYPTION_KEY, which _load_users() silently
    also returns {} for. Conflating the two let register()'s bootstrap
    promote every new signup to Admin while a broken store locked out every
    real user, and let login() blame "Invalid email or password" for what
    was actually a system failure."""
    return USERS_FILE.exists() and not users


# ── Public API ────────────────────────────────────────────────────────────────

def register(email: str, password: str, role: str = "Analyst") -> tuple[bool, str]:
    """
    Create a new account. Returns (success, message).
    The first account ever created is promoted to Admin regardless of
    the role argument. Fails if email already registered or inputs are invalid.
    """
    email = email.strip().lower()
    if not email or "@" not in email:
        return False, "Enter a valid email address."
    if len(password) < 8:
        return False, "Password must be at least 8 characters."
    if role not in ROLES:
        return False, f"Unknown role '{role}'."

    users = _load_users()
    if _store_broken(users):
        logkit.get_logger("uvalu.auth").critical(
            "user store unreadable", extra={"event": "auth.store.unreadable", "op": "register"})
        return False, ("The user store could not be read (wrong encryption key or a "
                       "corrupted file). Registration is disabled until this is fixed.")
    if email in users:
        return False, "An account with this email already exists."

    # Bootstrap: first user becomes Admin
    bootstrap_admin = not users
    effective_role = "Admin" if bootstrap_admin else role

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    _now = datetime.now(timezone.utc).isoformat()
    users[email] = {
        "password_hash": hashed,
        "role":          effective_role,
        "status":        "Active",
        "created_at":    _now,
        "last_active":   "",
        "password_changed_at": _now,
    }
    _save_users(users)
    logkit.data_mutation(actor=logkit.user_id(), action="user.create", entity_type="user",
                         entity_id=logkit.user_hash(email), role=effective_role,
                         bootstrap_admin=bootstrap_admin)
    return True, "Account created. You can now log in."


def bootstrap_admin_from_env() -> tuple[bool, str] | None:
    """If the user store is empty and both ADMIN_EMAIL/ADMIN_PASSWORD are set
    in the environment, create that account — register()'s own "first
    account becomes Admin" logic promotes it. Returns None if skipped (store
    non-empty, or the env vars aren't both set — ADMIN_EMAIL alone logs a
    warning and skips, rather than generating a password with no channel to
    surface it on a fresh headless deployment). Called once at app boot
    (app.py), before auth_wall() — the only way left to create an account on
    a fresh instance now that the sign-in wall is invite-only (see
    uvalu/authgate.py). scripts/create_admin.py is the break-glass CLI
    equivalent for an instance that already has accounts but no working
    Admin."""
    if _load_users():
        return None
    email = os.environ.get("ADMIN_EMAIL", "").strip()
    if not email:
        return None
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not password:
        logkit.get_logger("uvalu.auth").warning(
            "ADMIN_EMAIL is set but ADMIN_PASSWORD is not -- skipping admin bootstrap",
            extra={"event": "auth.bootstrap.skipped_no_password"})
        return None
    return register(email, password)


_INVITE_TTL_DAYS = 7


def invite_user(email: str, role: str = "Analyst", invited_by: str = "") -> tuple[bool, str, str | None]:
    """
    Create a pending Invited account and a one-time invite token. No outbound
    email exists — returns (success, message, invite_token) so the caller can
    build a link (e.g. "?invite=<token>") and hand it to the invitee
    themselves. The account has no password and no linked identity until
    accept_invite_with_password() / accept_invite_with_oauth() finalizes it —
    unlike the account this replaces (a temp password usable immediately),
    the pending account can't sign in on its own until then.
    """
    email = email.strip().lower()
    if not email or "@" not in email:
        return False, "Enter a valid email address.", None
    if role not in ROLES:
        return False, f"Unknown role '{role}'.", None
    users = _load_users()
    if email in users:
        return False, "An account with this email already exists.", None

    token = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    users[email] = {
        "password_hash": None,
        "role":          role,
        "status":        "Invited",
        "created_at":    now.isoformat(),
        "last_active":   "",
        "password_changed_at": "",
        "linked_identities": [],
        "invite_token":        token,
        "invite_token_expires": (now + timedelta(days=_INVITE_TTL_DAYS)).isoformat(),
        "invited_by":          invited_by,
    }
    _save_users(users)
    logkit.data_mutation(actor=logkit.user_id(), action="user.invite", entity_type="user",
                         entity_id=logkit.user_hash(email), role=role, status="Invited")
    return True, f"{email} invited.", token


def get_pending_invite(token: str) -> dict | None:
    """{email, role, invited_by} for a not-yet-expired invite token, for the
    invite-acceptance screen — or None if the token is unknown or expired."""
    if not token:
        return None
    users = _load_users()
    now = datetime.now(timezone.utc)
    for email, user in users.items():
        if user.get("invite_token") != token:
            continue
        expires = user.get("invite_token_expires")
        if not expires or datetime.fromisoformat(expires) < now:
            return None
        return {"email": email, "role": user.get("role", "Analyst"),
                "invited_by": user.get("invited_by", "")}
    return None


def find_pending_invite_by_email(email: str) -> dict | None:
    """Same as get_pending_invite(), keyed by email instead of token.

    Needed because Streamlit's st.login() redirects back to the app's home
    page, not the page (or query params) the user started from — so a
    "Continue with Google" click from the invite-acceptance screen loses the
    ?invite=<token> in the URL by the time the identity comes back.
    auth_wall()'s post-redirect handling falls back to this once oauth_login()
    finds no existing linked identity, rather than needing the token to
    survive the round trip at all."""
    email = email.strip().lower()
    users = _load_users()
    user = users.get(email)
    if not user or not user.get("invite_token"):
        return None
    expires = user.get("invite_token_expires")
    if not expires or datetime.fromisoformat(expires) < datetime.now(timezone.utc):
        return None
    return {"token": user["invite_token"], "role": user.get("role", "Analyst"),
            "invited_by": user.get("invited_by", "")}


def accept_invite_with_password(token: str, password: str, user_agent: str = "") -> tuple[bool, str]:
    """Finalize a pending invite by setting a password — the invited user is
    signed in immediately, same as login(). Returns (True, jwt) on success,
    (False, error_message) otherwise."""
    invite = get_pending_invite(token)
    if not invite:
        return False, "This invite link is invalid or has expired. Ask your admin to send a new one."
    _ok, _err = validate_new_password(password)
    if not _ok:
        return False, _err
    users = _load_users()
    email = invite["email"]
    user = users[email]
    now = datetime.now(timezone.utc)
    user["password_hash"]        = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user["password_changed_at"]  = now.isoformat()
    user["status"]                = "Active"
    user["last_active"]           = now.isoformat()
    user["invite_token"]          = None
    user["invite_token_expires"]  = None
    token_jwt = _issue_session(users, email, user, user_agent)
    logkit.auth_event("invite.accepted", outcome="ok", user_id=logkit.user_hash(email), method="password")
    return True, token_jwt


def accept_invite_with_oauth(token: str, issuer: str, subject: str, oauth_email: str,
                             user_agent: str = "") -> tuple[bool, str]:
    """Finalize a pending invite by linking a provider identity instead of
    setting a password. The signed-in provider identity's email must match
    the address the invite was sent to — otherwise this would let anyone who
    knows (or guesses) an invite link claim it with an unrelated account."""
    invite = get_pending_invite(token)
    if not invite:
        return False, "This invite link is invalid or has expired. Ask your admin to send a new one."
    email = invite["email"]
    if oauth_email.strip().lower() != email:
        return False, (f"This invite was sent to {email}. Sign in with a matching account, "
                       f"or ask your admin to invite {oauth_email}.")
    users = _load_users()
    user = users[email]
    now = datetime.now(timezone.utc)
    user["status"]      = "Active"
    user["last_active"] = now.isoformat()
    user["invite_token"] = None
    user["invite_token_expires"] = None
    user["linked_identities"] = [{"issuer": issuer, "subject": subject,
                                  "email_at_link": oauth_email, "linked_at": now.isoformat()}]
    token_jwt = _issue_session(users, email, user, user_agent)
    logkit.auth_event("invite.accepted", outcome="ok", user_id=logkit.user_hash(email), method="oauth")
    return True, token_jwt


_RESET_TTL_HOURS = 24


def admin_request_password_reset(email: str, requested_by: str = "") -> tuple[bool, str, str | None]:
    """An admin generates a one-time password-reset link for an existing
    account that's locked out of its own password (there's no self-service
    "forgot password" — no outbound email exists, so the admin relays this
    link the same way invite_user() hands off an invite link). Returns
    (success, message, reset_token). Refuses a not-yet-accepted Invited
    account — that already has its own invite link/token; issuing a second,
    different token for the same account would just be confusing."""
    email = email.strip().lower()
    users = _load_users()
    if email not in users:
        return False, "User not found.", None
    if users[email].get("status") == "Invited":
        return False, "This account hasn't accepted its invite yet — resend the invite instead.", None

    token = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    users[email]["reset_token"]         = token
    users[email]["reset_token_expires"] = (now + timedelta(hours=_RESET_TTL_HOURS)).isoformat()
    _save_users(users)
    logkit.data_mutation(actor=logkit.user_id(), action="user.request_password_reset",
                         entity_type="user", entity_id=logkit.user_hash(email), requested_by=requested_by)
    return True, f"Reset link generated for {email}.", token


def get_pending_reset(token: str) -> dict | None:
    """{email} for a not-yet-expired reset token, for the reset-landing
    screen — or None if the token is unknown or expired."""
    if not token:
        return None
    users = _load_users()
    now = datetime.now(timezone.utc)
    for email, user in users.items():
        if user.get("reset_token") != token:
            continue
        expires = user.get("reset_token_expires")
        if not expires or datetime.fromisoformat(expires) < now:
            return None
        return {"email": email}
    return None


def complete_password_reset(token: str, new_password: str, user_agent: str = "") -> tuple[bool, str]:
    """Finalize an admin-issued reset by setting a new password — signs the
    user in immediately, same as accept_invite_with_password(). Returns
    (True, jwt) on success, (False, error_message) otherwise."""
    pending = get_pending_reset(token)
    if not pending:
        return False, "This reset link is invalid or has expired. Ask your admin to send a new one."
    _ok, _err = validate_new_password(new_password)
    if not _ok:
        return False, _err
    users = _load_users()
    email = pending["email"]
    user = users[email]
    now = datetime.now(timezone.utc)
    user["password_hash"]       = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    user["password_changed_at"] = now.isoformat()
    user["reset_token"]         = None
    user["reset_token_expires"] = None
    # A successful reset also clears any standing lockout — the whole point
    # is regaining access, and leaving a stale lock in place would let the
    # new password sit unusable until the timer happened to expire on its own.
    user["failed_attempts"] = 0
    user["locked_until"]    = None
    token_jwt = _issue_session(users, email, user, user_agent)
    logkit.auth_event("password.reset_completed", outcome="ok", user_id=logkit.user_hash(email))
    return True, token_jwt


def _rate_limit_settings() -> tuple[int, int]:
    """(attempts_before_lock, lock_minutes) from the Admin -> Security policy
    (settings.py's shared settings), workspace-wide like every other veto/
    threshold the Admin portal controls."""
    s = load_shared_settings()
    return (
        int(s.get("login_attempts_before_lock", 5)),
        int(s.get("lock_minutes", 15)),
    )


def _issue_session(users: dict, email: str, user: dict, user_agent: str = "") -> str:
    """Mint a session (sid + JWT) for `user`, persist it, and return the
    token. Shared by login(), accept_invite_with_password/oauth(), and
    oauth_login() — every path that ends with "this browser is now signed
    in" goes through here so there's exactly one place that mints a sid,
    prunes stale sessions, and shapes the JWT claims."""
    ttl_hours = _SESSION_TTL_HOURS.get(load_shared_settings().get("session_ttl", "24 h"), _JWT_TTL_H)
    now = datetime.now(timezone.utc)
    sid = uuid.uuid4().hex
    _cutoff = now - timedelta(hours=ttl_hours)
    sessions = [
        s for s in user.get("sessions", [])
        if datetime.fromisoformat(s["created_at"]) > _cutoff
    ]
    sessions.append({
        "sid":        sid,
        "created_at": now.isoformat(),
        "user_agent": (user_agent or "")[:200],
        "revoked":    False,
    })
    user["sessions"] = sessions
    users[email] = user
    _save_users(users)

    return jwt.encode(
        {
            "sub":  email,
            "role": user.get("role", "Analyst"),
            "sid":  sid,
            "exp":  now + timedelta(hours=ttl_hours),
            "iat":  now,
        },
        _JWT_SECRET,
        algorithm=_JWT_ALGO,
    )


def login(email: str, password: str, user_agent: str = "", device_id: str | None = None) -> tuple[bool, str]:
    """Verify credentials. Returns (success, jwt_token_or_error_message).

    Failed attempts on a *known* account count towards a per-account lockout
    (fields on the user record: failed_attempts, locked_until) so repeated
    guessing eventually has to wait out a timer rather than retry forever.
    Unknown emails never lock or reveal a count — there's no account to lock,
    and doing so would let an attacker use the "attempts remaining" copy to
    tell real accounts from made-up ones."""
    email = email.strip().lower()
    users = _load_users()
    if _store_broken(users):
        logkit.get_logger("uvalu.auth").critical(
            "user store unreadable", extra={"event": "auth.store.unreadable", "op": "login"})
        return False, ("The user store could not be read (wrong encryption key or a "
                       "corrupted file). Contact your administrator.")
    user = users.get(email)
    if not user:
        logkit.auth_event("login.failed", outcome="failed", reason="unknown_user",
                          user_id=logkit.user_hash(email))
        return False, "Invalid email or password."

    max_attempts, lock_minutes = _rate_limit_settings()
    now = datetime.now(timezone.utc)
    locked_until = user.get("locked_until")
    if locked_until:
        locked_dt = datetime.fromisoformat(locked_until)
        if now < locked_dt:
            # Checked before touching the password at all — a locked account
            # doesn't verify credentials, so a correct guess during the lock
            # window can't be distinguished from an incorrect one by timing
            # or response shape, and the lock can't be reset by retrying.
            remaining_min = max(1, -(-int((locked_dt - now).total_seconds()) // 60))  # ceil
            logkit.auth_event("login.failed", outcome="failed", reason="locked_out",
                              user_id=logkit.user_hash(email))
            return False, (f"This account is temporarily locked. Try again in "
                           f"{remaining_min} minute{'s' if remaining_min != 1 else ''}.")
        # Lock has expired — clear it before evaluating this attempt.
        user["locked_until"] = None
        user["failed_attempts"] = 0

    # No password_hash means a provider-only account (invited-but-not-yet-
    # accepted, or an OAuth account that never set one) — treated exactly
    # like a wrong password rather than its own branch, so this can't be
    # used to detect which accounts are password-less from the outside.
    _hash = user.get("password_hash")
    if not _hash or not bcrypt.checkpw(password.encode(), _hash.encode()):
        user["failed_attempts"] = user.get("failed_attempts", 0) + 1
        remaining_attempts = max_attempts - user["failed_attempts"]
        if remaining_attempts <= 0:
            user["locked_until"] = (now + timedelta(minutes=lock_minutes)).isoformat()
            user["failed_attempts"] = 0
            users[email] = user
            _save_users(users)
            logkit.auth_event("login.failed", outcome="locked", reason="bad_password",
                              user_id=logkit.user_hash(email))
            return False, (f"Invalid email or password. Too many failed attempts — "
                           f"this account is now locked for {lock_minutes} minutes.")
        users[email] = user
        _save_users(users)
        logkit.auth_event("login.failed", outcome="failed", reason="bad_password",
                          user_id=logkit.user_hash(email))
        return False, (f"Invalid email or password. {remaining_attempts} attempt"
                       f"{'s' if remaining_attempts != 1 else ''} remain before this "
                       f"account is locked for {lock_minutes} minutes.")
    if user.get("status") == "Suspended":
        logkit.auth_event("login.failed", outcome="failed", reason="suspended",
                          user_id=logkit.user_hash(email))
        return False, "This account has been suspended."

    # First successful login clears the Invited status; every login refreshes
    # last_active (shown in the Admin portal's Users table) and clears any
    # stale lockout bookkeeping from earlier failed attempts.
    was_invited = user.get("status") == "Invited"
    if was_invited:
        user["status"] = "Active"
    user["last_active"] = now.isoformat()
    user["failed_attempts"] = 0
    user["locked_until"] = None
    _save_users(users)  # persist status/last_active before the TOTP gate below

    if user.get("totp_enabled") and not is_trusted_device(email, device_id):
        logkit.auth_event("login.totp_required", outcome="pending", user_id=logkit.user_hash(email))
        return True, TOTP_REQUIRED

    token = _issue_session(users, email, user, user_agent)
    logkit.auth_event("login.ok", outcome="ok", user_id=logkit.user_hash(email),
                      role=user.get("role", "Analyst"), was_invited=was_invited)
    return True, token


def get_lockout(email: str) -> datetime | None:
    """Current lock expiry for an account, or None if it isn't locked (or
    doesn't exist) — lets a caller like uvalu/authgate.py render a countdown
    without re-deriving login()'s own lock-expiry check."""
    users = _load_users()
    user = users.get(email.strip().lower())
    if not user:
        return None
    locked_until = user.get("locked_until")
    if not locked_until:
        return None
    locked_dt = datetime.fromisoformat(locked_until)
    return locked_dt if datetime.now(timezone.utc) < locked_dt else None


def verify_token(token: str) -> tuple[str, str, str | None] | tuple[None, None, None]:
    """
    Validate a JWT. Returns (email, role, sid) on success, (None, None, None)
    on failure. `sid` identifies which entry in the user's `sessions` list
    this token belongs to (see login()) — it's None for a token issued
    before session tracking existed, which is treated as always-active by
    is_session_active() below rather than forcing every open tab to
    re-authenticate the moment this feature ships.
    """
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGO])
        return payload["sub"], payload.get("role", "Analyst"), payload.get("sid")
    except jwt.PyJWTError:
        logkit.get_logger("uvalu.auth").debug(
            "jwt verification failed", extra={"event": "auth.token.invalid"})
        return None, None, None


def is_session_active(email: str, sid: str | None) -> bool:
    """False if `sid` was explicitly signed out (see revoke_session() /
    revoke_other_sessions()). A missing sid (pre-session-tracking token) or a
    sid that's aged out of the list (see login()'s pruning) is treated as
    active — there's nothing to check it against, and the user's own
    password/lockout/suspension checks in auth_wall() already cover the
    security-relevant cases."""
    users = _load_users()
    user = users.get(email.strip().lower())
    if not user or not sid:
        return True
    for s in user.get("sessions", []):
        if s["sid"] == sid:
            return not s.get("revoked", False)
    return True


def list_sessions(email: str) -> list[dict]:
    """Non-revoked sessions for Settings -> Security's "Active sessions"
    card, most recent first."""
    users = _load_users()
    user = users.get(email.strip().lower())
    if not user:
        return []
    return sorted(
        (s for s in user.get("sessions", []) if not s.get("revoked", False)),
        key=lambda s: s["created_at"], reverse=True,
    )


def revoke_session(email: str, sid: str) -> tuple[bool, str]:
    """Sign out one session (e.g. a per-row 'Sign out' in Settings). Its JWT
    keeps decoding successfully — revocation is enforced by
    is_session_active(), not by invalidating the signature — so this only
    takes effect once that device's auth_wall() next re-checks (every
    rerun, same as a suspended account)."""
    email = email.strip().lower()
    users = _load_users()
    if email not in users:
        return False, "User not found."
    found = False
    for s in users[email].get("sessions", []):
        if s["sid"] == sid:
            s["revoked"] = True
            found = True
    if not found:
        return False, "Session not found."
    _save_users(users)
    logkit.data_mutation(actor=logkit.user_id(), action="user.revoke_session",
                         entity_type="user", entity_id=logkit.user_hash(email))
    return True, "Signed out of that session."


def revoke_other_sessions(email: str, keep_sid: str | None) -> tuple[bool, str]:
    """'Sign out everywhere else' — revoke every session except `keep_sid`
    (the caller's own, current one)."""
    email = email.strip().lower()
    users = _load_users()
    if email not in users:
        return False, "User not found."
    _n = 0
    for s in users[email].get("sessions", []):
        if s["sid"] != keep_sid and not s.get("revoked", False):
            s["revoked"] = True
            _n += 1
    _save_users(users)
    logkit.data_mutation(actor=logkit.user_id(), action="user.revoke_other_sessions",
                         entity_type="user", entity_id=logkit.user_hash(email), count=_n)
    return True, f"Signed out of {_n} other session{'s' if _n != 1 else ''}."


# ── Two-factor authentication (TOTP) ─────────────────────────────────────────

def is_totp_enabled(email: str) -> bool:
    users = _load_users()
    user = users.get(email.strip().lower())
    return bool(user and user.get("totp_enabled"))


def begin_totp_enrollment(email: str) -> tuple[str, str] | None:
    """Generate (but don't yet enable) a TOTP secret for `email` — the
    Settings enrollment dialog shows the QR/manual key from this, then calls
    confirm_totp_enrollment() once the user proves they scanned it correctly.
    Returns (secret, otpauth_uri), or None if the account doesn't exist.
    Calling this again before confirming overwrites the pending secret —
    intentional, since it means the user is retrying enrollment (e.g. after
    closing the dialog without finishing) rather than holding two secrets."""
    email = email.strip().lower()
    users = _load_users()
    if email not in users:
        return None
    secret = pyotp.random_base32()
    users[email]["totp_secret"] = secret
    _save_users(users)
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name="Uvalu")
    return secret, uri


def _fresh_backup_codes() -> tuple[list[str], list[str]]:
    """(plaintext_codes, bcrypt_hashes) — 10 single-use "xxxx-xxxx" codes.
    Plaintext is returned only so the caller can show it once; only the
    hashes are ever persisted, same as a password."""
    plain = [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(10)]
    hashed = [bcrypt.hashpw(c.encode(), bcrypt.gensalt()).decode() for c in plain]
    return plain, hashed


def confirm_totp_enrollment(email: str, code: str) -> tuple[bool, str, list[str] | None]:
    """Verify the enrollment code against the pending secret and, on success,
    enable TOTP and mint a fresh set of backup codes. Returns
    (success, message, backup_codes_or_None) — the plaintext codes are only
    ever returned from here (and regenerate_backup_codes()), never re-readable
    afterward, matching the mockup's "shown once, save them now" copy."""
    email = email.strip().lower()
    users = _load_users()
    user = users.get(email)
    if not user or not user.get("totp_secret"):
        return False, "Start enrollment again — no pending setup found.", None
    if not pyotp.totp.TOTP(user["totp_secret"]).verify(code, valid_window=1):
        return False, "That code didn't match. Try again.", None
    plain_codes, hashed_codes = _fresh_backup_codes()
    user["totp_enabled"]  = True
    user["backup_codes"]  = hashed_codes
    _save_users(users)
    logkit.data_mutation(actor=logkit.user_id(), action="user.totp_enabled",
                         entity_type="user", entity_id=logkit.user_hash(email))
    return True, "Two-factor authentication enabled.", plain_codes


def disable_totp(email: str) -> tuple[bool, str]:
    """Self-service turn-off from Settings — also drops backup codes and any
    trusted-device grants, since both are meaningless without TOTP enabled."""
    email = email.strip().lower()
    users = _load_users()
    if email not in users:
        return False, "User not found."
    users[email]["totp_enabled"]    = False
    users[email]["totp_secret"]     = None
    users[email]["backup_codes"]    = []
    users[email]["trusted_devices"] = []
    _save_users(users)
    logkit.data_mutation(actor=logkit.user_id(), action="user.totp_disabled",
                         entity_type="user", entity_id=logkit.user_hash(email))
    return True, "Two-factor authentication turned off."


def admin_reset_totp(email: str) -> tuple[bool, str]:
    """Admin Users-table 'Reset two-factor' action — same effect as
    disable_totp() (the user re-enrolls from scratch), for an account whose
    owner has lost their authenticator and can't disable it themselves."""
    email = email.strip().lower()
    users = _load_users()
    if email not in users:
        return False, "User not found."
    ok, _ = disable_totp(email)
    logkit.data_mutation(actor=logkit.user_id(), action="admin.reset_totp",
                         entity_type="user", entity_id=logkit.user_hash(email))
    return ok, f"Two-factor authentication reset for {email}."


def backup_codes_remaining(email: str) -> int:
    users = _load_users()
    user = users.get(email.strip().lower())
    return len(user.get("backup_codes", [])) if user else 0


def regenerate_backup_codes(email: str) -> list[str] | None:
    """Invalidate every existing backup code and issue 10 new ones — returns
    the plaintext list (shown once), or None if the account doesn't exist or
    doesn't have TOTP enabled (backup codes are meaningless without it)."""
    email = email.strip().lower()
    users = _load_users()
    user = users.get(email)
    if not user or not user.get("totp_enabled"):
        return None
    plain_codes, hashed_codes = _fresh_backup_codes()
    user["backup_codes"] = hashed_codes
    _save_users(users)
    logkit.data_mutation(actor=logkit.user_id(), action="user.backup_codes_regenerated",
                         entity_type="user", entity_id=logkit.user_hash(email))
    return plain_codes


def complete_totp_login(email: str, code: str, user_agent: str = "") -> tuple[bool, str]:
    """Second step of a TOTP-gated login() — verifies the 6-digit code and,
    on success, mints the session login() withheld."""
    email = email.strip().lower()
    users = _load_users()
    user = users.get(email)
    if not user or not user.get("totp_enabled"):
        return False, "Two-factor authentication isn't enabled for this account."
    if not pyotp.totp.TOTP(user["totp_secret"]).verify(code, valid_window=1):
        logkit.auth_event("login.failed", outcome="failed", reason="bad_totp_code",
                          user_id=logkit.user_hash(email))
        return False, "That code didn't match. Try again."
    token = _issue_session(users, email, user, user_agent)
    logkit.auth_event("login.ok", outcome="ok", user_id=logkit.user_hash(email),
                      role=user.get("role", "Analyst"), method="totp")
    return True, token


def complete_backup_code_login(email: str, code: str, user_agent: str = "") -> tuple[bool, str]:
    """Alternate second step when the authenticator itself isn't available —
    consumes one single-use backup code."""
    email = email.strip().lower()
    users = _load_users()
    user = users.get(email)
    if not user or not user.get("totp_enabled"):
        return False, "Two-factor authentication isn't enabled for this account."
    code = code.strip().lower()
    for i, hashed in enumerate(user.get("backup_codes", [])):
        if bcrypt.checkpw(code.encode(), hashed.encode()):
            user["backup_codes"].pop(i)
            token = _issue_session(users, email, user, user_agent)
            logkit.auth_event("login.ok", outcome="ok", user_id=logkit.user_hash(email),
                              role=user.get("role", "Analyst"), method="backup_code")
            return True, token
    logkit.auth_event("login.failed", outcome="failed", reason="bad_backup_code",
                      user_id=logkit.user_hash(email))
    return False, "That code didn't match. Try again."


def two_factor_status(email: str) -> str:
    """"ON" / "OFF" / "PROVIDER" / "REQUIRED" / "—" for the Admin Users
    table's 2FA column: ON/OFF for a password-capable account that has/hasn't
    enrolled; PROVIDER for a provider-only account (2FA is a password-path
    feature — see Settings); REQUIRED flags an Admin who hasn't enrolled while
    workspace policy requires it for Admins; "—" if the account doesn't
    exist."""
    users = _load_users()
    user = users.get(email.strip().lower())
    if not user:
        return "—"
    if user.get("totp_enabled"):
        return "ON"
    if not user.get("password_hash"):
        return "PROVIDER"
    policy = load_shared_settings().get("require_mfa", "Admins")
    if policy == "Everyone" or (policy == "Admins" and user.get("role") == "Admin"):
        return "REQUIRED"
    return "OFF"


# ── Trusted devices ───────────────────────────────────────────────────────────

def is_trusted_device(email: str, device_id: str | None) -> bool:
    if not device_id:
        return False
    users = _load_users()
    user = users.get(email.strip().lower())
    if not user:
        return False
    now = datetime.now(timezone.utc)
    for d in user.get("trusted_devices", []):
        if d.get("device_id") == device_id and datetime.fromisoformat(d["expires_at"]) > now:
            return True
    return False


def trust_this_device(email: str, days: int = 30) -> str:
    """Mark a new opaque device id as trusted for `days` (default 30) —
    "Remember this device" on the TOTP challenge. Returns the device_id for
    the caller to persist client-side (a long-lived cookie, distinct from the
    session cookie, so it survives a sign-out)."""
    email = email.strip().lower()
    users = _load_users()
    if email not in users:
        return ""
    device_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    devices = [d for d in users[email].get("trusted_devices", [])
              if datetime.fromisoformat(d["expires_at"]) > now]
    devices.append({"device_id": device_id, "created_at": now.isoformat(),
                    "expires_at": (now + timedelta(days=days)).isoformat()})
    users[email]["trusted_devices"] = devices
    _save_users(users)
    return device_id


def trusted_device_count(email: str) -> int:
    users = _load_users()
    user = users.get(email.strip().lower())
    if not user:
        return 0
    now = datetime.now(timezone.utc)
    return sum(1 for d in user.get("trusted_devices", [])
              if datetime.fromisoformat(d["expires_at"]) > now)


def revoke_trusted_devices(email: str) -> tuple[bool, str]:
    email = email.strip().lower()
    users = _load_users()
    if email not in users:
        return False, "User not found."
    users[email]["trusted_devices"] = []
    _save_users(users)
    logkit.data_mutation(actor=logkit.user_id(), action="user.revoke_trusted_devices",
                         entity_type="user", entity_id=logkit.user_hash(email))
    return True, "All trusted devices revoked."


# ── Password policy ───────────────────────────────────────────────────────────

_HIBP_TIMEOUT_S = 3.0


def check_password_breached(password: str) -> int | None:
    """Number of times this password appears in the Have I Been Pwned corpus,
    via the k-anonymity range API (only a 5-char SHA-1 prefix ever leaves this
    server) — or None if the check couldn't be completed (network error,
    non-200 response). Callers must treat None as "unknown", not "clean": a
    dependency outage shouldn't silently block every password change in the
    workspace, so validate_new_password() below fails OPEN on None rather
    than treating it as a hard block."""
    sha1 = hashlib.sha1(password.encode()).hexdigest().upper()
    prefix, suffix = sha1[:5], sha1[5:]
    try:
        resp = requests.get(f"https://api.pwnedpasswords.com/range/{prefix}", timeout=_HIBP_TIMEOUT_S)
        resp.raise_for_status()
    except requests.RequestException:
        logkit.get_logger("uvalu.auth").warning(
            "HIBP breach check unreachable — allowing password", exc_info=True,
            extra={"event": "auth.hibp.unreachable"})
        return None
    for line in resp.text.splitlines():
        parts = line.split(":")
        if len(parts) == 2 and parts[0] == suffix:
            return int(parts[1])
    return 0


def validate_new_password(password: str) -> tuple[bool, str | None]:
    """(ok, error_message) against the workspace's Admin -> Security password
    policy (min length, breach-block). Wired into every path that sets a
    NEW password chosen by the account owner themselves (invite acceptance,
    password reset, self-service change, provider-only "set a password") —
    deliberately NOT into register()/reset_password(), which are
    dev-only/admin-only paths predating this policy."""
    min_len = int(load_shared_settings().get("min_password_length", 12))
    if len(password) < min_len:
        return False, f"Password must be at least {min_len} characters."
    if load_shared_settings().get("block_breached_passwords", True):
        count = check_password_breached(password)
        if count:
            return False, ("This password has appeared in known data breaches. "
                           "Choose a different one.")
    return True, None


# ── Provider identities (OAuth) ──────────────────────────────────────────────
#
# An identity is keyed by (issuer, subject) — the OIDC issuer URL and that
# issuer's own stable subject id for the account — not by email or by our own
# "google"/"microsoft" provider label. Addresses get reused and renamed, and
# two providers can assert the same address, but issuer+subject is exactly
# what the provider itself guarantees is stable and unique (see Auth GUI
# Impact.dc.html's "Is a provider identity keyed by email or by subject?").
# One account can hold several (e.g. Google AND Microsoft at once) —
# `linked_identities` is a list, not a single column.

def _find_identity_owner(users: dict, issuer: str, subject: str) -> str | None:
    for email, user in users.items():
        for ident in user.get("linked_identities", []):
            if ident.get("issuer") == issuer and ident.get("subject") == subject:
                return email
    return None


def link_identity(email: str, issuer: str, subject: str, oauth_email: str = "") -> tuple[bool, str]:
    """Attach a provider identity to an already-authenticated account (the
    Settings -> Security 'Connect' action) — distinct from oauth_login()
    below, which resolves a *sign-in* attempt rather than a same-session
    linking action."""
    email = email.strip().lower()
    users = _load_users()
    if email not in users:
        return False, "User not found."
    owner = _find_identity_owner(users, issuer, subject)
    if owner and owner != email:
        return False, "This identity is already linked to a different account."
    identities = users[email].get("linked_identities", [])
    if any(i.get("issuer") == issuer for i in identities):
        return False, "This provider is already linked to your account."
    identities.append({"issuer": issuer, "subject": subject, "email_at_link": oauth_email,
                       "linked_at": datetime.now(timezone.utc).isoformat()})
    users[email]["linked_identities"] = identities
    _save_users(users)
    logkit.data_mutation(actor=logkit.user_id(), action="user.link_identity",
                         entity_type="user", entity_id=logkit.user_hash(email))
    return True, "Provider connected."


def unlink_identity(email: str, issuer: str) -> tuple[bool, str]:
    """Detach a provider identity — refused if it's the only sign-in method
    left (no password and no other linked identity), matching the mockup's
    'the last remaining method can never be removed'."""
    email = email.strip().lower()
    users = _load_users()
    if email not in users:
        return False, "User not found."
    user = users[email]
    identities = user.get("linked_identities", [])
    remaining = [i for i in identities if i.get("issuer") != issuer]
    if len(remaining) == len(identities):
        return False, "That provider isn't linked to your account."
    if not remaining and not user.get("password_hash"):
        return False, "Can't disconnect your only sign-in method — set a password first."
    users[email]["linked_identities"] = remaining
    _save_users(users)
    logkit.data_mutation(actor=logkit.user_id(), action="user.unlink_identity",
                         entity_type="user", entity_id=logkit.user_hash(email))
    return True, "Provider disconnected."


def set_password(email: str, new_password: str) -> tuple[bool, str]:
    """Set a first password on a provider-only account (Settings' 'Set a
    password' action) — distinct from change_password(), which requires
    proving the CURRENT password and so only applies once one already
    exists."""
    email = email.strip().lower()
    _ok, _err = validate_new_password(new_password)
    if not _ok:
        return False, _err
    users = _load_users()
    if email not in users:
        return False, "User not found."
    if users[email].get("password_hash"):
        return False, "This account already has a password — use Change instead."
    users[email]["password_hash"] = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    users[email]["password_changed_at"] = datetime.now(timezone.utc).isoformat()
    _save_users(users)
    logkit.data_mutation(actor=logkit.user_id(), action="user.set_password",
                         entity_type="user", entity_id=logkit.user_hash(email))
    return True, "Password set."


def oauth_login(issuer: str, subject: str, email: str, user_agent: str = "") -> tuple[bool, str]:
    """Resolve a completed OIDC sign-in (Streamlit's st.login()/st.user, via
    uvalu/oauth.py) against the user store. Returns (True, jwt) on success;
    (False, "not_invited") if this identity has no Uvalu account and
    workspace policy doesn't auto-provision one — the caller (authgate.py)
    renders the refusal screen using the email it already has, rather than
    this needing to round-trip it back."""
    email = email.strip().lower()
    users = _load_users()
    owner = _find_identity_owner(users, issuer, subject)
    if owner:
        user = users[owner]
        if user.get("status") == "Suspended":
            logkit.auth_event("login.failed", outcome="failed", reason="suspended",
                              user_id=logkit.user_hash(owner))
            return False, "suspended"
        was_invited = user.get("status") == "Invited"
        if was_invited:
            user["status"] = "Active"
        user["last_active"] = datetime.now(timezone.utc).isoformat()
        token = _issue_session(users, owner, user, user_agent)
        logkit.auth_event("login.ok", outcome="ok", user_id=logkit.user_hash(owner),
                          role=user.get("role", "Analyst"), was_invited=was_invited, method="oauth")
        return True, token

    shared = load_shared_settings()
    domain = email.rsplit("@", 1)[-1] if "@" in email else ""
    if shared.get("auto_provision_oauth", False) and domain in shared.get("allowed_email_domains", []):
        now = datetime.now(timezone.utc)
        new_user = {
            "password_hash": None, "role": "Analyst", "status": "Active",
            "created_at": now.isoformat(), "last_active": now.isoformat(),
            "password_changed_at": "", "linked_identities": [
                {"issuer": issuer, "subject": subject, "email_at_link": email, "linked_at": now.isoformat()}],
            "invite_token": None, "invite_token_expires": None, "invited_by": "",
        }
        users[email] = new_user
        token = _issue_session(users, email, new_user, user_agent)
        logkit.data_mutation(actor="system", action="user.auto_provision", entity_type="user",
                             entity_id=logkit.user_hash(email), role="Analyst")
        logkit.auth_event("login.ok", outcome="ok", user_id=logkit.user_hash(email),
                          role="Analyst", method="oauth", auto_provisioned=True)
        return True, token

    logkit.auth_event("login.failed", outcome="failed", reason="not_invited",
                      user_id=logkit.user_hash(email))
    return False, "not_invited"


def get_user_status(email: str) -> tuple[str, str] | None:
    """
    Current (role, status) for an email from the live user store, or None if
    the account no longer exists. A JWT's own `role` claim is only a
    snapshot from login time — it doesn't reflect an account that's since
    been suspended, deleted, or had its role changed. Callers that need an
    already-issued session to honor those changes immediately (rather than
    only once the JWT happens to expire) should re-check this on every
    request, not just trust the token's embedded role.
    """
    users = _load_users()
    user = users.get(email.strip().lower())
    if not user:
        return None
    return user.get("role", "Analyst"), user.get("status", "Active")


def password_last_changed(email: str) -> str | None:
    """ISO timestamp of the account's most recent password set/change/reset,
    for Settings -> Security's "Last changed" caption. None if the account
    doesn't exist (or has no password — a future OAuth-only account)."""
    users = _load_users()
    user = users.get(email.strip().lower())
    if not user:
        return None
    return user.get("password_changed_at") or None


def has_password(email: str) -> bool:
    """True if the account can sign in with a password at all — false for a
    provider-only account (Settings shows 'Set a password' instead of
    'Change' for these, mockup frame 11)."""
    users = _load_users()
    user = users.get(email.strip().lower())
    return bool(user and user.get("password_hash"))


def list_linked_identities(email: str) -> list[dict]:
    """This account's linked provider identities, for Settings ->
    Linked accounts. Each entry: {issuer, subject, email_at_link, linked_at}."""
    users = _load_users()
    user = users.get(email.strip().lower())
    return list(user.get("linked_identities", [])) if user else []


# ── Admin helpers ─────────────────────────────────────────────────────────────

def _other_active_admins(users: dict, exclude_email: str) -> int:
    """Count of Admin-role accounts other than `exclude_email` that are also
    Active (not Suspended) — used to block an action that would leave the
    workspace with no admin who can actually reach the Admin portal, since
    there's no other way back in (register()'s "first user becomes Admin"
    bootstrap only fires when the user list is completely empty, not merely
    lacking an active Admin). A *suspended* other admin doesn't count — they
    can't log in either, so they can't fix anything."""
    return sum(
        1 for email, u in users.items()
        if email != exclude_email and u.get("role") == "Admin"
        and u.get("status") != "Suspended"
    )


def list_users() -> list[dict]:
    """Return all users (without password hashes) sorted by creation date."""
    users = _load_users()
    return [
        {
            "email":       email,
            "role":        data.get("role", "Analyst"),
            "status":      data.get("status", "Active"),
            "created_at":  data.get("created_at", ""),
            "last_active": data.get("last_active", ""),
        }
        for email, data in sorted(users.items(), key=lambda kv: kv[1].get("created_at", ""))
    ]


def set_role(email: str, role: str) -> tuple[bool, str]:
    """Change a user's role. Returns (success, message)."""
    if role not in ROLES:
        return False, f"Unknown role '{role}'."
    users = _load_users()
    if email not in users:
        return False, "User not found."
    if (users[email].get("role") == "Admin" and role != "Admin"
            and _other_active_admins(users, email) == 0):
        logkit.authz_denied(action="admin.demote_last_admin", actor=logkit.user_id(),
                            resource=logkit.user_hash(email))
        return False, "Can't demote the last active Admin — promote another user first."
    _old_role = users[email].get("role")
    users[email]["role"] = role
    _save_users(users)
    logkit.data_mutation(actor=logkit.user_id(), action="user.set_role", entity_type="user",
                         entity_id=logkit.user_hash(email), before=_old_role, after=role)
    return True, f"{email} is now {role}."


def set_status(email: str, status: str) -> tuple[bool, str]:
    """Suspend or reactivate a user account. Returns (success, message)."""
    if status not in STATUSES:
        return False, f"Unknown status '{status}'."
    users = _load_users()
    if email not in users:
        return False, "User not found."
    if (status == "Suspended" and users[email].get("role") == "Admin"
            and _other_active_admins(users, email) == 0):
        logkit.authz_denied(action="admin.suspend_last_admin", actor=logkit.user_id(),
                            resource=logkit.user_hash(email))
        return False, "Can't suspend the last active Admin — promote another user first."
    _old_status = users[email].get("status")
    users[email]["status"] = status
    _save_users(users)
    logkit.data_mutation(actor=logkit.user_id(), action="user.set_status", entity_type="user",
                         entity_id=logkit.user_hash(email), before=_old_status, after=status)
    return True, f"{email} is now {status}."


def change_password(email: str, current_password: str, new_password: str) -> tuple[bool, str]:
    """Self-service password change from Settings -> Security — unlike
    reset_password() (Admin-only, no current-password check), this requires
    proving you already know the old one."""
    email = email.strip().lower()
    _ok, _err = validate_new_password(new_password)
    if not _ok:
        return False, _err
    users = _load_users()
    if email not in users:
        return False, "User not found."
    _hash = users[email].get("password_hash")
    if not _hash or not bcrypt.checkpw(current_password.encode(), _hash.encode()):
        logkit.auth_event("password.change_failed", outcome="failed", reason="bad_current_password",
                          user_id=logkit.user_hash(email))
        return False, "Current password is incorrect."
    users[email]["password_hash"] = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    users[email]["password_changed_at"] = datetime.now(timezone.utc).isoformat()
    _save_users(users)
    logkit.data_mutation(actor=logkit.user_id(), action="user.change_password",
                         entity_type="user", entity_id=logkit.user_hash(email))
    return True, "Password changed."


def reset_password(email: str, new_password: str) -> tuple[bool, str]:
    """Overwrite a user's password hash. Returns (success, message)."""
    email = email.strip().lower()
    if len(new_password) < 8:
        return False, "Password must be at least 8 characters."
    users = _load_users()
    if email not in users:
        return False, "User not found."
    users[email]["password_hash"] = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    users[email]["password_changed_at"] = datetime.now(timezone.utc).isoformat()
    _save_users(users)
    logkit.data_mutation(actor=logkit.user_id(), action="user.reset_password",
                         entity_type="user", entity_id=logkit.user_hash(email))
    return True, f"Password reset for {email}."


def delete_user(email: str) -> tuple[bool, str]:
    """Delete a user account. Returns (success, message)."""
    users = _load_users()
    if email not in users:
        return False, "User not found."
    if (users[email].get("role") == "Admin"
            and _other_active_admins(users, email) == 0):
        logkit.authz_denied(action="admin.delete_last_admin", actor=logkit.user_id(),
                            resource=logkit.user_hash(email))
        return False, "Can't delete the last active Admin — promote another user first."
    _deleted_role = users[email].get("role")
    del users[email]
    _save_users(users)
    logkit.data_mutation(actor=logkit.user_id(), action="user.delete", entity_type="user",
                         entity_id=logkit.user_hash(email), before=_deleted_role)
    return True, f"{email} deleted."
