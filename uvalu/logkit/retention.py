"""Purge rotated log files older than ``retention_days`` (spec §6, §11).

The active file's size is bounded by ``RotatingFileHandler`` (the hard
disk-fill guard); this deletes the *rotated* backups (``uvalu.log.1`` …) once
they age past the retention window. Runs once at startup and again roughly
daily from the hot-reload poll thread.
"""
from __future__ import annotations

import time
from pathlib import Path

from uvalu.logkit import config as _config


def resolve_log_path(cfg: "dict | None" = None, log_dir: "str | Path | None" = None) -> Path:
    cfg = cfg if cfg is not None else _config.current()
    raw = cfg.get("file", {}).get("path", "logs/uvalu.log")
    p = Path(raw)
    if not p.is_absolute():
        base = Path(log_dir) if log_dir else _config._REPO_ROOT
        p = base / p
    return p


def sweep(cfg: "dict | None" = None, log_dir: "str | Path | None" = None) -> int:
    """Delete rotated backups of the active log file older than
    ``retention_days``. Returns the number removed. Never touches the active
    file itself."""
    cfg = cfg if cfg is not None else _config.current()
    days = int(cfg.get("retention_days", 31))
    if days <= 0:
        return 0
    active = resolve_log_path(cfg, log_dir)
    folder = active.parent
    if not folder.is_dir():
        return 0
    cutoff = time.time() - days * 86400
    removed = 0
    for f in folder.glob(active.name + ".*"):
        try:
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except OSError:
            pass
    return removed
