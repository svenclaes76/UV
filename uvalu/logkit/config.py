"""Load ``logging.config.json`` and expose it as a merged snapshot.

The file is read at startup and (unless disabled) re-read on an mtime poll for
the live-adjustable keys — see ``uvalu.logkit.setup._start_hot_reload``. Missing
or unreadable file falls back to ``DEFAULTS`` verbatim, so the app still logs.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = _REPO_ROOT / "logging.config.json"

DEFAULTS: dict = {
    "level": "INFO",
    # null -> fall back to UVALU_ENV, then "development"
    "environment": None,
    "console": {"enabled": True, "format": "auto", "color": "auto"},
    "file": {
        "enabled": True,
        "path": "logs/uvalu.log",
        "max_bytes": 5 * 1024 * 1024,
        "backup_count": 10,
        "format": "json",
    },
    "retention_days": 31,
    "async": True,
    "queue_capacity": 10000,
    # "auto" -> full stack in dev/staging, error_type + fingerprint only in prod
    "stack_traces": "auto",
    "health_check_logging": False,
    "hot_reload": True,
    "per_logger_levels": {"uvalu.render": "WARNING"},
    "sampling": {
        "uvalu.screener.fetch": {"level": "INFO", "rate": 0.05},
        "uvalu.render": {"level": "DEBUG", "rate": 0.0},
    },
}

_lock = threading.Lock()
_current: dict = json.loads(json.dumps(DEFAULTS))  # deep copy


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path: "str | Path | None" = None) -> dict:
    """Read the config file (merged over ``DEFAULTS``) and cache it as the
    process-wide current config. Returns the merged dict."""
    global _current
    p = Path(path) if path else CONFIG_PATH
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raw = {}
    except (OSError, ValueError):
        raw = {}
    merged = _deep_merge(DEFAULTS, raw)
    with _lock:
        _current = merged
    return merged


def current() -> dict:
    with _lock:
        return _current


def file_mtime(path: "str | Path | None" = None) -> float:
    p = Path(path) if path else CONFIG_PATH
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def resolve_environment(cfg: "dict | None" = None) -> str:
    cfg = cfg if cfg is not None else current()
    val = cfg.get("environment") or os.environ.get("UVALU_ENV") or "development"
    return str(val).strip().lower()
