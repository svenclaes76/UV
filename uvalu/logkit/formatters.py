"""Record formatters: one-JSON-object-per-line (the stable schema, spec §11)
and a colorized human line for TTY consoles (spec §8)."""
from __future__ import annotations

import json
import logging
import time
import traceback

from uvalu.logkit import redaction

_LEVEL_NAME = {
    "DEBUG": "DEBUG", "INFO": "INFO", "WARNING": "WARN",
    "ERROR": "ERROR", "CRITICAL": "CRITICAL", "FATAL": "CRITICAL",
}

_SCHEMA_VERSION = 1
_SERVICE = "uvalu"

# Standard LogRecord attributes + the ones we surface explicitly — everything
# else on the record is treated as caller-supplied metadata.
_RESERVED = set(logging.makeLogRecord({}).__dict__) | {
    "message", "asctime", "taskName",
    "correlation_id", "user_id", "environment", "build_version",
    "event", "schema_version", "service",
}

_ANSI = {
    "DEBUG": "\033[38;5;244m",      # grey
    "INFO": "\033[38;5;39m",        # blue
    "WARN": "\033[38;5;214m",       # amber
    "ERROR": "\033[38;5;196m",      # red
    "CRITICAL": "\033[1;97;41m",    # bold white on red
}
_RESET = "\033[0m"
_DIM = "\033[2m"


def _resolve(v) -> bool:
    return bool(v() if callable(v) else v)


def _iso_utc(created: float) -> str:
    ms = int(round((created - int(created)) * 1000))
    if ms == 1000:  # rounding carry
        ms = 999
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(created)) + f".{ms:03d}Z"


def _metadata(record: logging.LogRecord, *, include_stack: bool) -> dict:
    md: dict = {
        "schema_version": _SCHEMA_VERSION,
        "environment": getattr(record, "environment", None),
        "build_version": getattr(record, "build_version", None),
    }
    if getattr(record, "event", None):
        md["event"] = record.event
    for k, v in record.__dict__.items():
        if k in _RESERVED or k.startswith("_"):
            continue
        md[k] = v
    if record.exc_info and record.exc_info[0] is not None:
        exc_type = record.exc_info[0]
        md.setdefault("error_type", getattr(exc_type, "__name__", str(exc_type)))
        if include_stack:
            # Exception args land here verbatim — scrub before they reach a sink
            # (the redaction filter only saw record.msg / extra, not this text).
            md["stack"] = redaction.scrub_text(
                "".join(traceback.format_exception(*record.exc_info)).rstrip()
            )
    return {k: v for k, v in md.items() if v is not None}


class JsonFormatter(logging.Formatter):
    """One JSON object per line — the schema in docs/logging.md."""

    def __init__(self, *, include_stack=True) -> None:
        super().__init__()
        self._include_stack = include_stack

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": _iso_utc(record.created),
            "level": _LEVEL_NAME.get(record.levelname, record.levelname),
            "service": _SERVICE,
            "module": record.name,
            "correlation_id": getattr(record, "correlation_id", None),
            "user_id": getattr(record, "user_id", None),
            "message": record.getMessage(),
            "metadata": _metadata(record, include_stack=_resolve(self._include_stack)),
        }
        return json.dumps(entry, ensure_ascii=False, default=str)


class ColorTextFormatter(logging.Formatter):
    """Readable single line: ``<ts> <LEVEL> <module> [<cid>/<user>] <msg>  ·  k=v …``

    ERROR/CRITICAL/WARN lines are wrapped in their level color so they stand out
    while scrolling; INFO/DEBUG only tint the level token. A stack trace, when
    present, is appended dimmed on following lines.
    """

    _SKIP_KV = {"schema_version", "environment", "build_version"}

    def __init__(self, *, color=True, include_stack=True) -> None:
        super().__init__()
        self._color = color
        self._include_stack = include_stack

    def format(self, record: logging.LogRecord) -> str:
        level = _LEVEL_NAME.get(record.levelname, record.levelname)
        md = _metadata(record, include_stack=_resolve(self._include_stack))
        stack = md.pop("stack", None)
        ts = _iso_utc(record.created)
        cid = (getattr(record, "correlation_id", None) or "--------")[:8]
        uid = getattr(record, "user_id", None) or "-"
        kvs = "  ".join(
            f"{k}={_render_val(v)}" for k, v in md.items() if k not in self._SKIP_KV
        )
        line = f"{ts}  {level:<8} {record.name}  [{cid}/{uid}]  {record.getMessage()}"
        if kvs:
            line += f"  ·  {kvs}"

        if _resolve(self._color):
            c = _ANSI.get(level, "")
            if level in ("WARN", "ERROR", "CRITICAL"):
                line = f"{c}{line}{_RESET}"
            elif c:
                line = line.replace(f" {level:<8} ", f" {c}{level:<8}{_RESET} ", 1)
            if stack:
                line += "\n" + _DIM + stack + _RESET
        elif stack:
            line += "\n" + stack
        return line


def _render_val(v) -> str:
    s = str(v)
    return f'"{s}"' if (" " in s or not s) else s
