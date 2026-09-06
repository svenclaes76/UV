"""``logging.Filter`` implementations, attached to the single entry handler (the
QueueHandler in async mode, one StreamHandler in synchronous/test mode) so every
record under ``uvalu.*`` passes through them exactly once.

Order matters: context -> redaction -> sampling -> fingerprint. The first two
always return True; the last two can drop a record (short-circuits the chain).
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from pathlib import Path

from uvalu.logkit import config as _config
from uvalu.logkit import redaction
from uvalu.logkit.context import correlation_id, user_id

# ── standard-attr set (values RedactionFilter must not walk) ─────────────────
_STD_ATTRS = set(logging.makeLogRecord({}).__dict__) | {
    "taskName", "correlation_id", "user_id", "environment", "build_version",
    "error_fingerprint", "error_count",
}

_BUILD_VERSION: "str | None" = None


def _build_version() -> str:
    global _BUILD_VERSION
    if _BUILD_VERSION is None:
        _BUILD_VERSION = _read_pyproject_version() or "unknown"
    return _BUILD_VERSION


def _read_pyproject_version() -> "str | None":
    try:
        import tomllib
        p = Path(__file__).resolve().parents[2] / "pyproject.toml"
        with p.open("rb") as fh:
            return tomllib.load(fh).get("project", {}).get("version")
    except Exception:
        return None


class ContextFilter(logging.Filter):
    """Inject correlation id, user id, environment and build version. Explicit
    values already on the record (passed via ``extra=``) win over context."""

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "correlation_id", None) is None:
            record.correlation_id = correlation_id()
        if getattr(record, "user_id", None) is None:
            record.user_id = user_id()
        record.environment = _config.resolve_environment()
        record.build_version = _build_version()
        return True


class RedactionFilter(logging.Filter):
    """Scrub the rendered message and every ``extra=`` value (spec §5)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        record.msg = redaction.scrub_text(msg)
        record.args = None
        for k in list(record.__dict__):
            if k in _STD_ATTRS or k.startswith("_"):
                continue
            if redaction.key_is_sensitive(k):
                record.__dict__[k] = redaction.REDACTED
            else:
                record.__dict__[k] = redaction.scrub(record.__dict__[k])
        return True


class SamplingFilter(logging.Filter):
    """Drop a configurable fraction of high-volume DEBUG/INFO records per logger
    (spec §9). WARN and above always pass. Deterministic 1-in-N keep."""

    def __init__(self) -> None:
        super().__init__()
        self._counters: dict[str, int] = {}
        self._lock = threading.Lock()

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.WARNING:
            return True
        rule = _config.current().get("sampling", {}).get(record.name)
        if not rule:
            return True
        target = rule.get("level")
        if target and record.levelname != str(target).upper():
            return True
        rate = float(rule.get("rate", 1.0))
        if rate >= 1.0:
            return True
        if rate <= 0.0:
            return False
        with self._lock:
            n = self._counters.get(record.name, 0) + 1
            self._counters[record.name] = n
        keep_every = max(1, round(1.0 / rate))
        return (n % keep_every) == 0


class FingerprintFilter(logging.Filter):
    """Group recurring exceptions (spec §10): stamp ``error_fingerprint`` +
    ``error_count`` and let only the first — then every Nth — occurrence
    through, so one root cause can't flood the log."""

    _EVERY = 10

    def __init__(self) -> None:
        super().__init__()
        self._seen: dict[str, dict] = {}
        self._lock = threading.Lock()

    def filter(self, record: logging.LogRecord) -> bool:
        if not record.exc_info:
            return True
        fp = _fingerprint(record)
        now = time.time()
        with self._lock:
            e = self._seen.get(fp)
            if e is None:
                e = self._seen[fp] = {"count": 0, "first": now, "last": now}
            e["count"] += 1
            e["last"] = now
            count = e["count"]
        record.error_fingerprint = fp
        record.error_count = count
        return count == 1 or (count % self._EVERY) == 0


def _fingerprint(record: logging.LogRecord) -> str:
    exc_type, exc_val, tb = record.exc_info
    last = tb
    while last is not None and last.tb_next is not None:
        last = last.tb_next
    frame = ""
    if last is not None:
        co = last.tb_frame.f_code
        frame = f"{co.co_filename}:{co.co_name}:{last.tb_lineno}"
    norm = re.sub(r"0x[0-9a-fA-F]+", "#", str(exc_val))
    norm = re.sub(r"\d+", "#", norm)
    basis = f"{record.name}|{getattr(exc_type, '__name__', exc_type)}|{frame}|{norm}"
    return hashlib.sha1(basis.encode()).hexdigest()[:6]


# ── process-wide singletons (attached by setup.init_logging) ────────────────
context_filter = ContextFilter()
redaction_filter = RedactionFilter()
sampling_filter = SamplingFilter()
fingerprint_filter = FingerprintFilter()


def all_filters() -> "list[logging.Filter]":
    return [context_filter, redaction_filter, sampling_filter, fingerprint_filter]


def reset() -> None:
    """Clear the mutable per-process state (test teardown)."""
    sampling_filter._counters.clear()
    with fingerprint_filter._lock:
        fingerprint_filter._seen.clear()


def error_stats() -> dict:
    """Snapshot of the recurring-exception table — the hook the future admin
    spike indicator (spec §12/§14) reads. A plain dict, not a monitoring system.
    """
    with fingerprint_filter._lock:
        return {k: dict(v) for k, v in fingerprint_filter._seen.items()}
