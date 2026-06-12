"""
Email/password authentication with bcrypt hashing and JWT sessions.

Roles:
  administrator — full access + user management panel
  normal        — full access to screener and portfolio
  demo          — read-only screener; portfolio and watchlist editing disabled

Users are stored in .cache/users.json. The first account created is
automatically assigned the administrator role. The JWT secret is read from
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

ROLES = ("administrator", "normal", "demo")


# ── User store ────────────────────────────────────────────────────────────────

def _load_users() -> dict:
    if USERS_FILE.exists():
        try:
            return json.loads(read_encrypted(USERS_FILE))
        except Exception:
            pass
    return {}


def _save_users(users: dict) -> None:
    write_encrypted(USERS_FILE, json.dumps(users, indent=2))


# ── Public API ────────────────────────────────────────────────────────────────

def register(email: str, password: str, role: str = "demo") -> tuple[bool, str]:
    """
    Create a new account. Returns (success, message).
    The first account ever created is promoted to administrator regardless of
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

    # Bootstrap: first user becomes administrator
    effective_role = "administrator" if not users else role

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    users[email] = {
        "password_hash": hashed,
        "role":          effective_role,
        "created_at":    datetime.now(timezone.utc).isoformat(),
    }
    _save_users(users)
    return True, "Account created. You can now log in."


def login(email: str, password: str) -> tuple[bool, str]:
    """Verify credentials. Returns (success, jwt_token_or_error_message)."""
    email = email.strip().lower()
    users = _load_users()
    user = users.get(email)
    if not user:
        return False, "Invalid email or password."
    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return False, "Invalid email or password."

    token = jwt.encode(
        {
            "sub":  email,
            "role": user.get("role", "normal"),
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
        return payload["sub"], payload.get("role", "normal")
    except jwt.PyJWTError:
        return None, None


# ── Admin helpers ─────────────────────────────────────────────────────────────

def list_users() -> list[dict]:
    """Return all users (without password hashes) sorted by creation date."""
    users = _load_users()
    return [
        {"email": email, "role": data.get("role", "normal"), "created_at": data.get("created_at", "")}
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


def delete_user(email: str) -> tuple[bool, str]:
    """Delete a user account. Returns (success, message)."""
    users = _load_users()
    if email not in users:
        return False, "User not found."
    del users[email]
    _save_users(users)
    return True, f"{email} deleted."
