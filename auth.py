"""
Email/password authentication with bcrypt hashing and JWT sessions.

Roles:
  Admin   — full access + user/workspace administration (Admin portal)
  Analyst — full read/write access to screener and portfolio
  Viewer  — read-only; mutating actions (Buy/Sell/Edit/Delete/Add dividend)
            are hidden or disabled across the app

Users are stored in .cache/users.json. The first account created is
automatically assigned the Admin role. The JWT secret is read from
the AUTH_SECRET environment variable; a random fallback is generated at
startup (sessions survive until the process restarts).
"""

import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
import jwt
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from crypto import read_encrypted, write_encrypted  # noqa: E402

USERS_FILE  = Path(__file__).parent / ".cache" / "users.json"
_JWT_SECRET = os.environ.get("AUTH_SECRET") or secrets.token_hex(32)
_JWT_ALGO   = "HS256"
_JWT_TTL_H  = 24

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
        "role":         role,
        "status":       data.get("status", "Active"),
        "last_active":  data.get("last_active", ""),
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
    if email in users:
        return False, "An account with this email already exists."

    # Bootstrap: first user becomes Admin
    effective_role = "Admin" if not users else role

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    users[email] = {
        "password_hash": hashed,
        "role":          effective_role,
        "status":        "Active",
        "created_at":    datetime.now(timezone.utc).isoformat(),
        "last_active":   "",
    }
    _save_users(users)
    return True, "Account created. You can now log in."


def invite_user(email: str, role: str = "Analyst") -> tuple[bool, str, str | None]:
    """
    Create an Invited account with a random temporary password. No outbound
    email exists — returns (success, message, temp_password) so the caller
    can display the password once for the admin to hand off manually.
    """
    email = email.strip().lower()
    if not email or "@" not in email:
        return False, "Enter a valid email address.", None
    if role not in ROLES:
        return False, f"Unknown role '{role}'.", None
    users = _load_users()
    if email in users:
        return False, "An account with this email already exists.", None

    temp_password = secrets.token_urlsafe(9)
    hashed = bcrypt.hashpw(temp_password.encode(), bcrypt.gensalt()).decode()
    users[email] = {
        "password_hash": hashed,
        "role":          role,
        "status":        "Invited",
        "created_at":    datetime.now(timezone.utc).isoformat(),
        "last_active":   "",
    }
    _save_users(users)
    return True, f"{email} invited.", temp_password


def login(email: str, password: str) -> tuple[bool, str]:
    """Verify credentials. Returns (success, jwt_token_or_error_message)."""
    email = email.strip().lower()
    users = _load_users()
    user = users.get(email)
    if not user:
        return False, "Invalid email or password."
    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return False, "Invalid email or password."
    if user.get("status") == "Suspended":
        return False, "This account has been suspended."

    # First successful login clears the Invited status; every login refreshes
    # last_active (shown in the Admin portal's Users table).
    if user.get("status") == "Invited":
        user["status"] = "Active"
    user["last_active"] = datetime.now(timezone.utc).isoformat()
    users[email] = user
    _save_users(users)

    token = jwt.encode(
        {
            "sub":  email,
            "role": user.get("role", "Analyst"),
            "exp":  datetime.now(timezone.utc) + timedelta(hours=_JWT_TTL_H),
            "iat":  datetime.now(timezone.utc),
        },
        _JWT_SECRET,
        algorithm=_JWT_ALGO,
    )
    return True, token


def verify_token(token: str) -> tuple[str, str] | tuple[None, None]:
    """
    Validate a JWT. Returns (email, role) on success, (None, None) on failure.
    """
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGO])
        return payload["sub"], payload.get("role", "Analyst")
    except jwt.PyJWTError:
        return None, None


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


# ── Admin helpers ─────────────────────────────────────────────────────────────

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
    users[email]["role"] = role
    _save_users(users)
    return True, f"{email} is now {role}."


def set_status(email: str, status: str) -> tuple[bool, str]:
    """Suspend or reactivate a user account. Returns (success, message)."""
    if status not in STATUSES:
        return False, f"Unknown status '{status}'."
    users = _load_users()
    if email not in users:
        return False, "User not found."
    users[email]["status"] = status
    _save_users(users)
    return True, f"{email} is now {status}."


def reset_password(email: str, new_password: str) -> tuple[bool, str]:
    """Overwrite a user's password hash. Returns (success, message)."""
    email = email.strip().lower()
    if len(new_password) < 8:
        return False, "Password must be at least 8 characters."
    users = _load_users()
    if email not in users:
        return False, "User not found."
    users[email]["password_hash"] = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    _save_users(users)
    return True, f"Password reset for {email}."


def delete_user(email: str) -> tuple[bool, str]:
    """Delete a user account. Returns (success, message)."""
    users = _load_users()
    if email not in users:
        return False, "User not found."
    del users[email]
    _save_users(users)
    return True, f"{email} deleted."
