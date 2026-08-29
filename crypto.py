"""
Symmetric encryption helpers for cache files at rest.

Key derivation: PBKDF2-HMAC-SHA256 over ENCRYPTION_KEY env var → Fernet key.
The salt is fixed (non-secret) so the same key always produces the same derived
key, which is required for persistent encrypted files.  The security guarantee
comes entirely from the secret ENCRYPTION_KEY value.
"""

import base64
import os
import threading
from hashlib import pbkdf2_hmac
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

# Fixed salt — keeps derived key stable across restarts.
_SALT = b"uv-portfolio-v1"
_ITERATIONS = 200_000

# Cached (source key, derived Fernet) pair — PBKDF2 at 200k iterations is
# deliberately slow (that's the point, for brute-force resistance), and
# ENCRYPTION_KEY doesn't change during a running process, but _fernet() used
# to re-derive it from scratch on every single encrypt/decrypt call. Every
# page's read_encrypted/write_encrypted calls pay that cost repeatedly —
# including auth._load_users() on every Streamlit rerun (see
# auth-session-revocation-fix). Keyed on the raw env value, not just "have we
# ever computed one," so a changed ENCRYPTION_KEY within the same process
# (e.g. across tests that monkeypatch different keys) still re-derives
# instead of silently reusing a stale Fernet from a previous key.
#
# _cache_lock guards the check-then-write below: without it, two threads
# racing here with DIFFERENT raw values (only possible in this app's own
# test suite via monkeypatch.setenv — ENCRYPTION_KEY never changes mid-process
# in production) could interleave their writes and leave _cached_key from one
# thread paired with _cached_fernet from the other, a real mismatched pair
# that would silently encrypt/decrypt with the wrong derived key. The lock
# only guards the (rare) recompute path — same key returns via the fast,
# lock-free comparison below.
_cache_lock = threading.Lock()
_cached_key: str | None = None
_cached_fernet: Fernet | None = None


def _fernet() -> Fernet:
    global _cached_key, _cached_fernet
    raw = os.environ.get("ENCRYPTION_KEY", "").strip()
    if not raw:
        raise EnvironmentError(
            "ENCRYPTION_KEY environment variable is not set. "
            "Add it to your .env file."
        )
    if raw != _cached_key:
        with _cache_lock:
            # Re-check: another thread may have already recomputed this
            # exact key while we were waiting for the lock.
            if raw != _cached_key:
                key_bytes = pbkdf2_hmac("sha256", raw.encode(), _SALT, _ITERATIONS, dklen=32)
                _cached_fernet = Fernet(base64.urlsafe_b64encode(key_bytes))
                # Written last, after _cached_fernet: any thread that observes
                # _cached_key already matching raw (fast path, no lock) is
                # therefore guaranteed to also see the matching _cached_fernet.
                _cached_key = raw
    return _cached_fernet


def encrypt_text(plain: str) -> bytes:
    """Encrypt a UTF-8 string and return ciphertext bytes."""
    return _fernet().encrypt(plain.encode("utf-8"))


def decrypt_text(ciphertext: bytes) -> str:
    """Decrypt ciphertext bytes back to a UTF-8 string."""
    return _fernet().decrypt(ciphertext).decode("utf-8")


def read_encrypted(path: Path) -> str:
    """Read an encrypted file and return the plaintext string."""
    return decrypt_text(path.read_bytes())


def write_encrypted(path: Path, plain: str) -> None:
    """Write a plaintext string to an encrypted file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encrypt_text(plain))
