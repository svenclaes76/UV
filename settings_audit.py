"""
Audit log of shared model settings and model versions — REC-9 / REC-11 of
"Uvalu — Legal Requirements for Launch".

The shared screening settings (thresholds, screening style) and the model code
decide every user's badge. The conflicts of interest policy promises that the
founder does not trade an affected stock from the moment a change that alters
signals is decided until 2 trading days after it is live (MAR art. 12(2)(d),
art. 15). This append-only JSON-lines log is the evidence: it records when a
change was planned, when each setting changed (who, old → new), and when each
model version first went live. Compare it against the personal trade register.

Events (``event`` field):
  "planned"        a signal-moving change was decided (start of the blackout)
  "setting"        one shared setting changed: key, old, new
  "model_version"  a new MODEL_VERSION / settings id was first used to score

The ``actor`` is the admin's account email: personal data, kept under
legitimate interest (regulatory evidence) and listed in the privacy notice.

Part of the legal-compliance candidate set; not yet wired into the app
(see docs/legal/algorithm-compliance-review.md §4).
"""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

AUDIT_FILE = Path(__file__).parent / "data" / "settings_audit.jsonl"

EVENT_PLANNED       = "planned"
EVENT_SETTING       = "setting"
EVENT_MODEL_VERSION = "model_version"

_lock = threading.Lock()


def _now(at: "datetime | None") -> str:
    return (at or datetime.now(timezone.utc)).isoformat(timespec="seconds")


def _append(records: list[dict], path: Path) -> int:
    if not records:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    return len(records)


def read_log(path: Path = AUDIT_FILE, *, event: "str | None" = None) -> list[dict]:
    """Every logged event, oldest first, optionally of one ``event`` type."""
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue   # a torn last line from a crash must not hide the rest
            if event is None or rec.get("event") == event:
                out.append(rec)
    return out


def record_planned_change(actor: str, description: str, *, at: "datetime | None" = None,
                          path: Path = AUDIT_FILE) -> None:
    """Log that a change which may alter signals was decided — the start of
    the founder's trading blackout under the conflicts of interest policy."""
    with _lock:
        _append([{"at": _now(at), "event": EVENT_PLANNED, "actor": actor,
                  "description": description}], path)


def record_settings_change(actor: str, before: dict, after: dict, *,
                           at: "datetime | None" = None, path: Path = AUDIT_FILE) -> int:
    """Log one "setting" event per shared setting whose value differs between
    `before` and `after` (keys present in either). Call it from the shared-
    settings save, with the settings as loaded and as saved. Returns the
    number of events written (0 when nothing changed)."""
    stamp = _now(at)
    recs = [{"at": stamp, "event": EVENT_SETTING, "actor": actor,
             "key": key, "old": before.get(key), "new": after.get(key)}
            for key in sorted(set(before) | set(after))
            if before.get(key) != after.get(key)]
    with _lock:
        return _append(recs, path)


def record_model_version(model_version: str, model_settings_id: str, *,
                         at: "datetime | None" = None, path: Path = AUDIT_FILE) -> bool:
    """Log the model version and settings id a universe build scored with,
    when they differ from the last logged pair. Call it after each build;
    returns True when a new event was written."""
    with _lock:
        last = next(iter(reversed(read_log(path, event=EVENT_MODEL_VERSION))), None)
        if last and (last.get("model_version"), last.get("model_settings_id")) == \
                (model_version, model_settings_id):
            return False
        _append([{"at": _now(at), "event": EVENT_MODEL_VERSION,
                  "model_version": model_version, "model_settings_id": model_settings_id}], path)
        return True
