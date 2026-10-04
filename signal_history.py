"""
Signal history log — REC-7 / REC-11 of "Uvalu — Legal Requirements for Launch".

Two stores, both fed by screener_compliant.signal_records():

* An append-only JSON-lines **change log** (HISTORY_FILE). A record is written
  when a ticker's signal_code differs from the last one logged, or when the
  model version or shared settings behind it changed (``log_reason``). That is
  the badge history users see (REC-7), and it ties each logged badge to the
  model and settings that produced it (REC-11).
* A **daily snapshot** of every public signal with its inputs
  (SNAPSHOT_DIR/YYYY-MM-DD.jsonl.gz). The change log alone can't say which
  fair value and margin of safety were shown on a day the badge didn't change;
  the snapshot can, so any past screen can be reproduced on request.

Only rows of the shared public universe are stored (``public_universe`` is
True): a ticker one user added for themselves never lands in a log every user
can read.

Part of the legal-compliance candidate set (screener_compliant.py,
risk_compliant.py); not yet wired into the app.
"""

import gzip
import json
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HISTORY_FILE = Path(__file__).parent / "data" / "signal_history.jsonl"
SNAPSHOT_DIR = Path(__file__).parent / "data" / "signal_snapshots"

# REC-7: changes stay visible to users for at least this long. Nothing here
# deletes records or snapshots; prune only entries older than this, and only
# deliberately.
RETENTION_DAYS = 366

# Why a change-log record was written.
REASON_FIRST        = "first"           # first record for the ticker
REASON_SIGNAL       = "signal_change"   # signal_code changed
REASON_MODEL        = "model_change"    # same signal, new model version or settings

_lock = threading.Lock()


def _is_public(rec: dict) -> bool:
    return rec.get("public_universe") is True


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue   # a torn last line from a crash must not hide the rest
    return out


def _last_records(path: Path) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for rec in _read(path):
        if rec.get("Ticker"):
            latest[rec["Ticker"]] = rec
    return latest


def last_signals(path: Path = HISTORY_FILE) -> dict[str, str]:
    """{ticker: signal_code} of the newest logged record per ticker."""
    return {t: r.get("signal_code") for t, r in _last_records(path).items()}


def _log_reason(rec: dict, prev: "dict | None") -> "str | None":
    if prev is None:
        return REASON_FIRST
    if prev.get("signal_code") != rec.get("signal_code"):
        return REASON_SIGNAL
    if (prev.get("model_version") != rec.get("model_version")
            or prev.get("model_settings_id") != rec.get("model_settings_id")):
        return REASON_MODEL
    return None


def record_changes(records: list[dict], path: Path = HISTORY_FILE) -> int:
    """Append each public record whose signal_code, model_version or
    model_settings_id changed since the ticker's last logged one (or that has
    none logged yet), tagged with ``log_reason``. "pending" is not a signal and
    is never logged; non-public rows are skipped. Returns the number written."""
    with _lock:
        prev = _last_records(path)
        new = []
        for r in records:
            if not r.get("Ticker") or r.get("signal_code") in (None, "pending") or not _is_public(r):
                continue
            reason = _log_reason(r, prev.get(r["Ticker"]))
            if reason:
                new.append({**r, "log_reason": reason})
        if not new:
            return 0
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            for r in new:
                fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
        return len(new)


def history_for(ticker: str, path: Path = HISTORY_FILE, *,
                days: int = RETENTION_DAYS, now: "datetime | None" = None,
                signal_changes_only: bool = True) -> list[dict]:
    """The logged records for one ticker within the last `days`, oldest
    first. By default only badge changes (what a stock page shows as its
    history); ``signal_changes_only=False`` adds the model/settings changes."""
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    out = []
    for rec in _read(path):
        if rec.get("Ticker") != ticker:
            continue
        if signal_changes_only and rec.get("log_reason") == REASON_MODEL:
            continue
        try:
            ts = datetime.fromisoformat(str(rec.get("signal_computed_at")))
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts >= cutoff:
            out.append(rec)
    return out


def _snapshot_path(day: date, directory: Path) -> Path:
    return directory / f"{day.isoformat()}.jsonl.gz"


def write_daily_snapshot(records: list[dict], *, day: "date | None" = None,
                         directory: Path = SNAPSHOT_DIR) -> "Path | None":
    """REC-11: store every public signal record of `day` (default: today,
    UTC), once per day — the first universe build of the day wins, later
    calls return None. Returns the file written."""
    day = day or datetime.now(timezone.utc).date()
    rows = [r for r in records if r.get("Ticker") and _is_public(r)]
    if not rows:
        return None
    with _lock:
        path = _snapshot_path(day, directory)
        if path.exists():
            return None
        directory.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
        tmp.replace(path)
        return path


def read_snapshot(day: date, *, ticker: "str | None" = None,
                  directory: Path = SNAPSHOT_DIR) -> list[dict]:
    """The records of one day's snapshot, optionally for a single ticker;
    [] when no snapshot was taken that day."""
    path = _snapshot_path(day, directory)
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    return [r for r in rows if ticker is None or r.get("Ticker") == ticker]
