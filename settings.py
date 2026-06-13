"""User-scoped app settings — stored encrypted in data/settings.json."""

from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from crypto import read_encrypted, write_encrypted  # noqa: E402

_DATA_DIR = Path(__file__).parent / "data"
_DATA_DIR.mkdir(exist_ok=True)

SETTINGS_FILE = _DATA_DIR / "settings.json"

ALL_EXCHANGES: list[str] = ["brussels", "amsterdam", "paris", "milan", "frankfurt", "swiss"]

EXCHANGE_LABELS: dict[str, str] = {
    "brussels":  "Euronext Brussels",
    "amsterdam": "Euronext Amsterdam",
    "paris":     "Euronext Paris",
    "milan":     "Borsa Italiana",
    "frankfurt": "Deutsche Börse",
    "swiss":     "SIX Swiss Exchange",
}

_DEFAULTS: dict = {"enabled_exchanges": ALL_EXCHANGES}


def load_settings() -> dict:
    if not SETTINGS_FILE.exists():
        return dict(_DEFAULTS)
    try:
        data = json.loads(read_encrypted(SETTINGS_FILE))
        # Fill in any keys added after the file was written
        for k, v in _DEFAULTS.items():
            data.setdefault(k, v)
        return data
    except Exception:
        return dict(_DEFAULTS)


def save_settings(s: dict) -> None:
    write_encrypted(SETTINGS_FILE, json.dumps(s, indent=2))
