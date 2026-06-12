"""
One-time migration: encrypt existing plain-text JSON cache files.

Run once after setting ENCRYPTION_KEY in .env:
    python migrate_cache.py
"""

import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from crypto import encrypt_text, decrypt_text  # noqa: E402

SENSITIVE_FILES = [
    Path(".cache/users.json"),
    Path(".cache/portfolio.json"),
    Path(".cache/sold.json"),
    Path(".cache/dividends_history.json"),
    Path(".cache/watchlist.json"),
]


def _is_encrypted(path: Path) -> bool:
    """Fernet tokens always start with 'gAAA' when base64-decoded."""
    try:
        data = path.read_bytes()
        decrypt_text(data)
        return True
    except Exception:
        return False


def migrate():
    for path in SENSITIVE_FILES:
        if not path.exists():
            print(f"  skip  {path}  (not found)")
            continue

        if _is_encrypted(path):
            print(f"  skip  {path}  (already encrypted)")
            continue

        try:
            plain = path.read_text(encoding="utf-8")
            json.loads(plain)  # validate it's valid JSON before overwriting
        except Exception as exc:
            print(f"  ERROR {path}  could not read as JSON: {exc}")
            continue

        path.write_bytes(encrypt_text(plain))
        print(f"  done  {path}")


if __name__ == "__main__":
    print("Encrypting cache files...")
    migrate()
    print("Migration complete.")
