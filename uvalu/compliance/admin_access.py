"""Record of administrator actions on another user's account or data (L16).

Privacy notice §6 promises that the administrator "records each such access".
The event logs keep admin actions for 31 days only (uvalu/logkit); this file
keeps one line per action for ADMIN_ACCESS_KEEP_DAYS, as accountability
evidence (GDPR art. 5(2)) and to answer a user who asks who touched their
account.

Both sides are stored as the same pseudonymous id the logs use
(logkit.user_hash: sha256 of the lower-cased email, 16 hex characters), so a
user's request can be answered by hashing their email, without keeping
another list of addresses.

No Streamlit import; unit-tested in tests/test_admin_access.py.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from uvalu.logkit.context import user_hash

ACCESS_FILE = Path(__file__).resolve().parents[2] / "data" / "compliance" / "admin_access.jsonl"
ADMIN_ACCESS_KEEP_DAYS = 731   # 24 months, like the signal history

# Actions recorded. Keep in step with the call sites in uvalu/pages_/admin.py.
ACTIONS = {
    "reset_link": "Generated a password reset link",
    "reset_two_factor": "Reset two-factor authentication",
    "role_change": "Changed the role",
    "status_change": "Changed the status (suspend or reactivate)",
    "sign_out_sessions": "Signed out every session",
    "delete_account": "Deleted the account and its data",
    "restore_backup": "Restored a backup over the account's data",
}

_lock = threading.Lock()


def record(actor_email: str, target_email: str, action: str, *, detail: str = "",
           at: "datetime | None" = None, path: "Path | None" = None) -> None:
    """Append one admin action on `target_email`'s account. Unknown actions
    are refused, so the list in ACTIONS stays the complete set."""
    if action not in ACTIONS:
        raise ValueError(f"unknown admin action {action!r}")
    path = path or ACCESS_FILE
    stamp = (at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(timespec="seconds")
    rec = {"at": stamp, "actor": user_hash(actor_email), "target": user_hash(target_email),
           "action": action}
    if detail:
        rec["detail"] = detail
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        _prune(path)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _prune(path: Path) -> None:
    """Drop records older than ADMIN_ACCESS_KEEP_DAYS (called under _lock)."""
    recs = _read(path)
    cutoff = datetime.now(timezone.utc) - timedelta(days=ADMIN_ACCESS_KEEP_DAYS)
    keep = [r for r in recs if _when(r) is None or _when(r) >= cutoff]
    if len(keep) != len(recs):
        path.write_text("".join(json.dumps(r) + "\n" for r in keep), encoding="utf-8")


def _when(rec: dict) -> "datetime | None":
    try:
        return datetime.fromisoformat(rec["at"])
    except (KeyError, TypeError, ValueError):
        return None


def for_user(email: str, path: "Path | None" = None) -> list[dict]:
    """Every recorded admin action on `email`'s account, oldest first."""
    target = user_hash(email)
    return [r for r in _read(path or ACCESS_FILE) if r.get("target") == target]
