"""
Signal history log — REC-7 / REC-11 of "Uvalu — Legal Requirements for Launch".

Append-only JSON-lines log of model-signal changes per stock, fed by
screener_compliant.signal_records(). A record is written only when a ticker's
signal_code differs from the last one logged, so the file holds the history
of badge changes (REC-7) together with the inputs, fair values, model version
and settings id that produced each one (REC-11).

Part of the legal-compliance candidate set (screener_compliant.py,
risk_compliant.py); not yet wired into the app.
"""

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

HISTORY_FILE = Path(__file__).parent / "data" / "signal_history.jsonl"

# REC-7: changes stay visible to users for at least this long. Nothing here
# deletes records; prune only entries older than this, and only deliberately.
RETENTION_DAYS = 366

_lock = threading.Lock()


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


def last_signals(path: Path = HISTORY_FILE) -> dict[str, str]:
    """{ticker: signal_code} of the newest logged record per ticker."""
    latest: dict[str, str] = {}
    for rec in _read(path):
        if rec.get("Ticker"):
            latest[rec["Ticker"]] = rec.get("signal_code")
    return latest


def record_changes(records: list[dict], path: Path = HISTORY_FILE) -> int:
    """Append each record whose signal_code changed since the ticker's last
    logged one (or that has none logged yet). "pending" is not a signal and is
    never logged. Returns the number of records written."""
    with _lock:
        prev = last_signals(path)
        new = [r for r in records
               if r.get("Ticker") and r.get("signal_code") not in (None, "pending")
               and prev.get(r["Ticker"]) != r.get("signal_code")]
        if not new:
            return 0
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            for r in new:
                fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
        return len(new)


def history_for(ticker: str, path: Path = HISTORY_FILE, *,
                days: int = RETENTION_DAYS, now: "datetime | None" = None) -> list[dict]:
    """The logged signal changes for one ticker within the last `days`,
    oldest first — what a stock page shows as its badge history."""
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    out = []
    for rec in _read(path):
        if rec.get("Ticker") != ticker:
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
