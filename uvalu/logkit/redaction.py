"""Scrub secrets and raw PII out of log payloads (spec §5).

This is the enforcement point: call sites are told never to pass a password,
token, key, or raw email, but ``RedactionFilter`` (filters.py) runs ``scrub``
over every record's message and ``extra`` metadata so a slip doesn't leak.
"""
from __future__ import annotations

import re

REDACTED = "[redacted]"

# Case-insensitive substrings; a metadata key containing any of these has its
# value replaced wholesale.
_KEY_DENYLIST = (
    "password", "passwd", "pwd", "secret", "token", "jwt", "authorization",
    "bearer", "auth_secret", "encryption_key", "api_key", "apikey", "cookie",
    "session", "crumb", "password_hash", "private_key", "access_key",
)

_JWT_RE     = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
_FERNET_RE  = re.compile(r"gAAAAA[A-Za-z0-9_\-=]{20,}")
_BCRYPT_RE  = re.compile(r"\$2[aby]\$\d\d\$[./A-Za-z0-9]{53}")
_HEX64_RE   = re.compile(r"\b[0-9a-fA-F]{64}\b")
_EMAIL_RE   = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
# 13+ digits, optionally space/dash grouped — card / SSN heuristic.
_LONGNUM_RE = re.compile(r"\b\d(?:[ \-]?\d){12,}\b")

_MAX_DEPTH = 6


def _email_to_hash(email: str) -> str:
    from uvalu.logkit.context import user_hash
    return f"user:{user_hash(email)}"


def scrub_text(s: str) -> str:
    s = _JWT_RE.sub(REDACTED, s)
    s = _FERNET_RE.sub(REDACTED, s)
    s = _BCRYPT_RE.sub(REDACTED, s)
    s = _HEX64_RE.sub(REDACTED, s)
    s = _EMAIL_RE.sub(lambda m: _email_to_hash(m.group(0)), s)
    s = _LONGNUM_RE.sub(REDACTED, s)
    return s


def key_is_sensitive(key: str) -> bool:
    k = key.lower()
    return any(bad in k for bad in _KEY_DENYLIST)


def scrub(value, _depth: int = 0):
    """Recursively scrub a value: sensitive dict keys are blanked, strings are
    pattern-scrubbed, containers are walked. Non-str scalars pass through."""
    if _depth > _MAX_DEPTH:
        return value
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        return {
            k: (REDACTED if key_is_sensitive(str(k)) else scrub(v, _depth + 1))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return type(value)(scrub(v, _depth + 1) for v in value)
    return value
