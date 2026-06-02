"""
Email/password authentication with bcrypt hashing and JWT sessions.

Users are stored in .cache/users.json. The JWT secret is read from the
AUTH_SECRET environment variable; a random fallback is generated at startup
(sessions survive until the process restarts).
"""

import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
import jwt

USERS_FILE = Path(__file__).parent / ".cache" / "users.json"
_JWT_SECRET = os.environ.get("AUTH_SECRET") or secrets.token_hex(32)
_JWT_ALGO   = "HS256"
_JWT_TTL_H  = 24  # hours before token expires


# ── User store ────────────────────────────────────────────────────────────────

def _load_users() -> dict:
    if USERS_FILE.exists():
        try:
            return json.loads(USERS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_users(users: dict) -> None:
    USERS_FILE.parent.mkdir(exist_ok=True)
    USERS_FILE.write_text(json.dumps(users, indent=2), encoding="utf-8")


# ── Public API ────────────────────────────────────────────────────────────────

def register(email: str, password: str) -> tuple[bool, str]:
    """
    Create a new account. Returns (success, message).
    Fails if email already registered or inputs are invalid.
    """
    email = email.strip().lower()
    if not email or "@" not in email:
        return False, "Enter a valid email address."
    if len(password) < 8:
        return False, "Password must be at least 8 characters."

    users = _load_users()
    if email in users:
        return False, "An account with this email already exists."

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    users[email] = {"password_hash": hashed, "created_at": datetime.now(timezone.utc).isoformat()}
    _save_users(users)
    return True, "Account created. You can now log in."


def login(email: str, password: str) -> tuple[bool, str]:
    """
    Verify credentials. Returns (success, jwt_token_or_error_message).
    """
    email = email.strip().lower()
    users = _load_users()
    user = users.get(email)
    if not user:
        return False, "Invalid email or password."
    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return False, "Invalid email or password."

    token = jwt.encode(
        {
            "sub": email,
            "exp": datetime.now(timezone.utc) + timedelta(hours=_JWT_TTL_H),
            "iat": datetime.now(timezone.utc),
        },
        _JWT_SECRET,
        algorithm=_JWT_ALGO,
    )
    return True, token


def verify_token(token: str) -> str | None:
    """
    Validate a JWT. Returns the email (subject) on success, None on failure.
    """
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGO])
        return payload["sub"]
    except jwt.PyJWTError:
        return None
