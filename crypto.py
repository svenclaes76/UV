"""
Symmetric encryption helpers for cache files at rest.

Key derivation: PBKDF2-HMAC-SHA256 over ENCRYPTION_KEY env var → Fernet key.
The salt is fixed (non-secret) so the same key always produces the same derived
key, which is required for persistent encrypted files.  The security guarantee
comes entirely from the secret ENCRYPTION_KEY value.
"""

import base64
import os
from hashlib import pbkdf2_hmac
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

# Fixed salt — keeps derived key stable across restarts.
_SALT = b"uv-portfolio-v1"
_ITERATIONS = 200_000


def _fernet() -> Fernet:
    raw = os.environ.get("ENCRYPTION_KEY", "").strip()
    if not raw:
        raise EnvironmentError(
            "ENCRYPTION_KEY environment variable is not set. "
            "Add it to your .env file."
        )
    key_bytes = pbkdf2_hmac("sha256", raw.encode(), _SALT, _ITERATIONS, dklen=32)
    return Fernet(base64.urlsafe_b64encode(key_bytes))


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
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(encrypt_text(plain))
