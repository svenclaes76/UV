"""User-scoped app settings — one encrypted file per user in data/settings/."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from crypto import read_encrypted, write_encrypted  # noqa: E402

_DATA_DIR = Path(__file__).parent / "data" / "settings"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

ALL_EXCHANGES: list[str] = ["brussels", "amsterdam", "paris", "milan", "frankfurt", "swiss"]

EXCHANGE_LABELS: dict[str, str] = {
    "brussels":  "Euronext Brussels",
    "amsterdam": "Euronext Amsterdam",
    "paris":     "Euronext Paris",
    "milan":     "Borsa Italiana",
    "frankfurt": "Deutsche Börse",
    "swiss":     "SIX Swiss Exchange",
}

_SHARED_FILE   = _DATA_DIR / "shared.json"
_SHARED_DEFAULTS: dict = {"enabled_exchanges": ALL_EXCHANGES}

_USER_DEFAULTS: dict = {}


def _settings_file(email: str) -> Path:
    slug = hashlib.sha256(email.strip().lower().encode()).hexdigest()[:16]
    return _DATA_DIR / f"{slug}.json"


# ── Shared settings (admin-controlled, apply to all users) ───────────────────

def load_shared_settings() -> dict:
    if not _SHARED_FILE.exists():
        return dict(_SHARED_DEFAULTS)
    try:
        data = json.loads(read_encrypted(_SHARED_FILE))
        for k, v in _SHARED_DEFAULTS.items():
            data.setdefault(k, v)
        return data
    except Exception:
        return dict(_SHARED_DEFAULTS)


def save_shared_settings(s: dict) -> None:
    write_encrypted(_SHARED_FILE, json.dumps(s, indent=2))


# ── Per-user settings ────────────────────────────────────────────────────────

def load_settings(email: str = "") -> dict:
    path = _settings_file(email) if email else _DATA_DIR / "default.json"
    if not path.exists():
        return dict(_USER_DEFAULTS)
    try:
        data = json.loads(read_encrypted(path))
        for k, v in _USER_DEFAULTS.items():
            data.setdefault(k, v)
        return data
    except Exception:
        return dict(_USER_DEFAULTS)


def save_settings(s: dict, email: str = "") -> None:
    path = _settings_file(email) if email else _DATA_DIR / "default.json"
    write_encrypted(path, json.dumps(s, indent=2))
